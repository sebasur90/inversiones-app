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

export interface ProyeccionConInteres {
  aporteMensualNecesarioConInteres: number | null
  ahorroAporteMensualUsd: number | null
  mesesNecesariosSinInteres: number | null
  mesesNecesariosConInteres: number | null
  mesesAhorrados: number | null
}

// Proyecta el objetivo con una tasa de interés anual esperada (crecimiento compuesto de lo
// invertido + aportes mensuales), comparando contra el escenario lineal (0% interés) actual.
export function calcularProyeccionConInteres(
  valorActualUsd: number,
  montoObjetivoUsd: number,
  mesesRestantes: number,
  aporteMensualPromedioUsd: number,
  aporteMensualNecesarioBaselineUsd: number | null,
  tasaAnualPct: number
): ProyeccionConInteres {
  const i = tasaAnualPct > 0 ? Math.pow(1 + tasaAnualPct / 100, 1 / 12) - 1 : 0

  // 1) Aporte mensual necesario para llegar a la fecha límite, con interés (despeja C de
  //    V0*(1+i)^n + C*((1+i)^n - 1)/i = G).
  let aporteMensualNecesarioConInteres: number | null = null
  if (mesesRestantes > 0) {
    if (i === 0) {
      aporteMensualNecesarioConInteres = Math.max(0, (montoObjetivoUsd - valorActualUsd) / mesesRestantes)
    } else {
      const factor = Math.pow(1 + i, mesesRestantes)
      aporteMensualNecesarioConInteres = Math.max(0, ((montoObjetivoUsd - valorActualUsd * factor) * i) / (factor - 1))
    }
  }

  const ahorroAporteMensualUsd =
    aporteMensualNecesarioBaselineUsd != null && aporteMensualNecesarioConInteres != null
      ? Math.max(0, aporteMensualNecesarioBaselineUsd - aporteMensualNecesarioConInteres)
      : null

  // 2) Meses necesarios al ritmo actual (aporte promedio fijo), despejando n de la misma ecuación.
  const mesesNecesarios = (tasaMensual: number): number | null => {
    if (valorActualUsd >= montoObjetivoUsd) return 0
    if (aporteMensualPromedioUsd <= 0) return null
    if (tasaMensual === 0) return (montoObjetivoUsd - valorActualUsd) / aporteMensualPromedioUsd
    const x =
      (montoObjetivoUsd + aporteMensualPromedioUsd / tasaMensual) /
      (valorActualUsd + aporteMensualPromedioUsd / tasaMensual)
    return x > 0 ? Math.log(x) / Math.log(1 + tasaMensual) : null
  }

  const mesesNecesariosSinInteres = mesesNecesarios(0)
  const mesesNecesariosConInteres = mesesNecesarios(i)
  const mesesAhorrados =
    mesesNecesariosSinInteres != null && mesesNecesariosConInteres != null
      ? Math.max(0, mesesNecesariosSinInteres - mesesNecesariosConInteres)
      : null

  return {
    aporteMensualNecesarioConInteres,
    ahorroAporteMensualUsd,
    mesesNecesariosSinInteres,
    mesesNecesariosConInteres,
    mesesAhorrados,
  }
}

const HEATMAP_MAX_ALPHA = 0.45
const HEATMAP_CAP_PCT = 20 // |retorno| >= 20% satura a la intensidad máxima

// Mapea un retorno (razón, ej. 0.1059) a un color de fondo teal/coral cuya intensidad
// escala con la magnitud, reutilizando la paleta de la app. Alpha tope en 0.45: por encima
// de eso el texto claro pierde contraste sobre el teal (verde claro incluso en tema oscuro).
export function heatmapIntensity(ratio: number | null | undefined): { backgroundColor: string } {
  if (ratio == null) return { backgroundColor: 'transparent' }
  const pct = ratio * 100
  const magnitud = Math.min(Math.abs(pct) / HEATMAP_CAP_PCT, 1)
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
