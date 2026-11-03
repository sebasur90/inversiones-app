"""Catálogo de series macroeconómicas del régimen (`catalogos/ciclos_macro.json`).

Mismo criterio que `ciclos_catalogo`: lo que se mide se edita en el JSON, no en el código. Una serie inválida se descarta
**sola** y se informa en `errores`; un archivo ausente o roto equivale a un catálogo vacío. Nunca lanza.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .ciclos_catalogo import _leer, _ruta, _texto

EJES_CLASIFICAN = ("crecimiento", "inflacion")
EJES_CONTEXTO = ("liquidez", "condiciones_financieras", "dolar")
FRECUENCIAS = ("diaria", "semanal", "mensual")
TRANSFORMACIONES = ("variacion_12m", "nivel")
FUENTE = "FRED (Reserva Federal de St. Louis)"
MESES_COMPARACION_DEFECTO = 3
MINIMO_VOTOS_DEFECTO = 3
DIAS_ATRASO_DEFECTO = {"diaria": 10, "semanal": 21, "mensual": 75}

_ID_RE = re.compile(r"^[A-Z0-9_]{2,30}$")


@dataclass(frozen=True)
class SerieMacro:
    id: str
    nombre: str
    eje: str
    frecuencia: str
    transformacion: str
    sentido: int
    unidad: str
    descripcion: str
    nota: str | None

    @property
    def clasifica(self) -> bool:
        return self.eje in EJES_CLASIFICAN


@dataclass
class CatalogoMacro:
    meses_comparacion: int = MESES_COMPARACION_DEFECTO
    minimo_votos: int = MINIMO_VOTOS_DEFECTO
    dias_maximos: dict[str, int] = field(default_factory=lambda: dict(DIAS_ATRASO_DEFECTO))
    series: dict[str, SerieMacro] = field(default_factory=dict)
    errores: list[str] = field(default_factory=list)

    def por_eje(self, eje: str) -> list[SerieMacro]:
        return [s for s in self.series.values() if s.eje == eje]


def _entero(valor, defecto: int, minimo: int, maximo: int, nombre: str, errores: list[str]) -> int:
    if valor is None:
        return defecto
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        errores.append(f"{nombre} inválido ({valor!r}); se usa {defecto}")
        return defecto
    return valor


def _armar(crudo: dict) -> SerieMacro:
    if not isinstance(crudo, dict):
        raise ValueError("no es un objeto")
    id_ = _texto(crudo.get("id")) or ""
    if not _ID_RE.match(id_):
        raise ValueError(f"id inválido {id_!r} (el código de FRED, en mayúsculas)")
    nombre = _texto(crudo.get("nombre"))
    if not nombre:
        raise ValueError("falta el nombre")
    eje = _texto(crudo.get("eje"))
    if eje not in (*EJES_CLASIFICAN, *EJES_CONTEXTO):
        raise ValueError(f"eje inválido {eje!r}")
    frecuencia = _texto(crudo.get("frecuencia"))
    if frecuencia not in FRECUENCIAS:
        raise ValueError(f"frecuencia inválida {frecuencia!r}")
    transformacion = _texto(crudo.get("transformacion"))
    if transformacion not in TRANSFORMACIONES:
        raise ValueError(f"transformación inválida {transformacion!r}")
    sentido = crudo.get("sentido", 1)
    if sentido not in (1, -1) or isinstance(sentido, bool):
        raise ValueError("`sentido` debe ser 1 o -1")
    return SerieMacro(id_, nombre, eje, frecuencia, transformacion, int(sentido), _texto(crudo.get("unidad")) or "",
                      _texto(crudo.get("descripcion")) or "", _texto(crudo.get("nota")))


def construir(datos: dict) -> CatalogoMacro:
    """Valida el contenido ya leído. Puro: lo usan `cargar()` y los tests."""
    cat = CatalogoMacro()
    cat.meses_comparacion = _entero(datos.get("meses_comparacion"), MESES_COMPARACION_DEFECTO, 1, 24, "meses_comparacion", cat.errores)
    cat.minimo_votos = _entero(datos.get("minimo_votos"), MINIMO_VOTOS_DEFECTO, 1, 10, "minimo_votos", cat.errores)
    maximos = datos.get("dias_maximos_de_atraso")
    if isinstance(maximos, dict):
        for f in FRECUENCIAS:
            cat.dias_maximos[f] = _entero(maximos.get(f), DIAS_ATRASO_DEFECTO[f], 1, 400, f"dias_maximos_de_atraso.{f}", cat.errores)
    for crudo in datos.get("series") or []:
        id_ = crudo.get("id") if isinstance(crudo, dict) else None
        try:
            s = _armar(crudo)
        except ValueError as exc:
            cat.errores.append(f"serie {id_!r}: {exc}; se descarta")
            continue
        if s.id in cat.series:
            cat.errores.append(f"serie {s.id}: id repetido; se descarta la segunda")
            continue
        cat.series[s.id] = s
    return cat


def cargar() -> CatalogoMacro:
    errores: list[str] = []
    datos = _leer(_ruta("ciclos_macro.json", "CICLOS_MACRO_FILE"), errores)
    cat = construir(datos)
    cat.errores = errores + cat.errores
    return cat
