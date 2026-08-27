import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getAnalisisTicker, getRiesgoTicker, getHistoricoTicker, type TickerAnalysisOut, type TickerRiesgoOut, type TickerHistoricoOut } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Button from '../components/ui/Button'
import Segmented from '../components/ui/Segmented'
import { Icon } from '../components/icons/Icons'
import TickerResumenTab from './ticker/TickerResumenTab'
import TickerRendimientoTab from './ticker/TickerRendimientoTab'
import TickerRiesgoTab from './ticker/TickerRiesgoTab'
import TickerHistoricoTab from './ticker/TickerHistoricoTab'

type TabKey = 'resumen' | 'rendimiento' | 'riesgo' | 'historico'

export default function TickerDetalle() {
  const { ticker: tickerParam } = useParams<{ ticker: string }>()
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, syncVersion } = useInversionesContext()

  const [tab, setTab] = useState<TabKey>('resumen')
  const [analisis, setAnalisis] = useState<TickerAnalysisOut | null>(null)
  const [riesgo, setRiesgo] = useState<TickerRiesgoOut | null>(null)
  const [historico, setHistorico] = useState<TickerHistoricoOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingRiesgo, setLoadingRiesgo] = useState(false)
  const [loadingHistorico, setLoadingHistorico] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ticker = tickerParam ? decodeURIComponent(tickerParam) : ''

  // Eager load: análisis (position + performance)
  useEffect(() => {
    if (!ticker) return
    let cancelado = false
    setLoading(true)
    setError(null)

    getAnalisisTicker(ticker, carteraSeleccionada)
      .then(data => {
        if (!cancelado) {
          setAnalisis(data)
          setError(null)
        }
      })
      .catch(() => {
        if (!cancelado) {
          setAnalisis(null)
          setError('Ticker no encontrado')
        }
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })

    return () => {
      cancelado = true
    }
  }, [ticker, carteraSeleccionada, syncVersion])

  // Lazy load: riesgo
  useEffect(() => {
    if (tab !== 'riesgo' || !ticker || riesgo) return
    let cancelado = false
    setLoadingRiesgo(true)

    const monedaBackend = monedaSeleccionada === 'ARS' ? 'ars_nominal' : 'usd'
    getRiesgoTicker(ticker, carteraSeleccionada, monedaBackend)
      .then(data => {
        if (!cancelado) {
          setRiesgo(data)
        }
      })
      .catch(() => {
        if (!cancelado) {
          setRiesgo(null)
        }
      })
      .finally(() => {
        if (!cancelado) setLoadingRiesgo(false)
      })

    return () => {
      cancelado = true
    }
  }, [tab, ticker, carteraSeleccionada, monedaSeleccionada, syncVersion])

  // Lazy load: historico
  useEffect(() => {
    if (tab !== 'historico' || !ticker || historico) return
    let cancelado = false
    setLoadingHistorico(true)

    getHistoricoTicker(ticker, carteraSeleccionada)
      .then(data => {
        if (!cancelado) {
          setHistorico(data)
        }
      })
      .catch(() => {
        if (!cancelado) {
          setHistorico(null)
        }
      })
      .finally(() => {
        if (!cancelado) setLoadingHistorico(false)
      })

    return () => {
      cancelado = true
    }
  }, [tab, ticker, carteraSeleccionada, syncVersion])

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ticker" onBack={() => navigate(-1)} />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (error || !analisis) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ticker" onBack={() => navigate(-1)} />
        <div className="py-8 px-4 text-center">
          <div className="text-app-text-dim text-[13px] mb-4">{error || 'Ticker no encontrado'}</div>
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
        <div className="w-[46px] h-[46px] rounded-2xl bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-[12px] font-bold text-app-text shrink-0">
          {position.ticker.slice(0, 4)}
        </div>
        <div className="min-w-0">
          <div className="font-display text-[19px] font-semibold text-app-text truncate">{position.ticker}</div>
          <div className="text-[11.5px] text-app-text-dim truncate">{position.nombre}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 my-2.5">
        {[position.tipo_instrumento, position.mercado, position.moneda, position.pais, position.sector].filter(Boolean).map(tag => (
          <span key={tag} className="text-[10px] font-semibold text-app-text-dim bg-app-surface-2 border border-app-border px-2 py-1 rounded-[7px]">
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
          <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
        ) : riesgo ? (
          <TickerRiesgoTab riesgo={riesgo} />
        ) : (
          <div className="py-8 text-center text-app-text-dim text-[13px]">No hay datos disponibles</div>
        )
      )}

      {tab === 'historico' && (
        loadingHistorico ? (
          <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
        ) : historico ? (
          <TickerHistoricoTab historico={historico} monedaSeleccionada={monedaSeleccionada} />
        ) : (
          <div className="py-8 text-center text-app-text-dim text-[13px]">No hay datos disponibles</div>
        )
      )}

      <Button variant="outline" icon={<Icon name="list" className="w-4 h-4" />} className="w-full mt-4" onClick={() => navigate(`/movimientos?ticker=${encodeURIComponent(position.ticker)}`)}>
        Ver movimientos de {position.ticker}
      </Button>
    </div>
  )
}
