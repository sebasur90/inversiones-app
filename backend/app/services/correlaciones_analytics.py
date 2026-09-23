"""Adaptador entre los datos reales (Session/DB) y `correlaciones_engine` para la pantalla
"Matriz de correlaciones".

A diferencia de `contribucion_analytics.get_correlaciones` (retornos mensuales fin-de-mes,
carry-forward sin tope de antigüedad), este módulo:

- soporta frecuencia diaria/semanal/mensual, no sólo mensual;
- rechaza un boundary si el precio conocido (carry-forward) está más viejo que una tolerancia
  por frecuencia, para no fabricar retornos 0 en huecos de precios;
- nunca encadena un retorno sobre boundaries no consecutivos (si un boundary se rechaza, el
  siguiente retorno válido arranca recién en el boundary consecutivo aceptado).

Ambos módulos coexisten a propósito: `get_correlaciones` sigue sirviendo a la pantalla
Contribución sin cambios (ver test de no-regresión), y esta pantalla nueva declara su propio
criterio, más estricto. Los números mensuales de una y otra pueden diferir ante huecos de datos
(ver `test_mensual_nueva_puede_diferir_de_la_vieja_ante_un_hueco`); es esperado, no un bug.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import correlaciones_engine
from .cache import cache_por_sync
from .inversiones_analytics import (
    EPS,
    UMBRAL_APROXIMADO_DIAS,
    _convertir,
    _holdings_por_cartera_ticker,
    _movimientos_ordenados,
    _precio_conocido,
    _precios_por_ticker,
    _to_usd,
)

FRECUENCIAS_VALIDAS = ("diaria", "semanal", "mensual")

# tolerancia < espaciado entre boundaries consecutivos, siempre. Si no se cumpliera, dos
# boundaries consecutivos podrían resolver al mismo precio carry-forward y el %-change sería
# un 0 fabricado, justo el sesgo hacia 0 que este módulo existe para evitar.
#  - diaria (espaciado 1 día hábil): 0 es el único valor que respeta la regla. Un feriado sin
#    precio cargado se pierde como observación en vez de inventar un 0.
#  - semanal (espaciado 7 días, boundary = viernes): 3 cubre un feriado el viernes o una carga
#    corrida al jueves/miércoles, y 3 < 7/2 así que nunca empata dos viernes consecutivos.
#  - mensual (espaciado ~30 días): 10 cubre fin de mes en domingo o feriados largos, y 10 < 28/2
#    (el mes más corto) así que nunca empata dos fines de mes consecutivos. Deliberadamente muy
#    por debajo de UMBRAL_APROXIMADO_DIAS=45, que es un umbral de VALUACIÓN (un precio viejo sólo
#    degrada el valor mostrado) y no de RETORNO (donde fabricaría una observación falsa).
TOLERANCIA_DIAS = {"diaria": 0, "semanal": 3, "mensual": 10}

# Ventana por defecto cuando no se pide `desde`, para no recorrer una serie diaria completa por
# accidente. `None` = sin recorte (usa todo el historial disponible).
VENTANA_DEFAULT_DIAS = {"diaria": 365, "semanal": 365 * 3, "mensual": None}

MAX_BOUNDARIES = 3000
MAX_TICKERS = 12

assert TOLERANCIA_DIAS["mensual"] < UMBRAL_APROXIMADO_DIAS  # documenta la relación explicada arriba


# ── Boundaries por frecuencia ─────────────────────────────────────────────────

def _boundaries_frecuencia(frecuencia: str, desde: date, hasta: date) -> list[date]:
    """Fechas de corte homogéneas para la frecuencia pedida.

    A diferencia de `inversiones_analytics._fin_de_mes_range`, NO agrega `hasta` como punto
    extra ni clampea el último período: un último tramo de pocos días comparado contra tramos
    completos distorsionaría tanto el retorno como la correlación.
    """
    if desde > hasta:
        return []

    if frecuencia == "diaria":
        dias = (hasta - desde).days
        return [desde + timedelta(days=i) for i in range(dias + 1) if (desde + timedelta(days=i)).weekday() < 5]

    if frecuencia == "semanal":
        # Primer viernes >= desde, luego cada 7 días. Viernes fijo (no "último día disponible")
        # para que el boundary sea determinístico y no dependa de qué ticker se esté mirando.
        dias_hasta_viernes = (4 - desde.weekday()) % 7
        cursor = desde + timedelta(days=dias_hasta_viernes)
        boundaries = []
        while cursor <= hasta:
            boundaries.append(cursor)
            cursor += timedelta(days=7)
        return boundaries

    # mensual: último día de cada mes completo dentro de [desde, hasta]. Excluye el mes en curso.
    boundaries = []
    cursor = date(desde.year, desde.month, 1)
    while True:
        if cursor.month == 12:
            fin_mes = date(cursor.year, 12, 31)
            siguiente = date(cursor.year + 1, 1, 1)
        else:
            siguiente = date(cursor.year, cursor.month + 1, 1)
            fin_mes = siguiente - timedelta(days=1)
        if siguiente > hasta:
            break  # el mes de `cursor` no terminó dentro del rango (incluye "mes en curso")
        if fin_mes >= desde:
            boundaries.append(fin_mes)
        cursor = siguiente
    return boundaries


def _recortar_boundaries(boundaries: list[date], tope: int = MAX_BOUNDARIES) -> tuple[list[date], bool]:
    """Conserva los últimos `tope` boundaries (los más recientes). Devuelve (lista, recortado)."""
    if len(boundaries) <= tope:
        return boundaries, False
    return boundaries[-tope:], True


# ── Retornos por boundaries ────────────────────────────────────────────────────

def _retornos_por_boundaries(
    precios_sorted: list[tuple[date, float, str]],
    boundaries: list[date],
    tolerancia_dias: int,
    moneda_destino: str,
    db: Session,
    mep_cache: dict,
) -> tuple[dict[date, float], dict]:
    """Serie de retornos entre boundaries CONSECUTIVOS y ambos aceptados (nunca se encadena
    sobre un hueco), más un resumen de cobertura. Clave de la serie = fecha del boundary final
    del intervalo.

    Un boundary se acepta sólo si `_precio_conocido` (carry-forward) devuelve un precio cuya
    fecha esté a <= `tolerancia_dias` del boundary, y la conversión a `moneda_destino` da un
    valor positivo. Todos los tickers de una misma matriz comparten la lista de `boundaries`,
    así que una clave común en dos series significa literalmente el mismo intervalo calendario.
    """
    aceptados: dict[int, float] = {}
    for idx, b in enumerate(boundaries):
        info = _precio_conocido(precios_sorted, b) if precios_sorted else None
        if info is None:
            continue
        fecha_precio, precio, moneda = info
        if (b - fecha_precio).days > tolerancia_dias:
            continue
        convertido = _convertir(precio, moneda, moneda_destino, b, db, mep_cache)
        if convertido is None or convertido <= EPS:
            continue
        aceptados[idx] = convertido

    serie: dict[date, float] = {}
    for idx in range(1, len(boundaries)):
        if idx in aceptados and (idx - 1) in aceptados:
            v0, v1 = aceptados[idx - 1], aceptados[idx]
            serie[boundaries[idx]] = v1 / v0 - 1

    cobertura = {
        "n_aceptados": len(aceptados),
        "n_retornos": len(serie),
        "primer_periodo": min(serie) if serie else None,
        "ultimo_periodo": max(serie) if serie else None,
        "cobertura_pct": round(len(serie) / max(1, len(boundaries) - 1) * 100, 1) if len(boundaries) > 1 else 0.0,
    }
    return serie, cobertura


# ── Selección de tickers ───────────────────────────────────────────────────────

def _tickers_por_defecto(cartera: str | None, db: Session, tope: int = MAX_TICKERS) -> list[str]:
    """Tenencias vivas de hoy, ordenadas por valor USD actual descendente. No usa
    `_clasificados_valorizados` porque ése exige ficha en `InstrumentoInversion`; acá alcanza
    con tener precio conocido."""
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return []

    hoy = date.today()
    holdings = _holdings_por_cartera_ticker(movs, hoy)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}

    valor_por_ticker: dict[str, float] = {}
    for (_cart, ticker), cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, hoy) if precios_sorted else None
        if info is None:
            continue
        _fecha, precio, moneda = info
        usd = _to_usd(precio * cantidad, moneda, hoy, db, mep_cache)
        if usd is not None:
            valor_por_ticker[ticker] = valor_por_ticker.get(ticker, 0.0) + abs(usd)

    ordenados = sorted(valor_por_ticker.items(), key=lambda kv: -kv[1])
    return [t for t, _v in ordenados[:tope]]


def _resolver_tickers(
    pedidos: list[str], cartera: str | None, db: Session
) -> tuple[list[str], list[dict]]:
    """Dedup preservando orden, uppercase, descarta los sin precios cargados, aplica el tope.
    Devuelve (tickers_usables, descartados=[{ticker, motivo}])."""
    precios_por_ticker = _precios_por_ticker(db)
    descartados: list[dict] = []

    if pedidos:
        vistos: set[str] = set()
        candidatos: list[str] = []
        for t in pedidos:
            t_norm = t.strip().upper()
            if not t_norm or t_norm in vistos:
                continue
            vistos.add(t_norm)
            candidatos.append(t_norm)
    else:
        candidatos = _tickers_por_defecto(cartera, db)

    usables: list[str] = []
    for t in candidatos:
        if not precios_por_ticker.get(t):
            descartados.append({"ticker": t, "motivo": "sin_precios"})
            continue
        usables.append(t)

    if len(usables) > MAX_TICKERS:
        for t in usables[MAX_TICKERS:]:
            descartados.append({"ticker": t, "motivo": "tope_tickers"})
        usables = usables[:MAX_TICKERS]

    return usables, descartados


# ── Período efectivo ───────────────────────────────────────────────────────────

def _periodo_efectivo(
    desde: date | None, hasta: date | None, frecuencia: str, precios_por_ticker: dict, tickers: list[str]
) -> tuple[date, date]:
    hoy = date.today()
    hasta_efectivo = min(hasta, hoy) if hasta else hoy

    if desde is not None:
        return desde, hasta_efectivo

    ventana = VENTANA_DEFAULT_DIAS[frecuencia]
    if ventana is not None:
        return hasta_efectivo - timedelta(days=ventana), hasta_efectivo

    fechas_iniciales = [precios_por_ticker[t][0][0] for t in tickers if precios_por_ticker.get(t)]
    if not fechas_iniciales:
        return hasta_efectivo, hasta_efectivo
    return min(fechas_iniciales), hasta_efectivo


# ── Orquestación ────────────────────────────────────────────────────────────────

def _vacio(estado: str, frecuencia: str, min_obs: int, desde: date | None, hasta: date | None) -> dict:
    return {
        "estado": estado,
        "moneda": "USD",
        "frecuencia_pedida": frecuencia,
        "frecuencia_efectiva": frecuencia,
        "min_obs": min_obs,
        "periodo_pedido_desde": desde,
        "periodo_pedido_hasta": hasta,
        "periodo_desde": None,
        "periodo_hasta": None,
        "n_periodos": 0,
        "n_periodos_posibles": 0,
        "tickers": [],
        "n_tickers": 0,
        "tickers_detalle": [],
        "tickers_descartados": [],
        "matriz": [],
        "pares": [],
        "n_pares": 0,
        "n_pares_ok": 0,
        "correlacion_promedio": None,
        "nivel_diversificacion": None,
        "ranking": {"mas_correlacionados": [], "menos_correlacionados": [], "mas_negativos": []},
        "pocos_datos": False,
        "advertencias": [],
    }


@cache_por_sync
def get_matriz_correlaciones(
    cartera: str | None,
    db: Session,
    tickers: list[str] | None = None,
    frecuencia: str = "mensual",
    desde: date | None = None,
    hasta: date | None = None,
    min_obs: int | None = None,
) -> dict:
    tickers_pedidos = tickers or []
    min_obs_efectivo = min_obs if min_obs is not None else correlaciones_engine.MIN_OBS_POR_FRECUENCIA[frecuencia]

    tickers_usables, descartados = _resolver_tickers(tickers_pedidos, cartera, db)
    if not tickers_usables:
        resultado = _vacio("sin_tickers", frecuencia, min_obs_efectivo, desde, hasta)
        resultado["tickers_descartados"] = descartados
        return resultado
    if len(tickers_usables) < 2:
        resultado = _vacio("sin_suficientes_tickers", frecuencia, min_obs_efectivo, desde, hasta)
        resultado["tickers"] = tickers_usables
        resultado["n_tickers"] = len(tickers_usables)
        resultado["tickers_descartados"] = descartados
        return resultado

    precios_por_ticker = _precios_por_ticker(db)
    desde_efectivo, hasta_efectivo = _periodo_efectivo(desde, hasta, frecuencia, precios_por_ticker, tickers_usables)

    boundaries = _boundaries_frecuencia(frecuencia, desde_efectivo, hasta_efectivo)
    boundaries, recortado = _recortar_boundaries(boundaries)

    if len(boundaries) < 2:
        resultado = _vacio("datos_insuficientes", frecuencia, min_obs_efectivo, desde, hasta)
        resultado["tickers"] = tickers_usables
        resultado["n_tickers"] = len(tickers_usables)
        resultado["tickers_descartados"] = descartados
        return resultado

    mep_cache: dict = {}
    tolerancia = TOLERANCIA_DIAS[frecuencia]
    series_por_ticker: dict[str, dict] = {}
    tickers_detalle: list[dict] = []

    for t in tickers_usables:
        serie, cobertura = _retornos_por_boundaries(
            precios_por_ticker.get(t, []), boundaries, tolerancia, "USD", db, mep_cache
        )
        series_por_ticker[t] = serie
        tickers_detalle.append({
            "ticker": t,
            "n_retornos": cobertura["n_retornos"],
            "cobertura_pct": cobertura["cobertura_pct"],
            "primer_periodo": cobertura["primer_periodo"],
            "ultimo_periodo": cobertura["ultimo_periodo"],
        })

    n_periodos_posibles = len(boundaries) - 1
    matriz_resultado = correlaciones_engine.construir_matriz(
        tickers_usables, series_por_ticker, min_obs_efectivo, n_periodos_posibles
    )
    ranking = correlaciones_engine.rankear_pares(matriz_resultado["pares"])
    advertencias = correlaciones_engine.construir_advertencias(
        frecuencia=frecuencia,
        min_obs=min_obs_efectivo,
        n_pares=matriz_resultado["n_pares"],
        n_pares_insuficientes=matriz_resultado["n_pares_insuficientes"],
        tickers_descartados=descartados,
        n_periodos=len(boundaries),
        recortado=recortado,
    )

    periodos_con_datos = [d["ultimo_periodo"] for d in tickers_detalle if d["ultimo_periodo"] is not None]
    periodos_desde = [d["primer_periodo"] for d in tickers_detalle if d["primer_periodo"] is not None]

    return {
        "estado": "ok",
        "moneda": "USD",
        "frecuencia_pedida": frecuencia,
        "frecuencia_efectiva": frecuencia,
        "min_obs": min_obs_efectivo,
        "periodo_pedido_desde": desde,
        "periodo_pedido_hasta": hasta,
        "periodo_desde": min(periodos_desde) if periodos_desde else None,
        "periodo_hasta": max(periodos_con_datos) if periodos_con_datos else None,
        "n_periodos": len(boundaries),
        "n_periodos_posibles": n_periodos_posibles,
        "tickers": tickers_usables,
        "n_tickers": len(tickers_usables),
        "tickers_detalle": tickers_detalle,
        "tickers_descartados": descartados,
        "matriz": matriz_resultado["matriz"],
        "pares": matriz_resultado["pares"],
        "n_pares": matriz_resultado["n_pares"],
        "n_pares_ok": matriz_resultado["n_pares_ok"],
        "correlacion_promedio": matriz_resultado["correlacion_promedio"],
        "nivel_diversificacion": correlaciones_engine.nivel_diversificacion(matriz_resultado["correlacion_promedio"]),
        "ranking": ranking,
        "pocos_datos": matriz_resultado["pocos_datos"],
        "advertencias": advertencias,
    }
