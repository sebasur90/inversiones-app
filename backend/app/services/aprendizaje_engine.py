"""Aprendizaje sobre el propio proceso de decisión. Puro: calculado en cada pedido, no se persiste.

Busca patrones en las decisiones guardadas, sus revisiones y las operaciones reales (el diario de operaciones). El
foco es la **calidad del proceso** (¿definiste cómo invalidar la idea?, ¿la revisaste?, ¿seguiste tu estrategia?),
no sólo si una operación ganó o perdió.

Muestra mínima, sin excepciones:
- menos de `MIN_DESCRIPTIVO` casos → no se dice nada (sólo "evidencia insuficiente");
- de `MIN_DESCRIPTIVO` a `MIN_REPETIDO − 1` → "patrón descriptivo";
- desde `MIN_REPETIDO` → "patrón repetido".
Nunca se habla de significancia estadística ni de un sesgo psicológico: con decenas de casos lo honesto es
describir lo que se repite, no diagnosticar.
"""
from __future__ import annotations

from datetime import date

MIN_DESCRIPTIVO = 3
MIN_REPETIDO = 10
DESVIO_ACCIONES = {"entrar_ahora", "escalonada", "aumentar"}
CONCLUSIONES_DESFAVORABLES = {"riesgo_elevado", "valoracion_exigente", "datos_insuficientes"}


def _tono(n: int) -> str | None:
    if n < MIN_DESCRIPTIVO:
        return None
    return "patron_repetido" if n >= MIN_REPETIDO else "patron_descriptivo"


def _patron(clave: str, titulo: str, k: int, n: int, texto: str, regla: str, foco: str = "proceso") -> dict:
    tono = _tono(n)
    return {
        "clave": clave, "titulo": titulo, "casos": k, "muestra": n, "tono": tono or "insuficiente",
        "texto": texto if tono else f"Evidencia insuficiente: {n} caso(s), hacen falta al menos {MIN_DESCRIPTIVO}.",
        "regla": regla, "foco": foco,
    }


