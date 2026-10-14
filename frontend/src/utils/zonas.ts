/**
 * Cómo se nombra una zona de precio en la app.
 *
 * Una zona es un rango con los dos bordes opcionales, así que no se puede imprimir con un solo
 * formato: "4500 – 4900", "≤ 4900" y "≥ 2000" son tres frases distintas y las tres son zonas
 * válidas. Está acá y no en cada pantalla porque la watchlist, el resumen del gráfico y el detalle
 * del instrumento tienen que decir lo mismo.
 */
import type { TipoZona, ZonaPrecioOut } from '../api'

/** El borde cuyo cruce dispara el aviso: el techo si se compra (el precio baja y entra en la
 * banda), el piso si se vende. */
export function bordeDisparo(zona: ZonaPrecioOut, tipo: TipoZona): number | null {
  return tipo === 'compra' ? zona.techo : zona.piso
}

/**
 * La zona en palabras. `formatear` recibe el precio y la moneda de la zona, así que la pantalla
 * decide si tapa los importes (modo privacidad) y con qué símbolo los muestra.
 */
export function textoZona(
  zona: ZonaPrecioOut | null | undefined,
  formatear: (valor: number, moneda: string) => string,
): string {
  if (!zona) return '—'
  const { piso, techo, moneda } = zona
  const f = (v: number) => formatear(v, moneda)
  if (piso != null && techo != null) return `${f(piso)} – ${f(techo)}`
  if (techo != null) return `≤ ${f(techo)}`
  if (piso != null) return `≥ ${f(piso)}`
  return '—'
}

/**
 * ¿Esta zona se puede representar con un solo input de precio?
 *
 * El detalle de la watchlist tiene el atajo "comprar por debajo de X", que es una zona de compra
 * abierta hacia abajo sobre la serie local. Una zona con piso, o medida sobre el subyacente, no
 * cabe en ese input: mostrarla ahí la truncaría al guardar, así que esas se editan en el gráfico.
 */
export function cabeEnUnInput(zona: ZonaPrecioOut | null | undefined): boolean {
  return !zona || (zona.piso == null && zona.variante === 'local')
}
