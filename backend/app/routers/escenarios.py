"""Router para simulaciones de escenarios."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas import (
    EscenarioSimulacionRequest,
    EscenarioSimulacionOut,
    EscenarioOut,
    EscenarioGuardarRequest,
    EscenarioVidaRequest,
    EscenarioVidaOut,
    DefaultsVidaOut,
)
from app.routers.inversiones import _validar_cartera
from app.services import escenarios_analytics
from app.services import vida_analytics
from app.services import vida_engine


router = APIRouter(prefix="/api/inversiones", tags=["inversiones"])


# ─── Constantes de validación ────────────────────────────────────────────────

MODOS_DIVIDENDOS_VALIDOS = ("reinvertir_total", "reinvertir_parcial", "retirar")
TIPOS_PRESET_VALIDOS = ("alcista", "bajista", "crisis", "personalizado")
TIPOS_VIDA_VALIDOS = vida_engine.TIPOS_VIDA
MONEDAS_VIDA_VALIDAS = vida_engine.MONEDAS_VALIDAS


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/scenarios/simulate", response_model=EscenarioSimulacionOut)
def simular_escenarios(
    body: EscenarioSimulacionRequest,
    cartera: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Simula múltiples escenarios contra el mismo snapshot."""
    if cartera is not None:
        _validar_cartera(cartera, db)

    # Validaciones explícitas
    for item in body.escenarios:
        if item.tipo_preset not in TIPOS_PRESET_VALIDOS:
            raise HTTPException(
                status_code=422,
                detail=f"tipo_preset inválido: {item.tipo_preset}. Válidos: {TIPOS_PRESET_VALIDOS}",
            )

        if item.tipo_preset == "personalizado" and item.parametros is None:
            raise HTTPException(
                status_code=422,
                detail="tipo_preset 'personalizado' requiere parametros",
            )

        if item.parametros and item.parametros.modo_dividendos not in MODOS_DIVIDENDOS_VALIDOS:
            raise HTTPException(
                status_code=422,
                detail=f"modo_dividendos inválido: {item.parametros.modo_dividendos}. Válidos: {MODOS_DIVIDENDOS_VALIDOS}",
            )

        if (item.parametros and
                item.parametros.modo_dividendos == "reinvertir_parcial" and
                item.parametros.pct_dividendo_reinvertido is None):
            raise HTTPException(
                status_code=422,
                detail="modo_dividendos 'reinvertir_parcial' requiere pct_dividendo_reinvertido",
            )

    resultado = escenarios_analytics.simular_escenario_cartera(cartera, body, db)
    return EscenarioSimulacionOut(**resultado)


