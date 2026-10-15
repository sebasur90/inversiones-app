import { useEffect, useState } from 'react'

export interface AltosGrafico {
  precio: number
  oscilador: number
  equity: number
  volumen: number
}

const NORMAL: AltosGrafico = { precio: 240, oscilador: 90, equity: 110, volumen: 70 }

/** Lo que ocupa todo lo que no es panel en pantalla completa: encabezado del overlay, ficha,
 * leyenda, eje de fechas, pie y márgenes. Estimado, no medido: errarle por unos píxeles sólo
 * agrega un poco de scroll, y medirlo obligaría a renderizar dos veces. */
const FIJO = { vertical: 230, horizontal: 175 }
/** Título y margen de cada panel debajo del precio. */
const POR_PANEL = 26
const PESO = { precio: 3, oscilador: 1, equity: 1.2, volumen: 0.8 }

function acotar(v: number, min: number, max: number) {
  return Math.round(Math.max(min, Math.min(max, v)))
}

function medirVentana() {
  return { alto: window.innerHeight, ancho: window.innerWidth }
}

/**
 * Altos de los paneles del gráfico. En la vista normal son fijos; en pantalla completa se reparten
 * el alto de la ventana (precio ~3 partes, cada panel inferior ~1), así en el celular horizontal el
 * gráfico entra entero en vez de obligar a scrollear un panel de precio de 400 px. Se recalcula al
 * girar el teléfono.
 */
export function useAltosGrafico(
  fullscreen: boolean,
  paneles: { osciladores: number; equity: boolean; volumen: boolean },
): AltosGrafico {
  const [ventana, setVentana] = useState(medirVentana)

  useEffect(() => {
    if (!fullscreen) return
    const actualizar = () => setVentana(medirVentana())
    actualizar()
    window.addEventListener('resize', actualizar)
    window.addEventListener('orientationchange', actualizar)
    return () => {
      window.removeEventListener('resize', actualizar)
      window.removeEventListener('orientationchange', actualizar)
    }
  }, [fullscreen])

  if (!fullscreen) return NORMAL

  const horizontal = ventana.ancho > ventana.alto
  const extras = paneles.osciladores + (paneles.equity ? 1 : 0) + (paneles.volumen ? 1 : 0)
  const disponible = ventana.alto - (horizontal ? FIJO.horizontal : FIJO.vertical) - extras * POR_PANEL
  const pesoTotal = PESO.precio
    + paneles.osciladores * PESO.oscilador
    + (paneles.equity ? PESO.equity : 0)
    + (paneles.volumen ? PESO.volumen : 0)
  const unidad = disponible / pesoTotal
  const minPrecio = horizontal ? 140 : 200
  const minOtro = horizontal ? 50 : 70

  return {
    precio: acotar(unidad * PESO.precio, minPrecio, 560),
    oscilador: acotar(unidad * PESO.oscilador, minOtro, 170),
    equity: acotar(unidad * PESO.equity, minOtro, 190),
    volumen: acotar(unidad * PESO.volumen, minOtro * 0.8, 130),
  }
}
