"""Revisión de una decisión guardada: qué cambió entre la foto de ese día y el análisis de hoy. Puro.

Compara la **foto inicial congelada** (`DecisionSnapshot` tipo `inicial`) con el análisis recalculado ahora. No
reconstruye el pasado con datos de hoy y no pisa nada: el resultado es una fila nueva (`DecisionRevision`).

Lo determinista se resuelve acá (precio, índice, alternativas, condiciones de precio, dimensiones, banderas). Lo
que no tiene dato queda "a tu juicio" para que el usuario lo marque. El resultado de la inversión sólo se informa
si el usuario marcó la decisión como ejecutada, y es una aproximación por precio (el resultado exacto, con
cantidades y comisiones, está en Posiciones).
"""
from __future__ import annotations

from datetime import date

VERSION_REGLAS = 1
DETERIORO_PUNTOS = 15.0
VALORACION_EXIGENTE = 35.0


def _var(a: float | None, b: float | None) -> float | None:
    return b / a - 1.0 if a and b and a > 0 else None


def _dims(evaluacion: dict | None) -> dict[str, dict]:
    return {d["clave"]: d for d in (evaluacion or {}).get("dimensiones", [])}


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def condiciones_cumplidas(condiciones: list[dict], precio_actual: float | None, moneda_actual: str | None,
                          evaluacion_actual: dict | None) -> list[dict]:
    """Cada condición de invalidación con `cumplida` True/False/None (None = no se puede evaluar)."""
    dims = _dims(evaluacion_actual)
    salida = []
    for c in condiciones or []:
        estado = None
        if c.get("tipo") == "precio_bajo":
            valor = _num(c.get("valor"))
            if valor is not None and precio_actual is not None and (c.get("moneda") in (None, moneda_actual)):
                estado = precio_actual <= valor
        elif c.get("tipo") == "precio_sobre":
            valor = _num(c.get("valor"))
            if valor is not None and precio_actual is not None and (c.get("moneda") in (None, moneda_actual)):
                estado = precio_actual >= valor
        elif c.get("tipo") == "dimension":
            p = (dims.get(c.get("dimension")) or {}).get("puntaje")
            umbral = _num(c.get("umbral"))
            if p is not None and umbral is not None:
                estado = p < umbral
        salida.append({**c, "cumplida": estado})
    return salida


