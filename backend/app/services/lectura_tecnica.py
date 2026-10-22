"""Adaptador DB → `lectura_tecnica_engine`: la lectura técnica de un ticker sobre su serie diaria.

Lo usan el endpoint `/tecnico/{ticker}/lectura` y el Centro de Decisiones. No valida que el ticker esté en
cartera o watchlist (eso lo hace el router): sin barras devuelve una lectura vacía.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import benchmarks, fuerza_relativa_engine, lectura_tecnica_engine, ohlcv_analytics


def leer_ticker(ticker: str, variante: str, db: Session) -> dict:
    """`variante` es una serie concreta (`local` | `subyacente`)."""
    serie = ohlcv_analytics.get_serie_barras(
        ticker, date.min, date.today(), db,
        max_barras=lectura_tecnica_engine.BARRAS_NECESARIAS, variante=variante,
    )
    barras = serie["barras"]
    bench = benchmarks.por_defecto(serie["moneda"])
    bench_barras = (
        benchmarks.barras(db, bench, desde=barras[0].fecha - timedelta(days=15)) if barras else []
    )
    alineado = (
        fuerza_relativa_engine.alinear_benchmark(barras, bench_barras) if bench_barras else None
    )
    return {
        "ticker": ticker, "variante": variante, "moneda": serie["moneda"],
        **lectura_tecnica_engine.leer(barras, alineado),
        "benchmark": bench if alineado else None,
        "benchmark_nombre": benchmarks.BENCHMARKS[bench]["nombre"] if alineado else None,
    }
