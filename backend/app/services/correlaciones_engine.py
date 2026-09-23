"""Motor puro de la pantalla "Matriz de correlaciones".

Sin dependencias de `Session`/DB/FastAPI: reutiliza `contribucion_engine.calcular_correlacion_par`
(el Pearson calculado a mano, ver docstring de ese módulo) y agrega lo que esa pantalla no
necesita pero ésta sí: `min_obs` variable por frecuencia, cobertura por par, motivo desagregado
del "datos_insuficientes", ranking de pares y advertencias en español.

No se extiende `contribucion_engine.construir_matriz_correlacion` porque su forma de retorno
calza 1:1 con el schema `CorrelacionesOut` ya en producción (pantalla Contribución): agregarle
campos nuevos obligaría a tocar ese contrato o a bifurcar su comportamiento con un flag. Acá se
reimplementa sólo el ensamblado de la matriz, reutilizando la única parte matemática real
(`calcular_correlacion_par`) tal cual está.
"""
from . import contribucion_engine
from .contribucion_engine import ClaveSerie

# 6 observaciones mensuales es el criterio que ya usa el resto del proyecto
# (`contribucion_engine.MIN_OBS_CORRELACION`, alineado con `risk_engine.MIN_OBS_VOLATILIDAD`).
# Para diaria/semanal 6 observaciones son ruido: 20 ruedas ≈ un mes de mercado, 12 semanas ≈ un
# trimestre. Son puntos de partida razonables, no un test estadístico formal; están expuestos como
# `min_obs` overrideable en el endpoint.
MIN_OBS_POR_FRECUENCIA = {"diaria": 20, "semanal": 12, "mensual": contribucion_engine.MIN_OBS_CORRELACION}

# Si más de esta fracción de los pares no llega a `min_obs`, se enciende `pocos_datos` para que
# el frontend muestre un aviso único sin inspeccionar cada celda. Estrictamente mayor a la mitad,
# igual que `construir_matriz_correlacion.advertencia_historial_corto`.
UMBRAL_POCOS_DATOS = 0.5

TOP_RANKING = 5


def _motivo(resultado: dict, min_obs: int) -> str:
    """Desagrega el `estado == "datos_insuficientes"` de `calcular_correlacion_par` en un motivo
    legible, derivándolo de lo que esa función ya devuelve (no la modifica)."""
    if resultado["estado"] == "ok":
        return "ok"
    if resultado["n_obs"] == 0:
        return "sin_solapamiento"
    if resultado["n_obs"] < min_obs:
        return "menos_de_min_obs"
    return "serie_constante"  # n_obs >= min_obs pero alguna varianza ~0


def construir_matriz(
    tickers: list[str],
    series_por_ticker: dict[str, dict[ClaveSerie, float]],
    min_obs: int,
    n_periodos_posibles: int,
) -> dict:
    """Matriz simétrica de correlación entre `tickers`, en el orden dado, con metadata de
    cobertura y motivo por par. `n_periodos_posibles` es el máximo teórico de observaciones
    solapadas (para expresar `solapamiento_pct`); si es 0, ese campo queda en `None`."""
    n = len(tickers)
    matriz: list[list[float | None]] = [[None] * n for _ in range(n)]
    pares: list[dict] = []
    n_pares = 0
    n_pares_ok = 0
    n_pares_insuficientes = 0
    suma_correlaciones = 0.0

    for i, ticker_a in enumerate(tickers):
        for j, ticker_b in enumerate(tickers):
            if j < i:
                continue
            if i == j:
                matriz[i][j] = 1.0
                continue
            resultado = contribucion_engine.calcular_correlacion_par(
                series_por_ticker.get(ticker_a, {}), series_por_ticker.get(ticker_b, {}), min_obs
            )
            matriz[i][j] = resultado["valor"]
            matriz[j][i] = resultado["valor"]
            solapamiento_pct = (
                round(resultado["n_obs"] / n_periodos_posibles * 100, 1) if n_periodos_posibles > 0 else None
            )
            pares.append({
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "valor": resultado["valor"],
                "n_obs": resultado["n_obs"],
                "solapamiento_pct": solapamiento_pct,
                "estado": resultado["estado"],
                "motivo": _motivo(resultado, min_obs),
            })
            n_pares += 1
            if resultado["estado"] == "ok":
                n_pares_ok += 1
                suma_correlaciones += resultado["valor"]
            else:
                n_pares_insuficientes += 1

    correlacion_promedio = round(suma_correlaciones / n_pares_ok, 4) if n_pares_ok > 0 else None
    pocos_datos = n_pares > 0 and (n_pares_insuficientes / n_pares) > UMBRAL_POCOS_DATOS

    return {
        "matriz": matriz,
        "pares": pares,
        "n_pares": n_pares,
        "n_pares_ok": n_pares_ok,
        "n_pares_insuficientes": n_pares_insuficientes,
        "correlacion_promedio": correlacion_promedio,
        "pocos_datos": pocos_datos,
    }


