import { useEffect, useRef, useState, type RefObject } from 'react'

/** Ancho en píxeles del contenedor, actualizado por `ResizeObserver`. Los paneles del gráfico
 * técnico dibujan SVG a mano (no un contenedor responsive de una lib), así que necesitan el
 * ancho real para calcular la escala X. */
export function useAnchoContenedor<T extends HTMLElement>(minimo = 280): [RefObject<T>, number] {
  const ref = useRef<T>(null)
  const [ancho, setAncho] = useState(minimo)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width
      if (w) setAncho(Math.max(minimo, w))
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [minimo])

  return [ref, ancho]
}
