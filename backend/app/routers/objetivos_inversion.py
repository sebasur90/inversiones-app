from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db, ObjetivoInversion
from ..schemas import ObjetivoInversionCreate, ObjetivoInversionUpdate, ObjetivoInversionOut, AportesHistoricosOut
from ..services.inversiones_analytics import get_aportes_historicos, get_progreso_objetivo

router = APIRouter(prefix="/api/inversiones", tags=["inversiones"])


@router.get("/carteras/{nombre}/aportes-historicos", response_model=AportesHistoricosOut)
def fetch_aportes_historicos(nombre: str, db: Session = Depends(get_db)):
    """Obtiene el histórico de aportes netos acumulados para una cartera."""
    return get_aportes_historicos(nombre, db)


@router.get("/carteras/{nombre}/objetivo", response_model=ObjetivoInversionOut)
def fetch_objetivo(nombre: str, db: Session = Depends(get_db)):
    """Obtiene el objetivo de inversión de una cartera, incluyendo progreso."""
    objetivo = db.query(ObjetivoInversion).filter(ObjetivoInversion.cartera == nombre).first()
    if not objetivo:
        raise HTTPException(status_code=404, detail="No existe un objetivo para esta cartera")

    progreso = get_progreso_objetivo(nombre, objetivo.id, db)
    if not progreso:
        raise HTTPException(status_code=404, detail="No existe un objetivo para esta cartera")

    return ObjetivoInversionOut(
        id=objetivo.id,
        cartera=objetivo.cartera,
        nombre=objetivo.nombre,
        icono=objetivo.icono,
        monto_usd=float(objetivo.monto_usd),
        fecha_limite=objetivo.fecha_limite,
        valor_actual_usd=progreso["valor_actual_usd"],
        aporte_mensual_promedio_usd=progreso["aporte_mensual_promedio_usd"],
        aporte_mensual_necesario_usd=progreso["aporte_mensual_necesario_usd"],
        meses_restantes=progreso["meses_restantes"],
        proyeccion_usd=progreso["proyeccion_usd"],
        alcanzable=progreso["alcanzable"],
        deficit_usd=progreso["deficit_usd"],
    )


@router.post("/carteras/{nombre}/objetivo", response_model=ObjetivoInversionOut)
def crear_objetivo(nombre: str, payload: ObjetivoInversionCreate, db: Session = Depends(get_db)):
    """Crea un nuevo objetivo de inversión para una cartera."""
    existente = db.query(ObjetivoInversion).filter(ObjetivoInversion.cartera == nombre).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe un objetivo para esta cartera")

    objetivo = ObjetivoInversion(
        cartera=nombre,
        nombre=payload.nombre,
        icono=payload.icono,
        monto_usd=payload.monto_usd,
        fecha_limite=payload.fecha_limite,
    )
    db.add(objetivo)
    db.commit()
    db.refresh(objetivo)

    progreso = get_progreso_objetivo(nombre, objetivo.id, db)
    if not progreso:
        raise HTTPException(status_code=500, detail="Error calculando progreso")

    return ObjetivoInversionOut(
        id=objetivo.id,
        cartera=objetivo.cartera,
        nombre=objetivo.nombre,
        icono=objetivo.icono,
        monto_usd=float(objetivo.monto_usd),
        fecha_limite=objetivo.fecha_limite,
        valor_actual_usd=progreso["valor_actual_usd"],
        aporte_mensual_promedio_usd=progreso["aporte_mensual_promedio_usd"],
        aporte_mensual_necesario_usd=progreso["aporte_mensual_necesario_usd"],
        meses_restantes=progreso["meses_restantes"],
        proyeccion_usd=progreso["proyeccion_usd"],
        alcanzable=progreso["alcanzable"],
        deficit_usd=progreso["deficit_usd"],
    )


@router.put("/objetivos-inversion/{objetivo_id}", response_model=ObjetivoInversionOut)
def editar_objetivo(objetivo_id: int, payload: ObjetivoInversionUpdate, db: Session = Depends(get_db)):
    """Edita un objetivo de inversión existente."""
    objetivo = db.query(ObjetivoInversion).filter(ObjetivoInversion.id == objetivo_id).first()
    if not objetivo:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")

    objetivo.nombre = payload.nombre
    objetivo.icono = payload.icono
    objetivo.monto_usd = payload.monto_usd
    objetivo.fecha_limite = payload.fecha_limite
    db.commit()
    db.refresh(objetivo)

    progreso = get_progreso_objetivo(objetivo.cartera, objetivo.id, db)
    if not progreso:
        raise HTTPException(status_code=500, detail="Error calculando progreso")

    return ObjetivoInversionOut(
        id=objetivo.id,
        cartera=objetivo.cartera,
        nombre=objetivo.nombre,
        icono=objetivo.icono,
        monto_usd=float(objetivo.monto_usd),
        fecha_limite=objetivo.fecha_limite,
        valor_actual_usd=progreso["valor_actual_usd"],
        aporte_mensual_promedio_usd=progreso["aporte_mensual_promedio_usd"],
        aporte_mensual_necesario_usd=progreso["aporte_mensual_necesario_usd"],
        meses_restantes=progreso["meses_restantes"],
        proyeccion_usd=progreso["proyeccion_usd"],
        alcanzable=progreso["alcanzable"],
        deficit_usd=progreso["deficit_usd"],
    )


@router.delete("/objetivos-inversion/{objetivo_id}")
def eliminar_objetivo(objetivo_id: int, db: Session = Depends(get_db)):
    """Elimina un objetivo de inversión."""
    objetivo = db.query(ObjetivoInversion).filter(ObjetivoInversion.id == objetivo_id).first()
    if not objetivo:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")

    db.delete(objetivo)
    db.commit()
    return {"mensaje": "Objetivo eliminado correctamente"}
