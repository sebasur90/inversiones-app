import { useEffect, useState } from 'react'
import { useNavigate, useParams, Navigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getPreciosTicker, getDescomposicionFxPorPosicion, type PrecioPunto, type DescomposicionFxPosicionItem } from '../api'
import { formatARS, formatCantidad, formatPctRatio, formatPrecio, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Sparkline from '../components/charts/Sparkline'
import Button from '../components/ui/Button'
import { Icon } from '../components/icons/Icons'
import InfoTerm from '../components/ui/InfoTerm'
import type { GlosarioKey } from '../data/glosario'

export default function TickerDetalle() {
  const { ticker: tickerParam } = useParams<{ ticker: string }>()
  const navigate = useNavigate()
  const { carteraSeleccionada, rendimientoPorTicker, monedaSeleccionada, loading } = useInversionesContext()
  const [precios, setPrecios] = useState<PrecioPunto[]>([])
  const [descomposicionFxPorTicker, setDescomposicionFxPorTicker] = useState<DescomposicionFxPosicionItem | null>(null)

  const ticker = tickerParam ? decodeURIComponent(tickerParam) : ''
  const item = rendimientoPorTicker.find(i => i.ticker === ticker)

  useEffect(() => {
    if (!ticker) return
    let cancelado = false
    Promise.all([
      getPreciosTicker(ticker),
      getDescomposicionFxPorPosicion(carteraSeleccionada),
    ])
      .then(([preciosOut, fxData]) => {
        if (!cancelado) {
          setPrecios(preciosOut.puntos)
          const fxPorTicker = fxData.posiciones.find(p => p.ticker === ticker)
          setDescomposicionFxPorTicker(fxPorTicker || null)
        }
      })
      .catch(() => {
        if (!cancelado) {
          setPrecios([])
          setDescomposicionFxPorTicker(null)
        }
      })
    return () => {
      cancelado = true
    }
  }, [ticker, carteraSeleccionada])

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Ticker" onBack={() => navigate(-1)} />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (!item) {
    return <Navigate to="/posiciones" replace />
  }

  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD
  const valorInvertido = esARS ? item.valor_invertido_ars : item.valor_invertido_usd
  const valorActual = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const rendimiento = esARS ? item.rendimiento_simple_ars : item.rendimiento_simple_usd
  const positivo = (rendimiento ?? 0) >= 0

  return (
    <div className="pb-4">
      <ScreenHeader title={item.ticker} onBack={() => navigate(-1)} />

      <div className="flex items-center gap-3 mb-1">
        <div className="w-[46px] h-[46px] rounded-2xl bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-[12px] font-bold text-app-text shrink-0">
          {item.ticker.slice(0, 4)}
        </div>
        <div className="min-w-0">
          <div className="font-display text-[19px] font-semibold text-app-text truncate">{item.ticker}</div>
          <div className="text-[11.5px] text-app-text-dim truncate">{item.nombre}</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 my-2.5">
        {[item.tipo_instrumento, item.mercado, item.moneda, item.pais, item.sector].filter(Boolean).map(tag => (
          <span key={tag} className="text-[10px] font-semibold text-app-text-dim bg-app-surface-2 border border-app-border px-2 py-1 rounded-[7px]">
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-3">
        <div className="font-mono text-[26px] font-bold text-app-text tabular-nums">{formatPrecio(item.precio_actual)}</div>
        {rendimiento != null && (
          <span className={`inline-flex items-center gap-0.5 font-mono font-bold text-[12px] mt-1 tabular-nums ${positivo ? 'text-app-teal' : 'text-app-coral'}`}>
            <Icon name={positivo ? 'up' : 'down'} className="w-3 h-3" />
            {formatPctRatio(rendimiento)} desde promedio
          </span>
        )}
        {(item.objetivo_alcanzado || item.stop_loss_disparado) && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {item.objetivo_alcanzado && (
              <span className="text-[10.5px] font-bold text-app-teal bg-app-teal/10 border border-app-teal/30 px-2 py-1 rounded-[7px]">
                🎯 Objetivo alcanzado
              </span>
            )}
            {item.stop_loss_disparado && (
              <span className="text-[10.5px] font-bold text-app-coral bg-app-coral/10 border border-app-coral/30 px-2 py-1 rounded-[7px]">
                🛑 Stop loss disparado
              </span>
            )}
          </div>
        )}
        <Sparkline
          data={precios.map(p => p.precio)}
          color={positivo ? '#4fd1ae' : '#e2665a'}
          className="w-full h-14 mt-2.5"
        />
      </div>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <StatCell label="Cantidad" value={formatCantidad(item.cantidad_actual)} />
        <StatCell label="Precio promedio" value={formatPrecio(item.precio_promedio)} />
        <StatCell label="Invertido" infoTerm="invertido" value={formatMoneda(valorInvertido)} />
        <StatCell label="Valor actual" value={formatMoneda(valorActual)} />
        <StatCell label="Rend. simple" infoTerm="simple" value={formatPctRatio(rendimiento)} tone={rendimiento == null ? undefined : positivo ? 'pos' : 'neg'} />
        {esARS && item.rendimiento_simple_ars_real != null && (
          <StatCell label="Rend. ARS real" value={formatPctRatio(item.rendimiento_simple_ars_real)} tone={item.rendimiento_simple_ars_real >= 0 ? 'pos' : 'neg'} />
        )}
        {descomposicionFxPorTicker && descomposicionFxPorTicker.estado === 'ok' && (
          <>
            <StatCell
              label="Efecto FX"
              infoTerm="efecto_fx"
              value={formatPctRatio(descomposicionFxPorTicker.efecto_fx_pct)}
              tone={descomposicionFxPorTicker.efecto_fx_pct == null ? undefined : descomposicionFxPorTicker.efecto_fx_pct >= 0 ? 'pos' : 'neg'}
            />
            <StatCell
              label="Retorno activo"
              infoTerm="retorno_activo"
              value={formatPctRatio(descomposicionFxPorTicker.retorno_activo_pct)}
              tone={descomposicionFxPorTicker.retorno_activo_pct == null ? undefined : descomposicionFxPorTicker.retorno_activo_pct >= 0 ? 'pos' : 'neg'}
            />
          </>
        )}
        {item.precio_objetivo != null && (
          <StatCell
            label="Precio Objetivo"
            infoTerm="objetivo"
            value={formatPrecio(item.precio_objetivo)}
            sub={item.pct_a_objetivo != null ? `${item.pct_a_objetivo >= 0 ? 'falta' : 'superado por'} ${(Math.abs(item.pct_a_objetivo) * 100).toFixed(2)}%` : undefined}
            tone={item.objetivo_alcanzado ? 'pos' : undefined}
          />
        )}
        {item.precio_stop_loss != null && (
          <StatCell
            label="Stop Loss"
            infoTerm="stopLoss"
            value={formatPrecio(item.precio_stop_loss)}
            sub={item.pct_a_stop_loss != null ? `${item.pct_a_stop_loss <= 0 ? 'superado por' : 'falta'} ${(Math.abs(item.pct_a_stop_loss) * 100).toFixed(2)}%` : undefined}
            tone={item.stop_loss_disparado ? 'neg' : undefined}
          />
        )}
      </div>

      <Button variant="outline" icon={<Icon name="list" className="w-4 h-4" />} className="w-full mt-4" onClick={() => navigate(`/movimientos?ticker=${encodeURIComponent(item.ticker)}`)}>
        Ver movimientos de {item.ticker}
      </Button>
    </div>
  )
}

function StatCell({ label, infoTerm, value, sub, tone }: { label: string; infoTerm?: GlosarioKey; value: string; sub?: string; tone?: 'pos' | 'neg' }) {
  return (
    <div className="bg-app-surface border border-app-border rounded-[13px] p-2.5">
      <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
        {infoTerm ? <InfoTerm term={infoTerm} label={label} /> : label}
      </div>
      <div className={`font-mono text-[14.5px] font-bold tabular-nums ${tone === 'pos' ? 'text-app-teal' : tone === 'neg' ? 'text-app-coral' : 'text-app-text'}`}>{value}</div>
      {sub && <div className="text-[10px] text-app-text-dim mt-0.5">{sub}</div>}
    </div>
  )
}
