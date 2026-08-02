from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db, MovimientoInversion
from ..schemas import (
    SyncResult,
    CarteraInfo,
    InversionesResumen,
    ExposicionOut,
    MovimientoInversionOut,
    RendimientoPorTickerItem,
)
from ..services.sheets_client import SheetsClientError
from ..services.inversiones_sync import sync_from_sheet, get_ultimo_sync
from ..services.inversiones_analytics import get_carteras, get_resumen, get_exposicion

router = APIRouter(prefix="/api/inversiones", tags=["inversiones"])


@router.post("/sync", response_model=SyncResult)
def sync(db: Session = Depends(get_db)):
    try:
        result = sync_from_sheet(db)
    except SheetsClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/carteras", response_model=list[CarteraInfo])
def list_carteras(db: Session = Depends(get_db)):
    ultimo_sync = get_ultimo_sync()
    ultimo_sync_str = ultimo_sync.isoformat() if ultimo_sync else None
    return [CarteraInfo(nombre=nombre, ultimo_sync=ultimo_sync_str) for nombre in get_carteras(db)]


def _validar_cartera(nombre: str, db: Session) -> None:
    existe = db.query(MovimientoInversion).filter(MovimientoInversion.cartera == nombre).first()
    if not existe:
        raise HTTPException(status_code=404, detail=f"Cartera '{nombre}' no encontrada")


@router.get("/carteras/{nombre}/resumen", response_model=InversionesResumen)
def resumen_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_resumen(nombre, db)


@router.get("/consolidado/resumen", response_model=InversionesResumen)
def resumen_consolidado(db: Session = Depends(get_db)):
    return get_resumen(None, db)


@router.get("/carteras/{nombre}/exposicion", response_model=ExposicionOut)
def exposicion_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_exposicion(nombre, db)


@router.get("/consolidado/exposicion", response_model=ExposicionOut)
def exposicion_consolidado(db: Session = Depends(get_db)):
    return get_exposicion(None, db)


@router.get("/movimientos", response_model=list[MovimientoInversionOut])
def list_movimientos(
    cartera: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(MovimientoInversion)
    if cartera:
        q = q.filter(MovimientoInversion.cartera == cartera)
    if ticker:
        q = q.filter(MovimientoInversion.ticker == ticker)
    return q.order_by(MovimientoInversion.fecha.desc(), MovimientoInversion.id.desc()).all()


@router.get("/carteras/{nombre}/rendimiento-por-ticker", response_model=list[RendimientoPorTickerItem])
def rendimiento_por_ticker(nombre: str, db: Session = Depends(get_db)):
    """Rendimiento individual por ticker en una cartera."""
    from ..services.inversiones_analytics import get_rendimiento_por_ticker

    _validar_cartera(nombre, db)
    return get_rendimiento_por_ticker(nombre, db)


@router.get("/consolidado/rendimiento-por-ticker", response_model=list[RendimientoPorTickerItem])
def rendimiento_por_ticker_consolidado(db: Session = Depends(get_db)):
    """Rendimiento individual por ticker consolidado."""
    from ..services.inversiones_analytics import get_rendimiento_por_ticker

    return get_rendimiento_por_ticker(None, db)
