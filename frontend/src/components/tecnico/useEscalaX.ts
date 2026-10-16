import { useMemo } from 'react'

/**
 * Escala X compartida entre paneles (precio, indicadores, volumen): todos dibujan el mismo tramo
 * de barras sobre el mismo ancho, así el índice de una barra cae en el mismo píxel en todos los
 * paneles y el crosshair no se desincroniza.
 *
 * La ventana puede pasar de la última barra: el margen vacío a la derecha (el "futuro") ocupa
 * ancho pero no tiene índices; `indiceDeX` ahí devuelve la última barra.
 *
 * La **ventana visible** que produce `useVentanaVisible` puede empezar en una fracción de barra:
 * el desplazamiento con el dedo sigue al dedo píxel a píxel, no a saltos de una vela. Esa fracción
 * vive sólo en `xDeIndice`/`indiceDeX`; `inicio`/`fin` son **enteros** (la primera y la última
 * barra con datos al menos en parte a la vista), así los bucles de los paneles no cambian. Lo que queda a
 * medias contra el borde lo recorta el propio `<svg>`.
 *
 * Los paneles siguen recibiendo las series completas y usan estos índices para acotar lo que
 * dibujan y el rango de la escala Y: recortar los arrays en cambio rompería la alineación 1:1 entre
 * barras, señales, curvas e indicadores, que es el contrato del backtest.
 */
export interface EscalaX {
  ancho: number
  n: number
  inicio: number
  fin: number
  /** Barras a la vista, redondeado (para mostrar). */
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
    const ultimo = Math.max(0, n - 1)
    const desde = Math.max(0, Math.min(inicioPedido, ultimo))
    // La ventana puede pasar de la última barra: ese margen vacío cuenta para el ancho de cada
    // barra, pero no hay nada que dibujar ahí.
    const hastaPedido = Math.max(desde, finPedido)
    const hasta = Math.min(hastaPedido, ultimo)
    const visiblesExactos = n > 0 ? hastaPedido - desde + 1 : 0
    const pasoX = visiblesExactos > 0 ? ancho / visiblesExactos : ancho
    // El epsilon evita que un 12.0000001 de la aritmética de punto flotante sume una barra fantasma.
    const inicio = Math.floor(desde + 1e-6)
    const fin = Math.min(ultimo, Math.max(inicio, Math.ceil(hasta - 1e-6)))
    return {
      ancho,
      n,
      inicio,
      fin,
      visibles: n > 0 ? Math.round(hasta - desde + 1) : 0,
      pasoX,
      xDeIndice: (i: number) => (i - desde) * pasoX + pasoX / 2,
      indiceDeX: (x: number) => Math.min(fin, Math.max(inicio, Math.floor(desde + x / (pasoX || 1)))),
      visible: (i: number) => i >= inicio - 1 && i <= fin + 1,
    }
  }, [n, ancho, inicioPedido, finPedido])
}
