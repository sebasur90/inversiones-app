"""Calendario de eventos de mercado: eventos pasados y futuros, noticias, vínculos con instrumentos,
sincronización de fuentes y comportamiento observado del precio alrededor de cada evento.

Ningún endpoint escribe movimientos, precios ni nada en la planilla: la fuente de verdad de la cartera
sigue siendo el Google Sheet. Las consultas a proveedores externos salen sólo del backend.
"""
import threading
from datetime import date, time
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..schemas import (
    EventoAnalisisOut, EventoDetalleOut, EventoFusionIn, EventoImpactoOut, EventoIn, EventoPatchIn, EventoPatronOut,
    EventosFuentesOut, EventosImportarOut, EventosListaOut, EventosOpcionesOut, EventoTickerUniversoOut,
    EventoVinculoIn, EventoVinculoOut, NoticiaAsociarIn, NoticiaCrearEventoIn, NoticiaEventoOut,
    NoticiasEventoListaOut,
)
from ..services.eventos import eventos_analytics as ea
from ..services.eventos import eventos_sync, impacto_analytics, importacion
from ..services.eventos import CATEGORIAS

router = APIRouter(prefix="/api/inversiones", tags=["eventos"])


def _error(codigo: str):
    raise HTTPException(status_code=422, detail=ea.MENSAJE_ERROR.get(codigo, codigo))


def _evento(db: Session, evento_id: int):
    try:
        return ea.obtener(db, evento_id)
    except ea.EventoNoEncontrado:
        raise HTTPException(status_code=404, detail="Evento no encontrado")


def _noticia(db: Session, noticia_id: int):
    try:
        return ea.obtener_noticia(db, noticia_id)
    except ea.EventoNoEncontrado:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")


def _hora(valor: Optional[str]) -> Optional[time]:
    if not valor:
        return None
    h, m = valor.split(":")
    return time(int(h), int(m))


def _datos(body, parcial: bool) -> dict:
    datos = body.model_dump(exclude_unset=parcial)
    if "hora_evento" in datos:
        datos["hora_evento"] = _hora(datos["hora_evento"])
    if datos.get("instrumentos") is not None:
        datos["instrumentos"] = [dict(v) for v in datos["instrumentos"]]
    if parcial:
        # En una edición, `null` en un campo de texto lo vacía; en una marca, no cambia nada.
        for marca in ("fijado", "descartado", "programado", "importancia", "categoria", "fecha_evento",
                      "precision_fecha", "verificacion", "estado", "titulo"):
            if marca in datos and datos[marca] is None:
                datos.pop(marca)
    elif datos.get("estado") is None:
        datos.pop("estado", None)
    return datos


def _lista(valor: Optional[list[str]]) -> Optional[list[str]]:
    """Acepta tanto `?x=a&x=b` como `?x=a,b`."""
    if not valor:
        return None
    out = [p.strip() for v in valor for p in v.split(",") if p.strip()]
    return out or None


@router.get("/eventos", response_model=EventosListaOut)
def listar_eventos(
    desde: Optional[date] = None, hasta: Optional[date] = None,
    categoria: Optional[list[str]] = Query(default=None), pais: Optional[list[str]] = Query(default=None),
    ticker: Optional[list[str]] = Query(default=None), sector: Optional[list[str]] = Query(default=None),
    en_cartera: bool = False, importancia_min: Optional[int] = Query(default=None, ge=1, le=3),
    verificacion: Optional[list[str]] = Query(default=None), origen: Optional[list[str]] = Query(default=None),
    proveedor: Optional[list[str]] = Query(default=None),
    temporalidad: str = Query(default="todos", pattern="^(todos|pasados|futuros)$"),
    q: Optional[str] = Query(default=None, max_length=200), incluir_descartados: bool = False,
    orden: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1), limite: int = Query(default=100, ge=1, le=ea.LIMITE_MAXIMO),
    db: Session = Depends(get_db),
):
    if desde and hasta and hasta < desde:
        raise HTTPException(status_code=422, detail="'hasta' no puede ser anterior a 'desde'")
    tickers_cartera = None
    if en_cartera:
        from ..services.watchlist_analytics import _tickers_en_cartera
        tickers_cartera = {t.upper() for t in _tickers_en_cartera(db, date.today())}
    return ea.listar(
        db, desde=desde, hasta=hasta, categorias=_lista(categoria), paises=_lista(pais), tickers=_lista(ticker),
        sectores=_lista(sector), tickers_cartera=tickers_cartera, importancia_min=importancia_min,
        verificaciones=_lista(verificacion), origenes=_lista(origen), proveedores=_lista(proveedor),
        temporalidad=temporalidad, q=q, incluir_descartados=incluir_descartados, orden=orden,
        page=page, limite=limite,
    )


@router.get("/eventos/opciones", response_model=EventosOpcionesOut)
def opciones_eventos(db: Session = Depends(get_db)):
    return ea.opciones(db)


