"""Adaptador Session/DB → `descomposicion_engine`: descomposición jerárquica de la cartera en
Familia → País → Sector → Ticker.

Reutiliza `_clasificados_valorizados` (valuación + clasificación) de `inversiones_analytics`,
igual que hacen `contribucion_analytics`/`riesgo_analytics`, en vez de recalcular la valuación
de cartera.
"""
from datetime import date

from sqlalchemy.orm import Session

from .cache import cache_por_sync
from .descomposicion_engine import NIVELES, construir_arbol
from .inversiones_analytics import (
    EPS,
    _clasificados_valorizados,
    _holdings_por_cartera_ticker,
    _movimientos_ordenados,
)


@cache_por_sync
def get_descomposicion(cartera: str | None, db: Session) -> dict:
    valores, _clasificados, instrumentos = _clasificados_valorizados(cartera, db)

    # Consolidar por ticker: en Consolidado el mismo ticker puede estar en más de una cartera,
    # y acá tiene que aparecer como una sola hoja (sumando los valores de todas).
    por_ticker: dict[str, dict] = {}
    for _cart, ticker, valor_usd, valor_ars in valores:
        acc = por_ticker.setdefault(ticker, {"valor_usd": 0.0, "valor_ars": 0.0})
        acc["valor_usd"] += valor_usd
        acc["valor_ars"] += valor_ars

    posiciones = []
    for ticker, acc in por_ticker.items():
        inst = instrumentos.get(ticker)
        posiciones.append({
            "ticker": ticker,
            "nombre": inst.nombre if inst else ticker,
            "tipo_instrumento": inst.tipo_instrumento if inst else None,
            "sector": inst.sector if inst else None,
            "pais": inst.pais if inst else None,
            # Sin ficha en Instrumentos: cae directo en el bucket "Sin clasificar" del árbol
            # (ver `descomposicion_engine.familia_de`), en vez de desaparecer como hace
            # `get_exposicion` con los tickers fuera de `clasificados`.
            "con_ficha": inst is not None,
            "valor_usd": acc["valor_usd"],
            "valor_ars": acc["valor_ars"],
        })

    total_usd = sum(p["valor_usd"] for p in posiciones)
    total_ars = sum(p["valor_ars"] for p in posiciones)

    raiz = construir_arbol(posiciones, total_usd, total_ars)

    # Posiciones con tenencia pero que `_clasificados_valorizados` descartó (sin precio
    # conocido para hoy, o sin MEP para convertir su moneda): no entran al árbol —igual
    # criterio que Exposición/Rebalanceo— pero se listan para avisar, no para ocultarlas en
    # silencio.
    hoy = date.today()
    movs = _movimientos_ordenados(db, None)
    holdings = _holdings_por_cartera_ticker(movs, hoy)
    tickers_con_tenencia = {
        ticker
        for (cart, ticker), cantidad in holdings.items()
        if abs(cantidad) >= EPS and (cartera is None or cart == cartera)
    }
    posiciones_sin_precio = sorted(tickers_con_tenencia - set(por_ticker))

    return {
        "niveles": list(NIVELES),
        "total_usd": round(total_usd, 2),
        "total_ars": round(total_ars, 2),
        "instrumentos": len(posiciones),
        "raiz": raiz,
        "posiciones_sin_precio": posiciones_sin_precio,
    }