@router.post("/scenarios/vida/simulate", response_model=EscenarioVidaOut)
def simular_escenarios_vida(
    body: EscenarioVidaRequest,
    cartera: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Simula 'Escenarios de vida': capa sencilla que reutiliza el motor de escenarios.
    No toca la cartera real: los supuestos vienen enteros en el body."""
    if cartera is not None:
        _validar_cartera(cartera, db)

    if body.supuestos.moneda not in MONEDAS_VIDA_VALIDAS:
        raise HTTPException(
            status_code=422,
            detail=f"moneda inválida: {body.supuestos.moneda}. Válidas: {MONEDAS_VIDA_VALIDAS}",
        )

    for item in body.escenarios:
        if item.tipo not in TIPOS_VIDA_VALIDOS:
            raise HTTPException(
                status_code=422,
                detail=f"tipo de escenario inválido: {item.tipo}. Válidos: {TIPOS_VIDA_VALIDOS}",
            )
        if item.tipo in vida_engine.TIPOS_CON_MONTO_O_PCT and item.monto is None and item.pct is None:
            raise HTTPException(
                status_code=422,
                detail=f"'{item.tipo}' requiere 'monto' o 'pct'",
            )
        if item.tipo == "aumentar_aportes_anualmente" and item.pct is None:
            raise HTTPException(
                status_code=422,
                detail="'aumentar_aportes_anualmente' requiere 'pct'",
            )
        if item.tipo in vida_engine.TIPOS_EXTRAORDINARIOS:
            if item.monto is None:
                raise HTTPException(status_code=422, detail=f"'{item.tipo}' requiere 'monto'")
            if item.mes is None:
                raise HTTPException(status_code=422, detail=f"'{item.tipo}' requiere 'mes'")
            if not (1 <= item.mes <= body.supuestos.horizonte_meses):
                raise HTTPException(
                    status_code=422,
                    detail=f"'mes' debe estar entre 1 y {body.supuestos.horizonte_meses} (horizonte_meses)",
                )

    resultado = vida_analytics.simular_vida_cartera(cartera, body, db)
    return EscenarioVidaOut(**resultado)


@router.get("/scenarios/vida/defaults", response_model=DefaultsVidaOut)
def defaults_escenarios_vida(
    cartera: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Precarga de patrimonio inicial y aporte mensual para 'Escenarios de vida',
    a partir de datos que la app ya calcula (no introduce fuentes nuevas)."""
    if cartera is not None:
        _validar_cartera(cartera, db)

    resultado = vida_analytics.get_defaults_vida(cartera, db)
    return DefaultsVidaOut(**resultado)


@router.get("/scenarios", response_model=list[EscenarioOut])
def listar_scenarios(
    cartera: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Lista escenarios guardados para una cartera."""
    if cartera is not None:
        _validar_cartera(cartera, db)

    escenarios = escenarios_analytics.listar_escenarios(cartera, db)
    return [
        EscenarioOut(
            id=e.id,
            cartera=e.cartera,
            nombre=e.nombre,
            tipo_preset=e.tipo_preset,
            parametros=e.parametros,
            fecha_creacion=e.fecha_creacion,
            fecha_actualizacion=e.fecha_actualizacion,
        )
        for e in escenarios
    ]


@router.post("/scenarios", response_model=EscenarioOut, status_code=201)
def crear_scenario(
    body: EscenarioGuardarRequest,
    db: Session = Depends(get_db),
):
    """Crea y guarda un nuevo escenario."""
    if body.cartera is not None:
        _validar_cartera(body.cartera, db)

    if body.tipo_preset not in TIPOS_PRESET_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"tipo_preset inválido: {body.tipo_preset}",
        )

    escenario = escenarios_analytics.crear_escenario(
        cartera=body.cartera,
        nombre=body.nombre,
        tipo_preset=body.tipo_preset,
        parametros=body.parametros.model_dump(),
        db=db,
    )

    return EscenarioOut(
        id=escenario.id,
        cartera=escenario.cartera,
        nombre=escenario.nombre,
        tipo_preset=escenario.tipo_preset,
        parametros=escenario.parametros,
        fecha_creacion=escenario.fecha_creacion,
        fecha_actualizacion=escenario.fecha_actualizacion,
    )


@router.post("/scenarios/{escenario_id}/duplicate", response_model=EscenarioOut, status_code=201)
def duplicar_scenario(
    escenario_id: int,
    nuevo_nombre: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Duplica un escenario con un nuevo nombre."""
    resultado = escenarios_analytics.duplicar_escenario(escenario_id, nuevo_nombre, db)

    if resultado is None:
        raise HTTPException(status_code=404, detail="Escenario no encontrado")

    return EscenarioOut(
        id=resultado.id,
        cartera=resultado.cartera,
        nombre=resultado.nombre,
        tipo_preset=resultado.tipo_preset,
        parametros=resultado.parametros,
        fecha_creacion=resultado.fecha_creacion,
        fecha_actualizacion=resultado.fecha_actualizacion,
    )


@router.delete("/scenarios/{escenario_id}", status_code=204)
def eliminar_scenario(
    escenario_id: int,
    db: Session = Depends(get_db),
):
    """Elimina un escenario."""
    if not escenarios_analytics.eliminar_escenario(escenario_id, db):
        raise HTTPException(status_code=404, detail="Escenario no encontrado")
