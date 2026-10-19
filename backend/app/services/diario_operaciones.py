"""Diario de operaciones: todas las compras y ventas del usuario, con el contexto de mercado de cada
una y un resumen de cómo opera.

Reúne `operaciones_grafico.get_operaciones_grafico` de cada ticker con movimientos, cada uno sobre
su serie de referencia (el subyacente en USD para un CEDEAR): el contexto (RSI, SMA200, rango anual)
y el "después de vender" son los mismos que el usuario ve en el gráfico del ticker. Los números del
resumen y las frases están en `diario_operaciones_engine`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..database import MovimientoInversion
from . import diario_operaciones_engine as eng
from . import ohlcv_analytics, operaciones_grafico
from .cache import cache_por_sync

TIPOS_DEL_DIARIO = ("compra", "venta", "amortizacion")
CAMPOS = (
    "fecha", "tipo", "cantidad", "precio", "moneda", "precio_usd_mep", "resultado_usd", "resultado_pct",
    "rsi", "dist_sma200_pct", "rango_52s_pct", "post_30_pct", "post_90_pct", "post_180_pct", "aproximado",
)


@cache_por_sync
def get_diario(db: Session) -> dict:
    tickers = sorted({
        t for (t,) in db.query(MovimientoInversion.ticker)
        .filter(MovimientoInversion.tipo_movimiento.in_(TIPOS_DEL_DIARIO)).distinct()
    })
    operaciones: list[dict] = []
    ciclos: list[dict] = []
    sin_serie: list[str] = []

    for ticker in tickers:
        variante = ohlcv_analytics.variante_efectiva(db, ticker, None)
        datos = operaciones_grafico.get_operaciones_grafico(ticker, variante, db)
        if "sin_serie" in datos["advertencias"]:
            sin_serie.append(ticker)
        for op in datos["operaciones"]:
            if op["tipo"] in TIPOS_DEL_DIARIO:
                operaciones.append({"ticker": ticker, "variante": variante, **{k: op[k] for k in CAMPOS}})
        ciclos.extend({"ticker": ticker, **c} for c in datos["ciclos"])

    operaciones.sort(key=lambda o: (o["fecha"], o["ticker"]), reverse=True)
    resumen = eng.resumir(operaciones, ciclos)
    return {
        "operaciones": operaciones,
        "resumen": resumen,
        "frases": eng.frases(resumen),
        "tickers_sin_serie": sin_serie,
    }
