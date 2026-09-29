"""Motor puro del comparador de estrategias: cálculos nuevos sobre resultados ya producidos por
`estrategia_engine.backtest` y `risk_engine`. Sin `Session`/DB — recibe curvas y operaciones ya
resueltas y devuelve `dict`s planos, para poder testear cada cuenta con valores a mano.

Nada de esto reimplementa el backtest: `estrategia_engine` sigue siendo la única fuente de
`curva_equity`/`curva_buy_hold`/métricas. Lo que vive acá es exactamente lo que
`estrategia_engine`/`risk_engine` no calculan: capital final, las tres formas de "diferencia"
(pp/monetaria/relativa), volatilidad de una curva de backtest (`risk_engine.calcular_volatilidad`
es de cartera, no de curva de equity), duración del drawdown en días y tramos de divergencia entre
dos curvas.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date

from . import risk_engine
from .inversiones_analytics import _fin_de_mes_range

CAPITAL_DEFAULT = 1_000_000.0
MAX_ESTRATEGIAS = 8
# Por debajo de esto, ni siquiera vale la pena mostrar métricas: dos o tres ruedas no describen
# nada. `estrategia_engine`/`risk_engine` ya tienen sus propios mínimos (operaciones cerradas,
# 6 meses de volatilidad); éste es el mínimo de la ventana completa para intentar comparar.
MIN_BARRAS_VENTANA = 20
MAX_PUNTOS_CURVA = 400
UMBRAL_DIVERGENCIA_PP = 2.0
MAX_TRAMOS_DIVERGENCIA = 5

DISCLAIMER_MEJOR = (
    "Según los datos históricos disponibles, esta fue la estrategia con mayor rendimiento en el "
    "período elegido. No es una recomendación: no garantiza que vaya a repetirse ni que sea la "
    "mejor forma de operar este instrumento de acá en adelante."
)


def dsl_sin_costos(dsl: dict) -> dict:
    """Copia del DSL con `comision_pct = 0.0`, para el toggle "Con costos / Sin costos": muestra
    cuánto de la diferencia contra la referencia viene de la comisión y no de la señal en sí."""
    copia = deepcopy(dsl)
    ejecucion = dict(copia.get("ejecucion") or {})
    ejecucion["comision_pct"] = 0.0
    copia["ejecucion"] = ejecucion
    return copia


def dinero(retorno_pct: float, capital: float) -> dict:
    """Capital final y ganancia en dinero de aplicar `retorno_pct` (base 100, como devuelve el
    motor) sobre `capital`."""
    capital_final = capital * (1 + retorno_pct / 100)
    return {"capital_final": round(capital_final, 2), "ganancia": round(capital_final - capital, 2)}


def diferencia(retorno_pct: float, retorno_ref_pct: float, capital: float) -> dict:
    """Las tres formas de comparar contra la referencia, sin confundirlas:

    - `pp`: resta simple de los dos retornos porcentuales (lo que "se siente" más intuitivo, pero
      no es una tasa: 10 pp de diferencia sobre 5% no es "el doble").
    - `monetaria`: esa misma resta, llevada a dinero con el capital inicial.
    - `relativa_pct`: cuánto más (o menos) creció un peso invertido en la estrategia respecto de
      uno invertido en la referencia — la única de las tres que sí es una tasa comparable entre sí.
    """
    pp = retorno_pct - retorno_ref_pct
    base_ref = 1 + retorno_ref_pct / 100
    relativa_pct = ((1 + retorno_pct / 100) / base_ref - 1) * 100 if base_ref != 0 else None
    return {
        "pp": round(pp, 4),
        "monetaria": round(capital * pp / 100, 2),
        "relativa_pct": round(relativa_pct, 4) if relativa_pct is not None else None,
    }


def volatilidad_curva(curva_ventana: list[tuple[date, float]]) -> dict:
    """Volatilidad anualizada de una curva de equity (base 100), en la misma convención que
    `/riesgo`: retornos mensuales encadenados (`risk_engine.serie_retornos_mensuales_desde_niveles`,
    el mismo puente que usa `/riesgo` para pasar de una serie diaria a retornos mensuales) +
    `risk_engine.calcular_volatilidad` (desvío mensual × √12), con el mismo mínimo de 6 meses.
    Nunca un número por debajo de ese mínimo: `estado` lo dice explícito.
    """
    if len(curva_ventana) < 2:
        return {"estado": "datos_insuficientes", "anualizada_pct": None, "n_obs": 0}
    boundaries = _fin_de_mes_range(curva_ventana[0][0], curva_ventana[-1][0])
    retornos_por_mes = risk_engine.serie_retornos_mensuales_desde_niveles(curva_ventana, boundaries)
    retornos = [retornos_por_mes[k] for k in sorted(retornos_por_mes)]
    resultado = risk_engine.calcular_volatilidad(retornos)
    if resultado["estado"] != "ok":
        return {"estado": "datos_insuficientes", "anualizada_pct": None, "n_obs": resultado["n_obs"]}
    return {"estado": "ok", "anualizada_pct": round(resultado["anualizada"] * 100, 4), "n_obs": resultado["n_obs"]}


def duracion_drawdown(curva_ventana: list[tuple[date, float]], fecha_pico: date | None, fecha_valle: date | None) -> dict:
    """Días entre el pico y el valle del máximo drawdown, y días entre el valle y la recuperación
    (`None` si todavía no se recuperó dentro de la ventana). `risk_engine.calcular_drawdown` da esas
    mismas fechas pero el tiempo de recuperación en meses enteros (pensado para retornos
    mensuales de cartera); acá se cuenta en días exactos sobre la curva diaria del backtest.
    """
    if fecha_pico is None or fecha_valle is None:
        return {"dias_caida": None, "dias_recuperacion": None, "recuperado": None}

    dias_caida = (fecha_valle - fecha_pico).days
    pico_valor = next((v for f, v in curva_ventana if f == fecha_pico), None)
    if pico_valor is None:
        return {"dias_caida": dias_caida, "dias_recuperacion": None, "recuperado": None}

    for fecha, valor in curva_ventana:
        if fecha > fecha_valle and valor >= pico_valor:
            return {"dias_caida": dias_caida, "dias_recuperacion": (fecha - fecha_valle).days, "recuperado": True}

    return {"dias_caida": dias_caida, "dias_recuperacion": None, "recuperado": False}


def submuestrear(fechas: list[date], curvas: dict[str, list[float | None]], max_puntos: int = MAX_PUNTOS_CURVA) -> tuple[list[date], dict[str, list[float | None]]]:
    """Reduce `fechas` (y cada curva de `curvas`, en paralelo) a lo sumo `max_puntos`, conservando
    siempre el primer y el último punto. El payload manda las fechas una sola vez y una curva por
    fila; submuestrear ambas con los mismos índices es lo que las mantiene alineadas."""
    n = len(fechas)
    if n <= max_puntos:
        return fechas, curvas
    paso = (n - 1) / (max_puntos - 1)
    indices = sorted({round(i * paso) for i in range(max_puntos)})
    indices[0] = 0
    indices[-1] = n - 1
    fechas_out = [fechas[i] for i in indices]
    curvas_out = {clave: [serie[i] for i in indices] for clave, serie in curvas.items()}
    return fechas_out, curvas_out


_CAMPOS_VELAS = {"apertura", "maximo", "minimo"}
_INDICADORES_VOLUMEN = {"OBV", "VOLUMEN_PROMEDIO"}


def _operandos_de_condicion(cond: dict):
    op = cond.get("op")
    if op in ("y", "o"):
        for hijo in cond.get("condiciones", []) or []:
            yield from _operandos_de_condicion(hijo)
    elif op == "no":
        yield from _operandos_de_condicion(cond.get("condicion") or {})
    elif op in ("mayor", "menor", "mayor_igual", "menor_igual", "cruce_arriba", "cruce_abajo"):
        for clave in ("izq", "der"):
            if clave in cond:
                yield cond[clave]
    elif op == "entre":
        for clave in ("valor", "minimo", "maximo"):
            if clave in cond:
                yield cond[clave]
    elif op in ("subiendo", "bajando"):
        if "operando" in cond:
            yield cond["operando"]


def _usa_campo(dsl: dict, campos: set[str]) -> bool:
    for clave in ("entrada", "salida"):
        cond = dsl.get(clave)
        if not cond:
            continue
        for operando in _operandos_de_condicion(cond):
            if isinstance(operando, dict) and operando.get("campo") in campos:
                return True
    return False


def advertencias_dsl_serie(dsl: dict, tiene_velas: bool, tiene_volumen: bool) -> list[str]:
    """`"requiere_velas"`/`"requiere_volumen"` si el DSL usa `{campo: apertura|maximo|minimo}` o
    `{campo: volumen}`/un indicador de volumen (OBV, VOLUMEN_PROMEDIO) sobre una serie que no los
    tiene: el motor degrada solo (usa el cierre, o el indicador devuelve `None`), pero el resultado
    no está midiendo lo que la estrategia promete."""
    advertencias = []
    if not tiene_velas and _usa_campo(dsl, _CAMPOS_VELAS):
        advertencias.append("requiere_velas")
    if not tiene_volumen and (
        _usa_campo(dsl, {"volumen"})
        or any(item.get("tipo") in _INDICADORES_VOLUMEN for item in dsl.get("indicadores", []) or [])
    ):
        advertencias.append("requiere_volumen")
    return advertencias


def _pct_invertido(operaciones: list[tuple[int, int]], i0: int, i1: int) -> float:
    """% de las barras `[i0, i1]` (índices relativos a la ventana) cubiertas por alguna operación
    `(indice_entrada, indice_salida)` — la salida ya resuelta a un índice concreto (última barra de
    la ventana si la posición sigue abierta). Se usa para explicar los tramos de divergencia sin una
    heurística aparte: es lo mismo que ya calculó el motor, sólo que acotado al tramo."""
    total = i1 - i0 + 1
    if total <= 0:
        return 0.0
    cubiertas = 0
    for entrada, salida in operaciones:
        lo, hi = max(entrada, i0), min(salida, i1)
        if hi >= lo:
            cubiertas += hi - lo + 1
    return round(min(cubiertas, total) / total * 100, 2)


def divergencias(
    fechas: list[date], curva_a: list[float], curva_b: list[float],
    operaciones_a: list[tuple[int, int]], operaciones_b: list[tuple[int, int]],
    umbral_pp: float = UMBRAL_DIVERGENCIA_PP, max_tramos: int = MAX_TRAMOS_DIVERGENCIA,
) -> list[dict]:
    """Tramos mensuales donde `curva_a` y `curva_b` (ambas base 100, misma ventana) se separaron al
    menos `umbral_pp` puntos porcentuales, con quién estaba invertido en cada uno. Se agrupa por mes
    calendario y se compara el ratio `a/b` entre el primer y el último punto del mes: son los tramos
    "donde las curvas se separaron", no un umbral sobre el nivel absoluto. Devuelve los
    `max_tramos` de mayor separación, no los primeros cronológicamente.
    """
    if len(fechas) < 2 or len(curva_a) != len(fechas) or len(curva_b) != len(fechas):
        return []

    grupos: dict[tuple[int, int], list[int]] = {}
    for i, f in enumerate(fechas):
        grupos.setdefault((f.year, f.month), []).append(i)

    tramos = []
    for clave in sorted(grupos):
        idxs = grupos[clave]
        i0, i1 = idxs[0], idxs[-1]
        if i0 == i1 or curva_b[i0] == 0 or curva_b[i1] == 0:
            continue
        ratio_i0 = curva_a[i0] / curva_b[i0]
        ratio_i1 = curva_a[i1] / curva_b[i1]
        if ratio_i0 == 0:
            continue
        delta_pp = (ratio_i1 / ratio_i0 - 1) * 100
        if abs(delta_pp) < umbral_pp:
            continue
        tramos.append({
            "desde": fechas[i0], "hasta": fechas[i1], "delta_pp": round(delta_pp, 4),
            "invertida_pct": _pct_invertido(operaciones_a, i0, i1),
            "invertida_referencia_pct": _pct_invertido(operaciones_b, i0, i1),
        })

    tramos.sort(key=lambda t: abs(t["delta_pp"]), reverse=True)
    return tramos[:max_tramos]
