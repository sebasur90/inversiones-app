import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
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

const STORAGE_CARTERA = 'inversiones-cartera'
const STORAGE_MONEDA = 'inversiones-moneda'

// localStorage puede fallar (modo privado, cookies bloqueadas): nunca debe tumbar la app.
function leerPreferencia(clave: string): string | null {
  try {
    return localStorage.getItem(clave)
  } catch {
    return null
  }
}

function guardarPreferencia(clave: string, valor: string | null): void {
  try {
    if (valor === null) localStorage.removeItem(clave)
    else localStorage.setItem(clave, valor)
  } catch {
    // sin persistencia, la sesión sigue funcionando igual
  }
}

export function useInversiones() {
  const [carteras, setCarteras] = useState<CarteraInfo[]>([])
  const [carteraSeleccionada, setCarteraSeleccionada] = useState<string | null>(
    () => leerPreferencia(STORAGE_CARTERA),
  )
  const [monedaSeleccionada, setMonedaSeleccionada] = useState<'USD' | 'ARS'>(
    () => (leerPreferencia(STORAGE_MONEDA) === 'ARS' ? 'ARS' : 'USD'),
  )
  const [resumen, setResumen] = useState<InversionesResumen | null>(null)
  const [exposicion, setExposicion] = useState<ExposicionOut>({ ejes: [] })
  const [rebalanceo, setRebalanceo] = useState<RebalanceoOut>({ ejes: [] })
  const [movimientos, setMovimientos] = useState<MovimientoInversion[]>([])
  const [rendimientoPorTicker, setRendimientoPorTicker] = useState<RendimientoPorTickerItem[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchSeqRef = useRef(0)

  const fetchCarteras = useCallback(async () => {
    try {
      const data = await getCarterasInversion()
      setCarteras(data)
      return data
    } catch {
      setError('Error al cargar las carteras de inversión')
      setLoading(false)
      return []
    }
  }, [])

  const fetchDetalle = useCallback(async (cartera: string | null) => {
    const seq = ++fetchSeqRef.current
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
      if (fetchSeqRef.current !== seq) return // respuesta obsoleta, se descarta
      setResumen(r)
      setExposicion(ex)
      setRebalanceo(rb)
      setMovimientos(mv)
      setRendimientoPorTicker(rt)
    } catch {
      if (fetchSeqRef.current !== seq) return
      setError('Error al cargar los datos de inversiones')
    } finally {
      if (fetchSeqRef.current === seq) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCarteras()
  }, [fetchCarteras])

  // La cartera guardada puede haber desaparecido del Sheet: se vuelve al consolidado.
  useEffect(() => {
    if (carteras.length === 0 || carteraSeleccionada === null) return
    if (!carteras.some(c => c.nombre === carteraSeleccionada)) {
      setCarteraSeleccionada(null)
    }
  }, [carteras, carteraSeleccionada])

  useEffect(() => {
    if (carteras.length === 0) {
      setLoading(false)
      return
    }
    fetchDetalle(carteraSeleccionada)
  }, [carteraSeleccionada, carteras.length, fetchDetalle])

  const elegirCartera = useCallback((cartera: string | null) => {
    setCarteraSeleccionada(cartera)
    guardarPreferencia(STORAGE_CARTERA, cartera)
  }, [])

  const elegirMoneda = useCallback((moneda: 'USD' | 'ARS') => {
    setMonedaSeleccionada(moneda)
    guardarPreferencia(STORAGE_MONEDA, moneda)
  }, [])

  const sincronizar = useCallback(async (): Promise<SyncResult> => {
    setSyncing(true)
    try {
      const resultado = await syncInversiones()
      const nuevasCarteras = await fetchCarteras()
      if (carteraSeleccionada && !nuevasCarteras.some(c => c.nombre === carteraSeleccionada)) {
        elegirCartera(null)
      } else {
        await fetchDetalle(carteraSeleccionada)
      }
      return resultado
    } finally {
      setSyncing(false)
    }
  }, [carteraSeleccionada, fetchCarteras, fetchDetalle, elegirCartera])

  // Objeto estable: el contexto lo memoiza y de él cuelgan los 21 consumidores.
  return useMemo(
    () => ({
      carteras,
      carteraSeleccionada,
      setCarteraSeleccionada: elegirCartera,
      monedaSeleccionada,
      setMonedaSeleccionada: elegirMoneda,
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
    }),
    [
      carteras, carteraSeleccionada, elegirCartera, monedaSeleccionada, elegirMoneda,
      resumen, exposicion, rebalanceo, movimientos, rendimientoPorTicker,
      loading, syncing, error, sincronizar,
    ],
  )
}
