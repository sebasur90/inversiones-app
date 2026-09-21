"""Adaptador entre los datos reales (Session/DB) y el motor puro de explicación del resultado
(`explicacion_resultado_engine`) — la pantalla "¿Por qué ganó o perdió mi cartera?".

Reutiliza las funciones privadas de `inversiones_analytics` (holdings, valuación, conversión de
moneda, TWR/XIRR) en vez de reimplementar la valuación de cartera — mismo patrón que
`contribucion_analytics.py`, `riesgo_analytics.py` y `fx_decomposition_analytics.py`.

**No mezcla aportes con rendimiento**: los aportes/retiros/amortizaciones del período se calculan
aparte (son movimientos de capital, no P&L) y el P&L se calcula por la identidad de
`explicacion_resultado_engine.descomponer_ticker` (ver ese módulo para la fórmula completa).
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import InstrumentoInversion
from . import explicacion_resultado_engine, fx_decomposition_engine
from .inversiones_analytics import (
    EPS,
    UMBRAL_APROXIMADO_DIAS,
    _movimientos_ordenados,
    _precios_por_ticker,
    _precio_conocido,
    _convertir,
    _mep_sheet,
    _monto_bruto,
    _monto_usd,
    _monto_ars,
    _comision_usd,
    _comision_ars,
    _flujos_cashflow,
    _calcular_xirr,
    _xirr_a_periodo,
    _dias_periodo_medido,
    _calcular_twr,
    _calcular_twr_ars,
    _HoldingsTracker,
)
from .cache import cache_por_sync

MONEDAS_VALIDAS = ("usd", "ars")

# Cuántos contribuyentes/detractores mostrar como máximo.
TOP_N = 8


def _valor_ticker_en(
    ticker: str,
    cantidad: float,
    fecha: date,
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    moneda_destino: str,
    costo: tuple[float, str] | None,
) -> tuple[float | None, bool]:
    """Valor de mercado de la tenencia de un ticker a una fecha, en `moneda_destino`.

    Mismo criterio de fallback que `inversiones_analytics._valuar_holdings`: sin cotización
    conocida usa el costo promedio de compra (marcando `aproximado=True`) en vez de descartar
    la posición. Devuelve `(None, False)` si no hay ni precio ni costo, o si falta el tipo de
    cambio para convertir a `moneda_destino`.
    """
    if abs(cantidad) < EPS:
        return 0.0, False
    precios_sorted = precios_por_ticker.get(ticker)
    info = _precio_conocido(precios_sorted, fecha) if precios_sorted else None
    if info is None:
        if costo is None:
            return None, False
        precio, moneda_nativa = costo
        aproximado = True
    else:
        fecha_precio, precio, moneda_nativa = info
        aproximado = (fecha - fecha_precio).days > UMBRAL_APROXIMADO_DIAS
    valor = _convertir(precio * cantidad, moneda_nativa, moneda_destino, fecha, db, mep_cache)
    return valor, aproximado


def _total(items: list[dict], campo: str) -> float | None:
    """Suma un campo sobre los ítems que sí lo tienen calculado; `None` si ninguno lo tiene."""
    valores = [it[campo] for it in items if it.get(campo) is not None]
    if not valores:
        return None
    return round(sum(valores), 2)


def _descomponer_por_ticker(
    movs: list,
    desde: date | None,
    hoy: date,
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    moneda_destino: str,
) -> tuple[list[dict], bool]:
    """Descompone el P&L del período en cada ticker con tenencia o movimientos, en
    `moneda_destino` ("USD" | "ARS"). Devuelve `(items, hubo_precio_aproximado)`.
    """
    mep_cache: dict = {}

    tracker0 = _HoldingsTracker(movs)
    if desde is not None:
        tracker0.avanzar_a(desde)
    holdings0 = tracker0.snapshot() if desde is not None else {}
    costos0 = tracker0.costo_snapshot() if desde is not None else {}

    tracker1 = _HoldingsTracker(movs)
    tracker1.avanzar_a(hoy)
    holdings1 = tracker1.snapshot()
    costos1 = tracker1.costo_snapshot()

    movs_periodo_por_ticker: dict[str, list] = {}
    for mov in movs:
        if desde is not None and mov.fecha <= desde:
            continue
        movs_periodo_por_ticker.setdefault(mov.ticker, []).append(mov)

    tickers = set(holdings0) | set(holdings1) | set(movs_periodo_por_ticker)
    monto_fn = _monto_usd if moneda_destino == "USD" else _monto_ars
    comision_fn = _comision_usd if moneda_destino == "USD" else _comision_ars

    items: list[dict] = []
    aproximado_alguno = False

    for ticker in sorted(tickers):
        v0, aprox0 = (
            _valor_ticker_en(ticker, holdings0.get(ticker, 0.0), desde, precios_por_ticker, db, mep_cache, moneda_destino, costos0.get(ticker))
            if desde is not None else (0.0, False)
        )
        v1, aprox1 = _valor_ticker_en(
            ticker, holdings1.get(ticker, 0.0), hoy, precios_por_ticker, db, mep_cache, moneda_destino, costos1.get(ticker)
        )
        aproximado_alguno = aproximado_alguno or aprox0 or aprox1

        compras_bruto = compras_neto = 0.0
        ventas_bruto = ventas_neto = 0.0
        amort_bruto = amort_neto = 0.0
        dividendos = cupones = comisiones = 0.0
        fallo_flujos = False

        for mov in movs_periodo_por_ticker.get(ticker, []):
            bruto_conv = _convertir(_monto_bruto(mov), mov.moneda, moneda_destino, mov.fecha, db, mep_cache)
            neto_conv = monto_fn(mov, db, mep_cache)
            com_conv = comision_fn(mov, db, mep_cache)
            if bruto_conv is None or neto_conv is None or com_conv is None:
                fallo_flujos = True
                continue
            comisiones += com_conv
            if mov.tipo_movimiento == "compra":
                compras_bruto += bruto_conv
                compras_neto += neto_conv
            elif mov.tipo_movimiento == "venta":
                ventas_bruto += bruto_conv
                ventas_neto += neto_conv
            elif mov.tipo_movimiento == "amortizacion":
                amort_bruto += bruto_conv
                amort_neto += neto_conv
            elif mov.tipo_movimiento == "dividendo":
                dividendos += bruto_conv
            elif mov.tipo_movimiento == "cupon":
                cupones += bruto_conv

        if fallo_flujos:
            compras_bruto = compras_neto = ventas_bruto = ventas_neto = None
            amort_bruto = amort_neto = dividendos = cupones = comisiones = None

        items.append(explicacion_resultado_engine.descomponer_ticker(
            ticker, v0, v1,
            compras_bruto, compras_neto,
            ventas_bruto, ventas_neto,
            amort_bruto, amort_neto,
            dividendos, cupones, comisiones,
        ))

    return items, aproximado_alguno


def _resultado_vacio(desde: date | None, hoy: date) -> dict:
    return {
        "estado": "sin_datos",
        "periodo": {"desde": desde, "hasta": hoy},
        "resultado": {
            "v0": None, "v1": None, "pnl": None,
            "twr_pct": None, "xirr_pct": None, "rendimiento_simple_pct": None,
            "aportes": None, "retiros": None, "amortizaciones": None, "ingresos": None,
        },
        "componentes": {"precio": None, "dividendos": None, "cupones": None, "comisiones": None},
        "por_tipo": [], "por_mercado": [], "por_ticker": [],
        "contribuyentes": [], "detractores": [], "no_disponibles": [],
        "fx": {"estado": "no_aplica", "resultado_activos_ars": None, "efecto_mep_ars": None,
               "efecto_fx_pct": None, "identidad_verificada": True},
        "explicacion": {"titulo": "Todavía no hay movimientos cargados para esta cartera.", "frases": []},
        "advertencias": [],
    }


@cache_por_sync
def get_explicacion_resultado(cartera: str | None, desde: date | None, moneda: str, db: Session) -> dict:
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}. Válidas: {MONEDAS_VALIDAS}")
    moneda_destino = moneda.upper()

    hoy = date.today()
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return _resultado_vacio(desde, hoy)

    precios_por_ticker = _precios_por_ticker(db)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}

    items, aproximado = _descomponer_por_ticker(movs, desde, hoy, precios_por_ticker, db, moneda_destino)
    for it in items:
        inst = instrumentos.get(it["ticker"])
        it["nombre"] = inst.nombre if inst else it["ticker"]

    v0_total = _total(items, "v0")
    v1_total = _total(items, "v1")
    pnl_total = _total(items, "pnl")
    precio_total = _total(items, "precio")
    dividendos_total = _total(items, "dividendos")
    cupones_total = _total(items, "cupones")
    comisiones_total = _total(items, "comisiones")
    aportes_total = _total(items, "aportes")
    retiros_total = _total(items, "retiros")
    amortizaciones_total = _total(items, "amortizaciones")
    ingresos_total = (
        round(dividendos_total + cupones_total, 2)
        if dividendos_total is not None and cupones_total is not None else None
    )

    base_periodo = (v0_total or 0.0) + (aportes_total or 0.0)
    rendimiento_simple_pct = (
        round(pnl_total / base_periodo * 100, 2)
        if pnl_total is not None and abs(base_periodo) > EPS else None
    )

    # TWR/XIRR: reusan el núcleo compartido con Rendimiento/Resumen (`_calcular_twr*`), sólo
    # con la ventana `(desde, hoy]` (ver extensión de `_calcular_twr_encadenado`).
    mep_cache_periodo: dict = {}
    if moneda_destino == "USD":
        twr_periodo, _, _ = _calcular_twr(movs, precios_por_ticker, db, mep_cache_periodo, hoy, desde=desde)
    else:
        twr_periodo, _, _ = _calcular_twr_ars(movs, precios_por_ticker, db, mep_cache_periodo, hoy, desde=desde)

    monto_fn = _monto_usd if moneda_destino == "USD" else _monto_ars
    movs_periodo = [m for m in movs if desde is None or m.fecha > desde]
    flujos = _flujos_cashflow(movs_periodo, lambda mov: monto_fn(mov, db, mep_cache_periodo))
    if desde is not None:
        flujos = [(desde, -(v0_total or 0.0))] + flujos
    flujos = flujos + [(hoy, v1_total or 0.0)]
    dias_periodo = (hoy - desde).days if desde is not None else _dias_periodo_medido(movs, hoy)
    xirr = _calcular_xirr(flujos) if dias_periodo > 0 else None
    xirr_periodo = _xirr_a_periodo(xirr, dias_periodo) if dias_periodo > 0 else None

    items_contrib = explicacion_resultado_engine.con_contribucion(items, base_periodo)
    por_ticker = sorted(items_contrib, key=lambda it: -abs(it["contribucion_pct"] or 0))
    contribuyentes = explicacion_resultado_engine.ranking(items_contrib, n=TOP_N, positivos=True)
    detractores = explicacion_resultado_engine.ranking(items_contrib, n=TOP_N, positivos=False)

    entries_tipo = [
        (instrumentos[it["ticker"]].tipo_instrumento if it["ticker"] in instrumentos else "—", it)
        for it in items
    ]
    por_tipo = explicacion_resultado_engine.con_contribucion(
        explicacion_resultado_engine.agrupar_por_etiqueta(entries_tipo), base_periodo
    )
    por_tipo.sort(key=lambda x: -abs(x["contribucion_pct"] or 0))

    entries_mercado = [
        (instrumentos[it["ticker"]].mercado if it["ticker"] in instrumentos else "—", it)
        for it in items
    ]
    por_mercado = explicacion_resultado_engine.con_contribucion(
        explicacion_resultado_engine.agrupar_por_etiqueta(entries_mercado), base_periodo
    )
    por_mercado.sort(key=lambda x: -abs(x["contribucion_pct"] or 0))

    no_disponibles = [
        {"ticker": it["ticker"], "nombre": it["nombre"], "motivo": "sin precio o tipo de cambio para este período"}
        for it in items if not it["disponible"]
    ]

    # Bloque FX (sólo vista ARS): identidad exacta en dinero + el % vía el motor ya existente
    # de descomposición FX (no se duplica la fórmula).
    if moneda_destino == "ARS":
        items_usd, _ = _descomponer_por_ticker(movs, desde, hoy, precios_por_ticker, db, "USD")
        pnl_total_usd = _total(items_usd, "pnl")
        mep_hoy = _mep_sheet(hoy, db, mep_cache_periodo)
        fx_dinero = explicacion_resultado_engine.descomponer_fx_periodo(pnl_total, pnl_total_usd, mep_hoy)

        twr_usd_periodo, _, _ = _calcular_twr(movs, precios_por_ticker, db, mep_cache_periodo, hoy, desde=desde)
        fecha_mep_inicio = desde if desde is not None else movs[0].fecha
        mep_inicio = _mep_sheet(fecha_mep_inicio, db, mep_cache_periodo)
        fx_pct = fx_decomposition_engine.descomponer_retorno_periodo(twr_periodo, twr_usd_periodo, mep_inicio, mep_hoy)
        fx = {
            "estado": fx_dinero["estado"],
            "resultado_activos_ars": fx_dinero["resultado_activos_ars"],
            "efecto_mep_ars": fx_dinero["efecto_mep_ars"],
            "efecto_fx_pct": fx_pct["efecto_fx_pct"],
            "identidad_verificada": fx_pct["identidad_verificada"],
        }
    else:
        fx = {"estado": "no_aplica", "resultado_activos_ars": None, "efecto_mep_ars": None,
              "efecto_fx_pct": None, "identidad_verificada": True}

    explicacion = explicacion_resultado_engine.explicar(
        pnl_total, precio_total, dividendos_total, cupones_total, comisiones_total, moneda
    )

    advertencias = []
    if aproximado:
        advertencias.append("Algunos precios usados tienen más de 45 días de antigüedad (carry-forward).")
    if no_disponibles:
        advertencias.append(
            f"{len(no_disponibles)} instrumento(s) no se pudieron calcular con precisión (ver 'No disponible')."
        )

    estado = "sin_datos" if not items else ("parcial" if no_disponibles else "ok")

    return {
        "estado": estado,
        "periodo": {"desde": desde, "hasta": hoy},
        "resultado": {
            "v0": v0_total, "v1": v1_total, "pnl": pnl_total,
            "twr_pct": round(twr_periodo * 100, 2) if twr_periodo is not None else None,
            "xirr_pct": round(xirr_periodo * 100, 2) if xirr_periodo is not None else None,
            "rendimiento_simple_pct": rendimiento_simple_pct,
            "aportes": aportes_total, "retiros": retiros_total,
            "amortizaciones": amortizaciones_total, "ingresos": ingresos_total,
        },
        "componentes": {
            "precio": precio_total, "dividendos": dividendos_total,
            "cupones": cupones_total, "comisiones": comisiones_total,
        },
        "por_tipo": por_tipo,
        "por_mercado": por_mercado,
        "por_ticker": por_ticker,
        "contribuyentes": contribuyentes,
        "detractores": detractores,
        "no_disponibles": no_disponibles,
        "fx": fx,
        "explicacion": explicacion,
        "advertencias": advertencias,
    }
