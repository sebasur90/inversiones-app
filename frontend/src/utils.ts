export function formatARS(value: number | null | undefined): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatUSD(value: number | null | undefined): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatPct(value: number | null | undefined): string {
  if (value == null) return '—'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

// Igual que formatPct pero recibe una razón (0.1059) en vez de un porcentaje (10.59)
export function formatPctRatio(value: number | null | undefined): string {
  if (value == null) return '—'
  return formatPct(value * 100)
}

export function formatCantidad(value: number): string {
  return value.toLocaleString('es-AR', { maximumFractionDigits: 8 })
}

export function formatPrecio(value: number): string {
  return value.toLocaleString('es-AR', { maximumFractionDigits: 6 })
}

const HEATMAP_MAX_ALPHA = 0.45
const HEATMAP_CAP_PCT = 20 // |retorno| >= 20% satura a la intensidad máxima

// Mapea un retorno (razón, ej. 0.1059) a un color de fondo teal/coral cuya intensidad
// escala con la magnitud, reutilizando la paleta de la app. Alpha tope en 0.45: por encima
// de eso el texto claro pierde contraste sobre el teal (verde claro incluso en tema oscuro).
// `capPct` es el |valor*100| que satura la intensidad máxima: 20 para retornos (heatmap
// mensual/anual), 100 para coeficientes de correlación (-1..1, donde 1.0 * 100 = 100).
export function heatmapIntensity(ratio: number | null | undefined, capPct: number = HEATMAP_CAP_PCT): { backgroundColor: string } {
  if (ratio == null) return { backgroundColor: 'transparent' }
  const pct = ratio * 100
  const magnitud = Math.min(Math.abs(pct) / capPct, 1)
  const alpha = (magnitud * HEATMAP_MAX_ALPHA).toFixed(3)
  const rgb = pct >= 0 ? '79, 209, 174' : '226, 102, 90' // app-teal / app-coral
  return { backgroundColor: `rgba(${rgb}, ${alpha})` }
}

export const TIPO_COLORS: Record<string, string> = {
  ingreso: '#4fd1ae',
  egreso: '#e2665a',
  neutro: '#8ca39b',
}

// Paleta categórica de la app ("ledger"): oro, verde azulado, acero, ciruela, salvia, coral.
export const CHART_COLORS = [
  '#d8b14a', '#4fd1ae', '#5b8ba0', '#9c7aa0', '#7e9c90', '#e2665a',
  '#c9a53a', '#3fb599', '#4a7688', '#856787', '#6a877c', '#c9544a',
]

export type PeriodoEvolucion = '1M' | '3M' | '6M' | '1Y' | 'YTD' | 'ALL'

export function calcularDesde(periodo: PeriodoEvolucion): string | undefined {
  const hoy = new Date()
  if (periodo === 'ALL') return undefined
  if (periodo === 'YTD') return `${hoy.getFullYear()}-01-01`
  const d = new Date(hoy)
  if (periodo === '1M') d.setMonth(d.getMonth() - 1)
  if (periodo === '3M') d.setMonth(d.getMonth() - 3)
  if (periodo === '6M') d.setMonth(d.getMonth() - 6)
  if (periodo === '1Y') d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().slice(0, 10)
}
