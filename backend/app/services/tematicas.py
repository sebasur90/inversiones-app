"""Temáticas de búsqueda del Centro de Decisiones, **definidas por reglas sobre datos que la app tiene**. Puro.

No hay una clasificación temática de fuente externa ("inteligencia artificial", "transición energética"): la
app no la inventa. Esas búsquedas se resuelven con los filtros reales de sector e industria, y la pantalla dice
que la temática no está cubierta como tal.
"""
from __future__ import annotations

from . import valuacion_engine as ve

TEMATICAS = {
    "dividendos": {
        "nombre": "Pagan dividendos",
        "regla": "rendimiento por dividendo ≥ 2 % anual y payout menor a 100 % (o no informado)",
    },
    "crecimiento": {
        "nombre": "Empresas de crecimiento",
        "regla": "crecimiento de ingresos interanual ≥ 10 % (último trimestre contra el mismo de hace un año)",
    },
    "valor": {
        "nombre": "Baratas frente a sus pares",
        "regla": "lectura de valuación «barata» contra su grupo de pares",
    },
    "calidad": {
        "nombre": "Alta calidad",
        "regla": "dimensión calidad del diagnóstico en nivel «bien» (márgenes y retornos en el cuarto mejor de sus pares)",
    },
}

NO_CUBIERTAS = (
    "Las temáticas como «inteligencia artificial» o «energías limpias» no tienen una clasificación de fuente confiable "
    "en la app: buscá por sector o industria (por ejemplo, Semiconductores o Software) y revisá cada empresa."
)


def cumple(tematica: str, ficha: ve.Ficha | None, lectura: str | None, nivel_calidad: str | None) -> bool | None:
    """`True`/`False`, o `None` si falta el dato para decidir (no se asume que no cumple)."""
    if ficha is None:
        return None
    v = ficha.valores
    if tematica == "dividendos":
        dy = v.get("div_yield")
        if dy is None:
            return None
        payout = ficha.extra.get("payout")
        return dy >= 0.02 and (payout is None or payout < 1.0)
    if tematica == "crecimiento":
        ci = v.get("crec_ingresos")
        return None if ci is None else ci >= 0.10
    if tematica == "valor":
        return None if lectura in (None, ve.LECTURA_SIN_DATOS) else lectura == ve.LECTURA_BARATA
    if tematica == "calidad":
        return None if nivel_calidad in (None, "sin_datos", "no_aplica") else nivel_calidad == "bien"
    raise ValueError(f"temática desconocida: {tematica}")
