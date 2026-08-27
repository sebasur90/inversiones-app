import { HelpContent } from '../types'

export type PatrimonioHelpKey =
  | 'patrimonio_descomposicion_aportes'
  | 'patrimonio_descomposicion_rendimiento'
  | 'patrimonio_descomposicion_otros_ajustes'
  | 'patrimonio_descomposicion_total'
  | 'patrimonio_valor_mercado'
  | 'patrimonio_capital_aportado'

export const PATRIMONIO_HELP: Record<PatrimonioHelpKey, HelpContent> = {
  patrimonio_descomposicion_aportes: {
    title: 'Aportes del período',
    shortDescription: 'El total neto que depositaste o retiraste de la cartera durante el período seleccionado (depósitos menos retiros), sin contar ganancias ni dividendos.',
    whyItMatters: 'Te permite separar cuánto de tu variación patrimonial vino de tu propio dinero versus cuánto vino de que tus inversiones rindieron.',
    relatedTerms: ['invertido'],
  },
  patrimonio_descomposicion_rendimiento: {
    title: 'Rendimiento del período',
    shortDescription: 'La parte de la variación de tu patrimonio explicada por el cambio de precio de tus activos durante el período, sin contar tus aportes/retiros ni los dividendos cobrados.',
    whyItMatters: 'Es el componente que mejor refleja qué tan bien te fue con tus inversiones en sí, independiente de cuánta plata pusiste o sacaste.',
    limitations: 'No es lo mismo que el XIRR o TWR: es una descomposición en pesos/dólares del cambio total, no una tasa de retorno anualizada.',
    relatedTerms: ['xirr', 'twr'],
  },
  patrimonio_descomposicion_otros_ajustes: {
    title: 'Otros ajustes del período',
    shortDescription: 'Las comisiones pagadas durante el período, siempre negativas: la parte de tus aportes que se fue en costos de transacción en vez de convertirse en tenencia o rendimiento.',
    whyItMatters: 'Sin este componente, el costo de las comisiones queda mezclado dentro de "Rendimiento", haciendo parecer que el mercado rindió peor de lo que realmente rindió.',
  },
  patrimonio_descomposicion_total: {
    title: 'Total del período',
    shortDescription: 'La suma de Aportes + Rendimiento + Dividendos + Otros ajustes: la variación total de tu patrimonio durante el período seleccionado.',
    whyItMatters: 'Coincide con la "Variación del período" que se muestra arriba del gráfico; acá se desglosa en sus componentes.',
  },
  patrimonio_valor_mercado: {
    title: 'Valor de mercado',
    shortDescription: 'El valor actual de tu cartera a precios de mercado: cuánto valdría si liquidaras todo hoy.',
  },
  patrimonio_capital_aportado: {
    title: 'Capital aportado',
    shortDescription: 'Línea de referencia que muestra cuánta plata pusiste (depósitos menos retiros) acumulada hasta cada fecha, sin contar ganancias ni pérdidas. La distancia entre esta línea y el valor de mercado es tu ganancia o pérdida no realizada.',
    relatedTerms: ['invertido', 'noRealizado'],
  },
}