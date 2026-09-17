import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  actualizarWatchlist,
  agregarAWatchlist,
  eliminarDeWatchlist,
  getSenalesTecnicas,
  getWatchlist,
  refrescarPrecioWatchlist,
  type CatalogoInstrumentoOut,
  type SenalTickerOut,
  type WatchlistItemOut,
} from '../api'
import { qk } from '../api/queryClient'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import EmptyState from '../components/ui/EmptyState'
import Segmented from '../components/ui/Segmented'
import QueryBoundary from '../components/ui/QueryBoundary'
import Modal from '../components/ui/Modal'
import Button from '../components/ui/Button'
import Toast from '../components/ui/Toast'
import InfoTooltip from '../help/components/InfoTooltip'
import AlertaPrecioBadge from '../components/inversiones/AlertaPrecioBadge'
import SelectorInstrumento from '../components/inversiones/SelectorInstrumento'
import DetalleWatchlist from '../components/inversiones/DetalleWatchlist'
import { Icon } from '../components/icons/Icons'
import { formatARS, formatUSD, formatPrecio } from '../utils'
import { estadoWatchlist, type EstadoAlerta } from '../utils/alertasPrecio'

type Filtro = 'todas' | 'con_alerta'

function formatMoneda(valor: number, moneda: string): string {
  if (moneda === 'ARS') return formatARS(valor)
  if (moneda === 'USD') return formatUSD(valor)
  return formatPrecio(valor)
}

const AVATAR_ALERTA: Record<EstadoAlerta, string> = {
  stop_loss_disparado: 'border-app-neg/40 text-app-neg',
  stop_loss_cerca: 'border-app-accent/40 text-app-accent',
  objetivo_alcanzado: 'border-app-pos/40 text-app-pos',
  objetivo_cerca: 'border-app-accent/40 text-app-accent',
  compra_en_zona: 'border-app-accent/40 text-app-accent',
  compra_cerca: 'border-app-pos/40 text-app-pos',
}

