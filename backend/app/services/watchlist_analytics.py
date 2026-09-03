"""Watchlist: instrumentos a seguir y su distancia a la zona de compra.

La diferencia con las alertas de precio de `Posiciones` es la dirección: el `Objetivo` de un
instrumento en cartera es un precio de **venta** (se cruza hacia arriba), mientras que el de la
watchlist es un precio de **compra** (se cruza hacia abajo). Por eso `_nivel_precio` se invoca acá
con `alcanzado_si_mayor=False`, igual que el stop-loss.

La detección de "cerca" (el umbral de proximidad) vive en el frontend, como la de posiciones: es
una preferencia del usuario guardada en localStorage y se aplica sobre `pct_a_objetivo` sin
necesidad de re-sincronizar.
"""
from datetime import date

from sqlalchemy.orm import Session

from ..database import InstrumentoInversion, MovimientoInversion, PrecioWatchlist, WatchlistItem
from .inversiones_analytics import (
    _holdings_por_cartera_ticker,
    _nivel_precio,
    _precio_conocido,
    _precios_por_ticker,
)


def _tickers_en_cartera(db: Session, hasta: date) -> set[str]:
    """Tickers con tenencia > 0 a `hasta`, sumando todas las carteras."""
    movs = db.query(MovimientoInversion).all()
    totales: dict[str, float] = {}
    for (_cartera, ticker), cantidad in _holdings_por_cartera_ticker(movs, hasta).items():
        totales[ticker] = totales.get(ticker, 0.0) + cantidad
    return {t for t, cant in totales.items() if cant > 0}


def get_watchlist(db: Session) -> list[dict]:
    """La watchlist con precio actual, distancia al objetivo y si está en zona de compra.

    El precio sale de la serie de `precios_instrumento` (con carry-forward) cuando el ticker
    también existe en `Instrumentos` -- ahí hay historia real --, y de `precios_watchlist` cuando
    es un ticker que sólo se está siguiendo.

    Ordena por urgencia: primero lo que ya está en zona, después lo más cerca del objetivo, y al
    final lo que no tiene objetivo o precio.
    """
    items = db.query(WatchlistItem).order_by(WatchlistItem.ticker).all()
    if not items:
        return []

    hoy = date.today()
    tickers_instrumento = {row[0] for row in db.query(InstrumentoInversion.ticker).all()}
    en_cartera = _tickers_en_cartera(db, hoy)
    precios_wl = {row.ticker: row for row in db.query(PrecioWatchlist).all()}
    precios_inst = _precios_por_ticker(db) if tickers_instrumento else {}

    resultado: list[dict] = []
    for item in items:
        precio_actual: float | None = None
        fecha_precio: date | None = None
        moneda_precio: str | None = None
        fuente_precio: str | None = None

        if item.ticker in tickers_instrumento:
            conocido = _precio_conocido(precios_inst.get(item.ticker, []), hoy)
            if conocido is not None:
                fecha_precio, precio_actual, moneda_precio = conocido
                fuente_precio = "cartera"
        else:
            fila = precios_wl.get(item.ticker)
            if fila is not None:
                fecha_precio = fila.fecha
                precio_actual = float(fila.precio)
                moneda_precio = fila.moneda
                fuente_precio = fila.fuente

        objetivo = float(item.objetivo) if item.objetivo is not None else None
        precio_objetivo, pct_a_objetivo, en_zona = _nivel_precio(
            "Fijo" if objetivo is not None else None,
            objetivo,
            0.0,  # sin precio promedio de compra: el modo "Fijo" no lo usa
            precio_actual if precio_actual is not None else 0.0,
            alcanzado_si_mayor=False,
        )

        resultado.append({
            "ticker": item.ticker,
            "nombre": item.nombre,
            "tipo_instrumento": item.tipo_instrumento,
            "mercado": item.mercado,
            "moneda": item.moneda,
            "pais": item.pais,
            "sector": item.sector,
            "precio_actual": precio_actual,
            "fecha_precio": fecha_precio,
            "moneda_precio": moneda_precio or item.moneda,
            "fuente_precio": fuente_precio,
            "precio_objetivo": precio_objetivo,
            "pct_a_objetivo": pct_a_objetivo,
            "en_zona": en_zona,
            "en_cartera": item.ticker in en_cartera,
        })

    def _orden(fila: dict) -> tuple[int, float]:
        if fila["en_zona"]:
            return (0, -abs(fila["pct_a_objetivo"] or 0.0))
        if fila["pct_a_objetivo"] is not None:
            return (1, abs(fila["pct_a_objetivo"]))
        return (2, 0.0)

    return sorted(resultado, key=_orden)
