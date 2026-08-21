from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db, ObjetivoInversion
from ..schemas import ObjetivoInversionOut, AportesHistoricosOut
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
        aporte_mensual_esperado_usd=progreso["aporte_mensual_esperado_usd"],
        meses_restantes=progreso["meses_restantes"],
        proyeccion_usd=progreso["proyeccion_usd"],
        alcanzable=progreso["alcanzable"],
        deficit_usd=progreso["deficit_usd"],
        desviacion_usd=progreso["desviacion_usd"],
        desviacion_pct=progreso["desviacion_pct"],
        adelantado=progreso["adelantado"],
        aportado_a_la_fecha_usd=progreso["aportado_a_la_fecha_usd"],
        esperado_a_la_fecha_usd=progreso["esperado_a_la_fecha_usd"],
    )


