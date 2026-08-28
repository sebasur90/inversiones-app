import { HelpContent } from '../types'

export type FlujoCajaHelpKey =
  | 'flujocaja_titulo'
  | 'flujocaja_inferido'
  | 'flujocaja_confianza'
  | 'flujocaja_capital'
  | 'flujocaja_horizonte'

export const FLUJOCAJA_HELP: Record<FlujoCajaHelpKey, HelpContent> = {
  flujocaja_titulo: {
    title: 'Flujo de caja proyectado',
    shortDescription:
      'Estimación de cuánto vas a cobrar mes a mes por tus bonos, ON y letras en los próximos 12-24 meses: cupones de renta más las amortizaciones de capital, apilados por instrumento.',
    whyItMatters:
      'Saber cuándo y cuánto entra te permite planificar reinversiones, cubrir gastos con esos cobros o detectar meses flojos antes de que lleguen. Es la contracara del calendario de vencimientos: no cuándo termina el bono, sino cuánto va rindiendo en el camino.',
    howItIsCalculated:
      'No hay una API pública de cronogramas de bonos argentinos, así que todo se infiere de tu propio historial: la periodicidad sale del tiempo mediano entre los cupones que ya cobraste de cada ticker, y el monto por unidad sale de la mediana de "importe del cupón ÷ tenencia" de esos mismos cobros. Esa serie se proyecta hacia adelante, anclada a la fecha de vencimiento, valuando con tu tenencia actual.',
    limitations:
      'Es una estimación, no el cronograma oficial. Si un bono todavía no pagó ningún cupón, no hay de qué inferir y queda fuera de la proyección. Los cupones de bonos que amortizan no ajustan por la caída de capital residual, y el tipo de cambio se supone constante (MEP más reciente).',
    relatedTerms: ['ingresos'],
  },
  flujocaja_inferido: {
    title: 'Dato inferido',
    shortDescription:
      'Todos los cobros futuros de esta pantalla se calculan a partir del patrón de tus cobros pasados, no de un cronograma cargado. Un cambio de régimen del bono (canje, reperfilamiento) no se refleja hasta que aparezca en tus movimientos.',
    whyItMatters:
      'Sirve para planificar con un orden de magnitud, no para conciliar al peso. Cuando cobres el próximo cupón real, la proyección se recalibra sola.',
  },
  flujocaja_confianza: {
    title: 'Confianza de la periodicidad',
    shortDescription:
      'Alta: 3 o más cupones cobrados con intervalos parejos. Media: hay historial pero los intervalos varían. Baja: un solo cupón cobrado, se asume periodicidad semestral (lo más habitual en bonos argentinos).',
    whyItMatters:
      'Con confianza baja o media, tomá el calendario como referencia gruesa: la fecha exacta y hasta la cantidad de cobros pueden moverse cuando haya más historial.',
  },
  flujocaja_capital: {
    title: 'Capital al vencimiento',
    shortDescription:
      'Si el bono ya mostró amortizaciones parciales en tu historial, se proyecta esa serie. Si no, se asume que devuelve todo el capital de una sola vez al vencimiento (bullet) y se estima ese monto con el precio de mercado actual del bono.',
    whyItMatters:
      'La amortización suele ser el cobro más grande del calendario. Estimarla con el precio actual es conservador para bonos que cotizan bajo la par y generoso para los que cotizan sobre la par: ajustá el número con criterio.',
  },
  flujocaja_horizonte: {
    title: 'Horizonte',
    shortDescription:
      'Cantidad de meses hacia adelante que cubre la proyección (por defecto 24). Los bonos que vencen más allá igual muestran sus cupones dentro de la ventana.',
    whyItMatters:
      'Un horizonte corto se enfoca en la liquidez inmediata; uno largo deja ver el peso de las amortizaciones que todavía faltan.',
  },
}
