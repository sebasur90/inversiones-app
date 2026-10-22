"""Evaluación de una posición existente: mantener, aumentar, reducir o salir. Puro: sin DB ni red.

Son **cuatro opciones para evaluar, no órdenes**. Cada una lista la evidencia a favor y en contra, cómo
cambiaría la cartera (con el simulador), qué condiciones deberían cumplirse y qué la invalidaría.

Reglas que no se negocian (hay tests):
- **El resultado de la posición (ganancia o pérdida) nunca es evidencia.** Describe el pasado y el precio de
  entrada; sirve para medir el rendimiento y estudiar el comportamiento, no para decidir. Que una posición esté
  en pérdida no empuja a salir, ni que el precio haya caído empuja a aumentar.
- Una caída de precio, sola, tampoco es evidencia: lo que cuenta son fundamentales, valoración, riesgo,
  concentración, la tesis original y las alternativas.
- Los textos describen; ninguno indica qué operación hacer.
"""
from __future__ import annotations

from . import evaluacion_engine as ev

VERSION_REGLAS = 1
MANTENER, AUMENTAR, REDUCIR, SALIR = "mantener", "aumentar", "reducir", "salir"
OPCIONES = (MANTENER, AUMENTAR, REDUCIR, SALIR)
NOMBRE = {MANTENER: "Mantener", AUMENTAR: "Aumentar", REDUCIR: "Reducir", SALIR: "Salir"}

# Montos con los que se simula cada opción, en fracción del valor actual de la posición.
FRACCION_SIMULADA = {AUMENTAR: 0.25, REDUCIR: -0.50, SALIR: -1.0}

FUNDAMENTOS_BUENOS, FUNDAMENTOS_DEBILES = 60.0, 35.0
VALORACION_ACOMPANA = 50.0
DETERIORO_PUNTOS = 15.0

NOTA_RESULTADO = ("El resultado de la posición (ganancia o pérdida) no se usa como argumento: describe lo que ya pasó y el "
                  "precio al que entraste, no lo que tiene más sentido hacer desde hoy.")

REGLA_OPCIONES = (
    f"fundamentos buenos ≥ {FUNDAMENTOS_BUENOS:.0f} y débiles < {FUNDAMENTOS_DEBILES:.0f} (puntaje de Fundamentales); la "
    f"valoración acompaña desde {VALORACION_ACOMPANA:.0f}; concentración con los umbrales de Salud de cartera por "
    f"emisor; la tesis se considera deteriorada si una dimensión bajó ≥ {DETERIORO_PUNTOS:.0f} puntos o apareció una "
    "bandera crítica desde la última decisión. El resultado (ganancia o pérdida) no entra"
)


def comparar_tesis(tesis: dict | None, evaluacion: dict) -> dict:
    """Qué cambió desde la última decisión guardada sobre este activo. `tesis` = evaluación congelada."""
    if not tesis:
        return {"existe": False, "deteriorada": False, "cambios": [], "banderas_nuevas": []}
    antes = {d["clave"]: d.get("puntaje") for d in tesis.get("dimensiones", [])}
    cambios = []
    for d in evaluacion["dimensiones"]:
        a, h = antes.get(d["clave"]), d["puntaje"]
        if a is None or h is None:
            continue
        if abs(h - a) >= 1:
            cambios.append({"dimension": d["clave"], "nombre": d["nombre"], "antes": a, "ahora": h, "delta": round(h - a, 1)})
    claves_antes = {b["clave"] for b in tesis.get("banderas", [])}
    nuevas = [b for b in evaluacion["banderas"] if b["clave"] not in claves_antes and b["severidad"] == ev.ALTA]
    deteriorada = any(c["delta"] <= -DETERIORO_PUNTOS for c in cambios) or bool(nuevas)
    return {"existe": True, "deteriorada": deteriorada, "cambios": cambios, "banderas_nuevas": nuevas}


def _cambio(sim: dict | None, emisor: str) -> dict | None:
    if not sim:
        return None
    eje = next((e for e in sim["ejes"] if e["eje"] == "Emisor"), None)
    fila = next((f for f in (eje or {}).get("items", []) if f["etiqueta"] == emisor), None)
    return {
        "peso_antes_pct": fila["antes_pct"] if fila else 0.0,
        "peso_despues_pct": fila["despues_pct"] if fila else 0.0,
        "liquidez_usd": sim.get("liquidez_usd", 0.0),
        "observaciones": [o for o in sim["observaciones"]],
        "comision_estimada_usd": sim.get("comision_estimada_usd"),
        "venta": (sim.get("ventas") or [None])[0],
    }


