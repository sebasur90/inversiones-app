/**
 * Cómo se nombra una zona de precio en la app.
 *
 * Una zona es un rango con los dos bordes opcionales, así que no se puede imprimir con un solo
 * formato: "4500 – 4900", "≤ 4900" y "≥ 2000" son tres frases distintas y las tres son zonas
 * válidas. Está acá y no en cada pantalla porque la watchlist, el resumen del gráfico y el detalle
 * del instrumento tienen que decir lo mismo.
 */
import type { TipoZona, VarianteSerie, ZonaPrecioOut } from '../api'

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
 * abierta hacia abajo sobre la **serie de referencia** del instrumento (USD para un CEDEAR con su
 * serie del subyacente, local para el resto). Una zona con piso, o medida sobre la otra serie, no
 * cabe en ese input: mostrarla ahí la truncaría o la pasaría de serie al guardar, así que esas se
 * editan en el gráfico. Una zona vencida sí: no tiene nada que conservar y el atajo es la forma
 * más corta de reemplazarla.
 */
export function cabeEnUnInput(
  zona: ZonaPrecioOut | null | undefined, referencia: VarianteSerie = 'local',
): boolean {
  return !zona || zona.vencida || (zona.piso == null && zona.variante === referencia)
}
