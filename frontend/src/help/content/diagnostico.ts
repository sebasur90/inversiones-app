import { HelpContent } from '../types'

export type DiagnosticoHelpKey =
  | 'diagnostico_salud_cartera'
  | 'diagnostico_dimension_rendimiento'
  | 'diagnostico_dimension_diversificacion'
  | 'diagnostico_dimension_riesgo'
  | 'diagnostico_dimension_costos'
  | 'diagnostico_hallazgos'
  | 'diagnostico_datos_insuficientes_performance'
  | 'diagnostico_datos_insuficientes_objetivo'

export const DIAGNOSTICO_HELP: Record<DiagnosticoHelpKey, HelpContent> = {
  diagnostico_salud_cartera: {
    title: 'Salud de cartera',
    shortDescription: 'Puntuación de 0–100 que resume la calidad integral de tu cartera considerando rendimiento, diversificación, riesgo y costos.',
    whyItMatters: 'Una cartera saludable (≥70) tiene buenos rendimientos ajustados por riesgo, está bien diversificada y tiene costos bajo control. Puntuaciones menores indican áreas a mejorar.',
    limitations: 'La puntuación es una simplificación; revisar cada dimensión por separado te da más detalle.',
    relatedTerms: ['riesgo', 'diversificacion'],
  },
  diagnostico_dimension_rendimiento: {
    title: 'Dimensión: Rendimiento',
    shortDescription: 'Evalúa cómo se desempeña tu cartera en relación con benchmarks y objetivos de inversión.',
    whyItMatters: 'Rendimientos consistentes y por encima de los benchmarks indicadores una estrategia efectiva.',
    relatedTerms: ['benchmark', 'xirr'],
  },
  diagnostico_dimension_diversificacion: {
    title: 'Dimensión: Diversificación',
    shortDescription: 'Mide cuán distribuida está tu cartera entre diferentes activos y sectores. Evita concentración excesiva.',
    whyItMatters: 'Una cartera bien diversificada reduce riesgo idiosincrático y proporciona estabilidad ante movimientos de mercado.',
    relatedTerms: ['riesgo', 'exposicion'],
  },
  diagnostico_dimension_riesgo: {
    title: 'Dimensión: Riesgo',
    shortDescription: 'Analiza volatilidad, drawdown máximo y ajuste entre el riesgo de tu cartera y tu tolerancia de riesgo.',
    whyItMatters: 'Riesgo desalineado con tus objetivos puede resultar en estrés emocional o pérdidas inesperadas.',
    relatedTerms: ['volatilidad', 'drawdown'],
  },
  diagnostico_dimension_costos: {
    title: 'Dimensión: Costos',
    shortDescription: 'Examina comisiones, spreads y otros costos explícitos e implícitos que impactan tu retorno neto.',
    whyItMatters: 'Costos elevados erosionan el rendimiento; optimizar esta dimensión mejora significativamente el retorno a largo plazo.',
    relatedTerms: ['comisiones'],
  },
  diagnostico_hallazgos: {
    title: 'Hallazgos',
    shortDescription: 'Lista de alertas y recomendaciones específicas basadas en el análisis de tu cartera. Cada hallazgo es accionable.',
    whyItMatters: 'Los hallazgos te guían sobre qué revisar o cambiar para mejorar la salud de tu cartera.',
  },
  diagnostico_datos_insuficientes_performance: {
    title: 'Datos insuficientes: Performance',
    shortDescription: 'Esta dimensión no se puede calcular porque faltan datos históricos de rendimiento.',
    whyItMatters: 'Para evaluar la performance de tu cartera se necesita: (1) historial de al menos 3–6 meses de evolución de valores, (2) datos de precios actualizados para todos los instrumentos, y (3) un benchmark configurado en "Configuración de Cartera". Sin esto, no es posible calcular métricas como CAGR o Sharpe ratio.',
    limitations: 'Una vez que tengas 3+ meses de historial con precios actualizados, esta dimensión se calculará automáticamente en el próximo diagnóstico.',
  },
  diagnostico_datos_insuficientes_objetivo: {
    title: 'Datos insuficientes: Objetivo',
    shortDescription: 'Esta dimensión no se puede calcular porque no hay un objetivo de inversión definido.',
    whyItMatters: 'Para evaluar el progreso hacia tu objetivo necesitas: (1) un objetivo de inversión creado en "Objetivo de Cartera" (monto y fecha límite), y (2) historial de aportes/evolución de la cartera para comparar contra la proyección. Sin un objetivo definido, no se puede evaluar si vas en camino correcto.',
    limitations: 'Crea un objetivo de inversión en la pantalla "Objetivo de Cartera" para habilitar esta dimensión.',
  },
}
