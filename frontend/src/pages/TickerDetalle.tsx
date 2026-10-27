import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { useInversionesContext } from '../context/InversionesContext'
import { getAnalisisTicker, getRiesgoTicker, getHistoricoTicker } from '../api'
import AvatarTicker from '../components/ui/AvatarTicker'
import EmptyState from '../components/ui/EmptyState'
import ScreenHeader from '../components/layout/ScreenHeader'
import Button from '../components/ui/Button'
import Segmented from '../components/ui/Segmented'
import { Icon } from '../components/icons/Icons'
import TickerResumenTab from './ticker/TickerResumenTab'
import TickerRendimientoTab from './ticker/TickerRendimientoTab'
import TickerRiesgoTab from './ticker/TickerRiesgoTab'
import TickerHistoricoTab from './ticker/TickerHistoricoTab'
import TickerParesTab from './ticker/TickerParesTab'
import SkeletonPantalla from '../components/ui/Skeleton'
import { qk } from '../api/queryClient'

type TabKey = 'resumen' | 'rendimiento' | 'riesgo' | 'historico' | 'pares'

export default function TickerDetalle() {
  const { ticker: tickerParam } = useParams<{ ticker: string }>()
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()

  const [searchParams] = useSearchParams()
  const TABS: TabKey[] = ['resumen', 'rendimiento', 'riesgo', 'historico', 'pares']
  const tabInicial = searchParams.get('tab') as TabKey | null
  const [tab, setTab] = useState<TabKey>(tabInicial && TABS.includes(tabInicial) ? tabInicial : 'resumen')

  const ticker = tickerParam ? decodeURIComponent(tickerParam) : ''
  const monedaBackend = monedaSeleccionada === 'ARS' ? 'ars_nominal' : 'usd'

  const analisisQuery = useQuery({
    queryKey: qk.de('ticker-analisis', ticker, carteraSeleccionada),
    queryFn: () => getAnalisisTicker(ticker, carteraSeleccionada),
    enabled: ticker !== '',
  })

  // Las pestañas de riesgo e histórico se piden recién al abrirlas, y una vez pedidas quedan
  // cacheadas: volver a la pestaña ya no dispara otro fetch.
  const riesgoQuery = useQuery({
    queryKey: qk.de('ticker-riesgo', ticker, carteraSeleccionada, monedaBackend),
    queryFn: () => getRiesgoTicker(ticker, carteraSeleccionada, monedaBackend),
    enabled: ticker !== '' && tab === 'riesgo',
  })
  const historicoQuery = useQuery({
    queryKey: qk.de('ticker-historico', ticker, carteraSeleccionada),
    queryFn: () => getHistoricoTicker(ticker, carteraSeleccionada),
    enabled: ticker !== '' && tab === 'historico',
  })

  const analisis = analisisQuery.data ?? null
  const riesgo = riesgoQuery.data ?? null
  const historico = historicoQuery.data ?? null
  const loading = analisisQuery.isLoading
  const loadingRiesgo = riesgoQuery.isLoading && tab === 'riesgo'
  const loadingHistorico = historicoQuery.isLoading && tab === 'historico'
  const error = analisisQuery.error ? 'Ticker no encontrado' : null

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ticker" onBack={() => navigate(-1)} />
        <SkeletonPantalla />
      </div>
    )
  }

  // 404 = el ticker no está en la planilla (viene del catálogo, de la watchlist o de un par): no hay
  // posición ni rendimiento propios que mostrar, pero la comparación contra pares sí existe.
  const fueraDeLaPlanilla = isAxiosError(analisisQuery.error) && analisisQuery.error.response?.status === 404

  if (fueraDeLaPlanilla) {
    return (
      <div className="pb-4">
        <ScreenHeader title={ticker} onBack={() => navigate(-1)} />
        <div className="flex items-center gap-3 mb-3">
          <AvatarTicker ticker={ticker} grande className="border-app-border text-app-text" />
          <div className="min-w-0">
            <div className="font-display text-heading font-semibold text-app-text truncate">{ticker}</div>
            <div className="text-caption text-app-text-dim">No está en tu cartera ni en tu planilla</div>
          </div>
        </div>
        <TickerParesTab ticker={ticker} />
      </div>
    )
  }

  if (error || !analisis) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ticker" onBack={() => navigate(-1)} />
        <EmptyState
          ilustracion="lupa"
          emoji="😕"
          title={error || 'Ticker no encontrado'}
          description="Puede que ya no esté en tu planilla o que el ticker esté mal escrito."
          action={
            <Button variant="outline" icon={<Icon name="back" className="w-4 h-4" />} onClick={() => navigate(-1)}>
              Volver
            </Button>
          }
        />
      </div>
    )
  }

  const { position, performance } = analisis

  return (
    <div className="pb-4">
      <ScreenHeader title={position.ticker} onBack={() => navigate(-1)} />

      <div className="flex items-center gap-3 mb-1">
        <AvatarTicker ticker={position.ticker} grande className="border-app-border text-app-text" />
        <div className="min-w-0">
          <div className="font-display text-heading font-semibold text-app-text truncate">{position.ticker}</div>
          <div className="text-caption text-app-text-dim truncate">{position.nombre}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 my-2.5">
        {[position.tipo_instrumento, position.mercado, position.moneda, position.pais, position.sector].filter(Boolean).map(tag => (
          <span key={tag} className="text-label font-semibold text-app-text-dim bg-app-surface-2 border border-app-border px-2.5 py-1 rounded-full">
            {tag}
          </span>
        ))}
      </div>

      <div className="my-3">
        <Segmented
          options={[
            { label: 'Resumen', value: 'resumen' },
            { label: 'Rendimiento', value: 'rendimiento' },
            { label: 'Riesgo', value: 'riesgo' },
            { label: 'Histórico', value: 'historico' },
            { label: 'Pares', value: 'pares' },
          ]}
          value={tab}
          onChange={v => setTab(v as TabKey)}
        />
      </div>

      {tab === 'resumen' && <TickerResumenTab position={position} cartera={carteraSeleccionada} monedaSeleccionada={monedaSeleccionada} />}

      {tab === 'rendimiento' && <TickerRendimientoTab performance={performance} position={position} monedaSeleccionada={monedaSeleccionada} />}

      {tab === 'riesgo' && (
        loadingRiesgo ? (
          <SkeletonPantalla />
        ) : riesgo ? (
          <TickerRiesgoTab riesgo={riesgo} />
        ) : (
          <EmptyState ilustracion="lupa" title="No hay datos disponibles" description="Todavía no hay historia suficiente para este ticker." />
        )
      )}

      {tab === 'historico' && (
        loadingHistorico ? (
          <SkeletonPantalla />
        ) : historico ? (
          <TickerHistoricoTab historico={historico} monedaSeleccionada={monedaSeleccionada} />
        ) : (
          <EmptyState ilustracion="lupa" title="No hay datos disponibles" description="Todavía no hay historia suficiente para este ticker." />
        )
      )}

      {tab === 'pares' && <TickerParesTab ticker={ticker} />}

      <Button variant="outline" icon={<Icon name="swap" className="w-4 h-4" />} className="w-full mt-4" onClick={() => navigate(`/movimientos?ticker=${encodeURIComponent(position.ticker)}`)}>
        Ver movimientos de {position.ticker}
      </Button>
      <Button variant="outline" icon={<Icon name="calendarDays" className="w-4 h-4" />} className="w-full mt-2" onClick={() => navigate(`/eventos?tab=impacto&ticker=${encodeURIComponent(position.ticker)}`)}>
        Eventos de {position.ticker}
      </Button>
    </div>
  )
}
