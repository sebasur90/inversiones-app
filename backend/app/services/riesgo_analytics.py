"""Adaptador entre los datos reales (Session/DB) y el motor puro de riesgo (`risk_engine`).

Reutiliza las funciones privadas de `inversiones_analytics` (holdings, valuación, TWR mensual
encadenado, conversión de moneda/CER) en vez de reimplementar la valuación de cartera.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import BenchmarkValor, IndiceMercado
from . import risk_engine
from .benchmarks_analytics import BENCHMARK_DOLAR, BENCHMARK_INFLACION
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
)

MONEDAS_VALIDAS = ("ars_nominal", "ars_real", "usd")


def get_benchmarks_disponibles(db: Session) -> list[str]:
    benchmarks = []

    if db.query(IndiceMercado).filter(IndiceMercado.mep.isnot(None)).first():
        benchmarks.append(BENCHMARK_DOLAR)

    if db.query(IndiceMercado).filter(IndiceMercado.cer.isnot(None)).first():
        benchmarks.append(BENCHMARK_INFLACION)

    rows = db.query(BenchmarkValor.benchmark).distinct().order_by(BenchmarkValor.benchmark).all()
    benchmarks.extend([r[0] for r in rows])

    return benchmarks




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

    benchmark_retorno_anualizado = None
    if benchmark:
        from .benchmarks_analytics import _resolver_fuente
        retornos_benchmark = _resolver_fuente(benchmark, db, hoy)
        sharpe = risk_engine.calcular_sharpe_vs_benchmark(retornos_validos, retornos_benchmark, benchmark)
        if retornos_benchmark:
            indice_benchmark = risk_engine.construir_indice(retornos_benchmark)
            benchmark_retorno_anualizado = risk_engine.calcular_retorno_anualizado(indice_benchmark)
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
        "benchmark_retorno_anualizado": round(benchmark_retorno_anualizado, 4) if benchmark_retorno_anualizado is not None else None,
        "mejores_periodos": mejores_peores["mejores"],
        "peores_periodos": mejores_peores["peores"],
        "frecuencia_positivos_negativos": frecuencia,
    }
