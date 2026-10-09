"""Adaptador Session/DB → `descomposicion_engine`: descomposición jerárquica de la cartera en
Familia → País → Sector → Ticker.

Reutiliza `_clasificados_valorizados` (valuación + clasificación) de `inversiones_analytics`,
igual que hacen `contribucion_analytics`/`riesgo_analytics`, en vez de recalcular la valuación
de cartera: por eso el total de acá es el mismo que el de la pantalla principal.
"""
from sqlalchemy.orm import Session

from .cache import cache_por_sync
from .descomposicion_engine import NIVELES, construir_arbol
from .inversiones_analytics import _clasificados_valorizados


@cache_por_sync
def get_descomposicion(cartera: str | None, db: Session) -> dict:
    pos = _clasificados_valorizados(cartera, db)
    instrumentos = pos.instrumentos

    # Consolidar por ticker: en Consolidado el mismo ticker puede estar en más de una cartera,
    # y acá tiene que aparecer como una sola hoja (sumando los valores de todas).
    por_ticker: dict[str, dict] = {}
    for _cart, ticker, valor_usd, valor_ars in pos.valores:
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
            # (ver `descomposicion_engine.familia_de`), mismo criterio que el bucket residual
            # de los ejes de `get_exposicion`.
            "con_ficha": inst is not None,
            "valor_usd": acc["valor_usd"],
            "valor_ars": acc["valor_ars"],
        })

    total_usd = sum(p["valor_usd"] for p in posiciones)
    total_ars = sum(p["valor_ars"] for p in posiciones)

    raiz = construir_arbol(posiciones, total_usd, total_ars)

    return {
        "niveles": list(NIVELES),
        "total_usd": round(total_usd, 2),
        "total_ars": round(total_ars, 2),
        "instrumentos": len(posiciones),
        "raiz": raiz,
        # Las posiciones sin cotización ya entran al árbol valuadas al costo (igual que en la
        # pantalla principal): lo que se avisa es cuáles son aproximadas y cuáles no se pudo
        # valuar de ninguna forma, no una lista de excluidas en silencio.
        "avisos": pos.avisos(),
    }
