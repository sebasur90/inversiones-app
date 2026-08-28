import { HelpContent } from '../types'

export type VencimientosHelpKey =
  | 'vencimientos_titulo'
  | 'vencimientos_dias_restantes'
  | 'vencimientos_fecha_vencimiento'
  | 'vencimientos_vencido'
  | 'vencimientos_valor_actual'
  | 'vencimientos_inferido'
  | 'vencimientos_paridad'
  | 'vencimientos_tir'
  | 'vencimientos_duration'
  | 'vencimientos_por_anio'

export const VENCIMIENTOS_HELP: Record<VencimientosHelpKey, HelpContent> = {
  vencimientos_titulo: {
    title: 'Calendario de vencimientos',
    shortDescription: 'Listado de todos tus bonos, instrumentos y otros activos que tienen una fecha de vencimiento. Útil para planificar reinversiones y gestionar flujos de caja.',
    whyItMatters: 'Conocer cuándo vencen tus instrumentos te permite reinvertir a tiempo, evitar caer en efectivo ocioso y tomar decisiones de rebalanceo proactivas en lugar de reactivas.',
    relatedTerms: ['amortizacion'],
  },
  vencimientos_dias_restantes: {
    title: 'Días restantes',
    shortDescription: 'Tiempo que falta hasta el vencimiento del instrumento. Se codifica por color: rojo si vencido o <30 días, amarillo si 30-180 días, gris si >180 días.',
    whyItMatters: 'Te permite priorizar qué vencimientos atender primero. Los más cercanos (rojo) requieren decisión inmediata: ¿reinvertir, cambiar de activo o dejar el efectivo?',
  },
  vencimientos_fecha_vencimiento: {
    title: 'Fecha de vencimiento',
    shortDescription: 'La fecha exacta en que el emisor devuelve el capital (o paga la última cuota) del bono o instrumento. Después de esa fecha, la posición ya no devenga intereses.',
    whyItMatters: 'Es la fecha clave para saber cuándo recuperarás el capital. Antes de esa fecha es cuando decides si reinvertir en el mismo activo, cambiar a otro o simplemente retirar los fondos.',
  },
  vencimientos_vencido: {
    title: 'Vencido',
    shortDescription: 'Estado que indica que la fecha de vencimiento ya pasó. Significa que el emisor ya devolvió (o debería haber devuelto) el capital.',
    whyItMatters: 'Si una posición aparece como "Vencida", revisa si el dinero ya llegó a tu cuenta. Si no, podría indicar un atraso o problema con el emisor que requiere seguimiento.',
  },
  vencimientos_valor_actual: {
    title: 'Valor actual',
    shortDescription: 'El valor de mercado actual del instrumento, mostrado en la moneda seleccionada (USD o ARS). Es lo que obtendrías si vendieras ahora, o lo que recuperarás al vencimiento (si todo va según lo planeado).',
    whyItMatters: 'Te permite evaluar si el precio actual del bono cambió (por suba/baja de tasas o cambios de riesgo del emisor) desde que lo compraste. Importante para decidir si mantener hasta vencimiento o vender antes.',
  },
  vencimientos_inferido: {
    title: 'Métricas estimadas',
    shortDescription:
      'La paridad, la TIR al vencimiento y la duration se calculan sobre un cronograma de cupones y amortizaciones inferido de tu propio historial de cobros, no de un cronograma oficial. Es el mismo motor que la pantalla Flujo de caja proyectado.',
    whyItMatters:
      'Sirven para comparar bonos entre sí y ver un orden de magnitud, no para operar al punto básico. Cuando cobres el próximo cupón real, la estimación se recalibra sola. Los bonos sin cupones cobrados todavía no muestran estas métricas.',
  },
  vencimientos_paridad: {
    title: 'Paridad',
    shortDescription:
      'Precio de mercado dividido el valor técnico (valor residual del capital + intereses corridos), ambos por unidad. Arriba de 1 (100%) el bono cotiza sobre la par; abajo de 1, bajo la par.',
    whyItMatters:
      'Es la forma estándar de comparar bonos con distinto cupón y amortización. Una paridad baja puede indicar castigo por riesgo o tasas altas; una alta, que ya descontó buena parte del recorrido. Acá el valor residual se estima (par = 1, ajustado por las cuotas de amortización ya inferidas), así que tomala como referencia.',
  },
  vencimientos_tir: {
    title: 'TIR al vencimiento',
    shortDescription:
      'Tasa interna de retorno anualizada si comprás hoy al precio de mercado y mantenés hasta el vencimiento, cobrando todos los cupones y amortizaciones proyectados. Se calcula con el mismo método que la TIR de la cartera.',
    whyItMatters:
      'Es el rendimiento comparable entre bonos. Ojo: para los bonos bullet el capital al vencimiento se estima con el precio de mercado actual, así que la TIR tiende a parecerse a la TIR corriente (cupón ÷ precio) y no captura la ganancia o pérdida de capital contra la par.',
  },
  vencimientos_duration: {
    title: 'Duration modificada',
    shortDescription:
      'Sensibilidad aproximada del precio del bono a un cambio de 1 punto porcentual en su tasa: una duration modificada de 2 significa que el precio cae ~2% si la tasa sube 1 pp. Se deriva de la duration de Macaulay (plazo promedio ponderado de los cobros) dividida por (1 + TIR).',
    whyItMatters:
      'Mide el riesgo de tasa. Más duration = más volatilidad ante movimientos de tasas. Útil para dimensionar cuánto pega una suba de tasas en la parte de renta fija de la cartera.',
  },
  vencimientos_por_anio: {
    title: '% de la cartera que vence por año',
    shortDescription:
      'Agrupa el valor de mercado de los instrumentos con vencimiento por año calendario y lo divide por el valor total de la cartera. Muestra qué porción del patrimonio vuelve a efectivo cada año.',
    whyItMatters:
      'Concentrar muchos vencimientos en un mismo año expone a reinvertir todo junto a la tasa que haya en ese momento (riesgo de reinversión). Escalonar los vencimientos suaviza ese riesgo.',
  },
}
