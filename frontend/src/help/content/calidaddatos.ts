import { HelpContent } from '../types'

export type CalidadDatosHelpKey =
  | 'calidaddatos_health_score'
  | 'calidaddatos_sync_timestamp'
  | 'calidaddatos_issues'
  | 'calidaddatos_filas_error'
  | 'calidaddatos_filas_advertencia'

export const CALIDADDATOS_HELP: Record<CalidadDatosHelpKey, HelpContent> = {
  calidaddatos_health_score: {
    title: 'Puntuación de calidad de datos',
    shortDescription: 'Indicador de 0–100 que refleja la salud general de tus datos. Considera la cantidad de errores, advertencias y sincronizaciones exitosas.',
    whyItMatters: 'Una puntuación alta significa que tus datos están actualizados y confiables. Una baja indica que hay problemas de sincronización o integridad que deberías revisar.',
    relatedTerms: ['invertido'],
  },
  calidaddatos_sync_timestamp: {
    title: 'Última sincronización',
    shortDescription: 'Fecha y hora del último intento de sincronizar tus datos con el servidor, más el tiempo que tardó el proceso.',
    whyItMatters: 'Te permite saber si tus datos son recientes o si hace mucho que no se actualiza la información.',
  },
  calidaddatos_issues: {
    title: 'Problemas encontrados',
    shortDescription: 'Lista de errores críticos (🔴) y advertencias (🟡) detectados durante la sincronización. Los errores requieren atención inmediata; las advertencias son informativas.',
    whyItMatters: 'Identificar y resolver estos problemas asegura que tus reportes y cálculos sean precisos.',
  },
  calidaddatos_filas_error: {
    title: 'Errores críticos',
    shortDescription: 'Cantidad de registros que fallaron al sincronizar. Estos problemas pueden afectar la precisión de tus datos.',
    whyItMatters: 'Los errores críticos deben resolverse para garantizar la integridad de la información.',
  },
  calidaddatos_filas_advertencia: {
    title: 'Advertencias',
    shortDescription: 'Cantidad de registros que se sincronizaron pero con problemas menores. La información se cargó, pero hay detalles que podrían revisarse.',
    whyItMatters: 'Las advertencias no bloquean el cálculo, pero vale la pena revisar qué problemas encontró el sistema.',
  },
}
