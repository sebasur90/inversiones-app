import { HelpContent } from '../types'

export type WatchlistHelpKey =
  | 'watchlist_precio_objetivo'
  | 'watchlist_zona_compra'
  | 'watchlist_distancia'

export const WATCHLIST_HELP: Record<WatchlistHelpKey, HelpContent> = {
  watchlist_precio_objetivo: {
    title: 'Comprar por debajo de',
    shortDescription: 'El precio por debajo del cual querés comprar el instrumento. Es el atajo para la forma más común de zona de compra: una abierta hacia abajo, sin piso.',
    whyItMatters: 'Fijarlo en frío, antes de que el precio se mueva, evita perseguir una suba o dudar en el momento.',
    howToInterpret: 'Siempre es un precio fijo, nunca un porcentaje: acá no hay precio de compra previo del que partir, a diferencia del stop-loss o el objetivo de una posición.',
    limitations: 'Si querés un rango con piso y techo, o medirlo sobre el precio del subyacente en dólares, hay que dibujar la zona en el gráfico de análisis técnico: eso no cabe en un solo número y por eso acá se muestra en modo lectura.',
    relatedTerms: ['zonas_precio', 'objetivo'],
  },
  watchlist_zona_compra: {
    title: 'Zona de compra',
    shortDescription: 'Se dispara cuando el precio de mercado baja y entra en la zona de compra que definiste. Es la misma mecánica que el stop-loss de una posición, pero mirando hacia abajo en vez de hacia arriba.',
    whyItMatters: 'Convierte "avisame cuando esté para comprar" en algo automático, sin tener que revisar la cotización todos los días.',
    howItIsCalculated: 'Se compara el último precio conocido del ticker contra el techo de la zona, que es el borde que dispara. 🛒 ZONA: el precio ya está en el techo o por debajo. 👀 CERCA (amarillo): todavía no, pero está dentro del margen que configuraste en Ajustes → Alertas de precio.',
    limitations: 'Usa el último precio registrado, no una cotización en vivo. Un instrumento sin zona nunca va a avisar. Es sólo una señal, no ejecuta ninguna compra. Esta lista compara contra el precio local: una zona medida sobre el subyacente en dólares se evalúa en su propia moneda y no muestra distancia acá.',
    relatedTerms: ['zonas_precio', 'watchlist_precio_objetivo', 'watchlist_distancia'],
  },
  watchlist_distancia: {
    title: 'Distancia a la zona',
    shortDescription: '(Techo de la zona − Precio actual) ÷ Precio actual. Negativa mientras el precio esté por encima de la zona (todavía caro); cero o positiva una vez que entró.',
    whyItMatters: 'Ordena la lista por lo más cerca de comprarse, para no tener que hacer la cuenta ticker por ticker.',
  },
}
