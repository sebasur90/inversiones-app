import { HelpContent } from '../types'

export type AnalisisTecnicoHelpKey =
  | 'analisis_tecnico_titulo'
  | 'analisis_tecnico_indicadores'
  | 'analisis_tecnico_estrategias'
  | 'analisis_tecnico_backtest'
  | 'analisis_tecnico_precio_ejecucion'
  | 'analisis_tecnico_extremos'
  | 'analisis_tecnico_percentil'
  | 'screener_distancia'
  | 'screener_precio_gatillo'
  | 'screener_umbral'

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
  analisis_tecnico_extremos: {
    title: 'Extremos (canal)',
    shortDescription: 'Máximo, mínimo y medio de la ventana (canal de Donchian, incluye la barra actual), más la distancia porcentual del cierre a cada extremo: dist_max_pct (≤ 0, es 0 en un máximo nuevo) y dist_min_pct (≥ 0, es 0 en un mínimo nuevo).',
    howItIsCalculated: 'dist_max_pct = (cierre / máximo − 1) × 100; dist_min_pct = (cierre / mínimo − 1) × 100. Con ventana = 0 la ventana es "toda la serie" (histórico acumulado); con ventana = N son las últimas N ruedas.',
    howToInterpret: '"Comprar cerca del mínimo histórico" se escribe dist_min_pct ≤ 1 (a ≤ 1 % del mínimo). dist_max_pct con ventana = 0 es exactamente el drawdown desde el máximo histórico; con ventana = 252, el drawdown de 52 semanas (no hace falta un indicador aparte).',
    limitations: 'Con ventana = 0, "histórico" es desde el inicio de la serie cargada, no desde el debut del instrumento. La primera barra de la serie es su propio máximo y mínimo, así que dist_min_pct y dist_max_pct valen 0 ahí: usá un período de análisis razonable. Muchas series de esta app no tienen velas OHLC — en ese caso el canal usa el cierre.',
  },
  analisis_tecnico_percentil: {
    title: 'Percentil',
    shortDescription: 'Ranking del cierre actual dentro de la ventana: 0 cuando es el mínimo de la ventana, 100 cuando es el máximo. Con ventana = 0 el ranking es contra toda la historia cargada.',
    howItIsCalculated: '100 × (cantidad de cierres de la ventana estrictamente menores al actual) / (tamaño de la ventana − 1). Es un rank real, no un min-max: resiste outliers y da 0 y 100 exactos en los extremos.',
    howToInterpret: 'Valores bajos (< 10) marcan que el precio está en la zona más baja de su rango histórico; valores altos (> 90), en la más alta. Las líneas de referencia del panel están en 10 y 90.',
    limitations: 'Igual que Extremos: con ventana = 0, "histórico" es desde el inicio de la serie cargada. Necesita la ventana completa antes de dar el primer valor.',
  },
  screener_distancia: {
    title: 'Distancia al disparo',
    shortDescription: 'Cuánto tiene que moverse el precio (en %, con signo: negativo = tiene que bajar) para que la estrategia dispare compra o venta. Se busca el movimiento mínimo que hace cumplir la regla, no una proyección de hacia dónde va el precio.',
    whyItMatters: 'Ordena el universo por qué tan cerca está cada estrategia de activarse, sin tener que abrir el gráfico de cada ticker uno por uno.',
    limitations: 'Es una medida de distancia, no una predicción: que el precio esté a 1% de disparar no dice nada sobre si va a moverse en esa dirección.',
    relatedTerms: ['analisis_tecnico_estrategias', 'screener_precio_gatillo'],
  },
  screener_precio_gatillo: {
    title: 'Precio gatillo',
    shortDescription: 'El precio al que, de llegar el ticker, la estrategia dispararía hoy: `precio actual × (1 + distancia / 100)`.',
    whyItMatters: 'Es el número concreto para poner una alerta de precio o comparar contra el book, en vez de tener que calcular el porcentaje a mano.',
    relatedTerms: ['screener_distancia'],
  },
  screener_umbral: {
    title: 'Umbral de proximidad',
    shortDescription: 'El screener sólo muestra los pares (ticker, estrategia) cuya distancia al disparo es menor o igual a este porcentaje.',
    whyItMatters: 'Un umbral más angosto (1-2%) muestra sólo lo más inminente; uno más amplio (10%) da una vista más temprana, con más ruido.',
  },
}
