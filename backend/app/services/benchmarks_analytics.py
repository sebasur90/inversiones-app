"""Adaptador entre los datos reales (Session/DB) y las métricas de performance relativa.

Reúne la comparación de cartera contra benchmarks, normalizando la TWR mensual de ambos
a un rango común y computando métricas de relative performance (alpha, beta, tracking error,
information ratio).
"""
import bisect
from datetime import date
from sqlalchemy.orm import Session

from ..database import BenchmarkValor
from . import risk_engine
from .inversiones_analytics import (
    _movimientos_ordenados,
    _precios_por_ticker,
    _fin_de_mes_range,
    _calcular_twr_mensual,
    _calcular_twr_mensual_ars_real,
    _monto_usd,
    _monto_ars,
    _valuar_holdings,
    _valuar_holdings_ars,
    _cer_indice,
    get_configuracion_cartera,
)

MONEDAS_VALIDAS = ("ars_nominal", "ars_real", "usd")


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


def _twr_mensual_por_moneda(moneda: str, movs: list, precios_por_ticker: dict, db: Session, mep_cache: dict, cer_cache: dict, hoy: date) -> dict:
    """Selecciona y ejecuta el cálculo de TWR mensual según la moneda."""
    from . import riesgo_analytics  # Import here to avoid circular dependency

    if moneda == "usd":
        return _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_usd, _valuar_holdings)
    elif moneda == "ars_nominal":
        return _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_ars, _valuar_holdings_ars)
    else:  # ars_real
        cer_hoy = _cer_indice(hoy, db, cer_cache)
        return _calcular_twr_mensual_ars_real(movs, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, hoy)


def _filtrar_desde(retornos_por_mes: dict[tuple[int, int], float], desde: date | None) -> dict[tuple[int, int], float]:
    """Filtra un diccionario de retornos mensuales para excluir meses anteriores a `desde`."""
    if desde is None:
        return retornos_por_mes
    return {(a, m): r for (a, m), r in retornos_por_mes.items() if (a, m) >= (desde.year, desde.month)}


