"""Clasificación de instrumentos (región, sector, tipo, industria) y valuación contra pares.

Los datos salen de Yahoo vía una ingesta gradual (`services/fundamentales_ingesta.py`) que corre
sola dos veces por día; estos endpoints muestran su estado y permiten dispararla a mano.
"""
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import (
    ActualizarClasificacionIn, ActualizarClasificacionOut, DiferenciaClasificacionOut,
    EstadoClasificacionOut, ValuacionListaOut, ValuacionTickerOut,
)
from ..services import clasificacion_analytics, fundamentales_ingesta, scheduler, valuacion_analytics

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


@router.get("/clasificacion/diferencias", response_model=list[DiferenciaClasificacionOut])
def diferencias_clasificacion(db: Session = Depends(get_db)):
    """Tickers de cartera y watchlist cuya clasificación resuelta difiere de la ficha del Sheet,
    con la fuente de cada cambio."""
    return clasificacion_analytics.diferencias(db)


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


# ── Valuación contra pares ───────────────────────────────────────────────────

@router.get("/valuacion", response_model=ValuacionListaOut)
def valuacion_lista(
    universo: str = Query("cartera"),
    tipo: str | None = None,
    sector: str | None = None,
    region: str | None = None,
    lectura: str | None = None,
    db: Session = Depends(get_db),
):
    """Lectura de valuación (más barata / más cara / en línea…) de cada emisor del universo:
    lo que hay en cartera, en la watchlist o todo el catálogo con datos."""
    if universo not in valuacion_analytics.UNIVERSOS:
        raise HTTPException(status_code=422, detail=f"universo debe ser uno de {valuacion_analytics.UNIVERSOS}")
    return valuacion_analytics.get_valuacion_lista(universo, db, tipo=tipo, sector=sector, region=region, lectura=lectura)


@router.get("/valuacion/{ticker}", response_model=ValuacionTickerOut)
def valuacion_ticker(ticker: str, db: Session = Depends(get_db)):
    """Ficha de valuación de un ticker contra sus pares: clasificación con fuentes, pares y el
    criterio con que se eligieron, tabla lado a lado, percentiles, frases y fuerza relativa."""
    return valuacion_analytics.get_valuacion_ticker(ticker.strip().upper(), db)
