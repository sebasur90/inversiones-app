import { HelpContent } from '../types'

export type PosicionesHelpKey =
  | 'posiciones_tipo_instrumento'
  | 'posiciones_mercado'
  | 'posiciones_cantidad_actual'
  | 'posiciones_precio_promedio'
  | 'posiciones_rendimiento_simple'

export const POSICIONES_HELP: Record<PosicionesHelpKey, HelpContent> = {
  posiciones_tipo_instrumento: {
    title: 'Tipo de instrumento',
    shortDescription: 'Clasificación del activo que tenés: Acción (equity en una empresa), CEDEAR (certificado que replica una acción extranjera), Bono (deuda que paga cupones), Fondo (cesta diversificada), etc.',
    whyItMatters: 'Saber el tipo te ayuda a entender el riesgo, comportamiento y potencial de cada posición, y a planificar la diversificación correctamente.',
  },
  posiciones_mercado: {
    title: 'Mercado',
    shortDescription: 'Dónde se cotiza el activo: MERVAL (Bolsa de Buenos Aires), NYSE (Bolsa de Nueva York), NASDAQ, etc. Define el horario de operación, liquidación y costos de transacción.',
    whyItMatters: 'El mercado influye en la liquidez (qué tan fácil es comprar/vender), horarios de operación y spreads (diferencia bid-ask). Activos en mercados más grandes suelen ser más líquidos.',
    relatedTerms: ['mep', 'benchmark'],
  },
  posiciones_cantidad_actual: {
    title: 'Cantidad actual',
    shortDescription: 'Número de unidades del activo que tenés en cartera ahora: acciones, bonos, CEDEARs, etc.',
    whyItMatters: 'La cantidad determina tu exposición: si el precio sube o baja, tu P&L depende de cuántas unidades tengas.',
  },
  posiciones_precio_promedio: {
    title: 'Precio promedio de compra',
    shortDescription: 'Promedio ponderado del precio que pagaste por cada unidad al comprar. Si compraste 10 a $100 y luego 20 a $120, tu precio promedio es $113.33.',
    whyItMatters: 'Es tu "punto de equilibrio": si el precio actual está por encima, tenés ganancia; si está por debajo, tenés pérdida. Serve para evaluar si es buen momento de vender.',
  },
  posiciones_rendimiento_simple: {
    title: 'Rendimiento simple',
    shortDescription: 'La cuenta más básica: (Valor actual − Invertido) ÷ Invertido. Muestra la ganancia o pérdida porcentual desde que compraste, sin ajustes por tiempo.',
    whyItMatters: 'Es la forma más intuitiva de ver si ganaste o perdiste en cada posición individual. No es comparable entre períodos de diferente duración, pero da una idea rápida.',
    relatedTerms: ['invertido', 'realizado', 'noRealizado'],
  },
}
