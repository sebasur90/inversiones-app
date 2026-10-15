import type { BarraOut } from '../../api'
import type { EscalaX } from './useEscalaX'

/** Formatos de los números y fechas que el gráfico técnico muestra en ejes, ficha y leyenda.
 *
 * Un solo lugar para que el eje de precio, la etiqueta del último cierre y la ficha de la vela
 * digan el mismo número con los mismos decimales. Los decimales dependen de la magnitud: un CEDEAR
 * a 26.000 pesos con dos decimales es ruido, un bono a 0,85 con dos decimales pierde información. */

const formateadores = new Map<number, Intl.NumberFormat>()
function formateador(decimales: number): Intl.NumberFormat {
  let f = formateadores.get(decimales)
  if (!f) {
    f = new Intl.NumberFormat('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })
    formateadores.set(decimales, f)
  }
  return f
}

export function decimalesPrecio(v: number): number {
  const a = Math.abs(v)
  if (a >= 10000) return 0
  if (a >= 1) return 2
  return 4
}

export function formatoPrecio(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return formateador(decimalesPrecio(v)).format(v)
}

/** Para osciladores y medias: magnitudes muy distintas (RSI 0-100, MACD ±0,5, OBV millones). */
export function formatoValor(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return formatoVolumen(v)
  if (a >= 100) return formateador(1).format(v)
  if (a >= 1) return formateador(2).format(v)
  return formateador(3).format(v)
}

export function formatoVolumen(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e9) return `${formateador(1).format(v / 1e9)} B`
  if (a >= 1e6) return `${formateador(1).format(v / 1e6)} M`
  if (a >= 1e3) return `${formateador(1).format(v / 1e3)} k`
  return formateador(0).format(v)
}

export function formatoPct(v: number): string {
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${formateador(2).format(Math.abs(v))}%`
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** `2026-10-15` → `15/10/26`. */
export function fechaCorta(fecha: string | undefined): string {
  if (!fecha) return ''
  const [a, m, d] = fecha.slice(0, 10).split('-')
  return a && m && d ? `${d}/${m}/${a.slice(2)}` : fecha
}

/** Etiqueta del eje de fechas: día y mes si la ventana es corta, mes y año si es larga. */
function fechaEje(fecha: string, larga: boolean): string {
  const [a, m, d] = fecha.slice(0, 10).split('-')
  if (!a || !m || !d) return fecha
  return larga ? `${MESES[Number(m) - 1] ?? m} ${a.slice(2)}` : `${d}/${m}`
}

/** Separación mínima en píxeles entre dos fechas del eje: lo que ocupa `sep 26` más aire. */
const SEPARACION_FECHAS = 78
const PASOS_FECHAS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]

/**
 * Qué barras rotular en el eje de fechas.
 *
 * Se rotulan los índices múltiplos de un paso fijo (y no "4 fechas repartidas en la ventana"): así,
 * al desplazar, cada fecha viaja con su vela en lugar de saltar de una a otra en cada frame. El paso
 * sólo cambia con el zoom.
 */
export function ticksFechas(barras: BarraOut[], escalaX: EscalaX): { indice: number; x: number; texto: string }[] {
  if (barras.length === 0 || escalaX.pasoX <= 0) return []
  // Pasos "redondos": durante el pellizco el paso no cambia con cada píxel, sólo al cruzar uno.
  const minimo = SEPARACION_FECHAS / escalaX.pasoX
  const paso = PASOS_FECHAS.find(p => p >= minimo) ?? Math.ceil(minimo)
  const primera = barras[escalaX.inicio]?.fecha
  const ultima = barras[escalaX.fin]?.fecha
  const dias = primera && ultima ? (Date.parse(ultima) - Date.parse(primera)) / 86_400_000 : 0
  const larga = dias > 150
  const out: { indice: number; x: number; texto: string }[] = []
  for (let i = Math.ceil(escalaX.inicio / paso) * paso; i <= escalaX.fin; i += paso) {
    const x = escalaX.xDeIndice(i)
    // Una etiqueta cortada contra el borde se lee peor que ninguna.
    if (x < 18 || x > escalaX.ancho - 18) continue
    const b = barras[i]
    if (b) out.push({ indice: i, x, texto: fechaEje(b.fecha, larga) })
  }
  return out
}

/** Paso "redondo" (1, 2 o 5 por una potencia de 10) igual o mayor que `minimo`. Lo usa el arrastre
 * de las zonas: un píxel de alto equivale a un precio con decimales que nadie eligió, y un borde en
 * 165,2871 sugiere una precisión que el dedo no tiene. */
export function pasoRedondo(minimo: number): number {
  if (!(minimo > 0) || !Number.isFinite(minimo)) return 0.01
  const potencia = Math.pow(10, Math.floor(Math.log10(minimo)))
  for (const m of [1, 2, 5, 10]) if (m * potencia >= minimo) return m * potencia
  return 10 * potencia
}

/** Redondea a múltiplo de `paso` sin arrastrar el ruido de punto flotante (165.29999999). */
export function redondearA(valor: number, paso: number): number {
  if (!(paso > 0)) return valor
  return Number((Math.round(valor / paso) * paso).toFixed(8))
}

/** Un precio como lo escribe el input de una zona: punto decimal, sin separador de miles, sin
 * ceros de más (`165.3`, `25200`). */
export function textoBorde(valor: number): string {
  return String(Number(valor.toFixed(8)))
}
