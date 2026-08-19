import { HelpContent } from '../types'

export type BenchmarksHelpKey =
  | 'benchmarks_periodo'
  | 'benchmarks_moneda'
  | 'benchmarks_seleccion'
  | 'valorShadow'

export const BENCHMARKS_HELP: Record<BenchmarksHelpKey, HelpContent> = {
  benchmarks_periodo: {
    title: 'Período',
    shortDescription: 'El rango de tiempo sobre el cual comparar tu cartera vs. benchmarks.',
    whyItMatters: 'Períodos distintos pueden dar resultados muy diferentes. El desempeño relativo varía con el tiempo.',
    example: '"1Y" compara los últimos 12 meses. "ALL" compara desde el inicio del historial.',
  },
  benchmarks_moneda: {
    title: 'Moneda',
    shortDescription: 'En qué moneda visualizar los retornos: ARS nominal, ARS real (descontando inflación vía CER), o USD.',
    whyItMatters: 'El retorno en ARS es distinto del retorno en USD por efecto del tipo de cambio. El retorno real te muestra si ganaste poder de compra de verdad.',
    example: 'Si tu cartera rindió 15% en ARS nominal pero la inflación fue 10%, tu retorno real es ~4.5%.',
    relatedTerms: ['cer', 'mep'],
  },
  benchmarks_seleccion: {
    title: 'Seleccionar benchmarks',
    shortDescription: 'Elige cuáles índices/benchmarks deseas comparar contra tu cartera. Puedes seleccionar múltiples.',
    whyItMatters: 'Distintos benchmarks te permiten evaluar si estás siendo más inteligente que diferentes alternativas de inversión.',
    example: 'Selecciona "Dólar" para comparar vs. dolarizar tu cartera, o "Merval" para comparar vs. el índice local.',
  },
  valorShadow: {
    title: 'Valor shadow (valor sombra)',
    shortDescription: 'Cuánto valdría hoy tu cartera si hubieras invertido exactamente en el benchmark elegido en vez de en tus activos reales, con los mismos aportes y retiros.',
    whyItMatters: 'Te permite aislar el efecto de tus decisiones de selección: la diferencia entre tu valor real y el shadow value es lo que tu talento (o falta de él) agregó o restó.',
    example: 'Si tu cartera real vale USD 100.000 pero el valor shadow (si hubieras seguido el benchmark) es USD 95.000, ganaste USD 5.000 por mejor selección que el benchmark.',
    limitations: 'Solo es relevante si comparas con un período en el que el benchmark tuvo datos.',
  },
}
