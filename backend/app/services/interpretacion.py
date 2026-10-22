"""Capa de interpretación del Centro de Decisiones: convierte resultados calculados en frases.

En esta versión **no hay IA**: la única implementación es `Plantillas`, determinista, que sólo arma texto con
los números que ya calculó el backend. La interfaz `Interpretador` existe para poder enchufar después un
modelo de lenguaje sin tocar el resto (variable `DECISIONES_INTERPRETADOR`; hoy sólo vale `plantillas`).

Cualquier implementación tiene que pasar por `validar_cifras`: **todo número de una frase debe existir en los
datos estructurados que se le dieron** (con tolerancia de redondeo). Una frase que no pasa se descarta y se
registra en el log; nunca se muestra una cifra que no salga de un cálculo. Los tests aplican la misma guarda
a todas las plantillas.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Protocol

logger = logging.getLogger(__name__)

_NUMERO = re.compile(r"(?<![\w.])[-−+]?\d[\d.]*(?:,\d+)?")


class Interpretador(Protocol):
    nombre: str

    def resumen(self, analisis: dict) -> list[dict]:
        """Resumen ejecutivo: frases `{texto, regla, fuentes}`."""


def _a_float(token: str) -> float | None:
    t = token.replace("−", "-").replace("+", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def _numeros_de(valor, acumulado: set[float]) -> None:
    if isinstance(valor, bool) or valor is None:
        return
    if isinstance(valor, (int, float)):
        acumulado.add(float(valor))
        acumulado.add(float(valor) * 100)      # fracciones que se muestran como %
        return
    if isinstance(valor, str):
        for tok in _NUMERO.findall(valor):
            n = _a_float(tok)
            if n is not None:
                acumulado.add(n)
        return
    if isinstance(valor, dict):
        for v in valor.values():
            _numeros_de(v, acumulado)
        return
    if isinstance(valor, (list, tuple, set)):
        for v in valor:
            _numeros_de(v, acumulado)


def validar_cifras(texto: str, datos) -> list[str]:
    """Los números de `texto` que no aparecen en `datos` (vacío = la frase es trazable)."""
    disponibles: set[float] = set()
    _numeros_de(datos, disponibles)
    faltan = []
    for tok in _NUMERO.findall(texto):
        n = _a_float(tok)
        if n is None:
            continue
        if abs(n) < 10 and float(n).is_integer() and abs(n) <= 7:
            continue    # cardinales chicos ("3 de 5 dimensiones", "2 alternativas"): conteos, no cifras financieras
        # Tolerancia = medio paso de la última cifra mostrada: "58" vale para 58,3 y "58,3" para 58,27.
        decimales = len(tok.split(",", 1)[1]) if "," in tok else 0
        tol = 0.5 * 10 ** -decimales + 1e-9
        if not any(abs(abs(n) - abs(d)) <= max(tol, abs(d) * 0.0005) for d in disponibles):
            faltan.append(tok)
    return faltan


def _fmt(v: float, dec: int = 0) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


class Plantillas:
    nombre = "plantillas"

    def resumen(self, analisis: dict) -> list[dict]:
        ev = analisis.get("evaluacion") or {}
        concl = analisis.get("conclusion") or {}
        frases: list[dict] = []
        orden = ev.get("orden") or {}
        if orden.get("puntaje") is not None:
            frases.append({
                "texto": f"Puntaje de orden {_fmt(orden['puntaje'])} con tus preferencias (más alto = mejor ubicado); "
                         "sirve para priorizar, no para decidir solo.",
                "regla": orden.get("regla", ""), "fuentes": ["evaluacion.orden"],
            })
        elif orden:
            frases.append({"texto": f"Análisis incompleto: {orden.get('motivo')}.", "regla": orden.get("regla", ""),
                           "fuentes": ["evaluacion.orden"]})
        dims = {d["clave"]: d for d in ev.get("dimensiones", [])}
        fund, val = dims.get("fundamentales"), dims.get("valoracion")
        if fund and val and fund.get("puntaje") is not None and val.get("puntaje") is not None:
            frases.append({
                "texto": f"Calidad del negocio y precio van por separado: Fundamentales {_fmt(fund['puntaje'])}, "
                         f"Valoración {_fmt(val['puntaje'])}.",
                "regla": "dimensiones Fundamentales y Valoración del motor de evaluación", "fuentes": ["evaluacion.dimensiones"],
            })
        for b in (ev.get("banderas") or [])[:3]:
            frases.append({"texto": f"Atención: {b['texto']}", "regla": b.get("regla", ""), "fuentes": ["evaluacion.banderas"]})
        if concl:
            frases.append({"texto": f"{concl.get('titulo')}. {concl.get('respuestas', {}).get('por_que', '')}".strip(),
                           "regla": concl.get("regla", ""), "fuentes": ["conclusion"]})
        return frases


def interpretador() -> Interpretador:
    nombre = os.getenv("DECISIONES_INTERPRETADOR", "plantillas").strip().lower()
    if nombre != "plantillas":
        logger.warning("DECISIONES_INTERPRETADOR=%s no está implementado: se usan las plantillas", nombre)
    return Plantillas()


def resumen_validado(analisis: dict) -> list[dict]:
    """El resumen del interpretador, descartando toda frase con una cifra que no salga de los datos."""
    try:
        frases = interpretador().resumen(analisis)
    except Exception:   # un interpretador futuro que falle no puede tumbar el análisis
        logger.exception("el interpretador falló: el resumen sale vacío")
        return []
    salida = []
    for f in frases:
        faltan = validar_cifras(f.get("texto", ""), analisis)
        if faltan:
            logger.warning("frase descartada por cifras no trazables %s: %s", faltan, f.get("texto"))
            continue
        salida.append(f)
    return salida
