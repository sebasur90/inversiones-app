import { useQuery } from '@tanstack/react-query'
import {
  getObjetivoInversion,
  getAportesHistoricos,
  getEvolucionInversiones,
  getRiesgo,
  getConfiguracionCartera,
  type ObjetivoInversion,
  type AportesHistoricosOut,
  type EvolucionOut,
  type RiesgoOut,
  type ConfiguracionCartera,
} from '../api'
import { qk } from '../api/queryClient'

export interface UseObjetivoInversionResult {
  objetivo: ObjetivoInversion | null
  aportesHistoricos: AportesHistoricosOut | null
  evolucion: EvolucionOut | null
  riesgo: RiesgoOut | null
  configuracion: ConfiguracionCartera | null
  loading: boolean
  error: string | null
}

/** El objetivo es por cartera: en el consolidado no hay nada que pedir. */
export function useObjetivoInversion(cartera: string | null): UseObjetivoInversionResult {
  const query = useQuery({
    queryKey: qk.de('objetivo', cartera),
    enabled: cartera !== null,
    queryFn: async () => {
      const nombre = cartera as string
      const [objetivo, aportesHistoricos, riesgo, configuracion] = await Promise.all([
        getObjetivoInversion(nombre),
        getAportesHistoricos(nombre),
        getRiesgo(nombre, 'usd', null).catch(() => null),
        getConfiguracionCartera(nombre).catch(() => null),
      ])

      // La evolución arranca en el primer mes con aportes: pedir desde antes traería puntos
      // vacíos que sólo achatan el gráfico.
      const desde = aportesHistoricos?.curva[0]?.mes ? `${aportesHistoricos.curva[0].mes}-01` : undefined
      const evolucion = await getEvolucionInversiones(nombre, desde).catch(() => null)

      return { objetivo, aportesHistoricos, evolucion, riesgo, configuracion }
    },
  })

  return {
    objetivo: query.data?.objetivo ?? null,
    aportesHistoricos: query.data?.aportesHistoricos ?? null,
    evolucion: query.data?.evolucion ?? null,
    riesgo: query.data?.riesgo ?? null,
    configuracion: query.data?.configuracion ?? null,
    loading: cartera !== null && query.isLoading,
    error: query.error ? (query.error as Error).message || 'Error cargando objetivo' : null,
  }
}
