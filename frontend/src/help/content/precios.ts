import { HelpContent } from '../types'

export type PreciosHelpKey =
  | 'precios_titulo'
  | 'precios_ars_nominal'
  | 'precios_usd_mep'
  | 'precios_ars_real_cer'
  | 'precios_ultimo_registro'
  | 'precios_ticker'

export const PRECIOS_HELP: Record<PreciosHelpKey, HelpContent> = {
  precios_titulo: {
    title: 'Seguimiento de precios',
    shortDescription: 'Gráfico histórico de la evolución del precio de tus instrumentos. Permite alternar entre tres vistas: precio nominal (moneda original), dólar MEP (tipo de cambio implícito) y valor real ajustado por inflación (CER).',
    whyItMatters: 'Ver cómo se movió el precio te ayuda a entender patrones, detectar volatilidad excesiva, evaluar cuándo fue buen momento para comprar o vender, y comparar la rentabilidad real (ajustada por inflación o FX) contra la nominal.',
    relatedTerms: ['cer', 'mep'],
  },
  precios_ars_nominal: {
    title: 'ARS Nominal',
    shortDescription: 'Precio del instrumento expresado en pesos argentinos sin ajustar por inflación. Es el precio literal que cotiza en el mercado local.',
    whyItMatters: 'La cifra nominal es el punto de partida, pero no refleja cambios en tu poder de compra. Si el precio subió 20% pero la inflación fue 35%, perdiste poder de compra en términos reales. Por eso es útil compararlo con la vista "ARS Real (CER)".',
    relatedTerms: ['cer'],
  },
  precios_usd_mep: {
    title: 'USD (MEP)',
    shortDescription: 'Precio convertido al dólar MEP (Mercado Electrónico de Pagos). Es la cotización del dólar que resulta de las operaciones de compraventa en el mercado local de valores, no del dólar oficial.',
    whyItMatters: 'El MEP es la forma legal más accesible de "pesificar" dólares o dolarizar pesos sin usar dólar billete. Ver tu cartera en USD-MEP te permite comparar tu rentabilidad contra benchmarks en dólares y entender tu exposición real a FX.',
    relatedTerms: ['mep'],
  },
  precios_ars_real_cer: {
    title: 'ARS Real (CER)',
    shortDescription: 'Precio del instrumento ajustado por el CER (Coeficiente de Estabilización de Referencia), que sigue la inflación en Argentina. Muestra el valor en pesos descontando la erosión del poder de compra.',
    whyItMatters: 'Es la métrica más honesta para saber si ganaste dinero de verdad. Un precio que subió 50% en ARS nominal pero solo 10% en CER significa que ganaste, pero menos de lo que parece a primera vista porque la inflación comió la diferencia.',
    relatedTerms: ['cer'],
  },
  precios_ultimo_registro: {
    title: 'Último registro',
    shortDescription: 'El precio más reciente disponible del instrumento en la vista seleccionada, junto con la fecha en que se cargó ese dato.',
    whyItMatters: 'Te da la cotización más actualizada para saber el estado actual del precio. Es útil para saber si un movimiento reciente fue significativo o una fluctuación normal, y para validar que los datos sean recientes.',
  },
  precios_ticker: {
    title: 'Ticker',
    shortDescription: 'Símbolo único que identifica al instrumento en el mercado. Por ejemplo: "AL30" es un bono argentino, "GGAL" es Grupo Galicia, "GD30D" es un dólar MEP a plazo.',
    whyItMatters: 'El ticker es la forma estándar de referirse a un instrumento sin ambigüedad. Cuando buscás noticias, precios, o hablás del instrumento con otros inversores, el ticker es lo más rápido y preciso.',
  },
}
