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

export const TIPO_COLORS: Record<string, string> = {
  ingreso: '#3fb950',
  egreso: '#f85149',
  neutro: '#8b949e',
}

export const CHART_COLORS = [
  '#58a6ff', '#3fb950', '#f85149', '#d2a8ff', '#f0883e',
  '#79c0ff', '#56d364', '#ff7b72', '#bc8cff', '#ffa657',
  '#a5d6ff', '#85e89d', '#ffb8b5', '#d8b4fe', '#fed7aa',
]
