import { HelpContent } from '../types'

export type RecordatoriosHelpKey = 'recordatorios_que_es'

export const RECORDATORIOS_HELP: Record<RecordatoriosHelpKey, HelpContent> = {
  recordatorios_que_es: {
    title: 'Recordatorios',
    shortDescription: 'Avisos que te dejás para una fecha, con una nota y los tickers que querés revisar. Llegan por Telegram y aparecen en "Para mirar hoy" del Resumen.',
    whyItMatters: 'Una fecha importante (una elección, un balance, una entrada que estás esperando) se olvida fácil. Dejarla anotada con el motivo te ahorra tener que acordarte y te recuerda por qué querías mirarla.',
    howToInterpret: 'Vencido quiere decir que ya llegó el momento: sigue en la lista hasta que lo marques como hecho o lo pospongas. Si el mensaje no pudo salir, se reintenta solo.',
    limitations: 'El aviso es uno solo, no se repite, y puede demorar hasta 5 minutos. Para que llegue al celular, el servidor tiene que tener activados el job programado y Telegram; si falta algo, la pantalla lo dice. Es un recordatorio tuyo, no una recomendación de compra o venta.',
  },
}