@router.get("/eventos/fuentes", response_model=EventosFuentesOut)
def fuentes_eventos(db: Session = Depends(get_db)):
    """Qué proveedores están configurados, cuándo corrieron, qué pasó y cuánto cupo gastaron. Sin secretos."""
    return eventos_sync.estado_fuentes(db)


def _sincronizar_en_segundo_plano() -> None:
    db = SessionLocal()
    try:
        eventos_sync.correr(db)
    except Exception:  # pragma: no cover - se loguea dentro; un hilo no puede propagar
        eventos_sync.logger.exception("eventos: la sincronización manual falló")
        db.rollback()
    finally:
        db.close()


@router.post("/eventos/sincronizar", status_code=202)
def sincronizar_eventos():
    """Consulta ya mismo a los proveedores configurados. Responde enseguida; el estado se ve en `/eventos/fuentes`."""
    if eventos_sync.en_curso():
        raise HTTPException(status_code=409, detail="Ya hay una sincronización de eventos en curso")
    threading.Thread(target=_sincronizar_en_segundo_plano, daemon=True, name="eventos").start()
    return {"resultado": "iniciado"}


@router.post("/eventos/importar", response_model=EventosImportarOut)
def importar_eventos(datos: Any = Body(...), db: Session = Depends(get_db)):
    """Importa eventos con el formato de `services/eventos/importacion.py` (lista o `{"eventos": [...]}`).
    Idempotente por `id`: reimportar el mismo archivo actualiza en vez de duplicar."""
    crudos, errores = importacion.parsear(datos, proveedor="subida", origen="importacion", hoy=date.today())
    try:
        universo = eventos_sync.construir_universo(db)
    except Exception:
        eventos_sync.logger.exception("eventos: no se pudo armar el universo para la importación")
        universo = eventos_sync.Universo()
    cuenta = eventos_sync.incorporar_eventos(db, crudos, universo, date.today())
    db.commit()
    total = len(crudos) + len(errores)
    return {"recibidos": total, "errores": errores[:50], **{k: v for k, v in cuenta.items() if k in (
        "nuevos", "actualizados", "sin_cambios", "omitidos", "duplicados")}}


def _ticker(t: str) -> str:
    n = ea.normalizar_ticker(t)
    if n is None:
        raise HTTPException(status_code=422, detail="el ticker no es válido")
    return n


_BENCHMARK = "^(auto|ninguno|SPY|QQQ|\\^MERV)$"


@router.get("/eventos/impacto/universo", response_model=list[EventoTickerUniversoOut])
def universo_impacto(db: Session = Depends(get_db)):
    """Los tickers que se pueden analizar: cartera ∪ watchlist y los benchmarks."""
    return impacto_analytics.universo_tickers(db)


@router.get("/eventos/impacto/{ticker}", response_model=EventoImpactoOut)
def impacto_ticker(
    ticker: str, desde: Optional[date] = None, hasta: Optional[date] = None,
    categoria: Optional[list[str]] = Query(default=None), importancia_min: Optional[int] = Query(default=None, ge=1, le=3),
    benchmark: str = Query(default="auto", pattern=_BENCHMARK), incluir_generales: bool = True,
    db: Session = Depends(get_db),
):
    """Serie del ticker con los eventos marcados. La serie termina en la última cotización real; los eventos
    posteriores vuelven con `futuro=true` y sin precio."""
    try:
        return impacto_analytics.impacto(
            db, _ticker(ticker), desde=desde, hasta=hasta, categorias=_lista(categoria), importancia_min=importancia_min,
            benchmark=benchmark, incluir_generales=incluir_generales,
        )
    except impacto_analytics.TickerSinSerie:
        raise HTTPException(status_code=404, detail="El ticker no está en la cartera ni en la watchlist: agregalo para bajar su serie")


@router.get("/eventos/patron/{ticker}", response_model=EventoPatronOut)
def patron_ticker(ticker: str, categoria: str, n: int = Query(default=5, ge=1, le=60), db: Session = Depends(get_db)):
    """Cómo se comportó el ticker después de los eventos de una categoría, contra su línea de base."""
    if categoria not in CATEGORIAS:
        raise HTTPException(status_code=422, detail="La categoría no es válida")
    try:
        return impacto_analytics.patron_categoria(db, _ticker(ticker), categoria, n)
    except impacto_analytics.TickerSinSerie:
        raise HTTPException(status_code=404, detail="El ticker no está en la cartera ni en la watchlist")


