"""Ritmo de aportes: cuánto capital nuevo entra mes a mes, rachas, récords y proyección anual."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ObjetivoAporteIn, ObjetivoAporteOut, RitmoAportesOut
from ..services import objetivo_aporte_analytics
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


# ── Objetivo de aporte mensual ───────────────────────────────────────────────
# Lo fija el usuario desde la pantalla. `cartera=None` = consolidado, y es una meta distinta de
# la de cada cartera: no se suman ni se heredan.

def _objetivo_out(cartera: str | None, datos: dict) -> ObjetivoAporteOut:
    return ObjetivoAporteOut(
        cartera=cartera,
        monto_usd=datos["monto_usd"],
        vigente_desde=datos["vigente_desde"],
        retroactivo=datos["retroactivo"],
    )


# No tener objetivo es un estado válido, no un error: 204 en vez de 404. Devolver una `Response`
# directa, y no `None`, evita que FastAPI valide el cuerpo vacío contra el `response_model`.
SIN_OBJETIVO = {204: {"description": "No hay objetivo configurado"}}


@router.get("/carteras/{nombre}/aportes/objetivo", response_model=ObjetivoAporteOut,
            responses=SIN_OBJETIVO)
def objetivo_aporte_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    datos = objetivo_aporte_analytics.get_objetivo(nombre, db)
    if datos is None:
        return Response(status_code=204)
    return _objetivo_out(nombre, datos)


@router.put("/carteras/{nombre}/aportes/objetivo", response_model=ObjetivoAporteOut)
def guardar_objetivo_cartera(nombre: str, body: ObjetivoAporteIn, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    datos = objetivo_aporte_analytics.guardar_objetivo(
        nombre, body.monto_usd, db, retroactivo=body.retroactivo
    )
    return _objetivo_out(nombre, datos)


@router.delete("/carteras/{nombre}/aportes/objetivo", status_code=204)
def eliminar_objetivo_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    objetivo_aporte_analytics.eliminar_objetivo(nombre, db)


@router.get("/consolidado/aportes/objetivo", response_model=ObjetivoAporteOut,
            responses=SIN_OBJETIVO)
def objetivo_aporte_consolidado(db: Session = Depends(get_db)):
    datos = objetivo_aporte_analytics.get_objetivo(None, db)
    if datos is None:
        return Response(status_code=204)
    return _objetivo_out(None, datos)


@router.put("/consolidado/aportes/objetivo", response_model=ObjetivoAporteOut)
def guardar_objetivo_consolidado(body: ObjetivoAporteIn, db: Session = Depends(get_db)):
    datos = objetivo_aporte_analytics.guardar_objetivo(
        None, body.monto_usd, db, retroactivo=body.retroactivo
    )
    return _objetivo_out(None, datos)


@router.delete("/consolidado/aportes/objetivo", status_code=204)
def eliminar_objetivo_consolidado(db: Session = Depends(get_db)):
    objetivo_aporte_analytics.eliminar_objetivo(None, db)
