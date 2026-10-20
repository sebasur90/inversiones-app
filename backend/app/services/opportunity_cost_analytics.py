"""Adaptador para calcular costo de oportunidad de una cartera vs benchmark.

Resuelve el benchmark (explícito > config > sin_benchmark), arma flujos de caja,
valúa la cartera, calcula el valor "sombra" y devuelve el costo de oportunidad
(benchmark - cartera) en dólares y en pesos.

Cada moneda se calcula por separado con flujos, valuación y serie de la referencia en ESA
moneda (`costo_oportunidad_engine.normalizar_serie`). Antes los flujos salían en USD pero se
hacían crecer por una serie en pesos (el MEP, el CER) y el resultado se dividía otra vez por el
MEP: el "valor sombra" no era ni dólares ni pesos.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import IndiceMercado
from . import opportunity_cost_engine, costo_oportunidad_engine
from .inversiones_analytics import (
    EPS,
    _movimientos_ordenados,
    _precios_por_ticker,
    _flujos_cashflow,
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


_MONEDAS = ("usd", "ars_nominal")


def _vacio(estado: str, benchmark: str | None = None, moneda_nativa: str | None = None,
           valor_actual_usd: float | None = None, valor_actual_ars: float | None = None) -> dict:
    return {
        "estado": estado,
        "benchmark_usado": benchmark,
        "moneda_nativa_benchmark": moneda_nativa,
        "valor_actual_usd": valor_actual_usd,
        "valor_actual_ars": valor_actual_ars,
        "valor_shadow_usd": None,
        "valor_shadow_ars": None,
        "costo_oportunidad_usd": None,
        "costo_oportunidad_ars": None,
        "por_posicion": [],
    }


def _valor_actual_y_shadow(movs, desde: date | None, hoy: date, monto_fn, valuar_fn, serie_norm):
    """(valor actual de la cartera, valor sombra de los mismos flujos), ambos en la moneda de la serie.

    Con `desde`, la cartera que ya tenías en esa fecha entra como un aporte inicial al valor de
    mercado de ese día y sólo cuentan los movimientos posteriores: así la cartera y la referencia
    arrancan del mismo capital. Descartar los flujos anteriores sin más dejaba la tenencia
    previa en el valor actual y la sacaba del lado de la referencia.
    """
    tracker = _HoldingsTracker(movs)
    flujos = _flujos_cashflow(movs, monto_fn)
    if desde is not None:
        tracker.avanzar_a(desde)
        v0, _, _ = valuar_fn(tracker.snapshot(), desde, tracker.costo_snapshot())
        if v0 is None:
            return None
        inicial = [(desde, -v0)] if abs(v0) > EPS else []
        flujos = inicial + [(f, m) for f, m in flujos if f > desde]

    tracker.avanzar_a(hoy)
    valor_actual, _, _ = valuar_fn(tracker.snapshot(), hoy, tracker.costo_snapshot())
    if valor_actual is None:
        return None
    shadow = opportunity_cost_engine.valor_shadow(flujos, serie_norm, hoy)
    if shadow is None:
        return None
    return valor_actual, shadow


def _resolver_benchmark(cartera: str | None, benchmark: str | None, db: Session) -> str | None:
    if benchmark is not None:
        return benchmark
    config = get_configuracion_cartera(cartera, db)
    return config.get("benchmark") if config else None


def _series_por_moneda(referencia: str, db: Session):
    """({moneda: serie de la referencia en esa moneda}, moneda nativa declarada) o (None, nativa)."""
    from . import costo_oportunidad_analytics as co    # import diferido: ese módulo importa éste

    serie_nativa, moneda_nativa = co._serie_nativa_referencia(referencia, db)
    if not serie_nativa:
        return None, moneda_nativa
    serie_mep = _mep_indice_serie(db)
    serie_cer = _cer_indice_serie(db)
    series = {}
    for moneda in _MONEDAS:
        serie_norm, _ = costo_oportunidad_engine.normalizar_serie(serie_nativa, moneda, serie_mep, serie_cer, None)
        if not serie_norm:
            return None, moneda_nativa
        series[moneda] = serie_norm
    return series, moneda_nativa


def get_opportunity_cost(cartera: str | None, benchmark: str | None, desde: date | None, db: Session) -> dict:
    from . import costo_oportunidad_analytics as co    # import diferido: ese módulo importa éste

    movs = _movimientos_ordenados(db, cartera)
    benchmark_resuelto = _resolver_benchmark(cartera, benchmark, db)
    if benchmark_resuelto is None:
        return _vacio("sin_benchmark")
    if not movs:
        return _vacio("datos_insuficientes", benchmark_resuelto)

    series, moneda_nativa = _series_por_moneda(benchmark_resuelto, db)
    if series is None:
        return _vacio("datos_insuficientes", benchmark_resuelto, moneda_nativa)

    precios_por_ticker = _precios_por_ticker(db)
    hoy = date.today()
    mep_cache: dict = {}
    cer_cache: dict = {}

    valores: dict[str, tuple[float, float]] = {}
    for moneda in _MONEDAS:
        monto_fn = co._monto_fn_para_moneda(moneda, db, mep_cache, cer_cache, None)
        valuar_fn = co._valuar_fn_para_moneda(moneda, precios_por_ticker, db, mep_cache, cer_cache, None)
        r = _valor_actual_y_shadow(movs, desde, hoy, monto_fn, valuar_fn, series[moneda])
        if r is None:
            # Algún flujo cae antes del primer dato de la referencia (o falta MEP): sin dato.
            return _vacio("datos_insuficientes", benchmark_resuelto, moneda_nativa)
        valores[moneda] = r

    actual_usd, shadow_usd = valores["usd"]
    actual_ars, shadow_ars = valores["ars_nominal"]

    return {
        "estado": "ok",
        "benchmark_usado": benchmark_resuelto,
        "moneda_nativa_benchmark": moneda_nativa,
        "valor_actual_usd": round(actual_usd, 2),
        "valor_actual_ars": round(actual_ars, 2),
        "valor_shadow_usd": round(shadow_usd, 2),
        "valor_shadow_ars": round(shadow_ars, 2),
        "costo_oportunidad_usd": round(shadow_usd - actual_usd, 2),
        "costo_oportunidad_ars": round(shadow_ars - actual_ars, 2),
        "por_posicion": get_opportunity_cost_por_posicion(cartera, benchmark, db, desde),
    }


def get_opportunity_cost_por_posicion(
    cartera: str | None, benchmark: str | None, db: Session, desde: date | None = None,
) -> list[dict]:
    from . import costo_oportunidad_analytics as co    # import diferido: ese módulo importa éste

    movs = _movimientos_ordenados(db, cartera)
    benchmark_resuelto = _resolver_benchmark(cartera, benchmark, db)
    if benchmark_resuelto is None or not movs:
        return []
    series, _ = _series_por_moneda(benchmark_resuelto, db)
    if series is None:
        return []

    precios_por_ticker = _precios_por_ticker(db)
    hoy = date.today()
    mep_cache: dict = {}
    cer_cache: dict = {}
    monto_fns = {m: co._monto_fn_para_moneda(m, db, mep_cache, cer_cache, None) for m in _MONEDAS}
    valuar_fns = {
        m: co._valuar_fn_para_moneda(m, precios_por_ticker, db, mep_cache, cer_cache, None) for m in _MONEDAS
    }

    movs_por_ticker: dict[str, list] = {}
    for m in movs:
        movs_por_ticker.setdefault(m.ticker, []).append(m)

    por_posicion = []
    for ticker, movs_ticker in sorted(movs_por_ticker.items()):
        valores = {}
        for moneda in _MONEDAS:
            r = _valor_actual_y_shadow(movs_ticker, desde, hoy, monto_fns[moneda], valuar_fns[moneda], series[moneda])
            if r is None:
                break
            valores[moneda] = r
        if len(valores) < len(_MONEDAS):
            continue
        actual_usd, shadow_usd = valores["usd"]
        actual_ars, shadow_ars = valores["ars_nominal"]
        por_posicion.append({
            "ticker": ticker,
            "nombre": ticker,
            "valor_actual_usd": round(actual_usd, 2),
            "valor_shadow_usd": round(shadow_usd, 2),
            "costo_oportunidad_usd": round(shadow_usd - actual_usd, 2),
            "costo_oportunidad_ars": round(shadow_ars - actual_ars, 2),
        })

    por_posicion.sort(key=lambda x: abs(x["costo_oportunidad_usd"]), reverse=True)
    return por_posicion
