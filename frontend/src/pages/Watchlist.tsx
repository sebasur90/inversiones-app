import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getWatchlist } from '../api'
import { qk } from '../api/queryClient'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import EmptyState from '../components/ui/EmptyState'
import Segmented from '../components/ui/Segmented'
import QueryBoundary from '../components/ui/QueryBoundary'
import InfoTooltip from '../help/components/InfoTooltip'
import AlertaPrecioBadge from '../components/inversiones/AlertaPrecioBadge'
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
  stop_loss_disparado: 'border-app-coral/40 text-app-coral',
  stop_loss_cerca: 'border-app-gold/40 text-app-gold',
  objetivo_alcanzado: 'border-app-teal/40 text-app-teal',
  objetivo_cerca: 'border-app-gold/40 text-app-gold',
  compra_en_zona: 'border-app-gold/40 text-app-gold',
  compra_cerca: 'border-app-teal/40 text-app-teal',
}

export default function Watchlist() {
  const navigate = useNavigate()
  const { umbralProximidad } = useInversionesContext()
  const [searchParams, setSearchParams] = useSearchParams()
  const filtro: Filtro = searchParams.get('alerta') === 'con_alerta' ? 'con_alerta' : 'todas'

  const watchlistQuery = useQuery({
    queryKey: qk.watchlist,
    queryFn: () => getWatchlist(),
  })
  const items = watchlistQuery.data ?? []

  const conEstado = useMemo(
    () => items.map(item => ({ item, estado: estadoWatchlist(item, umbralProximidad) })),
    [items, umbralProximidad],
  )

  const conteoConAlerta = conEstado.filter(({ estado }) => estado !== null).length

  const filtrados = filtro === 'con_alerta' ? conEstado.filter(({ estado }) => estado !== null) : conEstado

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
      </div>

      <QueryBoundary
        isLoading={watchlistQuery.isLoading}
        error={watchlistQuery.error}
        onRetry={() => void watchlistQuery.refetch()}
      >
        {items.length === 0 ? (
          <EmptyState
            title="No hay watchlist cargada"
            description='Agregá una pestaña "Watchlist" al Sheet con las columnas Ticker, Nombre, Tipo Instrumento, Mercado, Moneda, País, Sector y Objetivo, y sincronizá.'
          />
        ) : filtrados.length === 0 ? (
          <EmptyState title="Ningún instrumento cerca de su zona de compra" />
        ) : (
          <div>
            {filtrados.map(({ item, estado }) => {
              const irADetalle = item.en_cartera
              return (
                <button
                  key={item.ticker}
                  onClick={() => irADetalle && navigate(`/ticker/${encodeURIComponent(item.ticker)}`)}
                  className={`w-full flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0 text-left ${irADetalle ? '' : 'cursor-default'}`}
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
                  {irADetalle && <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90 shrink-0" />}
                </button>
              )
            })}
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
