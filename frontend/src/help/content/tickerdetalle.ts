import { HelpContent } from '../types'

export type TickerDetalleHelpKey =
  | 'tickerdetalle_total_pl'
  | 'tickerdetalle_retorno_anualizado'
  | 'tickerdetalle_precio_nominal'
  | 'tickerdetalle_valor_posicion'

export const TICKERDETALLE_HELP: Record<TickerDetalleHelpKey, HelpContent> = {
  tickerdetalle_total_pl: {
    title: 'Total P&L',
    shortDescription: 'Profit & Loss total: la ganancia o pérdida acumulada del instrumento. Es la suma de: Realizado (ventas cerradas) + No realizado (en cartera) + Ingresos (dividendos/cupones) − Comisiones pagadas.',
    example: 'Si realizaste una venta ganando $100, tenés un activo que vale $200 más de lo que pagaste, y cobraste $50 en dividendos, tu P&L total es 100 + 200 + 50 = $350 (ignorando comisiones).',
  },
  tickerdetalle_retorno_anualizado: {
    title: 'Retorno anualizado',
    shortDescription: 'El rendimiento porcentual escalado a un año (12 meses) para ser comparable con otros períodos. Si tuviste +10% en 6 meses, el retorno anualizado es aproximadamente +20% (con capitalización).',
    whyItMatters: 'Permite comparar rendimientos de períodos de diferentes duraciones (3 meses, 1 año, 2 años). La métrica bruta "10% en 6 meses" no dice si fue bueno o malo sin contexto.',
    example: '+5% en 3 meses ≈ +20% anualizado. Una volatilidad anualizada es más comparable que volatilidad de un solo mes.',
  },
  tickerdetalle_precio_nominal: {
    title: 'Precio nominal',
    shortDescription: 'Precio del instrumento expresado en su moneda original, sin conversión a dólares ni ajuste por inflación. Es el precio literal que cotiza en el mercado en esa moneda.',
    relatedTerms: ['cer', 'mep'],
  },
  tickerdetalle_valor_posicion: {
    title: 'Valor posición',
    shortDescription: 'El valor total de tu tenencia en ese instrumento en esa fecha: cantidad × precio unitario. Es diferente del precio unitario (que es por acción/bono/CEDEAR).',
    example: 'Si tenés 100 acciones de AL30 que cotizan a 100 cada una, tu valor de posición es 10.000 (no 100).',
  },
}
