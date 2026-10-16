"""Comparador "¿qué compraría en su lugar?": un instrumento contra alternativas comparables. Puro.

Responde: dado este instrumento, ¿qué alternativas **comparables** hay —incluso fuera de su grupo
automático de pares— y cómo se ubica frente a ellas? Sigue el criterio del resto de la valuación:
**sin puntaje único**, reglas deterministas que se muestran tal cual, y ninguna orden de compra o
venta. Cada frase de la conclusión se puede rastrear a métricas y a una regla.

Cuatro piezas:

1. **Comparabilidad** (`evaluar_comparabilidad`). Compartir la industria de Yahoo no alcanza para
   llamar "equivalentes" a dos empresas. Cada alternativa se mide en criterios explícitos (emisor,
   tipo, modelo de negocio, industria, tamaño, región, cobertura de datos, período contable, moneda,
   frescura) y queda en un nivel: *alta*, *media*, *baja* (se ve en la tabla, no entra al ranking) o
   *no comparable* (se descarta con el motivo: el mismo emisor en otro mercado, un ETF contra una
   empresa, un banco contra una industrial, sin datos suficientes).
2. **Tabla lado a lado** (`armar_tabla`) con las métricas que le importan al sector (no todas), con
   unidad, período de referencia, origen y el motivo de lo que no aplica.
3. **Ranking dentro del grupo** (`rankear`): se vuelve a correr el diagnóstico de la Etapa 1 de cada
   miembro **contra los demás miembros** (no contra sus pares automáticos), así los percentiles son
   comparables entre sí. Con pocos miembros el percentil es grueso, y se dice.
4. **Conclusión** (`concluir`): reglas ordenadas, la primera que se cumple. Explica por qué una
   empresa puede merecer un múltiplo mayor o menor; no dice "comprá".

`VERSION_REGLAS` viaja en la respuesta (prepara el historial de la etapa 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from . import diagnostico_empresa_engine as de
from . import pares_engine as pe
from . import valuacion_engine as ve

VERSION_REGLAS = 1

# -- Cuántas alternativas --
MIN_ALTERNATIVAS = 2      # con 2 alternativas hay 3 valores por métrica: el mínimo para un percentil
MAX_ALTERNATIVAS = 6      # a más, la tabla deja de ser legible en el celular
N_DEFAULT = 4             # lo que se elige solo cuando el usuario no eligió
N_SUGERIDAS = 6
LIMITE_EVALUACION = 30    # candidatos fuera del grupo que se evalúan por completo (cuesta armar la ficha)

# -- Comparabilidad --
COBERTURA_MINIMA = 0.40   # menos que esto de las métricas aplicables con dato: no es comparable
COBERTURA_ALTA = 0.70

ALTA, MEDIA, BAJA, NO_COMPARABLE = "alta", "media", "baja", "no_comparable"
_RANK_NIVEL = {ALTA: 0, MEDIA: 1, BAJA: 2, NO_COMPARABLE: 3}
APTOS = (ALTA, MEDIA)     # los niveles que entran al ranking y a la conclusión

FAVORABLE, NEUTRO, DESFAVORABLE, SIN_DATO = "favorable", "neutro", "desfavorable", "sin_dato"

DIMENSIONES = ("valuacion", "calidad", "crecimiento", "solidez")
FUNDAMENTOS = ("calidad", "crecimiento", "solidez")
NOMBRE_DIMENSION = {
    "valuacion": "Valuación", "calidad": "Calidad del negocio", "crecimiento": "Crecimiento",
    "solidez": "Solidez financiera",
}
ARRIBA, MEDIO, ABAJO = "arriba", "medio", "abajo"

# -- Métricas pertinentes por modelo de negocio --
MODELO_FINANCIERO, MODELO_INMOBILIARIO, MODELO_OPERATIVO, MODELO_ETF = "financiero", "inmobiliario", "operativo", "etf"

METRICAS_POR_MODELO: dict[str, tuple[str, ...]] = {
    MODELO_OPERATIVO: (
        "pe", "forward_pe", "ev_ebitda", "ps", "fcf_yield", "pb", "div_yield",
        "margen_operativo", "margen_neto", "roe", "crec_ingresos", "crec_ganancias", "deuda_patrimonio", "rend_12m",
    ),
    MODELO_FINANCIERO: (
        "pe", "forward_pe", "pb", "div_yield", "roe", "roa", "margen_neto", "crec_ingresos", "crec_ganancias", "rend_12m",
    ),
    MODELO_INMOBILIARIO: (
        "pb", "fcf_yield", "div_yield", "margen_operativo", "crec_ingresos", "crec_ganancias", "rend_12m",
    ),
    MODELO_ETF: ("gastos", "pb", "div_yield", "rend_3m", "rend_6m", "rend_12m"),
}

# Qué métricas pesan en cada dimensión al comparar de a pares (las que están en la tabla del sector).
METRICAS_DIMENSION: dict[str, tuple[str, ...]] = {
    "valuacion": ("pe", "forward_pe", "ev_ebitda", "ps", "pb", "fcf_yield", "gastos"),
    "calidad": ("margen_operativo", "margen_neto", "roe", "roa"),
    "crecimiento": ("crec_ingresos", "crec_ganancias"),
    "solidez": ("deuda_patrimonio",),
}

PERIODO_METRICA: dict[str, str] = {
    "pe": "últimos 12 meses",
    "forward_pe": "próximo año (estimación de analistas)",
    "ev_ebitda": "último dato informado por Yahoo",
    "ps": "últimos 12 meses",
    "pb": "último balance",
    "fcf_yield": "últimos 12 meses ÷ capitalización",
    "div_yield": "dividendo anual ÷ precio",
    "gastos": "gasto anual del fondo",
    "margen_bruto": "último dato informado por Yahoo",
    "margen_operativo": "último dato informado por Yahoo",
    "margen_neto": "último dato informado por Yahoo",
    "roe": "último dato informado por Yahoo",
    "roa": "último dato informado por Yahoo",
    "deuda_patrimonio": "último balance",
    "crec_ingresos": "último trimestre vs. el mismo de hace un año",
    "crec_ganancias": "último trimestre vs. el mismo de hace un año",
    "rend_3m": "3 meses, precio en USD",
    "rend_6m": "6 meses, precio en USD",
    "rend_12m": "12 meses, precio en USD",
}

MOTIVO_NO_APLICA = {
    "ev_ebitda": "en un banco, aseguradora o inmobiliaria la deuda es parte del negocio: EV/EBITDA no se lee igual que en una empresa industrial",
    "ps": "los ingresos de un banco o inmobiliaria no se comparan con la capitalización como los de una empresa industrial",
    "fcf_yield": "el flujo de caja libre de un banco (depósitos, préstamos) no mide lo que mide en una empresa",
    "margen_bruto": "los bancos y las inmobiliarias no tienen margen bruto",
    "deuda_patrimonio": "la deuda de un banco o inmobiliaria es parte de su negocio, no una señal de fragilidad por sí sola",
}
MOTIVO_NO_APLICA_ETF = (
    "los márgenes, el ROE, el crecimiento y la deuda no aplican a un ETF: sus indicadores son los de las empresas "
    "que contiene, no los de un negocio propio"
)

LIMITES = (
    "No dice si el precio es el correcto: sólo compara contra las alternativas elegidas. El valor razonable por múltiplos es otro cálculo (tarjeta «Valor razonable»).",
    "No hay historia contable de varios años: la consistencia de resultados no se puede evaluar.",
    "No mide cuánto cambiaría tu cartera: eso lo hace la tarjeta «¿Cómo cambiaría mi cartera?», que es otro cálculo.",
    "Es un análisis relativo: que algo esté más barato o mejor que sus alternativas no dice que su precio sea el correcto.",
)
SALVEDAD_MULTIPLO = (
    "Esto explica la diferencia de precio relativo frente a las alternativas; no garantiza que sea una buena "
    "inversión ni que el precio sea el correcto."
)

NIVEL_SOLIDEZ_ORDEN = {de.BIEN: 3, de.NEUTRO: 2, de.ATENCION: 1, de.RIESGO: 0}


# ---------------------------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Perfil:
    """Un emisor candidato: lo estructural (`pares_engine.Candidato`) más cómo se relaciona con el grupo."""
    c: pe.Candidato
    en_grupo: bool = False    # está en el grupo de pares vigente (automático + agregados − quitados)
    a_mano: bool = False      # el usuario lo agregó a mano como par
    quitado: bool = False     # el usuario lo quitó a mano de sus pares

    @property
    def base(self) -> str:
        return self.c.ticker_base


@dataclass
class Criterio:
    clave: str
    nombre: str
    estado: str               # FAVORABLE | NEUTRO | DESFAVORABLE | SIN_DATO
    texto: str
    excluye: bool = False     # un criterio duro: con éste la alternativa no es comparable
    corto: str = ""           # la frase breve con la que entra al resumen del nivel


@dataclass
class Comparabilidad:
    nivel: str
    resumen: str
    criterios: list[Criterio] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)

    @property
    def apta(self) -> bool:
        return self.nivel in APTOS


@dataclass
class Alternativa:
    ticker_base: str
    nombre: str | None
    origen: str               # "grupo" | "elegida" | "sugerida"
    en_grupo: bool
    a_mano: bool
    nivel: str
    resumen: str
    criterios: list[Criterio]
    notas: list[str]
    en_ranking: bool
    tamano_usd: float | None
    region: str | None
    sector: str | None
    industria: str | None


@dataclass
class Rechazo:
    ticker_base: str
    nombre: str | None
    nivel: str
    motivo: str


@dataclass
class Celda:
    valor: float | None
    estado: str               # dato | sin_dato | no_aplica | sin_ganancias | moneda
    origen: str = "observado"


@dataclass
class Columna:
    ticker_base: str
    nombre: str | None
    es_objetivo: bool
    nivel: str | None         # comparabilidad (None en el objetivo)
    en_ranking: bool
    fecha_dato: date | None
    periodo_contable: date | None
    fecha_serie: date | None
    aviso_moneda: bool
    tamano_usd: float | None
    region: str | None
    sector: str | None
    industria: str | None


@dataclass
class FilaTabla:
    clave: str
    nombre: str
    grupo: str
    formato: str
    unidad: str
    periodo: str
    mayor_es_mejor: bool
    solo_apoya: bool
    celdas: dict[str, Celda]
    mejor: str | None = None
    peor: str | None = None


@dataclass
class NoAplica:
    nombre: str
    motivo: str


@dataclass
class Tabla:
    columnas: list[Columna]
    filas: list[FilaTabla]
    no_aplican: list[NoAplica]
    sin_dato_en_ninguna: list[str]


@dataclass
class PuestoDimension:
    ticker_base: str
    posicion: int | None
    estado: str
    nivel: str
    percentil: int | None


@dataclass
class RankingDimension:
    clave: str
    nombre: str
    regla: str
    puestos: list[PuestoDimension]
    posicion_objetivo: int | None
    de: int                   # cuántos miembros tienen posición en esta dimensión
    tercio: str | None        # ARRIBA | MEDIO | ABAJO (None si no hay ranking: hacen falta 3)
    estado_objetivo: str
    nivel_objetivo: str


@dataclass
class Linea:
    dimension: str
    veredicto: str | None     # "mejor" | "peor" | "similar" (el objetivo frente a la alternativa)
    texto: str
    tono: str
    metricas: list[str]
    regla: str


@dataclass
class ComparacionPar:
    ticker_base: str
    orientativa: bool         # alternativa de comparabilidad baja: no entra a la conclusión
    lineas: list[Linea]
    veredictos: dict[str, str | None]
    domina: str | None = None   # "alternativa" | "objetivo" | None
    texto_dominancia: str = ""


@dataclass
class FraseConclusion:
    texto: str
    regla: str
    tono: str
    origen: str
    metricas: list[str] = field(default_factory=list)
    dimension: str | None = None


@dataclass
class Conclusion:
    regla_aplicada: str
    titulo: str
    frases: list[FraseConclusion]
    destacadas: list[FraseConclusion]
    mayor: list[FraseConclusion]      # por qué podría merecer un múltiplo mayor
    menor: list[FraseConclusion]      # por qué podría merecer un múltiplo menor
    salvedad: str
    firmeza: str                      # alta | media | baja
    firmeza_razones: list[str]
    limites: list[str]
    regla: str


@dataclass
class Comparador:
    version_reglas: int
    estado: str               # ok | insuficiente | sin_datos
    mensaje: str
    minimo: int
    faltan: int
    modelo: str | None
    objetivo: Columna | None
    alternativas: list[Alternativa]
    sugeridas: list[Alternativa]
    rechazadas: list[Rechazo]
    tabla: Tabla | None
    ranking: list[RankingDimension]
    pares: list[ComparacionPar]
    conclusion: Conclusion | None


@dataclass
class Seleccion:
    alternativas: list[Alternativa]
    sugeridas: list[Alternativa]
    rechazadas: list[Rechazo]
    nombres: dict[str, str | None]


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------

def modelo_negocio(sector: str | None, es_etf: bool) -> str:
    if es_etf:
        return MODELO_ETF
    if sector == "Financiero":
        return MODELO_FINANCIERO
    if sector == "Inmobiliario":
        return MODELO_INMOBILIARIO
    return MODELO_OPERATIVO


def _valor(v: float | None, formato: str) -> str:
    if v is None:
        return "—"
    if formato == "x":
        return f"{v:.1f}x".replace(".", ",")
    return f"{v * 100:.1f}%".replace(".", ",")


def _usd(v: float | None) -> str:
    if v is None:
        return "—"
    for corte, div, suf in ((1e12, 1e12, "B"), (1e9, 1e9, "mil M"), (1e6, 1e6, "M")):
        if v >= corte:
            return f"US$ {v / div:.1f} {suf}".replace(".", ",")
    return f"US$ {v:.0f}"


def _veces(a: float, b: float) -> str:
    r = max(a, b) / min(a, b)
    return f"{r:.1f}".replace(".", ",") + "×"


def cobertura(f: ve.Ficha) -> tuple[int, int]:
    """(métricas aplicables con dato, métricas aplicables) de una ficha. Mismo criterio que la confianza."""
    omitir = {"pe", "forward_pe", "crec_ganancias", "crec_esperado"} if f.sin_ganancias else set()
    aplicables = [
        m for m in ve.metricas_para(f.es_etf)
        if m.grupo != "momentum" and m.clave not in de.OPCIONALES and m.clave not in omitir and de._aplica(m.clave, f.sector)
    ]
    return sum(1 for m in aplicables if f.valores.get(m.clave) is not None), len(aplicables)


def _tiene_problema_moneda(f: ve.Ficha | None) -> bool:
    return bool(f and (f.recalculadas or f.descartadas_moneda or f.momentum_aproximado))


# ---------------------------------------------------------------------------------------------
# Comparabilidad
# ---------------------------------------------------------------------------------------------

def _criterios_estructurales(obj: Perfil, alt: Perfil) -> list[Criterio]:
    o, a = obj.c, alt.c
    crits: list[Criterio] = []

    mismo = a.ticker_base == o.ticker_base or bool(a.simbolo_yahoo and a.simbolo_yahoo == o.simbolo_yahoo)
    crits.append(Criterio(
        "emisor", "Emisor", DESFAVORABLE if mismo else FAVORABLE,
        "Es el mismo emisor que el instrumento (otro mercado, su CEDEAR o su ADR): no es una alternativa independiente."
        if mismo else "Es un emisor distinto.",
        excluye=mismo,
    ))

    tipos_distintos = o.es_etf != a.es_etf
    crits.append(Criterio(
        "tipo", "Tipo", DESFAVORABLE if tipos_distintos else FAVORABLE,
        "Un ETF diversificado no se compara con una empresa individual: sus indicadores son los de sus tenencias."
        if tipos_distintos else ("Los dos son ETF." if o.es_etf else "Las dos son empresas individuales."),
        excluye=tipos_distintos,
    ))

    mo, ma = modelo_negocio(o.sector, o.es_etf), modelo_negocio(a.sector, a.es_etf)
    modelos_distintos = mo != ma and not tipos_distintos
    crits.append(Criterio(
        "modelo", "Modelo de negocio", DESFAVORABLE if modelos_distintos else FAVORABLE,
        f"Modelo de negocio distinto ({ma} vs. {mo}): las métricas que aplican y cómo se leen no son las mismas."
        if modelos_distintos else f"Mismo modelo de negocio ({mo}).",
        excluye=modelos_distintos,
    ))

    if o.es_etf:
        if o.categoria and pe._clave(a.categoria) == pe._clave(o.categoria):
            ind = Criterio("industria", "Categoría", FAVORABLE, f"Misma categoría: {o.categoria}.", corto="misma categoría")
        elif o.sector and pe._clave(a.sector) == pe._clave(o.sector) and pe._clave(a.region) == pe._clave(o.region):
            ind = Criterio("industria", "Categoría", NEUTRO, "Otra categoría, pero mismo sector y región.", corto="otra categoría, mismo sector y región")
        elif not o.categoria or not a.categoria:
            ind = Criterio("industria", "Categoría", SIN_DATO, "Falta la categoría de alguno de los dos.")
        else:
            ind = Criterio("industria", "Categoría", DESFAVORABLE, f"Otra categoría ({a.categoria} vs. {o.categoria}).", corto="otra categoría")
    else:
        if o.industria_raw and a.industria_raw and pe._clave(o.industria_raw) == pe._clave(a.industria_raw):
            ind = Criterio("industria", "Industria", FAVORABLE, f"Misma industria: {o.industria_raw}.", corto="misma industria")
        elif o.sector and a.sector and pe._clave(o.sector) == pe._clave(a.sector):
            ind = Criterio("industria", "Industria", NEUTRO,
                           f"Mismo sector ({o.sector}) pero otra industria"
                           + (f" ({a.industria_raw} vs. {o.industria_raw})." if o.industria_raw and a.industria_raw else "."),
                           corto="mismo sector, otra industria")
        elif not (o.sector and a.sector):
            ind = Criterio("industria", "Industria", SIN_DATO, "Falta el sector de alguno de los dos.")
        else:
            ind = Criterio("industria", "Industria", DESFAVORABLE, f"Otro sector ({a.sector} vs. {o.sector}).", corto="otro sector")
    crits.append(ind)

    nombre_tam = "Patrimonio (AUM)" if o.es_etf else "Tamaño"
    if not o.tamano_usd or not a.tamano_usd or o.tamano_usd <= 0 or a.tamano_usd <= 0:
        crits.append(Criterio("tamano", nombre_tam, SIN_DATO, "Falta el tamaño de alguno de los dos."))
    else:
        detalle = f"{_usd(a.tamano_usd)} vs. {_usd(o.tamano_usd)} ({_veces(a.tamano_usd, o.tamano_usd)})"
        if pe._en_rango(a.tamano_usd, o.tamano_usd, pe.RANGOS_TAMANO[0]):
            crits.append(Criterio("tamano", nombre_tam, FAVORABLE, f"Tamaño parecido: {detalle}.", corto="tamaño parecido"))
        elif pe._en_rango(a.tamano_usd, o.tamano_usd, pe.RANGOS_TAMANO[1]):
            crits.append(Criterio("tamano", nombre_tam, NEUTRO, f"Tamaño distinto: {detalle}.", corto="tamaño distinto"))
        else:
            crits.append(Criterio("tamano", nombre_tam, DESFAVORABLE, f"Tamaño muy distinto: {detalle}.", corto="tamaño muy distinto"))

    if not o.region or not a.region:
        crits.append(Criterio("region", "Región", SIN_DATO, "Falta la región de alguno de los dos."))
    elif pe._clave(o.region) == pe._clave(a.region):
        crits.append(Criterio("region", "Región", FAVORABLE, f"Misma región: {o.region}.", corto="misma región"))
    else:
        crits.append(Criterio("region", "Región", DESFAVORABLE,
                              f"Otra región ({a.region} vs. {o.region}): cambian el riesgo país y los múltiplos de referencia.",
                              corto="otra región"))
    return crits


def _nivel(es_etf: bool, crits: dict[str, Criterio]) -> str:
    ind, tam, reg = crits["industria"].estado, crits["tamano"].estado, crits["region"].estado
    ind_f, tam_f, reg_f = ind == FAVORABLE, tam == FAVORABLE, reg == FAVORABLE
    if es_etf:   # el patrimonio informa liquidez, pero no define qué tan parecidos son dos fondos
        if ind_f and reg_f:
            return ALTA
        if ind_f or (ind == NEUTRO and reg_f):
            return MEDIA
        return BAJA
    if ind_f and tam_f and reg_f:
        return ALTA
    if ind_f and (tam_f or reg_f):
        return MEDIA
    if ind == NEUTRO and tam_f and reg_f:
        return MEDIA
    return BAJA


def _resumen(nivel: str, crits: dict[str, Criterio]) -> str:
    if nivel == NO_COMPARABLE:
        return next((c.texto for c in crits.values() if c.excluye), "No es comparable.")
    partes = [crits[k].corto for k in ("industria", "tamano", "region") if crits[k].corto]
    return (", ".join(partes).capitalize() if partes else "Sin datos para compararlas") + f" → comparabilidad {nivel}."


def comparabilidad_estructural(obj: Perfil, alt: Perfil) -> Comparabilidad:
    """Lo que se puede decir sin armar las fichas: emisor, tipo, modelo, industria, tamaño y región."""
    crits = _criterios_estructurales(obj, alt)
    por_clave = {c.clave: c for c in crits}
    if any(c.excluye for c in crits):
        nivel = NO_COMPARABLE
    else:
        nivel = _nivel(obj.c.es_etf, por_clave)
    return Comparabilidad(nivel, _resumen(nivel, por_clave), crits)


def completar_comparabilidad(
    comp: Comparabilidad, obj: Perfil, alt: Perfil, ficha_obj: ve.Ficha | None, ficha_alt: ve.Ficha | None, hoy: date,
) -> Comparabilidad:
    """Suma los criterios que dependen de los datos (cobertura, período, moneda, frescura) y las notas
    de la corrección manual. Puede bajar el nivel, nunca subirlo (salvo la corrección manual a "media")."""
    crits = list(comp.criterios)
    notas = list(comp.notas)
    nivel = comp.nivel

    if nivel != NO_COMPARABLE:
        if ficha_alt is None:
            crits.append(Criterio("datos", "Datos", DESFAVORABLE,
                                  "Todavía no hay fundamentales de este emisor (se bajan en la próxima corrida de la ingesta).",
                                  excluye=True))
            nivel = NO_COMPARABLE
        else:
            con, total = cobertura(ficha_alt)
            cob = con / total if total else 0.0
            detalle = f"hay dato para {con} de {total} métricas aplicables ({cob * 100:.0f}%)"
            if cob < COBERTURA_MINIMA:
                crits.append(Criterio("datos", "Cobertura de datos", DESFAVORABLE,
                                      f"Datos insuficientes: {detalle}. Con tan poco, compararla sería ruido.", excluye=True))
                nivel = NO_COMPARABLE
            elif cob < COBERTURA_ALTA:
                crits.append(Criterio("datos", "Cobertura de datos", NEUTRO, f"Cobertura parcial: {detalle}."))
            else:
                crits.append(Criterio("datos", "Cobertura de datos", FAVORABLE, f"Datos completos: {detalle}."))

    degradar = False
    if nivel != NO_COMPARABLE and ficha_alt is not None and ficha_obj is not None:
        if ficha_obj.periodo_contable and ficha_alt.periodo_contable:
            dias = abs((ficha_obj.periodo_contable - ficha_alt.periodo_contable).days)
            if dias > de.DIAS_PERIODOS_DISTINTOS:
                crits.append(Criterio("periodo", "Período contable", NEUTRO,
                                      f"Balances de períodos distintos ({ficha_alt.periodo_contable.strftime('%d/%m/%Y')} vs. "
                                      f"{ficha_obj.periodo_contable.strftime('%d/%m/%Y')}): los múltiplos no son del todo comparables."))
                degradar = True
            else:
                crits.append(Criterio("periodo", "Período contable", FAVORABLE, "Balances del mismo período."))
        else:
            crits.append(Criterio("periodo", "Período contable", SIN_DATO,
                                  "Falta la fecha del último balance de alguno de los dos (se completa en la próxima descarga)."))

        if _tiene_problema_moneda(ficha_alt) or _tiene_problema_moneda(ficha_obj):
            crits.append(Criterio("moneda", "Moneda", NEUTRO,
                                  "El balance de alguno está en otra moneda que su cotización: algunos ratios se recalcularon "
                                  "en USD o se descartaron."))
            degradar = True
        else:
            crits.append(Criterio("moneda", "Moneda", FAVORABLE, "Ratios en la misma moneda que la cotización."))

        if ficha_alt.fecha_dato and (hoy - ficha_alt.fecha_dato).days > ve.DIAS_DATO_VIEJO:
            crits.append(Criterio("frescura", "Frescura", NEUTRO,
                                  f"Datos del {ficha_alt.fecha_dato.strftime('%d/%m/%Y')}: pueden estar desactualizados."))
            degradar = True

    if degradar and nivel == ALTA:
        nivel = MEDIA
        notas.append("Sería alta, pero los datos no son del todo comparables (período, moneda o frescura): queda en media.")
    if nivel == BAJA and alt.a_mano:
        nivel = MEDIA
        notas.append("La agregaste vos como par: se respeta y entra al ranking, aunque por sus características la comparabilidad automática sería baja.")
    if alt.quitado:
        notas.append("La quitaste vos de tus pares.")

    por_clave = {c.clave: c for c in crits}
    return Comparabilidad(nivel, _resumen(nivel, por_clave), crits, notas)


# ---------------------------------------------------------------------------------------------
# Selección
# ---------------------------------------------------------------------------------------------

def _distancia(obj: Perfil, alt: Perfil) -> float:
    pen = pe.PENALIZACION_REGION if (obj.c.region and alt.c.region and alt.c.region != obj.c.region) else 0.0
    return pe._distancia_tamano(alt.c.tamano_usd, obj.c.tamano_usd) + pen


def _orden(obj: Perfil, alt: Perfil, comp: Comparabilidad):
    return (_RANK_NIVEL[comp.nivel], round(_distancia(obj, alt), 6), alt.base)


def _a_alternativa(alt: Perfil, comp: Comparabilidad, origen: str) -> Alternativa:
    c = alt.c
    return Alternativa(
        ticker_base=alt.base, nombre=c.nombre, origen=origen, en_grupo=alt.en_grupo, a_mano=alt.a_mano,
        nivel=comp.nivel, resumen=comp.resumen, criterios=comp.criterios, notas=comp.notas, en_ranking=comp.apta,
        tamano_usd=c.tamano_usd, region=c.region, sector=c.sector, industria=c.industria_raw,
    )


def seleccionar(
    obj: Perfil,
    pool: list[Perfil],
    ficha_de: Callable[[str], ve.Ficha | None],
    con: list[str] | None = None,
    hoy: date | None = None,
) -> Seleccion:
    """Qué alternativas se comparan, cuáles se sugieren y cuáles se descartan (con el motivo).

    Sin `con` (el usuario no eligió): los pares del grupo con comparabilidad alta o media, hasta
    `N_DEFAULT`. Con `con`: exactamente esos (hasta `MAX_ALTERNATIVAS`), cada uno con su nivel; los
    de nivel bajo se ven en la tabla pero no cuentan para el ranking.
    """
    hoy = hoy or date.today()
    ficha_obj = ficha_de(obj.base)
    por_base = {p.base: p for p in pool if p.base != obj.base}
    pedidos = list(dict.fromkeys(b for b in (con or []) if b != obj.base))[:MAX_ALTERNATIVAS]
    elegido_por_usuario = bool(pedidos)

    estructural = {b: comparabilidad_estructural(obj, p) for b, p in por_base.items()}
    necesarios = [b for b in pedidos if b in por_base] + [b for b, p in por_base.items() if p.en_grupo]
    ya = set(necesarios)
    extra = sorted(
        (p for b, p in por_base.items() if b not in ya and not p.quitado and estructural[b].nivel in APTOS),
        key=lambda p: _orden(obj, p, estructural[p.base]),
    )[:LIMITE_EVALUACION]
    completos: dict[str, Comparabilidad] = {}
    for b in list(dict.fromkeys(necesarios)) + [p.base for p in extra]:
        completos[b] = completar_comparabilidad(estructural[b], obj, por_base[b], ficha_obj, ficha_de(b), hoy)

    rechazadas: list[Rechazo] = []
    if obj.base in (con or []):
        rechazadas.append(Rechazo(obj.base, obj.c.nombre, NO_COMPARABLE,
                                  "Es el mismo instrumento (o una variante de moneda de él): no es una alternativa."))
    nombres = {b: p.c.nombre for b, p in por_base.items()}

    def _rechazo(b: str, comp: Comparabilidad, motivo: str | None = None) -> Rechazo:
        return Rechazo(b, nombres.get(b), comp.nivel, motivo or comp.resumen)

    if elegido_por_usuario:
        origen_sel = "elegida"
        elegidas = []
        por_simbolo: dict[str, str] = {}
        for b in pedidos:
            if b not in por_base:
                rechazadas.append(Rechazo(b, None, NO_COMPARABLE,
                                          "No está entre los instrumentos con datos: se bajan en la próxima corrida de la "
                                          "ingesta (podés agregarlo como par para que entre)."))
                continue
            if completos[b].nivel == NO_COMPARABLE:
                rechazadas.append(_rechazo(b, completos[b]))
                continue
            simbolo = por_base[b].c.simbolo_yahoo
            if simbolo and simbolo in por_simbolo:
                # Dos tickers del mismo emisor (PBR y PETR3): contarlos por separado inflaría el grupo.
                rechazadas.append(Rechazo(b, nombres.get(b), NO_COMPARABLE,
                                          f"Es el mismo emisor que {por_simbolo[simbolo]}, que ya está elegido: no cuenta dos veces."))
                continue
            if simbolo:
                por_simbolo[simbolo] = b
            elegidas.append(b)
    else:
        origen_sel = "grupo"
        en_grupo = [b for b, p in por_base.items() if p.en_grupo]
        aptos = sorted((b for b in en_grupo if completos[b].apta), key=lambda b: _orden(obj, por_base[b], completos[b]))
        elegidas = aptos[:N_DEFAULT]
        for b in en_grupo:
            if b in elegidas or b in aptos:
                continue
            if completos[b].nivel == NO_COMPARABLE:
                rechazadas.append(_rechazo(b, completos[b]))
            else:
                rechazadas.append(_rechazo(
                    b, completos[b],
                    f"Es par de tu grupo, pero la comparabilidad es baja: {completos[b].resumen} "
                    "Podés sumarla igual desde el buscador; se ve en la tabla pero no entra al ranking."))

    alternativas = [_a_alternativa(por_base[b], completos[b], origen_sel) for b in elegidas]
    sel = set(elegidas)
    sugeridas = [
        _a_alternativa(p, completos[b], "sugerida")
        for b, p in sorted(
            ((b, por_base[b]) for b in completos if b not in sel and not por_base[b].quitado and completos[b].apta),
            key=lambda kv: _orden(obj, kv[1], completos[kv[0]]),
        )[:N_SUGERIDAS]
    ]
    return Seleccion(alternativas, sugeridas, rechazadas, nombres)


# ---------------------------------------------------------------------------------------------
# Tabla lado a lado
# ---------------------------------------------------------------------------------------------

def _estado_celda(f: ve.Ficha, clave: str) -> Celda:
    origen = de.origen_metrica(clave, f)
    valor = f.valores.get(clave)
    if clave.startswith("rend_") and f.momentum_aproximado:
        return Celda(None, "moneda", origen)
    if valor is not None:
        return Celda(valor, "dato", origen)
    if clave in f.descartadas_moneda:
        return Celda(None, "moneda", origen)
    if f.sin_ganancias and clave in ("pe", "forward_pe", "peg", "crec_ganancias", "crec_esperado"):
        return Celda(None, "sin_ganancias", origen)
    if not de._aplica(clave, f.sector):
        return Celda(None, "no_aplica", origen)
    return Celda(None, "sin_dato", origen)


def _columna(p: Perfil, f: ve.Ficha | None, es_objetivo: bool, nivel: str | None, en_ranking: bool) -> Columna:
    c = p.c
    return Columna(
        ticker_base=p.base, nombre=c.nombre, es_objetivo=es_objetivo, nivel=nivel, en_ranking=en_ranking,
        fecha_dato=f.fecha_dato if f else None, periodo_contable=f.periodo_contable if f else None,
        fecha_serie=f.fecha_serie if f else None, aviso_moneda=_tiene_problema_moneda(f),
        tamano_usd=c.tamano_usd, region=c.region, sector=c.sector, industria=c.industria_raw,
    )


def armar_tabla(
    obj: Perfil, ficha_obj: ve.Ficha, miembros: list[tuple[Perfil, ve.Ficha, str, bool]],
) -> Tabla:
    """`miembros`: (perfil, ficha, nivel, en_ranking) de las alternativas, en el orden de las columnas."""
    modelo = modelo_negocio(obj.c.sector, ficha_obj.es_etf)
    apoyo = ve.familias_que_solo_apoyan(ficha_obj.sector, ficha_obj.es_etf)
    columnas = [_columna(obj, ficha_obj, True, None, True)] + [_columna(p, f, False, n, r) for p, f, n, r in miembros]
    fichas = {obj.base: ficha_obj, **{p.base: f for p, f, _, _ in miembros}}
    en_ranking = {obj.base} | {p.base for p, _, _, r in miembros if r}

    filas: list[FilaTabla] = []
    vacias: list[str] = []
    for clave in METRICAS_POR_MODELO[modelo]:
        m = ve.METRICA_POR_CLAVE[clave]
        celdas = {b: _estado_celda(f, clave) for b, f in fichas.items()}
        if not any(c.estado == "dato" for c in celdas.values()):
            vacias.append(m.nombre)
            continue
        con_dato = {b: c.valor for b, c in celdas.items() if c.estado == "dato" and b in en_ranking}
        mejor = peor = None
        if len(con_dato) >= 2 and len(set(con_dato.values())) > 1:
            ordenados = sorted(con_dato, key=lambda b: con_dato[b], reverse=m.mayor_es_mejor)
            mejor, peor = ordenados[0], ordenados[-1]
        filas.append(FilaTabla(
            clave=clave, nombre=m.nombre, grupo=m.grupo, formato=m.formato,
            unidad="veces (x)" if m.formato == "x" else "%",
            periodo=PERIODO_METRICA.get(clave, "último dato informado por Yahoo"),
            mayor_es_mejor=m.mayor_es_mejor,
            solo_apoya=bool(m.familia and m.familia in apoyo),
            celdas=celdas, mejor=mejor, peor=peor,
        ))

    no_aplican: list[NoAplica] = []
    if modelo == MODELO_ETF:
        no_aplican.append(NoAplica("Márgenes, ROE, crecimiento y deuda", MOTIVO_NO_APLICA_ETF))
    else:
        for clave in ("ev_ebitda", "ps", "fcf_yield", "margen_bruto", "deuda_patrimonio"):
            if not de._aplica(clave, ficha_obj.sector):
                no_aplican.append(NoAplica(ve.METRICA_POR_CLAVE[clave].nombre, MOTIVO_NO_APLICA[clave]))
        if ficha_obj.sin_ganancias:
            no_aplican.append(NoAplica("P/E y crecimiento de ganancias",
                                       "el instrumento no tiene ganancias en los últimos 12 meses: esos indicadores no tienen sentido"))
    return Tabla(columnas, filas, no_aplican, vacias)


# ---------------------------------------------------------------------------------------------
# Ranking dentro del grupo comparable
# ---------------------------------------------------------------------------------------------

REGLA_RANKING = (
    "se vuelve a calcular el diagnóstico de cada miembro contra los demás miembros del grupo (no contra sus pares "
    "automáticos) y se ordena por la mediana de los percentiles favorables de las métricas de la dimensión; en "
    "solidez se ordena primero por el estado. Puesto 1 = el mejor (en valuación, el más barato). Los empates "
    "comparten puesto. Hace falta que al menos 3 miembros tengan dato: con menos no hay ranking"
)
REGLA_TERCIOS = (
    "arriba: primer tercio de los puestos; abajo: último tercio; medio: el resto (con 4 miembros sólo el 1.º es arriba y "
    "sólo el 4.º es abajo)"
)


def _clave_orden(dimension: str, d: de.Dimension) -> tuple | None:
    if d.nivel in (de.SIN_DATOS, de.NO_APLICA):
        return None
    if dimension == "solidez":
        return (NIVEL_SOLIDEZ_ORDEN.get(d.nivel, 0), d.percentil if d.percentil is not None else -1)
    if d.percentil is None:
        return None
    return (d.percentil,)


def _tercio(posicion: int | None, de_: int) -> str | None:
    if posicion is None or de_ < ve.N_MIN_PERCENTIL:
        return None
    rel = (posicion - 1) / (de_ - 1)
    return ARRIBA if rel < 1 / 3 else ABAJO if rel > 2 / 3 else MEDIO


def rankear(
    obj_base: str, fichas: dict[str, ve.Ficha], hoy: date,
) -> tuple[list[RankingDimension], dict[str, de.Diagnostico], dict[str, ve.ResultadoValuacion]]:
    """Diagnóstico de cada miembro contra los demás y ranking por dimensión. `fichas` incluye al objetivo."""
    resultados: dict[str, ve.ResultadoValuacion] = {}
    diags: dict[str, de.Diagnostico] = {}
    for base, f in fichas.items():
        otros = [g for b, g in fichas.items() if b != base]
        res = ve.evaluar(f, otros, hoy=hoy)
        resultados[base] = res
        diags[base] = de.diagnosticar(f, res, otros, hoy=hoy)

    es_etf = fichas[obj_base].es_etf
    ranking: list[RankingDimension] = []
    for dim in (("valuacion",) if es_etf else DIMENSIONES):
        por_base = {b: next(x for x in dg.dimensiones if x.clave == dim) for b, dg in diags.items()}
        claves = {b: _clave_orden(dim, d) for b, d in por_base.items()}
        ordenables = sorted((b for b in claves if claves[b] is not None), key=lambda b: (claves[b], b), reverse=True)
        posiciones: dict[str, int] = {}
        for b in ordenables:
            posiciones[b] = 1 + sum(1 for c in ordenables if claves[c] > claves[b])
        puestos = [
            PuestoDimension(b, posiciones.get(b), por_base[b].estado, por_base[b].nivel, por_base[b].percentil)
            for b in sorted(por_base, key=lambda b: (posiciones.get(b, 10**6), b))
        ]
        de_ = len(ordenables)
        pos_obj = posiciones.get(obj_base)
        ranking.append(RankingDimension(
            clave=dim, nombre=NOMBRE_DIMENSION[dim], regla=REGLA_RANKING + ". " + REGLA_TERCIOS, puestos=puestos,
            posicion_objetivo=pos_obj, de=de_, tercio=_tercio(pos_obj, de_),
            estado_objetivo=por_base[obj_base].estado, nivel_objetivo=por_base[obj_base].nivel,
        ))
    return ranking, diags, resultados


# ---------------------------------------------------------------------------------------------
# Ventajas y desventajas de a pares
# ---------------------------------------------------------------------------------------------

def _regla_directa() -> str:
    return (f"diferencia de al menos {ve.UMBRAL_DIRECTO * 100:.0f}% (o {ve.PISO_DIRECTO_PCT * 100:.0f} puntos en métricas en %) "
            "a favor o en contra; el veredicto de la dimensión es el de la mayoría de sus métricas")


def _lista(items: list[str]) -> str:
    return ve._lista(items)


def comparar_par(
    obj: ve.Ficha, alt: ve.Ficha, ticker_alt: str, orientativa: bool,
) -> ComparacionPar:
    """El objetivo frente a una alternativa, dimensión por dimensión, con comparación directa (±15 %)."""
    modelo = modelo_negocio(obj.sector, obj.es_etf)
    relevantes = set(METRICAS_POR_MODELO[modelo])
    apoyo = ve.familias_que_solo_apoyan(obj.sector, obj.es_etf)
    lineas: list[Linea] = []
    veredictos: dict[str, str | None] = {}

    for dim in (("valuacion",) if obj.es_etf else DIMENSIONES):
        mejores: list[tuple[str, str]] = []
        peores: list[tuple[str, str]] = []
        medias = 0
        for clave in METRICAS_DIMENSION[dim]:
            m = ve.METRICA_POR_CLAVE[clave]
            if clave not in relevantes or (m.familia and m.familia in apoyo):
                continue
            propio, otro = obj.valores.get(clave), alt.valores.get(clave)
            if propio is None or otro is None:
                continue
            r = ve.evaluar_metrica(m, propio, [otro])
            detalle = f"{ve._en_frase(m.nombre)} ({_valor(propio, m.formato)} vs. {_valor(otro, m.formato)})"
            if r.banda == "mejor":
                mejores.append((clave, detalle))
            elif r.banda == "peor":
                peores.append((clave, detalle))
            else:
                medias += 1
        total = len(mejores) + len(peores) + medias
        if total == 0:
            veredictos[dim] = None
            continue
        veredicto = "mejor" if len(mejores) > len(peores) else "peor" if len(peores) > len(mejores) else "similar"
        veredictos[dim] = veredicto
        if dim == "valuacion":
            partes = []
            if mejores:
                partes.append("más barata en " + _lista([d for _, d in mejores]))
            if peores:
                partes.append("más cara en " + _lista([d for _, d in peores]))
            texto = "Valuación: " + ("; ".join(partes) if partes else "en línea en las métricas comparables") + "."
            tono = "neutro"
        else:
            partes = []
            if mejores:
                partes.append("mejor en " + _lista([d for _, d in mejores]))
            if peores:
                partes.append("peor en " + _lista([d for _, d in peores]))
            texto = f"{NOMBRE_DIMENSION[dim]}: " + ("; ".join(partes) if partes else "en línea en las métricas comparables") + "."
            tono = "positivo" if veredicto == "mejor" else "negativo" if veredicto == "peor" else "neutro"
        lineas.append(Linea(dim, veredicto, texto, tono, [c for c, _ in mejores + peores], _regla_directa()))

    domina, texto_dom = None, ""
    fund = [veredictos.get(d) for d in FUNDAMENTOS]
    evaluadas = [v for v in fund if v is not None]
    if not obj.es_etf and len(evaluadas) >= 2 and not orientativa:
        if veredictos.get("valuacion") == "peor" and "mejor" not in evaluadas:
            domina = "alternativa"
            texto_dom = (f"{ticker_alt} cotiza más barata y, en los datos disponibles, no es peor en "
                         f"{_lista([NOMBRE_DIMENSION[d].lower() for d, v in zip(FUNDAMENTOS, fund) if v is not None])}.")
        elif veredictos.get("valuacion") == "mejor" and "peor" not in evaluadas:
            domina = "objetivo"
            texto_dom = (f"Cotiza más barata que {ticker_alt} y, en los datos disponibles, no es peor en "
                         f"{_lista([NOMBRE_DIMENSION[d].lower() for d, v in zip(FUNDAMENTOS, fund) if v is not None])}.")
    return ComparacionPar(ticker_alt, orientativa, lineas, veredictos, domina, texto_dom)


# ---------------------------------------------------------------------------------------------
# Conclusión
# ---------------------------------------------------------------------------------------------

REGLA_CONCLUSION = (
    "se mira en qué tercio del grupo cae el instrumento en valuación (arriba = más barato) y en calidad, crecimiento "
    "y solidez. Fundamento fuerte: tercio mejor y sin alerta propia (calidad débil, ingresos en caída, solidez "
    "frágil). Debilidad: tercio peor o alerta propia. R1: entre los más caros + algún fundamento fuerte + ninguna "
    "debilidad; R2: entre los más caros sin ese respaldo; R3: entre los más baratos + alguna debilidad; R4: entre los "
    "más baratos sin debilidades; R5: en el medio"
)
_TXT_VAL = {ARRIBA: "entre los más baratos del grupo", MEDIO: "en el medio del grupo", ABAJO: "entre los más caros del grupo"}
_TXT_FUND = {ARRIBA: "entre los mejores del grupo", MEDIO: "en el medio del grupo", ABAJO: "entre los peores del grupo"}


def _metricas_dim(d: de.Dimension) -> list[str]:
    claves: list[str] = []
    for v in d.votos:
        claves += v["metricas"]
    for r in d.razones:
        claves += r.metricas
    return list(dict.fromkeys(claves))


def _origen_dim(d: de.Dimension, ficha: ve.Ficha) -> str:
    return de._origen_conjunto(_metricas_dim(d), ficha)


def _clasificar_fundamentos(ranking: dict[str, RankingDimension]) -> tuple[list[str], list[str], list[str]]:
    fuertes, debiles, sin_evaluar = [], [], []
    for dim in FUNDAMENTOS:
        r = ranking.get(dim)
        if r is None or r.nivel_objetivo in (de.NO_APLICA,):
            continue
        alerta = r.nivel_objetivo == de.RIESGO
        if r.tercio == ABAJO or alerta:
            debiles.append(dim)
        elif r.tercio == ARRIBA:
            fuertes.append(dim)
        elif r.tercio is None:
            sin_evaluar.append(dim)
    return fuertes, debiles, sin_evaluar


def _puesto(r: RankingDimension) -> str:
    return f"puesto {r.posicion_objetivo} de {r.de}"


def _razones_dim(d: de.Dimension, tonos: tuple[str, ...], dimension: str, limite: int = 2) -> list[FraseConclusion]:
    out = []
    for rz in d.razones:
        if rz.tono in tonos:
            out.append(FraseConclusion(rz.texto, rz.regla or d.regla, "positivo" if "positivo" in tonos else "negativo",
                                       rz.origen, list(rz.metricas), dimension))
        if len(out) >= limite:
            break
    return out


def _firmeza(n_miembros: int, diag_obj: de.Diagnostico, comps: list[Comparabilidad]) -> tuple[str, list[str]]:
    razones: list[str] = []
    niveles = []
    if n_miembros >= 5:
        niveles.append(2)
        razones.append(f"Grupo de {n_miembros} instrumentos (5 o más): los percentiles son razonablemente finos.")
    else:
        niveles.append(1)
        razones.append(f"Grupo de sólo {n_miembros} instrumentos: el percentil es grueso, el ranking es orientativo.")
    conf = {"alta": 2, "media": 1, "baja": 0}.get(diag_obj.confianza, 0)
    niveles.append(conf)
    razones.append(f"Confianza de los datos del instrumento dentro de este grupo: {diag_obj.confianza}.")
    if any(any(c.estado == NEUTRO for c in comp.criterios if c.clave in ("periodo", "moneda", "frescura")) for comp in comps):
        niveles.append(1)
        razones.append("Alguna alternativa tiene balances de otro período, otra moneda o datos viejos.")
    if any(comp.nivel == MEDIA for comp in comps):
        razones.append("Hay alternativas de comparabilidad media: se parecen, pero no en todo.")
    return {2: "alta", 1: "media", 0: "baja"}[min(niveles)], razones


def concluir(
    obj_base: str, ficha_obj: ve.Ficha, ranking: list[RankingDimension], diag_obj: de.Diagnostico,
    res_obj: ve.ResultadoValuacion, pares: list[ComparacionPar], comps: list[Comparabilidad], n_miembros: int,
) -> Conclusion:
    por_dim = {r.clave: r for r in ranking}
    dims = {d.clave: d for d in diag_obj.dimensiones}
    firmeza, firmeza_razones = _firmeza(n_miembros, diag_obj, comps)
    destacadas = [
        FraseConclusion(p.texto_dominancia, _regla_directa() + "; una alternativa domina si es más barata y ninguna dimensión "
                        "de calidad, crecimiento o solidez la muestra peor (hacen falta al menos 2 dimensiones con dato)",
                        "alerta" if p.domina == "alternativa" else "positivo", "calculado", [], None)
        for p in pares if p.domina
    ]
    val = por_dim["valuacion"]

    # -- ETF: sólo valuación (costo, P/VL, dividendo) y rendimiento --
    if ficha_obj.es_etf:
        frases = []
        if val.tercio:
            frases.append(FraseConclusion(
                f"En valuación (gastos, P/VL y dividendo) está {_TXT_VAL[val.tercio]} ({_puesto(val)}).",
                REGLA_RANKING, "neutro", _origen_dim(dims["valuacion"], ficha_obj), _metricas_dim(dims["valuacion"]), "valuacion"))
        for r in res_obj.metricas:
            if r.clave in ("gastos", "pb", "div_yield") and r.banda in ("mejor", "peor") and r.valor is not None:
                frases.append(FraseConclusion(
                    f"{r.nombre}: {_valor(r.valor, r.formato)} contra {_valor(r.mediana_pares, r.formato)} de mediana del grupo "
                    f"({'más favorable' if r.banda == 'mejor' else 'menos favorable'}).",
                    f"percentil favorable {'≥ 75' if r.banda == 'mejor' else '≤ 25'} dentro del grupo (o ±15% contra el único par)",
                    "positivo" if r.banda == "mejor" else "negativo", de.origen_metrica(r.clave, ficha_obj), [r.clave], "valuacion"))
        frases.append(FraseConclusion(
            "No hay composición de tenencias: no se puede saber cuánto se superponen estos fondos, sólo cómo se comparan en costo y valuación.",
            "los ETF se evalúan por gastos, P/VL, dividendo y rendimiento", "alerta", "calculado", [], None))
        return Conclusion("ETF", "Costo y valuación frente a los otros ETF del grupo", frases, destacadas, [], [],
                          SALVEDAD_MULTIPLO, firmeza, firmeza_razones, list(LIMITES), REGLA_CONCLUSION)

    fuertes, debiles, sin_evaluar = _clasificar_fundamentos(por_dim)

    def _txt_dim(dim: str) -> str:
        r = por_dim[dim]
        base = f"{NOMBRE_DIMENSION[dim]} ({r.estado_objetivo.lower()})"
        return base if r.tercio is None else f"{base}, {_TXT_FUND[r.tercio]} ({_puesto(r)})"

    def _frases_dim(dims_: list[str], tono: str, prefijo: str) -> list[FraseConclusion]:
        out = []
        for dim in dims_:
            d = dims[dim]
            r = por_dim[dim]
            out.append(FraseConclusion(f"{prefijo}{_txt_dim(dim)}.", REGLA_RANKING + ". " + REGLA_TERCIOS + "; " + d.regla,
                                       tono, _origen_dim(d, ficha_obj), _metricas_dim(d), dim))
        return out

    mayor = [f for dim in fuertes for f in _razones_dim(dims[dim], ("positivo",), dim)]
    menor = [f for dim in debiles for f in _razones_dim(dims[dim], ("negativo", "alerta"), dim)]
    for lista, tonos_dim, destino in ((fuertes, "positivo", mayor), (debiles, "negativo", menor)):
        if not destino and lista:
            destino += _frases_dim(lista, tonos_dim, "")

    frases: list[FraseConclusion] = []
    if val.tercio is None:
        regla_ap = "R0"
        titulo = "No hay suficientes datos de valuación en el grupo para ubicar el precio"
        frases.append(FraseConclusion(
            "Dentro de este grupo no alcanzan los datos de valuación para decir si cotiza más barato o más caro.",
            "hacen falta al menos 3 miembros con dato de valuación", "alerta", "calculado", [], "valuacion"))
        frases += _frases_dim(fuertes, "positivo", "Fortaleza: ") + _frases_dim(debiles, "negativo", "Debilidad: ")
    else:
        pos_val = FraseConclusion(
            f"En valuación está {_TXT_VAL[val.tercio]} ({_puesto(val)}, de más barata a más cara).",
            REGLA_RANKING + ". " + REGLA_TERCIOS, "neutro", _origen_dim(dims["valuacion"], ficha_obj),
            _metricas_dim(dims["valuacion"]), "valuacion")
        if val.tercio == ABAJO and fuertes and not debiles:
            regla_ap = "R1"
            titulo = "Cotiza con prima, y sus fundamentos la acompañan"
            frases += [pos_val] + _frases_dim(fuertes, "positivo", "Lo que la respalda: ")
            frases.append(FraseConclusion(
                "Esa diferencia de calidad, crecimiento o solidez puede explicar que el mercado le pague un múltiplo mayor que a sus alternativas.",
                "R1: entre los más caros del grupo + al menos un fundamento fuerte + ninguna debilidad", "neutro", "calculado",
                [], None))
        elif val.tercio == ABAJO:
            regla_ap = "R2"
            titulo = "Cotiza con prima que los datos no respaldan"
            frases += [pos_val]
            if debiles:
                frases += _frases_dim(debiles, "negativo", "Lo que no la acompaña: ")
            else:
                frases.append(FraseConclusion(
                    "Ni calidad, crecimiento ni solidez la ubican entre las mejores del grupo.",
                    "R2: entre los más caros del grupo sin ningún fundamento fuerte", "negativo", "calculado", [], None))
            frases.append(FraseConclusion(
                "Con estos datos, un múltiplo mayor que el de sus alternativas sería más difícil de justificar.",
                "R2: entre los más caros del grupo sin ese respaldo", "neutro", "calculado", [], None))
        elif val.tercio == ARRIBA and debiles:
            regla_ap = "R3"
            titulo = "Cotiza con descuento, y hay razones que podrían explicarlo"
            frases += [pos_val] + _frases_dim(debiles, "negativo", "Posible explicación: ")
            frases.append(FraseConclusion(
                "Ese descuento puede reflejar que el mercado le asigna un múltiplo menor por esas debilidades.",
                "R3: entre los más baratos del grupo + al menos una debilidad", "neutro", "calculado", [], None))
        elif val.tercio == ARRIBA:
            regla_ap = "R4"
            titulo = "Cotiza con descuento y los datos no muestran una debilidad que lo explique"
            frases += [pos_val]
            frases += _frases_dim(fuertes, "positivo", "Además: ") if fuertes else []
            frases.append(FraseConclusion(
                "Frente a este grupo no aparece una debilidad de calidad, crecimiento o solidez que explique el descuento; "
                "puede deberse a algo que estos datos no ven (historia contable, estimaciones, riesgos del negocio).",
                "R4: entre los más baratos del grupo y ninguna debilidad", "neutro", "calculado", [], None))
        else:
            regla_ap = "R5"
            titulo = "Cotiza en línea con el grupo"
            frases += [pos_val]
            frases += _frases_dim(fuertes, "positivo", "Mejor que el grupo en: ") + _frases_dim(debiles, "negativo", "Peor que el grupo en: ")
            if not fuertes and not debiles:
                frases.append(FraseConclusion(
                    "Sus fundamentos tampoco se despegan del grupo en ningún sentido.",
                    "R5: en el medio en valuación y sin fortalezas ni debilidades", "neutro", "calculado", [], None))
    if sin_evaluar:
        frases.append(FraseConclusion(
            "Sin ranking por falta de datos en: " + _lista([NOMBRE_DIMENSION[d].lower() for d in sin_evaluar]) + ".",
            "una dimensión necesita al menos 3 miembros con dato para tener ranking", "alerta", "calculado", [], None))
    return Conclusion(regla_ap, titulo, frases, destacadas, mayor, menor, SALVEDAD_MULTIPLO, firmeza, firmeza_razones,
                      list(LIMITES), REGLA_CONCLUSION)


# ---------------------------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------------------------

def _mensaje_insuficiente(n_aptas: int, n_baja: int, hay_sugeridas: bool) -> tuple[str, int]:
    faltan = MIN_ALTERNATIVAS - n_aptas
    texto = (f"Hay {n_aptas} alternativa{'s' if n_aptas != 1 else ''} comparable{'s' if n_aptas != 1 else ''} con datos y hacen falta "
             f"{MIN_ALTERNATIVAS} para poder ordenar y concluir (faltan {faltan}).")
    if n_baja:
        texto += f" {n_baja} de las elegidas tiene comparabilidad baja: se ve en la tabla pero no cuenta."
    texto += (" Sumá alguna de las sugeridas." if hay_sugeridas
              else " Agregá alguna desde el buscador, idealmente de la misma industria, tamaño y región.")
    return texto, faltan


def comparar(
    obj: Perfil,
    pool: list[Perfil],
    ficha_de: Callable[[str], ve.Ficha | None],
    con: list[str] | None = None,
    hoy: date | None = None,
) -> Comparador:
    hoy = hoy or date.today()
    ficha_obj = ficha_de(obj.base)
    if ficha_obj is None:
        return Comparador(VERSION_REGLAS, "sin_datos",
                          "Todavía no hay fundamentales de este instrumento: la app los baja sola de a poco, o podés pedirlos con \"Actualizar datos\".",
                          MIN_ALTERNATIVAS, MIN_ALTERNATIVAS, None, None, [], [], [], None, [], [], None)
    con_obj, total_obj = cobertura(ficha_obj)
    if total_obj and con_obj / total_obj < COBERTURA_MINIMA:
        return Comparador(VERSION_REGLAS, "sin_datos",
                          f"El instrumento tiene dato para {con_obj} de {total_obj} métricas aplicables: es muy poco para compararlo.",
                          MIN_ALTERNATIVAS, MIN_ALTERNATIVAS, modelo_negocio(obj.c.sector, ficha_obj.es_etf),
                          _columna(obj, ficha_obj, True, None, True), [], [], [], None, [], [], None)

    sel = seleccionar(obj, pool, ficha_de, con, hoy)
    por_base = {p.base: p for p in pool}
    miembros = [(por_base[a.ticker_base], ficha_de(a.ticker_base), a.nivel, a.en_ranking) for a in sel.alternativas]
    modelo = modelo_negocio(obj.c.sector, ficha_obj.es_etf)
    tabla = armar_tabla(obj, ficha_obj, miembros) if miembros else None
    aptas = [a for a in sel.alternativas if a.en_ranking]
    n_baja = len(sel.alternativas) - len(aptas)

    if len(aptas) < MIN_ALTERNATIVAS:
        mensaje, faltan = _mensaje_insuficiente(len(aptas), n_baja, bool(sel.sugeridas))
        return Comparador(VERSION_REGLAS, "insuficiente", mensaje, MIN_ALTERNATIVAS, faltan, modelo,
                          _columna(obj, ficha_obj, True, None, True), sel.alternativas, sel.sugeridas, sel.rechazadas,
                          tabla, [], [], None)

    fichas = {obj.base: ficha_obj, **{a.ticker_base: ficha_de(a.ticker_base) for a in aptas}}
    ranking, diags, resultados = rankear(obj.base, fichas, hoy)
    pares = [comparar_par(ficha_obj, ficha_de(a.ticker_base), a.ticker_base, not a.en_ranking) for a in sel.alternativas]
    comps = [Comparabilidad(a.nivel, a.resumen, a.criterios, a.notas) for a in aptas]
    conclusion = concluir(obj.base, ficha_obj, ranking, diags[obj.base], resultados[obj.base], pares, comps, len(fichas))
    return Comparador(VERSION_REGLAS, "ok", "", MIN_ALTERNATIVAS, 0, modelo, _columna(obj, ficha_obj, True, None, True),
                      sel.alternativas, sel.sugeridas, sel.rechazadas, tabla, ranking, pares, conclusion)
