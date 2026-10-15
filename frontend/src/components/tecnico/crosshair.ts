import type { PointerEvent, RefObject } from 'react'
import type { EscalaX } from './useEscalaX'

/** Hover del **mouse** sobre un panel SVG, traducido a índice de barra vía `escalaX`.
 * Compartido entre PanelPrecio/PanelIndicador/PanelVolumen para que el crosshair quede
 * sincronizado sin importar sobre qué panel esté el puntero.
 *
 * Sólo mouse: en el celular la cruz la maneja `useVentanaVisible` (toque para fijarla, mantener
 * apretado para recorrer velas), porque ahí un dedo que se mueve es desplazamiento o scroll, y la
 * cruz no puede desaparecer al levantarlo. */
export function manejadoresPuntero(
  svgRef: RefObject<SVGSVGElement | null>,
  escalaX: EscalaX,
  onHover: (i: number | null) => void,
) {
  return {
    onPointerMove: (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') return
      const rect = svgRef.current?.getBoundingClientRect()
      if (!rect) return
      onHover(escalaX.indiceDeX(e.clientX - rect.left))
    },
    onPointerLeave: (e: PointerEvent) => {
      if (e.pointerType === 'mouse') onHover(null)
    },
  }
}
