"""Riesgo histórico, fuentes y fechas de los datos que usa el Centro de Decisiones. Puro salvo `riesgo_de`,
que sólo lee el `Universo` ya armado (sin red ni consultas nuevas).

El riesgo de **todos** los activos comparados sale de la misma base: la serie semanal en USD del snapshot de
fundamentales (`Universo.serie_usd`, ~5 años). Así la volatilidad de la alternativa y la del activo inicial
se miden sobre las mismas fechas y la misma moneda, aunque alguno no tenga serie diaria (técnica).

- Volatilidad anual = desvío estándar de los retornos logarítmicos semanales × √52 (`risk_engine` trabaja con
  retornos mensuales; acá hay semanales, por eso la cuenta va aparte).
- Caída máxima = mayor caída desde un máximo previo de la serie (`min(cierre / máximo previo − 1)`).
"""
from __future__ import annotations

import math
import statistics
from datetime import date

MIN_SEMANAS = 26
SEMANAS_POR_ANIO = 52
DIAS_FECHA_DATO_DISTINTA = 14
DIAS_PERIODO_DISTINTO = 120     # mismo umbral que el diagnóstico (balances de trimestres distintos)
DIAS_PRECIO_VIEJO = 7


def volatilidad_anual(cierres: list[float]) -> float | None:
    rets = [math.log(b / a) for a, b in zip(cierres, cierres[1:]) if a > 0 and b > 0]
    if len(rets) < MIN_SEMANAS - 1:
        return None
    return statistics.stdev(rets) * math.sqrt(SEMANAS_POR_ANIO)


def caida_maxima(cierres: list[float]) -> float | None:
    if len(cierres) < MIN_SEMANAS:
        return None
    pico, peor = cierres[0], 0.0
    for c in cierres:
        pico = max(pico, c)
        if pico > 0:
            peor = min(peor, c / pico - 1.0)
    return peor


def riesgo_serie(puntos: list[tuple[date, float]], beta: float | None) -> dict:
    """`puntos` = cierres semanales `(fecha, cierre)` ordenados."""
    cierres = [c for _, c in puntos]
    return {
        "volatilidad": volatilidad_anual(cierres),
        "caida_maxima": caida_maxima(cierres),
        "beta": beta,
        "semanas": len(cierres),
        "desde": puntos[0][0] if puntos else None,
        "fecha": puntos[-1][0] if puntos else None,
        "moneda_serie": "USD",
    }


def riesgo_de(u, base: str) -> dict:
    ficha = u.ficha(base)
    beta = ficha.extra.get("beta") if ficha is not None else None
    return riesgo_serie(u.serie_usd(base), beta)


def _antiguedad(fecha: date | None, hoy: date) -> int | None:
    return (hoy - fecha).days if fecha else None


def fuente(dato: str, origen: str, fecha: date | None, hoy: date, dias_viejo: int | None = None,
           nota: str = "") -> dict:
    dias = _antiguedad(fecha, hoy)
    if fecha is None:
        estado = "falta"
    elif dias_viejo is not None and dias is not None and dias > dias_viejo:
        estado = "viejo"
    else:
        estado = "ok"
    return {"dato": dato, "fuente": origen, "fecha": fecha, "antiguedad_dias": dias, "estado": estado, "nota": nota}


def compatibilidad_fechas(objetivo: dict, alternativas: list[dict]) -> list[str]:
    """Advertencias cuando la comparación mezcla datos de fechas o balances distintos.

    Cada dict trae `ticker`, `fecha_dato` y `periodo_contable` (fechas o None)."""
    out = []
    fo, po = objetivo.get("fecha_dato"), objetivo.get("periodo_contable")
    for a in alternativas:
        fa, pa = a.get("fecha_dato"), a.get("periodo_contable")
        if fo and fa and abs((fo - fa).days) > DIAS_FECHA_DATO_DISTINTA:
            out.append(f"{a['ticker']}: fundamentales del {fa.isoformat()} contra {fo.isoformat()} "
                       f"(más de {DIAS_FECHA_DATO_DISTINTA} días de diferencia)")
        if po and pa and abs((po - pa).days) > DIAS_PERIODO_DISTINTO:
            out.append(f"{a['ticker']}: último balance del {pa.isoformat()} contra {po.isoformat()} "
                       f"(trimestres distintos)")
        if po and pa is None:
            out.append(f"{a['ticker']}: no informa la fecha de su último balance")
    return out
