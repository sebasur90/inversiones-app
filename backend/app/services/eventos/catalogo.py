"""Catálogo semilla de eventos históricos (`datos/catalogo_historico.json`). Adaptador DB.

Para que el análisis "¿cómo se movió el activo alrededor de…?" tenga con qué empezar sin depender de una
API: elecciones, decisiones de tasas, guerras y crisis conocidas de 2019 en adelante, cada uno con su
fuente. Reglas:
- **sólo eventos pasados** (fecha ≤ la del archivo): nunca hay fechas futuras en el código;
- entran como `origen="catalogo"` y `verificacion="catalogo_revisar"`: son un punto de partida curado a
  mano, no una validación; el usuario los corrige, confirma o descarta;
- la siembra es idempotente (por `id`) y respeta lo que el usuario editó o descartó: corre en cada arranque
  sin deshacer nada.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from . import importacion

logger = logging.getLogger("eventos")

RUTA = Path(__file__).parent / "datos" / "catalogo_historico.json"


def cargar() -> tuple[dict, list, list[str]]:
    """`(archivo, eventos_crudos, errores)`. Los eventos con fecha posterior a la del archivo se rechazan."""
    datos = json.loads(RUTA.read_text(encoding="utf-8"))
    creado = date.fromisoformat(datos["creado"])
    crudos, errores = importacion.parsear(datos, proveedor="catalogo", origen="catalogo", hoy=creado)
    validos = []
    for c in crudos:
        if c.fecha_evento > creado:
            errores.append(f"{c.id_externo}: el catálogo sólo admite eventos pasados")
            continue
        c.verificacion = "catalogo_revisar"
        c.programado = False
        validos.append(c)
    return datos, validos, errores


def sembrar(db: Session, con_vinculos: bool = True) -> dict:
    """Siembra o actualiza el catálogo. Commitea. `con_vinculos=False` evita armar el universo (más rápido,
    sólo vínculos declarados): la próxima sincronización propone el resto."""
    from .eventos_sync import Universo, construir_universo, incorporar_eventos

    _, crudos, errores = cargar()
    for e in errores:
        logger.warning("eventos: catálogo: %s", e)
    universo = Universo()
    if con_vinculos:
        try:
            universo = construir_universo(db)
        except Exception:
            logger.exception("eventos: no se pudo armar el universo para el catálogo; se siembra sin proponer vínculos")
            db.rollback()
    cuenta = incorporar_eventos(db, crudos, universo, date.today())
    db.commit()
    return cuenta
