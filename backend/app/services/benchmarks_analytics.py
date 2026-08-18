"""Adaptador entre los datos reales (Session/DB) y las métricas de performance relativa.

Reúne la comparación de cartera contra benchmarks, normalizando la TWR mensual de ambos
a un rango común y computando métricas de relative performance (alpha, beta, tracking error,
information ratio).
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import BenchmarkValor, IndiceMercado, InstrumentoInversion, PrecioInstrumento
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
    _retornos_mensuales_ticker,
    get_configuracion_cartera,
)

MONEDAS_VALIDAS = ("ars_nominal", "ars_real", "usd")

BENCHMARK_DOLAR = "Dólar (MEP)"
BENCHMARK_INFLACION = "Inflación (CER)"
BENCHMARK_MONEDA_NATIVA = {"S&P 500": "usd"}


def _benchmark_retornos_mensuales(benchmark: str, db: Session, hasta: date) -> dict[tuple[int, int], float]:
    rows = (
        db.query(BenchmarkValor)
        .filter(BenchmarkValor.benchmark == benchmark)
        .order_by(BenchmarkValor.fecha)
        .all()
    )
    if not rows:
        return {}

    niveles = [(r.fecha, float(r.valor)) for r in rows]
    boundaries = _fin_de_mes_range(niveles[0][0], hasta)
    return risk_engine.serie_retornos_mensuales_desde_niveles(niveles, boundaries)


def _indice_mercado_retornos_mensuales(campo: str, db: Session, hasta: date) -> dict[tuple[int, int], float]:
    rows = (
        db.query(IndiceMercado)
        .filter(getattr(IndiceMercado, campo).isnot(None))
        .order_by(IndiceMercado.fecha)
        .all()
    )
    if not rows:
        return {}

    niveles = [(r.fecha, float(getattr(r, campo))) for r in rows]
    boundaries = _fin_de_mes_range(niveles[0][0], hasta)
    return risk_engine.serie_retornos_mensuales_desde_niveles(niveles, boundaries)


def _ticker_retornos_mensuales(ticker: str, db: Session, hasta: date) -> dict[tuple[int, int], float]:
    rows = (
        db.query(PrecioInstrumento)
        .filter(PrecioInstrumento.ticker == ticker)
        .order_by(PrecioInstrumento.fecha)
        .all()
    )
    if not rows:
        return {}

    niveles = [(r.fecha, float(r.precio)) for r in rows]
    boundaries = _fin_de_mes_range(niveles[0][0], hasta)
    return risk_engine.serie_retornos_mensuales_desde_niveles(niveles, boundaries)


def _resolver_fuente(nombre: str, db: Session, hasta: date) -> dict[tuple[int, int], float]:
    if nombre == BENCHMARK_DOLAR:
        return _indice_mercado_retornos_mensuales("mep", db, hasta)
    elif nombre == BENCHMARK_INFLACION:
        return _indice_mercado_retornos_mensuales("cer", db, hasta)
    elif db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == nombre).first():
        return _ticker_retornos_mensuales(nombre, db, hasta)
    else:
        return _benchmark_retornos_mensuales(nombre, db, hasta)


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
    return _performance_relativa_sobre_movs(movs, moneda, benchmark, desde, db)


def _performance_relativa_sobre_movs(movs: list, moneda: str, benchmark: str | None, desde: date | None, db: Session) -> dict:
    """Calcula performance relativa sobre una lista de movimientos ya filtrada."""
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}")

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


def get_performance_compare(
    cartera: str | None,
    moneda: str,
    desde: date | None,
    benchmarks: list[str] | None,
    tickers: list[str] | None,
    db: Session
) -> dict:
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}")

    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()

    retornos_cartera = _twr_mensual_por_moneda(moneda, movs, precios_por_ticker, db, mep_cache, cer_cache, hoy)
    retornos_cartera = _filtrar_desde(retornos_cartera, desde)
    indice_cartera_completo = risk_engine.construir_indice(retornos_cartera, base=100.0) if retornos_cartera else []

    fuentes = []
    if benchmarks:
        fuentes.extend(benchmarks)
    if tickers:
        fuentes.extend(tickers)

    if not fuentes:
        return {
            "estado": "sin_datos",
            "moneda": moneda,
            "periodo_desde": None,
            "periodo_hasta": None,
            "filas": [],
            "serie": [],
        }

    filas = []
    indices_by_fuente = {}
    fechas_globales = set(retornos_cartera.keys()) if retornos_cartera else set()

    for fuente in fuentes:
        retornos_fuente = _resolver_fuente(fuente, db, hoy)
        retornos_fuente = _filtrar_desde(retornos_fuente, desde)

        claves_comunes = sorted(set(retornos_cartera) & set(retornos_fuente)) if retornos_cartera and retornos_fuente else []

        if not claves_comunes:
            es_benchmark_virtual = fuente in (BENCHMARK_DOLAR, BENCHMARK_INFLACION)
            es_ticker = bool(db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == fuente).first())
            filas.append({
                "fuente": fuente,
                "tipo": "benchmark" if es_benchmark_virtual else ("ticker" if es_ticker else "benchmark"),
                "estado": "datos_insuficientes",
                "retorno_pct": None,
                "delta_pp": None,
                "valor_final_equivalente_usd": None,
                "valor_final_equivalente_ars": None,
                "ranking": None,
                "n_meses_historia": 0,
            })
            continue

        indice_fuente = risk_engine.construir_indice({k: retornos_fuente[k] for k in claves_comunes}, base=100.0)
        indices_by_fuente[fuente] = indice_fuente

        retorno_fuente_pct = (indice_fuente[-1][1] / 100.0) - 1 if indice_fuente else None
        retorno_cartera_pct = None
        if indice_cartera_completo:
            cartera_at_end = next((v for f, v in indice_cartera_completo if f == indice_fuente[-1][0]), None)
            if cartera_at_end:
                retorno_cartera_pct = (cartera_at_end / 100.0) - 1

        delta_pp = (retorno_cartera_pct - retorno_fuente_pct) * 100 if (retorno_cartera_pct is not None and retorno_fuente_pct is not None) else None

        fechas_globales.update(claves_comunes)

        es_benchmark_virtual = fuente in (BENCHMARK_DOLAR, BENCHMARK_INFLACION)
        es_ticker = bool(db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == fuente).first())
        filas.append({
            "fuente": fuente,
            "tipo": "benchmark" if es_benchmark_virtual else ("ticker" if es_ticker else "benchmark"),
            "estado": "ok",
            "retorno_pct": round(retorno_fuente_pct, 4) if retorno_fuente_pct is not None else None,
            "delta_pp": round(delta_pp, 2) if delta_pp is not None else None,
            "valor_final_equivalente_usd": None,
            "valor_final_equivalente_ars": None,
            "ranking": None,
            "n_meses_historia": len(claves_comunes),
        })

    filas_ok = [f for f in filas if f["estado"] == "ok"]
    if filas_ok:
        sorted_filas = sorted(filas_ok, key=lambda x: x["retorno_pct"] or float('-inf'), reverse=True)
        for i, fila in enumerate(sorted_filas, 1):
            for f in filas:
                if f["fuente"] == fila["fuente"]:
                    f["ranking"] = i
                    break

    serie = []
    for fecha_key in sorted(fechas_globales):
        punto = {"fecha": date(fecha_key[0], fecha_key[1], 1)}

        cartera_val = None
        for f, v in indice_cartera_completo:
            if f == punto["fecha"]:
                cartera_val = v
                break
        punto["cartera"] = round(cartera_val, 2) if cartera_val is not None else None

        for fuente, indice in indices_by_fuente.items():
            fuente_val = None
            for f, v in indice:
                if f == punto["fecha"]:
                    fuente_val = v
                    break
            punto[fuente] = round(fuente_val, 2) if fuente_val is not None else None

        serie.append(punto)

    periodo_desde = min(fechas_globales) if fechas_globales else None
    periodo_hasta = max(fechas_globales) if fechas_globales else None
    periodo_desde_date = date(periodo_desde[0], periodo_desde[1], 1) if periodo_desde else None
    periodo_hasta_date = date(periodo_hasta[0], periodo_hasta[1], 1) if periodo_hasta else None

    return {
        "estado": "ok" if filas_ok else "datos_insuficientes",
        "moneda": moneda,
        "periodo_desde": periodo_desde_date,
        "periodo_hasta": periodo_hasta_date,
        "filas": filas,
        "serie": serie,
    }
