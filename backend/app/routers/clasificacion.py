"""Clasificación de instrumentos (región, sector, tipo, industria) y valuación contra pares.

Los datos salen de Yahoo vía una ingesta gradual (`services/fundamentales_ingesta.py`) que corre
sola dos veces por día; estos endpoints muestran su estado y permiten dispararla a mano.
"""
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import (
    ActualizarClasificacionIn, ActualizarClasificacionOut, ClasificacionCorreccionIn,
    ClasificacionTickerOut, ComparadorAlternativasOut, DiferenciaClasificacionOut, EstadoClasificacionOut, ParCorreccionIn,
    ValuacionListaOut, ValuacionTickerOut,
)
from ..services import (
    clasificacion_analytics, comparador_analytics, comparador_engine, fundamentales_ingesta, scheduler,
    valuacion_analytics,
)

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


def _corrida_en_segundo_plano(tickers: list[str] | None = None) -> None:
    db = SessionLocal()
    try:
        fundamentales_ingesta.correr(db, tickers=tickers, pausa_seg=0 if tickers else None)
    except Exception:  # pragma: no cover - se loguea dentro; un hilo no puede propagar
        fundamentales_ingesta.logger.exception("fundamentales: la corrida manual falló")
        db.rollback()
    finally:
        db.close()


def pedir_datos_en_segundo_plano(tickers: list[str]) -> None:
    """Para el alta en watchlist: que el ticker nuevo tenga clasificación y fundamentales sin
    esperar al job de la noche. Best-effort: si Yahoo falla, lo trae la corrida programada."""
    from ..services.market_data.client import use_external_apis

    if tickers and use_external_apis():
        threading.Thread(
            target=_corrida_en_segundo_plano, args=(tickers[: fundamentales_ingesta.MAX_TICKERS_SINCRONICO],),
            daemon=True, name="fundamentales-alta",
        ).start()


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


@router.get("/valuacion/{ticker}/comparador", response_model=ComparadorAlternativasOut)
def valuacion_comparador(ticker: str, con: str = Query("", description="Alternativas separadas por coma"),
                         db: Session = Depends(get_db)):
    """"¿Qué compraría en su lugar?": el ticker contra alternativas comparables, incluso fuera de su
    grupo de pares. Sin `con` usa su grupo de pares; con `con=A,B` compara contra esas."""
    elegidas = list(dict.fromkeys(t.strip().upper() for t in con.split(",") if t.strip()))
    if len(elegidas) > comparador_engine.MAX_ALTERNATIVAS:
        raise HTTPException(status_code=422, detail=f"con admite hasta {comparador_engine.MAX_ALTERNATIVAS} alternativas")
    return comparador_analytics.get_comparador(ticker.strip().upper(), tuple(elegidas), db)


# ── Correcciones manuales ────────────────────────────────────────────────────
# Van después de las rutas fijas (`/clasificacion/estado`, `/diferencias`, `/actualizar`) para que
# `{ticker}` no se las trague.

@router.get("/clasificacion/{ticker}", response_model=ClasificacionTickerOut)
def clasificacion_ticker(ticker: str, db: Session = Depends(get_db)):
    """Clasificación resuelta de un ticker, con lo que dice cada fuente y las correcciones."""
    return clasificacion_analytics.get_clasificacion_ticker(db, ticker.strip().upper())


@router.put("/clasificacion/{ticker}", response_model=ClasificacionTickerOut)
def corregir_clasificacion(ticker: str, body: ClasificacionCorreccionIn, db: Session = Depends(get_db)):
    """Corrige a mano uno o más campos. La corrección es del emisor: vale para todas sus
    variantes de moneda (corregir `AAPLD` corrige `AAPL`)."""
    t = ticker.strip().upper()
    try:
        clasificacion_analytics.corregir(db, t, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return clasificacion_analytics.get_clasificacion_ticker(db, t)


@router.delete("/clasificacion/{ticker}/{campo}", response_model=ClasificacionTickerOut)
def borrar_correccion_clasificacion(ticker: str, campo: str, db: Session = Depends(get_db)):
    """Vuelve un campo a la clasificación automática (o al Sheet)."""
    t = ticker.strip().upper()
    if campo not in clasificacion_analytics.CAMPOS_CORREGIBLES:
        raise HTTPException(status_code=422, detail=f"campo debe ser uno de {clasificacion_analytics.CAMPOS_CORREGIBLES}")
    clasificacion_analytics.borrar_correccion(db, t, campo)
    return clasificacion_analytics.get_clasificacion_ticker(db, t)


@router.post("/pares/{ticker}", response_model=ValuacionTickerOut)
def corregir_par(ticker: str, body: ParCorreccionIn, db: Session = Depends(get_db)):
    """Agrega o quita un par del grupo de comparables. Devuelve la ficha de valuación recalculada.
    Un par agregado que todavía no tiene datos entra en la próxima corrida de la ingesta."""
    t = ticker.strip().upper()
    try:
        clasificacion_analytics.corregir_par(db, t, body.par, body.accion)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return valuacion_analytics.get_valuacion_ticker(t, db)


@router.delete("/pares/{ticker}/{par}", response_model=ValuacionTickerOut)
def borrar_correccion_par(ticker: str, par: str, db: Session = Depends(get_db)):
    """Deshace un agregado o un quitado: el par vuelve a lo que diga el criterio automático."""
    t = ticker.strip().upper()
    clasificacion_analytics.borrar_correccion_par(db, t, par)
    return valuacion_analytics.get_valuacion_ticker(t, db)
