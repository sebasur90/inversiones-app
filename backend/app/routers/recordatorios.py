"""Recordatorios con fecha: el usuario se deja un aviso para un día y el job lo manda por Telegram."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import Recordatorio, get_db
from ..schemas import RecordatorioIn, RecordatorioOut, RecordatorioPatchIn, RecordatorioPosponerIn, RecordatoriosListaOut
from ..services import recordatorios as servicio

router = APIRouter(prefix="/api/inversiones", tags=["recordatorios"])


def _error(codigo: str):
    raise HTTPException(status_code=422, detail=servicio.MENSAJE_ERROR.get(codigo, codigo))


def _recordatorio(db: Session, recordatorio_id: int) -> Recordatorio:
    try:
        return servicio.obtener(db, recordatorio_id)
    except servicio.RecordatorioNoEncontrado:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")


@router.get("/recordatorios", response_model=RecordatoriosListaOut)
def listar_recordatorios(db: Session = Depends(get_db)):
    return servicio.listar(db)


@router.post("/recordatorios", response_model=RecordatorioOut, status_code=201)
def crear_recordatorio(body: RecordatorioIn, db: Session = Depends(get_db)):
    r, error = servicio.crear(db, body.model_dump())
    if error:
        _error(error)
    return servicio.detalle(db, r)


@router.patch("/recordatorios/{recordatorio_id}", response_model=RecordatorioOut)
def editar_recordatorio(recordatorio_id: int, body: RecordatorioPatchIn, db: Session = Depends(get_db)):
    r = _recordatorio(db, recordatorio_id)
    error = servicio.editar(db, r, body.model_dump(exclude_unset=True))
    if error:
        _error(error)
    return servicio.detalle(db, r)


@router.post("/recordatorios/{recordatorio_id}/posponer", response_model=RecordatorioOut)
def posponer_recordatorio(recordatorio_id: int, body: RecordatorioPosponerIn, db: Session = Depends(get_db)):
    r = _recordatorio(db, recordatorio_id)
    error = servicio.posponer(db, r, body.dias)
    if error:
        _error(error)
    return servicio.detalle(db, r)


@router.delete("/recordatorios/{recordatorio_id}", status_code=204)
def borrar_recordatorio(recordatorio_id: int, db: Session = Depends(get_db)):
    servicio.borrar(db, _recordatorio(db, recordatorio_id))
    return Response(status_code=204)
