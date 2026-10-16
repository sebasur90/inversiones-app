"""Qué pasó con el precio después de cada estado del diagnóstico (backtest point-in-time). Puro.

**Sólo con el historial acumulado a futuro.** Cada evento es una foto de `diagnostico_historial`: lo que la
app decía ese día con las reglas de esa versión. No se reconstruye nada hacia atrás (no hay fundamentales
históricos), así que mientras el historial es corto el resultado honesto es "muestra insuficiente".

Reglas para no engañar:
- Un evento es una **entrada a un estado** (la primera foto, o una foto cuyo estado difiere del de la foto
  anterior de la misma versión de reglas). Contar cada foto repetiría el mismo episodio con ventanas
  superpuestas y fabricaría una muestra que no existe.
- Estados de **versiones de reglas distintas** no se mezclan: se agrupan por `(dimensión, estado, versión)`.
- El precio de arranque es el último cierre de la serie hasta la fecha del registro, y el de llegada el
  primer cierre desde `fecha + horizonte` dentro de una tolerancia; si la serie no llega, el evento no cuenta
  para ese horizonte (no se rellena).
- Se informa la línea de base (todos los eventos) al lado de cada estado: un retorno de +5 % a 90 días no dice
  nada si en general subió +6 %.
- Con menos de `MINIMO_MUESTRA` eventos por celda no se muestran estadísticas, sólo el conteo.
- Retornos en USD, sin dividendos ni costos. No es una promesa sobre el futuro ni una recomendación.
"""
from __future__ import annotations

import bisect
from collections import Counter
from datetime import date, timedelta
from statistics import median

HORIZONTES = (30, 90, 180)
MINIMO_MUESTRA = 30
TOLERANCIA_DIAS = 10
DIMENSIONES = ("valuacion", "calidad", "crecimiento", "solidez")

LIMITES = (
    "Sólo cuenta lo registrado desde que existe el historial: no hay datos contables históricos para reconstruir el pasado.",
    "Cada evento es una entrada a un estado; los estados de versiones de reglas distintas no se mezclan.",
    "Los retornos son del precio en USD, sin dividendos ni costos, y no prometen nada sobre el futuro.",
    "Con pocos eventos por estado el promedio no significa nada: por eso no se muestra hasta tener una muestra mínima.",
)


def _precio_hasta(serie: list[tuple[date, float]], fecha: date) -> tuple[date, float] | None:
    """Último cierre de `serie` (ordenada) con fecha <= `fecha`."""
    i = bisect.bisect_right([f for f, _ in serie], fecha)
    return serie[i - 1] if i else None


def _precio_desde(serie: list[tuple[date, float]], fecha: date, tolerancia: int) -> tuple[date, float] | None:
    """Primer cierre con fecha >= `fecha`, si cae dentro de la tolerancia."""
    i = bisect.bisect_left([f for f, _ in serie], fecha)
    if i >= len(serie):
        return None
    f, p = serie[i]
    return (f, p) if (f - fecha).days <= tolerancia else None


def entradas_a_estado(filas: list[dict]) -> list[dict]:
    """De las fotos de varios emisores, las que son una entrada a un estado de una dimensión.

    `filas`: `{ticker_base, fecha (date), version_diagnostico, estados {dim: {estado}}, id}`. Devuelve
    `{ticker_base, fecha, dimension, estado, version}`.
    """
    por_ticker: dict[str, list[dict]] = {}
    for f in sorted(filas, key=lambda x: (x["ticker_base"], x["fecha"], x.get("id", 0))):
        por_ticker.setdefault(f["ticker_base"], []).append(f)
    eventos = []
    for ticker, lista in por_ticker.items():
        previa = None
        for f in lista:
            for dim in DIMENSIONES:
                dato = (f["estados"] or {}).get(dim)
                if not dato or dato.get("nivel") in ("no_aplica", "sin_datos"):
                    continue
                anterior = None
                if previa is not None and previa["version_diagnostico"] == f["version_diagnostico"]:
                    anterior = ((previa["estados"] or {}).get(dim) or {}).get("estado")
                    if anterior == dato["estado"]:
                        continue                # mismo estado que la foto anterior: no es una entrada
                eventos.append({
                    "ticker_base": ticker, "fecha": f["fecha"], "dimension": dim,
                    "estado": dato["estado"], "version": f["version_diagnostico"],
                })
            previa = f
    return eventos


def _estadistica(valores: list[float]) -> dict:
    n = len(valores)
    if n < MINIMO_MUESTRA:
        return {"n": n, "suficiente": False, "mediana": None, "positivos_pct": None}
    return {
        "n": n, "suficiente": True, "mediana": median(valores),
        "positivos_pct": 100.0 * sum(1 for v in valores if v > 0) / n,
    }


def retornos_posteriores(
    eventos: list[dict],
    series: dict[str, list[tuple[date, float]]],
    hoy: date | None = None,
    horizontes: tuple[int, ...] = HORIZONTES,
) -> dict:
    """Retorno a cada horizonte tras cada entrada a un estado, agrupado por `(dimensión, estado, versión)`.

    `series`: `{ticker_base: [(fecha, cierre_usd)]}` ordenada. Un evento cuyo horizonte todavía no ocurrió
    (o que no tiene serie) no cuenta para ese horizonte.
    """
    hoy = hoy or date.today()
    conteo = Counter((e["dimension"], e["estado"], e["version"]) for e in eventos)
    celdas: dict[tuple[str, str, int], dict[int, list[float]]] = {}
    base: dict[int, list[float]] = {h: [] for h in horizontes}
    for ev in eventos:
        serie = series.get(ev["ticker_base"]) or []
        if not serie:
            continue
        ini = _precio_hasta(serie, ev["fecha"])
        if ini is None or ini[1] <= 0:
            continue
        clave = (ev["dimension"], ev["estado"], ev["version"])
        for h in horizontes:
            objetivo = ev["fecha"] + timedelta(days=h)
            if objetivo > hoy:
                continue
            fin = _precio_desde(serie, objetivo, TOLERANCIA_DIAS)
            if fin is None:
                continue
            r = fin[1] / ini[1] - 1.0
            celdas.setdefault(clave, {h2: [] for h2 in horizontes})[h].append(r)
            base[h].append(r)

    resultado = [
        {
            "dimension": dim, "estado": estado, "version": version,
            "eventos": conteo[(dim, estado, version)],
            "horizontes": {str(h): _estadistica(por_h[h]) for h in horizontes},
        }
        for (dim, estado, version), por_h in sorted(celdas.items())
    ]
    return {
        "horizontes": list(horizontes),
        "minimo_muestra": MINIMO_MUESTRA,
        "eventos_totales": len(eventos),
        "base": {str(h): _estadistica(base[h]) for h in horizontes},
        "estados": resultado,
        "suficiente": any(c["suficiente"] for r in resultado for c in r["horizontes"].values()),
        "limites": list(LIMITES),
    }
