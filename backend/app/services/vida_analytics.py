"""Orquestación de 'Escenarios de vida' (DB-aware). Capa fina: mapea el body a las
dataclasses de `vida_engine` y arma el dict de salida, igual que `escenarios_analytics`
hace para el simulador Avanzado.
"""
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from app.services import vida_engine
from app.services import escenarios_analytics
from app.services import aportes_analytics


def get_defaults_vida(cartera: str | None, db: Session) -> dict:
    """Precarga de patrimonio inicial y aporte mensual con datos que la app ya calcula:
    el mismo snapshot que usa el simulador Avanzado, y el ritmo de aportes de la cartera."""
    snapshot = escenarios_analytics.construir_snapshot(cartera, db)
    patrimonio_inicial_usd = snapshot.valor_total_usd

    ritmo = aportes_analytics.get_ritmo_aportes(cartera, db)
    estadisticas = ritmo.get("estadisticas")

    advertencias: list[str] = []
    if estadisticas is None:
        aporte_mensual_usd: Optional[float] = None
        origen_aporte = "sin_datos"
        meses_historia = 0
    else:
        aporte_mensual_usd = estadisticas.get("promedio_12_usd")
        origen_aporte = "promedio_12m"
        if aporte_mensual_usd is None:
            aporte_mensual_usd = estadisticas.get("promedio_usd")
            origen_aporte = "promedio_historico"
        meses_historia = estadisticas.get("meses_historia", 0)

        if aporte_mensual_usd is not None and aporte_mensual_usd < 0:
            aporte_mensual_usd = 0.0
            advertencias.append(
                "Tu promedio de aportes es negativo (retiraste más de lo que aportaste). "
                "Se precargó 0."
            )

    return {
        "cartera": cartera,
        "patrimonio_inicial_usd": patrimonio_inicial_usd,
        "aporte_mensual_usd": aporte_mensual_usd,
        "origen_aporte": origen_aporte,
        "meses_historia": meses_historia,
        "advertencias": advertencias,
    }


def simular_vida_cartera(cartera: str | None, request, db: Session) -> dict:
    """Ejecuta la simulación de escenarios de vida. No consulta la DB: los supuestos
    vienen enteros en el body (a diferencia del simulador Avanzado, que arma el
    snapshot desde la cartera real)."""
    supuestos = vida_engine.SupuestosVida(
        patrimonio_inicial=request.supuestos.patrimonio_inicial,
        aporte_mensual=request.supuestos.aporte_mensual,
        crecimiento_anual_pct=request.supuestos.crecimiento_anual_pct,
        horizonte_meses=request.supuestos.horizonte_meses,
        moneda=request.supuestos.moneda,
        inflacion_anual_pct=request.supuestos.inflacion_anual_pct,
    )
    especificaciones = [
        vida_engine.EscenarioVidaSpec(
            tipo=item.tipo, monto=item.monto, pct=item.pct, mes=item.mes,
        )
        for item in request.escenarios
    ]

    comparacion = vida_engine.simular_vida(supuestos, especificaciones, hoy=date.today())

    resultados_out = [
        {
            "tipo": r.tipo,
            "nombre": r.nombre,
            "descripcion": r.descripcion,
            "es_base": r.es_base,
            "aporte_mensual_efectivo": r.aporte_mensual_efectivo,
            "crecimiento_aporte_anual_pct": r.crecimiento_aporte_anual_pct,
            "mes_flujo_extraordinario": r.mes_flujo_extraordinario,
            "monto_flujo_extraordinario": r.monto_flujo_extraordinario,
            "se_agota_en_mes": r.se_agota_en_mes,
            "puntos": [
                {
                    "mes": p.mes,
                    "fecha": p.fecha,
                    "valor": p.valor,
                    "valor_real": p.valor_real,
                    "aportado_acum": p.aportado_acum,
                }
                for p in r.puntos
            ],
            "metricas": {
                "patrimonio_final": r.metricas.patrimonio_final,
                "patrimonio_final_real": r.metricas.patrimonio_final_real,
                "aportes_periodo": r.metricas.aportes_periodo,
                "crecimiento_estimado": r.metricas.crecimiento_estimado,
                "diferencia_vs_base": r.metricas.diferencia_vs_base,
                "diferencia_vs_base_pct": r.metricas.diferencia_vs_base_pct,
            },
            "advertencias": r.advertencias,
            "es_simulado": True,
        }
        for r in comparacion.resultados
    ]

    return {
        "cartera": cartera,
        "fecha_simulacion": datetime.utcnow(),
        "moneda": supuestos.moneda,
        "supuestos": request.supuestos,
        "resultados": resultados_out,
        "disclaimer": comparacion.disclaimer,
        "advertencias": comparacion.advertencias,
    }
