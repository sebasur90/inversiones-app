"""Registro semanal del estado de rotación de cada grupo (`ciclos_estado_historial`).

Se escribe después de cada ingesta, **sólo con semanas cerradas** y sólo si el grupo y su benchmark están
completos y al día (`estado == ok`): una actualización a medias no deja huecos ni estados dudosos. Es una
foto recalculable (no la fuente de verdad) con la versión del algoritmo; sirve para estudiar más adelante
qué tan bien anticipó cada estado y para detectar cambios confirmados (`ciclos_senales_engine`).
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..database import CiclosEstadoHistorial
from . import ciclos_analytics as ca
from . import ciclos_catalogo as cc
from . import ciclos_engine as eng
from . import sync_lock

logger = logging.getLogger("ciclos_historial")

SEMANAS_POR_CORRIDA = 52
LOCK_ESCRITURA_TIMEOUT_SEG = 300


def registrar(db: Session, hoy: date | None = None, semanas: int = SEMANAS_POR_CORRIDA) -> dict:
    """Agrega las semanas cerradas que falten. Idempotente. Hace commit; nunca lanza por datos."""
    hoy = hoy or date.today()
    cat = cc.cargar()
    fuentes = ca.Fuentes(db, cat)
    existentes = {
        (r.grupo_id, r.benchmark_id, r.semana)
        for r in db.query(CiclosEstadoHistorial).filter(CiclosEstadoHistorial.version_algoritmo == eng.VERSION_ALGORITMO)
    }
    nuevas, omitidos = [], []
    ahora = datetime.utcnow()
    for g in cat.activos():
        b = ca._benchmark_efectivo(cat, g)
        if b is None:
            continue
        a_usd, b_usd = fuentes.nativa(g), fuentes.nativa(b)
        if not a_usd or not b_usd:
            omitidos.append(g.id)
            continue
        rot = eng.rotacion(a_usd, b_usd, hoy=hoy)
        if rot["estado"] != eng.ESTADO_OK:
            omitidos.append(g.id)
            continue
        for p in rot["puntos"][-semanas:]:
            if not eng.semana_cerrada(p["fecha"], hoy) or (g.id, b.id, p["fecha"]) in existentes:
                continue
            nuevas.append(CiclosEstadoHistorial(
                grupo_id=g.id, benchmark_id=b.id, semana=p["fecha"], cuadrante=p["cuadrante"], rs_ratio=p["rs_ratio"],
                rs_momentum=p["rs_momentum"], version_algoritmo=eng.VERSION_ALGORITMO, ultima_fecha_datos=rot["ultima_fecha"],
                calculado_en=ahora,
            ))
    if nuevas:
        if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
            logger.warning("ciclos: el sync no soltó el lock; no se registra el historial en esta corrida")
            db.rollback()
            return {"filas_nuevas": 0, "omitidos": omitidos, "resultado": "lock_ocupado"}
        try:
            db.add_all(nuevas)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            sync_lock.lock.release()
    else:
        db.rollback()
    return {"filas_nuevas": len(nuevas), "omitidos": omitidos, "resultado": "ok"}


def historial_de(db: Session, grupo_id: str, benchmark_id: str) -> list[dict]:
    """Las semanas guardadas de un grupo contra un benchmark, para `ciclos_senales_engine.detectar`."""
    filas = (db.query(CiclosEstadoHistorial)
             .filter(CiclosEstadoHistorial.grupo_id == grupo_id, CiclosEstadoHistorial.benchmark_id == benchmark_id,
                     CiclosEstadoHistorial.version_algoritmo == eng.VERSION_ALGORITMO)
             .order_by(CiclosEstadoHistorial.semana).all())
    return [{"semana": f.semana, "cuadrante": f.cuadrante} for f in filas]
