"""Centro de Decisiones: análisis de oportunidades, posiciones existentes, simulación, diario y aprendizaje.

Todo es análisis, simulación o registro explícito de lo que decide el usuario: ningún endpoint escribe
movimientos, precios ni nada en la planilla (la fuente de verdad sigue siendo el Google Sheet).
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..database import MovimientoInversion, get_db
from ..schemas import (
    AprendizajeOut, CentroAnalisisOut, CentroExplorarOut, CentroFacetasOut, CentroPosicionOut, DecisionCrearIn,
    DecisionDetalleOut, DecisionOut, DecisionPatchIn, DecisionPreferenciasIn, DecisionPreferenciasOut,
    DecisionRevisionIn, DecisionRevisionOut, SimulacionDecisionIn, SimulacionDecisionOut,
)
from ..services import centro_decisiones_analytics as cda
from ..services import decision_preferencias, diario_decisiones, evaluacion_engine, simulador_decision
from ..services.impacto_cartera_analytics import TickerDesconocido
from ..services.valuacion_analytics import Universo

router = APIRouter(prefix="/api/inversiones", tags=["decisiones"])

_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")


def _ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not _TICKER.match(t):
        raise HTTPException(status_code=422, detail="el ticker no es válido")
    return t


def _cartera(nombre: Optional[str], db: Session) -> Optional[str]:
    if not nombre:
        return None
    if not db.query(MovimientoInversion.id).filter(MovimientoInversion.cartera == nombre).first():
        raise HTTPException(status_code=404, detail=f"Cartera '{nombre}' no encontrada")
    return nombre


def _con(con: str) -> tuple:
    elegidas = [c.strip().upper() for c in (con or "").split(",") if c.strip()]
    for c in elegidas:
        _ticker(c)
    if len(elegidas) > cda.MAX_ALTERNATIVAS:
        raise HTTPException(status_code=422, detail=f"con admite hasta {cda.MAX_ALTERNATIVAS} alternativas")
    return tuple(dict.fromkeys(elegidas))


def _prefs(db: Session, horizonte, objetivo, enfoque, moneda, tolerancia) -> dict:
    try:
        return decision_preferencias.combinar(db, {"horizonte": horizonte, "objetivo": objetivo, "enfoque": enfoque,
                                                    "moneda": moneda, "tolerancia": tolerancia})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _prefs_out(prefs: dict) -> dict:
    return {**prefs, "pesos_efectivos": evaluacion_engine.pesos_para(prefs), "pesos_tabla": evaluacion_engine.PESOS}


# ── Preferencias ────────────────────────────────────────────────────────────

@router.get("/decisiones/preferencias", response_model=DecisionPreferenciasOut)
def leer_preferencias(db: Session = Depends(get_db)):
    """Preferencias de análisis guardadas (o los defaults documentados, si nunca se guardaron)."""
    return _prefs_out(decision_preferencias.leer(db))


@router.put("/decisiones/preferencias", response_model=DecisionPreferenciasOut)
def guardar_preferencias(body: DecisionPreferenciasIn, db: Session = Depends(get_db)):
    try:
        return _prefs_out(decision_preferencias.guardar(db, body.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Oportunidades ───────────────────────────────────────────────────────────

@router.get("/decisiones/facetas", response_model=CentroFacetasOut)
def facetas(db: Session = Depends(get_db)):
    """Sectores, industrias, países, regiones, tipos y temáticas disponibles, con la cobertura del universo."""
    return cda.facetas(db)


@router.get("/decisiones/explorar", response_model=CentroExplorarOut)
def explorar(
    sector: Optional[str] = Query(None, max_length=80), industria: Optional[str] = Query(None, max_length=120),
    pais: Optional[str] = Query(None, max_length=80), region: Optional[str] = Query(None, max_length=80),
    tipo: Optional[str] = Query(None, max_length=40), tematica: Optional[str] = Query(None, max_length=40),
    universo: Optional[str] = Query(None), horizonte: Optional[str] = Query(None), objetivo: Optional[str] = Query(None),
    enfoque: Optional[str] = Query(None), moneda: Optional[str] = Query(None), tolerancia: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Ranking del universo con filtros. El orden sólo usa fundamentales, valoración y riesgo."""
    prefs = _prefs(db, horizonte, objetivo, enfoque, moneda, tolerancia)
    if universo:
        try:
            prefs = decision_preferencias.normalizar({**prefs, "universo": universo})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    try:
        return cda.explorar(prefs, sector, industria, pais, region, tipo, tematica, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/decisiones/analisis/{ticker}", response_model=CentroAnalisisOut)
def analisis(
    ticker: str,
    cartera: Optional[str] = Query(None, max_length=80),
    con: str = Query("", description="Alternativas elegidas, separadas por coma (hasta 6)"),
    monto_ref_usd: Optional[float] = Query(None, gt=0, le=1e9),
    horizonte: Optional[str] = Query(None), objetivo: Optional[str] = Query(None), enfoque: Optional[str] = Query(None),
    moneda: Optional[str] = Query(None), tolerancia: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Análisis completo: dimensiones con puntaje y regla, banderas, alternativas, escenarios de entrada y conclusión.
    No es una indicación de operar."""
    t = _ticker(ticker)
    return cda.analizar(t, _prefs(db, horizonte, objetivo, enfoque, moneda, tolerancia), _cartera(cartera, db),
                        _con(con), monto_ref_usd, db)


# ── Posición existente ──────────────────────────────────────────────────────

@router.get("/decisiones/posicion/{ticker}", response_model=CentroPosicionOut)
def posicion(
    ticker: str,
    cartera: Optional[str] = Query(None, max_length=80),
    horizonte: Optional[str] = Query(None), objetivo: Optional[str] = Query(None), enfoque: Optional[str] = Query(None),
    moneda: Optional[str] = Query(None), tolerancia: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Mantener / aumentar / reducir / salir de una posición, con la simulación de cada opción."""
    t = _ticker(ticker)
    c = _cartera(cartera, db)
    prefs = _prefs(db, horizonte, objetivo, enfoque, moneda, tolerancia)
    base = Universo(db).ctx.base(t)
    try:
        return cda.analizar_posicion(t, c, prefs, db, diario_decisiones.ultima_tesis(db, base),
                                     diario_decisiones.invalidacion_de_ticker(db, base))
    except cda.NoEsPosicion:
        raise HTTPException(status_code=404, detail=f"No hay una posición abierta de {t} en {'esa cartera' if c else 'el consolidado'}")


# ── Simulador ───────────────────────────────────────────────────────────────

def _simular(cartera: Optional[str], body: SimulacionDecisionIn, db: Session) -> dict:
    try:
        return simulador_decision.simular_operaciones(cartera, db, [(o.ticker, o.monto_usd) for o in body.operaciones])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except TickerDesconocido as exc:
        raise HTTPException(status_code=404, detail=f"Ticker '{exc}' no encontrado en la cartera, la watchlist ni el catálogo")


@router.post("/carteras/{nombre}/simular-decision", response_model=SimulacionDecisionOut)
def simular_cartera(nombre: str, body: SimulacionDecisionIn, db: Session = Depends(get_db)):
    """Cómo quedaría la cartera con operaciones hipotéticas (montos en USD: + suma, − reduce). No guarda nada."""
    return _simular(_cartera(nombre, db), body, db)


@router.post("/consolidado/simular-decision", response_model=SimulacionDecisionOut)
def simular_consolidado(body: SimulacionDecisionIn, db: Session = Depends(get_db)):
    return _simular(None, body, db)


# ── Diario de decisiones ────────────────────────────────────────────────────

@router.get("/decisiones", response_model=list[DecisionOut])
def listar_decisiones(ticker: Optional[str] = Query(None, max_length=15),
                      estado: Optional[str] = Query(None, pattern="^(abierta|cerrada)$"),
                      limite: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    return diario_decisiones.listar(db, ticker, estado, limite)


@router.post("/decisiones", response_model=DecisionDetalleOut, status_code=201)
def crear_decision(body: DecisionCrearIn, db: Session = Depends(get_db)):
    """Guarda una decisión. El servidor vuelve a correr el análisis y congela su resultado: del cliente sólo se
    toman los parámetros y lo que eligió el usuario."""
    t = _ticker(body.ticker)
    c = _cartera(body.cartera, db)
    con = _con(",".join(body.con))
    try:
        return diario_decisiones.crear(
            db, body.modo, t, body.accion_elegida, cartera=c, preferencias=body.preferencias, con=con,
            monto_ref_usd=body.monto_ref_usd, nota=body.nota, ejecutada=body.ejecutada,
            revisar_en_dias=body.revisar_en_dias, alternativa_elegida=body.alternativa_elegida,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except cda.NoEsPosicion:
        raise HTTPException(status_code=404, detail=f"No hay una posición abierta de {t}")


@router.get("/decisiones/pendientes", response_model=list[DecisionOut])
def pendientes(db: Session = Depends(get_db)):
    """Decisiones abiertas cuya fecha de revisión llegó o cuya condición de invalidación de precio se cumplió."""
    return diario_decisiones.pendientes(db)


@router.get("/decisiones/aprendizaje", response_model=AprendizajeOut)
def aprendizaje(db: Session = Depends(get_db)):
    """Patrones descriptivos de tu proceso de decisión (con muestra mínima)."""
    return diario_decisiones.aprendizaje(db)


@router.get("/decisiones/{decision_id}", response_model=DecisionDetalleOut)
def detalle(decision_id: int, db: Session = Depends(get_db)):
    try:
        return diario_decisiones.a_dict(db, diario_decisiones.obtener(db, decision_id), completo=True)
    except diario_decisiones.DecisionNoEncontrada:
        raise HTTPException(status_code=404, detail="Decisión no encontrada")


@router.patch("/decisiones/{decision_id}", response_model=DecisionDetalleOut)
def editar(decision_id: int, body: DecisionPatchIn, db: Session = Depends(get_db)):
    """Sólo los campos del usuario (ejecutada, nota, fecha de revisión, estado). Lo calculado no se edita."""
    try:
        return diario_decisiones.actualizar(db, decision_id, body.ejecutada, body.nota, body.revisar_el, body.estado)
    except diario_decisiones.DecisionNoEncontrada:
        raise HTTPException(status_code=404, detail="Decisión no encontrada")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/decisiones/{decision_id}", status_code=204)
def borrar(decision_id: int, db: Session = Depends(get_db)):
    try:
        diario_decisiones.borrar(db, decision_id)
    except diario_decisiones.DecisionNoEncontrada:
        raise HTTPException(status_code=404, detail="Decisión no encontrada")
    return Response(status_code=204)


@router.post("/decisiones/{decision_id}/revisiones", response_model=DecisionRevisionOut, status_code=201)
def revisar(decision_id: int, body: DecisionRevisionIn, db: Session = Depends(get_db)):
    """Revisión nueva: compara la foto del día de la decisión con el análisis de hoy. No pisa nada."""
    try:
        return diario_decisiones.revisar(db, decision_id, body.evaluacion_proceso, body.nota)
    except diario_decisiones.DecisionNoEncontrada:
        raise HTTPException(status_code=404, detail="Decisión no encontrada")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/decisiones/revisiones/{revision_id}", response_model=DecisionRevisionOut)
def calificar_revision(revision_id: int, body: DecisionRevisionIn, db: Session = Depends(get_db)):
    """Tu evaluación del proceso en una revisión ya hecha (la comparación calculada no cambia)."""
    try:
        return diario_decisiones.calificar_revision(db, revision_id, body.evaluacion_proceso, body.nota)
    except diario_decisiones.DecisionNoEncontrada:
        raise HTTPException(status_code=404, detail="Revisión no encontrada")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