def _obs_niveles(sim: dict | None) -> set[str]:
    return {o["nivel"] for o in (sim or {}).get("observaciones", [])}


def evaluar_opciones(evaluacion: dict, emisor: str, peso_emisor_pct: float, umbrales: tuple[float, float],
                     sims: dict[str, dict | None], tesis: dict, alternativa_superior: str | None,
                     invalidacion_cumplida: list[str]) -> list[dict]:
    """`umbrales = (atencion, revisar)` de peso por emisor; `sims[opción]` = salida de `simular_operaciones`."""
    fund = ev.puntaje_de(evaluacion, ev.FUNDAMENTALES)
    val = ev.puntaje_de(evaluacion, ev.VALORACION)
    riesgo = ev.puntaje_de(evaluacion, ev.RIESGO)
    criticas = [b for b in evaluacion["banderas"] if b["severidad"] == ev.ALTA]
    atencion, revisar = umbrales
    concentrada = peso_emisor_pct >= atencion

    def _pct(v):
        return f"{v:.1f} %".replace(".", ",")

    opciones = []

    # --- Mantener ---
    af, ec = [], []
    if fund is not None and fund >= 50:
        af.append(f"Fundamentales sin deterioro (puntaje {fund:.0f}).")
    if tesis["existe"] and not tesis["deteriorada"]:
        af.append("La tesis de tu última decisión no muestra deterioro grande.")
    if not criticas:
        af.append("No hay banderas críticas.")
    if not concentrada:
        af.append(f"El emisor pesa {_pct(peso_emisor_pct)}, debajo del umbral de atención ({_pct(atencion)}).")
    if criticas:
        ec += [f"Bandera crítica: {b['texto']}" for b in criticas]
    if peso_emisor_pct >= revisar:
        ec.append(f"El emisor pesa {_pct(peso_emisor_pct)}, sobre el umbral de revisar ({_pct(revisar)}).")
    if tesis["deteriorada"]:
        ec.append("La tesis se deterioró desde tu última decisión.")
    if alternativa_superior:
        ec.append(f"{alternativa_superior} aparece como alternativa relativamente más atractiva con los mismos criterios.")
    ec += [f"Condición de invalidación cumplida: {t}" for t in invalidacion_cumplida]
    opciones.append({
        "clave": MANTENER, "nombre": NOMBRE[MANTENER], "a_favor": af, "en_contra": ec,
        "cambio_en_cartera": {"peso_antes_pct": peso_emisor_pct, "peso_despues_pct": peso_emisor_pct,
                              "liquidez_usd": 0.0, "observaciones": [], "comision_estimada_usd": 0.0, "venta": None},
        "condiciones": ["que los fundamentales y la solidez no se deterioren", "que el peso no pase el umbral de revisar"],
        "invalidaria": ["una bandera crítica nueva", "que la valoración pase a ser de las más caras sin mejora de fundamentos"],
    })

    # --- Aumentar ---
    af, ec = [], []
    obs_aum = _obs_niveles(sims.get(AUMENTAR))
    if val is not None and val >= VALORACION_ACOMPANA:
        af.append(f"La valoración no es exigente frente a sus pares (puntaje {val:.0f}).")
    if fund is not None and fund >= FUNDAMENTOS_BUENOS:
        af.append(f"Fundamentales buenos (puntaje {fund:.0f}).")
    if not ({ "revisar", "atencion"} & obs_aum):
        af.append("Con el monto simulado no aparece ninguna observación de concentración.")
    if val is not None and val < ev.VALORACION_EXIGENTE:
        ec.append(f"Valoración exigente frente a sus pares (puntaje {val:.0f}).")
    if "revisar" in obs_aum or "atencion" in obs_aum:
        ec.append("Con el monto simulado la concentración pasaría un umbral de Salud de cartera.")
    if riesgo is not None and riesgo < ev.RIESGO_ELEVADO:
        ec.append(f"Riesgo histórico alto (puntaje {riesgo:.0f}).")
    ec += [f"Bandera crítica: {b['texto']}" for b in criticas]
    if alternativa_superior:
        ec.append(f"{alternativa_superior} aparece como alternativa relativamente más atractiva.")
    opciones.append({
        "clave": AUMENTAR, "nombre": NOMBRE[AUMENTAR], "a_favor": af, "en_contra": ec,
        "cambio_en_cartera": _cambio(sims.get(AUMENTAR), emisor),
        "condiciones": ["valoración que no sea exigente", f"que el emisor quede debajo de {_pct(atencion)} de la cartera"],
        "invalidaria": ["que la concentración pase el umbral de revisar", "una bandera crítica nueva"],
    })

    # --- Reducir ---
    af, ec = [], []
    if concentrada:
        af.append(f"Concentración: el emisor pesa {_pct(peso_emisor_pct)} (atención desde {_pct(atencion)}).")
    if val is not None and val < ev.VALORACION_EXIGENTE:
        af.append(f"Valoración exigente (puntaje {val:.0f}).")
    if tesis["deteriorada"]:
        af.append("Deterioro parcial de la tesis desde tu última decisión.")
    if fund is not None and fund < FUNDAMENTOS_DEBILES:
        af.append(f"Fundamentales débiles (puntaje {fund:.0f}).")
    if fund is not None and fund >= FUNDAMENTOS_BUENOS and (val is None or val >= VALORACION_ACOMPANA) and not concentrada:
        ec.append("Fundamentos buenos, valoración que acompaña y sin exceso de concentración.")
    ec.append("Lo liberado habría que reasignarlo o dejarlo líquido (ver la comparación con alternativas).")
    sim_red = sims.get(REDUCIR)
    if sim_red and sim_red.get("comision_estimada_usd"):
        ec.append(f"Costo estimado de la operación: {sim_red['comision_estimada_usd']:.2f} USD de comisión (sin impuestos).")
    opciones.append({
        "clave": REDUCIR, "nombre": NOMBRE[REDUCIR], "a_favor": af, "en_contra": ec,
        "cambio_en_cartera": _cambio(sim_red, emisor),
        "condiciones": ["un destino para lo liberado (alternativa o liquidez)", "que el motivo no sea sólo el precio al que entraste"],
        "invalidaria": ["que la concentración ya esté debajo del umbral", "una mejora clara de valoración o fundamentos"],
    })

    # --- Salir ---
    af, ec = [], []
    af += [f"Bandera crítica: {b['texto']}" for b in criticas]
    if fund is not None and fund < FUNDAMENTOS_DEBILES:
        af.append(f"Fundamentales débiles (puntaje {fund:.0f}).")
    if alternativa_superior:
        af.append(f"{alternativa_superior} aparece como alternativa relativamente más atractiva con los mismos criterios.")
    af += [f"Condición de invalidación cumplida: {t}" for t in invalidacion_cumplida]
    if fund is not None and fund >= 50 and not criticas:
        ec.append(f"Fundamentales sin deterioro (puntaje {fund:.0f}) y sin banderas críticas.")
    sim_salir = sims.get(SALIR)
    if sim_salir and sim_salir.get("comision_estimada_usd"):
        ec.append(f"Costo estimado: {sim_salir['comision_estimada_usd']:.2f} USD de comisión; impuestos no calculados.")
    else:
        ec.append("Costos de salida: impuestos no calculados.")
    if not alternativa_superior:
        ec.append("No hay una alternativa claramente superior: el capital quedaría líquido.")
    opciones.append({
        "clave": SALIR, "nombre": NOMBRE[SALIR], "a_favor": af, "en_contra": ec,
        "cambio_en_cartera": _cambio(sim_salir, emisor),
        "condiciones": ["un motivo de fondo (fundamentos, riesgo, estrategia o alternativa), no sólo el precio"],
        "invalidaria": ["que la bandera crítica se resuelva", "que la alternativa pierda su ventaja"],
    })

    for o in opciones:
        a, c = len(o["a_favor"]), len(o["en_contra"])
        o["balance"] = "mas_a_favor" if a > c else "mas_en_contra" if c > a else "mixta"
        o["regla"] = REGLA_OPCIONES
    return opciones
