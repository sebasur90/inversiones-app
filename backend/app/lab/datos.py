"""Datos para el laboratorio: la serie **exacta** de la app y adaptadores para prototipar.

El lab **sólo lee**: nunca escribe en la DB (y en Docker el volumen va montado `:ro`). Abre su
propia `Session` con `SessionLocal` porque no está detrás de la inyección de dependencias de
FastAPI.
"""
from __future__ import annotations

from datetime import date

from ..database import SessionLocal
from ..services import ohlcv_analytics
from ..services.indicadores_engine import Barra

__all__ = ["barras_de_db", "barras_de_dataframe", "correr_como_la_app"]


def _a_fecha(valor) -> date:
    if valor is None:
        raise ValueError("se esperaba una fecha")
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def barras_de_db(
    ticker: str,
    desde: str | date | None = None,
    hasta: str | date | None = None,
    variante: str = "local",
    *,
    barras_previas: int = 0,
    max_barras: int = 3000,
) -> list[Barra]:
    """La serie canónica: mismas velas, feriados y variantes que ve el backtest de la app
    (`ohlcv_analytics.get_serie_barras`). `variante="subyacente"` lee la serie en USD del
    subyacente."""
    db = SessionLocal()
    try:
        serie = ohlcv_analytics.get_serie_barras(
            ticker,
            _a_fecha(desde) if desde is not None else date(1900, 1, 1),
            _a_fecha(hasta) if hasta is not None else date.today(),
            db,
            barras_previas=barras_previas,
            max_barras=max_barras,
            variante=variante,
        )
    finally:
        db.close()
    return list(serie["barras"])


def barras_de_dataframe(df, columnas: dict[str, str] | None = None) -> list[Barra]:
    """Adaptador genérico para prototipar sobre cualquier DataFrame. `columnas` remapea roles a
    nombres de columna, p.ej. `{"cierre": "Close", "maximo": "High"}`. La fecha sale de la columna
    `fecha` (o del índice si no está). Las columnas OHLCV que falten quedan en `None` — el motor
    degrada solo (`_hl` → `(cierre, cierre)`)."""
    roles = {"fecha": "fecha", "apertura": "apertura", "maximo": "maximo",
             "minimo": "minimo", "cierre": "cierre", "volumen": "volumen"}
    roles.update(columnas or {})

    col_fecha = roles["fecha"]
    fechas = list(df[col_fecha]) if col_fecha in df.columns else list(df.index)

    def _col(rol):
        nombre = roles[rol]
        return list(df[nombre]) if nombre in df.columns else [None] * len(fechas)

    aperturas, maximos, minimos, cierres, volumenes = (
        _col("apertura"), _col("maximo"), _col("minimo"), _col("cierre"), _col("volumen"),
    )
    if roles["cierre"] not in df.columns:
        raise KeyError(f"el DataFrame no tiene la columna de cierre {roles['cierre']!r}")

    out: list[Barra] = []
    for i, f in enumerate(fechas):
        out.append(Barra(
            fecha=_a_fecha(getattr(f, "date", lambda: f)() if hasattr(f, "date") else f),
            cierre=float(cierres[i]),
            apertura=None if aperturas[i] is None else float(aperturas[i]),
            maximo=None if maximos[i] is None else float(maximos[i]),
            minimo=None if minimos[i] is None else float(minimos[i]),
            volumen=None if volumenes[i] is None else float(volumenes[i]),
        ))
    return out


def correr_como_la_app(
    ticker: str,
    estrategia,
    desde: str | date | None = None,
    hasta: str | date | None = None,
    variante: str = "local",
) -> dict:
    """Llama directo a `estrategias_analytics.ejecutar_backtest` — cero duplicación de la lógica
    de warm-up / `indice_inicio` / `max_barras`, y por lo tanto paridad garantizada con lo que
    vas a ver en la pantalla. **Esta es la función para verificar una estrategia antes de
    exportarla.** `estrategia` puede ser un `Estrategia` del builder o un DSL `dict` crudo."""
    from ..services import estrategias_analytics

    dsl = estrategia.definicion() if hasattr(estrategia, "definicion") else estrategia
    db = SessionLocal()
    try:
        return estrategias_analytics.ejecutar_backtest(
            ticker, dsl, db,
            desde=_a_fecha(desde) if desde is not None else None,
            hasta=_a_fecha(hasta) if hasta is not None else None,
            variante=variante,
        )
    finally:
        db.close()