def comparar(decision: dict, inicial: dict, actual: dict, precio_actual: float | None, moneda_actual: str | None,
             bench: dict | None, alternativas_actuales: dict[str, float | None], volatilidad_observada: float | None,
             movimientos_posteriores: list[dict], hoy: date) -> dict:
    """`decision` = fila de la decisión como dict; `inicial`/`actual` = payloads del análisis (inicial congelado,
    actual recalculado). `bench = {simbolo, nombre, inicio, fin}` o None. `alternativas_actuales = {ticker: precio}`.
    """
    ev0, ev1 = inicial.get("evaluacion") or {}, actual.get("evaluacion") or {}
    d0, d1 = _dims(ev0), _dims(ev1)
    dimensiones = []
    for clave, a in d0.items():
        b = d1.get(clave) or {}
        pa, pb = a.get("puntaje"), b.get("puntaje")
        dimensiones.append({
            "dimension": clave, "nombre": a.get("nombre"), "antes": pa, "ahora": pb,
            "delta": round(pb - pa, 1) if pa is not None and pb is not None else None,
        })
    b0 = {b["clave"]: b for b in ev0.get("banderas", [])}
    b1 = {b["clave"]: b for b in ev1.get("banderas", [])}
    nuevas = [b for k, b in b1.items() if k not in b0]
    resueltas = [b for k, b in b0.items() if k not in b1]

    precio_ref = _num(decision.get("precio_ref"))
    moneda_ref = decision.get("moneda")
    misma_moneda = moneda_ref is None or moneda_actual is None or moneda_ref == moneda_actual
    var_precio = _var(precio_ref, precio_actual) if misma_moneda else None
    var_bench = _var((bench or {}).get("inicio"), (bench or {}).get("fin"))

    alternativas = []
    for alt in decision.get("alternativas", []):
        if alt.get("rol") == "elegida" and alt.get("ticker") == decision.get("ticker_base"):
            continue
        p0, p1 = _num(alt.get("precio_ref")), alternativas_actuales.get(alt.get("ticker"))
        alternativas.append({"ticker": alt.get("ticker"), "rol": alt.get("rol"), "precio_ref": p0, "precio_actual": p1,
                             "variacion": _var(p0, p1), "moneda": alt.get("moneda")})

    condiciones = condiciones_cumplidas((decision.get("condiciones") or {}).get("invalidacion", []),
                                        precio_actual, moneda_actual, ev1)

    supuestos = []
    f0, f1 = (d0.get("fundamentales") or {}).get("puntaje"), (d1.get("fundamentales") or {}).get("puntaje")
    if f0 is not None and f1 is not None:
        supuestos.append({"supuesto": "Los fundamentales se mantienen", "antes": f0, "ahora": f1,
                          "estado": "refutado" if f1 <= f0 - DETERIORO_PUNTOS else "confirmado",
                          "regla": f"refutado si Fundamentales bajó {DETERIORO_PUNTOS:.0f} puntos o más"})
    else:
        supuestos.append({"supuesto": "Los fundamentales se mantienen", "antes": f0, "ahora": f1, "estado": "sin_dato",
                          "regla": "hace falta el puntaje de Fundamentales en las dos fechas"})
    v1 = (d1.get("valoracion") or {}).get("puntaje")
    supuestos.append({"supuesto": "La valoración no se vuelve exigente", "antes": (d0.get("valoracion") or {}).get("puntaje"),
                      "ahora": v1, "estado": "sin_dato" if v1 is None else ("refutado" if v1 < VALORACION_EXIGENTE else "confirmado"),
                      "regla": f"refutado si Valoración < {VALORACION_EXIGENTE:.0f}"})
    entrada = (decision.get("condiciones") or {}).get("entrada") or {}
    if _num(entrada.get("precio")) is not None:
        alcanzada = None
        if precio_actual is not None and entrada.get("moneda") in (None, moneda_actual):
            alcanzada = precio_actual <= _num(entrada["precio"])
        supuestos.append({"supuesto": f"Condición de entrada: {entrada.get('texto') or 'precio de entrada'}",
                          "antes": _num(entrada["precio"]), "ahora": precio_actual,
                          "estado": "sin_dato" if alcanzada is None else ("confirmado" if alcanzada else "pendiente"),
                          "regla": "el precio actual está en el nivel de entrada o por debajo (sólo mira el precio de hoy)"})
    for texto in (inicial.get("conclusion") or {}).get("respuestas", {}).get("invalidaria", [])[:2]:
        supuestos.append({"supuesto": f"No ocurre: {texto}", "antes": None, "ahora": None, "estado": "a_tu_juicio",
                          "regla": "no hay un dato que lo resuelva solo: lo evaluás vos"})

    vol_ref = _num(decision.get("volatilidad_ref"))
    riesgo = {
        "volatilidad_al_decidir": vol_ref, "volatilidad_observada": volatilidad_observada,
        "texto": None,
    }
    if vol_ref and volatilidad_observada:
        r = volatilidad_observada / vol_ref
        riesgo["texto"] = ("La volatilidad desde la decisión fue mayor que la histórica que se veía" if r > 1.25
                           else "La volatilidad desde la decisión fue menor que la histórica que se veía" if r < 0.8
                           else "La volatilidad desde la decisión fue parecida a la histórica")

    resultado = None
    if decision.get("ejecutada") and var_precio is not None:
        resultado = {"variacion_precio": var_precio, "contra_indice": (var_precio - var_bench) if var_bench is not None else None,
                     "nota": "Aproximación por precio desde la fecha de la decisión; el resultado exacto está en Posiciones."}
    sugerencia = None
    if not decision.get("ejecutada") and movimientos_posteriores:
        sugerencia = (f"Hay {len(movimientos_posteriores)} movimiento(s) de este activo desde la decisión: si la llevaste a "
                      "cabo, marcala como ejecutada.")

    creada = decision.get("creada_en")
    dias = (hoy - (creada.date() if hasattr(creada, "date") else date.fromisoformat(str(creada)[:10]))).days if creada else None
    return {
        "version_reglas": VERSION_REGLAS,
        "dias": dias,
        "orden": {"antes": (ev0.get("orden") or {}).get("puntaje"), "ahora": (ev1.get("orden") or {}).get("puntaje")},
        "conclusion": {"antes": (inicial.get("conclusion") or {}).get("titulo"), "ahora": (actual.get("conclusion") or {}).get("titulo"),
                       "tipo_antes": (inicial.get("conclusion") or {}).get("tipo"), "tipo_ahora": (actual.get("conclusion") or {}).get("tipo")},
        "dimensiones": dimensiones,
        "banderas_nuevas": nuevas,
        "banderas_resueltas": resueltas,
        "precio": {"referencia": precio_ref, "actual": precio_actual, "moneda": moneda_ref, "moneda_actual": moneda_actual,
                   "fecha_referencia": decision.get("fecha_precio"), "variacion": var_precio,
                   "nota": None if misma_moneda else "la referencia y el precio de hoy están en monedas distintas: no se comparan"},
        "benchmark": {**(bench or {}), "variacion": var_bench} if bench else None,
        "alternativas": alternativas,
        "condiciones": condiciones,
        "supuestos": supuestos,
        "riesgo": riesgo,
        "resultado": resultado,
        "movimientos_posteriores": movimientos_posteriores,
        "sugerencia": sugerencia,
        "salvedad": ("Compara lo que la app decía ese día con lo que dice hoy. Una buena decisión puede salir mal y una "
                     "mala salir bien: mirá el proceso, no sólo el precio."),
    }