def rankear_pares(pares: list[dict], top: int = TOP_RANKING) -> dict:
    """Tres recortes de los pares con `estado == "ok"`, para "qué se mueve parecido / qué
    diversifica / qué se cubre"."""
    pares_ok = [p for p in pares if p["estado"] == "ok" and p["valor"] is not None]

    mas_correlacionados = sorted(pares_ok, key=lambda p: -p["valor"])[:top]
    menos_correlacionados = sorted(pares_ok, key=lambda p: abs(p["valor"]))[:top]
    negativos = [p for p in pares_ok if p["valor"] < 0]
    mas_negativos = sorted(negativos, key=lambda p: p["valor"])[:top]

    return {
        "mas_correlacionados": mas_correlacionados,
        "menos_correlacionados": menos_correlacionados,
        "mas_negativos": mas_negativos,
    }


def construir_advertencias(
    frecuencia: str,
    min_obs: int,
    n_pares: int,
    n_pares_insuficientes: int,
    tickers_descartados: list[dict],
    n_periodos: int,
    recortado: bool,
) -> list[str]:
    """Advertencias en español, listas para mostrar. La nota de que correlación no implica
    causalidad NO va acá: no es condicional a los datos, se muestra siempre en la pantalla."""
    advertencias: list[str] = []

    if n_pares > 0 and n_pares_insuficientes > 0:
        palabra_frec = {"diaria": "diarias", "semanal": "semanales", "mensual": "mensuales"}[frecuencia]
        advertencias.append(
            f"{n_pares_insuficientes} de {n_pares} pares no tienen suficientes datos solapados: "
            f"hacen falta al menos {min_obs} observaciones {palabra_frec}."
        )
        if frecuencia == "diaria":
            advertencias.append(
                "Con frecuencia diaria varios instrumentos no tienen precio cargado todos los "
                "días hábiles. Probá con semanal o mensual para tener más datos."
            )

    if tickers_descartados:
        lista = ", ".join(d["ticker"] for d in tickers_descartados)
        advertencias.append(f"No se incluyeron {len(tickers_descartados)} instrumento(s): {lista}.")

    if recortado:
        advertencias.append(
            f"El período se recortó a los últimos {n_periodos} puntos para no exceder el límite de cálculo."
        )

    if frecuencia == "mensual":
        advertencias.append("El mes en curso no se incluye: sólo se usan meses completos.")

    return advertencias


def nivel_diversificacion(correlacion_promedio: float | None) -> str | None:
    """Lectura rápida de la correlación promedio de la cartera. Umbrales de esta pantalla
    (no replican ningún corte del backend de riesgo)."""
    if correlacion_promedio is None:
        return None
    if correlacion_promedio >= 0.7:
        return "baja"
    if correlacion_promedio >= 0.4:
        return "media"
    return "alta"
