"""Motor de evaluación del Centro de Decisiones: puntajes por dimensión, puntaje de orden y conclusión. Puro.

Junta lo que la app ya calcula (diagnóstico de empresa, valor razonable, lectura técnica, riesgo de la serie
semanal, impacto en la cartera) en **cinco dimensiones** con un puntaje 0–100 cada una:

- **Fundamentales**: calidad + crecimiento + solidez del diagnóstico de empresa (que ya cuenta familias de
  métricas, así que no se re-pondera nada: P/E y P/E estimado no votan dos veces).
- **Valoración**: la dimensión valuación del diagnóstico (percentil favorable: 100 = la más barata del
  grupo). El valor razonable sale de **los mismos múltiplos de los pares**, así que no suma un voto propio
  (sería contar dos veces lo mismo): sólo confirma o contradice con ±`AJUSTE_VALOR_RAZONABLE` puntos.
- **Riesgo** (más alto = menos riesgo): volatilidad anual y caída máxima de la serie semanal, y beta.
- **Técnico**: tendencia, momentum y fuerza relativa de la lectura técnica. Es una lectura de corto plazo y
  **nunca** toca las otras dimensiones.
- **Encaje con la cartera**: observaciones de concentración del simulador (umbrales de Salud de cartera) y,
  según el objetivo, dividendo o diversificación.

Reglas generales:
- **Faltante no es cero.** Una dimensión sin datos queda en `None` y sale del promedio; su peso no se
  reparte en silencio: baja la *cobertura*, y con cobertura < `COBERTURA_MINIMA` el orden es "incompleto"
  (sin número).
- **No aplica no es faltante.** Un ETF no tiene fundamentales de negocio; no lo penaliza.
- **Banderas críticas** se muestran siempre, aunque el puntaje de orden sea alto.
- Los pesos (`PESOS`) son una **decisión de diseño configurable**, no una verdad financiera: dependen del
  enfoque y el horizonte, se muestran y el usuario puede cambiarlos.
- El puntaje sirve para **ordenar** oportunidades. Nunca es una orden de operar: los textos describen,
  no indican qué hacer (un test lo garantiza).

`VERSION_REGLAS` viaja en cada evaluación y se guarda en cada decisión: si cambia una regla o un umbral, se
sube, para no comparar puntajes de reglas distintas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

VERSION_REGLAS = 1

FUNDAMENTALES, VALORACION, RIESGO, TECNICO, ENCAJE = "fundamentales", "valoracion", "riesgo", "tecnico", "encaje"
DIMENSIONES = (FUNDAMENTALES, VALORACION, RIESGO, TECNICO, ENCAJE)
NOMBRE = {
    FUNDAMENTALES: "Fundamentales", VALORACION: "Valoración", RIESGO: "Riesgo",
    TECNICO: "Técnico", ENCAJE: "Encaje con tu cartera",
}

ENFOQUES = ("fundamental", "tecnico", "combinado")

# Pesos por enfoque y horizonte (suman 100). Punto de partida documentado en docs/centro-decisiones.md.
# A más largo el horizonte, menos pesa el técnico (es una lectura de semanas, no de años).
PESOS: dict[str, dict[str, dict[str, int]]] = {
    "fundamental": {
        "corto":   {FUNDAMENTALES: 25, VALORACION: 25, RIESGO: 25, TECNICO: 15, ENCAJE: 10},
        "mediano": {FUNDAMENTALES: 30, VALORACION: 30, RIESGO: 20, TECNICO: 10, ENCAJE: 10},
        "largo":   {FUNDAMENTALES: 35, VALORACION: 30, RIESGO: 20, TECNICO: 5, ENCAJE: 10},
    },
    "tecnico": {
        "corto":   {FUNDAMENTALES: 5, VALORACION: 10, RIESGO: 25, TECNICO: 50, ENCAJE: 10},
        "mediano": {FUNDAMENTALES: 10, VALORACION: 15, RIESGO: 25, TECNICO: 40, ENCAJE: 10},
        "largo":   {FUNDAMENTALES: 20, VALORACION: 20, RIESGO: 25, TECNICO: 25, ENCAJE: 10},
    },
    "combinado": {
        "corto":   {FUNDAMENTALES: 15, VALORACION: 20, RIESGO: 25, TECNICO: 30, ENCAJE: 10},
        "mediano": {FUNDAMENTALES: 25, VALORACION: 25, RIESGO: 20, TECNICO: 20, ENCAJE: 10},
        "largo":   {FUNDAMENTALES: 30, VALORACION: 30, RIESGO: 20, TECNICO: 10, ENCAJE: 10},
    },
}
# La tolerancia al riesgo (si el usuario la definió) escala el peso de la dimensión Riesgo.
FACTOR_TOLERANCIA = {"baja": 1.5, "media": 1.0, "alta": 0.5, None: 1.0}

COBERTURA_MINIMA = 0.60
NIVEL_PUNTAJE = {"bien": 75.0, "neutro": 50.0, "atencion": 35.0, "riesgo": 15.0}
AJUSTE_VALOR_RAZONABLE = 5.0

# Riesgo: bandas (puntaje por tramo)
VOL_BAJA, VOL_ALTA = 0.25, 0.40                # volatilidad anual
CAIDA_MODERADA, CAIDA_FUERTE = -0.30, -0.50    # caída máxima en la serie
BETA_BAJA, BETA_ALTA = 1.0, 1.5

# Técnico
PUNTAJE_TENDENCIA = {"alcista": 70.0, "mixta": 50.0, "bajista": 30.0}
PUNTAJE_MOMENTUM = {"neutral": 55.0, "sobrecompra": 40.0, "sobreventa": 45.0}
PUNTAJE_FUERZA = {"mejor": 65.0, "parecida": 50.0, "peor": 35.0}

# Encaje
ENCAJE_BASE = 60.0
PENALIDAD_OBS = {"revisar": 30.0, "atencion": 15.0}
DIVIDENDO_INGRESOS = 0.02       # fracción anual (2 %): desde acá cuenta como "genera ingresos"

# Banderas
DIAS_DATO_VIEJO = 21
DIAS_PRECIO_VIEJO = 7           # ~5 ruedas
CAIDA_INGRESOS = -0.02
PAYOUT_NO_CUBIERTO = 1.0
RIESGO_BAJO_PARA_TOLERANCIA = 40.0

# Conclusión
DIFERENCIA_RELEVANTE = 10.0     # puntos de orden para hablar de una ventaja
ORDEN_INTERESANTE = 60.0
VALORACION_EXIGENTE = 35.0
RIESGO_ELEVADO = 35.0

DATOS_INSUFICIENTES, MAS_ATRACTIVA, INTERESANTE_PENDIENTE = "datos_insuficientes", "alternativa_mas_atractiva", "interesante_pendiente"
VALORACION_EXIGENTE_T, RIESGO_ELEVADO_T, NINGUNA_SUPERIOR = "valoracion_exigente", "riesgo_elevado", "ninguna_superior"
TITULOS = {
    DATOS_INSUFICIENTES: "Datos insuficientes para concluir",
    MAS_ATRACTIVA: "Alternativa relativamente más atractiva",
    INTERESANTE_PENDIENTE: "Oportunidad interesante, pendiente de confirmar condiciones",
    VALORACION_EXIGENTE_T: "Valoración exigente",
    RIESGO_ELEVADO_T: "Riesgo elevado para los criterios elegidos",
    NINGUNA_SUPERIOR: "Ninguna alternativa claramente superior",
}
REGLA_CONCLUSION = (
    "en orden: (1) datos insuficientes si el orden del activo es incompleto; (2) riesgo elevado si tiene una "
    f"bandera crítica de severidad alta o Riesgo < {RIESGO_ELEVADO:.0f}; (3) alternativa más atractiva si el "
    f"mejor orden supera al segundo por ≥ {DIFERENCIA_RELEVANTE:.0f} puntos, sin banderas críticas, con firmeza "
    "media o alta y el mismo ganador con los pesos de los tres enfoques; (4) valoración exigente si Valoración < "
    f"{VALORACION_EXIGENTE:.0f}; (5) interesante pendiente si el orden es ≥ {ORDEN_INTERESANTE:.0f} y el técnico o la "
    "valoración no acompañan; (6) ninguna claramente superior en el resto de los casos"
)

ALTA, MEDIA, BAJA = "alta", "media", "baja"


@dataclass
class Insumos:
    """Todo lo que el motor necesita de un activo (dicts ya calculados por los otros módulos)."""
    ticker: str
    es_etf: bool = False
    diagnostico: dict | None = None         # `asdict(Diagnostico)` de diagnostico_empresa_engine
    valor_razonable: dict | None = None     # salida de valor_razonable_analytics.calcular (o None)
    tecnico: dict | None = None             # salida de lectura_tecnica_engine.leer (o None = sin serie)
    riesgo: dict | None = None              # {volatilidad, caida_maxima, beta, semanas, fecha, moneda_serie}
    encaje: dict | None = None              # {observaciones, sin_cartera, sector_nuevo, pais_nuevo, en_cartera}
    metricas: dict = field(default_factory=dict)   # valores limpios de la ficha (div_yield, crec_ingresos…)
    extra: dict = field(default_factory=dict)      # payout, beta, liquidez (Ficha.extra)
    sin_ganancias: bool = False
    fecha_dato: date | None = None
    fecha_precio: date | None = None
    moneda_instrumento: str | None = None
    sigue_dolar: bool = False


@dataclass
class Factor:
    texto: str
    efecto: float           # puntos que suma (+) o resta (−) a la dimensión respecto de 50
    regla: str
    origen: str = "calculado"   # observado | estimado | calculado


@dataclass
class DimensionEval:
    clave: str
    nombre: str
    puntaje: float | None
    estado: str             # "evaluada" | "sin_datos" | "no_aplica"
    resumen: str
    regla: str
    factores: list[Factor] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)


@dataclass
class Bandera:
    clave: str
    texto: str
    regla: str
    severidad: str          # "alta" | "media"


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------

def _pct(v: float, dec: int = 0) -> str:
    return f"{v * 100:.{dec}f} %".replace(".", ",")


def _num(v: float, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def _media(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def normalizar_pesos(crudo) -> dict[str, int]:
    """Pesos del usuario: un entero 0–100 por dimensión, al menos uno > 0. `ValueError` si no valen."""
    if not isinstance(crudo, dict):
        raise ValueError("los pesos deben ser un objeto {dimensión: peso}")
    salida = {}
    for d in DIMENSIONES:
        v = crudo.get(d, 0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
            raise ValueError(f"el peso de {NOMBRE[d]} debe estar entre 0 y 100")
        salida[d] = int(round(v))
    if sum(salida.values()) <= 0:
        raise ValueError("al menos una dimensión tiene que tener peso")
    return salida


def pesos_para(prefs: dict) -> dict[str, float]:
    """Pesos efectivos: los del usuario si los definió, si no la tabla; con la tolerancia aplicada a Riesgo."""
    base = prefs.get("pesos") or PESOS[prefs.get("enfoque", "combinado")][prefs.get("horizonte", "largo")]
    pesos = {d: float(base.get(d, 0)) for d in DIMENSIONES}
    pesos[RIESGO] *= FACTOR_TOLERANCIA.get(prefs.get("tolerancia"), 1.0)
    return pesos


def _dim_diag(diag: dict | None, clave: str) -> dict | None:
    if not diag:
        return None
    return next((d for d in diag.get("dimensiones", []) if d.get("clave") == clave), None)


def _puntaje_diag(d: dict) -> float | None:
    """Percentil favorable cuando la dimensión lo tiene; si no, el nivel en palabras traducido."""
    if d is None or d.get("nivel") in ("sin_datos", "no_aplica"):
        return None
    if d.get("percentil") is not None:
        return float(d["percentil"])
    return NIVEL_PUNTAJE.get(d.get("nivel"))


# ---------------------------------------------------------------------------------------------
# Dimensiones
# ---------------------------------------------------------------------------------------------

REGLA_FUNDAMENTALES = (
    "promedio de calidad, crecimiento y solidez del diagnóstico de empresa; cada una vale su percentil favorable "
    "dentro del grupo de pares (100 = la mejor) o, sin percentil, su nivel: bien 75, neutro 50, atención 35, "
    "riesgo 15. Las que no tienen datos no entran al promedio"
)


def _fundamentales(ins: Insumos) -> DimensionEval:
    if ins.es_etf:
        return DimensionEval(FUNDAMENTALES, NOMBRE[FUNDAMENTALES], None, "no_aplica",
                             "No aplica a un ETF: sus fundamentales son los de las empresas que contiene.",
                             REGLA_FUNDAMENTALES)
    factores, puntajes, faltantes = [], [], []
    for clave, nombre in (("calidad", "Calidad"), ("crecimiento", "Crecimiento"), ("solidez", "Solidez financiera")):
        d = _dim_diag(ins.diagnostico, clave)
        p = _puntaje_diag(d) if d else None
        if p is None:
            faltantes.append(f"{nombre}: {(d or {}).get('resumen') or 'sin datos'}")
            continue
        puntajes.append(p)
        detalle = f"percentil {p:.0f}" if d.get("percentil") is not None else f"nivel {d.get('nivel')}"
        factores.append(Factor(f"{nombre}: {d.get('estado')} ({detalle}).", (p - 50) / 3, d.get("regla") or "", "calculado"))
        for f in d.get("faltantes") or []:
            faltantes.append(f"{nombre}: falta {f}")
    p = _media(puntajes)
    if p is None:
        return DimensionEval(FUNDAMENTALES, NOMBRE[FUNDAMENTALES], None, "sin_datos",
                             "No hay datos suficientes de calidad, crecimiento ni solidez.", REGLA_FUNDAMENTALES,
                             faltantes=faltantes)
    return DimensionEval(FUNDAMENTALES, NOMBRE[FUNDAMENTALES], round(p, 1), "evaluada",
                         f"Promedio de {len(puntajes)} de 3 sub-dimensiones.", REGLA_FUNDAMENTALES, factores, faltantes)


REGLA_VALORACION = (
    "percentil favorable de la valuación contra los pares (100 = la más barata del grupo); el valor razonable por "
    f"múltiplos de pares sólo ajusta ±{AJUSTE_VALOR_RAZONABLE:.0f} puntos (precio por debajo / por encima del rango) "
    "porque sale de los mismos múltiplos. Sin percentil: por debajo del rango 65, dentro 50, por encima 35"
)


def _valoracion(ins: Insumos) -> DimensionEval:
    d = _dim_diag(ins.diagnostico, "valuacion")
    vr = ins.valor_razonable if ins.valor_razonable and ins.valor_razonable.get("estado") == "ok" else None
    factores, faltantes = [], list((d or {}).get("faltantes") or [])
    p = None
    if d is not None and d.get("percentil") is not None and d.get("nivel") not in ("sin_datos", "no_aplica"):
        p = float(d["percentil"])
        factores.append(Factor(f"Contra sus pares: {d.get('estado')} (percentil {p:.0f}).", (p - 50) / 3,
                               d.get("regla") or "", "calculado"))
        if d.get("nivel") == "atencion":
            factores.append(Factor("La lectura advierte que lo barato puede tener motivo (fundamentos débiles).", 0.0,
                                   d.get("regla") or "", "calculado"))
    if vr:
        lectura = vr.get("lectura")
        ajuste = {"por_debajo": AJUSTE_VALOR_RAZONABLE, "por_encima": -AJUSTE_VALOR_RAZONABLE}.get(lectura, 0.0)
        if p is None:
            p = {"por_debajo": 65.0, "dentro": 50.0, "por_encima": 35.0}.get(lectura)
        elif ajuste:
            p += ajuste
        if lectura:
            factores.append(Factor(vr.get("lectura_texto") or f"Valor razonable: {lectura}.", ajuste,
                                   vr.get("regla_lectura") or "", "calculado"))
    elif ins.valor_razonable:
        faltantes.append(f"Valor razonable: {ins.valor_razonable.get('mensaje') or 'sin conclusión'}")
    if p is None:
        return DimensionEval(VALORACION, NOMBRE[VALORACION], None, "sin_datos",
                             "No hay múltiplos suficientes para comparar el precio con sus pares.", REGLA_VALORACION,
                             factores, faltantes)
    return DimensionEval(VALORACION, NOMBRE[VALORACION], round(_clamp(p), 1), "evaluada",
                         "Precio relativo a sus pares: no mide la calidad del negocio.", REGLA_VALORACION, factores, faltantes)


REGLA_RIESGO = (
    f"promedio de: volatilidad anual (≤ {_pct(VOL_BAJA)} → 75, hasta {_pct(VOL_ALTA)} → 50, más → 25), caída máxima "
    f"de la serie (menos de {_pct(-CAIDA_MODERADA)} → 75, hasta {_pct(-CAIDA_FUERTE)} → 50, más → 25) y beta "
    f"(≤ {_num(BETA_BAJA)} → 70, hasta {_num(BETA_ALTA)} → 50, más → 30). Más alto = menos riesgo"
)


def _riesgo(ins: Insumos, moneda_pref: str) -> DimensionEval:
    r = ins.riesgo or {}
    factores, puntajes, faltantes = [], [], []
    vol = r.get("volatilidad")
    if vol is not None:
        p = 75.0 if vol <= VOL_BAJA else 50.0 if vol <= VOL_ALTA else 25.0
        puntajes.append(p)
        factores.append(Factor(f"Volatilidad anual {_pct(vol)} ({r.get('semanas')} semanas, en {r.get('moneda_serie') or 'USD'}).",
                               (p - 50) / 3, REGLA_RIESGO))
    else:
        faltantes.append("volatilidad (sin serie semanal de precios)")
    caida = r.get("caida_maxima")
    if caida is not None:
        p = 75.0 if caida > CAIDA_MODERADA else 50.0 if caida > CAIDA_FUERTE else 25.0
        puntajes.append(p)
        factores.append(Factor(f"Caída máxima en la serie: {_pct(caida)}.", (p - 50) / 3, REGLA_RIESGO))
    else:
        faltantes.append("caída máxima (sin serie semanal de precios)")
    beta = r.get("beta")
    if beta is not None:
        p = 70.0 if beta <= BETA_BAJA else 50.0 if beta <= BETA_ALTA else 30.0
        puntajes.append(p)
        factores.append(Factor(f"Beta {_num(beta, 2)} (sensibilidad al mercado, informada por Yahoo).", (p - 50) / 3,
                               REGLA_RIESGO, "observado"))
    elif not ins.es_etf:
        faltantes.append("beta")
    if moneda_pref == "USD" and ins.moneda_instrumento == "ARS" and not ins.sigue_dolar:
        factores.append(Factor("Cotiza en pesos y no sigue al dólar: medido en USD suma el riesgo del tipo de cambio.",
                               0.0, "riesgo de divisa: informativo, no cambia el puntaje"))
    elif moneda_pref == "ARS" and ins.sigue_dolar:
        factores.append(Factor("Sigue al dólar: medido en pesos, su precio sube y baja también con el MEP.",
                               0.0, "riesgo de divisa: informativo, no cambia el puntaje"))
    p = _media(puntajes)
    if p is None:
        return DimensionEval(RIESGO, NOMBRE[RIESGO], None, "sin_datos", "No hay serie de precios ni beta para medir el riesgo.",
                             REGLA_RIESGO, factores, faltantes)
    return DimensionEval(RIESGO, NOMBRE[RIESGO], round(p, 1), "evaluada",
                         f"Promedio de {len(puntajes)} medidas de riesgo histórico (no predice el futuro).",
                         REGLA_RIESGO, factores, faltantes)


REGLA_TECNICO = (
    "promedio de: tendencia contra la SMA(50) (alcista 70, mixta 50, bajista 30), RSI(14) (neutral 55, sobreventa 45, "
    "sobrecompra 40) y fuerza relativa contra su índice a 63 ruedas (mejor 65, parecida 50, peor 35). Es una lectura "
    "de corto plazo: no cambia las conclusiones de fundamentales"
)


def _tecnico(ins: Insumos) -> DimensionEval:
    t = ins.tecnico
    if not t or t.get("ultimo_cierre") is None:
        return DimensionEval(TECNICO, NOMBRE[TECNICO], None, "sin_datos",
                             "No hay serie diaria de precios: el análisis técnico corre sobre la cartera y la watchlist.",
                             REGLA_TECNICO, faltantes=["serie diaria (agregá el ticker a la watchlist para que la app la baje)"])
    factores, puntajes, faltantes = [], [], []
    tend = t.get("tendencia")
    if tend:
        p = PUNTAJE_TENDENCIA[tend["estado"]]
        puntajes.append(p)
        factores.append(Factor(f"Tendencia {tend['estado']}: precio {_num(tend['distancia_pct'])} % contra su media de "
                               f"{tend['periodo_sma']} ruedas.", (p - 50) / 3, REGLA_TECNICO))
    else:
        faltantes.append("tendencia (menos de 60 ruedas de historia)")
    mom = t.get("momentum")
    if mom:
        p = PUNTAJE_MOMENTUM[mom["estado"]]
        puntajes.append(p)
        factores.append(Factor(f"RSI {_num(mom['rsi'], 0)} ({mom['estado']}).", (p - 50) / 3, REGLA_TECNICO))
    fr = t.get("fuerza_relativa")
    if fr:
        p = PUNTAJE_FUERZA[fr["estado"]]
        puntajes.append(p)
        factores.append(Factor(f"Fuerza relativa {fr['estado']}: {_num(fr['diferencia_puntos'])} puntos contra el índice "
                               f"en {fr['ruedas']} ruedas.", (p - 50) / 3, REGLA_TECNICO))
    else:
        faltantes.append("fuerza relativa (el índice de referencia todavía no está en la base)")
    p = _media(puntajes)
    if p is None:
        return DimensionEval(TECNICO, NOMBRE[TECNICO], None, "sin_datos", "La serie es demasiado corta.", REGLA_TECNICO,
                             factores, faltantes)
    return DimensionEval(TECNICO, NOMBRE[TECNICO], round(p, 1), "evaluada", "Momento del precio, no calidad ni valor.",
                         REGLA_TECNICO, factores, faltantes)


REGLA_ENCAJE = (
    f"parte de {ENCAJE_BASE:.0f}; cada observación de concentración del simulador resta (revisar −{PENALIDAD_OBS['revisar']:.0f}, "
    f"atención −{PENALIDAD_OBS['atencion']:.0f}; umbrales de Salud de cartera). Con objetivo ingresos: dividendo ≥ "
    f"{_pct(DIVIDENDO_INGRESOS)} suma 15, sin dividendo resta 15. Con objetivo diversificación: sector o país "
    "que no tenés suman 10 cada uno; un emisor que ya tenés resta 10"
)


def _encaje(ins: Insumos, objetivo: str) -> DimensionEval:
    e = ins.encaje
    if not e or e.get("sin_cartera"):
        return DimensionEval(ENCAJE, NOMBRE[ENCAJE], None, "no_aplica",
                             "No hay una cartera valuada con la cual comparar.", REGLA_ENCAJE)
    p, factores, faltantes = ENCAJE_BASE, [], []
    for o in e.get("observaciones") or []:
        resta = PENALIDAD_OBS.get(o.get("nivel"))
        if resta:
            p -= resta
            factores.append(Factor(o.get("texto", ""), -resta, o.get("regla") or REGLA_ENCAJE))
    if objetivo == "ingresos":
        dy = ins.metricas.get("div_yield")
        if dy is None:
            faltantes.append("rendimiento por dividendo (Yahoo no lo informa: puede no pagar)")
        elif dy >= DIVIDENDO_INGRESOS:
            p += 15
            factores.append(Factor(f"Rinde {_pct(dy, 1)} anual por dividendo.", 15, REGLA_ENCAJE, "observado"))
        else:
            p -= 15
            factores.append(Factor(f"El dividendo ({_pct(dy, 1)}) no alcanza el {_pct(DIVIDENDO_INGRESOS)} del objetivo ingresos.",
                                   -15, REGLA_ENCAJE, "observado"))
    if objetivo == "diversificacion":
        if e.get("en_cartera"):
            p -= 10
            factores.append(Factor("Ya tenés este emisor: no suma un nombre nuevo.", -10, REGLA_ENCAJE))
        if e.get("sector_nuevo"):
            p += 10
            factores.append(Factor("Suma un sector que hoy no tenés.", 10, REGLA_ENCAJE))
        if e.get("pais_nuevo"):
            p += 10
            factores.append(Factor("Suma un país que hoy no tenés.", 10, REGLA_ENCAJE))
    if not factores:
        factores.append(Factor("Con el monto de referencia no aparece ninguna observación de concentración.", 0.0, REGLA_ENCAJE))
    return DimensionEval(ENCAJE, NOMBRE[ENCAJE], round(_clamp(p), 1), "evaluada",
                         f"Simulado con {e.get('monto_ref_texto') or 'un monto de referencia'}.", REGLA_ENCAJE, factores, faltantes)


# ---------------------------------------------------------------------------------------------
# Banderas y orden
# ---------------------------------------------------------------------------------------------

def banderas(ins: Insumos, dims: dict[str, DimensionEval], prefs: dict, hoy: date) -> list[Bandera]:
    out: list[Bandera] = []
    solidez = _dim_diag(ins.diagnostico, "solidez")
    if solidez and solidez.get("nivel") == "riesgo":
        out.append(Bandera("solidez", f"Solidez financiera en riesgo: {solidez.get('resumen')}", solidez.get("regla") or "", ALTA))
    if ins.sin_ganancias and not ins.es_etf:
        out.append(Bandera("sin_ganancias", "Informa pérdidas: los múltiplos de ganancias no aplican.",
                           "P/E negativo o ganancias netas negativas", ALTA))
    ci = ins.metricas.get("crec_ingresos")
    if ci is not None and ci < CAIDA_INGRESOS:
        out.append(Bandera("caida_ingresos", f"Ingresos cayendo {_pct(-ci, 1)} interanual.",
                           f"crecimiento de ingresos menor a {_pct(CAIDA_INGRESOS)}", MEDIA))
    payout = ins.extra.get("payout")
    if payout is not None and payout > PAYOUT_NO_CUBIERTO:
        out.append(Bandera("payout", f"Reparte más dividendo que lo que gana (payout {_pct(payout)}).",
                           f"payout mayor a {_pct(PAYOUT_NO_CUBIERTO)}", MEDIA))
    if ins.fecha_dato and (hoy - ins.fecha_dato).days > DIAS_DATO_VIEJO:
        out.append(Bandera("dato_viejo", f"Los fundamentales son del {ins.fecha_dato.isoformat()} ({(hoy - ins.fecha_dato).days} días).",
                           f"datos de más de {DIAS_DATO_VIEJO} días", MEDIA))
    if ins.fecha_precio and (hoy - ins.fecha_precio).days > DIAS_PRECIO_VIEJO:
        out.append(Bandera("precio_viejo", f"La última cotización es del {ins.fecha_precio.isoformat()} ({(hoy - ins.fecha_precio).days} días).",
                           f"cotización de más de {DIAS_PRECIO_VIEJO} días (~5 ruedas)", MEDIA))
    for o in (ins.encaje or {}).get("observaciones") or []:
        if o.get("nivel") == "revisar":
            out.append(Bandera("concentracion", o.get("texto", ""), o.get("regla") or "", MEDIA))
    confianza = (ins.diagnostico or {}).get("confianza")
    if confianza == "baja":
        out.append(Bandera("confianza", "La confianza de los datos del diagnóstico es baja.",
                           "dimensión confianza del diagnóstico de empresa", MEDIA))
    riesgo = dims[RIESGO].puntaje
    if prefs.get("tolerancia") == "baja" and riesgo is not None and riesgo < RIESGO_BAJO_PARA_TOLERANCIA:
        out.append(Bandera("tolerancia", "El riesgo histórico es alto para la tolerancia baja que elegiste.",
                           f"Riesgo < {RIESGO_BAJO_PARA_TOLERANCIA:.0f} con tolerancia baja", ALTA))
    return out


REGLA_ORDEN = (
    "promedio ponderado de los puntajes de las dimensiones con dato (pesos según enfoque y horizonte, o los tuyos). "
    f"Si las dimensiones con dato suman menos del {COBERTURA_MINIMA * 100:.0f} % del peso, o la confianza de los datos es "
    "baja, el orden es incompleto y no se da un número"
)


def ordenar(dims: dict[str, DimensionEval], pesos: dict[str, float], confianza: str | None) -> dict:
    total = sum(pesos.values())
    con_dato = {d: pesos[d] for d in DIMENSIONES if dims[d].puntaje is not None and pesos[d] > 0}
    aplicables = sum(pesos[d] for d in DIMENSIONES if dims[d].estado != "no_aplica")
    peso_con_dato = sum(con_dato.values())
    cobertura = peso_con_dato / aplicables if aplicables > 0 else 0.0
    motivo = None
    if total <= 0 or aplicables <= 0:
        motivo = "ninguna dimensión con peso aplica a este activo"
    elif cobertura < COBERTURA_MINIMA:
        faltan = [NOMBRE[d] for d in DIMENSIONES if dims[d].estado == "sin_datos" and pesos[d] > 0]
        motivo = f"faltan datos de {', '.join(faltan)}: cubren menos del {COBERTURA_MINIMA * 100:.0f} % del peso"
    elif confianza in ("baja", "sin_datos") and dims[FUNDAMENTALES].estado != "no_aplica":
        motivo = "la confianza de los datos del diagnóstico es baja"
    puntaje = None
    contribuciones = []
    if motivo is None:
        puntaje = round(sum(dims[d].puntaje * w for d, w in con_dato.items()) / peso_con_dato, 1)
        for d, w in con_dato.items():
            contribuciones.append({"dimension": d, "nombre": NOMBRE[d], "peso_pct": round(w / peso_con_dato * 100, 1),
                                   "aporte": round((dims[d].puntaje - 50) * w / peso_con_dato, 1)})
        contribuciones.sort(key=lambda c: -abs(c["aporte"]))
    return {
        "puntaje": puntaje,
        "incompleto": motivo is not None,
        "motivo": motivo,
        "cobertura": round(cobertura, 3),
        "pesos": {d: round(w, 1) for d, w in pesos.items()},
        "contribuciones": contribuciones,
        "regla": REGLA_ORDEN,
    }


def evaluar(ins: Insumos, prefs: dict, hoy: date | None = None) -> dict:
    """Evaluación completa de un activo con las preferencias dadas."""
    hoy = hoy or date.today()
    dims = {
        FUNDAMENTALES: _fundamentales(ins),
        VALORACION: _valoracion(ins),
        RIESGO: _riesgo(ins, prefs.get("moneda", "USD")),
        TECNICO: _tecnico(ins),
        ENCAJE: _encaje(ins, prefs.get("objetivo", "crecimiento")),
    }
    flags = banderas(ins, dims, prefs, hoy)
    orden = ordenar(dims, pesos_para(prefs), (ins.diagnostico or {}).get("confianza"))
    return {
        "version_reglas": VERSION_REGLAS,
        "ticker": ins.ticker,
        "dimensiones": [asdict(dims[d]) for d in DIMENSIONES],
        "banderas": [asdict(b) for b in flags],
        "orden": orden,
    }


def puntaje_de(evaluacion: dict, dimension: str) -> float | None:
    return next((d["puntaje"] for d in evaluacion["dimensiones"] if d["clave"] == dimension), None)


def reordenar(evaluacion: dict, pesos: dict[str, float], confianza: str | None) -> float | None:
    """El puntaje de orden de una evaluación ya hecha con otros pesos (para medir la robustez)."""
    dims = {d["clave"]: DimensionEval(**{**d, "factores": []}) for d in evaluacion["dimensiones"]}
    return ordenar(dims, pesos, confianza)["puntaje"]


# ---------------------------------------------------------------------------------------------
# Conclusión
# ---------------------------------------------------------------------------------------------

def _frases_factores(evaluacion: dict, signo: int, limite: int = 3) -> list[str]:
    factores = [(f["efecto"], d["nombre"], f["texto"]) for d in evaluacion["dimensiones"] for f in d["factores"]
                if (f["efecto"] > 0 if signo > 0 else f["efecto"] < 0)]
    factores.sort(key=lambda x: -abs(x[0]))
    return [f"{n}: {t}" for _, n, t in factores[:limite]]


def concluir(objetivo: dict, alternativas: list[dict], robustez: dict, firmeza: str | None,
             advertencias_fechas: list[str]) -> dict:
    """Conclusión estructurada por reglas (`REGLA_CONCLUSION`). `objetivo` y `alternativas` son evaluaciones
    (`evaluar`) con `ticker`; `robustez = {enfoque: ganador | None}`; `firmeza` la del comparador."""
    obj_orden = objetivo["orden"]["puntaje"]
    miembros = [objetivo] + [a for a in alternativas if a["orden"]["puntaje"] is not None]
    ordenados = sorted([m for m in miembros if m["orden"]["puntaje"] is not None],
                       key=lambda m: -m["orden"]["puntaje"])
    criticas = [b for b in objetivo["banderas"] if b["severidad"] == ALTA]
    riesgo = puntaje_de(objetivo, RIESGO)
    valoracion = puntaje_de(objetivo, VALORACION)
    tecnico = puntaje_de(objetivo, TECNICO)

    ganador = None
    diferencia = None
    if len(ordenados) >= 2:
        diferencia = ordenados[0]["orden"]["puntaje"] - ordenados[1]["orden"]["puntaje"]
    ganadores = {g for g in robustez.values()}
    robusta = len(ganadores) == 1 and None not in ganadores
    if (len(ordenados) >= 2 and diferencia >= DIFERENCIA_RELEVANTE
            and not any(b["severidad"] == ALTA for b in ordenados[0]["banderas"])
            and firmeza in (ALTA, MEDIA) and robusta and next(iter(ganadores)) == ordenados[0]["ticker"]):
        ganador = ordenados[0]

    condiciones = []
    if obj_orden is None:
        tipo = DATOS_INSUFICIENTES
    elif criticas or (riesgo is not None and riesgo < RIESGO_ELEVADO):
        tipo = RIESGO_ELEVADO_T
    elif ganador is not None:
        tipo = MAS_ATRACTIVA
    elif valoracion is not None and valoracion < VALORACION_EXIGENTE:
        tipo = VALORACION_EXIGENTE_T
    elif obj_orden >= ORDEN_INTERESANTE and (tecnico is None or tecnico < 50 or valoracion is None or valoracion < 50):
        tipo = INTERESANTE_PENDIENTE
        if tecnico is None:
            condiciones.append("confirmar el momento del precio con la serie técnica (hoy no hay serie diaria)")
        elif tecnico < 50:
            condiciones.append("que la lectura técnica mejore (tendencia o fuerza relativa)")
        if valoracion is None or valoracion < 50:
            condiciones.append("un precio más cercano al rango de valor razonable de sus pares")
    else:
        tipo = NINGUNA_SUPERIOR

    # 1-2. qué encaja mejor y por qué
    if tipo == MAS_ATRACTIVA:
        que_encaja = ganador["ticker"]
        por_que = (f"{ganador['ticker']} supera al siguiente por {_num(diferencia)} puntos de orden con los pesos de los tres "
                   "enfoques y sin banderas críticas.")
    elif tipo == DATOS_INSUFICIENTES:
        que_encaja, por_que = None, f"El análisis de {objetivo['ticker']} es incompleto: {objetivo['orden']['motivo']}."
    elif ordenados:
        que_encaja = None
        por_que = ("Las diferencias de orden entre los activos comparados no alcanzan para destacar uno "
                   f"(hace falta ≥ {DIFERENCIA_RELEVANTE:.0f} puntos, sin banderas críticas y el mismo resultado con otros pesos).")
    else:
        que_encaja, por_que = None, "No hay activos con orden completo para comparar."

    foco = ganador or objetivo
    evidencia = _frases_factores(foco, +1)
    desventajas = _frases_factores(foco, -1)
    if ganador is not None and ganador is not objetivo:
        for d in ganador["dimensiones"]:
            po = puntaje_de(objetivo, d["clave"])
            if d["puntaje"] is not None and po is not None and po - d["puntaje"] >= DIFERENCIA_RELEVANTE:
                desventajas.append(f"{d['nombre']}: {objetivo['ticker']} está mejor ({_num(po)} contra {_num(d['puntaje'])}).")
    evidencia_en_contra = desventajas[:] or ["No aparecen factores en contra con los datos disponibles: revisá lo que falta."]
    for b in foco["banderas"]:
        evidencia_en_contra.append(f"Bandera: {b['texto']}")

    # 5. qué invalidaría
    invalidaria = [
        "que la solidez financiera pase a «riesgo» en el próximo balance",
        "que la valoración relativa pase a ser de las más caras del grupo sin una mejora de fundamentos",
    ]
    if tipo == MAS_ATRACTIVA:
        invalidaria.insert(0, f"que la diferencia de orden con el siguiente baje de {DIFERENCIA_RELEVANTE:.0f} puntos")

    # 6. siguiente paso
    if tipo in (DATOS_INSUFICIENTES,):
        siguiente = "profundizar"
        siguiente_texto = "Completar los datos que faltan antes de sacar conclusiones."
    elif tipo in (RIESGO_ELEVADO_T,):
        siguiente = "descartar_por_ahora"
        siguiente_texto = "Con los criterios elegidos, el riesgo pesa más que el resto: descartarla por ahora o revisar los criterios."
    elif tipo in (VALORACION_EXIGENTE_T, INTERESANTE_PENDIENTE):
        siguiente = "esperar_condicion"
        siguiente_texto = "Esperar una condición (precio o técnica) y volver a mirar."
    else:
        siguiente = "profundizar"
        siguiente_texto = "Profundizar el análisis de los activos mejor ordenados antes de decidir."

    # 7. incertidumbre
    razones_inc = []
    if objetivo["orden"]["cobertura"] < 0.85:
        razones_inc.append(f"las dimensiones con dato cubren el {objetivo['orden']['cobertura'] * 100:.0f} % del peso")
    if firmeza in (BAJA, None):
        razones_inc.append("la comparación con pares es poco firme" if firmeza else "no hay comparación con pares")
    if not robusta and len(ordenados) >= 2:
        razones_inc.append("el primero cambia según los pesos del enfoque: depende de supuestos")
    razones_inc.extend(advertencias_fechas)
    incertidumbre = ALTA if len(razones_inc) >= 2 or tipo == DATOS_INSUFICIENTES else MEDIA if razones_inc else BAJA

    preguntas = [
        "¿Qué tendría que pasar en el próximo balance para que dejes de sostener esta idea?",
        "¿La razón principal es la calidad del negocio o el precio? ¿Lo distinguís en los datos?",
        "Si el precio cayera hasta la condición de invalidación, ¿qué harías y por qué?",
    ]
    if criticas:
        preguntas.insert(0, "¿Cómo explicás la bandera crítica? ¿Tenés información que la app no ve?")

    return {
        "tipo": tipo,
        "titulo": TITULOS[tipo],
        "ganador": ganador["ticker"] if ganador else None,
        "diferencia": round(diferencia, 1) if diferencia is not None else None,
        "robusta": robusta,
        "respuestas": {
            "que_encaja": que_encaja,
            "por_que": por_que,
            "evidencia": evidencia,
            "desventajas": desventajas,
            "invalidaria": invalidaria,
            "siguiente_paso": siguiente,
            "siguiente_paso_texto": siguiente_texto,
            "incertidumbre": incertidumbre,
            "incertidumbre_razones": razones_inc,
        },
        "condiciones": condiciones,
        "evidencia_en_contra": evidencia_en_contra,
        "preguntas": preguntas,
        "regla": REGLA_CONCLUSION,
        "salvedad": ("Ordena con reglas fijas sobre los datos disponibles; no predice precios ni indica qué operación hacer. "
                     "El puntaje sirve para priorizar qué mirar con más detalle."),
    }
