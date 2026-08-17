"""Motor puro de contribución, concentración (HHI) y correlación entre activos.

Sin dependencias de `Session`/DB/FastAPI: todas las funciones reciben pesos o series de
retornos ya calculados y devuelven `dict`s planos. Mismo criterio que `risk_engine.py`:
testeable con `pytest` sin fixtures de base de datos.

Supuestos documentados:
- HHI: se calcula sobre pesos porcentuales (escala 0-100, igual que `ExposicionItem.porcentaje`
  en `inversiones_analytics._agrupar`), dando un índice en escala 0-10000 (convención estándar
  de concentración de mercado). `hhi_normalizado` (0-1) y `effective_n` (1/hhi_normalizado,
  "cuántas posiciones iguales equivalen a esta concentración") se derivan del mismo cálculo.
- Correlación: coeficiente de Pearson calculado a mano (sin numpy/scipy, igual que
  `risk_engine.py`) sobre la intersección de meses con retorno conocido en ambas series.
  `MIN_OBS_CORRELACION = 6` coincide a propósito con `risk_engine.MIN_OBS_VOLATILIDAD`: es el
  mínimo de observaciones mensuales que el resto del proyecto ya considera necesario antes de
  confiar en una métrica estadística sobre retornos mensuales.
- "Datos insuficientes": igual que `risk_engine.py`, se devuelve `estado: "datos_insuficientes"`
  con los valores numéricos en `None` en vez de un número que aparente ser válido.
"""
import math
import statistics

EPS = 1e-9
MIN_OBS_CORRELACION = 6  # igual a risk_engine.MIN_OBS_VOLATILIDAD


def calcular_hhi(pesos_pct: list[float]) -> dict:
    """HHI = Σ(peso%)², sobre pesos ya expresados en escala 0-100."""
    pesos = [p for p in pesos_pct if p is not None]
    if not pesos:
        return {"estado": "sin_datos", "hhi": None, "hhi_normalizado": None, "n_componentes": 0, "effective_n": None}

    hhi = sum(p * p for p in pesos)
    hhi_normalizado = hhi / 10000
    effective_n = (1 / hhi_normalizado) if hhi_normalizado > EPS else None

    return {
        "estado": "ok",
        "hhi": round(hhi, 2),
        "hhi_normalizado": round(hhi_normalizado, 6),
        "n_componentes": len(pesos),
        "effective_n": round(effective_n, 2) if effective_n is not None else None,
    }


def calcular_correlacion_par(
    retornos_x: dict[tuple[int, int], float],
    retornos_y: dict[tuple[int, int], float],
    min_obs: int = MIN_OBS_CORRELACION,
) -> dict:
    """Pearson sobre la intersección de meses (año, mes) presentes en ambas series."""
    claves_comunes = sorted(set(retornos_x) & set(retornos_y))
    n = len(claves_comunes)
    if n < min_obs:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    xs = [retornos_x[k] for k in claves_comunes]
    ys = [retornos_y[k] for k in claves_comunes]
    media_x = statistics.mean(xs)
    media_y = statistics.mean(ys)

    cov = sum((x - media_x) * (y - media_y) for x, y in zip(xs, ys))
    var_x = sum((x - media_x) ** 2 for x in xs)
    var_y = sum((y - media_y) ** 2 for y in ys)

    if var_x <= EPS or var_y <= EPS:
        return {"estado": "datos_insuficientes", "valor": None, "n_obs": n}

    correlacion = cov / math.sqrt(var_x * var_y)
    correlacion = max(-1.0, min(1.0, correlacion))  # recorte por error de punto flotante
    return {"estado": "ok", "valor": round(correlacion, 4), "n_obs": n}


def construir_matriz_correlacion(
    tickers: list[str],
    series_por_ticker: dict[str, dict[tuple[int, int], float]],
    min_obs: int = MIN_OBS_CORRELACION,
) -> dict:
    """Matriz simétrica de correlación entre `tickers`, en el orden dado.

    `advertencia_historial_corto` se enciende cuando más de la mitad de los pares no
    alcanzan `min_obs` meses solapados, para que el frontend pueda mostrar un aviso único
    sin inspeccionar cada celda.
    """
    n = len(tickers)
    matriz: list[list[float | None]] = [[None] * n for _ in range(n)]
    pares = []
    n_pares = 0
    n_insuficientes = 0

    for i, ticker_a in enumerate(tickers):
        for j, ticker_b in enumerate(tickers):
            if j < i:
                continue
            if i == j:
                matriz[i][j] = 1.0
                continue
            resultado = calcular_correlacion_par(
                series_por_ticker.get(ticker_a, {}), series_por_ticker.get(ticker_b, {}), min_obs
            )
            matriz[i][j] = resultado["valor"]
            matriz[j][i] = resultado["valor"]
            pares.append({
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "valor": resultado["valor"],
                "n_obs": resultado["n_obs"],
                "estado": resultado["estado"],
            })
            n_pares += 1
            if resultado["estado"] != "ok":
                n_insuficientes += 1

    advertencia = n_pares > 0 and (n_insuficientes / n_pares) > 0.5

    return {
        "tickers": tickers,
        "n_tickers": n,
        "matriz": matriz,
        "pares": pares,
        "advertencia_historial_corto": advertencia,
    }
