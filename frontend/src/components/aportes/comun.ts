import dayjs from 'dayjs'

/** "sep 2025" a partir de "2025-09". */
export function mesCorto(mes: string | null | undefined): string {
  return mes ? dayjs(`${mes}-01`).format('MMM YYYY') : '—'
}

export function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`
}

/** Verde/rojo sólo para deltas: 0 y nulo quedan neutros para no teñir de rojo un "sin cambios". */
export function claseTono(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-app-text-dim'
  return v > 0 ? 'text-app-pos' : 'text-app-neg'
}

export function plural(n: number, singular: string, plural_: string): string {
  return `${n} ${n === 1 ? singular : plural_}`
}

export function meses(n: number): string {
  return plural(n, 'mes', 'meses')
}
