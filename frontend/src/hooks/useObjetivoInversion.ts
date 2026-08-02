import { useState, useEffect, useCallback } from 'react'
import {
  getObjetivoInversion,
  getAportesHistoricos,
  crearObjetivoInversion,
  editarObjetivoInversion,
  eliminarObjetivoInversion,
  type ObjetivoInversion,
  type AportesHistoricosOut,
  type ObjetivoInversionPayload,
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

    const fetch = async () => {
      try {
        setLoading(true)
        setError(null)
        const [obj, aportes] = await Promise.all([
          getObjetivoInversion(cartera),
          getAportesHistoricos(cartera),
        ])
        setObjetivo(obj)
        setAportesHistoricos(aportes)
      } catch (err: any) {
        setError((err as Error).message || 'Error cargando objetivo')
        setObjetivo(null)
        setAportesHistoricos(null)
      } finally {
        setLoading(false)
      }
    }

    fetch()
  }, [cartera])

  const crear = useCallback(
    async (payload: ObjetivoInversionPayload): Promise<ObjetivoInversion | null> => {
      if (!cartera) return null
      try {
        const nuevo = await crearObjetivoInversion(cartera, payload)
        setObjetivo(nuevo)
        return nuevo
      } catch (err: any) {
        setError((err as Error).message || 'Error creando objetivo')
        throw err
      }
    },
    [cartera]
  )

  const editar = useCallback(
    async (payload: ObjetivoInversionPayload): Promise<ObjetivoInversion | null> => {
      if (!objetivo) return null
      try {
        const actualizado = await editarObjetivoInversion(objetivo.id, payload)
        setObjetivo(actualizado)
        return actualizado
      } catch (err: any) {
        setError((err as Error).message || 'Error editando objetivo')
        throw err
      }
    },
    [objetivo]
  )

  const eliminar = useCallback(async (): Promise<void> => {
    if (!objetivo) return
    try {
      await eliminarObjetivoInversion(objetivo.id)
      setObjetivo(null)
    } catch (err: any) {
      setError((err as Error).message || 'Error eliminando objetivo')
      throw err
    }
  }, [objetivo])

  return {
    objetivo,
    aportesHistoricos,
    loading,
    error,
    crear,
    editar,
    eliminar,
  }
}