def patrones(decisiones: list[dict], revisiones: list[dict], diario: dict | None, hoy: date) -> dict:
    """`decisiones`: dicts con accion_elegida, conclusion.tipo, ejecutada, revisar_el, condiciones, calidad,
    banderas_altas, concentracion_revisar, favorable_pct, id. `revisiones`: dicts con decision_id, comparacion."""
    salida = []
    n = len(decisiones)

    # 1. Revisiones a tiempo
    vencidas = [d for d in decisiones if d.get("revisar_el") and d["revisar_el"] <= hoy]
    revisadas_ids = {r["decision_id"] for r in revisiones}
    k = sum(1 for d in vencidas if d["id"] in revisadas_ids)
    salida.append(_patron("revision", "Revisás tus decisiones", k, len(vencidas),
                          f"Revisaste {k} de {len(vencidas)} decisiones cuya fecha de revisión ya llegó.",
                          "decisiones con fecha de revisión pasada que tienen al menos una revisión"))

    # 2. Desvío respecto de la conclusión del análisis
    activas = [d for d in decisiones if d.get("accion_elegida") in DESVIO_ACCIONES]
    k = sum(1 for d in activas if d.get("conclusion_tipo") in CONCLUSIONES_DESFAVORABLES)
    salida.append(_patron("desvio", "Entradas contra la conclusión del análisis", k, len(activas),
                          f"En {k} de {len(activas)} decisiones de entrar o aumentar, el análisis concluía riesgo elevado, "
                          "valoración exigente o datos insuficientes.",
                          "acción entrar/escalonada/aumentar con conclusión riesgo_elevado, valoracion_exigente o datos_insuficientes"))

    # 3. Entradas con banderas críticas
    k = sum(1 for d in activas if d.get("banderas_altas"))
    salida.append(_patron("banderas", "Entradas con banderas críticas", k, len(activas),
                          f"{k} de {len(activas)} decisiones de entrar o aumentar tenían al menos una bandera crítica.",
                          "bandera de severidad alta al momento de decidir"))

    # 4. Concentración recurrente
    aumentos = [d for d in decisiones if d.get("accion_elegida") in DESVIO_ACCIONES]
    k = sum(1 for d in aumentos if d.get("concentracion_revisar"))
    salida.append(_patron("concentracion", "Concentración recurrente", k, len(aumentos),
                          f"En {k} de {len(aumentos)} decisiones de entrar o aumentar, la simulación ya marcaba concentración "
                          "en nivel «revisar».", "observación «revisar» del encaje con la cartera al decidir"))

    # 5. Condiciones de invalidación definidas
    k = sum(1 for d in decisiones if (d.get("condiciones") or {}).get("invalidacion"))
    salida.append(_patron("invalidacion", "Definís cómo invalidar la idea", k, n,
                          f"{k} de {n} decisiones tienen al menos una condición de invalidación.",
                          "condiciones de invalidación guardadas en la decisión"))

    # 6. Expectativa vs. resultado (sólo ejecutadas y revisadas)
    pares = []
    for r in revisiones:
        d = next((x for x in decisiones if x["id"] == r["decision_id"]), None)
        var = ((r.get("comparacion") or {}).get("precio") or {}).get("variacion")
        if d and d.get("ejecutada") and d.get("favorable_pct") is not None and var is not None:
            pares.append((d["favorable_pct"], var))
    k = sum(1 for fav, var in pares if fav > 0 and var < fav * 0.25)
    salida.append(_patron("expectativa", "Escenario favorable vs. lo observado", k, len(pares),
                          f"En {k} de {len(pares)} revisiones de decisiones ejecutadas, el precio avanzó menos de un cuarto del "
                          "escenario favorable que se veía.", "variación de precio a la revisión < 25 % del potencial favorable",
                          foco="expectativas"))

    # 7. Riesgo esperado vs. observado
    rs = [((r.get("comparacion") or {}).get("riesgo") or {}) for r in revisiones]
    rs = [x for x in rs if x.get("volatilidad_al_decidir") and x.get("volatilidad_observada")]
    k = sum(1 for x in rs if x["volatilidad_observada"] > 1.25 * x["volatilidad_al_decidir"])
    salida.append(_patron("riesgo", "Riesgo mayor al esperado", k, len(rs),
                          f"En {k} de {len(rs)} revisiones la volatilidad observada superó en más de 25 % a la histórica que se "
                          "veía al decidir.", "volatilidad semanal anualizada desde la decisión > 1,25 × la de la serie al decidir",
                          foco="riesgo"))

    # 8. Invalidación cumplida sin revisar
    k, m = 0, 0
    for r in revisiones:
        conds = (r.get("comparacion") or {}).get("condiciones") or []
        if any(c.get("cumplida") for c in conds):
            m += 1
    salida.append(_patron("invalidacion_cumplida", "Ideas invalidadas", m, len(revisiones),
                          f"En {m} de {len(revisiones)} revisiones se había cumplido alguna condición de invalidación.",
                          "condición de invalidación cumplida al revisar"))

    # Operaciones reales (diario de operaciones): reusa sus números
    operaciones = []
    if diario:
        res = diario.get("resumen") or {}
        n_rango = res.get("n_rango") or 0
        medio = res.get("rango_52s_medio_compras")
        if medio is not None:
            operaciones.append(_patron("compras_maximos", "Compras después de subas", n_rango, n_rango,
                                       f"En promedio tus compras se hicieron al {medio:.0f} % del rango de 52 semanas "
                                       "(100 = en el máximo anual).", "posición en el rango de 52 semanas al comprar",
                                       foco="operaciones"))
        n_post = res.get("n_ventas_con_post90") or 0
        operaciones.append(_patron("ventas_previas", "Ventas antes de subas", res.get("n_ventas_subieron") or 0, n_post,
                                   f"{res.get('n_ventas_subieron') or 0} de {n_post} ventas fueron seguidas por una suba de más "
                                   "de 10 % a 90 días.", "precio 90 días después de cada venta", foco="operaciones"))
        ventas_caida = diario.get("ventas_tras_caida")
        if ventas_caida:
            k2, n2 = ventas_caida
            operaciones.append(_patron("ventas_caida", "Ventas cerca de mínimos anuales", k2, n2,
                                       f"{k2} de {n2} ventas se hicieron en el 30 % más bajo del rango de 52 semanas (después "
                                       "de una caída).", "posición en el rango de 52 semanas al vender ≤ 30 %", foco="operaciones"))

    return {
        "decisiones": n,
        "revisiones": len(revisiones),
        "minimo_descriptivo": MIN_DESCRIPTIVO,
        "minimo_repetido": MIN_REPETIDO,
        "patrones": salida,
        "operaciones": operaciones,
        "salvedad": ("Patrones descriptivos sobre tus propios datos, no conclusiones estadísticas ni un diagnóstico de "
                     "sesgos: con pocos casos lo que se repite puede ser casualidad."),
    }
