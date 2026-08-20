import dayjs from 'dayjs'
import type { ConfiguracionCartera, RiesgoOut } from '../api'

// ── Tipos ──────────────────────────────────────────────────────────────────

export interface ParametrosSimulacion {
  valorInicialUsd: number
  aporteMensualUsd: number
  crecimientoAporteAnualPct: number
  tasaAnualPct: number
}

export interface PuntoSimulado {
  mes: number
  fecha: string
  valorUsd: number
  aporteDelMesUsd: number
}

export interface PlanObjetivo {
  fechaInicio: string
  mesesTotales: number
  aporteMensualEsperadoUsd: number
  tasaBaseAnualPct: number
}

export interface DesviacionPlan {
  valorPlanHoyUsd: number
  valorRealHoyUsd: number
  desviacionUsd: number
  desviacionPct: number | null
  adelantado: boolean
}

export interface Escenarios {
  conservador: number
  base: number
  optimista: number
  fuenteSpread: 'volatilidad' | 'fallback'
}

export interface CeldaSensibilidad {
  mesesResultado: number | null
  fecha: string | null
}

export interface ResultadoSolverAporte {
  aporteMensualUsd: number | null
  motivo?: 'sin_tiempo'
}

export interface ResultadoSolverFecha {
  meses: number | null
  fecha: string | null
  motivo?: 'nunca'
}

export interface ResultadoSolverTasa {
  tasaAnualPct: number | null
  motivo?: 'sin_tiempo' | 'fuera_de_rango' | 'ya_alcanzable_con_minimo'
}

// ── Constantes ─────────────────────────────────────────────────────────────

const MESES_MAX_SIMULACION = 1200 // 100 años, tope defensivo
const TASA_MIN_PCT = -99 // guarda contra 1+i <= 0
const SPREAD_FALLBACK_PP = 3
const FALLBACK_TASA_PCT = 7
const TOLERANCIA_BUSQUEDA = 0.01 // USD

// ── Utilitarios ────────────────────────────────────────────────────────────

function tasaMensualDesdeAnual(tasaAnualPct: number): number {
  const t = Math.max(tasaAnualPct, TASA_MIN_PCT)
  return t === 0 ? 0 : Math.pow(1 + t / 100, 1 / 12) - 1
}

function aporteDelMes(base: number, crecimientoAnualPct: number, mes: number): number {
  const escalon = Math.floor((mes - 1) / 12)
  return base * Math.pow(1 + crecimientoAnualPct / 100, escalon)
}

function dayjsDiffMeses(start: dayjs.Dayjs, end: dayjs.Dayjs): number {
  return end.diff(start, 'month', true)
}

// ── Motor de simulación mes a mes ──────────────────────────────────────────

export function simularMesAMes(
  params: ParametrosSimulacion,
  meses: number,
  fechaInicio: Date = new Date()
): PuntoSimulado[] {
  if (meses < 0) return []
  const i = tasaMensualDesdeAnual(params.tasaAnualPct)
  const puntos: PuntoSimulado[] = [
    {
      mes: 0,
      fecha: dayjs(fechaInicio).format('YYYY-MM-DD'),
      valorUsd: params.valorInicialUsd,
      aporteDelMesUsd: 0,
    },
  ]
  let valor = params.valorInicialUsd
  for (let m = 1; m <= meses; m++) {
    const aporte = aporteDelMes(params.aporteMensualUsd, params.crecimientoAporteAnualPct, m)
    valor = valor * (1 + i) + aporte
    puntos.push({
      mes: m,
      fecha: dayjs(fechaInicio).add(m, 'month').format('YYYY-MM-DD'),
      valorUsd: valor,
      aporteDelMesUsd: aporte,
    })
  }
  return puntos
}

export function valorFinalSimulado(params: ParametrosSimulacion, meses: number): number {
  if (meses <= 0) return params.valorInicialUsd
  const puntos = simularMesAMes(params, Math.min(Math.ceil(meses), MESES_MAX_SIMULACION))
  return puntos[puntos.length - 1].valorUsd
}

