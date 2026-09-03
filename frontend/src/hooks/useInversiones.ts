import { useCallback, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  syncInversiones,
  getCarterasInversion,
  getResumenInversiones,
  getExposicionInversiones,
  getRebalanceoInversiones,
  getMovimientosInversion,
  getRendimientoPorTicker,
  getWatchlist,
  type ExposicionOut,
  type RebalanceoOut,
  type MovimientoInversion,
  type RendimientoPorTickerItem,
  type WatchlistItemOut,
  type SyncResult,
} from '../api'
import { qk } from '../api/queryClient'
import { alertasDeCompra } from '../utils/alertasPrecio'
import {
  leerPreferencia,
  guardarPreferencia,
  CLAVE_CARTERA as STORAGE_CARTERA,
  CLAVE_MONEDA as STORAGE_MONEDA,
  CLAVE_UMBRAL_PROXIMIDAD as STORAGE_UMBRAL_PROXIMIDAD,
  UMBRAL_PROXIMIDAD_DEFAULT,
  UMBRAL_PROXIMIDAD_MAX,
  usePreferencia,
} from './usePreferencia'

const EXPOSICION_VACIA: ExposicionOut = { ejes: [] }
const REBALANCEO_VACIO: RebalanceoOut = { ejes: [] }
const MOVIMIENTOS_VACIOS: MovimientoInversion[] = []
const RENDIMIENTO_VACIO: RendimientoPorTickerItem[] = []
const WATCHLIST_VACIA: WatchlistItemOut[] = []

// A nivel de módulo: si fueran inline, `usePreferencia` devolvería un setter nuevo en cada
// render y el useMemo de abajo (y con él el contexto entero) se recalcularía siempre.
const parseCartera = (crudo: string): string | null => crudo
const serializarCartera = (valor: string | null): string => valor ?? ''
const parseMoneda = (crudo: string): 'USD' | 'ARS' => (crudo === 'ARS' ? 'ARS' : 'USD')
const serializarMoneda = (valor: 'USD' | 'ARS'): string => valor
// No se usa `usePreferenciaNumerica`: sus callbacks son inline, así que devolvería un setter
// nuevo en cada render y rompería el useMemo de abajo.
const parseUmbral = (crudo: string): number | null => {
  const n = Number(crudo)
  return Number.isFinite(n) && n >= 0 && n <= UMBRAL_PROXIMIDAD_MAX ? n : null
}
const serializarUmbral = (valor: number): string => String(valor)

