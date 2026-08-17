import type { HallazgoItem } from '../api'
import type { DesviacionPlan } from './proyeccion'

export const TIPO_PRIORIDAD = [
  'stop_loss_disparado',
  'drawdown_elevado',
  'objetivo_inversion_riesgo',
  'objetivo_patrimonio_desviado',
  'vencimiento_proximo',
  'concentracion_alta',
  'rebalanceo_necesario',
  'comision_elevada',
  'volatilidad_elevada',
  'objetivo_precio_alcanzado',
] as const

const SEVERIDAD_RANK: Record<string, number> = { critico: 0, advertencia: 1, info: 2 }

export function priorizarHallazgos(hallazgos: HallazgoItem[]): HallazgoItem[] {
  return [...hallazgos].sort((a, b) => {
    const rankDiff = SEVERIDAD_RANK[a.severidad] - SEVERIDAD_RANK[b.severidad]
    if (rankDiff !== 0) return rankDiff
    const indexA = TIPO_PRIORIDAD.indexOf(a.tipo as any)
    const indexB = TIPO_PRIORIDAD.indexOf(b.tipo as any)
    return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB)
  })
}

const UMBRAL_DESVIACION_CRITICO = -0.20
const UMBRAL_DESVIACION_ADVERTENCIA = -0.08
const UMBRAL_DESVIACION_ADELANTADO_INFO = 0.08

export function evaluarDesviacionPlan(desviacion: DesviacionPlan | null): HallazgoItem | null {
  if (!desviacion || desviacion.desviacionPct == null) return null
  const pct = desviacion.desviacionPct

  if (pct <= UMBRAL_DESVIACION_CRITICO) {
    return {
      tipo: 'objetivo_patrimonio_desviado',
      severidad: 'critico',
      titulo: 'Objetivo de patrimonio muy atrasado',
      explicacion: `Estás ${(Math.abs(pct) * 100).toFixed(1)}% por debajo del plan esperado. Necesitas acelerar aportes o mejorar el rendimiento.`,
      dato_disparador: {
        desviacion_pct: Math.round(pct * 10000) / 100,
        valor_plan_usd: Math.round(desviacion.valorPlanHoyUsd),
        valor_real_usd: Math.round(desviacion.valorRealHoyUsd),
      },
      pantalla: '/objetivo',
      fecha_calculo: new Date().toISOString().split('T')[0],
    }
  }

  if (pct <= UMBRAL_DESVIACION_ADVERTENCIA) {
    return {
      tipo: 'objetivo_patrimonio_desviado',
      severidad: 'advertencia',
      titulo: 'Objetivo de patrimonio algo atrasado',
      explicacion: `Estás ${(Math.abs(pct) * 100).toFixed(1)}% por debajo del plan esperado. Considera revisar tu estrategia de aportes.`,
      dato_disparador: {
        desviacion_pct: Math.round(pct * 10000) / 100,
        valor_plan_usd: Math.round(desviacion.valorPlanHoyUsd),
        valor_real_usd: Math.round(desviacion.valorRealHoyUsd),
      },
      pantalla: '/objetivo',
      fecha_calculo: new Date().toISOString().split('T')[0],
    }
  }

  if (pct >= UMBRAL_DESVIACION_ADELANTADO_INFO) {
    return {
      tipo: 'objetivo_patrimonio_desviado',
      severidad: 'info',
      titulo: 'Vas adelantado en tu objetivo',
      explicacion: `Excelente: estás ${(pct * 100).toFixed(1)}% por encima del plan esperado. Al ritmo actual alcanzarás antes tu meta.`,
      dato_disparador: {
        desviacion_pct: Math.round(pct * 10000) / 100,
        valor_plan_usd: Math.round(desviacion.valorPlanHoyUsd),
        valor_real_usd: Math.round(desviacion.valorRealHoyUsd),
      },
      pantalla: '/objetivo',
      fecha_calculo: new Date().toISOString().split('T')[0],
    }
  }

  return null
}
