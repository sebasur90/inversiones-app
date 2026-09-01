"""Adaptador entre datos reales (Session/DB) y el motor puro de diagnóstico.

Orquesta llamadas a los analytics existentes (riesgo, concentración, rebalanceo, etc.) y
pasa los resultados al motor de hallazgos y score.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import ObjetivoInversion
from . import diagnostico_engine
from .riesgo_analytics import get_riesgo
from .contribucion_analytics import get_concentracion
from .inversiones_analytics import (
    get_resumen,
    get_configuracion_cartera,
    get_rebalanceo,
    get_rendimiento_por_ticker,
    get_vencimientos,
    get_comisiones,
    get_progreso_objetivo,
)
from .cache import cache_por_sync


def _get_objetivo(cartera: str | None, db: Session, resumen: dict | None = None) -> dict | None:
    """Obtiene objetivo de inversión + progreso, o None si no existe."""
    if cartera is None:
        # No hay objetivo consolidado
        return None
    fila = db.query(ObjetivoInversion).filter(ObjetivoInversion.cartera == cartera).first()
    if not fila:
        return None
    progreso = get_progreso_objetivo(cartera, fila.id, db, resumen=resumen)
    if not progreso:
        return None
    return {**progreso, "monto_usd": float(fila.monto_usd)}


@cache_por_sync
def get_diagnostico(cartera: str | None, db: Session) -> dict:
    """Orquesta y agrega el diagnóstico completo.

    `resumen` y `rendimiento_por_ticker` se calculan una sola vez y se pasan a los analytics
    que los necesitan: son las dos partes más caras, y antes se recalculaban por dentro
    (get_resumen tres veces, una de ellas por cada rama de get_aportes_historicos).
    """
    resumen = get_resumen(cartera, db)
    config = get_configuracion_cartera(cartera, db)

    # Fetch riesgo con benchmark de la configuración
    benchmark = config.get("benchmark")
    riesgo = get_riesgo(cartera, "usd", benchmark, db)

    concentracion = get_concentracion(cartera, db)
    rebalanceo = get_rebalanceo(cartera, db)
    rendimiento_por_ticker = get_rendimiento_por_ticker(cartera, db)
    vencimientos = get_vencimientos(cartera, db, rendimientos=rendimiento_por_ticker)
    comisiones = get_comisiones(cartera, db)
    objetivo = _get_objetivo(cartera, db, resumen=resumen)

    # Evaluar hallazgos
    candidatos = [
        diagnostico_engine.evaluar_drawdown(riesgo.get("drawdown", {})),
        diagnostico_engine.evaluar_volatilidad(riesgo.get("volatilidad", {})),
        diagnostico_engine.evaluar_concentracion(concentracion),
        diagnostico_engine.evaluar_rebalanceo(rebalanceo.get("ejes", []), config.get("tolerancia", 2.0)),
        diagnostico_engine.evaluar_stop_loss(rendimiento_por_ticker),
        diagnostico_engine.evaluar_objetivo_precio(rendimiento_por_ticker),
        diagnostico_engine.evaluar_objetivo_inversion(objetivo),
        diagnostico_engine.evaluar_vencimientos(vencimientos),
        diagnostico_engine.evaluar_comisiones(comisiones, resumen.get("valor_actual_usd", 0)),
    ]
    hallazgos = diagnostico_engine.priorizar_hallazgos([h for h in candidatos if h is not None])

    # Calcular score de salud
    salud = diagnostico_engine.calcular_salud_cartera({
        "riesgo": diagnostico_engine.score_riesgo(
            riesgo.get("drawdown", {}),
            riesgo.get("volatilidad", {}),
        ),
        "concentracion": diagnostico_engine.score_concentracion(concentracion),
        "diversificacion": diagnostico_engine.score_diversificacion(concentracion),
        "performance": diagnostico_engine.score_performance(
            riesgo.get("calmar", {}),
            riesgo.get("benchmark_retorno_anualizado"),
            config.get("rendimiento_objetivo"),
        ),
        "objetivo": diagnostico_engine.score_objetivo(objetivo),
    })

    return {
        "cartera": cartera,
        "salud": salud,
        "hallazgos": hallazgos,
        "fecha_calculo": date.today(),
    }
