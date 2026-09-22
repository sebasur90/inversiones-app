import { HelpContent } from '../types'

// Claves prefijadas "costooportunidad_" a propósito: ya existe "costoOportunidad" en
// glosario.ts y "valorShadow" en benchmarks.ts (el tab viejo de /benchmarks-comparacion),
// que hablan de un cálculo distinto y no se tocan.
export type CostoOportunidadHelpKey =
  | 'costooportunidad_comparacion'
  | 'costooportunidad_referencia'
  | 'costooportunidad_diferencia_pp'
  | 'costooportunidad_diferencia_monetaria'
  | 'costooportunidad_periodo_efectivo'
  | 'costooportunidad_homogeneidad'
  | 'costooportunidad_moneda'

export const COSTOOPORTUNIDAD_HELP: Record<CostoOportunidadHelpKey, HelpContent> = {
  costooportunidad_comparacion: {
    title: 'Costo de oportunidad',
    shortDescription: 'Compara cómo le fue a tu cartera contra una referencia elegida, durante el mismo período y con los mismos aportes y retiros.',
    whyItMatters: 'Sirve para entender el resultado en contexto: ¿el rendimiento fue bueno "en el vacío" o comparado con una alternativa simple?',
    howItIsCalculated: 'Se toman los mismos flujos de caja de la cartera (mismo capital inicial, mismos aportes y retiros, en las mismas fechas) y se calcula cuánto valdrían si se hubieran invertido en la referencia en vez de en la cartera real.',
    limitations: 'Es una comparación de lo que ya pasó, no una proyección ni una recomendación. La referencia se sigue de forma teórica, sin comisiones ni impuestos, y con reinversión instantánea. Cambiar el período, la moneda o la referencia cambia el resultado.',
    relatedTerms: ['costooportunidad_diferencia_monetaria', 'costooportunidad_homogeneidad'],
  },
  costooportunidad_referencia: {
    title: 'Referencia',
    shortDescription: 'El benchmark, índice o ticker contra el que se compara la cartera: puede ser el Dólar (MEP), la Inflación (CER), un ticker cargado en el Sheet, u otro benchmark propio.',
    whyItMatters: 'La elección de referencia cambia completamente la lectura: compararse contra el dólar no es lo mismo que compararse contra un índice accionario.',
    howToInterpret: 'Se puede cambiar libremente arriba de la pantalla; el resultado se recalcula al instante.',
  },
  costooportunidad_diferencia_pp: {
    title: 'Diferencia (cartera − referencia)',
    shortDescription: 'La resta entre el rendimiento porcentual de la cartera y el de la referencia, en puntos porcentuales.',
    howItIsCalculated: 'resultado_cartera_pct − resultado_referencia_pct, expresado en pp.',
    howToInterpret: 'Positivo: la cartera rindió más que la referencia en el período. Negativo: rindió menos.',
  },
  costooportunidad_diferencia_monetaria: {
    title: 'Diferencia en dinero',
    shortDescription: 'Cuánto más (o menos) vale la cartera hoy, comparada con lo que valdría si el mismo capital y los mismos aportes hubieran seguido a la referencia.',
    howItIsCalculated: 'Valor final de la cartera menos el valor que tendrían los mismos flujos de caja si hubieran crecido al ritmo de la referencia.',
    limitations: 'No es una ganancia ni una pérdida "real" adicional: es una comparación contra un escenario hipotético, no contra dinero que efectivamente se dejó de ganar.',
  },
  costooportunidad_periodo_efectivo: {
    title: 'Período efectivamente comparado',
    shortDescription: 'El tramo de tiempo que realmente se pudo comparar, recortado a meses calendario completos.',
    howItIsCalculated: 'Arranca en el cierre del mes anterior al primer mes en el que hay datos de la cartera y de la referencia a la vez, y termina hoy o al final del período pedido.',
    limitations: 'Puede ser más corto que el período pedido si a la cartera o a la referencia les falta historia más atrás. Cuando eso pasa, la pantalla lo advierte.',
  },
  costooportunidad_homogeneidad: {
    title: 'Homogeneidad de la comparación',
    shortDescription: 'Lista de advertencias sobre por qué esta comparación puede no ser del todo pareja: moneda convertida, período recortado, datos de la referencia poco frecuentes, valuaciones aproximadas, entre otras.',
    whyItMatters: 'Comparar dos series no siempre es comparar manzanas con manzanas. Estas advertencias señalan explícitamente dónde puede haber ruido en el resultado.',
    howToInterpret: 'No invalidan el resultado, pero conviene tenerlas en cuenta antes de sacar conclusiones fuertes.',
  },
  costooportunidad_moneda: {
    title: 'Moneda de la comparación',
    shortDescription: 'USD, ARS o ARS real (ajustado por CER): la moneda en la que se expresan tanto la cartera como la referencia.',
    whyItMatters: 'La referencia se convierte a esta moneda antes de comparar, para que "seguir al dólar" valuado en dólares dé 0% (no rendimiento) en vez de reflejar la suba del dólar en pesos.',
    howItIsCalculated: 'La serie nativa de la referencia se convierte punto a punto usando el dólar MEP y, para ARS real, también el CER.',
  },
}
