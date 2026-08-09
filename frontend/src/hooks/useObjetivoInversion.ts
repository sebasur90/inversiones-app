import { useState, useEffect } from 'react'
import {
  getObjetivoInversion,
  getAportesHistoricos,
  type ObjetivoInversion,
  type AportesHistoricosOut,
} from '../api'

export function useObjetivoInversion(cartera: string | null) {
  const [objetivo, setObjetivo] = useState<ObjetivoInversion | null>(null)
  const [aportesHistoricos, setAportesHistoricos] = useState<AportesHistoricosOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!cartera) {
      setObjetivo(null)
      setAportesHistoricos(null)
      setLoading(false)
      return
    }

    let cancelado = false

    const fetch = async () => {
      try {
        setLoading(true)
        setError(null)
        const [obj, aportes] = await Promise.all([
          getObjetivoInversion(cartera),
          getAportesHistoricos(cartera),
        ])
        if (cancelado) return
        setObjetivo(obj)
        setAportesHistoricos(aportes)
      } catch (err: any) {
        if (cancelado) return
        setError((err as Error).message || 'Error cargando objetivo')
        setObjetivo(null)
        setAportesHistoricos(null)
      } finally {
        if (!cancelado) setLoading(false)
      }
    }

    fetch()
    return () => {
      cancelado = true
    }
  }, [cartera])

  return {
    objetivo,
    aportesHistoricos,
    loading,
    error,
  }
}
