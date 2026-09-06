import { useMemo } from 'react'

/**
 * Escala X compartida entre paneles (precio, indicadores, volumen): todos dibujan la misma
 * cantidad de barras sobre el mismo ancho, así el índice de una barra cae en el mismo píxel en
 * todos los paneles y el crosshair no se desincroniza.
 */
export interface EscalaX {
  ancho: number
  n: number
  pasoX: number
  xDeIndice: (i: number) => number
  indiceDeX: (x: number) => number
}

export function useEscalaX(n: number, ancho: number): EscalaX {
  return useMemo(() => {
    const pasoX = n > 0 ? ancho / n : ancho
    return {
      ancho,
      n,
      pasoX,
      xDeIndice: (i: number) => i * pasoX + pasoX / 2,
      indiceDeX: (x: number) => Math.min(Math.max(n - 1, 0), Math.max(0, Math.floor(x / pasoX))),
    }
  }, [n, ancho])
}
