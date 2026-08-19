import { HelpContent } from '../types'

export type VencimientosHelpKey =
  | 'vencimientos_titulo'
  | 'vencimientos_dias_restantes'
  | 'vencimientos_fecha_vencimiento'
  | 'vencimientos_vencido'
  | 'vencimientos_valor_actual'

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
}
