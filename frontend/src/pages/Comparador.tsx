import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import {
  getTickersConPrecios, getPreciosHistoricos,
  type TickerConPrecio, type PrecioHistoricoOut, type PrecioHistoricoPunto,
} from '../api'
import { CHART_COLORS } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import Card from '../components/ui/Card'
import InfoTooltip from '../help/components/InfoTooltip'
import SkeletonPantalla, { Skeleton } from '../components/ui/Skeleton'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../api/queryClient'

type Vista = 'nominal' | 'usd' | 'cer'

const MAX_TICKERS = 5

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

function valorEnVista(punto: PrecioHistoricoPunto, vista: Vista): number | null {
  if (vista === 'nominal') return punto.precio_nominal
  if (vista === 'usd') return punto.precio_usd
  return punto.precio_cer
}

type Fila = { fecha: string } & Record<string, string | number | null>

function mergeSeries(series: PrecioHistoricoOut[], vista: Vista): Fila[] {
  const fechas = Array.from(new Set(series.flatMap(s => s.puntos.map(p => p.fecha)))).sort()
  const mapas = series.map(s => new Map(s.puntos.map(p => [p.fecha, valorEnVista(p, vista)])))
  return fechas.map(fecha => {
    const fila: Fila = { fecha }
    series.forEach((s, i) => {
      fila[s.ticker] = mapas[i].get(fecha) ?? null
    })
    return fila
  })
}

function aBase100(filas: Fila[], tickers: string[]): Fila[] {
  const base: Record<string, number | null> = {}
  for (const t of tickers) {
    const primera = filas.find(f => f[t] != null)
    base[t] = primera ? (primera[t] as number) : null
  }
  return filas.map(fila => {
    const out: Fila = { fecha: fila.fecha }
    for (const t of tickers) {
      const b = base[t]
      const v = fila[t]
      out[t] = v != null && b ? (Number(v) / b) * 100 : null
    }
    return out
  })
}

function formatValor(v: number, vista: Vista, normalizado: boolean): string {
  if (normalizado) return v.toFixed(1)
  const num = v.toLocaleString('es-AR', { maximumFractionDigits: 2 })
  return vista === 'usd' ? `U$S ${num}` : num
}

