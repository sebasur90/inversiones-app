import { HelpContent } from '../types'

export type AnalisisTecnicoHelpKey =
  | 'analisis_tecnico_titulo'
  | 'analisis_tecnico_indicadores'
  | 'analisis_tecnico_estrategias'
  | 'analisis_tecnico_backtest'
  | 'analisis_tecnico_precio_ejecucion'

export const ANALISISTECNICO_HELP: Record<AnalisisTecnicoHelpKey, HelpContent> = {
  analisis_tecnico_titulo: {
    title: 'Análisis técnico',
    shortDescription: 'Velas (donde la fuente las provee) o línea de cierres, con indicadores clásicos activables y estrategias propias backtesteables, sobre los tickers de tu cartera y tu watchlist.',
    whyItMatters: 'Te ayuda a decidir cuándo entrar o salir de un instrumento con reglas explícitas y verificables contra la historia, en vez de a ojo.',
  },
  analisis_tecnico_indicadores: {
    title: 'Indicadores',
    shortDescription: 'Medias móviles, RSI, MACD, Bandas de Bollinger, ATR, Estocástico, OBV y volumen promedio, calculados sobre la serie de precios de este ticker.',
    whyItMatters: 'Cada indicador resume un aspecto distinto del precio (tendencia, momentum, volatilidad, volumen); combinarlos da más contexto que mirar el precio solo.',
    limitations: 'Necesitan un warm-up (p. ej. una media de 200 ruedas recién está definida desde la rueda 200): la zona sombreada del gráfico marca dónde todavía no hay dato.',
  },
  analisis_tecnico_estrategias: {
    title: 'Estrategias',
    shortDescription: 'Reglas de compra y venta combinables (cruces de medias, niveles de RSI, bandas de Bollinger, etc.) que se pueden guardar, duplicar y reusar en cualquier ticker.',
    whyItMatters: 'Formalizar la regla te obliga a ser explícito sobre cuándo entrarías y saldrías, y permite contrastarla contra la historia antes de arriesgar capital real.',
  },
  analisis_tecnico_backtest: {
    title: 'Backtest',
    shortDescription: 'Corre la estrategia sobre la historia disponible del ticker: señal por señal, con stop loss/take profit/trailing si los configuraste, comisión por operación, y la compara contra comprar y mantener (buy & hold).',
    whyItMatters: 'Una estrategia que "se ve bien" en el gráfico puede perder contra simplemente comprar y mantener una vez que se cuenta la comisión y el drawdown real.',
    limitations: 'Es sobre historia pasada: no garantiza que la estrategia siga funcionando igual en el futuro. Con menos de 2 operaciones cerradas, las métricas de ratio (win rate, profit factor) no se calculan.',
  },
  analisis_tecnico_precio_ejecucion: {
    title: 'Precio de ejecución',
    shortDescription: '"Cierre": opera al cierre de la misma rueda que generó la señal (coincide con la flecha que ves en el gráfico). "Apertura siguiente": opera a la apertura de la rueda siguiente, sin el sesgo de saber el cierre antes de operar.',
    whyItMatters: 'Con "cierre" el backtest asume que pudiste operar exactamente al precio que generó la señal, algo que en la vida real no siempre es posible antes de que cierre la rueda.',
  },
}
