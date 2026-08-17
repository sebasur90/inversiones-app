import { useState, useEffect } from 'react'
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

export interface UseObjetivoInversionResult {
  objetivo: ObjetivoInversion | null
  aportesHistoricos: AportesHistoricosOut | null
  evolucion: EvolucionOut | null
  riesgo: RiesgoOut | null
  configuracion: ConfiguracionCartera | null
  loading: boolean
  error: string | null
}

export function useObjetivoInversion(cartera: string | null): UseObjetivoInversionResult {
  const [objetivo, setObjetivo] = useState<ObjetivoInversion | null>(null)
  const [aportesHistoricos, setAportesHistoricos] = useState<AportesHistoricosOut | null>(null)
  const [evolucion, setEvolucion] = useState<EvolucionOut | null>(null)
  const [riesgo, setRiesgo] = useState<RiesgoOut | null>(null)
  const [configuracion, setConfiguracion] = useState<ConfiguracionCartera | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!cartera) {
      setObjetivo(null)
      setAportesHistoricos(null)
      setEvolucion(null)
      setRiesgo(null)
      setConfiguracion(null)
      setLoading(false)
      return
    }

    let cancelado = false

    const fetch = async () => {
      try {
        setLoading(true)
        setError(null)

        // Fetch objetivo, aportes, riesgo, configuracion en paralelo
        const [obj, aportes, riesgoData, configData] = await Promise.all([
          getObjetivoInversion(cartera),
          getAportesHistoricos(cartera),
          getRiesgo(cartera, 'usd', null).catch(() => null),
          getConfiguracionCartera(cartera).catch(() => null),
        ])

        if (cancelado) return

        // Fetch evolucion con desde = primer mes de aportes
        const desde = aportes?.curva[0]?.mes ? `${aportes.curva[0].mes}-01` : undefined
        const evolucionData = await getEvolucionInversiones(cartera, desde).catch(() => null)

        if (cancelado) return

        setObjetivo(obj)
        setAportesHistoricos(aportes)
        setEvolucion(evolucionData)
        setRiesgo(riesgoData)
        setConfiguracion(configData)
      } catch (err: any) {
        if (cancelado) return
        setError((err as Error).message || 'Error cargando objetivo')
        setObjetivo(null)
        setAportesHistoricos(null)
        setEvolucion(null)
        setRiesgo(null)
        setConfiguracion(null)
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
    evolucion,
    riesgo,
    configuracion,
    loading,
    error,
  }
}
