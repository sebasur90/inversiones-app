"""Comportamiento observado del precio alrededor de un evento (estudio de eventos). Puro.

Describe lo que pasó, **no demuestra que el evento lo haya causado**: en la misma ventana pueden haber
pasado otras cosas (se listan los otros eventos superpuestos) y el mercado en general también se mueve (por
eso va el benchmark al lado).

**Mercado de la serie.** El subyacente en USD (`@SUB`), SPY y QQQ son de Nueva York (cierre 16:00,
`America/New_York`); la serie local de BYMA y el Merval, de Buenos Aires (cierre 17:00). Las ruedas son las
fechas que tienen barra en la serie: no se inventa un calendario de feriados.

**Cuándo lo supo el mercado.** Si el evento estaba programado (una reunión de la Fed, un balance), cuenta la
fecha y hora del evento. Si no, cuenta la fecha de publicación de la noticia cuando la hay (en UTC), y si no,
la fecha del evento.

**Rueda de referencia (T0)**, con ese momento llevado a la hora del mercado de la serie:
- hubo rueda ese día y fue antes del cierre → T0 es esa rueda;
- fue después del cierre → T0 es la rueda siguiente (una noticia de las 19 h no estuvo disponible en la rueda
  de ese día);
- no hubo rueda ese día (fin de semana, feriado) → T0 es la primera rueda posterior;
- sin hora conocida → T0 es la rueda de ese día si la hubo, con el aviso `hora_desconocida` (si fue después
  del cierre, la reacción aparece recién en T0+1).

**Retornos** sobre cierres (`C`), para cada ventana `N` ruedas:
- previo: `C[T0-1] / C[T0-1-N] - 1` (lo que venía pasando antes);
- rueda del evento: `C[T0] / C[T0-1] - 1`;
- posterior: `C[T0+N] / C[T0] - 1` (con N=1, la primera rueda posterior a la del evento);
- acumulado: `C[T0+N] / C[T0-1-N] - 1` (toda la ventana).

Si la serie no llega a cubrir un extremo, ese dato queda `None` con su motivo (`ventana_incompleta`,
`sin_datos_posteriores`): **nunca** se completa con el precio actual ni se interpola. Un hueco de más de
`HUECO_DIAS` días corridos entre dos ruedas de la ventana se avisa (`huecos`).

**Benchmark**: el mismo cálculo sobre el índice en las **mismas fechas** (el cierre del índice de esa fecha o
del día hábil anterior, a no más de `TOLERANCIA_BENCH_DIAS`; si no, `None`). La diferencia es simple: activo
menos índice, en puntos porcentuales.

**Volatilidad**: desvío estándar de los retornos diarios de la ventana posterior (T0..T0+N) frente al de las
20 ruedas previas, con al menos `MIN_OBS_VOL` retornos. **Volumen relativo**: volumen promedio de la
ventana posterior sobre el de las 20 ruedas previas, sólo si hay volumen en todas.

Los porcentajes salen en % (2.5 = 2,5 %).
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from statistics import median, pstdev
from zoneinfo import ZoneInfo

VENTANAS = (1, 5, 20)
VENTANA_LARGA = 60           # se agrega sólo si la serie alcanza
HUECO_DIAS = 7
TOLERANCIA_BENCH_DIAS = 3
RUEDAS_BASE = 20
MIN_OBS_VOL = 5
MINIMO_MUESTRA_PATRON = 8

LEYENDA = (
    "Comportamiento observado alrededor del evento: no demuestra que el evento haya causado el movimiento. "
    "En la misma ventana pueden haber pasado otras cosas y el mercado en general también se mueve."
)


@dataclass(frozen=True)
class Mercado:
    nombre: str
    zona: str
    cierre: time


NYSE = Mercado("NYSE", "America/New_York", time(16, 0))
BYMA = Mercado("BYMA", "America/Argentina/Buenos_Aires", time(17, 0))
_INDICES_NY = ("SPY", "QQQ")


def mercado_de(ticker: str, variante: str) -> Mercado:
    if variante == "subyacente" or ticker.upper() in _INDICES_NY:
        return NYSE
    return BYMA


def momento_conocimiento(evento: dict) -> dict:
    """`{fecha, hora, zona, fuente}`: cuándo y en qué zona horaria lo supo el mercado.

    `evento`: `fecha_evento` (date), `hora_evento` (time | None), `zona_horaria`, `fecha_publicacion`
    (datetime UTC naive | None), `programado` (bool).
    """
    pub = evento.get("fecha_publicacion")
    fecha = evento["fecha_evento"]
    if not evento.get("programado") and pub is not None and pub.date() >= fecha - timedelta(days=1):
        return {"fecha": pub.date(), "hora": pub.time(), "zona": "UTC", "fuente": "publicacion"}
    hora = evento.get("hora_evento")
    zona = evento.get("zona_horaria") if hora is not None else None
    return {"fecha": fecha, "hora": hora, "zona": zona, "fuente": "evento"}


def _a_hora_del_mercado(m: dict, mercado: Mercado) -> tuple[date, time | None]:
    if m["hora"] is None:
        return m["fecha"], None
    try:
        origen = timezone.utc if m["zona"] in (None, "UTC") else ZoneInfo(m["zona"])
    except Exception:
        origen = ZoneInfo(mercado.zona)
    instante = datetime.combine(m["fecha"], m["hora"]).replace(tzinfo=origen).astimezone(ZoneInfo(mercado.zona))
    return instante.date(), instante.time()


def rueda_referencia(fechas: list[date], evento: dict, mercado: Mercado) -> dict:
    """`{indice, fecha, regla, motivo, avisos, conocimiento}`. `indice` es None si la serie no llega."""
    m = momento_conocimiento(evento)
    dia, hora = _a_hora_del_mercado(m, mercado)
    avisos: list[str] = []
    i = bisect.bisect_left(fechas, dia)
    hay_rueda = i < len(fechas) and fechas[i] == dia
    if hay_rueda and hora is None:
        indice, regla = i, "Rueda del mismo día (no se conoce la hora: si fue después del cierre, la reacción aparece en la rueda siguiente)"
        avisos.append("hora_desconocida")
    elif hay_rueda and hora < mercado.cierre:
        indice, regla = i, f"Antes del cierre de {mercado.nombre} ({mercado.cierre:%H:%M}): rueda del mismo día"
    elif hay_rueda:
        indice, regla = i + 1, f"Después del cierre de {mercado.nombre} ({mercado.cierre:%H:%M}): primera rueda siguiente"
    else:
        indice, regla = i, "Ese día no hubo rueda: primera rueda siguiente"
    conocimiento = {"fecha": dia, "hora": hora.strftime("%H:%M") if hora else None, "zona": mercado.zona if hora else None,
                    "fuente": m["fuente"]}
    if not fechas or indice >= len(fechas):
        return {"indice": None, "fecha": None, "regla": regla, "motivo": "sin_datos_posteriores", "avisos": avisos,
                "conocimiento": conocimiento}
    if indice == 0:
        avisos.append("sin_datos_previos")
    return {"indice": indice, "fecha": fechas[indice], "regla": regla, "motivo": None, "avisos": avisos,
            "conocimiento": conocimiento}


def _ret(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a <= 0:
        return None
    return round((b / a - 1) * 100, 4)


def _valor_en(serie_bench: list[tuple[date, float]], fechas_bench: list[date], d: date | None) -> float | None:
    if d is None:
        return None
    i = bisect.bisect_right(fechas_bench, d)
    if not i:
        return None
    f, v = serie_bench[i - 1]
    return v if (d - f).days <= TOLERANCIA_BENCH_DIAS else None


def _desvio(cierres: list[float]) -> float | None:
    rets = [cierres[k] / cierres[k - 1] - 1 for k in range(1, len(cierres)) if cierres[k - 1] > 0]
    if len(rets) < MIN_OBS_VOL:
        return None
    return round(pstdev(rets) * 100, 4)


def ventana(serie: list[tuple[date, float, float | None]], t0: int, n: int,
            bench: list[tuple[date, float]] | None = None) -> dict:
    """Los retornos de una ventana de `n` ruedas alrededor de `t0` (índice en `serie`)."""
    fechas = [s[0] for s in serie]
    c = [s[1] for s in serie]
    ok = lambda k: 0 <= k < len(serie)
    i_ini, i_pre, i_fin = t0 - 1 - n, t0 - 1, t0 + n
    motivos = []
    if not ok(i_ini):
        motivos.append("ventana_incompleta_antes")
    if not ok(i_fin):
        motivos.append("sin_datos_posteriores" if t0 + 1 >= len(serie) else "ventana_incompleta_despues")
    v = lambda k: c[k] if ok(k) else None
    f = lambda k: fechas[k] if ok(k) else None
    out = {
        "n": n,
        "previo_pct": _ret(v(i_ini), v(i_pre)), "rueda_pct": _ret(v(i_pre), v(t0)),
        "posterior_pct": _ret(v(t0), v(i_fin)), "acumulado_pct": _ret(v(i_ini), v(i_fin)),
        "fechas": {"inicio": f(i_ini), "previa": f(i_pre), "referencia": f(t0), "fin": f(i_fin)},
        "observaciones": len(range(max(0, i_ini), min(len(serie), i_fin + 1))),
        "completa": not motivos, "motivos": motivos,
    }
    tramo = fechas[max(0, i_ini): min(len(serie), i_fin + 1)]
    if any((tramo[k] - tramo[k - 1]).days > HUECO_DIAS for k in range(1, len(tramo))):
        out["motivos"].append("huecos")
    # Volatilidad y volumen
    post = c[t0: i_fin + 1] if ok(i_fin) else []
    base = c[max(0, t0 - 1 - RUEDAS_BASE): t0]
    out["volatilidad_posterior_pct"] = _desvio([c[t0 - 1]] + post if t0 >= 1 and post else post)
    out["volatilidad_previa_pct"] = _desvio(base)
    vol_post = [serie[k][2] for k in range(t0, i_fin + 1)] if ok(i_fin) else []
    vol_base = [serie[k][2] for k in range(max(0, t0 - RUEDAS_BASE), t0)]
    if vol_post and len(vol_base) >= MIN_OBS_VOL and all(x for x in vol_post + vol_base):
        out["volumen_relativo"] = round((sum(vol_post) / len(vol_post)) / (sum(vol_base) / len(vol_base)), 3)
    else:
        out["volumen_relativo"] = None
    # Benchmark en las mismas fechas
    if bench:
        fb = [b[0] for b in bench]
        bv = {k: _valor_en(bench, fb, f(k)) for k in (i_ini, i_pre, t0, i_fin)}
        out.update({
            "bench_previo_pct": _ret(bv[i_ini], bv[i_pre]), "bench_rueda_pct": _ret(bv[i_pre], bv[t0]),
            "bench_posterior_pct": _ret(bv[t0], bv[i_fin]), "bench_acumulado_pct": _ret(bv[i_ini], bv[i_fin]),
        })
        dif = lambda a, b: round(a - b, 4) if a is not None and b is not None else None
        out["dif_rueda_pct"] = dif(out["rueda_pct"], out["bench_rueda_pct"])
        out["dif_posterior_pct"] = dif(out["posterior_pct"], out["bench_posterior_pct"])
        out["dif_acumulado_pct"] = dif(out["acumulado_pct"], out["bench_acumulado_pct"])
    return out


def analizar(serie: list[tuple[date, float, float | None]], evento: dict, mercado: Mercado,
             bench: list[tuple[date, float]] | None = None, otros: list[dict] | None = None,
             ventanas: tuple[int, ...] = VENTANAS) -> dict:
    """Análisis completo de un evento sobre una serie ordenada `[(fecha, cierre, volumen)]`.

    `otros`: los demás eventos que podrían superponerse (`{id, titulo, categoria, importancia, fecha_evento,
    hora_evento, zona_horaria, fecha_publicacion, programado}`).
    """
    fechas = [s[0] for s in serie]
    ref = rueda_referencia(fechas, evento, mercado)
    base = {"referencia": ref, "ventanas": [], "superpuestos": [], "avisos": list(ref["avisos"]), "leyenda": LEYENDA,
            "mercado": mercado.nombre}
    if not serie:
        base["avisos"].append("sin_serie")
        return base
    if ref["indice"] is None:
        base["avisos"].append("sin_datos_posteriores")
        return base
    t0 = ref["indice"]
    lista = list(ventanas)
    if VENTANA_LARGA not in lista and t0 - 1 - VENTANA_LARGA >= 0 and t0 + VENTANA_LARGA < len(serie):
        lista.append(VENTANA_LARGA)
    base["ventanas"] = [ventana(serie, t0, n, bench) for n in lista]
    n_max = max(lista)
    for o in otros or []:
        r = rueda_referencia(fechas, o, mercado)
        if r["indice"] is None or o.get("id") == evento.get("id"):
            continue
        distancia = r["indice"] - t0
        if abs(distancia) <= n_max:
            base["superpuestos"].append({
                "evento_id": o.get("id"), "titulo": o.get("titulo"), "categoria": o.get("categoria"),
                "importancia": o.get("importancia"), "fecha_referencia": r["fecha"], "distancia_ruedas": distancia,
                "ventanas": [n for n in lista if abs(distancia) <= n],
            })
    base["superpuestos"].sort(key=lambda s: (abs(s["distancia_ruedas"]), -(s["importancia"] or 0)))
    if any(s["distancia_ruedas"] == 0 for s in base["superpuestos"]):
        base["avisos"].append("otro_evento_misma_rueda")
    return base


def retornos_base(serie: list[tuple[date, float, float | None]], n: int) -> list[float]:
    """Todos los retornos de `n` ruedas de la serie (sin superposición): la línea de base contra la que se
    compara lo observado después de los eventos. Sin ella, "+3 % a 5 ruedas" no dice nada si la serie sube
    +3 % cada 5 ruedas en general."""
    c = [s[1] for s in serie]
    return [(c[k + n] / c[k] - 1) * 100 for k in range(0, len(c) - n, n) if c[k] > 0]


def patron(casos: list[dict], base: list[float], minimo: int = MINIMO_MUESTRA_PATRON) -> dict:
    """Resumen de varios eventos de una misma categoría sobre un ticker. Con menos de `minimo` casos no se
    muestran estadísticas: sólo los casos."""
    valores = [c["posterior_pct"] for c in casos if c.get("posterior_pct") is not None]
    out = {"casos_validos": len(valores), "minimo": minimo, "suficiente": len(valores) >= minimo,
           "mediana_posterior_pct": None, "positivos_pct": None,
           "mediana_base_pct": round(median(base), 4) if len(base) >= minimo else None,
           "positivos_base_pct": round(100 * sum(1 for b in base if b > 0) / len(base), 1) if len(base) >= minimo else None}
    if out["suficiente"]:
        out["mediana_posterior_pct"] = round(median(valores), 4)
        out["positivos_pct"] = round(100 * sum(1 for v in valores if v > 0) / len(valores), 1)
    return out
