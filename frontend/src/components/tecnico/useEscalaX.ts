import { useMemo } from 'react'

/**
 * Escala X compartida entre paneles (precio, indicadores, volumen): todos dibujan el mismo tramo
 * de barras sobre el mismo ancho, así el índice de una barra cae en el mismo píxel en todos los
 * paneles y el crosshair no se desincroniza.
 *
 * `inicio`/`fin` son la **ventana visible** (índices de barra, ambos inclusive) que produce
 * `useVentanaVisible` al hacer zoom o desplazar. Los paneles siguen recibiendo las series
 * completas y usan estos índices para acotar lo que dibujan y el rango de la escala Y: recortar
 * los arrays en cambio rompería la alineación 1:1 entre barras, señales, curvas e indicadores,
 * que es el contrato del backtest.
 */
export interface EscalaX {
  ancho: number
  n: number
  inicio: number
  fin: number
  visibles: number
  pasoX: number
  xDeIndice: (i: number) => number
  indiceDeX: (x: number) => number
  /** ¿El índice cae dentro de la ventana visible? Con un margen de una barra, para que el trazo
   * de una serie entre y salga del panel en vez de cortarse justo en el borde. */
  visible: (i: number) => boolean
}

export function useEscalaX(n: number, ancho: number, ventana?: { inicio: number; fin: number }): EscalaX {
  const inicioPedido = ventana?.inicio ?? 0
  const finPedido = ventana?.fin ?? n - 1

  return useMemo(() => {
    const inicio = Math.max(0, Math.min(inicioPedido, Math.max(0, n - 1)))
    const fin = Math.max(inicio, Math.min(finPedido, Math.max(0, n - 1)))
    const visibles = n > 0 ? fin - inicio + 1 : 0
    const pasoX = visibles > 0 ? ancho / visibles : ancho
    return {
      ancho,
      n,
      inicio,
      fin,
      visibles,
      pasoX,
      xDeIndice: (i: number) => (i - inicio) * pasoX + pasoX / 2,
      indiceDeX: (x: number) => Math.min(fin, Math.max(inicio, inicio + Math.floor(x / pasoX))),
      visible: (i: number) => i >= inicio - 1 && i <= fin + 1,
    }
  }, [n, ancho, inicioPedido, finPedido])
}
