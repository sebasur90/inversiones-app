import dayjs from 'dayjs'
import { getRecordatorios, type Recordatorio } from '../api'
import { qk } from '../api/queryClient'

const CINCO_MINUTOS = 5 * 60_000

/**
 * La misma consulta para la pantalla y el Resumen. Lleva tiempos propios porque el `staleTime` global
 * es infinito, y que un recordatorio venza no invalida nada: con la app abierta nunca aparecería.
 */
export const consultaRecordatorios = {
  queryKey: qk.de('recordatorios'),
  queryFn: getRecordatorios,
  staleTime: CINCO_MINUTOS,
  refetchInterval: CINCO_MINUTOS,
}

/** `Vencido`, `Hoy`, `Mañana` o `En 12 días`. */
export function textoPlazo(r: Recordatorio): string {
  if (r.vencido) return 'Vencido'
  const dias = dayjs(r.fecha).startOf('day').diff(dayjs().startOf('day'), 'day')
  if (dias <= 0) return 'Hoy'
  if (dias === 1) return 'Mañana'
  return `En ${dias} días`
}
