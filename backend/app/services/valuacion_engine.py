"""Valuación relativa: ¿cotiza más barato o más caro que sus pares? Puro: sin DB ni red.

**No hay puntaje único** (mismo criterio que Salud de cartera). Por cada métrica se informa dónde
cae el emisor dentro de su grupo de pares (percentil), y la lectura final sale de reglas que se
muestran tal cual. Lo que se quiere evitar es el número mágico "7,3/10" que no se puede auditar.

Grupos de métricas:
- **Valuación** (¿barata o cara?): P/E, P/E estimado, EV/EBITDA, P/Ventas, P/Valor libro, PEG,
  rendimiento del flujo de caja libre, dividendo. En ETFs además los **gastos** anuales.
- **Calidad**: márgenes, ROE, ROA, deuda/patrimonio.
- **Crecimiento**: de ingresos y de ganancias.
- **Momentum**: rendimiento en USD a 3, 6 y 12 meses.

Calidad y crecimiento existen para no presentar como oportunidad algo que está barato por una
buena razón: una empresa "barata" con márgenes en el piso de su grupo, ingresos cayendo o un precio
que viene hundiéndose es una **posible trampa de valor**, y se dice así.

Limpieza de datos (Yahoo trae de todo):
- P/E con ganancias negativas no tiene sentido: no entra al percentil y se avisa "sin ganancias".
- Topes de cordura (P/E > 300 es ruido contable, no valuación).
- Cuando el balance está en otra moneda que la cotización (ADRs argentinos, `.BA`) los ratios de
  Yahoo mezclan monedas: P/E y P/Ventas se recalculan con las magnitudes ya pasadas a USD por la
  ingesta, y los que no se pueden recalcular se descartan.
- Con 5 o más valores, la distribución de los pares se recorta en `Q1 − 3·IQR` / `Q3 + 3·IQR`
  para que un outlier no aplaste el resto.
- Con menos de `N_MIN_PERCENTIL` valores no se calcula percentil: no se compara contra casi nadie.

Unidades de Yahoo (verificadas): `dividendYield` y `netExpenseRatio` vienen en **porcentaje**,
`yield` (ETFs), márgenes, ROE y crecimientos en **fracción**, `debtToEquity` en **porcentaje**.
Acá todo queda en fracción (0,023 = 2,3 %) o en veces ("x").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Callable

N_MIN_PERCENTIL = 3
N_MIN_WINSORIZAR = 5
TOPE_MULTIPLO = 300.0
TOPE_PEG = 10.0
BANDA_BAJA = 25.0
BANDA_ALTA = 75.0
DIAS_DATO_VIEJO = 21

SECTORES_SIN_EBITDA = ("Financiero", "Inmobiliario")

LECTURA_BARATA = "barata"
LECTURA_CARA = "cara"
LECTURA_EN_LINEA = "en_linea"
LECTURA_MIXTA = "mixta"
LECTURA_TRAMPA = "barata_con_alertas"
LECTURA_CARA_JUSTIFICADA = "cara_justificada"
LECTURA_SIN_DATOS = "datos_insuficientes"

TEXTO_LECTURA = {
    LECTURA_BARATA: "Más barata que sus pares",
    LECTURA_CARA: "Más cara que sus pares",
    LECTURA_EN_LINEA: "En línea con sus pares",
    LECTURA_MIXTA: "Señales mixtas",
    LECTURA_TRAMPA: "Barata, con señales de alerta",
    LECTURA_CARA_JUSTIFICADA: "Cara, con fundamentos que la acompañan",
    LECTURA_SIN_DATOS: "Datos insuficientes",
}


@dataclass(frozen=True)
class Metrica:
    clave: str
    nombre: str
    grupo: str            # "valuacion" | "calidad" | "crecimiento" | "momentum"
    mayor_es_mejor: bool  # en valuación, "mejor" = más barata
    formato: str          # "x" | "pct"
    solo_etf: bool = False
    solo_accion: bool = False


METRICAS = (
    Metrica("pe", "P/E", "valuacion", False, "x"),
    Metrica("forward_pe", "P/E estimado", "valuacion", False, "x", solo_accion=True),
    Metrica("ev_ebitda", "EV/EBITDA", "valuacion", False, "x", solo_accion=True),
    Metrica("ps", "P/Ventas", "valuacion", False, "x", solo_accion=True),
    Metrica("pb", "P/Valor libro", "valuacion", False, "x"),
    Metrica("peg", "PEG", "valuacion", False, "x", solo_accion=True),
    Metrica("fcf_yield", "Rendimiento FCF", "valuacion", True, "pct", solo_accion=True),
    Metrica("div_yield", "Dividendo", "valuacion", True, "pct"),
    Metrica("gastos", "Gastos anuales", "valuacion", False, "pct", solo_etf=True),
    Metrica("margen_bruto", "Margen bruto", "calidad", True, "pct", solo_accion=True),
    Metrica("margen_operativo", "Margen operativo", "calidad", True, "pct", solo_accion=True),
    Metrica("margen_neto", "Margen neto", "calidad", True, "pct", solo_accion=True),
    Metrica("roe", "ROE", "calidad", True, "pct", solo_accion=True),
    Metrica("roa", "ROA", "calidad", True, "pct", solo_accion=True),
    Metrica("deuda_patrimonio", "Deuda/Patrimonio", "calidad", False, "x", solo_accion=True),
    Metrica("crec_ingresos", "Crecimiento de ingresos", "crecimiento", True, "pct", solo_accion=True),
    Metrica("crec_ganancias", "Crecimiento de ganancias", "crecimiento", True, "pct", solo_accion=True),
    Metrica("rend_3m", "Rendimiento 3 meses", "momentum", True, "pct"),
    Metrica("rend_6m", "Rendimiento 6 meses", "momentum", True, "pct"),
    Metrica("rend_12m", "Rendimiento 12 meses", "momentum", True, "pct"),
)
METRICA_POR_CLAVE = {m.clave: m for m in METRICAS}


def metricas_para(es_etf: bool) -> list[Metrica]:
    return [m for m in METRICAS if not (m.solo_etf and not es_etf) and not (m.solo_accion and es_etf)]


# ---------------------------------------------------------------------------------------------
# Extracción y limpieza
# ---------------------------------------------------------------------------------------------

def _pos(v) -> float | None:
    return v if isinstance(v, (int, float)) and v > 0 else None


def _multiplo(v, tope: float = TOPE_MULTIPLO) -> float | None:
    v = _pos(v)
    return v if v is not None and v <= tope else None


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


@dataclass
class Extraidas:
    valores: dict[str, float | None]
    sin_ganancias: bool = False
    recalculadas: list[str] = field(default_factory=list)
    descartadas_moneda: list[str] = field(default_factory=list)


def extraer_metricas(
    metricas_raw: dict,
    ratios_confiables: bool,
    es_etf: bool,
    sector: str | None,
) -> Extraidas:
    """Las métricas limpias de un snapshot (`FundamentalesSnapshot.metricas`)."""
    m = metricas_raw or {}
    usd = m.get("_usd") or {}
    mcap = _pos(usd.get("market_cap"))
    v: dict[str, float | None] = {}
    out = Extraidas(valores=v)

    # -- P/E --
    trailing = _num(m.get("trailingPE"))
    net_usd = _num(usd.get("netIncomeToCommon"))
    if ratios_confiables:
        if trailing is not None and trailing <= 0:
            out.sin_ganancias = True
        v["pe"] = _multiplo(trailing)
    elif mcap and net_usd is not None:
        if net_usd <= 0:
            out.sin_ganancias = True
            v["pe"] = None
        else:
            v["pe"] = _multiplo(mcap / net_usd)
            out.recalculadas.append("pe")
    else:
        v["pe"] = None
    if not es_etf and net_usd is not None and net_usd <= 0:
        out.sin_ganancias = True
        v["pe"] = None

    if es_etf:
        v["pb"] = _multiplo(m.get("priceToBook"), 100.0)
        dy = _num(m.get("yield"))
        v["div_yield"] = dy if dy is not None and dy >= 0 else None
        gastos = _num(m.get("netExpenseRatio"))
        if gastos is not None:
            v["gastos"] = gastos / 100.0 if gastos >= 0 else None
        else:
            anual = _num(m.get("annualReportExpenseRatio"))
            v["gastos"] = anual if anual is not None and anual >= 0 else None
        return out

    sin_ebitda = sector in SECTORES_SIN_EBITDA

    # -- Ratios que sólo valen en la misma moneda --
    if ratios_confiables:
        v["forward_pe"] = _multiplo(m.get("forwardPE"))
        v["ev_ebitda"] = None if sin_ebitda else _multiplo(m.get("enterpriseToEbitda"))
        v["ps"] = None if sin_ebitda else _multiplo(m.get("priceToSalesTrailing12Months"), 100.0)
        v["pb"] = _multiplo(m.get("priceToBook"), 100.0)
        v["peg"] = _multiplo(m.get("trailingPegRatio") or m.get("pegRatio"), TOPE_PEG)
    else:
        rev_usd = _pos(usd.get("totalRevenue"))
        v["ps"] = None if sin_ebitda or not (mcap and rev_usd) else _multiplo(mcap / rev_usd, 100.0)
        if v["ps"] is not None:
            out.recalculadas.append("ps")
        v["forward_pe"] = v["ev_ebitda"] = v["pb"] = v["peg"] = None
        out.descartadas_moneda = ["forward_pe", "pb", "peg"] + ([] if sin_ebitda else ["ev_ebitda"])

    fcf_usd = _num(usd.get("freeCashflow"))
    v["fcf_yield"] = fcf_usd / mcap if fcf_usd is not None and mcap else None
    dy = _num(m.get("dividendYield"))
    v["div_yield"] = dy / 100.0 if dy is not None and dy >= 0 else None

    # -- Calidad y crecimiento (no dependen de la moneda: son proporciones) --
    # El margen bruto de un banco no existe (Yahoo lo informa como 0): no se compara.
    v["margen_bruto"] = None if sin_ebitda else _num(m.get("grossMargins"))
    v["margen_operativo"] = _num(m.get("operatingMargins"))
    v["margen_neto"] = _num(m.get("profitMargins"))
    v["roe"] = _num(m.get("returnOnEquity"))
    v["roa"] = _num(m.get("returnOnAssets"))
    de = _num(m.get("debtToEquity"))
    v["deuda_patrimonio"] = None if sin_ebitda or de is None or de < 0 else de / 100.0
    v["crec_ingresos"] = _num(m.get("revenueGrowth"))
    v["crec_ganancias"] = _num(m.get("earningsGrowth"))
    return out


def rendimientos(
    serie: list[dict] | None,
    a_usd: Callable[[date], float | None] | None = None,
) -> dict[str, float | None]:
    """Rendimiento a 3, 6 y 12 meses de una serie semanal `[{"fecha", "cierre"}]`.

    `a_usd(fecha)` da cuántos USD vale una unidad de la moneda de la serie en esa fecha (None si
    no se sabe). Sin él se asume que la serie ya está en USD. Una serie en pesos sin pasar a USD
    mediría inflación, no desempeño, así que sin factor no hay rendimiento.
    """
    puntos = []
    for p in serie or []:
        try:
            f = date.fromisoformat(p["fecha"])
            c = float(p["cierre"])
        except (KeyError, TypeError, ValueError):
            continue
        if c <= 0:
            continue
        if a_usd is not None:
            factor = a_usd(f)
            if not factor:
                continue
            c *= factor
        puntos.append((f, c))
    puntos.sort()
    salida: dict[str, float | None] = {"rend_3m": None, "rend_6m": None, "rend_12m": None}
    if len(puntos) < 2:
        return salida
    ultima_fecha, ultimo = puntos[-1]
    for clave, semanas in (("rend_3m", 13), ("rend_6m", 26), ("rend_12m", 52)):
        objetivo = ultima_fecha - timedelta(weeks=semanas)
        previos = [(f, c) for f, c in puntos if f <= objetivo]
        if not previos:
            continue
        f0, c0 = previos[-1]
        if (objetivo - f0).days > 14:  # el hueco más cercano está demasiado lejos
            continue
        salida[clave] = ultimo / c0 - 1.0
    return salida


# ---------------------------------------------------------------------------------------------
# Percentiles
# ---------------------------------------------------------------------------------------------

def _cuartiles(valores: list[float]) -> tuple[float, float]:
    s = sorted(valores)
    n = len(s)

    def _q(p: float) -> float:
        pos = p * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)

    return _q(0.25), _q(0.75)


def winsorizar(valores: list[float]) -> list[float]:
    if len(valores) < N_MIN_WINSORIZAR:
        return list(valores)
    q1, q3 = _cuartiles(valores)
    iqr = q3 - q1
    lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
    return [min(max(v, lo), hi) for v in valores]


def percentil(valor: float, grupo: list[float]) -> float:
    """Percentil por rango medio de `valor` dentro de `grupo` (que lo incluye): 0 = el menor."""
    menores = sum(1 for g in grupo if g < valor)
    iguales = sum(1 for g in grupo if g == valor)
    return 100.0 * (menores + 0.5 * iguales) / len(grupo)


@dataclass
class ResultadoMetrica:
    clave: str
    nombre: str
    grupo: str
    formato: str
    valor: float | None
    mediana_pares: float | None
    n: int                      # cuántos valores (pares + el propio) entraron
    percentil: float | None     # "favorable": 100 = el mejor del grupo (en valuación, el más barato)
    banda: str | None           # "mejor" | "peor" | "media" | None
    mayor_es_mejor: bool


def evaluar_metrica(m: Metrica, propio: float | None, pares: list[float | None]) -> ResultadoMetrica:
    validos_pares = [p for p in pares if p is not None]
    mediana = median(validos_pares) if validos_pares else None
    if propio is None or len(validos_pares) + 1 < N_MIN_PERCENTIL:
        return ResultadoMetrica(m.clave, m.nombre, m.grupo, m.formato, propio, mediana,
                                len(validos_pares) + (propio is not None), None, None, m.mayor_es_mejor)
    grupo = winsorizar(validos_pares + [propio])
    propio_w = grupo[-1]
    p = percentil(propio_w, grupo)
    favorable = p if m.mayor_es_mejor else 100.0 - p
    banda = "mejor" if favorable >= BANDA_ALTA else "peor" if favorable <= BANDA_BAJA else "media"
    return ResultadoMetrica(m.clave, m.nombre, m.grupo, m.formato, propio, mediana, len(grupo),
                            round(favorable, 1), banda, m.mayor_es_mejor)


# ---------------------------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------------------------

@dataclass
class Ficha:
    """Lo que se compara de un emisor: métricas limpias + rendimientos + metadatos."""
    ticker_base: str
    valores: dict[str, float | None]
    es_etf: bool = False
    sin_ganancias: bool = False
    recalculadas: list[str] = field(default_factory=list)
    descartadas_moneda: list[str] = field(default_factory=list)
    fecha_dato: date | None = None
    momentum_aproximado: bool = False


@dataclass
class Frase:
    texto: str
    regla: str
    tono: str = "neutro"          # "positivo" | "negativo" | "alerta" | "neutro"
    metricas: list[str] = field(default_factory=list)


@dataclass
class ResultadoValuacion:
    lectura: str
    lectura_texto: str
    regla_lectura: str
    frases: list[Frase]
    metricas: list[ResultadoMetrica]
    n_pares_con_datos: int
    advertencias: list[str] = field(default_factory=list)


def _lista(nombres: list[str]) -> str:
    if len(nombres) <= 1:
        return "".join(nombres)
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _en_frase(nombre: str) -> str:
    """"Margen bruto" -> "margen bruto", pero "ROE" queda "ROE" y "P/E" queda "P/E"."""
    if len(nombre) > 1 and nombre[1].islower():
        return nombre[0].lower() + nombre[1:]
    return nombre


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    signo = "+" if v > 0 else ""
    return f"{signo}{v * 100:.0f}%"


def evaluar(objetivo: Ficha, pares: list[Ficha], hoy: date | None = None) -> ResultadoValuacion:
    hoy = hoy or date.today()
    resultados = [
        evaluar_metrica(m, objetivo.valores.get(m.clave), [p.valores.get(m.clave) for p in pares])
        for m in metricas_para(objetivo.es_etf)
    ]
    por_clave = {r.clave: r for r in resultados}
    n_pares = sum(1 for p in pares if any(v is not None for v in p.valores.values()))

    def _en(grupo: str, banda: str) -> list[ResultadoMetrica]:
        return [r for r in resultados if r.grupo == grupo and r.banda == banda]

    val_con_banda = [r for r in resultados if r.grupo == "valuacion" and r.banda is not None]
    baratas, caras = _en("valuacion", "mejor"), _en("valuacion", "peor")
    calidad_buena = _en("calidad", "mejor") + _en("crecimiento", "mejor")
    calidad_mala = _en("calidad", "peor")
    crec_ing = objetivo.valores.get("crec_ingresos")
    mom12 = por_clave.get("rend_12m")

    frases: list[Frase] = []
    advertencias: list[str] = []

    # -- Lectura --
    regla = ("barata: 2+ métricas de valuación en el cuarto más barato del grupo y ninguna en el más "
             "caro; cara: al revés; mixta: hay de las dos; en línea: el resto")
    if len(val_con_banda) < 2:
        lectura = LECTURA_SIN_DATOS
        regla = f"hacen falta al menos 2 métricas de valuación comparables (hay {len(val_con_banda)})"
    elif len(baratas) >= 2 and not caras:
        lectura = LECTURA_BARATA
    elif len(caras) >= 2 and not baratas:
        lectura = LECTURA_CARA
    elif baratas and caras:
        lectura = LECTURA_MIXTA
    else:
        lectura = LECTURA_EN_LINEA

    # -- Frases de valuación --
    if baratas:
        frases.append(Frase(
            f"Más barata que sus pares en {_lista([r.nombre for r in baratas])}.",
            "percentil favorable ≥ 75 dentro del grupo", "positivo", [r.clave for r in baratas],
        ))
    if caras:
        frases.append(Frase(
            f"Más cara que sus pares en {_lista([r.nombre for r in caras])}.",
            "percentil favorable ≤ 25 dentro del grupo", "negativo", [r.clave for r in caras],
        ))
    if lectura == LECTURA_EN_LINEA and val_con_banda:
        frases.append(Frase("Sus múltiplos están en el rango de sus pares.",
                            "ninguna métrica de valuación en los extremos del grupo", "neutro"))

    # -- Calidad / crecimiento --
    if calidad_buena:
        frases.append(Frase(
            f"Mejor {_lista([_en_frase(r.nombre) for r in calidad_buena])} que sus pares.",
            "calidad o crecimiento con percentil ≥ 75", "positivo", [r.clave for r in calidad_buena],
        ))
    peores_calidad = calidad_mala + _en("crecimiento", "peor")
    if peores_calidad:
        frases.append(Frase(
            f"Peor {_lista([_en_frase(r.nombre) for r in peores_calidad])} que sus pares.",
            "calidad o crecimiento con percentil ≤ 25", "negativo", [r.clave for r in peores_calidad],
        ))

    # -- Momentum --
    if mom12 and mom12.banda in ("mejor", "peor") and mom12.valor is not None:
        verbo = "Subió más que" if mom12.banda == "mejor" else "Quedó atrás de"
        frases.append(Frase(
            f"{verbo} sus pares en 12 meses ({_pct(mom12.valor)} vs. mediana {_pct(mom12.mediana_pares)}).",
            "rendimiento 12 meses en USD, percentil ≥ 75 o ≤ 25", "positivo" if mom12.banda == "mejor" else "negativo",
            ["rend_12m"],
        ))

    if objetivo.sin_ganancias:
        frases.append(Frase("Sin ganancias en los últimos 12 meses: el P/E no aplica.",
                            "resultado neto ≤ 0", "alerta", ["pe"]))

    # -- Trampa de valor / cara justificada --
    if lectura == LECTURA_BARATA:
        motivos = []
        if len(calidad_mala) >= 2:
            motivos.append(f"calidad en el piso del grupo ({_lista([_en_frase(r.nombre) for r in calidad_mala])})")
        if crec_ing is not None and crec_ing < 0:
            motivos.append(f"ingresos cayendo ({_pct(crec_ing)} interanual)")
        if mom12 and mom12.banda == "peor":
            motivos.append("el precio viene quedando atrás de sus pares")
        if objetivo.sin_ganancias:
            motivos.append("no tiene ganancias")
        if motivos:
            lectura = LECTURA_TRAMPA
            regla = ("barata, pero con 2+ métricas de calidad ≤ p25, ingresos cayendo, momentum 12m "
                     "≤ p25 o sin ganancias")
            frases.insert(0, Frase(
                f"Ojo: está barata, pero con señales de trampa de valor: {_lista(motivos)}.",
                regla, "alerta",
            ))
    elif lectura == LECTURA_CARA and len(calidad_buena) >= 2:
        lectura = LECTURA_CARA_JUSTIFICADA
        regla = "cara, pero con 2+ métricas de calidad o crecimiento ≥ p75"
        frases.insert(0, Frase(
            "Cotiza con prima, pero sus fundamentos son mejores que los del grupo.", regla, "neutro",
        ))

    # -- Advertencias --
    if objetivo.recalculadas or objetivo.descartadas_moneda:
        advertencias.append(
            "El balance está en otra moneda que la cotización: "
            + (f"{_lista([METRICA_POR_CLAVE[c].nombre for c in objetivo.recalculadas])} se recalcularon en USD"
               if objetivo.recalculadas else "")
            + ("; " if objetivo.recalculadas and objetivo.descartadas_moneda else "")
            + (f"{_lista([METRICA_POR_CLAVE[c].nombre for c in objetivo.descartadas_moneda])} no se muestran"
               if objetivo.descartadas_moneda else "")
            + "."
        )
    if objetivo.momentum_aproximado:
        advertencias.append("El rendimiento se midió en la moneda local del símbolo, no en USD.")
    if objetivo.fecha_dato and (hoy - objetivo.fecha_dato).days > DIAS_DATO_VIEJO:
        advertencias.append(f"Los datos son del {objetivo.fecha_dato.strftime('%d/%m/%Y')}: pueden estar desactualizados.")
    if n_pares < N_MIN_PERCENTIL - 1:
        advertencias.append("Hay muy pocos pares con datos: la comparación es poco representativa.")

    return ResultadoValuacion(
        lectura=lectura,
        lectura_texto=TEXTO_LECTURA[lectura],
        regla_lectura=regla,
        frases=frases,
        metricas=resultados,
        n_pares_con_datos=n_pares,
        advertencias=advertencias,
    )
