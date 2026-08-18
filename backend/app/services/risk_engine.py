"""Motor puro de métricas de riesgo (drawdown, volatilidad, Sharpe, Sortino, Calmar, ...).

Sin dependencias de `Session`/DB/FastAPI: todas las funciones reciben series de retornos o
índices ya calculados y devuelven `dict`s planos. Esto lo hace testeable con `pytest` sin
fixtures de base de datos, y reutilizable para cualquier nivel (cartera, Consolidado, ticker)
que le pase una serie de retornos mensuales.

Supuestos documentados (ver también "Consideraciones" del pedido original):
- Frecuencia de observación: mensual, 12 períodos/año. Se reutiliza el TWR mensual encadenado
  ya existente en `inversiones_analytics._calcular_twr_mensual*` en vez de construir una serie
  diaria nueva (el proyecto no tiene una serie NAV diaria limpia ni numpy/scipy).
- Tratamiento de meses sin valuación (sin tenencia, `None` en el retorno mensual): se excluyen
  de la serie de retornos (no se tratan como 0%). El índice NAV se mantiene plano (no compone)
  durante esos meses.
- Volatilidad anualizada: `stdev_mensual * sqrt(12)`.
- Retorno anualizado (para Calmar): CAGR sobre el índice NAV completo,
  `(nav_final / nav_inicial) ** (12 / n_meses) - 1`, no una extrapolación de la media mensual.
- Desvío estándar: muestral (`statistics.stdev`, ddof=1), no poblacional.
- "Datos insuficientes": por debajo de los mínimos de observaciones definidos abajo, las
  métricas devuelven `estado: "datos_insuficientes"` con los valores numéricos en `None` en vez
  de un número que aparente ser válido.
"""
import math
import statistics
from datetime import date

PERIODOS_POR_ANIO = 12
MIN_OBS_DRAWDOWN = 2
MIN_OBS_VOLATILIDAD = 6


def construir_indice(retornos_por_mes: dict[tuple[int, int], float | None], base: float = 100.0) -> list[tuple[date, float]]:
    """Construye un índice NAV encadenando retornos mensuales, en orden cronológico.

    Los meses con retorno `None` (sin tenencia) mantienen el índice plano: no componen.
    La fecha asociada a cada punto es el fin de mes correspondiente.
    """
    indice: list[tuple[date, float]] = []
    valor = base
    for (anio, mes) in sorted(retornos_por_mes.keys()):
        retorno = retornos_por_mes[(anio, mes)]
        if retorno is not None:
            valor = valor * (1 + retorno)
        ultimo_dia = _ultimo_dia_mes(anio, mes)
        indice.append((ultimo_dia, valor))
    return indice


def _ultimo_dia_mes(anio: int, mes: int) -> date:
    import calendar
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def calcular_drawdown(indice: list[tuple[date, float]]) -> dict:
    """Drawdown actual y máximo sobre un índice NAV, con tiempo de recuperación.

    `tiempo_recuperacion_meses` es `None` si el drawdown máximo todavía no se recuperó.
    """
    if len(indice) < MIN_OBS_DRAWDOWN:
        return {
            "estado": "datos_insuficientes",
            "actual": None,
            "maximo": None,
            "fecha_pico": None,
            "fecha_valle": None,
            "en_recuperacion": None,
            "tiempo_recuperacion_meses": None,
        }

    pico_valor = indice[0][1]
    pico_fecha = indice[0][0]

    max_dd = 0.0
    max_dd_pico_valor = pico_valor
    max_dd_pico_fecha = pico_fecha
    max_dd_valle_fecha = pico_fecha
    max_dd_valle_idx = 0

    for i, (fecha, valor) in enumerate(indice):
        if valor > pico_valor:
            pico_valor = valor
            pico_fecha = fecha
        dd = valor / pico_valor - 1 if pico_valor > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            max_dd_pico_valor = pico_valor
            max_dd_pico_fecha = pico_fecha
            max_dd_valle_fecha = fecha
            max_dd_valle_idx = i

    ultimo_valor = indice[-1][1]
    dd_actual = ultimo_valor / pico_valor - 1 if pico_valor > 0 else 0.0

    tiempo_recuperacion_meses = None
    recuperado = False
    if max_dd < 0:
        for fecha, valor in indice[max_dd_valle_idx + 1:]:
            if valor >= max_dd_pico_valor:
                tiempo_recuperacion_meses = _meses_entre(max_dd_valle_fecha, fecha)
                recuperado = True
                break

    en_recuperacion = max_dd < 0 and not recuperado

    return {
        "estado": "ok",
        "actual": round(dd_actual, 4),
        "maximo": round(max_dd, 4),
        "fecha_pico": max_dd_pico_fecha,
        "fecha_valle": max_dd_valle_fecha,
        "en_recuperacion": en_recuperacion,
        "tiempo_recuperacion_meses": tiempo_recuperacion_meses,
    }


