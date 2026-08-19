import { HelpContent } from '../types'

export type PerformanceRelativaHelpKey =
  | 'excesoRetorno'
  | 'performancerelativa_indice_normalizado'
  | 'performancerelativa_historial_comun'

export const PERFORMANCERELATIVA_HELP: Record<PerformanceRelativaHelpKey, HelpContent> = {
  excesoRetorno: {
    title: 'Exceso de retorno',
    shortDescription: 'La diferencia simple entre el rendimiento de tu cartera y el rendimiento del benchmark en el período seleccionado. No ajusta por riesgo (eso es el Alpha).',
    whyItMatters: 'Te dice de un vistazo si ganaste más o menos que el benchmark, sin distracciones. Si es positivo, tu selección fue mejor; si es negativo, el benchmark te hubiera ido mejor.',
    example: 'Si tu cartera rindió 15% en un año y el benchmark rindió 10%, tu exceso de retorno es 5 pp. Eso no significa que fuiste "más riesgoso" (eso mide el Alpha, ajustado por beta).',
    relatedTerms: ['alpha', 'beta'],
  },
  performancerelativa_indice_normalizado: {
    title: 'Índice normalizado',
    shortDescription: 'En el gráfico de Performance vs benchmark, ambas líneas parten de una base común normalizada (típicamente 100 en la fecha más antigua). Esto permite comparar visualmente el % de evolución sin que la diferencia de escala las distorsione.',
    whyItMatters: 'Si una línea cotiza en 1.000 y otra en 10, verías la primera gigante y la segunda microscópica, aunque ambas subieron 50%. La normalización arregla eso.',
  },
  performancerelativa_historial_comun: {
    title: 'Historial común',
    shortDescription: 'El período de tiempo en el que tanto tu cartera como el benchmark tienen datos disponibles. Las métricas de performance relativa (Alpha, Beta, Tracking error, etc.) requieren superposición de datos de ambos para ser confiables.',
    whyItMatters: 'Si tu cartera tiene 24 meses de historia pero el benchmark solo tiene 6, el Sharpe/Sortino/Calmar calculados con esos 6 meses puede no ser representativo de la estrategia real.',
  },
}
