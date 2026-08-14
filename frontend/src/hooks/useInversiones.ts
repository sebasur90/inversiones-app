import { useState, useEffect, useCallback } from 'react'
import {
  syncInversiones,
  getCarterasInversion,
  getResumenInversiones,
  getExposicionInversiones,
  getRebalanceoInversiones,
  getMovimientosInversion,
  getRendimientoPorTicker,
  type CarteraInfo,
  type InversionesResumen,
  type ExposicionOut,
  type RebalanceoOut,
  type MovimientoInversion,
  type RendimientoPorTickerItem,
  type SyncResult,
} from '../api'

export function useInversiones() {
  const [carteras, setCarteras] = useState<CarteraInfo[]>([])
  const [carteraSeleccionada, setCarteraSeleccionada] = useState<string | null>(null)
  const [monedaSeleccionada, setMonedaSeleccionada] = useState<'USD' | 'ARS'>('USD')
  const [resumen, setResumen] = useState<InversionesResumen | null>(null)
  const [exposicion, setExposicion] = useState<ExposicionOut>({ ejes: [] })
  const [rebalanceo, setRebalanceo] = useState<RebalanceoOut>({ ejes: [] })
  const [movimientos, setMovimientos] = useState<MovimientoInversion[]>([])
  const [rendimientoPorTicker, setRendimientoPorTicker] = useState<RendimientoPorTickerItem[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchCarteras = useCallback(async () => {
    const data = await getCarterasInversion()
    setCarteras(data)
    return data
  }, [])

  const fetchDetalle = useCallback(async (cartera: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const [r, ex, rb, mv, rt] = await Promise.all([
        getResumenInversiones(cartera),
        getExposicionInversiones(cartera),
        getRebalanceoInversiones(cartera),
        getMovimientosInversion(cartera ? { cartera } : {}),
        getRendimientoPorTicker(cartera),
      ])
      setResumen(r)
      setExposicion(ex)
      setRebalanceo(rb)
      setMovimientos(mv)
      setRendimientoPorTicker(rt)
    } catch {
      setError('Error al cargar los datos de inversiones')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCarteras()
  }, [fetchCarteras])

  useEffect(() => {
    if (carteras.length === 0) {
      setLoading(false)
      return
    }
    fetchDetalle(carteraSeleccionada)
  }, [carteraSeleccionada, carteras.length, fetchDetalle])

  const sincronizar = async (): Promise<SyncResult> => {
    setSyncing(true)
    try {
      const resultado = await syncInversiones()
      const nuevasCarteras = await fetchCarteras()
      if (carteraSeleccionada && !nuevasCarteras.some(c => c.nombre === carteraSeleccionada)) {
        setCarteraSeleccionada(null)
      } else {
        await fetchDetalle(carteraSeleccionada)
      }
      return resultado
    } finally {
      setSyncing(false)
    }
  }

  return {
    carteras,
    carteraSeleccionada,
    setCarteraSeleccionada,
    monedaSeleccionada,
    setMonedaSeleccionada,
    resumen,
    exposicion,
    rebalanceo,
    movimientos,
    rendimientoPorTicker,
    loading,
    syncing,
    error,
    sincronizar,
    sinDatos: carteras.length === 0,
  }
}
