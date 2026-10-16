"""Clasificación de instrumentos (región, sector, tipo, industria) y valuación contra pares.

Los datos salen de Yahoo vía una ingesta gradual (`services/fundamentales_ingesta.py`) que corre
sola dos veces por día; estos endpoints muestran su estado y permiten dispararla a mano.
"""
import threading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import (
    ActualizarClasificacionIn, ActualizarClasificacionOut, EstadoClasificacionOut,
)
from ..services import fundamentales_ingesta, scheduler

router = APIRouter(prefix="/api/inversiones", tags=["clasificacion"])


@router.get("/clasificacion/estado", response_model=EstadoClasificacionOut)
def estado_clasificacion(db: Session = Depends(get_db)):
    """Cobertura de datos (cuántos emisores del universo ya tienen clasificación y fundamentales)
    y la última corrida de la ingesta."""
    return EstadoClasificacionOut(
        cobertura=fundamentales_ingesta.cobertura(db),
        ultima_corrida=fundamentales_ingesta.ultima_corrida(db),
        horas_programadas=scheduler._horas_fundamentales() if scheduler.habilitado() else "",
    )


@router.post("/clasificacion/actualizar", response_model=ActualizarClasificacionOut)
def actualizar_clasificacion(body: ActualizarClasificacionIn, db: Session = Depends(get_db)):
    """Pide ya mismo a Yahoo los datos de hasta 5 tickers (el botón "Actualizar datos" de la
    ficha). Sincrónico: tarda unos segundos por ticker. Ignora frescura y backoff."""
    if not body.tickers:
        return ActualizarClasificacionOut(resultado="sin_tickers")
    resumen = fundamentales_ingesta.correr(db, tickers=body.tickers, pausa_seg=0)
    return ActualizarClasificacionOut(**{k: resumen.get(k, 0) for k in ("procesados", "ok", "fallidos")},
                                      resultado=resumen["resultado"])


def _corrida_en_segundo_plano() -> None:
    db = SessionLocal()
    try:
        fundamentales_ingesta.correr(db)
    except Exception:  # pragma: no cover - se loguea dentro; un hilo no puede propagar
        fundamentales_ingesta.logger.exception("fundamentales: la corrida manual falló")
        db.rollback()
    finally:
        db.close()


@router.post("/clasificacion/actualizar-lote", response_model=ActualizarClasificacionOut, status_code=202)
def actualizar_lote():
    """Dispara una corrida normal de la ingesta (la misma del job) en segundo plano. Responde al
    instante; el avance se ve en `GET /clasificacion/estado`."""
    threading.Thread(target=_corrida_en_segundo_plano, daemon=True, name="fundamentales-manual").start()
    return ActualizarClasificacionOut(resultado="iniciada")
