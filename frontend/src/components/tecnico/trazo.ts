import type { EscalaX } from './useEscalaX'

/** Path SVG de una serie con `null` (warm-up): corta el trazo en cada hueco en vez de
 * interpolar a través de él. */
export function trazoDeSerie(vals: (number | null)[], escalaX: EscalaX, yDeValor: (v: number) => number): string {
  let d = ''
  let dibujando = false
  vals.forEach((v, i) => {
    if (v == null) { dibujando = false; return }
    const x = escalaX.xDeIndice(i)
    const y = yDeValor(v)
    d += dibujando ? ` L ${x} ${y}` : `${d ? ' ' : ''}M ${x} ${y}`
    dibujando = true
  })
  return d.trim()
}
