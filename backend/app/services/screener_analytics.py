"""Orquestación del screener: corre `screener_engine` sobre todos los pares (estrategia, ticker)
del universo cartera ∪ watchlist y devuelve, ordenados por cercanía, los que están a menos de
`umbral_pct` de disparar.

Esqueleto calcado de `estrategias_analytics.senales_recientes`: un ticker o una estrategia rota no
tira abajo el escaneo entero (`try/except` por par), y la fuente de precios es
`ohlcv_analytics.get_serie_barras`, ya cacheada por sync.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..database import EstrategiaTecnica
from . import estrategia_engine, estrategias_universo, ohlcv_analytics, screener_engine
from .cache import cache_por_sync

# La expansión de estrategias sobre el universo (y su tope) es compartida con
# `estrategias_analytics.senales_recientes`: vive en `estrategias_universo`.
MAX_PARES = estrategias_universo.MAX_PARES

_ORIGENES_VALIDOS = estrategias_universo.ORIGENES_VALIDOS


def _evaluar_par(estrategia: EstrategiaTecnica, ticker_info: dict, db: Session, hoy: date) -> dict | None:
    dsl = estrategia.definicion
    variante = getattr(estrategia, "variante", None) or "local"
    max_barras = estrategias_universo.max_barras_para(dsl)

    serie = ohlcv_analytics.get_serie_barras(
        ticker_info["ticker"], date(1900, 1, 1), hoy, db,
        barras_previas=0, max_barras=max_barras, variante=variante,
    )
    barras = serie["barras"]
    if len(barras) < 2:
        return None

    resultado = estrategia_engine.backtest(dsl, barras)
    ultima_operacion = resultado.operaciones[-1] if resultado.operaciones else None
    abierta = ultima_operacion is not None and ultima_operacion.abierta

    base = {
        "ticker": ticker_info["ticker"], "nombre": ticker_info["nombre"], "origen": ticker_info["origen"],
        "estrategia_id": estrategia.id, "estrategia_nombre": estrategia.nombre,
        "variante": variante, "moneda": serie["moneda"],
        "precio_actual": barras[-1].cierre, "fecha_precio": barras[-1].fecha,
        "posicion_abierta": abierta,
        "retorno_abierta_pct": round(ultima_operacion.retorno_neto_pct, 4) if abierta else None,
    }

    if not abierta:
        distancia = screener_engine.distancia_al_disparo(dsl, barras, "entrada")
        if distancia is None:
            return None
        candidatos = [("entrada", distancia)]
    else:
        candidatos = []
        distancia_salida = screener_engine.distancia_al_disparo(dsl, barras, "salida")
        if distancia_salida is not None:
            candidatos.append(("regla_salida", distancia_salida))
        riesgo = dsl.get("riesgo") or {}
        for stop in screener_engine.distancia_a_stops(
            barras, ultima_operacion.indice_entrada, ultima_operacion.precio_entrada, riesgo,
        ):
            candidatos.append((stop["motivo"], stop["distancia_pct"]))
        if not candidatos:
            return None

    motivo, distancia = min(candidatos, key=lambda par: abs(par[1]))
    condicion = "salida" if abierta else "entrada"

    return {
        **base,
        "tipo": "venta" if abierta else "compra",
        "motivo": motivo,
        "distancia_pct": round(distancia, 4),
        "precio_gatillo": round(barras[-1].cierre * (1 + distancia / 100), 4),
        "dispara_ahora": distancia == 0.0,
        "condiciones": screener_engine.desglose_condiciones(dsl, barras, condicion),
    }


@cache_por_sync
def escanear(
    db: Session, estrategia_ids: tuple[int, ...] = (), umbral_pct: float = 3.0, origen: str = "todos",
) -> dict:
    """Filas de (estrategia, ticker) a `<= umbral_pct` de disparar, ordenadas por cercanía.

    `estrategia_ids` vacío = todas las guardadas. `origen` filtra el universo de tickers
    (`"todos"|"cartera"|"watchlist"`), no las estrategias: una estrategia con `ticker` propio
    corre en ese ticker sin importar `origen` si ese ticker no queda filtrado afuera.
    """
    if origen not in _ORIGENES_VALIDOS:
        raise ValueError(f"origen desconocido: {origen!r}")

    hoy = date.today()
    advertencias: list[str] = []

    estrategias, hubo_invalidas = estrategias_universo.estrategias_validas(db, estrategia_ids)
    if hubo_invalidas:
        advertencias.append("estrategias_invalidas_omitidas")

    universo = ohlcv_analytics.listar_tickers_tecnicos(db)
    pares, truncado = estrategias_universo.armar_pares(estrategias, universo, origen)
    if truncado:
        advertencias.append("universo_truncado")

    filas: list[dict] = []
    tickers_evaluados: set[str] = set()
    for estrategia, ticker_info in pares:
        tickers_evaluados.add(ticker_info["ticker"])
        try:
            fila = _evaluar_par(estrategia, ticker_info, db, hoy)
        except (ValueError, KeyError, TypeError):
            continue  # DSL válido para el validador pero roto para esta serie: se omite
        if fila is None:
            continue
        if abs(fila["distancia_pct"]) > umbral_pct:
            continue
        filas.append(fila)

    filas.sort(key=lambda f: (abs(f["distancia_pct"]), f["ticker"]))

    return {
        "filas": filas,
        "tickers_evaluados": len(tickers_evaluados),
        "pares_evaluados": len(pares),
        "umbral_pct": umbral_pct,
        "fecha": hoy,
        "advertencias": advertencias,
    }
