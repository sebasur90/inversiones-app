import { HelpContent } from '../types'

export type ComisionesHelpKey =
  | 'comisiones_total_pagado'
  | 'comisiones_movimientos'
  | 'comisiones_periodo_moneda'

export const COMISIONES_HELP: Record<ComisionesHelpKey, HelpContent> = {
  comisiones_total_pagado: {
    title: 'Total pagado',
    shortDescription: 'Suma de todas las comisiones pagadas en las operaciones de compra y venta registradas en esta cartera.',
    limitations: 'El modelo actual solo cuenta comisión por operación (compra/venta), no incluye custodia de títulos ni comisiones de mantenimiento u otros cargos periódicos que tu broker podría cobrar fuera de las operaciones.',
  },
  comisiones_movimientos: {
    title: 'Movimientos con comisión',
    shortDescription: 'Cantidad de operaciones de compra o venta que tuvieron comisión asociada. No incluye movimientos sin comisión (ej. transferencias, reinversiones de dividendos que no generen costo).',
  },
  comisiones_periodo_moneda: {
    title: 'Desglose Mensual/Anual (moneda)',
    shortDescription: 'Los desgloses por periodo (Mensual, Anual) siempre se muestran en USD, sin importar el selector global de moneda. Los desgloses por Cartera y Ticker sí respetan tu selector ARS/USD.',
    limitations: 'Esta es una limitación actual de la interfaz. Si necesitas verlas en ARS, selecciona globalmente ARS y luego vuelve a Cartera/Ticker (Mensual/Anual seguirá en USD).',
  },
}
