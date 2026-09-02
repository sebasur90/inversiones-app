"""Adaptador entre los datos reales (Session/DB) y el motor puro de contribución/concentración/
correlación (`contribucion_engine`).

Reutiliza las funciones privadas de `inversiones_analytics` (holdings, valuación, agrupación por
eje, P&L realizado/no realizado) en vez de reimplementar la valuación de cartera, igual que hace
`riesgo_analytics.py` para el motor de riesgo.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import InstrumentoInversion
from . import contribucion_engine
from .inversiones_analytics import (
    EPS,
    _movimientos_ordenados,
    _precios_por_ticker,
    _precio_conocido,
    _fin_de_mes_range,
    _HoldingsTracker,
    _holdings_por_cartera_ticker,
    _to_usd,
    _monto_usd,
    _agrupar,
    _clasificados_valorizados,
    _retornos_mensuales_ticker,
    get_pnl_realizado_no_realizado,
)
from .cache import cache_por_sync

UNIVERSOS_VALIDOS = ("tenencias", "todos")


# ── Contribución al rendimiento ──────────────────────────────────────────────

def _peso_promedio_por_ticker(movs, precios_por_ticker, db: Session, mep_cache: dict) -> dict[str, float]:
    """Peso promedio (%) de cada ticker sobre el valor total de la cartera, promediado en
    cada fin de mes desde el primer movimiento (inclusive). Los meses previos a la primera
    compra de un ticker cuentan como 0% en su promedio (decisión de producto confirmada:
    el peso promedio se mide "desde que empecé a invertir", no "desde que tengo esta posición")."""
    primera_fecha = movs[0].fecha
    hoy = date.today()
    boundaries = _fin_de_mes_range(primera_fecha, hoy)
    if not boundaries:
        return {}

    tracker = _HoldingsTracker(movs)
    pesos_acumulados: dict[str, float] = {}

    for b in boundaries:
        tracker.avanzar_a(b)
        valores_ticker: dict[str, float] = {}
        for ticker, cantidad in tracker.snapshot().items():
            if abs(cantidad) < EPS:
                continue
            precios_sorted = precios_por_ticker.get(ticker)
            info = _precio_conocido(precios_sorted, b) if precios_sorted else None
            if info is None:
                continue
            _fecha_precio, precio, moneda = info
            usd = _to_usd(precio * cantidad, moneda, b, db, mep_cache)
            if usd is not None:
                valores_ticker[ticker] = usd
        total_b = sum(valores_ticker.values())
        if total_b <= EPS:
            continue
        for ticker, v in valores_ticker.items():
            pesos_acumulados[ticker] = pesos_acumulados.get(ticker, 0.0) + v / total_b

    n_boundaries = len(boundaries)
    return {ticker: (suma / n_boundaries) * 100 for ticker, suma in pesos_acumulados.items()}


@cache_por_sync
def get_contribucion(cartera: str | None, db: Session) -> dict:
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return {"contribucion": [], "concentracion": []}

    precios_por_ticker = _precios_por_ticker(db)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}
    mep_cache: dict = {}

    peso_promedio_pct = _peso_promedio_por_ticker(movs, precios_por_ticker, db, mep_cache)

    # Reusa get_pnl_realizado_no_realizado para que el P&L por ticker coincida exactamente
    # con lo que ya muestra la pantalla de PnL (realizado + no_realizado + ingresos).
    pnl_data = get_pnl_realizado_no_realizado(cartera, db)
    pnl_por_ticker = {item["ticker"]: item["total_usd"] for item in pnl_data["por_ticker"]}

    costo_total_por_ticker: dict[str, float] = {}
    for mov in movs:
        if mov.tipo_movimiento != "compra":
            continue
        monto_usd = _monto_usd(mov, db, mep_cache)
        if monto_usd is None:
            continue
        costo_total_por_ticker[mov.ticker] = costo_total_por_ticker.get(mov.ticker, 0.0) + monto_usd

    costo_total_portfolio = sum(costo_total_por_ticker.values())
    tickers_todos = set(peso_promedio_pct) | set(pnl_por_ticker) | set(costo_total_por_ticker)

    def _item(etiqueta: str, pnl: float, costo: float, peso: float) -> dict:
        rentabilidad = (pnl / costo * 100) if abs(costo) > EPS else None
        # Mismo denominador para todos los tickers: la suma de contribucion_pct reconcilia
        # exactamente con el retorno simple total de la cartera (no es TWR/XIRR).
        contribucion = (pnl / costo_total_portfolio * 100) if abs(costo_total_portfolio) > EPS else 0.0
        return {
            "etiqueta": etiqueta,
            "peso_promedio_pct": round(peso, 2),
            "pnl_usd": round(pnl, 2),
            "costo_total_usd": round(costo, 2),
            "rentabilidad_pct": round(rentabilidad, 2) if rentabilidad is not None else None,
            "contribucion_pct": round(contribucion, 2),
        }

    items_ticker = [
        _item(t, pnl_por_ticker.get(t, 0.0), costo_total_por_ticker.get(t, 0.0), peso_promedio_pct.get(t, 0.0))
        for t in tickers_todos
    ]
    items_ticker.sort(key=lambda it: -abs(it["contribucion_pct"]))

    ejes = [{"eje": "Ticker", "items": items_ticker}] if items_ticker else []

    def _rollup(nombre_eje: str, attr: str, bucket_sin_dato: str | None = None) -> None:
        grupos: dict[str, dict[str, float]] = {}
        for t in tickers_todos:
            instrumento = instrumentos.get(t)
            etiqueta = getattr(instrumento, attr, None) if instrumento else None
            if etiqueta is None:
                if bucket_sin_dato is None or instrumento is None:
                    continue
                etiqueta = bucket_sin_dato
            g = grupos.setdefault(etiqueta, {"pnl": 0.0, "costo": 0.0, "peso": 0.0})
            g["pnl"] += pnl_por_ticker.get(t, 0.0)
            g["costo"] += costo_total_por_ticker.get(t, 0.0)
            g["peso"] += peso_promedio_pct.get(t, 0.0)
        if not grupos:
            return
        items = [_item(etq, g["pnl"], g["costo"], g["peso"]) for etq, g in grupos.items()]
        items.sort(key=lambda it: -abs(it["contribucion_pct"]))
        ejes.append({"eje": nombre_eje, "items": items})

    _rollup("Tipo de instrumento", "tipo_instrumento")
    _rollup("Sector", "sector", bucket_sin_dato="Sin sector")
    _rollup("Mercado", "mercado")

    return {"contribucion": ejes, "concentracion": get_concentracion(cartera, db)}


# ── Concentración (HHI) ──────────────────────────────────────────────────────

def get_concentracion(cartera: str | None, db: Session) -> list[dict]:
    _valores, clasificados, instrumentos = _clasificados_valorizados(cartera, db)
    if not clasificados:
        return []

    total_usd = sum(v_usd for _, _, v_usd, _ in clasificados)

    def _con_hhi(eje: str, items: list[dict]) -> dict:
        pesos = [it["porcentaje"] for it in items]
        return {"eje": eje, **contribucion_engine.calcular_hhi(pesos)}

    def _con_hhi_residual(eje: str, items: list[dict], bucket_residual: str) -> dict:
        """Ejes con bucket residual: además del HHI, cuántas categorías son reales
        (M8: el guardrail de diversificación no debe contar "Sin sector"/"Sin país" como país)."""
        d = _con_hhi(eje, items)
        d["n_componentes_reales"] = sum(1 for it in items if it["etiqueta"] != bucket_residual)
        return d

    resultado = []

    ticker_items = _agrupar([(t, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    resultado.append(_con_hhi("Ticker", ticker_items))

    tipo_items = _agrupar([(instrumentos[t].tipo_instrumento, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    resultado.append(_con_hhi("Tipo de instrumento", tipo_items))

    mercado_items = _agrupar([(instrumentos[t].mercado, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    resultado.append(_con_hhi("Mercado", mercado_items))

    moneda_items = _agrupar([(instrumentos[t].moneda, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    resultado.append(_con_hhi("Moneda", moneda_items))

    # A diferencia de get_exposicion, el eje Sector pasa `total_usd` a `_agrupar` y usa un bucket
    # explícito "Sin sector": el HHI necesita que los pesos sumen el 100% real de la cartera,
    # no el subtotal de lo etiquetado (si no, una cartera con muchos tickers sin clasificar
    # parecería artificialmente diversificada).
    sector_entries = [
        (instrumentos[t].sector if instrumentos[t].sector else "Sin sector", v_usd, v_ars)
        for _, t, v_usd, v_ars in clasificados
    ]
    sector_items = _agrupar(sector_entries, total_usd)
    resultado.append(_con_hhi_residual("Sector", sector_items, "Sin sector"))

    # Igual que Sector: bucket explícito "Sin país" para que los pesos sumen el 100% real
    # (si no, una cartera mayormente sin país etiquetado parecería diversificada).
    pais_entries = [
        (instrumentos[t].pais if instrumentos[t].pais else "Sin país", v_usd, v_ars)
        for _, t, v_usd, v_ars in clasificados
    ]
    pais_items = _agrupar(pais_entries, total_usd)
    resultado.append(_con_hhi_residual("País", pais_items, "Sin país"))

    return resultado


# ── Correlaciones ────────────────────────────────────────────────────────────

def get_correlaciones(cartera: str | None, db: Session, universo: str = "tenencias") -> dict:
    vacio = {"universo": universo, "n_tickers": 0, "tickers": [], "matriz": [], "pares": [], "advertencia_historial_corto": False}

    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return vacio

    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    hoy = date.today()

    if universo == "tenencias":
        holdings = _holdings_por_cartera_ticker(movs, hoy)
        tickers = sorted({t for (_cart, t), c in holdings.items() if abs(c) > EPS})
    else:
        tickers = sorted(precios_por_ticker.keys())

    if not tickers:
        return vacio

    fechas_iniciales = [precios_por_ticker[t][0][0] for t in tickers if precios_por_ticker.get(t)]
    if not fechas_iniciales:
        return {**vacio, "tickers": tickers, "n_tickers": len(tickers)}

    boundaries = _fin_de_mes_range(min(fechas_iniciales), hoy)

    series_por_ticker = {
        t: _retornos_mensuales_ticker(precios_por_ticker.get(t, []), boundaries, "USD", db, mep_cache)
        for t in tickers
    }

    resultado = contribucion_engine.construir_matriz_correlacion(tickers, series_por_ticker)
    resultado["universo"] = universo
    return resultado
