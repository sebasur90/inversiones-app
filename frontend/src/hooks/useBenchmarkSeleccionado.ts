import { useEffect, useState } from 'react'
import { getBenchmarksDisponibles, getConfiguracionCartera } from '../api'

export function useBenchmarkSeleccionado(cartera: string | null) {
  const [benchmarks, setBenchmarks] = useState<string[]>([])
  const [benchmarkSeleccionado, setBenchmarkSeleccionado] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    Promise.all([getBenchmarksDisponibles(), getConfiguracionCartera(cartera).catch(() => null)])
      .then(([data, config]) => {
        if (cancelado) return
        setBenchmarks(data)
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
  }, [cartera])

  return { benchmarks, benchmarkSeleccionado, setBenchmarkSeleccionado, loading }
}
