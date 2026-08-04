import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  getTickersConPrecios, getPreciosHistoricos,
  type TickerConPrecio, type PrecioHistoricoOut,
} from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import { Icon } from '../components/icons/Icons'

type Vista = 'nominal' | 'usd' | 'cer'

function formatCompact(v: number, esUSD: boolean): string {
  const abs = Math.abs(v)
  if (esUSD) {
    if (abs >= 1_000_000) return `U$S ${(v / 1_000_000).toFixed(1)}M`
    if (abs >= 1000) return `U$S ${(v / 1000).toFixed(0)}K`
    return `U$S ${v.toFixed(2)}`
  }
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (abs >= 1000) return `$${(v / 1000).toFixed(0)}K`
  return `$${v.toFixed(0)}`
}

function formatFechaLabel(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const mes = (d.getMonth() + 1).toString().padStart(2, '0')
  const anio = d.getFullYear().toString().slice(2)
  return `${mes}/${anio}`
}

function formatFechaTooltip(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function Precios() {
  const navigate = useNavigate()
  const [tickers, setTickers] = useState<TickerConPrecio[]>([])
  const [tickerSel, setTickerSel] = useState<string | null>(null)
  const [datos, setDatos] = useState<PrecioHistoricoOut | null>(null)
  const [vista, setVista] = useState<Vista>('nominal')
  const [loading, setLoading] = useState(true)
  const [loadingChart, setLoadingChart] = useState(false)

  useEffect(() => {
    getTickersConPrecios()
      .then(data => {
        setTickers(data)
        if (data.length > 0) setTickerSel(data[0].ticker)
      })
      .catch(() => setTickers([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!tickerSel) return
    setLoadingChart(true)
    setDatos(null)
    getPreciosHistoricos(tickerSel)
      .then(data => {
        setDatos(data)
        setVista('nominal')
      })
      .catch(() => setDatos(null))
      .finally(() => setLoadingChart(false))
  }, [tickerSel])

  const instrumento = tickers.find(t => t.ticker === tickerSel)
  const esARS = instrumento?.moneda === 'ARS'

  const opcionesVista: { value: Vista; label: string }[] = esARS
    ? [
        { value: 'nominal', label: 'ARS Nominal' },
        { value: 'usd',     label: 'USD (MEP)'   },
        { value: 'cer',     label: 'ARS Real (CER)' },
      ]
    : [
        { value: 'nominal', label: 'USD Nominal' },
        { value: 'cer',     label: 'ARS (MEP)'   },
      ]

  // Determinar si la vista actual se muestra en USD
  const vistaEsUSD = vista === 'usd' || (vista === 'nominal' && !esARS)

  const datosGrafico = (datos?.puntos ?? []).map(p => {
    const valor =
      vista === 'nominal' ? p.precio_nominal :
      vista === 'usd'     ? p.precio_usd :
                            p.precio_cer
    return { fecha: p.fecha, valor }
  }).filter(p => p.valor != null) as { fecha: string; valor: number }[]

  const colorLinea =
    vista === 'usd' || (vista === 'nominal' && !esARS) ? '#4fd1ae' :
    vista === 'cer'                                    ? '#9c7aa0' :
                                                         '#d8b14a'

  const ultimoPunto = datosGrafico.length > 0 ? datosGrafico[datosGrafico.length - 1] : undefined

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Precios" />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (tickers.length === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Precios" />
        <EmptyState title="Sin precios cargados" description="Sincronizá el sheet para ver la evolución de precios." />
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Precios" />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
        <button onClick={() => navigate('/indicadores')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Indicadores macro (CER/MEP)
        </button>
        <button onClick={() => navigate('/comparar')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Comparar varios tickers
        </button>
      </div>

      {/* Selector de ticker */}
      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-2 mb-3 -mx-4 px-4">
        {tickers.map(t => (
          <button
            key={t.ticker}
            onClick={() => setTickerSel(t.ticker)}
            className={`shrink-0 font-semibold text-[11.5px] px-3 py-1.5 rounded-[10px] border transition-colors ${
              t.ticker === tickerSel
                ? 'bg-app-gold-soft border-app-gold text-app-gold'
                : 'bg-app-surface border-app-border text-app-text-dim'
            }`}
          >
            {t.ticker}
          </button>
        ))}
      </div>

      {/* Info del instrumento + último precio */}
      {instrumento && (
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="font-semibold text-[15px] text-app-text">{instrumento.ticker}</div>
            <div className="text-[11.5px] text-app-text-dim">{instrumento.nombre}</div>
          </div>
          {ultimoPunto && (
            <div className="text-right shrink-0 ml-4">
              <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Último registro</div>
              <div className="font-mono font-bold text-[15px] text-app-text tabular-nums">
                {formatCompact(ultimoPunto.valor, vistaEsUSD)}
              </div>
              <div className="text-[10px] text-app-text-dim">{formatFechaTooltip(ultimoPunto.fecha)}</div>
            </div>
          )}
        </div>
      )}

      {/* Selector de vista */}
      <div className="mb-3">
        <Segmented options={opcionesVista} value={vista} onChange={setVista} />
      </div>

      {/* Gráfico */}
      {loadingChart ? (
        <div className="h-[220px] flex items-center justify-center text-app-text-dim text-[12.5px]">
          Cargando…
        </div>
      ) : datosGrafico.length === 0 ? (
        <div className="h-[220px] flex items-center justify-center text-app-text-dim text-[12.5px]">
          Sin datos para esta vista
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
            <XAxis
              dataKey="fecha"
              stroke="#8ca39b"
              tick={{ fontSize: 10, fill: '#8ca39b' }}
              tickFormatter={formatFechaLabel}
              interval="preserveStartEnd"
            />
            <YAxis
              stroke="#8ca39b"
              tick={{ fontSize: 10, fill: '#8ca39b' }}
              width={62}
              tickFormatter={v => formatCompact(v, vistaEsUSD)}
            />
            <Tooltip
              contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: '#edf2ef' }}
              formatter={(v: number) => [formatCompact(v, vistaEsUSD), 'Precio']}
              labelFormatter={formatFechaTooltip}
              cursor={{ stroke: colorLinea, strokeWidth: 1 }}
            />
            <Line
              type="monotone"
              dataKey="valor"
              stroke={colorLinea}
              strokeWidth={2}
              dot={{ r: 3.5, fill: colorLinea, strokeWidth: 0 }}
              activeDot={{ r: 5, fill: colorLinea }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {datos && datos.puntos.length > 0 && (
        <div className="mt-2 text-[10.5px] text-app-text-dim">
          {datos.puntos.length} registro{datos.puntos.length !== 1 ? 's' : ''} cargados
          {' · '}desde {formatFechaTooltip(datos.puntos[0].fecha)}
        </div>
      )}
    </div>
  )
}