export default function Watchlist() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { umbralProximidad } = useInversionesContext()
  const [searchParams, setSearchParams] = useSearchParams()
  const filtro: Filtro = searchParams.get('alerta') === 'con_alerta' ? 'con_alerta' : 'todas'

  const [agregarAbierto, setAgregarAbierto] = useState(false)
  const [tickerAbierto, setTickerAbierto] = useState<string | null>(null)
  const [aviso, setAviso] = useState<{ texto: string; tono: 'success' | 'error' } | null>(null)

  const watchlistQuery = useQuery({
    queryKey: qk.watchlist,
    queryFn: () => getWatchlist(),
  })
  const items = useMemo(() => watchlistQuery.data ?? [], [watchlistQuery.data])

  // Señales de las estrategias técnicas guardadas para estos tickers. Es información extra: si
  // el pedido falla, la watchlist se muestra igual (sin badges).
  const senalesQuery = useQuery({
    queryKey: qk.de('tecnico-senales'),
    queryFn: () => getSenalesTecnicas(),
  })
  const senalPorTicker = useMemo(() => {
    const mapa = new Map<string, SenalTickerOut>()
    for (const s of senalesQuery.data ?? []) {
      if (!mapa.has(s.ticker)) mapa.set(s.ticker, s)  // ya vienen ordenadas por antigüedad
    }
    return mapa
  }, [senalesQuery.data])

  // Sólo se invalida la watchlist: la lista no alimenta ningún otro cálculo de la app.
  const refrescarLista = () => queryClient.invalidateQueries({ queryKey: qk.watchlist })

  const agregarMut = useMutation({
    mutationFn: (instrumento: CatalogoInstrumentoOut) =>
      agregarAWatchlist({ ticker: instrumento.simbolo }),
    onSuccess: async (item) => {
      await refrescarLista()
      setAgregarAbierto(false)
      // Se abre el detalle en el acto: agregar sin fijar el objetivo deja el instrumento sin alerta.
      setTickerAbierto(item.ticker)
      setAviso(
        item.precio_actual == null
          ? { texto: `${item.ticker} agregado, pero no se pudo cotizar`, tono: 'error' }
          : { texto: `${item.ticker} agregado`, tono: 'success' },
      )
    },
    onError: () => setAviso({ texto: 'No se pudo agregar el instrumento', tono: 'error' }),
  })

  const guardarMut = useMutation({
    mutationFn: ({ ticker, ...cambios }: { ticker: string; objetivo: number | null; notas: string | null }) =>
      actualizarWatchlist(ticker, cambios),
    onSuccess: async () => {
      await refrescarLista()
      setTickerAbierto(null)
      setAviso({ texto: 'Cambios guardados', tono: 'success' })
    },
    onError: () => setAviso({ texto: 'No se pudieron guardar los cambios', tono: 'error' }),
  })

  const refrescarMut = useMutation({
    mutationFn: (ticker: string) => refrescarPrecioWatchlist(ticker),
    onSuccess: async (item) => {
      await refrescarLista()
      setAviso(
        item.precio_actual == null
          ? { texto: 'Todavía sin cotización', tono: 'error' }
          : { texto: `Precio actualizado: ${formatMoneda(item.precio_actual, item.moneda_precio ?? item.moneda)}`, tono: 'success' },
      )
    },
    onError: () => setAviso({ texto: 'No se pudo actualizar el precio', tono: 'error' }),
  })

  const eliminarMut = useMutation({
    mutationFn: (ticker: string) => eliminarDeWatchlist(ticker),
    onSuccess: async (_data, ticker) => {
      await refrescarLista()
      setTickerAbierto(null)
      setAviso({ texto: `${ticker} ya no se sigue`, tono: 'success' })
    },
    onError: () => setAviso({ texto: 'No se pudo dar de baja el instrumento', tono: 'error' }),
  })

  const conEstado = useMemo(
    () => items.map(item => ({ item, estado: estadoWatchlist(item, umbralProximidad) })),
    [items, umbralProximidad],
  )

  const conteoConAlerta = conEstado.filter(({ estado }) => estado !== null).length

  const filtrados = filtro === 'con_alerta' ? conEstado.filter(({ estado }) => estado !== null) : conEstado

  const yaSeguidos = useMemo(() => new Set(items.map(i => i.ticker)), [items])
  const itemAbierto: WatchlistItemOut | null =
    items.find(i => i.ticker === tickerAbierto) ?? null

  function cambiarFiltro(nuevo: Filtro) {
    setSearchParams(nuevo === 'todas' ? {} : { alerta: nuevo }, { replace: true })
  }

  const opciones: { value: Filtro; label: string }[] = [
    { value: 'todas', label: `Todos · ${items.length}` },
    { value: 'con_alerta', label: `Con alerta · ${conteoConAlerta}` },
  ]

  return (
    <div className="pb-4">
      <ScreenHeader title="Watchlist" onBack={() => navigate(-1)} />

      <div className="flex items-center gap-1.5 mb-3">
        <div className="min-w-0 flex-1">
          <Segmented options={opciones} value={filtro} onChange={cambiarFiltro} />
        </div>
        <InfoTooltip term="watchlist_zona_compra" />
        <Button
          className="h-9 px-3 shrink-0"
          onClick={() => setAgregarAbierto(true)}
          icon={<Icon name="plus" className="w-4 h-4" />}
        >
          Agregar
        </Button>
      </div>

      <QueryBoundary
        isLoading={watchlistQuery.isLoading}
        error={watchlistQuery.error}
        onRetry={() => void watchlistQuery.refetch()}
      >
        {items.length === 0 ? (
          <EmptyState
            title="Todavía no seguís ningún instrumento"
            description='Tocá "Agregar" y elegí del catálogo de instrumentos: la app baja el último precio y vos fijás a qué precio querrías comprarlo.'
          />
        ) : filtrados.length === 0 ? (
          <EmptyState title="Ningún instrumento cerca de su zona de compra" />
        ) : (
          <div>
            {filtrados.map(({ item, estado }) => {
              const senal = senalPorTicker.get(item.ticker)
              return (
                <button
                  key={item.ticker}
                  onClick={() => setTickerAbierto(item.ticker)}
                  className="w-full flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0 text-left"
                >
                  <div
                    className={`w-9 h-9 rounded-[11px] bg-app-surface-2 border flex items-center justify-center font-mono text-label font-bold shrink-0 ${
                      estado ? AVATAR_ALERTA[estado] : 'border-app-border text-app-text'
                    }`}
                  >
                    {item.ticker.slice(0, 4)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <div className="text-caption font-bold text-app-text truncate">{item.nombre}</div>
                      {estado && <AlertaPrecioBadge estado={estado} pct={item.pct_a_objetivo} compacto />}
                      {senal && (
                        <span
                          title={`${senal.estrategia_nombre} · ${senal.motivo} · ${senal.fecha} · ${senal.moneda || ''} ${senal.precio.toFixed(2)}${senal.variante === 'subyacente' ? ' (subyacente)' : ''}`}
                          className={`shrink-0 rounded-md px-1.5 py-0.5 text-label font-bold border ${
                            senal.tipo === 'compra'
                              ? 'border-app-pos/40 text-app-pos bg-app-pos-soft'
                              : 'border-app-neg/40 text-app-neg bg-app-neg-soft'
                          }`}
                        >
                          {senal.tipo === 'compra' ? '▲' : '▼'} {senal.tipo}
                          {senal.variante === 'subyacente' && <span className="ml-1 opacity-70">{senal.moneda || 'USD'}</span>}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 text-label text-app-text-dim mt-0.5 truncate">
                      {item.tipo_instrumento || '—'} · {item.mercado || '—'}
                      {item.en_cartera && ' · En cartera'}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-mono text-caption font-bold text-app-text tabular-nums">
                      {item.precio_actual != null ? formatMoneda(item.precio_actual, item.moneda_precio ?? item.moneda) : '—'}
                    </div>
                    <div className="flex items-center justify-end gap-0.5 text-label text-app-text-dim mt-0.5 tabular-nums">
                      <span className="inline-flex items-center gap-0.5">
                        Obj. {item.precio_objetivo != null ? formatMoneda(item.precio_objetivo, item.moneda) : '—'}
                        <InfoTooltip term="watchlist_precio_objetivo" />
                      </span>
                    </div>
                  </div>
                  <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90 shrink-0" />
                </button>
              )
            })}
          </div>
        )}
      </QueryBoundary>

      <Modal open={agregarAbierto} onClose={() => setAgregarAbierto(false)} title="Agregar instrumento">
        <SelectorInstrumento
          yaSeguidos={yaSeguidos}
          deshabilitado={agregarMut.isPending}
          onElegir={instrumento => agregarMut.mutate(instrumento)}
        />
      </Modal>

      <Modal
        open={itemAbierto !== null}
        onClose={() => setTickerAbierto(null)}
        title={itemAbierto?.ticker ?? ''}
      >
        {itemAbierto && (
          <DetalleWatchlist
            item={itemAbierto}
            formatMoneda={formatMoneda}
            guardando={guardarMut.isPending}
            refrescando={refrescarMut.isPending}
            eliminando={eliminarMut.isPending}
            onGuardar={cambios => guardarMut.mutate({ ticker: itemAbierto.ticker, ...cambios })}
            onRefrescar={() => refrescarMut.mutate(itemAbierto.ticker)}
            onEliminar={() => eliminarMut.mutate(itemAbierto.ticker)}
            onVerTecnico={() => navigate(`/ticker/${encodeURIComponent(itemAbierto.ticker)}`)}
          />
        )}
      </Modal>

      <Toast message={aviso?.texto ?? null} tone={aviso?.tono} onDone={() => setAviso(null)} />
    </div>
  )
}