def _meses_entre(d0: date, d1: date) -> int:
    return (d1.year - d0.year) * 12 + (d1.month - d0.month)


def serie_drawdown(indice: list[tuple[date, float]]) -> list[dict]:
    """Serie completa de drawdown (valor / pico corriente - 1), para graficar la curva underwater."""
    resultado = []
    pico: float | None = None
    for fecha, valor in indice:
        if pico is None or valor > pico:
            pico = valor
        dd = valor / pico - 1 if pico else 0.0
        resultado.append({"fecha": fecha, "drawdown": round(dd, 4)})
    return resultado


def calcular_volatilidad(retornos: list[float]) -> dict:
    n = len(retornos)
    if n < MIN_OBS_VOLATILIDAD:
        return {"estado": "datos_insuficientes", "mensual": None, "anualizada": None, "n_obs": n}
    desvio_mensual = statistics.stdev(retornos)
    return {
        "estado": "ok",
        "mensual": round(desvio_mensual, 4),
        "anualizada": round(desvio_mensual * math.sqrt(PERIODOS_POR_ANIO), 4),
        "n_obs": n,
    }


def calcular_sharpe_vs_benchmark(
    retornos_por_mes: dict[tuple[int, int], float],
    retornos_benchmark_por_mes: dict[tuple[int, int], float],
    benchmark_nombre: str | None,
) -> dict:
    if not retornos_benchmark_por_mes or not benchmark_nombre:
        return {"estado": "sin_benchmark", "valor": None, "benchmark": benchmark_nombre, "n_obs": 0}

    excesos = [
        retornos_por_mes[k] - retornos_benchmark_por_mes[k]
        for k in sorted(set(retornos_por_mes) & set(retornos_benchmark_por_mes))
    ]
    n = len(excesos)
    if n < MIN_OBS_VOLATILIDAD:
        return {"estado": "datos_insuficientes", "valor": None, "benchmark": benchmark_nombre, "n_obs": n}

    desvio = statistics.stdev(excesos)
    if desvio == 0:
        return {"estado": "datos_insuficientes", "valor": None, "benchmark": benchmark_nombre, "n_obs": n}

    media = statistics.mean(excesos)
    sharpe = (media / desvio) * math.sqrt(PERIODOS_POR_ANIO)
    return {"estado": "ok", "valor": round(sharpe, 4), "benchmark": benchmark_nombre, "n_obs": n}


def calcular_tracking_error(
    retornos_por_mes: dict[tuple[int, int], float],
    retornos_benchmark_por_mes: dict[tuple[int, int], float],
) -> dict:
    """Desvío estándar anualizado del exceso de retorno mensual (cartera - benchmark)."""
    excesos = [
        retornos_por_mes[k] - retornos_benchmark_por_mes[k]
        for k in sorted(set(retornos_por_mes) & set(retornos_benchmark_por_mes))
    ]
    n = len(excesos)
    if n < MIN_OBS_VOLATILIDAD:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    desvio = statistics.stdev(excesos)
    return {"estado": "ok", "valor": round(desvio * math.sqrt(PERIODOS_POR_ANIO), 4), "n_obs": n}


def calcular_information_ratio(
    retornos_por_mes: dict[tuple[int, int], float],
    retornos_benchmark_por_mes: dict[tuple[int, int], float],
    benchmark_nombre: str | None,
) -> dict:
    """Ratio de información: media del exceso de retorno / tracking error, anualizado.

    Matemáticamente idéntico a `calcular_sharpe_vs_benchmark` (que ya usa el exceso sobre el
    benchmark, no una tasa libre de riesgo) — se reutiliza esa función en vez de recalcular la
    misma media/desvío por separado, sólo se reempaqueta el resultado.
    """
    sharpe = calcular_sharpe_vs_benchmark(retornos_por_mes, retornos_benchmark_por_mes, benchmark_nombre)
    return {"estado": sharpe["estado"], "valor": sharpe["valor"], "n_obs": sharpe["n_obs"]}


def calcular_beta(
    retornos_por_mes: dict[tuple[int, int], float],
    retornos_benchmark_por_mes: dict[tuple[int, int], float],
) -> dict:
    """Beta de la cartera respecto del benchmark: cov(cartera, benchmark) / var(benchmark)."""
    claves = sorted(set(retornos_por_mes) & set(retornos_benchmark_por_mes))
    n = len(claves)
    if n < MIN_OBS_VOLATILIDAD:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    cartera = [retornos_por_mes[k] for k in claves]
    benchmark = [retornos_benchmark_por_mes[k] for k in claves]
    varianza_benchmark = statistics.variance(benchmark)
    if varianza_benchmark == 0:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    covarianza = statistics.covariance(cartera, benchmark)
    return {"estado": "ok", "valor": round(covarianza / varianza_benchmark, 4), "n_obs": n}


