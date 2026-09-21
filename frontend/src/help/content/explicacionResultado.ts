import { HelpContent } from '../types'

export type ExplicacionResultadoHelpKey =
  | 'explicacion_que_es'
  | 'explicacion_precio'
  | 'explicacion_dividendos_cupones'
  | 'explicacion_comisiones'
  | 'explicacion_efecto_mep'
  | 'explicacion_no_disponible'
  | 'explicacion_amortizaciones'

export const EXPLICACIONRESULTADO_HELP: Record<ExplicacionResultadoHelpKey, HelpContent> = {
  explicacion_que_es: {
    title: '¿Por qué ganó o perdió mi cartera?',
    shortDescription: 'Descompone el resultado de un período en las causas que lo explican, en vez de mostrar sólo el porcentaje final.',
    whyItMatters: 'Un número de rendimiento solo no dice si la cartera ganó por suerte de mercado, por dividendos, o si simplemente aportaste capital nuevo (que no es ganancia). Esta pantalla separa cada causa.',
    howItIsCalculated: 'Reutiliza los mismos cálculos que Rendimiento, P&L y Contribución (TWR, XIRR, P&L realizado/no realizado): no se inventa ninguna fórmula financiera nueva.',
    limitations: 'Cuando falta un precio o un tipo de cambio para algún instrumento, ese componente se muestra como "No disponible" en vez de estimarse.',
  },
  explicacion_precio: {
    title: 'Movimiento de precio',
    shortDescription: 'Cuánto del resultado vino de que los activos subieron o bajaron de precio.',
    howItIsCalculated: 'Es un residuo exacto: (valor final − valor inicial) − compras + ventas + amortizaciones, todo a precio de mercado. También incluye el resultado de vender o amortizar por encima o por debajo del precio de compra.',
  },
  explicacion_dividendos_cupones: {
    title: 'Dividendos y cupones',
    shortDescription: 'Efectivo cobrado por tenencias, sin vender nada.',
    howItIsCalculated: 'Suma de los movimientos de tipo "dividendo" y "cupón" del período, en la moneda elegida.',
  },
  explicacion_comisiones: {
    title: 'Comisiones',
    shortDescription: 'Lo que se pagó en comisiones de compra, venta y otras operaciones durante el período.',
    howItIsCalculated: 'Siempre resta al resultado: es el único componente que sólo puede achicar la ganancia.',
  },
  explicacion_efecto_mep: {
    title: 'Efecto moneda / MEP',
    shortDescription: 'En la vista ARS, separa cuánto del resultado en pesos vino de los activos en sí y cuánto del movimiento del dólar MEP.',
    howItIsCalculated: 'Resultado de los activos = P&L en dólares × MEP de hoy. Efecto MEP = P&L en pesos − ese número. Es una identidad exacta, no una estimación.',
    limitations: 'No aplica en la vista USD: ahí el tipo de cambio ya está incorporado en el precio en dólares de cada activo.',
  },
  explicacion_no_disponible: {
    title: '"No disponible"',
    shortDescription: 'Un instrumento sin cotización o sin tipo de cambio para el período pedido.',
    whyItMatters: 'Es preferible mostrar "No disponible" a inventar un número que parezca exacto y no lo sea. El resto de los instrumentos sí calculados no se ven afectados.',
  },
  explicacion_amortizaciones: {
    title: 'Amortizaciones',
    shortDescription: 'Devolución de capital de un bono (parcial o total), no una ganancia.',
    whyItMatters: 'Se muestra por separado de aportes/retiros y no genera una "ganancia" propia: calcularla exigiría el precio de mercado exacto del día, que no siempre es preciso. Su resultado frente al mercado queda dentro de "Movimiento de precio".',
  },
}
