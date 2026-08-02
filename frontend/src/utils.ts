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