def calcular_alpha(
    retorno_anualizado_cartera: float | None,
    retorno_anualizado_benchmark: float | None,
    beta: float | None,
) -> dict:
    """Alpha simple (tasa libre de riesgo = 0): cartera - beta * benchmark, ambos anualizados."""
    if retorno_anualizado_cartera is None or retorno_anualizado_benchmark is None or beta is None:
        return {"estado": "datos_insuficientes", "valor": None}
    return {"estado": "ok", "valor": round(retorno_anualizado_cartera - beta * retorno_anualizado_benchmark, 4)}


def calcular_sortino(retornos: list[float], mar: float = 0.0) -> dict:
    n = len(retornos)
    if n < MIN_OBS_VOLATILIDAD:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    bajo_mar = [r - mar for r in retornos if r < mar]
    if not bajo_mar:
        return {"estado": "ok", "valor": None, "n_obs": n}

    desvio_bajo = math.sqrt(sum(d * d for d in bajo_mar) / (n - 1))
    if desvio_bajo == 0:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    media = statistics.mean(r - mar for r in retornos)
    sortino = (media / desvio_bajo) * math.sqrt(PERIODOS_POR_ANIO)
    return {"estado": "ok", "valor": round(sortino, 4), "n_obs": n}


def calcular_retorno_anualizado(indice: list[tuple[date, float]]) -> float | None:
    """CAGR sobre el índice NAV completo. `None` si hay menos de 2 puntos o el rango es 0 meses."""
    if len(indice) < 2:
        return None
    nav_inicial = indice[0][1]
    nav_final = indice[-1][1]
    n_meses = _meses_entre(indice[0][0], indice[-1][0])
    if nav_inicial <= 0 or n_meses <= 0:
        return None
    return (nav_final / nav_inicial) ** (PERIODOS_POR_ANIO / n_meses) - 1


def calcular_calmar(retorno_anualizado: float | None, max_drawdown: float | None) -> dict:
    if retorno_anualizado is None or max_drawdown is None or max_drawdown == 0:
        return {"estado": "datos_insuficientes", "valor": None, "retorno_anualizado": retorno_anualizado}
    return {
        "estado": "ok",
        "valor": round(retorno_anualizado / abs(max_drawdown), 4),
        "retorno_anualizado": round(retorno_anualizado, 4),
    }


def mejores_peores_periodos(retornos_por_mes: dict[tuple[int, int], float], n: int = 3) -> dict:
    items = sorted(
        ({"anio": a, "mes": m, "retorno": round(r, 4)} for (a, m), r in retornos_por_mes.items()),
        key=lambda x: x["retorno"],
    )
    return {
        "mejores": list(reversed(items[-n:])) if items else [],
        "peores": items[:n],
    }


def frecuencia_positivos_negativos(retornos: list[float]) -> dict:
    n = len(retornos)
    if n < MIN_OBS_DRAWDOWN:
        return {"estado": "datos_insuficientes", "pct_positivos": None, "pct_negativos": None, "n_obs": n}
    positivos = sum(1 for r in retornos if r > 0)
    negativos = sum(1 for r in retornos if r < 0)
    return {
        "estado": "ok",
        "pct_positivos": round(positivos / n, 4),
        "pct_negativos": round(negativos / n, 4),
        "n_obs": n,
    }


def serie_retornos_mensuales_desde_niveles(
    niveles: list[tuple[date, float]], boundaries: list[date]
) -> dict[tuple[int, int], float]:
    """Convierte una serie de niveles diarios a retornos mensuales encadenados.

    Para cada mes de `boundaries`, toma el último nivel conocido (carry-forward) en cada fin de mes,
    encadena la variación porcentual mes a mes. Si un mes no tiene dato, se omite.

    Args:
        niveles: lista de (fecha, valor) ordenada cronológicamente
        boundaries: lista de fechas fin-de-mes (usualmente desde _fin_de_mes_range)

    Returns:
        dict[(año, mes), retorno_porcentual] — solo meses con al menos un dato anterior
    """
    if not niveles or not boundaries:
        return {}

    fechas = [v[0] for v in niveles]
    puntos: list[tuple[date, float]] = []

    for b in boundaries:
        idx = _bisect_right_carry_forward(fechas, b)
        if idx < 0:
            continue
        puntos.append((b, niveles[idx][1]))

    resultado: dict[tuple[int, int], float] = {}
    for i in range(1, len(puntos)):
        d0, v0 = puntos[i - 1]
        d1, v1 = puntos[i]
        if v0 == 0:
            continue
        resultado[(d1.year, d1.month)] = v1 / v0 - 1
    return resultado


def _bisect_right_carry_forward(fechas: list[date], fecha_buscada: date) -> int:
    """Busca el índice del último elemento en `fechas` que sea <= `fecha_buscada`.
    Retorna -1 si no hay ninguno (la búsqueda está antes de todas las fechas).
    """
    import bisect
    idx = bisect.bisect_right(fechas, fecha_buscada) - 1
    return idx
