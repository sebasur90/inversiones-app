import { HelpContent } from '../types'

export type ExposicionHelpKey =
  | 'exposicion_titulo'
  | 'exposicion_eje'
  | 'exposicion_porcentaje'
  | 'exposicion_ticker_top10'
  | 'exposicion_vencimientos'
  | 'exposicion_contribucion_concentracion'

export const EXPOSICION_HELP: Record<ExposicionHelpKey, HelpContent> = {
  exposicion_titulo: {
    title: 'Exposición',
    shortDescription: 'Vista agregada de cuál es tu inversión actual distribuida según diferentes dimensiones (Ticker, Sector, País, etc.). Te muestra dónde está concentrado tu dinero y cuál es el peso % de cada componente.',
    whyItMatters: 'Entender tu exposición es fundamental para evaluar si tu cartera está diversificada, si está muy concentrada en un sector, país o instrumento específico, y si se alinea con tu estrategia de inversión.',
    relatedTerms: ['correlacion', 'concentracion'],
  },
  exposicion_eje: {
    title: 'Eje de análisis',
    shortDescription: 'Dimensión elegida para agrupar y visualizar tu exposición: puede ser Ticker (instrumento), Sector (rubro de negocio), País (donde opera el emisor), Moneda (ARS, USD, etc.) u otra categoría. Cada eje muestra cómo se distribuye tu cartera según esa agrupación.',
    whyItMatters: 'Cambiar entre ejes te permite ver tu exposición desde diferentes perspectivas: por ejemplo, ver si estás muy invertido en un solo sector, o si tienes mucha exposición a un país específico.',
  },
  exposicion_porcentaje: {
    title: 'Porcentaje de exposición',
    shortDescription: 'El peso relativo de cada componente (Ticker, Sector, País, etc.) sobre el total de tu cartera. Se suma sobre 100% en cada eje. Junto con el valor absoluto en USD/ARS, te da una idea clara de la importancia relativa de cada inversión.',
    whyItMatters: 'El porcentaje es más importante que el valor absoluto para entender concentración: una posición de USD 10k es diferente si tu cartera es USD 50k (20%) vs USD 500k (2%). Monitorear % de exposición te ayuda a detectar cuando una posición se vuelve demasiado grande.',
  },
  exposicion_ticker_top10: {
    title: 'Otros (Top 10)',
    shortDescription: 'Cuando visualizas por Ticker (instrumento), la pantalla agrupa automáticamente los tickers del 11° en adelante en una categoría "Otros", mostrando la suma de sus valores y porcentajes. Esto evita saturar la visualización con demasiados elementos pequeños.',
    whyItMatters: 'Mantiene la visualización legible y enfocada en las posiciones más importantes. Si necesitás detallar cada instrumento individual, abre la pestaña "Posiciones" que muestra el listado completo.',
    relatedTerms: ['exposicion'],
  },
  exposicion_vencimientos: {
    title: 'Calendario de vencimientos',
    shortDescription: 'Acceso rápido a la vista de vencimientos de tus bonos y otros instrumentos con fecha de vencimiento. Útil para planificar reinversiones y entender cuándo recuperarás capital.',
    whyItMatters: 'Conocer tus vencimientos próximos te ayuda a gestionar flujos de caja y a rebalancear tu cartera de forma proactiva, en lugar de enfrentar sorpresas cuando vence un bono o un instrumento.',
  },
  exposicion_contribucion_concentracion: {
    title: 'Contribución y concentración',
    shortDescription: 'Vista especializada que muestra cómo cada posición contribuyó al rendimiento total de tu cartera (en dólares) y métricas de concentración (HHI, N efectivo). Complementa la exposición actual con contexto de histórico y de riesgo de concentración.',
    whyItMatters: 'Te permite evaluar no solo dónde está tu dinero ahora, sino cuál fue el rol de cada posición en tu desempeño y qué tan concentrada realmente está tu cartera (más allá de los % visibles).',
    relatedTerms: ['contribucion', 'hhi'],
  },
}
