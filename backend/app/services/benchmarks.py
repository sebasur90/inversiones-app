"""Índices de referencia para la fuerza relativa (SPY, QQQ, Merval).

Se guardan en `serie_ohlcv` bajo la clave `SIMBOLO@BENCH` (ver `ohlcv_analytics.SUFIJO_BENCHMARK`),
con el mismo upsert y la misma precedencia que el resto de las series, pero no forman parte del
universo técnico: no se pueden graficar ni analizar, y el sync no los purga. Se leen directo de
`BarraOHLCV`, no con `get_serie_barras`.

Ciclo de vida: **backfill la primera vez que se piden** (`asegurar`) y **refresco diario** en el
job liviano de precios (`refrescar`). Sólo se refrescan los que ya existen: no se bajan índices que
nadie miró. Se guardan únicamente ruedas cerradas (`fecha < hoy`); el valor intradía de hoy no
se persiste porque el upsert no pisa una barra que ya tiene velas.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import BarraOHLCV
from . import ohlcv_analytics
from .indicadores_engine import Barra
from .market_data import yahoo
from .market_data.client import use_external_apis

logger = logging.getLogger("benchmarks")

BENCHMARKS: dict[str, dict] = {
    "SPY": {"nombre": "S&P 500 (SPY)", "moneda": "USD"},
    "QQQ": {"nombre": "Nasdaq 100 (QQQ)", "moneda": "USD"},
    "^MERV": {"nombre": "Merval", "moneda": "ARS"},
}
HISTORIA_ANIOS = 15
# Al refrescar se piden unos días hacia atrás por si quedaron ruedas sin bajar.
SOLAPE_DIAS = 7


def clave(simbolo: str) -> str:
    return f"{simbolo}{ohlcv_analytics.SUFIJO_BENCHMARK}"


def por_defecto(moneda: str) -> str:
    """El índice natural para una serie: el Merval para una en pesos, el S&P 500 para el resto."""
    return "^MERV" if (moneda or "").upper() == "ARS" else "SPY"


def _ultima_rueda_cerrada(hoy: date) -> date:
    """El último día de semana anterior a `hoy` (no mira feriados: a lo sumo se pide de más)."""
    d = hoy - timedelta(days=1)
    while d.weekday() > 4:
        d -= timedelta(days=1)
    return d


def _bajar(db: Session, simbolo: str, desde: date) -> int:
    """Baja `[desde, ayer]` de Yahoo y lo persiste (flush, sin commit). Devuelve cuántas filas
    llegaron; 0 si no hay red o no hubo ruedas."""
    hoy = date.today()
    if desde >= hoy:
        return 0
    crudas = yahoo.fetch_historico_ohlcv(simbolo, desde, hoy - timedelta(days=1))
    if not crudas:
        return 0
    moneda = BENCHMARKS[simbolo]["moneda"]
    filas = [
        {
            "ticker": clave(simbolo), "fecha": b.fecha, "apertura": b.apertura, "maximo": b.maximo,
            "minimo": b.minimo, "cierre": b.cierre, "volumen": b.volumen, "moneda": moneda,
            "fuente": "yahoo",
        }
        for b in crudas if b.fecha < hoy
    ]
    ohlcv_analytics.upsert_barras(db, filas)
    return len(filas)


def _f(valor) -> float | None:
    """Las columnas son `Numeric` (Decimal): el motor trabaja con floats."""
    return float(valor) if valor is not None else None


def barras(db: Session, simbolo: str, desde: date | None = None) -> list[Barra]:
    """Barras diarias del índice, ordenadas. Vacío si nunca se bajó."""
    q = db.query(BarraOHLCV).filter(BarraOHLCV.ticker == clave(simbolo))
    if desde is not None:
        q = q.filter(BarraOHLCV.fecha >= desde)
    return [
        Barra(fecha=r.fecha, cierre=_f(r.cierre), apertura=_f(r.apertura), maximo=_f(r.maximo),
              minimo=_f(r.minimo), volumen=_f(r.volumen))
        for r in q.order_by(BarraOHLCV.fecha).all()
    ]


def asegurar(db: Session, simbolo: str) -> bool:
    """Garantiza que el índice tenga historia; la primera vez que se pide la baja entera.
    Devuelve si hay datos después. Best effort: sin red devuelve lo que haya. Commitea si bajó."""
    tiene = db.query(func.count(BarraOHLCV.id)).filter(BarraOHLCV.ticker == clave(simbolo)).scalar() > 0
    if not tiene and use_external_apis():
        hoy = date.today()
        if _bajar(db, simbolo, date(hoy.year - HISTORIA_ANIOS, 1, 1)):
            db.commit()
            tiene = True
    return tiene


def refrescar(db: Session) -> int:
    """Pone al día los índices que ya existen y quedaron atrás. No commitea (lo hace el job).
    Devuelve cuántas filas nuevas procesó. Nunca lanza por red."""
    if not use_external_apis():
        return 0
    cerrada = _ultima_rueda_cerrada(date.today())
    total = 0
    for simbolo in BENCHMARKS:
        ultima = db.query(func.max(BarraOHLCV.fecha)).filter(BarraOHLCV.ticker == clave(simbolo)).scalar()
        # Sin filas: nadie lo pidió todavía. Al día: la última rueda cerrada ya está.
        if ultima is None or ultima >= cerrada:
            continue
        total += _bajar(db, simbolo, ultima - timedelta(days=SOLAPE_DIAS))
    db.flush()
    return total
