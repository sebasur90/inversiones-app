"""Qué pasó con el rendimiento relativo de un grupo después de estar en cada estado del ciclo. Puro: sin DB ni red.

**Describe el pasado; no mide cuánto sirve el estado para anticipar nada.** Para cada semana en la que el grupo estaba
en un estado, se mira cuánto rindió contra su referencia en las `h` semanas siguientes (`h` = 4, 13 y 26) y se compara con
lo que pasó en *cualquier* semana. Sin esa base, un estado que «acierta» el 60 % de las veces no dice nada si el 60 % de
las semanas el grupo le ganaba a la referencia de todos modos.

Reglas que evitan engañarse:

- **Sin mirar el futuro.** El estado de una semana es el **confirmado** con los datos hasta esa semana (el cuadrante se
  sostuvo `CONFIRMACION_SEMANAS` semanas seguidas; una corrida más corta no cambia el estado, igual que en la pantalla).
  La rotación usa EMAs causales, así que lo que se cuenta es lo que se habría visto en ese momento.
- **Rendimiento relativo** = `(1 + r_grupo) / (1 + r_referencia) − 1` entre las dos mismas semanas = `RS[t+h] / RS[t] − 1`,
  en dólares (la moneda de la rotación).
- **Las semanas seguidas no son observaciones independientes**: con horizonte de 13 semanas, dos semanas contiguas comparten
  12 de 13. Por eso cada estado informa cuántos **episodios** distintos hay detrás (una racha continua en ese estado) y la
  muestra se declara insuficiente por episodios, no por semanas.
- **Al confirmarse** (la vista del aviso): sólo la semana en que el estado se confirma, un dato por episodio. Es lo que
  tenías a mano el día que llegó el aviso.
- Con pocos episodios (`MIN_EPISODIOS`) no se calcula ningún promedio: se informa cuántos hay y nada más.
"""
from __future__ import annotations

import statistics

from . import ciclos_engine as eng

HORIZONTES_SEMANAS = (4, 13, 26)
MIN_EPISODIOS = 5
MIN_SEMANAS_ANALISIS = 2 * eng.VENTANA_RRG + 8      # tras el calentamiento de las EMAs, algo de historia que mirar


def _percentil(ordenados: list[float], p: float) -> float:
    """Interpolación lineal entre los dos valores vecinos (`ordenados` no vacío)."""
    if len(ordenados) == 1:
        return ordenados[0]
    pos = p * (len(ordenados) - 1)
    i = int(pos)
    resto = pos - i
    return ordenados[i] if i + 1 >= len(ordenados) else ordenados[i] * (1 - resto) + ordenados[i + 1] * resto


def estadisticas(valores: list[float], episodios: int, minimo: int = MIN_EPISODIOS) -> dict:
    """Resumen de una lista de rendimientos relativos. Sin episodios suficientes sólo informa los conteos."""
    base = {"n": len(valores), "episodios": episodios, "suficiente": episodios >= minimo and len(valores) > 0}
    if not base["suficiente"]:
        return {**base, "mediana": None, "media": None, "p25": None, "p75": None, "positivos_pct": None}
    orden = sorted(valores)
    return {
        **base,
        "mediana": statistics.median(orden), "media": statistics.fmean(orden),
        "p25": _percentil(orden, 0.25), "p75": _percentil(orden, 0.75),
        "positivos_pct": 100.0 * sum(1 for v in orden if v > 0) / len(orden),
    }


def observaciones(
    a: eng.Serie, b: eng.Serie, clave: str, *, ventana: int = eng.VENTANA_RRG,
    confirmacion: int = eng.CONFIRMACION_SEMANAS, horizontes: tuple[int, ...] = HORIZONTES_SEMANAS,
) -> dict:
    """Una fila por semana con estado confirmado: `{fecha, cuadrante, episodio, confirma, fwd: {h: relativo}}`.

    Usa el último tramo continuo de semanas en común (igual que `ciclos_engine.rotacion`) e informa cuántas descartó.
    `clave` identifica al grupo para que los episodios no se confundan al juntar varios.
    """
    a, b = eng.normalizar(a), eng.normalizar(b)
    tramo, descartadas = eng.ultimo_tramo_continuo(eng.semanal_comun(a, b)) if a and b else ([], 0)
    base = {"clave": clave, "obs": [], "semanas": len(tramo), "semanas_descartadas": descartadas, "desde": None, "hasta": None}
    if len(tramo) < MIN_SEMANAS_ANALISIS + 2 * ventana:
        return {**base, "motivo": "pocas semanas continuas en común con la referencia"}

    puntos = eng.calcular_rrg(tramo, ventana)
    posicion = {f: i for i, (f, _, _) in enumerate(tramo)}
    rs = [x / y for _, x, y in tramo]

    confirmado, corrida, previo, episodio = None, 0, None, 0
    obs = []
    for p in puntos:
        q = p["cuadrante"]
        corrida = corrida + 1 if q == previo else 1
        previo = q
        confirma = False
        if corrida >= confirmacion and confirmado != q:
            if confirmado is not None:
                confirma = True              # el primer estado confirmado de la serie no es un cambio, es el punto de partida
            confirmado = q
            episodio += 1
        if confirmado is None:
            continue
        k = posicion[p["fecha"]]
        obs.append({
            "fecha": p["fecha"], "cuadrante": confirmado, "episodio": f"{clave}:{episodio}", "confirma": confirma,
            "fwd": {h: rs[k + h] / rs[k] - 1.0 for h in horizontes if k + h < len(rs)},
        })
    if not obs:
        return {**base, "motivo": "ningún estado llegó a confirmarse"}
    return {**base, "obs": obs, "desde": obs[0]["fecha"], "hasta": obs[-1]["fecha"], "motivo": None}


def resumir(todas: list[dict], horizontes: tuple[int, ...] = HORIZONTES_SEMANAS) -> dict:
    """Junta las observaciones de uno o varios grupos y las resume por estado, contra la base de todas las semanas."""
    obs = [o for t in todas for o in t["obs"]]

    def _por(filtro, h: int) -> dict:
        elegidas = [o for o in obs if filtro(o) and h in o["fwd"]]
        return estadisticas([o["fwd"][h] for o in elegidas], len({o["episodio"] for o in elegidas}))

    base = {h: _por(lambda o: True, h) for h in horizontes}
    estados = []
    for q in eng.CUADRANTES:
        propios = [o for o in obs if o["cuadrante"] == q]
        horiz, al_confirmar = {}, {}
        for h in horizontes:
            e = _por(lambda o, q=q: o["cuadrante"] == q, h)
            c = _por(lambda o, q=q: o["cuadrante"] == q and o["confirma"], h)
            for est in (e, c):
                est["mediana_vs_base"] = est["mediana"] - base[h]["mediana"] if est["suficiente"] and base[h]["mediana"] is not None else None
            horiz[h], al_confirmar[h] = e, c
        estados.append({
            "cuadrante": q, "semanas": len(propios), "episodios": len({o["episodio"] for o in propios}),
            "cambios_a_este_estado": sum(1 for o in propios if o["confirma"]),
            "horizontes": horiz, "al_confirmar": al_confirmar,
        })
    return {
        "horizontes_semanas": list(horizontes), "base": base, "por_estado": estados, "semanas_analizadas": len(obs),
        "desde": min((o["fecha"] for o in obs), default=None), "hasta": max((o["fecha"] for o in obs), default=None),
    }
