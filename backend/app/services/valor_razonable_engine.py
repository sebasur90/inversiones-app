"""Valor razonable por múltiplos de los pares y escenarios. Puro: sin DB ni red.

**No es un valor intrínseco** (no hay flujo de caja descontado) **ni un pronóstico de precio**: responde
"¿a qué precio cotizaría esta empresa si se le aplicaran los múltiplos que hoy pagan sus pares?". Si
todo el grupo está caro o barato, el valor razonable lo hereda, y la pantalla lo dice.

Cómo se calcula (todo en proporciones, así que no depende de la moneda del balance ni de convertir nada):

- Múltiplo de precio `M` (P/E, P/E estimado, P/Ventas, P/Valor libro, Precio/Flujo de caja libre):
  `valor = precio × M_ref ÷ M_propio`, porque `M = precio ÷ magnitud por acción`.
- EV/EBITDA: `EV_ref = M_ref × EV ÷ M_propio`, `cap_ref = EV_ref − (EV − capitalización)` y
  `valor = precio × cap_ref ÷ capitalización`. La deuda neta es `EV − capitalización`: una aproximación que
  incluye también minoritarios y preferidas, y se dice.
- `M_ref` por escenario: **pesimista = cuartil 1**, **base = mediana**, **optimista = cuartil 3** de los
  múltiplos de los pares (recortados con la misma regla de outliers que la valuación).
- Las métricas de una misma **familia** (P/E y P/E estimado; EV/EBITDA y P/Ventas) votan **una** vez: se toma
  la mediana de la familia, y después la mediana entre familias. Las que "sólo apoyan" (valor libro en
  tecnología, comunicaciones y salud) se muestran pero no deciden.

**Margen de seguridad y potencial son dos números distintos** y se informan por separado:
`margen = (valor − precio) ÷ valor` (cuánto del valor es colchón) y `potencial = (valor − precio) ÷ precio`
(cuánto subiría el precio hasta el valor). Con valor 125 y precio 100: margen 20 %, potencial +25 %.

Reglas generales (iguales al resto del módulo):
- **Faltante no es negativo**: un método sin dato se lista en "qué falta"; nunca se reemplaza por cero.
- **No aplica no es faltante**: un banco no usa EV/EBITDA; con pérdidas no hay P/E.
- **Un método inestable se muestra y se excluye**, no se oculta (valor fuera de 0,2×–5× el precio).
- Sin conclusión si no hay al menos `FAMILIAS_MINIMAS` familias con `N_MIN_PARES` pares con dato.
- Los supuestos (ajuste, exclusiones, múltiplo manual) son del usuario y se repiten en la respuesta.
- Ningún texto dice qué hacer con la acción.

`VERSION_REGLAS` viaja en la respuesta: si cambia una regla o un umbral se sube (historial de la etapa 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from . import comparador_engine as comp
from . import diagnostico_empresa_engine as de
from . import valuacion_engine as ve

VERSION_REGLAS = 1

N_MIN_PARES = 4                 # pares con dato en un método para usarlo
FAMILIAS_MINIMAS = 2            # familias que deciden para concluir
FACTOR_MIN, FACTOR_MAX = 0.2, 5.0   # un método que da menos de 0,2× o más de 5× el precio es inestable
DISPERSION_BUENA = 1.5
DISPERSION_MAXIMA = 2.0         # mayor/menor valor base entre familias; más que esto = no convergen
PARES_COMODOS = 6
AJUSTE_MAX_PCT = 50.0

PESIMISTA, BASE, OPTIMISTA = "pesimista", "base", "optimista"
ESCENARIOS = (PESIMISTA, BASE, OPTIMISTA)
NOMBRE_ESCENARIO = {PESIMISTA: "Pesimista", BASE: "Base", OPTIMISTA: "Optimista"}

ESTADO_OK, ESTADO_SIN_CONCLUSION, ESTADO_NO_APLICA, ESTADO_SIN_DATOS = "ok", "sin_conclusion", "no_aplica", "sin_datos"

# Estados de cada método
USADO, NO_APLICA, FALTA, INESTABLE, EXCLUIDO = "usado", "no_aplica", "falta", "inestable", "excluido"

LECTURA_POR_DEBAJO, LECTURA_DENTRO, LECTURA_POR_ENCIMA = "por_debajo", "dentro", "por_encima"

SALVEDAD = (
    "Es un valor relativo a los pares elegidos, no un valor intrínseco ni un pronóstico: si todo el grupo está caro "
    "o barato, este valor lo hereda."
)
LIMITES = (
    "Usa los datos de los últimos 12 meses que informa Yahoo: no hay historia de varios años, así que no se compara "
    "con los múltiplos históricos de la propia empresa.",
    "Los escenarios son los cuartiles de los múltiplos de los pares (no son pronósticos de precio).",
    "La deuda neta se aproxima con EV − capitalización (incluye minoritarios y acciones preferidas).",
    "Margen de seguridad y potencial miden lo mismo desde dos lados: el primero contra el valor, el segundo contra el precio.",
)


@dataclass(frozen=True)
class Metodo:
    clave: str
    nombre: str
    familia: str            # clave de `ve.FAMILIAS`
    ficha: str              # clave en `Ficha.valores`
    ev: bool = False        # EV/EBITDA se convierte a valor del patrimonio descontando la deuda neta


METODOS = (
    Metodo("pe", "P/E", "ganancias", "pe"),
    Metodo("forward_pe", "P/E estimado", "ganancias", "forward_pe"),
    Metodo("ev_ebitda", "EV/EBITDA", "ventas_ebitda", "ev_ebitda", ev=True),
    Metodo("ps", "P/Ventas", "ventas_ebitda", "ps"),
    Metodo("p_fcf", "Precio/Flujo de caja libre", "flujo", "fcf_yield"),
    Metodo("pb", "P/Valor libro", "patrimonio", "pb"),
)
METODO_POR_CLAVE = {m.clave: m for m in METODOS}


# ---------------------------------------------------------------------------------------------
# Entradas y salidas
# ---------------------------------------------------------------------------------------------

@dataclass
class DatosMercado:
    """Lo que el valor razonable necesita y la `Ficha` no trae: precio y tamaño en la moneda de cotización."""
    precio: float | None = None
    moneda: str | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    ratios_confiables: bool = True
    analistas: dict | None = None       # {"media", "minimo", "maximo", "n"}: referencia externa, nunca entra al cálculo


@dataclass
class Supuestos:
    ajuste_pct: float = 0.0
    excluir: tuple[str, ...] = ()
    multiplos: dict[str, float] = field(default_factory=dict)

    @property
    def por_defecto(self) -> bool:
        return self.ajuste_pct == 0 and not self.excluir and not self.multiplos


def normalizar_supuestos(raw: dict | None) -> Supuestos:
    """Valida los supuestos que escribe el usuario. Lanza `ValueError` con un mensaje para mostrar."""
    raw = raw or {}
    ajuste = raw.get("ajuste_pct", 0.0)
    if ajuste is None:
        ajuste = 0.0
    if isinstance(ajuste, bool) or not isinstance(ajuste, (int, float)):
        raise ValueError("el ajuste debe ser un número")
    if abs(ajuste) > AJUSTE_MAX_PCT:
        raise ValueError(f"el ajuste debe estar entre -{AJUSTE_MAX_PCT:.0f} % y {AJUSTE_MAX_PCT:.0f} %")
    excluir = tuple(dict.fromkeys(raw.get("excluir") or ()))
    for c in excluir:
        if c not in METODO_POR_CLAVE:
            raise ValueError(f"método desconocido: {c}")
    multiplos: dict[str, float] = {}
    for c, v in (raw.get("multiplos") or {}).items():
        if c not in METODO_POR_CLAVE:
            raise ValueError(f"método desconocido: {c}")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= ve.TOPE_MULTIPLO:
            raise ValueError(f"el múltiplo de {METODO_POR_CLAVE[c].nombre} debe estar entre 0 y {ve.TOPE_MULTIPLO:.0f}")
        multiplos[c] = float(v)
    return Supuestos(float(ajuste), excluir, multiplos)


@dataclass
class ResultadoMetodo:
    clave: str
    nombre: str
    familia: str
    familia_nombre: str
    estado: str                         # USADO | NO_APLICA | FALTA | INESTABLE | EXCLUIDO
    motivo: str = ""
    origen: str = "observado"           # observado | estimado | calculado
    decide: bool = True                 # False: la familia sólo apoya y no entra al valor
    multiplo_propio: float | None = None
    n_pares: int = 0
    referencias: dict[str, float | None] = field(default_factory=dict)   # múltiplo de referencia por escenario
    valores: dict[str, float | None] = field(default_factory=dict)       # precio implícito por escenario
    manual: bool = False
    regla: str = ""


@dataclass
class ValorFamilia:
    familia: str
    nombre: str
    decide: bool
    metodos: list[str]
    valores: dict[str, float]


@dataclass
class Escenario:
    clave: str
    nombre: str
    valor: float
    margen_seguridad: float | None      # (valor − precio) ÷ valor
    potencial: float | None             # (valor − precio) ÷ precio


@dataclass
class ValorRazonable:
    version_reglas: int
    estado: str
    mensaje: str
    modelo: str
    moneda: str | None
    precio: float | None
    escenarios: list[Escenario] = field(default_factory=list)
    metodos: list[ResultadoMetodo] = field(default_factory=list)
    familias: list[ValorFamilia] = field(default_factory=list)
    lectura: str | None = None
    lectura_texto: str = ""
    regla_lectura: str = ""
    dispersion: float | None = None
    convergen: bool | None = None
    confianza: str = "sin_datos"        # alta | media | baja | sin_datos
    regla_confianza: str = ""
    n_pares: int = 0
    supuestos: dict = field(default_factory=dict)
    faltantes: list[str] = field(default_factory=list)
    analistas: dict | None = None
    salvedad: str = SALVEDAD
    limites: list[str] = field(default_factory=lambda: list(LIMITES))


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------

def _num(v: float, decimales: int = 2) -> str:
    return f"{v:,.{decimales}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _precio(v: float, moneda: str | None) -> str:
    return f"{_num(v)} {moneda}" if moneda else _num(v)


def _pct(v: float) -> str:
    return f"{v * 100:.1f} %".replace(".", ",")


def _veces(v: float) -> str:
    return f"{_num(v, 1)}x"


def multiplo_de(m: Metodo, valores: dict[str, float | None]) -> float | None:
    """El múltiplo de un método en una ficha, o None. Precio/FCF es la inversa del rendimiento del FCF."""
    v = valores.get(m.ficha)
    if v is None:
        return None
    if m.clave == "p_fcf":
        return 1.0 / v if v > 0 and 1.0 / v <= ve.TOPE_MULTIPLO else None
    return v if v > 0 else None


def _referencias(valores_pares: list[float]) -> dict[str, float]:
    w = ve.winsorizar(valores_pares)
    q1, q3 = ve._cuartiles(w)
    return {PESIMISTA: q1, BASE: median(w), OPTIMISTA: q3}


def _valor_implicito(m: Metodo, m_ref: float, m_propio: float, precio: float,
                     mercado: DatosMercado) -> float | None:
    if m.ev:
        ev, cap = mercado.enterprise_value, mercado.market_cap
        if not ev or not cap or ev <= 0 or cap <= 0:
            return None
        cap_ref = m_ref * ev / m_propio - (ev - cap)
        return precio * cap_ref / cap if cap_ref > 0 else None
    return precio * m_ref / m_propio


def _regla_metodo(m: Metodo) -> str:
    if m.ev:
        return ("valor = precio × (EV/EBITDA de referencia × EV ÷ EV/EBITDA propio − deuda neta) ÷ capitalización; "
                "deuda neta ≈ EV − capitalización")
    return f"valor = precio × {m.nombre} de referencia ÷ {m.nombre} propio"


def _evaluar_metodo(m: Metodo, modelo: str, ficha: ve.Ficha, pares: list[ve.Ficha], mercado: DatosMercado,
                    supuestos: Supuestos, apoyan: frozenset[str]) -> ResultadoMetodo:
    r = ResultadoMetodo(
        clave=m.clave, nombre=m.nombre, familia=m.familia, familia_nombre=ve.FAMILIAS[m.familia],
        estado=FALTA, origen=de.origen_metrica(m.ficha, ficha), decide=m.familia not in apoyan,
        regla=_regla_metodo(m),
    )
    # 1. ¿Es pertinente para este tipo de negocio?
    if m.ficha not in comp.METRICAS_POR_MODELO[modelo]:
        r.estado = NO_APLICA
        r.motivo = comp.MOTIVO_NO_APLICA.get(m.ficha, "no se usa para este tipo de negocio")
        return r
    # 2. ¿Existe para esta empresa?
    if m.ficha in ficha.descartadas_moneda:
        r.estado = NO_APLICA
        r.motivo = "el balance está en otra moneda que la cotización: Yahoo mezcla monedas y el múltiplo no es confiable"
        return r
    if ficha.sin_ganancias and m.clave in ("pe", "forward_pe"):
        r.estado = NO_APLICA
        r.motivo = "la empresa no tiene ganancias en los últimos 12 meses: el P/E no existe"
        return r
    y = ficha.valores.get("fcf_yield")
    if m.clave == "p_fcf" and y is not None and y <= 0:
        r.estado = NO_APLICA
        r.motivo = "el flujo de caja libre es negativo o nulo: no hay múltiplo"
        return r
    propio = multiplo_de(m, ficha.valores)
    r.multiplo_propio = propio
    if m.clave in supuestos.excluir:
        r.estado = EXCLUIDO
        r.motivo = "lo excluiste en tus supuestos"
        return r
    if propio is None:
        r.motivo = "Yahoo no informó este dato de la empresa (o su valor no es utilizable)"
        return r
    precio = mercado.precio
    if precio is None or precio <= 0:
        r.motivo = "no hay precio actual en los datos de Yahoo"
        return r
    if m.ev and not (mercado.enterprise_value and mercado.market_cap):
        r.motivo = "Yahoo no informó el valor de empresa (EV) o la capitalización"
        return r
    # 3. ¿Hay suficientes pares con dato?
    del_grupo = [v for v in (multiplo_de(m, p.valores) for p in pares) if v is not None]
    r.n_pares = len(del_grupo)
    if len(del_grupo) < N_MIN_PARES:
        r.motivo = f"sólo {len(del_grupo)} pares con dato; hacen falta {N_MIN_PARES}"
        return r
    # 4. Múltiplo de referencia por escenario, con los supuestos del usuario
    refs = _referencias(del_grupo)
    manual = supuestos.multiplos.get(m.clave)
    if manual is not None:
        base = refs[BASE]
        refs = {e: manual * (refs[e] / base if base > 0 else 1.0) for e in ESCENARIOS}
        refs[BASE] = manual
        r.manual = True
    else:
        factor = 1.0 + supuestos.ajuste_pct / 100.0
        refs = {e: refs[e] * factor for e in ESCENARIOS}
    r.referencias = refs
    r.valores = {e: _valor_implicito(m, refs[e], propio, precio, mercado) for e in ESCENARIOS}
    # 5. ¿El resultado es utilizable?
    base_v = r.valores[BASE]
    if any(v is None for v in r.valores.values()):
        r.estado = INESTABLE
        r.motivo = "con la deuda neta de la empresa, el valor del patrimonio no resulta positivo en algún escenario"
        return r
    if not FACTOR_MIN <= base_v / precio <= FACTOR_MAX:
        r.estado = INESTABLE
        r.motivo = (f"da {_veces(base_v / precio)} el precio actual, fuera de {_veces(FACTOR_MIN)}–{_veces(FACTOR_MAX)}: "
                    "se muestra pero no entra al valor")
        return r
    r.estado = USADO
    return r


# ---------------------------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------------------------

def _confianza(n_familias: int, dispersion: float, min_pares: int, confianza_datos: str | None) -> tuple[str, str]:
    puntos = (n_familias >= 3) + (dispersion <= DISPERSION_BUENA) + (min_pares >= PARES_COMODOS)
    nivel = {3: "alta", 2: "media"}.get(puntos, "baja")
    notas = [
        f"{n_familias} familias de múltiplos ({'suma' if n_familias >= 3 else 'no suma'} 1 punto: hacen falta 3)",
        f"los métodos difieren {_veces(dispersion)} entre sí ({'suma' if dispersion <= DISPERSION_BUENA else 'no suma'} "
        f"1 punto: hasta {_veces(DISPERSION_BUENA)})",
        f"mínimo de {min_pares} pares por método ({'suma' if min_pares >= PARES_COMODOS else 'no suma'} 1 punto: "
        f"{PARES_COMODOS} o más)",
    ]
    if dispersion > DISPERSION_MAXIMA:
        nivel = "baja"
        notas.append(f"los métodos no convergen (más de {_veces(DISPERSION_MAXIMA)} de diferencia): confianza baja")
    if confianza_datos in ("baja", "sin_datos"):
        nivel = "baja"
        notas.append("la confianza de los datos del diagnóstico es baja: limita ésta")
    elif confianza_datos == "media" and nivel == "alta":
        nivel = "media"
        notas.append("la confianza de los datos del diagnóstico es media: limita ésta")
    return nivel, "; ".join(notas)


def _lectura(precio: float, esc: dict[str, float], moneda: str | None) -> tuple[str, str, str]:
    pes, base, opt = esc[PESIMISTA], esc[BASE], esc[OPTIMISTA]
    regla = (f"precio actual {_precio(precio, moneda)} contra el rango entre el escenario pesimista "
             f"({_precio(pes, moneda)}) y el optimista ({_precio(opt, moneda)})")
    if precio < pes:
        return LECTURA_POR_DEBAJO, (
            "El precio actual está por debajo del escenario pesimista: con los múltiplos que hoy pagan sus pares, "
            "cotiza más barato que todo el rango."), regla
    if precio > opt:
        return LECTURA_POR_ENCIMA, (
            "El precio actual está por encima del escenario optimista: con los múltiplos que hoy pagan sus pares, "
            "cotiza más caro que todo el rango."), regla
    lado = "por debajo" if precio < base else "por encima" if precio > base else "en"
    detalle = "en el valor base" if lado == "en" else f"{lado} del valor base"
    return LECTURA_DENTRO, (
        f"El precio actual está dentro del rango entre el escenario pesimista y el optimista, {detalle}."), regla


def _supuestos_dict(s: Supuestos) -> dict:
    return {"ajuste_pct": s.ajuste_pct, "excluir": list(s.excluir), "multiplos": dict(s.multiplos),
            "por_defecto": s.por_defecto}


def valor_razonable(
    ficha: ve.Ficha | None,
    pares: list[ve.Ficha],
    mercado: DatosMercado,
    supuestos: Supuestos | None = None,
    confianza_datos: str | None = None,
) -> ValorRazonable:
    """Valor razonable y escenarios de `ficha` contra el grupo `pares`. Determinista."""
    supuestos = supuestos or Supuestos()
    sup = _supuestos_dict(supuestos)
    if ficha is None:
        return ValorRazonable(
            VERSION_REGLAS, ESTADO_SIN_DATOS, "Todavía no hay fundamentales de este emisor: la ingesta los trae en su "
            "próxima corrida.", comp.MODELO_OPERATIVO, mercado.moneda, mercado.precio, supuestos=sup,
            faltantes=["fundamentales del emisor"], analistas=mercado.analistas)
    modelo = comp.modelo_negocio(ficha.sector, ficha.es_etf)
    if modelo == comp.MODELO_ETF:
        return ValorRazonable(
            VERSION_REGLAS, ESTADO_NO_APLICA, "Un ETF no tiene un valor razonable por múltiplos: es una canasta de otras "
            "empresas. Se evalúa por su valuación y la confianza de sus datos.", modelo, mercado.moneda,
            mercado.precio, supuestos=sup, analistas=mercado.analistas)

    apoyan = ve.familias_que_solo_apoyan(ficha.sector, ficha.es_etf)
    metodos = [_evaluar_metodo(m, modelo, ficha, pares, mercado, supuestos, apoyan) for m in METODOS]
    faltantes = [f"{r.nombre}: {r.motivo}" for r in metodos if r.estado == FALTA]
    if mercado.precio is None or mercado.precio <= 0:
        faltantes = ["precio actual"] + [f for f in faltantes if "precio actual" not in f]

    # Por familia: mediana de los métodos usados
    familias: list[ValorFamilia] = []
    for clave, nombre in ve.FAMILIAS.items():
        usados = [r for r in metodos if r.familia == clave and r.estado == USADO]
        if not usados:
            continue
        familias.append(ValorFamilia(
            clave, nombre, clave not in apoyan, [r.clave for r in usados],
            {e: median([r.valores[e] for r in usados]) for e in ESCENARIOS},
        ))
    deciden = [f for f in familias if f.decide]
    res = ValorRazonable(
        VERSION_REGLAS, ESTADO_SIN_CONCLUSION, "", modelo, mercado.moneda, mercado.precio, metodos=metodos,
        familias=familias, supuestos=sup, faltantes=faltantes, analistas=mercado.analistas,
        n_pares=len(pares),
    )
    if len(deciden) < FAMILIAS_MINIMAS:
        res.mensaje = (
            f"No alcanza para estimar un valor: hacen falta al menos {FAMILIAS_MINIMAS} familias de múltiplos con "
            f"{N_MIN_PARES} o más pares con dato y hay {len(deciden)}. Un valor basado en una sola mirada no es concluyente.")
        return res

    precio = mercado.precio
    valores = {e: median([f.valores[e] for f in deciden]) for e in ESCENARIOS}
    res.escenarios = [
        Escenario(
            e, NOMBRE_ESCENARIO[e], valores[e],
            (valores[e] - precio) / valores[e] if valores[e] > 0 else None,
            (valores[e] - precio) / precio,
        )
        for e in ESCENARIOS
    ]
    bases = [f.valores[BASE] for f in deciden]
    res.dispersion = max(bases) / min(bases) if min(bases) > 0 else None
    res.convergen = res.dispersion is not None and res.dispersion <= DISPERSION_MAXIMA
    min_pares = min(r.n_pares for r in metodos if r.estado == USADO and r.decide)
    res.confianza, res.regla_confianza = _confianza(
        len(deciden), res.dispersion if res.dispersion is not None else float("inf"), min_pares, confianza_datos)
    res.estado = ESTADO_OK
    res.mensaje = "Valor razonable estimado con los múltiplos de los pares."
    res.lectura, res.lectura_texto, res.regla_lectura = _lectura(precio, valores, mercado.moneda)
    return res
