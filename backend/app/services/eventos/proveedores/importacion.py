"""Archivos JSON de eventos programados en el volumen de datos (calendarios oficiales que mantiene el
usuario: elecciones, reuniones de bancos centrales, calendarios corporativos). Formato en
`services/eventos/importacion.py`. Sin red: siempre configurado; si la carpeta no existe, no hay nada que
leer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .. import importacion
from .base import CAP_EVENTOS_PROGRAMADOS, ESTADO_OK, ESTADO_PARCIAL, ContextoProveedor, ProveedorEventos, ResultadoProveedor

DIR_DEFAULT = "/app/data/eventos_programados"
MAX_BYTES = 2_000_000


def directorio() -> Path:
    return Path(os.getenv("EVENTOS_IMPORTACION_DIR") or DIR_DEFAULT)


class ImportacionArchivos(ProveedorEventos):
    nombre = "importacion"
    etiqueta = "Archivos de calendarios (importación)"
    capacidades = (CAP_EVENTOS_PROGRAMADOS,)
    ayuda = (
        "Dejá archivos .json con el formato documentado en docs/calendario-eventos.md dentro de "
        "data/eventos_programados (volumen del backend), o subilos desde esta pantalla."
    )
    usa_red = False

    def max_por_corrida(self) -> int:
        return 1

    def obtener(self, ctx: ContextoProveedor) -> ResultadoProveedor:
        carpeta = directorio()
        if not carpeta.is_dir():
            return ResultadoProveedor(estado=ESTADO_OK, mensaje="Sin carpeta de calendarios (nada para importar)")
        eventos, errores = [], []
        archivos = sorted(p for p in carpeta.glob("*.json") if p.is_file())
        for p in archivos:
            try:
                if p.stat().st_size > MAX_BYTES:
                    errores.append(f"{p.name}: el archivo es demasiado grande")
                    continue
                datos = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errores.append(f"{p.name}: no se pudo leer ({type(exc).__name__})")
                continue
            evs, errs = importacion.parsear(datos, proveedor=f"archivo:{p.stem}"[:60], origen="importacion", hoy=ctx.hoy)
            eventos.extend(evs)
            errores.extend(f"{p.name} {e}" for e in errs)
        mensaje = f"{len(eventos)} eventos de {len(archivos)} archivos"
        if errores:
            mensaje += f"; {len(errores)} con errores: " + " | ".join(errores[:3])
        return ResultadoProveedor(estado=ESTADO_PARCIAL if errores else ESTADO_OK, mensaje=mensaje[:900], eventos=eventos)