@router.get("/eventos/noticias", response_model=NoticiasEventoListaOut)
def listar_noticias(
    estado: str = Query(default="por_revisar", pattern="^(por_revisar|asociada|descartada)$"),
    page: int = Query(default=1, ge=1), limite: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return ea.listar_noticias(db, estado, page, limite)


@router.post("/eventos/noticias/{noticia_id}/asociar", response_model=NoticiaEventoOut)
def asociar_noticia(noticia_id: int, body: NoticiaAsociarIn, db: Session = Depends(get_db)):
    n = _noticia(db, noticia_id)
    e = _evento(db, body.evento_id)
    ea.asociar_noticia(db, n, e)
    return ea.noticia_a_dict(n)


@router.post("/eventos/noticias/{noticia_id}/crear-evento", response_model=EventoDetalleOut, status_code=201)
def crear_evento_desde_noticia(noticia_id: int, body: NoticiaCrearEventoIn, db: Session = Depends(get_db)):
    n = _noticia(db, noticia_id)
    e, error = ea.crear_evento_desde_noticia(db, n, body.model_dump(exclude_unset=True))
    if error:
        _error(error)
    return ea.detalle(db, e.id)


@router.post("/eventos/noticias/{noticia_id}/descartar", response_model=NoticiaEventoOut)
def descartar_noticia(noticia_id: int, db: Session = Depends(get_db)):
    n = _noticia(db, noticia_id)
    ea.descartar_noticia(db, n)
    return ea.noticia_a_dict(n)


@router.get("/eventos/{evento_id}", response_model=EventoDetalleOut)
def detalle_evento(evento_id: int, db: Session = Depends(get_db)):
    _evento(db, evento_id)
    return ea.detalle(db, evento_id)


@router.get("/eventos/{evento_id}/analisis", response_model=list[EventoAnalisisOut])
def analisis_evento(evento_id: int, benchmark: str = Query(default="auto", pattern=_BENCHMARK), db: Session = Depends(get_db)):
    """El comportamiento observado de cada instrumento vinculado al evento."""
    _evento(db, evento_id)
    return impacto_analytics.analisis_evento(db, evento_id, benchmark)


@router.get("/eventos/{evento_id}/analisis/{ticker}", response_model=EventoAnalisisOut)
def analisis_evento_ticker(evento_id: int, ticker: str, benchmark: str = Query(default="auto", pattern=_BENCHMARK),
                           db: Session = Depends(get_db)):
    _evento(db, evento_id)
    try:
        return impacto_analytics.analisis(db, evento_id, _ticker(ticker), benchmark)
    except impacto_analytics.TickerSinSerie:
        raise HTTPException(status_code=404, detail="El ticker no está en la cartera ni en la watchlist")


@router.post("/eventos", response_model=EventoDetalleOut, status_code=201)
def crear_evento(body: EventoIn, db: Session = Depends(get_db)):
    e, error = ea.crear(db, _datos(body, parcial=False))
    if error:
        _error(error)
    return ea.detalle(db, e.id)


@router.patch("/eventos/{evento_id}", response_model=EventoDetalleOut)
def editar_evento(evento_id: int, body: EventoPatchIn, db: Session = Depends(get_db)):
    e = _evento(db, evento_id)
    error = ea.editar(db, e, _datos(body, parcial=True))
    if error:
        _error(error)
    return ea.detalle(db, e.id)


@router.delete("/eventos/{evento_id}")
def borrar_evento(evento_id: int, db: Session = Depends(get_db)):
    """Un evento manual se borra (204). Uno importado queda descartado (200 + `{"resultado": "descartado"}`)
    para que la próxima sincronización no lo vuelva a crear."""
    e = _evento(db, evento_id)
    resultado = ea.borrar(db, e)
    if resultado == "borrado":
        return Response(status_code=204)
    return {"resultado": resultado}


@router.post("/eventos/{evento_id}/fusionar", response_model=EventoDetalleOut)
def fusionar_evento(evento_id: int, body: EventoFusionIn, db: Session = Depends(get_db)):
    """Absorbe este evento en `destino_id` (duplicados). Devuelve el destino."""
    origen = _evento(db, evento_id)
    destino = _evento(db, body.destino_id)
    error = ea.fusionar(db, origen, destino)
    if error:
        _error(error)
    return ea.detalle(db, destino.id)


@router.put("/eventos/{evento_id}/instrumentos/{ticker}", response_model=EventoVinculoOut)
def guardar_vinculo(evento_id: int, ticker: str, body: EventoVinculoIn, db: Session = Depends(get_db)):
    e = _evento(db, evento_id)
    fila, error = ea.guardar_vinculo(db, e, ticker, body.model_dump(exclude={"ticker"}))
    if error:
        _error(error)
    return ea.vinculo_a_dict(fila)


@router.delete("/eventos/{evento_id}/instrumentos/{ticker}", status_code=204)
def quitar_vinculo(evento_id: int, ticker: str, db: Session = Depends(get_db)):
    e = _evento(db, evento_id)
    if not ea.quitar_vinculo(db, e, ticker):
        raise HTTPException(status_code=404, detail="El evento no tiene ese instrumento")
    return Response(status_code=204)
