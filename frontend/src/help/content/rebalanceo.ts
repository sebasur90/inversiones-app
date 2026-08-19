import { HelpContent } from '../types'

export type RebalanceoHelpKey =
  | 'rebalanceo_modo_simulador'
  | 'rebalanceo_tolerancia'
  | 'rebalanceo_cambios_necesarios_opcionales'
  | 'rebalanceo_sin_objetivo'

export const REBALANCEO_HELP: Record<RebalanceoHelpKey, HelpContent> = {
  rebalanceo_modo_simulador: {
    title: 'Modo de simulación',
    shortDescription: '"Rebalanceo completo" recalcula toda la cartera para que cada categoría alcance exactamente su objetivo. "Solo nuevos aportes" solo asigna el dinero nuevo sin vender nada; es más conservador si no querés tocar posiciones existentes.',
    example: 'Tienes 100 en Renta Fija (objetivo 30%) y 100 en Acciones (objetivo 70%). En "Completo": vendes 40 de Renta Fija y compras 40 de Acciones (resultado: 60/140). En "Solo aportes": si sumás 100 nuevos, asignas 30 a Renta Fija y 70 a Acciones (resultado: 130/170).',
  },
  rebalanceo_tolerancia: {
    title: 'Tolerancia',
    shortDescription: 'Rango de desvío (en puntos porcentuales) permitido antes de marcar una categoría como "fuera de rango" (rojo). Hoy está fijo en 2 pp. Una categoría en objetivo 30% con tolerancia 2 pp se considera "OK" si está entre 28-32%.',
  },
  rebalanceo_cambios_necesarios_opcionales: {
    title: 'Cambios necesarios vs. opcionales',
    shortDescription: '"Necesarios" = categorías fuera de tolerancia, requieren acción inmediata. "Opcionales" = categorías dentro de tolerancia pero que podrían mejorarse. Aplica solo si usaste "Rebalanceo completo".',
  },
  rebalanceo_sin_objetivo: {
    title: 'Sin objetivo',
    shortDescription: 'Posiciones o categorías que tienen dinero invertido pero no tienen un % objetivo cargado en el Sheet. Aparecen separadas porque no puedes rebalancearlas sin definir un objetivo primero.',
  },
}
