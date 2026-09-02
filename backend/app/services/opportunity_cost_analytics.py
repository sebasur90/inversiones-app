"""Adaptador para calcular costo de oportunidad de una cartera vs benchmark.

Resuelve el benchmark (explícito > config > sin_benchmark), arma flujos de caja,
valúa la cartera, calcula valor_shadow en la moneda nativa del benchmark, y devuelve
costo de oportunidad (benchmark - cartera) en ambas monedas.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import IndiceMercado, PrecioInstrumento
from . import opportunity_cost_engine
from .benchmarks_analytics import BENCHMARK_DOLAR, BENCHMARK_INFLACION
from .inversiones_analytics import (
    _movimientos_ordenados,
    _precios_por_ticker,
    _flujos_cashflow,
    _valuar_holdings,
    _valuar_holdings_ars,
    _monto_usd,
    _mep_sheet,
    _HoldingsTracker,
    get_configuracion_cartera,
)


def _mep_indice_serie(db: Session) -> list[tuple[date, float]]:
    rows = (
        db.query(IndiceMercado)
        .filter(IndiceMercado.mep.isnot(None))
        .order_by(IndiceMercado.fecha)
        .all()
    )
    return [(r.fecha, float(r.mep)) for r in rows]


def _cer_indice_serie(db: Session) -> list[tuple[date, float]]:
    rows = (
        db.query(IndiceMercado)
        .filter(IndiceMercado.cer.isnot(None))
        .order_by(IndiceMercado.fecha)
        .all()
    )
    return [(r.fecha, float(r.cer)) for r in rows]


def _ticker_indice_serie(ticker: str, db: Session) -> list[tuple[date, float]]:
    rows = (
        db.query(PrecioInstrumento)
        .filter(PrecioInstrumento.ticker == ticker)
        .order_by(PrecioInstrumento.fecha)
        .all()
    )
    return [(r.fecha, float(r.precio)) for r in rows]


def get_opportunity_cost(cartera: str | None, benchmark: str | None, desde: date | None, db: Session) -> dict:
    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    hoy = date.today()

    benchmark_resuelto = benchmark
    if benchmark_resuelto is None:
        config = get_configuracion_cartera(cartera, db)
        benchmark_resuelto = config.get("benchmark") if config else None

    if benchmark_resuelto is None:
        return {
            "estado": "sin_benchmark",
            "benchmark_usado": None,
            "moneda_nativa_benchmark": None,
            "valor_actual_usd": None,
            "valor_actual_ars": None,
            "valor_shadow_usd": None,
            "valor_shadow_ars": None,
            "costo_oportunidad_usd": None,
            "costo_oportunidad_ars": None,
            "por_posicion": [],
        }

    tracker = _HoldingsTracker(movs)
    tracker.avanzar_a(hoy)
    holdings = tracker.snapshot()
    costos = tracker.costo_snapshot()

    valor_actual_usd, _, _ = _valuar_holdings(holdings, hoy, precios_por_ticker, db, mep_cache, costos)
    valor_actual_ars, _, _ = _valuar_holdings_ars(holdings, hoy, precios_por_ticker, db, mep_cache, costos)

    flujos = _flujos_cashflow(movs, lambda m: _monto_usd(m, db, mep_cache))
    if desde:
        flujos = [(f, m) for f, m in flujos if f >= desde]

    moneda_nativa = "ars"
    serie_niveles = None

    if benchmark_resuelto == BENCHMARK_DOLAR:
        moneda_nativa = "ars"
        serie_niveles = _mep_indice_serie(db)
    elif benchmark_resuelto == BENCHMARK_INFLACION:
        moneda_nativa = "ars"
        serie_niveles = _cer_indice_serie(db)
    else:
        serie_niveles = _ticker_indice_serie(benchmark_resuelto, db)

    if not serie_niveles:
        return {
            "estado": "datos_insuficientes",
            "benchmark_usado": benchmark_resuelto,
            "moneda_nativa_benchmark": moneda_nativa,
            "valor_actual_usd": round(valor_actual_usd, 2),
            "valor_actual_ars": round(valor_actual_ars, 2),
            "valor_shadow_usd": None,
            "valor_shadow_ars": None,
            "costo_oportunidad_usd": None,
            "costo_oportunidad_ars": None,
            "por_posicion": [],
        }

    valor_shadow_nativo = opportunity_cost_engine.valor_shadow(flujos, serie_niveles, hoy)

    if valor_shadow_nativo is None:
        return {
            "estado": "datos_insuficientes",
            "benchmark_usado": benchmark_resuelto,
            "moneda_nativa_benchmark": moneda_nativa,
            "valor_actual_usd": round(valor_actual_usd, 2),
            "valor_actual_ars": round(valor_actual_ars, 2),
            "valor_shadow_usd": None,
            "valor_shadow_ars": None,
            "costo_oportunidad_usd": None,
            "costo_oportunidad_ars": None,
            "por_posicion": [],
        }

    mep_hoy = _mep_sheet(hoy, db, mep_cache)

    if moneda_nativa == "ars":
        valor_shadow_ars = valor_shadow_nativo
        valor_shadow_usd = valor_shadow_ars / mep_hoy if mep_hoy else None
        costo_oportunidad_ars = valor_shadow_ars - valor_actual_ars
        costo_oportunidad_usd = valor_shadow_usd - valor_actual_usd if valor_shadow_usd is not None else None
    else:
        valor_shadow_usd = valor_shadow_nativo
        valor_shadow_ars = valor_shadow_usd * mep_hoy if mep_hoy else None
        costo_oportunidad_usd = valor_shadow_usd - valor_actual_usd
        costo_oportunidad_ars = valor_shadow_ars - valor_actual_ars if valor_shadow_ars is not None else None

    por_posicion = get_opportunity_cost_por_posicion(cartera, benchmark, db)

    return {
        "estado": "ok",
        "benchmark_usado": benchmark_resuelto,
        "moneda_nativa_benchmark": moneda_nativa,
        "valor_actual_usd": round(valor_actual_usd, 2),
        "valor_actual_ars": round(valor_actual_ars, 2),
        "valor_shadow_usd": round(valor_shadow_usd, 2) if valor_shadow_usd is not None else None,
        "valor_shadow_ars": round(valor_shadow_ars, 2) if valor_shadow_ars is not None else None,
        "costo_oportunidad_usd": round(costo_oportunidad_usd, 2) if costo_oportunidad_usd is not None else None,
        "costo_oportunidad_ars": round(costo_oportunidad_ars, 2) if costo_oportunidad_ars is not None else None,
        "por_posicion": por_posicion,
    }


def get_opportunity_cost_por_posicion(cartera: str | None, benchmark: str | None, db: Session) -> list[dict]:
    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    hoy = date.today()

    benchmark_resuelto = benchmark
    if benchmark_resuelto is None:
        config = get_configuracion_cartera(cartera, db)
        benchmark_resuelto = config.get("benchmark") if config else None

    if benchmark_resuelto is None or not movs:
        return []

    serie_niveles = None
    moneda_nativa = "ars"

    if benchmark_resuelto == BENCHMARK_DOLAR:
        moneda_nativa = "ars"
        serie_niveles = _mep_indice_serie(db)
    elif benchmark_resuelto == BENCHMARK_INFLACION:
        moneda_nativa = "ars"
        serie_niveles = _cer_indice_serie(db)
    else:
        serie_niveles = _ticker_indice_serie(benchmark_resuelto, db)

    if not serie_niveles:
        return []

    mep_hoy = _mep_sheet(hoy, db, mep_cache)
    por_posicion = []

    movs_por_ticker: dict[str, list] = {}
    for m in movs:
        movs_por_ticker.setdefault(m.ticker, []).append(m)

    for ticker, movs_ticker in sorted(movs_por_ticker.items()):
        flujos_ticker = _flujos_cashflow(movs_ticker, lambda m: _monto_usd(m, db, mep_cache))

        tracker = _HoldingsTracker(movs_ticker)
        tracker.avanzar_a(hoy)
        holdings_ticker = tracker.snapshot()
        costos_ticker = tracker.costo_snapshot()

        valor_actual_ticker_usd, _, _ = _valuar_holdings(holdings_ticker, hoy, precios_por_ticker, db, mep_cache, costos_ticker)

        valor_shadow_ticker = opportunity_cost_engine.valor_shadow(flujos_ticker, serie_niveles, hoy)

        if valor_shadow_ticker is not None:
            if moneda_nativa == "ars":
                valor_shadow_ticker_usd = valor_shadow_ticker / mep_hoy if mep_hoy else 0
                costo_oportunidad_usd = valor_shadow_ticker_usd - valor_actual_ticker_usd
                costo_oportunidad_ars = costo_oportunidad_usd * mep_hoy if mep_hoy else 0
            else:
                valor_shadow_ticker_usd = valor_shadow_ticker
                costo_oportunidad_usd = valor_shadow_ticker_usd - valor_actual_ticker_usd
                costo_oportunidad_ars = costo_oportunidad_usd * mep_hoy if mep_hoy else 0

            por_posicion.append({
                "ticker": ticker,
                "nombre": ticker,
                "valor_actual_usd": round(valor_actual_ticker_usd, 2),
                "valor_shadow_usd": round(valor_shadow_ticker_usd, 2),
                "costo_oportunidad_usd": round(costo_oportunidad_usd, 2),
                "costo_oportunidad_ars": round(costo_oportunidad_ars, 2),
            })

    por_posicion.sort(key=lambda x: abs(x["costo_oportunidad_usd"]), reverse=True)
    return por_posicion
