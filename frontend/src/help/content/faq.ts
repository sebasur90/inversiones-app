import type { HelpKey } from './index'

export interface FaqItem {
  pregunta: string
  respuesta: string
  termino?: HelpKey
}

/** Preguntas frecuentes del Centro de ayuda. Dudas recurrentes de alguien nuevo en la app, no
 *  documentación técnica — para eso está `DESARROLLO.md` en el repo. */
export const FAQ: FaqItem[] = [
  {
    pregunta: '¿Por qué el número no coincide exactamente con lo que veo en mi broker?',
    respuesta:
      'Puede haber varios motivos: el precio que usa la app es el del último cierre cargado (no en vivo), la conversión a USD usa el dólar MEP del día y tu broker puede usar otro tipo de cambio, o hay una comisión o un ajuste que se registró distinto. Si la diferencia es grande y persistente, revisá el precio de ese ticker en la pestaña Precios del Sheet.',
    termino: 'mep',
  },
  {
    pregunta: '¿Por qué a un ticker le falta historial de precios?',
    respuesta:
      'El historial disponible depende de desde cuándo hay precios cargados para ese instrumento, ya sea automáticamente (cuando hay una fuente externa disponible) o a mano en el Sheet. Un ticker recién agregado va a tener poco historial hasta que pase tiempo o se complete hacia atrás.',
  },
  {
    pregunta: '¿Qué hace exactamente "Sincronizar"?',
    respuesta:
      'Vuelve a leer tu Google Sheet completo (movimientos, instrumentos, precios, objetivos, watchlist, rebalanceo) y recalcula todo en la app con esos datos. Es de solo lectura: nunca escribe nada de vuelta en el Sheet.',
  },
  {
    pregunta: 'Sincronicé y aparecieron errores o advertencias, ¿qué hago?',
    respuesta:
      'Un error crítico suele significar que falta un dato obligatorio o el formato de una fila no es el esperado, y esa fila no se pudo procesar. Una advertencia es algo que se pudo resolver igual, pero conviene revisar. En ambos casos, el detalle dice la pestaña y la fila exactas: corregilo en el Sheet y sincronizá de nuevo.',
    termino: 'calidaddatos_issues',
  },
  {
    pregunta: '¿En qué se diferencia ver los montos en USD o en ARS?',
    respuesta:
      'Es sólo la moneda en la que se muestran los importes, no cambia tus datos ni tus cálculos de fondo. La conversión usa el dólar MEP del día para cada fecha. Para instrumentos en pesos, "ARS Real (CER)" además ajusta por inflación, para comparar el poder adquisitivo en el tiempo, no sólo la cantidad de pesos.',
    termino: 'cer',
  },
  {
    pregunta: '¿Por qué una métrica dice "Datos insuficientes"?',
    respuesta:
      'Varias métricas (volatilidad, Sharpe, Sortino, drawdown, entre otras) necesitan un mínimo de meses de historial mensual para calcularse de forma confiable. Con una cartera nueva o un ticker recién agregado, es esperable verlo hasta que se acumule más historia.',
  },
  {
    pregunta: '¿La app puede comprar o vender algo por mí?',
    respuesta:
      'No. La app es de solo lectura: lee tu Google Sheet, calcula métricas y te las muestra. Cualquier operación (comprar, vender, rebalancear) la hacés vos en tu broker, y después la cargás como movimiento en el Sheet.',
  },
]
