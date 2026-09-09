import type { EscalaX } from './useEscalaX'

/** Path SVG de una serie con `null` (warm-up): corta el trazo en cada hueco en vez de
 * interpolar a través de él. Sólo recorre el tramo visible de `escalaX` — con la serie completa
 * y la ventana con zoom, dibujar los miles de puntos de afuera cuesta y no se ve. */
export function trazoDeSerie(vals: (number | null)[], escalaX: EscalaX, yDeValor: (v: number) => number): string {
  let d = ''
  let dibujando = false
  // Un punto de más a cada lado para que el trazo entre y salga del panel en lugar de arrancar
  // recién en el borde.
  const desde = Math.max(0, escalaX.inicio - 1)
  const hasta = Math.min(vals.length - 1, escalaX.fin + 1)
  for (let i = desde; i <= hasta; i++) {
    const v = vals[i]
    if (v == null) { dibujando = false; continue }
    const x = escalaX.xDeIndice(i)
    const y = yDeValor(v)
    d += dibujando ? ` L ${x} ${y}` : `${d ? ' ' : ''}M ${x} ${y}`
    dibujando = true
  }
  return d.trim()
}

/** Los valores de una serie dentro de la ventana visible, sin `null`. La escala Y de cada panel se
 * calcula con esto y no con la serie entera: al acercar el zoom, el panel reescala en vertical
 * sobre lo que se está mirando, que es lo que uno espera de un gráfico de precios. */
export function valoresVisibles(vals: (number | null)[], escalaX: EscalaX): number[] {
  const out: number[] = []
  const hasta = Math.min(vals.length - 1, escalaX.fin)
  for (let i = Math.max(0, escalaX.inicio); i <= hasta; i++) {
    const v = vals[i]
    if (v != null && Number.isFinite(v)) out.push(v)
  }
  return out
}
