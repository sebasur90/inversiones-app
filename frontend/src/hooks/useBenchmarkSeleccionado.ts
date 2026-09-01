import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getBenchmarksDisponibles, getConfiguracionCartera, getTickersConPrecios } from '../api'
import { qk } from '../api/queryClient'

export function useBenchmarkSeleccionado(cartera: string | null) {
  const [elegido, setBenchmarkSeleccionado] = useState<string | null>(null)

  const query = useQuery({
    queryKey: qk.de('benchmarks-disponibles', cartera),
    queryFn: async () => {
      const [data, config, tickers] = await Promise.all([
        getBenchmarksDisponibles(),
        getConfiguracionCartera(cartera).catch(() => null),
        // El backend ya acepta cualquier ticker como benchmark (compara la cartera contra un
        // activo puntual, ej. "vs. GGAL"), pero GET /benchmarks sólo devuelve los benchmarks
        // "de verdad". Se agregan acá para no tener que tocar ese endpoint.
        getTickersConPrecios().catch(() => []),
      ])
      const conTickers = [...data, ...tickers.map(t => t.ticker).filter(t => !data.includes(t))]
      const preferido = config?.benchmark && data.includes(config.benchmark) ? config.benchmark : data[0] ?? null
      return { benchmarks: conTickers, preferido }
    },
  })

  const benchmarks = query.data?.benchmarks ?? []
  // Lo que eligió el usuario manda; si todavía no eligió, el de la configuración de la cartera.
  const benchmarkSeleccionado = elegido ?? query.data?.preferido ?? null

  return { benchmarks, benchmarkSeleccionado, setBenchmarkSeleccionado, loading: query.isLoading }
}
