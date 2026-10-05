"""Carga y persistencia de `EstadoMarketDataTicker` como dict.

Las rutas de `market_data.precios` reciben un `estado_por_ticker` (dict de dicts) que **mutan in
place**: el factor de escala calibrado, el estado de backfill, el símbolo del subyacente resuelto.
Quien orquesta lo carga antes y lo persiste después, una sola vez.

Vive acá porque lo usan dos orquestadores: `inversiones_sync.sync_from_sheet` (el sync completo) y
`refresco_precios.refrescar` (el job liviano de precios). Antes el bloque estaba escrito a mano
dentro del sync, y el job habría tenido que copiar las dos listas de doce campos.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..database import EstadoMarketDataTicker

# Los campos que viajan en el dict, en un solo lugar: agregar una columna al modelo y olvidarse de
# una de las dos mitades era la forma natural de perder un valor calibrado en silencio.
CAMPOS = (
    "factor_escala",
    "factor_fecha",
    "backfill_estado",
    "backfill_intento",
    "ohlcv_estado",
    "ohlcv_intento",
    "simbolo_local",
    "simbolo_subyacente",
    "mercado_subyacente",
    "moneda_subyacente",
    "resolucion_estado",
    "resolucion_intento",
)


def cargar(db: Session) -> dict[str, dict]:
    """`{ticker: {campo: valor}}` con el estado guardado de todos los tickers."""
    salida: dict[str, dict] = {}
    for fila in db.query(EstadoMarketDataTicker).all():
        estado = {campo: getattr(fila, campo) for campo in CAMPOS}
        # `factor_escala` es Numeric en la DB y las rutas de precios lo esperan float.
        if estado["factor_escala"] is not None:
            estado["factor_escala"] = float(estado["factor_escala"])
        salida[fila.ticker] = estado
    return salida


def persistir(db: Session, estado_por_ticker: dict[str, dict]) -> None:
    """Vuelca el dict a la tabla (upsert por ticker). Hace `flush`, no `commit`."""
    for ticker, estado in estado_por_ticker.items():
        fila = db.get(EstadoMarketDataTicker, ticker)
        if fila is None:
            fila = EstadoMarketDataTicker(ticker=ticker)
            db.add(fila)
        for campo in CAMPOS:
            setattr(fila, campo, estado.get(campo))
    db.flush()