// ── Solvers (binary search) ────────────────────────────────────────────────

export function resolverAporteMensual(
  objetivoUsd: number,
  meses: number,
  base: Omit<ParametrosSimulacion, 'aporteMensualUsd'>
): ResultadoSolverAporte {
  if (meses <= 0) {
    const sinAporte = valorFinalSimulado({ ...base, aporteMensualUsd: 0 }, 0)
    return {
      aporteMensualUsd: null,
      motivo: sinAporte < objetivoUsd ? 'sin_tiempo' : undefined,
    }
  }

  const sinAportes = valorFinalSimulado({ ...base, aporteMensualUsd: 0 }, meses)
  if (sinAportes >= objetivoUsd) {
    return { aporteMensualUsd: 0 }
  }

  let hi = 100
  while (
    valorFinalSimulado({ ...base, aporteMensualUsd: hi }, meses) < objetivoUsd &&
    hi < 1e8
  ) {
    hi *= 2
  }

  let lo = 0
  for (let iter = 0; iter < 60; iter++) {
    const mid = (lo + hi) / 2
    if (valorFinalSimulado({ ...base, aporteMensualUsd: mid }, meses) >= objetivoUsd) {
      hi = mid
    } else {
      lo = mid
    }
  }

  return { aporteMensualUsd: Math.round(hi * 100) / 100 }
}

export function resolverFechaAlcanzable(
  objetivoUsd: number,
  params: ParametrosSimulacion,
  maxMeses: number = MESES_MAX_SIMULACION,
  fechaInicio: Date = new Date()
): ResultadoSolverFecha {
  if (params.valorInicialUsd >= objetivoUsd) {
    return { meses: 0, fecha: dayjs(fechaInicio).format('YYYY-MM-DD') }
  }

  if (params.aporteMensualUsd <= 0 && params.tasaAnualPct <= 0) {
    return { meses: null, fecha: null, motivo: 'nunca' }
  }

  const trayectoria = simularMesAMes(params, maxMeses, fechaInicio)
  if (trayectoria[trayectoria.length - 1].valorUsd < objetivoUsd) {
    return { meses: null, fecha: null, motivo: 'nunca' }
  }

  // Búsqueda lineal: primer mes que cumple la meta
  for (const punto of trayectoria) {
    if (punto.valorUsd >= objetivoUsd) {
      return { meses: punto.mes, fecha: punto.fecha }
    }
  }

  return { meses: null, fecha: null, motivo: 'nunca' }
}

export function resolverTasaNecesaria(
  objetivoUsd: number,
  meses: number,
  base: Omit<ParametrosSimulacion, 'tasaAnualPct'>,
  rango: [number, number] = [-90, 300]
): ResultadoSolverTasa {
  if (meses <= 0) {
    return { tasaAnualPct: null, motivo: 'sin_tiempo' }
  }

  const [rMin, rMax] = rango
  if (valorFinalSimulado({ ...base, tasaAnualPct: rMin }, meses) >= objetivoUsd) {
    return { tasaAnualPct: rMin, motivo: 'ya_alcanzable_con_minimo' }
  }

  if (valorFinalSimulado({ ...base, tasaAnualPct: rMax }, meses) < objetivoUsd) {
    return { tasaAnualPct: null, motivo: 'fuera_de_rango' }
  }

  let lo = rMin
  let hi = rMax
  for (let iter = 0; iter < 60; iter++) {
    const mid = (lo + hi) / 2
    if (valorFinalSimulado({ ...base, tasaAnualPct: mid }, meses) >= objetivoUsd) {
      hi = mid
    } else {
      lo = mid
    }
  }

  return { tasaAnualPct: Math.round(hi * 100) / 100 }
}

// ── Plan y desviación ──────────────────────────────────────────────────────

