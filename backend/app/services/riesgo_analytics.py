"""Adaptador entre los datos reales (Session/DB) y el motor puro de riesgo (`risk_engine`).

Reutiliza las funciones privadas de `inversiones_analytics` (holdings, valuación, TWR mensual
encadenado, conversión de moneda/CER) en vez de reimplementar la valuación de cartera.
"""
import bisect
from datetime import date
from sqlalchemy.orm import Session

from ..database import BenchmarkValor
from . import risk_engine
from .inversiones_analytics import (
    _movimientos_ordenados,
    _precios_por_ticker,
    _calcular_twr_mensual,
    _calcular_twr_mensual_ars_real,
    _monto_usd,
    _monto_ars,
    _valuar_holdings,
    _valuar_holdings_ars,
    _cer_indice,
    _fin_de_mes_range,
)

MONEDAS_VALIDAS = ("ars_nominal", "ars_real", "usd")


def get_benchmarks_disponibles(db: Session) -> list[str]:
    rows = db.query(BenchmarkValor.benchmark).distinct().order_by(BenchmarkValor.benchmark).all()
    return [r[0] for r in rows]


def _benchmark_retornos_mensuales(benchmark: str, db: Session, hasta: date) -> dict[tuple[int, int], float]:
    """Retornos mensuales de un benchmark, alineados por (año, mes) con los de cartera.

    Toma el último valor conocido (carry-forward) en cada fin de mes y encadena la variación
    porcentual mes a mes, con el mismo criterio de fin de mes (`_fin_de_mes_range`) que el TWR
    mensual de cartera.
    """
    rows = (
        db.query(BenchmarkValor)
        .filter(BenchmarkValor.benchmark == benchmark)
        .order_by(BenchmarkValor.fecha)
        .all()
    )
    if not rows:
        return {}

    valores = [(r.fecha, float(r.valor)) for r in rows]
    fechas = [v[0] for v in valores]
    boundaries = _fin_de_mes_range(valores[0][0], hasta)

    puntos: list[tuple[date, float]] = []
    for b in boundaries:
        idx = bisect.bisect_right(fechas, b) - 1
        if idx < 0:
            continue
        puntos.append((b, valores[idx][1]))

    resultado: dict[tuple[int, int], float] = {}
    for i in range(1, len(puntos)):
        d0, v0 = puntos[i - 1]
        d1, v1 = puntos[i]
        if v0 == 0:
            continue
        resultado[(d1.year, d1.month)] = v1 / v0 - 1
    return resultado


def get_riesgo(cartera: str | None, moneda: str, benchmark: str | None, db: Session) -> dict:
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}")

    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()

    if moneda == "usd":
        retornos_por_mes = _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_usd, _valuar_holdings)
    elif moneda == "ars_nominal":
        retornos_por_mes = _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_ars, _valuar_holdings_ars)
    else:  # ars_real
        cer_hoy = _cer_indice(hoy, db, cer_cache)
        retornos_por_mes = _calcular_twr_mensual_ars_real(movs, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, hoy)

    retornos_validos = {k: v for k, v in retornos_por_mes.items() if v is not None}
    retornos_lista = [retornos_validos[k] for k in sorted(retornos_validos)]
    n_meses = len(retornos_validos)

    indice = risk_engine.construir_indice(retornos_por_mes)
    drawdown = risk_engine.calcular_drawdown(indice)
    drawdown["serie"] = risk_engine.serie_drawdown(indice) if drawdown["estado"] == "ok" else []
    volatilidad = risk_engine.calcular_volatilidad(retornos_lista)
    sortino = risk_engine.calcular_sortino(retornos_lista)
    retorno_anualizado = risk_engine.calcular_retorno_anualizado(indice)
    calmar = risk_engine.calcular_calmar(retorno_anualizado, drawdown.get("maximo"))
    mejores_peores = risk_engine.mejores_peores_periodos(retornos_validos)
    frecuencia = risk_engine.frecuencia_positivos_negativos(retornos_lista)

    if benchmark:
        retornos_benchmark = _benchmark_retornos_mensuales(benchmark, db, hoy)
        sharpe = risk_engine.calcular_sharpe_vs_benchmark(retornos_validos, retornos_benchmark, benchmark)
    else:
        sharpe = {"estado": "sin_benchmark", "valor": None, "benchmark": None, "n_obs": 0}

    return {
        "frecuencia": "mensual",
        "moneda": moneda,
        "benchmark_usado": benchmark if sharpe["estado"] == "ok" else None,
        "n_meses_historia": n_meses,
        "drawdown": drawdown,
        "volatilidad": volatilidad,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "mejores_periodos": mejores_peores["mejores"],
        "peores_periodos": mejores_peores["peores"],
        "frecuencia_positivos_negativos": frecuencia,
    }
