import { useEffect, useState } from 'react'
import { getBenchmarksDisponibles, getConfiguracionCartera, getTickersConPrecios } from '../api'
import { useInversionesContext } from '../context/InversionesContext'

export function useBenchmarkSeleccionado(cartera: string | null) {
  const { syncVersion } = useInversionesContext()
  const [benchmarks, setBenchmarks] = useState<string[]>([])
  const [benchmarkSeleccionado, setBenchmarkSeleccionado] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    Promise.all([
      getBenchmarksDisponibles(),
      getConfiguracionCartera(cartera).catch(() => null),
      // El backend ya acepta cualquier ticker como benchmark (compara la cartera contra un
      // activo puntual, ej. "vs. GGAL"), pero GET /benchmarks sólo devuelve los benchmarks
      // "de verdad". Se agregan acá para no tener que tocar ese endpoint.
      getTickersConPrecios().catch(() => []),
    ])
      .then(([data, config, tickers]) => {
        if (cancelado) return
        const conTickers = [...data, ...tickers.map(t => t.ticker).filter(t => !data.includes(t))]
        setBenchmarks(conTickers)
        const preferido = config?.benchmark && data.includes(config.benchmark) ? config.benchmark : data[0] ?? null
        setBenchmarkSeleccionado(prev => prev ?? preferido)
      })
      .catch(() => {
        if (!cancelado) setBenchmarks([])
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [cartera, syncVersion])

  return { benchmarks, benchmarkSeleccionado, setBenchmarkSeleccionado, loading }
}
