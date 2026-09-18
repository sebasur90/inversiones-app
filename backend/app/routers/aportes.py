"""Ritmo de aportes: cuánto capital nuevo entra mes a mes, rachas, récords y proyección anual."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import RitmoAportesOut
from ..services.aportes_analytics import get_ritmo_aportes
from .inversiones import _validar_cartera

router = APIRouter(prefix="/api/inversiones", tags=["inversiones"])


@router.get("/carteras/{nombre}/aportes/ritmo", response_model=RitmoAportesOut)
def ritmo_aportes_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_ritmo_aportes(nombre, db)


@router.get("/consolidado/aportes/ritmo", response_model=RitmoAportesOut)
def ritmo_aportes_consolidado(db: Session = Depends(get_db)):
    return get_ritmo_aportes(None, db)
