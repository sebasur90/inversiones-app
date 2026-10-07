/** Cómo se nombra y se colorea un aviso de Telegram dentro de la app.
 *
 * El backend ya manda resuelto lo importante de cada aviso (`accion`, `encabezado`, `etiqueta`),
 * justamente para que el historial de la app y lo que llegó al celular no puedan contar cosas
 * distintas. Acá sólo viven el color, el icono y las dos o tres frases que la pantalla arma.
 *
 * `tipo` **no** es una unión cerrada: una señal técnica viaja como `estrategia:<id>` porque el id
 * de la estrategia tiene que entrar en la clave del aviso (ver `alertas_engine.PREFIJO_SENAL`).
 * Por eso se pregunta con `esAvisoDeSenal()` y nunca comparando contra literales.
 */
import type { AccionAviso, AlertaPrecioOut } from '../api'
import { ETIQUETA_MOTIVO } from '../components/tecnico/motivosSalida'

const PREFIJO_SENAL = 'estrategia:'

export function esAvisoDeSenal(tipo: string): boolean {
  return tipo.startsWith(PREFIJO_SENAL)
}

/** Color del texto de la acción. Nunca es la única señal: siempre va con la palabra. */
export const COLOR_ACCION: Record<AccionAviso, string> = {
  COMPRA: 'text-app-pos',
  VENTA: 'text-app-neg',
  REVISAR: 'text-app-accent',
}

export const ETIQUETA_ACCION: Record<AccionAviso, string> = {
  COMPRA: 'Comprar',
  VENTA: 'Vender',
  REVISAR: 'Revisar',
}

/** De dónde salió el aviso, en una frase. Es lo que el mensaje viejo no decía. */
export function etiquetaOrigen(aviso: AlertaPrecioOut): string {
  if (aviso.cartera) return `cartera ${aviso.cartera}`
  if (aviso.origen === 'watchlist') return aviso.en_cartera ? 'watchlist · ya tenés posición' : 'watchlist'
  return '—'
}

/** Qué regla lo disparó: la estrategia y su motivo, o el nivel de precio. */
export function etiquetaRegla(aviso: AlertaPrecioOut): string {
  if (!esAvisoDeSenal(aviso.tipo)) return aviso.etiqueta
  const motivo = aviso.senal_motivo ? ETIQUETA_MOTIVO[aviso.senal_motivo] ?? aviso.senal_motivo : null
  const nombre = aviso.estrategia_nombre ?? 'Estrategia'
  return motivo ? `${nombre} · ${motivo}` : nombre
}
