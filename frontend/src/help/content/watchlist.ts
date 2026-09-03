import { HelpContent } from '../types'

export type WatchlistHelpKey =
  | 'watchlist_precio_objetivo'
  | 'watchlist_zona_compra'
  | 'watchlist_distancia'

export const WATCHLIST_HELP: Record<WatchlistHelpKey, HelpContent> = {
  watchlist_precio_objetivo: {
    title: 'Objetivo de compra',
    shortDescription: 'El precio al que querés comprar el instrumento. Sale de la columna Objetivo de la pestaña Watchlist del Sheet, siempre como un valor fijo (no admite modo Porcentaje: acá no hay precio de compra previo del que partir).',
    whyItMatters: 'Fijarlo en frío, antes de que el precio se mueva, evita perseguir una suba o dudar en el momento.',
    relatedTerms: ['objetivo'],
  },
  watchlist_zona_compra: {
    title: 'Zona de compra',
    shortDescription: 'Se dispara cuando el precio de mercado baja hasta el Objetivo o por debajo. Es la misma mecánica que el stop-loss de una posición, pero mirando hacia abajo en vez de hacia arriba.',
    whyItMatters: 'Convierte "avisame cuando esté para comprar" en algo automático, sin tener que revisar la cotización todos los días.',
    howItIsCalculated: 'Se compara el último precio conocido del ticker contra su Objetivo. 🛒 ZONA: el precio ya está en el Objetivo o por debajo. 👀 CERCA (amarillo): todavía no, pero está dentro del margen que configuraste en Ajustes → Alertas de precio.',
    limitations: 'Usa el último precio registrado, no una cotización en vivo. Un ticker sin Objetivo cargado en el Sheet nunca va a avisar. Es sólo una señal, no ejecuta ninguna compra.',
    relatedTerms: ['watchlist_precio_objetivo', 'watchlist_distancia'],
  },
  watchlist_distancia: {
    title: 'Distancia al objetivo',
    shortDescription: '(Objetivo − Precio actual) ÷ Precio actual. Negativa mientras el precio esté por encima del Objetivo (todavía caro); cero o positiva una vez que entró en zona de compra.',
    whyItMatters: 'Ordena la lista por lo más cerca de comprarse, para no tener que hacer la cuenta ticker por ticker.',
  },
}
