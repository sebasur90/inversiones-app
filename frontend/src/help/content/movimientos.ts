import { HelpContent } from '../types'

export type MovimientosHelpKey =
  | 'movimientos_dividendo'
  | 'movimientos_cupon'
  | 'movimientos_amortizacion'
  | 'movimientos_comision'

export const MOVIMIENTOS_HELP: Record<MovimientosHelpKey, HelpContent> = {
  movimientos_dividendo: {
    title: 'Dividendo',
    shortDescription: 'Ingresos que pagó una empresa a sus accionistas por tenencia de acciones. Se refleja como movimiento de entrada de efectivo sin vender la posición.',
    whyItMatters: 'Los dividendos son parte de tu rendimiento total; suman a la ganancia acumulada aunque no hayas vendido el activo.',
    relatedTerms: ['ingresos'],
  },
  movimientos_cupon: {
    title: 'Cupón',
    shortDescription: 'Pago periódico de intereses que genera un bono. Se refleja como movimiento de entrada de efectivo sin vender el bono.',
    whyItMatters: 'Los cupones son los intereses que te paga el emisor del bono; junto con la amortización y el cambio de precio, constituyen tu rendimiento total en bonos.',
    relatedTerms: ['ingresos'],
  },
  movimientos_amortizacion: {
    title: 'Amortización',
    shortDescription: 'Devolución parcial o total del capital de un bono que realiza el emisor antes de su vencimiento. Se refleja como movimiento de entrada de efectivo.',
    whyItMatters: 'La amortización acorta tu exposición al bono y devuelve plata; si coincide con una caída de precios, protege parte de tu inversión.',
  },
  movimientos_comision: {
    title: 'Comisión',
    shortDescription: 'Costo cobrado por el broker o plataforma por cada operación (compra, venta, movimiento de fondos). Se descuenta del efectivo disponible o del rendimiento de la operación.',
    whyItMatters: 'Las comisiones erosionan el rendimiento total; optimizarlas (usando brokers con comisiones bajas o consolidando operaciones) mejora significativamente tu resultado final.',
    relatedTerms: ['invertido', 'realizado'],
  },
}
