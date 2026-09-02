import { HelpContent } from '../types'

export type PosicionesHelpKey =
  | 'posiciones_tipo_instrumento'
  | 'posiciones_mercado'
  | 'posiciones_cantidad_actual'
  | 'posiciones_precio_promedio'
  | 'posiciones_rendimiento_simple'
  | 'posiciones_alerta_precio'
  | 'posiciones_filtro_alerta'

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
  posiciones_alerta_precio: {
    title: 'Alertas de precio',
    shortDescription: 'El cartelito de color al lado del nombre avisa que la posición cruzó —o está por cruzar— uno de sus dos niveles de precio: el stop-loss (el piso donde cortás la pérdida) o el objetivo (el techo donde tomás ganancias).',
    whyItMatters: 'Los dos niveles los definís cuando comprás, en frío. La alerta existe para que la decisión no dependa de que justo ese día se te ocurra mirar el precio de ese ticker.',
    howItIsCalculated: 'Los niveles salen de las columnas Objetivo y Stop Loss de la pestaña Instrumentos del Sheet, en modo Fijo (un precio) o Porcentaje (sobre tu precio promedio de compra). La app compara ese nivel contra el último precio conocido.',
    howToInterpret: '🛑 STOP (rojo): el precio ya cayó al stop-loss. 🎯 META (verde): ya alcanzó el objetivo. ⚠ STOP / ⚠ META (amarillo): todavía no lo cruzó, pero está dentro del margen de aviso que configuraste en Ajustes → Alertas de precio. Sin cartelito, o no hay niveles cargados para ese ticker, o el precio está lejos de ellos.',
    limitations: 'La alerta usa el último precio registrado, no una cotización en vivo: si hace días que no sincronizás, puede llegar tarde. Un ticker sin niveles en el Sheet nunca va a avisar. Y es sólo una señal, no una orden: no ejecuta ninguna venta.',
    relatedTerms: ['objetivo', 'stopLoss'],
  },
  posiciones_filtro_alerta: {
    title: 'Filtro por alerta',
    shortDescription: 'Acota la lista a las posiciones que cruzaron o están por cruzar alguno de sus niveles de precio. El número al lado de cada solapa es cuántas caen ahí.',
    whyItMatters: 'Con muchas posiciones, ir buscando los cartelitos a ojo entre toda la lista es justo lo que hace que se te pase alguno.',
    howToInterpret: '"Con alerta" junta todo; "Stop loss" y "Objetivo" separan por tipo de nivel. Se combina con el buscador: podés filtrar por alerta y además escribir un ticker. Si una posición cruzó los dos niveles, cuenta como stop-loss, que es lo urgente.',
    relatedTerms: ['objetivo', 'stopLoss'],
  },
}