export default function Comparador() {
  const navigate = useNavigate()
  const [tickersSel, setTickersSel] = useState<string[]>([])
  const [vista, setVista] = useState<Vista>('usd')
  const [normalizado, setNormalizado] = useState(true)

  const tickersQuery = useQuery({
    queryKey: qk.de('tickers-con-precios'),
    queryFn: () => getTickersConPrecios(),
  })
  const tickers: TickerConPrecio[] = tickersQuery.data ?? []
  const loading = tickersQuery.isLoading

  // Las series de cada ticker se cachean por separado: agregar un sexto ticker no vuelve a
  // pedir los cinco que ya estaban.
  const seriesQuery = useQuery({
    queryKey: qk.de('precios-historicos-multi', [...tickersSel].sort()),
    queryFn: () => Promise.all(tickersSel.map(t => getPreciosHistoricos(t))),
    enabled: tickersSel.length > 0,
  })
  const series: PrecioHistoricoOut[] = tickersSel.length === 0 ? [] : seriesQuery.data ?? []
  const loadingChart = tickersSel.length > 0 && seriesQuery.isLoading

  const monedasSel = useMemo(
    () => new Set(tickers.filter(t => tickersSel.includes(t.ticker)).map(t => t.moneda)),
    [tickers, tickersSel],
  )

  const opcionesVista = useMemo(() => {
    const opts: { value: Vista; label: string }[] = [{ value: 'usd', label: 'USD (MEP)' }]
    if (monedasSel.size <= 1) opts.unshift({ value: 'nominal', label: 'Nominal' })
    if (monedasSel.size === 1 && monedasSel.has('ARS')) opts.push({ value: 'cer', label: 'ARS Real (CER)' })
    return opts
  }, [monedasSel])

  useEffect(() => {
    if (!opcionesVista.some(o => o.value === vista)) setVista(opcionesVista[0]?.value ?? 'usd')
  }, [opcionesVista, vista])

  const datosGrafico = useMemo(() => {
    const merged = mergeSeries(series, vista)
    return normalizado ? aBase100(merged, tickersSel) : merged
  }, [series, vista, normalizado, tickersSel])

  function toggleTicker(ticker: string) {
    setTickersSel(prev => {
      if (prev.includes(ticker)) return prev.filter(t => t !== ticker)
      if (prev.length >= MAX_TICKERS) return prev
      return [...prev, ticker]
    })
  }

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Comparador" onBack={() => navigate(-1)} />
        <SkeletonPantalla />
      </div>
    )
  }

  if (tickers.length === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Comparador" onBack={() => navigate(-1)} />
        <EmptyState title="Sin precios cargados" description="Sincronizá el sheet para poder comparar tickers." />
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Comparador" onBack={() => navigate(-1)} />

      <div className="text-label text-app-text-dim mb-2">Elegí hasta {MAX_TICKERS} tickers para comparar</div>

      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-2 mb-3 -mx-4 px-4">
        {tickers.map(t => {
          const activo = tickersSel.includes(t.ticker)
          return (
            <button
              key={t.ticker}
              onClick={() => toggleTicker(t.ticker)}
              disabled={!activo && tickersSel.length >= MAX_TICKERS}
              className={`shrink-0 font-semibold text-caption px-3 py-1.5 rounded-[10px] border transition-colors disabled:opacity-40 ${
                activo
                  ? 'bg-app-gold-soft border-app-gold text-app-gold'
                  : 'bg-app-surface border-app-border text-app-text-dim'
              }`}
            >
              {t.ticker}
            </button>
          )
        })}
      </div>

      {tickersSel.length === 0 ? (
        <EmptyState title="Elegí al menos un ticker" description="Tocá los chips de arriba para agregarlos a la comparación." />
      ) : (
        <>
          <div className="px-4 mb-4 pt-2">
            <div className="text-caption text-app-text-dim space-y-1.5 mb-3">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-app-text">USD (MEP)</span>
                <InfoTooltip term="precios_usd_mep" />
              </div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-app-text">ARS Real (CER)</span>
                <InfoTooltip term="precios_ars_real_cer" />
              </div>
              {monedasSel.size <= 1 && (
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-app-text">Nominal</span>
                  <InfoTooltip term="comparador_nominal" />
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 mb-3">
            <Segmented options={opcionesVista} value={vista} onChange={setVista} />
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setNormalizado(v => !v)}
                className={`shrink-0 font-semibold text-label px-2.5 py-1.5 rounded-lg border ${
                  normalizado ? 'bg-app-gold-soft border-app-gold text-app-gold' : 'bg-app-surface border-app-border text-app-text-dim'
                }`}
              >
                Base 100
              </button>
              <InfoTooltip term="comparador_base100" />
            </div>
          </div>

          <Card>
            {loadingChart ? (
              <Skeleton className="h-[240px] rounded-xl" />
            ) : datosGrafico.length === 0 ? (
              <div className="h-[240px] flex items-center justify-center text-app-text-dim text-caption">Sin datos para esta vista</div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
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
                    tickFormatter={v => formatValor(v, vista, normalizado)}
                  />
                  <Tooltip
                    contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
                    labelStyle={{ color: '#edf2ef' }}
                    formatter={(v: number) => formatValor(v, vista, normalizado)}
                    labelFormatter={formatFechaTooltip}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#8ca39b' }} />
                  {tickersSel.map((ticker, i) => (
                    <Line
                      key={ticker}
                      type="monotone"
                      dataKey={ticker}
                      stroke={CHART_COLORS[i % CHART_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