def get_performance_relativa(cartera: str | None, moneda: str, benchmark: str | None, desde: date | None, db: Session) -> dict:
    """Compara el rendimiento de una cartera contra un benchmark.

    Retorna un diccionario con índices base-100 pareados, métricas de diferencia (delta,
    costo de oportunidad), y métricas avanzadas de relative performance (alpha, beta,
    tracking error, information ratio).
    """
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}")

    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()

    # Resolver benchmark: preferencia explícita > configuración > sin_benchmark
    benchmark_resuelto = benchmark
    if benchmark_resuelto is None:
        config = get_configuracion_cartera(cartera, db)
        benchmark_resuelto = config.get("benchmark") if config else None

    if benchmark_resuelto is None:
        return {
            "estado": "sin_benchmark",
            "moneda": moneda,
            "benchmark_usado": None,
            "periodo_desde": None,
            "periodo_hasta": None,
            "n_meses_historia": 0,
            "retorno_cartera_pct": None,
            "retorno_benchmark_pct": None,
            "delta_pp": None,
            "costo_oportunidad_pp": None,
            "exceso_retorno": {"estado": "sin_benchmark", "valor": None, "n_obs": 0},
            "alpha": {"estado": "sin_benchmark", "valor": None},
            "beta": {"estado": "sin_benchmark", "valor": None, "n_obs": 0},
            "tracking_error": {"estado": "sin_benchmark", "valor": None, "n_obs": 0},
            "information_ratio": {"estado": "sin_benchmark", "valor": None, "n_obs": 0},
            "serie": [],
        }

    # Calcular TWR mensual de cartera
    retornos_cartera = _twr_mensual_por_moneda(moneda, movs, precios_por_ticker, db, mep_cache, cer_cache, hoy)
    retornos_cartera = _filtrar_desde(retornos_cartera, desde)

    # Calcular retornos mensuales del benchmark
    retornos_benchmark = _benchmark_retornos_mensuales(benchmark_resuelto, db, hoy)
    retornos_benchmark = _filtrar_desde(retornos_benchmark, desde)

    # Restricción a meses comunes (intersección)
    claves_comunes = sorted(set(retornos_cartera) & set(retornos_benchmark))
    if not claves_comunes:
        return {
            "estado": "datos_insuficientes",
            "moneda": moneda,
            "benchmark_usado": benchmark_resuelto,
            "periodo_desde": None,
            "periodo_hasta": None,
            "n_meses_historia": 0,
            "retorno_cartera_pct": None,
            "retorno_benchmark_pct": None,
            "delta_pp": None,
            "costo_oportunidad_pp": None,
            "exceso_retorno": {"estado": "datos_insuficientes", "valor": None, "n_obs": 0},
            "alpha": {"estado": "datos_insuficientes", "valor": None},
            "beta": {"estado": "datos_insuficientes", "valor": None, "n_obs": 0},
            "tracking_error": {"estado": "datos_insuficientes", "valor": None, "n_obs": 0},
            "information_ratio": {"estado": "datos_insuficientes", "valor": None, "n_obs": 0},
            "serie": [],
        }

    retornos_cartera_comunes = {k: retornos_cartera[k] for k in claves_comunes}
    retornos_benchmark_comunes = {k: retornos_benchmark[k] for k in claves_comunes}

    # Construir índices base-100 pareados
    indice_cartera = risk_engine.construir_indice(retornos_cartera_comunes, base=100.0)
    indice_benchmark = risk_engine.construir_indice(retornos_benchmark_comunes, base=100.0)

    # Retornos finales (últimos valores del índice)
    retorno_cartera_pct = (indice_cartera[-1][1] / 100.0) - 1 if indice_cartera else None
    retorno_benchmark_pct = (indice_benchmark[-1][1] / 100.0) - 1 if indice_benchmark else None

    # Diferencias
    delta_pp = (retorno_cartera_pct - retorno_benchmark_pct) * 100 if (retorno_cartera_pct is not None and retorno_benchmark_pct is not None) else None
    costo_oportunidad_pp = (retorno_benchmark_pct - retorno_cartera_pct) * 100 if (retorno_cartera_pct is not None and retorno_benchmark_pct is not None) else None

    # Métricas avanzadas
    retorno_anualizado_cartera = risk_engine.calcular_retorno_anualizado(indice_cartera)
    retorno_anualizado_benchmark = risk_engine.calcular_retorno_anualizado(indice_benchmark)
    beta = risk_engine.calcular_beta(retornos_cartera_comunes, retornos_benchmark_comunes)
    exceso_retorno = risk_engine.calcular_tracking_error(retornos_cartera_comunes, retornos_benchmark_comunes)
    alpha_result = risk_engine.calcular_alpha(retorno_anualizado_cartera, retorno_anualizado_benchmark, beta.get("valor"))
    ir = risk_engine.calcular_information_ratio(retornos_cartera_comunes, retornos_benchmark_comunes, benchmark_resuelto)

    # Serie pareada
    serie = []
    for (fecha_c, indice_c), (fecha_b, indice_b) in zip(indice_cartera, indice_benchmark):
        if fecha_c == fecha_b:  # Por construcción, deberían coincidir
            serie.append({"fecha": fecha_c, "indice_cartera": round(indice_c, 2), "indice_benchmark": round(indice_b, 2)})

    periodo_desde = claves_comunes[0] if claves_comunes else None
    periodo_desde_date = date(periodo_desde[0], periodo_desde[1], 1) if periodo_desde else None
    periodo_hasta = claves_comunes[-1] if claves_comunes else None
    periodo_hasta_date = date(periodo_hasta[0], periodo_hasta[1], 1) if periodo_hasta else None

    return {
        "estado": "ok",
        "moneda": moneda,
        "benchmark_usado": benchmark_resuelto,
        "periodo_desde": periodo_desde_date,
        "periodo_hasta": periodo_hasta_date,
        "n_meses_historia": len(claves_comunes),
        "retorno_cartera_pct": round(retorno_cartera_pct, 4) if retorno_cartera_pct is not None else None,
        "retorno_benchmark_pct": round(retorno_benchmark_pct, 4) if retorno_benchmark_pct is not None else None,
        "delta_pp": round(delta_pp, 2) if delta_pp is not None else None,
        "costo_oportunidad_pp": round(costo_oportunidad_pp, 2) if costo_oportunidad_pp is not None else None,
        "exceso_retorno": exceso_retorno,
        "alpha": alpha_result,
        "beta": beta,
        "tracking_error": exceso_retorno,
        "information_ratio": ir,
        "serie": serie,
    }
