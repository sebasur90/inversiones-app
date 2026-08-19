import { HelpContent } from '../types'

export type DiagnosticoHelpKey =
  | 'diagnostico_salud_cartera'
  | 'diagnostico_dimension_rendimiento'
  | 'diagnostico_dimension_diversificacion'
  | 'diagnostico_dimension_riesgo'
  | 'diagnostico_dimension_costos'
  | 'diagnostico_hallazgos'

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
}
