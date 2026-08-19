import { HelpContent } from '../types'

export type ComparadorHelpKey =
  | 'comparador_base100'
  | 'comparador_nominal'

export const COMPARADOR_HELP: Record<ComparadorHelpKey, HelpContent> = {
  comparador_base100: {
    title: 'Base 100',
    shortDescription: 'Normaliza todas las series para que arranquen en 100 en la fecha más antigua cargada. Permite comparar la evolución % de tickers cuyo precio nominal es muy diferente (ej. "AL30" vale ~100 y "APPLE" vale ~200, pero querés ver cuál se movió más en %).',
    whyItMatters: 'Sin normalizar, un ticker que sube de 10 a 12 (20% de ganancia) se vería "más chico" visualmente que uno que sube de 100 a 105 (5% de ganancia), porque el gráfico escala por valor absoluto, no por %. La base 100 arregla esto.',
    example: 'Si AL30 arranca en 100 (su precio real es 98) y GGAL arranca en 100 (su precio real es 3500), ambas líneas empiezan visualmente al mismo nivel y podés comparar cuál tuvo mejor evolución % sin distracciones.',
    limitations: 'La base 100 es solo visual. Los números en el eje Y no son precios reales, son índices. Si querés saber el precio actual, volvé a la vista sin normalizar.',
  },
  comparador_nominal: {
    title: 'Nominal',
    shortDescription: 'Precio del instrumento en su moneda original, sin conversión a dólares ni ajuste por inflación. Es el precio literal que cotiza en el mercado.',
    whyItMatters: 'La vista Nominal solo aparece si todos los tickers que elegiste están en la misma moneda. Si mezclas ARS y USD, no podés verlos juntos en Nominal porque no son comparables directamente. Por eso se reemplaza por vistas en dólares (MEP) o pesos reales (CER).',
    relatedTerms: ['cer', 'mep'],
  },
}
