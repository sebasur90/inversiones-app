import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getAnalisisTicker, getRiesgoTicker, getHistoricoTicker } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Button from '../components/ui/Button'
import Segmented from '../components/ui/Segmented'
import { Icon } from '../components/icons/Icons'
import TickerResumenTab from './ticker/TickerResumenTab'
import TickerRendimientoTab from './ticker/TickerRendimientoTab'
import TickerRiesgoTab from './ticker/TickerRiesgoTab'
import TickerHistoricoTab from './ticker/TickerHistoricoTab'
import SkeletonPantalla from '../components/ui/Skeleton'
import { qk } from '../api/queryClient'

type TabKey = 'resumen' | 'rendimiento' | 'riesgo' | 'historico'

export default function TickerDetalle() {
  const { ticker: tickerParam } = useParams<{ ticker: string }>()
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()

  const [tab, setTab] = useState<TabKey>('resumen')

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

  if (error || !analisis) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ticker" onBack={() => navigate(-1)} />
        <div className="py-8 px-4 text-center">
          <div className="text-app-text-dim text-body mb-4">{error || 'Ticker no encontrado'}</div>
          <Button variant="outline" onClick={() => navigate(-1)}>
            Volver
          </Button>
        </div>
      </div>
    )
  }

  const { position, performance } = analisis

  return (
    <div className="pb-4">
      <ScreenHeader title={position.ticker} onBack={() => navigate(-1)} />

      <div className="flex items-center gap-3 mb-1">
        <div className="w-[46px] h-[46px] rounded-2xl bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-caption font-bold text-app-text shrink-0">
          {position.ticker.slice(0, 4)}
        </div>
        <div className="min-w-0">
          <div className="font-display text-heading font-semibold text-app-text truncate">{position.ticker}</div>
          <div className="text-caption text-app-text-dim truncate">{position.nombre}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 my-2.5">
        {[position.tipo_instrumento, position.mercado, position.moneda, position.pais, position.sector].filter(Boolean).map(tag => (
          <span key={tag} className="text-label font-semibold text-app-text-dim bg-app-surface-2 border border-app-border px-2 py-1 rounded-[7px]">
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
          <div className="py-8 text-center text-app-text-dim text-body">No hay datos disponibles</div>
        )
      )}

      {tab === 'historico' && (
        loadingHistorico ? (
          <SkeletonPantalla />
        ) : historico ? (
          <TickerHistoricoTab historico={historico} monedaSeleccionada={monedaSeleccionada} />
        ) : (
          <div className="py-8 text-center text-app-text-dim text-body">No hay datos disponibles</div>
        )
      )}

      <Button variant="outline" icon={<Icon name="list" className="w-4 h-4" />} className="w-full mt-4" onClick={() => navigate(`/movimientos?ticker=${encodeURIComponent(position.ticker)}`)}>
        Ver movimientos de {position.ticker}
      </Button>
    </div>
  )
}
