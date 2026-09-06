import type { MouseEvent, RefObject, TouchEvent } from 'react'
import type { EscalaX } from './useEscalaX'

/** Maneja hover/touch sobre un panel SVG y lo traduce a índice de barra vía `escalaX`.
 * Compartido entre PanelPrecio/PanelIndicador/PanelVolumen para que el crosshair quede
 * sincronizado sin importar sobre qué panel esté el puntero. */
export function manejadoresPuntero(
  svgRef: RefObject<SVGSVGElement | null>,
  escalaX: EscalaX,
  onHover: (i: number | null) => void,
) {
  const desdeClientX = (clientX: number) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    onHover(escalaX.indiceDeX(clientX - rect.left))
  }
  return {
    onMouseMove: (e: MouseEvent) => desdeClientX(e.clientX),
    onMouseLeave: () => onHover(null),
    onTouchMove: (e: TouchEvent) => {
      const t = e.touches[0]
      if (t) desdeClientX(t.clientX)
    },
    onTouchEnd: () => onHover(null),
  }
}
