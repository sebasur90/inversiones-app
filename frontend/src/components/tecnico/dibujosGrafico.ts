import type { BarraOut, DibujoOut } from '../../api'
import type { EscalaX } from './useEscalaX'

/** Geometría de los dibujos manuales sobre el panel de precio, y la prueba de si un toque cae sobre
 * uno. Pura: la usan por igual el dibujo (`DibujosGrafico`) y la selección (`PanelPrecio`), así lo
 * que se ve y lo que se puede tocar son siempre lo mismo.
 *
 * Un dibujo está anclado por **fecha y precio**. Acá la fecha se traduce a un índice de barra
 * (fraccionario fuera del rango cargado) y de ahí a píxeles, de modo que sobrevive a cambios de
 * período y de intervalo. Una recta de tendencia es recta en la pantalla (en escala logarítmica
 * también: es lo que el usuario dibujó con el dedo). */

/** Retrocesos de Fibonacci que se dibujan. 0 % es el final del movimiento y 100 % su comienzo. */
export const NIVELES_FIBONACCI = [0, 0.236, 0.382, 0.5, 0.618, 1] as const

export const ETIQUETA_TIPO: Record<DibujoOut['tipo'], string> = {
  horizontal: 'Soporte / resistencia', tendencia: 'Línea de tendencia', fibonacci: 'Fibonacci',
}

/** Qué es una línea horizontal para el precio de hoy: soporte si queda por debajo del último
 * cierre, resistencia si queda por encima. */
export function rolHorizontal(precio: number, ultimoCierre: number | null): 'Soporte' | 'Resistencia' | 'Línea' {
  if (ultimoCierre == null) return 'Línea'
  return precio < ultimoCierre ? 'Soporte' : 'Resistencia'
}

const dia = (f: string) => f.slice(0, 10)
const MS_DIA = 86_400_000

/** Índice de barra de una fecha. Dentro del rango, la primera barra con fecha >= la pedida (en
 * semanal o mensual, la barra que contiene ese día). Fuera, se extrapola con la separación media
 * entre barras: una línea de tendencia que arranca antes del tramo cargado sigue teniendo pendiente. */
export function indiceDeFecha(barras: BarraOut[], fecha: string): number {
  const n = barras.length
  if (n === 0) return 0
  const f = dia(fecha)
  let lo = 0
  let hi = n
  while (lo < hi) {
    const medio = (lo + hi) >> 1
    if (dia(barras[medio].fecha) < f) lo = medio + 1
    else hi = medio
  }
  if (lo < n && !(lo === 0 && dia(barras[0].fecha) > f)) return lo
  const t0 = Date.parse(dia(barras[0].fecha))
  const tN = Date.parse(dia(barras[n - 1].fecha))
  const diasPorBarra = n > 1 ? Math.max(0.5, (tN - t0) / MS_DIA / (n - 1)) : 1
  if (lo >= n) return n - 1 + (Date.parse(f) - tN) / MS_DIA / diasPorBarra
  return -(t0 - Date.parse(f)) / MS_DIA / diasPorBarra
}

/** Precio de cada nivel de Fibonacci entre los dos puntos del dibujo. */
export function nivelesFibonacci(precio1: number, precio2: number): { nivel: number; precio: number }[] {
  return NIVELES_FIBONACCI.map(nivel => ({ nivel, precio: precio2 + (precio1 - precio2) * nivel }))
}

export interface Segmento {
  x1: number
  y1: number
  x2: number
  y2: number
  etiqueta?: string
  /** Para el Fibonacci: el nivel (0 a 1) de esta línea. */
  nivel?: number
}

export interface GeometriaDibujo {
  segmentos: Segmento[]
  /** Los puntos de anclaje en píxeles (las manijas del dibujo seleccionado). */
  anclas: { x: number; y: number }[]
}

export function geometriaDibujo(
  d: DibujoOut, barras: BarraOut[], escalaX: EscalaX, yDeValor: (v: number) => number,
): GeometriaDibujo {
  const ancho = escalaX.ancho
  const x1 = escalaX.xDeIndice(indiceDeFecha(barras, d.fecha1))
  const y1 = yDeValor(d.precio1)

  if (d.tipo === 'horizontal' || d.fecha2 == null || d.precio2 == null) {
    return { segmentos: [{ x1: 0, y1, x2: ancho, y2: y1 }], anclas: [{ x: x1, y: y1 }] }
  }

  const x2 = escalaX.xDeIndice(indiceDeFecha(barras, d.fecha2))
  const y2 = yDeValor(d.precio2)
  const anclas = [{ x: x1, y: y1 }, { x: x2, y: y2 }]

  if (d.tipo === 'tendencia') {
    // Se extiende hacia la derecha hasta el borde del panel. Con los dos puntos en la misma
    // columna (no debería: el servidor exige días distintos) queda el segmento.
    const dx = x2 - x1
    const xFin = Math.max(ancho, x1, x2)
    const yFin = dx !== 0 ? y2 + ((y2 - y1) / dx) * (xFin - x2) : y2
    return { segmentos: [{ x1, y1, x2: xFin, y2: yFin }], anclas }
  }

  // Fibonacci: desde el más a la izquierda de los dos anclajes hasta el borde derecho.
  const xDesde = Math.min(x1, x2)
  return {
    anclas,
    segmentos: nivelesFibonacci(d.precio1, d.precio2).map(({ nivel, precio }) => {
      const y = yDeValor(precio)
      return { x1: xDesde, y1: y, x2: ancho, y2: y, nivel, etiqueta: `${(nivel * 100).toFixed(1).replace('.', ',').replace(',0', '')}%` }
    }),
  }
}

/** Distancia en píxeles de un punto a un segmento. */
export function distanciaASegmento(px: number, py: number, s: Segmento): number {
  const dx = s.x2 - s.x1
  const dy = s.y2 - s.y1
  const largo2 = dx * dx + dy * dy
  const t = largo2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - s.x1) * dx + (py - s.y1) * dy) / largo2))
  return Math.hypot(px - (s.x1 + t * dx), py - (s.y1 + t * dy))
}

/** Radio, en píxeles, dentro del cual un toque cuenta como "sobre el dibujo": lo que un dedo acierta
 * sin apuntar. */
export const RADIO_TOQUE_DIBUJO = 14

/** El dibujo más cercano al punto `(x, y)` del panel, si alguno queda dentro del radio. */
export function dibujoEnPunto(
  dibujos: DibujoOut[], x: number, y: number, barras: BarraOut[], escalaX: EscalaX,
  yDeValor: (v: number) => number,
): DibujoOut | null {
  let mejor: DibujoOut | null = null
  let distanciaMejor = RADIO_TOQUE_DIBUJO
  for (const d of dibujos) {
    for (const s of geometriaDibujo(d, barras, escalaX, yDeValor).segmentos) {
      const dist = distanciaASegmento(x, y, s)
      if (dist <= distanciaMejor) {
        mejor = d
        distanciaMejor = dist
      }
    }
  }
  return mejor
}
