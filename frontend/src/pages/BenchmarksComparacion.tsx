import { useState, useEffect } from 'react'
import {
  getPerformanceCompare,
  getOpportunityCost,
  getBenchmarksDisponibles,
  getTickersConPrecios,
  type PerformanceCompareOut,
  type OpportunityCostOut,
} from '../api'
import BenchmarkComparisonTable from '../components/inversiones/BenchmarkComparisonTable'
import PerformanceCompareChart from '../components/charts/PerformanceCompareChart'
import { formatUSD, formatARS } from '../utils'
import { Icon } from '../components/icons/Icons'

const calcularDesdeFromPeriod = (period: string): string | undefined => {
  const hoy = new Date()
  let desde: Date | null = null

  switch (period) {
    case '1m':
      desde = new Date(hoy.setMonth(hoy.getMonth() - 1))
      break
    case '3m':
      desde = new Date(hoy.setMonth(hoy.getMonth() - 3))
      break
    case '6m':
      desde = new Date(hoy.setMonth(hoy.getMonth() - 6))
      break
    case '1y':
      desde = new Date(hoy.setFullYear(hoy.getFullYear() - 1))
      break
    default:
      return undefined
  }

  return desde ? desde.toISOString().split('T')[0] : undefined
}

interface BenchmarksComparacionProps {
  cartera?: string | null
}