export function useInversiones() {
  const queryClient = useQueryClient()

  const [carteraSeleccionada, elegirCartera] = usePreferencia<string | null>(
    STORAGE_CARTERA, null, parseCartera, serializarCartera,
  )
  const [monedaSeleccionada, elegirMoneda] = usePreferencia<'USD' | 'ARS'>(
    STORAGE_MONEDA, 'USD', parseMoneda, serializarMoneda,
  )
  // Vive acá, y no en cada pantalla, porque el badge del nav, la lista de posiciones y el
  // detalle del ticker tienen que reaccionar juntos cuando se cambia en Ajustes.
  const [umbralProximidadPct, elegirUmbralProximidad] = usePreferencia<number>(
    STORAGE_UMBRAL_PROXIMIDAD, UMBRAL_PROXIMIDAD_DEFAULT, parseUmbral, serializarUmbral,
  )

  const carterasQuery = useQuery({
    queryKey: qk.carteras,
    queryFn: () => getCarterasInversion(),
  })
  const carteras = carterasQuery.data ?? []

  // La cartera guardada puede haber desaparecido del Sheet: se pide el consolidado. Se
  // resuelve al leer, no con un efecto que corrija el estado después de un render con la
  // cartera fantasma.
  const carteraValida =
    carteraSeleccionada !== null && carteras.length > 0 && !carteras.some(c => c.nombre === carteraSeleccionada)
      ? null
      : carteraSeleccionada

  const hayCarteras = carteras.length > 0
  // `keepPreviousData`: al cambiar de cartera la pantalla mantiene los números anteriores
  // mientras llegan los nuevos, en vez de vaciarse.
  const comun = { enabled: hayCarteras, placeholderData: keepPreviousData }

  const resumenQuery = useQuery({
    queryKey: qk.resumen(carteraValida),
    queryFn: () => getResumenInversiones(carteraValida),
    ...comun,
  })
  const exposicionQuery = useQuery({
    queryKey: qk.exposicion(carteraValida),
    queryFn: () => getExposicionInversiones(carteraValida),
    ...comun,
  })
  const rebalanceoQuery = useQuery({
    queryKey: qk.rebalanceo(carteraValida),
    queryFn: () => getRebalanceoInversiones(carteraValida),
    ...comun,
  })
  const movimientosQuery = useQuery({
    queryKey: qk.movimientos(carteraValida),
    queryFn: () => getMovimientosInversion(carteraValida ? { cartera: carteraValida } : {}),
    ...comun,
  })
  const rendimientoQuery = useQuery({
    queryKey: qk.rendimientoPorTicker(carteraValida),
    queryFn: () => getRendimientoPorTicker(carteraValida),
    ...comun,
  })

  // Global, no por cartera: no depende de `hayCarteras` ni entra en `comun`/`detalleQueries`
  // (el badge de watchlist y el bloque de Resumen deben poder mostrarse aunque el consolidado
  // de carteras todavía esté cargando).
  const watchlistQuery = useQuery({
    queryKey: qk.watchlist,
    queryFn: () => getWatchlist(),
  })

  const detalleQueries = [resumenQuery, exposicionQuery, rebalanceoQuery, movimientosQuery, rendimientoQuery]

  // Sólo la primera carga vacía la pantalla; las siguientes muestran los datos previos.
  const loading =
    carterasQuery.isLoading || (hayCarteras && detalleQueries.some(q => q.isLoading))

  const error = carterasQuery.isError
    ? 'Error al cargar las carteras de inversión'
    : detalleQueries.some(q => q.isError)
      ? 'Error al cargar los datos de inversiones'
      : null

  const syncMutation = useMutation({
    mutationFn: syncInversiones,
    // Todo lo cacheado quedó viejo: los datos sólo cambian acá. Esto reemplaza al contador
    // `syncVersion` que antes cada pantalla tenía que poner en las dependencias de su efecto.
    onSuccess: () => queryClient.invalidateQueries(),
  })

  const { mutateAsync } = syncMutation
  const sincronizar = useCallback((): Promise<SyncResult> => mutateAsync(), [mutateAsync])
  const syncing = syncMutation.isPending

  return useMemo(
    () => ({
      carteras,
      carteraSeleccionada: carteraValida,
      setCarteraSeleccionada: elegirCartera,
      monedaSeleccionada,
      setMonedaSeleccionada: elegirMoneda,
      umbralProximidadPct,
      setUmbralProximidadPct: elegirUmbralProximidad,
      // Como ratio, la unidad en la que el backend devuelve `pct_a_objetivo`/`pct_a_stop_loss`:
      // así ningún consumidor tiene que acordarse de dividir por 100.
      umbralProximidad: umbralProximidadPct / 100,
      resumen: resumenQuery.data ?? null,
      exposicion: exposicionQuery.data ?? EXPOSICION_VACIA,
      rebalanceo: rebalanceoQuery.data ?? REBALANCEO_VACIO,
      movimientos: movimientosQuery.data ?? MOVIMIENTOS_VACIOS,
      rendimientoPorTicker: rendimientoQuery.data ?? RENDIMIENTO_VACIO,
      watchlist: watchlistQuery.data ?? WATCHLIST_VACIA,
      // Derivada acá, no en cada pantalla: el badge del menú Más y el bloque de Resumen
      // comparten el mismo cálculo sin duplicar el fetch ni el umbral.
      alertasCompra: alertasDeCompra(watchlistQuery.data ?? WATCHLIST_VACIA, umbralProximidadPct / 100),
      loading,
      syncing,
      error,
      sincronizar,
      sinDatos: !carterasQuery.isLoading && carteras.length === 0,
      // Es el timestamp del último SyncRun: viene igual en todas las carteras.
      ultimoSync: carteras[0]?.ultimo_sync ?? null,
    }),
    [
      carteras, carteraValida, elegirCartera, monedaSeleccionada, elegirMoneda,
      umbralProximidadPct, elegirUmbralProximidad,
      resumenQuery.data, exposicionQuery.data, rebalanceoQuery.data,
      movimientosQuery.data, rendimientoQuery.data, watchlistQuery.data,
      loading, syncing, error, sincronizar, carterasQuery.isLoading,
    ],
  )
}

export { leerPreferencia, guardarPreferencia }