export function derivarPlanObjetivo(
  montoObjetivoUsd: number,
  fechaLimite: string,
  primerMesCurva: string | null,
  tasaBaseAnualPct: number,
  valorActualUsd: number = 0
): PlanObjetivo | null {
  if (!primerMesCurva) return null

  const fechaInicio = dayjs(`${primerMesCurva}-01`)
  const fechaLimiteDay = dayjs(fechaLimite)

  if (!fechaInicio.isBefore(fechaLimiteDay)) return null

  const mesesTotales = Math.ceil(dayjsDiffMeses(fechaInicio, fechaLimiteDay))
  if (mesesTotales <= 0) return null

  const resolver = resolverAporteMensual(montoObjetivoUsd, mesesTotales, {
    valorInicialUsd: valorActualUsd,
    crecimientoAporteAnualPct: 0,
    tasaAnualPct: tasaBaseAnualPct,
  })

  if (resolver.aporteMensualUsd == null) return null

  return {
    fechaInicio: fechaInicio.format('YYYY-MM-DD'),
    mesesTotales,
    aporteMensualEsperadoUsd: resolver.aporteMensualUsd,
    tasaBaseAnualPct,
  }
}

export function calcularDesviacionPlan(
  plan: PlanObjetivo,
  valorRealHoyUsd: number,
  hoy: Date = new Date()
): DesviacionPlan {
  const mesesTranscurridos = Math.min(
    Math.max(
      0,
      dayjsDiffMeses(dayjs(plan.fechaInicio), dayjs(hoy))
    ),
    plan.mesesTotales
  )

  const valorPlanHoyUsd = valorFinalSimulado(
    {
      valorInicialUsd: 0,
      aporteMensualUsd: plan.aporteMensualEsperadoUsd,
      crecimientoAporteAnualPct: 0,
      tasaAnualPct: plan.tasaBaseAnualPct,
    },
    Math.round(mesesTranscurridos)
  )

  const desviacionUsd = valorRealHoyUsd - valorPlanHoyUsd

  return {
    valorPlanHoyUsd,
    valorRealHoyUsd,
    desviacionUsd,
    desviacionPct: valorPlanHoyUsd > 0 ? desviacionUsd / valorPlanHoyUsd : null,
    adelantado: desviacionUsd >= 0,
  }
}

// ── Escenarios ─────────────────────────────────────────────────────────────

export function calcularEscenarios(
  tasaBaseAnualPct: number,
  volatilidadAnualizadaRatio: number | null
): Escenarios {
  const spreadPp =
    volatilidadAnualizadaRatio != null
      ? volatilidadAnualizadaRatio * 100
      : SPREAD_FALLBACK_PP

  return {
    conservador: tasaBaseAnualPct - spreadPp,
    base: tasaBaseAnualPct,
    optimista: tasaBaseAnualPct + spreadPp,
    fuenteSpread:
      volatilidadAnualizadaRatio != null ? 'volatilidad' : 'fallback',
  }
}

// ── Grilla de sensibilidad ─────────────────────────────────────────────────

export function calcularGrillaSensibilidad(
  objetivoUsd: number,
  valorInicialUsd: number,
  tasasAnualPct: number[],
  aportesUsd: number[]
): CeldaSensibilidad[][] {
  return tasasAnualPct.map(tasa =>
    aportesUsd.map(aporte => {
      const r = resolverFechaAlcanzable(objetivoUsd, {
        valorInicialUsd,
        aporteMensualUsd: aporte,
        crecimientoAporteAnualPct: 0,
        tasaAnualPct: tasa,
      })
      return { mesesResultado: r.meses, fecha: r.fecha }
    })
  )
}

// ── Tasa base (con fallbacks) ──────────────────────────────────────────────

export function resolverTasaBase(
  configuracion: ConfiguracionCartera | null,
  riesgo: RiesgoOut | null
): { valor: number; fuente: 'configuracion' | 'historico' | 'fallback' } {
  if (configuracion?.rendimiento_objetivo != null) {
    return { valor: configuracion.rendimiento_objetivo, fuente: 'configuracion' }
  }

  if (riesgo?.calmar.retorno_anualizado != null) {
    return {
      valor: riesgo.calmar.retorno_anualizado * 100,
      fuente: 'historico',
    }
  }

  return { valor: FALLBACK_TASA_PCT, fuente: 'fallback' }
}