export default function BenchmarksComparacion({ cartera = null }: BenchmarksComparacionProps) {
  const [periodo, setPeriodo] = useState('1y')
  const [moneda, setMoneda] = useState<'usd' | 'ars_nominal' | 'ars_real'>('usd')
  const [benchmarks, setBenchmarks] = useState<string[]>([])
  const [tickers, setTickers] = useState<string[]>([])
  const [benchmarksDisponibles, setBenchmarksDisponibles] = useState<string[]>([])
  const [tickersConPrecios, setTickersConPrecios] = useState<string[]>([])
  const [performanceData, setPerformanceData] = useState<PerformanceCompareOut | null>(null)
  const [opportunityCostData, setOpportunityCostData] = useState<OpportunityCostOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('comparacion')

  useEffect(() => {
    Promise.all([getBenchmarksDisponibles(), getTickersConPrecios()])
      .then(([benchs, ticks]) => {
        setBenchmarksDisponibles(benchs)
        setTickersConPrecios(ticks.map(t => t.ticker))
        if (benchs.length > 0) {
          setBenchmarks(benchs.slice(0, 2))
        }
      })
      .catch(err => console.error('Error loading benchmarks/tickers:', err))
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const desde = calcularDesdeFromPeriod(periodo)
      const [perfData, oppData] = await Promise.all([
        getPerformanceCompare(cartera, moneda, desde, benchmarks, tickers),
        benchmarks.length > 0 ? getOpportunityCost(cartera, benchmarks[0], desde) : Promise.resolve(null),
      ])
      setPerformanceData(perfData)
      if (oppData) setOpportunityCostData(oppData)
    } catch (err) {
      console.error('Error loading performance data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (benchmarks.length > 0 || tickers.length > 0) {
      loadData()
    }
  }, [periodo, moneda, benchmarks, tickers])

  return (
    <div className="w-full">
      <h1 className="text-[18px] font-bold text-app-text mb-4">Comparación de Benchmarks</h1>

      <div className="bg-app-surface border border-app-border rounded-2xl p-4 mb-4">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] font-bold uppercase text-app-text-faint mb-2">Período</div>
              <div className="flex gap-1 flex-wrap">
                {['1m', '3m', '6m', '1y', 'all'].map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriodo(p)}
                    className={`px-2.5 py-1.5 rounded text-[11px] font-semibold ${
                      periodo === p
                        ? 'bg-app-teal text-app-bg'
                        : 'bg-app-border text-app-text-dim hover:text-app-text'
                    }`}
                  >
                    {p === '1m' ? '1m' : p === '3m' ? '3m' : p === '6m' ? '6m' : p === '1y' ? '1y' : 'Todo'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase text-app-text-faint mb-2">Moneda</div>
              <div className="flex gap-1 flex-wrap">
                {(['usd', 'ars_nominal', 'ars_real'] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMoneda(m)}
                    className={`px-2.5 py-1.5 rounded text-[11px] font-semibold ${
                      moneda === m
                        ? 'bg-app-teal text-app-bg'
                        : 'bg-app-border text-app-text-dim hover:text-app-text'
                    }`}
                  >
                    {m === 'usd' ? 'USD' : m === 'ars_nominal' ? 'ARS' : 'ARS Real'}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] font-bold uppercase text-app-text-faint mb-2">Benchmarks</div>
              <div className="flex flex-wrap gap-2">
                {benchmarksDisponibles.map((b) => (
                  <button
                    key={b}
                    onClick={() =>
                      setBenchmarks(benchmarks.includes(b)
                        ? benchmarks.filter(x => x !== b)
                        : [...benchmarks, b]
                      )
                    }
                    className={`px-2 py-1 rounded text-[11px] ${
                      benchmarks.includes(b)
                        ? 'bg-app-teal text-app-bg'
                        : 'bg-app-border text-app-text-dim'
                    }`}
                  >
                    {b}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase text-app-text-faint mb-2">Tickers</div>
              <div className="flex flex-wrap gap-2 max-h-12 overflow-y-auto">
                {tickersConPrecios.map((t) => (
                  <button
                    key={t}
                    onClick={() =>
                      setTickers(tickers.includes(t)
                        ? tickers.filter(x => x !== t)
                        : [...tickers, t]
                      )
                    }
                    className={`px-2 py-1 rounded text-[11px] whitespace-nowrap ${
                      tickers.includes(t)
                        ? 'bg-app-teal text-app-bg'
                        : 'bg-app-border text-app-text-dim'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-app-teal"></div>
        </div>
      )}

      {performanceData && !loading && (
        <>
          <div className="flex gap-2 mb-4 border-b border-app-border">
            {(['comparacion', 'oportunidad'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-2 text-[12px] font-semibold border-b-2 ${
                  activeTab === tab
                    ? 'border-app-teal text-app-teal'
                    : 'border-transparent text-app-text-dim hover:text-app-text'
                }`}
              >
                {tab === 'comparacion' ? 'Comparación' : 'Costo de Oportunidad'}
              </button>
            ))}
          </div>

          {activeTab === 'comparacion' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-[13px] font-bold text-app-text mb-3">Rendimientos</h3>
                <div className="bg-app-surface border border-app-border rounded-2xl p-3 overflow-x-auto">
                  <BenchmarkComparisonTable filas={performanceData.filas} />
                </div>
              </div>

              {performanceData.serie && performanceData.serie.length > 0 && (
                <div>
                  <h3 className="text-[13px] font-bold text-app-text mb-3">Evolución del Índice</h3>
                  <div className="bg-app-surface border border-app-border rounded-2xl p-4">
                    <PerformanceCompareChart serie={performanceData.serie} />
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'oportunidad' && (
            <div className="space-y-4">
              {opportunityCostData ? (
                <>
                  <div>
                    <h3 className="text-[13px] font-bold text-app-text mb-3">Resumen</h3>
                    {opportunityCostData.estado === 'ok' ? (
                      <div className="grid grid-cols-2 gap-2">
                        <div className="bg-app-surface border border-app-border rounded-lg p-3">
                          <div className="text-[10px] text-app-text-faint uppercase mb-1">Valor Actual</div>
                          <div className="font-mono font-bold text-[13px] text-app-text">
                            {moneda === 'usd'
                              ? formatUSD(opportunityCostData.valor_actual_usd || 0)
                              : formatARS(opportunityCostData.valor_actual_ars || 0)}
                          </div>
                        </div>
                        <div className="bg-app-surface border border-app-border rounded-lg p-3">
                          <div className="text-[10px] text-app-text-faint uppercase mb-1">Valor Shadow</div>
                          <div className="font-mono font-bold text-[13px] text-app-text">
                            {moneda === 'usd'
                              ? formatUSD(opportunityCostData.valor_shadow_usd || 0)
                              : formatARS(opportunityCostData.valor_shadow_ars || 0)}
                          </div>
                        </div>
                        <div className="bg-app-surface border border-app-border rounded-lg p-3">
                          <div className="text-[10px] text-app-text-faint uppercase mb-1">Costo Oportunidad</div>
                          <div className={`font-mono font-bold text-[13px] ${
                            (opportunityCostData.costo_oportunidad_usd || 0) > 0 ? 'text-app-coral' : 'text-app-teal'
                          }`}>
                            {moneda === 'usd'
                              ? formatUSD(opportunityCostData.costo_oportunidad_usd || 0)
                              : formatARS(opportunityCostData.costo_oportunidad_ars || 0)}
                          </div>
                        </div>
                        <div className="bg-app-surface border border-app-border rounded-lg p-3">
                          <div className="text-[10px] text-app-text-faint uppercase mb-1">Benchmark</div>
                          <div className="text-[12px] font-semibold text-app-text">
                            {opportunityCostData.benchmark_usado}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="bg-app-surface border border-app-border rounded-lg p-3 text-app-text-dim text-[12px]">
                        {opportunityCostData.estado === 'sin_benchmark'
                          ? 'No hay benchmark configurado'
                          : 'Datos insuficientes'}
                      </div>
                    )}
                  </div>

                  {opportunityCostData.estado === 'ok' && opportunityCostData.por_posicion.length > 0 && (
                    <div>
                      <h3 className="text-[13px] font-bold text-app-text mb-3">Por Posición</h3>
                      <div className="bg-app-surface border border-app-border rounded-2xl p-3 overflow-x-auto">
                        <table className="w-full text-[11px]">
                          <thead>
                            <tr className="border-b border-app-border">
                              <th className="text-left py-2 px-2 text-app-text-faint font-bold">Ticker</th>
                              <th className="text-right py-2 px-2 text-app-text-faint font-bold">Actual</th>
                              <th className="text-right py-2 px-2 text-app-text-faint font-bold">Shadow</th>
                              <th className="text-right py-2 px-2 text-app-text-faint font-bold">Costo (USD)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {opportunityCostData.por_posicion.map((pos) => (
                              <tr key={pos.ticker} className="border-b border-app-border hover:bg-app-bg">
                                <td className="py-1.5 px-2 font-semibold">{pos.ticker}</td>
                                <td className="py-1.5 px-2 text-right font-mono text-app-text-dim">
                                  {formatUSD(pos.valor_actual_usd)}
                                </td>
                                <td className="py-1.5 px-2 text-right font-mono text-app-text-dim">
                                  {formatUSD(pos.valor_shadow_usd)}
                                </td>
                                <td className={`py-1.5 px-2 text-right font-mono ${
                                  pos.costo_oportunidad_usd > 0 ? 'text-app-coral' : 'text-app-teal'
                                }`}>
                                  {formatUSD(pos.costo_oportunidad_usd)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="bg-app-surface border border-app-border rounded-lg p-3 text-app-text-dim text-[12px]">
                  Selecciona un benchmark para ver el análisis de costo de oportunidad
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
