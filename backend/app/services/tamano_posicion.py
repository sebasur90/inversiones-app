"""Insumos de la calculadora de tamaño de posición del gráfico técnico.

La cuenta (riesgo ÷ distancia al stop) la hace el frontend, que es donde el usuario mueve los
números; acá sólo se juntan los datos que viven en el servidor: el último cierre y el ATR de la
serie, el último precio local (para contar CEDEARs sin necesitar el ratio), el MEP y el valor de
la cartera. No hay concepto de cash disponible en la app, así que el riesgo "% de la cartera" se
mide sobre el valor actual de lo que se tiene.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import indicadores_engine as ind
from . import inversiones_analytics as ia
from . import ohlcv_analytics

PERIODO_ATR = 14
# El ATR es de Wilder (recursivo): con unas pocas centenas de barras la semilla ya no pesa.
BARRAS_ATR = 300


def get_tamano_posicion(ticker: str, variante: str, db: Session) -> dict:
    """`variante` es una serie concreta (`local` | `subyacente`), nunca `referencia`."""
    serie = ohlcv_analytics.get_serie_barras(
        ticker, date.min, date.today(), db, max_barras=BARRAS_ATR, variante=variante,
    )
    barras = serie["barras"]
    ultima = barras[-1] if barras else None

    precios = ia._precios_por_ticker(db).get(ticker)
    local = precios[-1] if precios else None

    valor = ia.get_resumen(None, db).get("valor_actual_usd")
    return {
        "ticker": ticker, "variante": variante, "moneda": serie["moneda"],
        "ultimo_cierre": ultima.cierre if ultima else None,
        "fecha_cierre": ultima.fecha if ultima else None,
        "atr": ind.atr(barras, PERIODO_ATR)[-1] if barras else None,
        "precio_local": local[1] if local else None,
        "moneda_local": local[2] if local else None,
        "mep": ia.get_mep_actual(db),
        "valor_cartera_usd": valor if valor and valor > 0 else None,
    }
