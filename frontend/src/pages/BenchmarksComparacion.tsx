import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import {
  getBenchmarksDisponibles,
  getOpportunityCost,
  getPerformanceCompare,
  getTickersConPrecios,
  type MonedaRiesgo,
} from '../api'
import { calcularDesde, type PeriodoEvolucion } from '../utils'
import { formatMonto } from '../utils/formatoMonto'
import { useMontosOcultos } from '../utils/privacidad'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import MetricTile from '../components/ui/MetricTile'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import BenchmarkComparisonTable from '../components/inversiones/BenchmarkComparisonTable'
import PerformanceCompareChart from '../components/charts/PerformanceCompareChart'
import FormHelp from '../help/components/FormHelp'

/** Los períodos que ofrece esta pantalla, un subconjunto de los que `calcularDesde` ya resuelve. */
type Periodo = Extract<PeriodoEvolucion, '1M' | '3M' | '6M' | '1Y' | 'ALL'>

const OPCIONES_PERIODO: { value: Periodo; label: string }[] = [
  { value: '1M', label: '1M' },
  { value: '3M', label: '3M' },
  { value: '6M', label: '6M' },
  { value: '1Y', label: '1A' },
  { value: 'ALL', label: 'Todo' },
]

const OPCIONES_MONEDA: { value: MonedaRiesgo; label: string }[] = [
  { value: 'usd', label: 'USD' },
  { value: 'ars_nominal', label: 'ARS' },
  { value: 'ars_real', label: 'ARS real' },
]

type Tab = 'comparacion' | 'oportunidad'

const OPCIONES_TAB: { value: Tab; label: string }[] = [
  { value: 'comparacion', label: 'Comparación' },
  { value: 'oportunidad', label: 'Costo de oportunidad' },
]

/**
 * Chip de selección múltiple.
 *
 * El color de "elegido" es `accent`, no `pos`: en el resto de la app el verde significa
 * "positivo" (ganancia), y usarlo para "seleccionado" rompe esa convención.
 */
function ChipSeleccion({ label, activo, onClick }: { label: string; activo: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={activo}
      className={`px-2.5 py-1.5 rounded-lg text-label font-semibold whitespace-nowrap ${
        activo ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface border border-app-border text-app-text-dim'
      }`}
    >
      {label}
    </button>
  )
}

function alternar(lista: string[], valor: string): string[] {
  return lista.includes(valor) ? lista.filter(x => x !== valor) : [...lista, valor]
}

export default function BenchmarksComparacion() {
  const navigate = useNavigate()
  // La cartera sale del contexto, como en el resto de las pantallas. Antes entraba por una prop
  // con default `null` que `App.tsx` nunca pasaba: la pantalla mostraba siempre el consolidado
  // aunque tuvieras otra cartera elegida, y sin avisarlo.
  const { carteraSeleccionada } = useInversionesContext()
  const [periodo, setPeriodo] = useState<Periodo>('1Y')
  const [moneda, setMoneda] = useState<MonedaRiesgo>('usd')
  const [tab, setTab] = useState<Tab>('comparacion')
  const ocultos = useMontosOcultos()

  // `ars_real` es la serie ajustada por CER: sigue siendo pesos.
  const fmt = (v: number | null | undefined) => formatMonto(v, moneda === 'usd' ? 'USD' : 'ARS', ocultos)
  const fmtUsd = (v: number | null | undefined) => formatMonto(v, 'USD', ocultos)

  // Catálogos. `tickers-con-precios` comparte clave con Precios, Comparador y Matriz de
  // correlaciones: es el mismo catálogo y se cachea una sola vez para las cuatro pantallas.
  const catalogoBenchmarks = useQuery({
    queryKey: qk.de('benchmarks'),
    queryFn: getBenchmarksDisponibles,
  })
  const catalogoTickers = useQuery({
    queryKey: qk.de('tickers-con-precios'),
    queryFn: getTickersConPrecios,
  })

  const benchmarksDisponibles = catalogoBenchmarks.data ?? []
  const tickersDisponibles = (catalogoTickers.data ?? []).map(t => t.ticker)

  // `null` = el usuario todavía no tocó la selección, y se usan los dos primeros benchmarks.
  // Derivarlo en vez de sembrarlo desde un efecto evita el render intermedio sin selección.
  const [seleccionBenchmarks, setSeleccionBenchmarks] = useState<string[] | null>(null)
  const [tickers, setTickers] = useState<string[]>([])
  const benchmarks = seleccionBenchmarks ?? benchmarksDisponibles.slice(0, 2)

  const desde = calcularDesde(periodo)
  const hayAlgoQueComparar = benchmarks.length > 0 || tickers.length > 0

  const comparacion = useQuery({
    queryKey: qk.de(
      'performance-compare',
      carteraSeleccionada,
      moneda,
      periodo,
      [...benchmarks].sort(),
      [...tickers].sort(),
    ),
    queryFn: () => getPerformanceCompare(carteraSeleccionada, moneda, desde, benchmarks, tickers),
    enabled: hayAlgoQueComparar,
  })

  // Query aparte en vez de un `Promise.all` con la comparación: si el costo de oportunidad falla,
  // la comparación -- que es el contenido principal -- tiene que seguir mostrándose.
  const oportunidad = useQuery({
    queryKey: qk.de('opportunity-cost', carteraSeleccionada, benchmarks[0] ?? null, periodo),
    queryFn: () => getOpportunityCost(carteraSeleccionada, benchmarks[0], desde),
    enabled: benchmarks.length > 0,
  })

  const performance = comparacion.data ?? null
  const costo = oportunidad.data ?? null

  return (
    <div className="pb-4">
      <ScreenHeader title="Comparar benchmarks" onBack={() => navigate(-1)} />

      <div className="flex flex-col gap-2 mb-4">
        <div>
          <FormHelp term="benchmarks_periodo" label="Período" />
          <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
        </div>
        <div>
          <FormHelp term="benchmarks_moneda" label="Moneda" />
          <Segmented options={OPCIONES_MONEDA} value={moneda} onChange={setMoneda} />
        </div>
      </div>

      <Card className="mb-4">
        <div className="flex flex-col gap-3">
          <div>
            <FormHelp term="benchmarks_seleccion" label="Benchmarks" />
            <div className="flex flex-wrap gap-1.5">
              {benchmarksDisponibles.map(b => (
                <ChipSeleccion
                  key={b}
                  label={b}
                  activo={benchmarks.includes(b)}
                  onClick={() => setSeleccionBenchmarks(alternar(benchmarks, b))}
                />
              ))}
            </div>
          </div>
          <div>
            <div className="text-caption font-semibold text-app-text mb-2">Tickers</div>
            <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
              {tickersDisponibles.map(t => (
                <ChipSeleccion
                  key={t}
                  label={t}
                  activo={tickers.includes(t)}
                  onClick={() => setTickers(alternar(tickers, t))}
                />
              ))}
            </div>
          </div>
        </div>
      </Card>

      <div className="mb-4">
        <Segmented options={OPCIONES_TAB} value={tab} onChange={setTab} />
      </div>

      {!hayAlgoQueComparar ? (
        <EmptyState title="Elegí al menos un benchmark o un ticker para comparar" />
      ) : tab === 'comparacion' ? (
        <QueryBoundary
          isLoading={comparacion.isLoading}
          error={comparacion.error}
          onRetry={() => void comparacion.refetch()}
        >
          {performance && (
            <div className="space-y-6">
              <div>
                <h3 className="text-body font-bold text-app-text mb-3">Rendimientos</h3>
                <Card className="p-3">
                  <BenchmarkComparisonTable filas={performance.filas} />
                </Card>
              </div>

              {performance.serie && performance.serie.length > 0 && (
                <div>
                  <h3 className="text-body font-bold text-app-text mb-3">Evolución del índice</h3>
                  <Card>
                    <PerformanceCompareChart serie={performance.serie} />
                  </Card>
                </div>
              )}
            </div>
          )}
        </QueryBoundary>
      ) : (
        <QueryBoundary
          isLoading={oportunidad.isLoading}
          error={oportunidad.error}
          onRetry={() => void oportunidad.refetch()}
        >
          {costo === null ? (
            <EmptyState title="Elegí un benchmark para ver el análisis de costo de oportunidad" />
          ) : (
            <div className="space-y-4">
              <div>
                <h3 className="text-body font-bold text-app-text mb-3">Resumen</h3>
                {costo.estado === 'ok' ? (
                  <div className="grid grid-cols-2 gap-2">
                    <MetricTile
                      label="Valor actual"
                      value={fmt(moneda === 'usd' ? costo.valor_actual_usd : costo.valor_actual_ars)}
                    />
                    <MetricTile
                      label="Valor shadow"
                      value={fmt(moneda === 'usd' ? costo.valor_shadow_usd : costo.valor_shadow_ars)}
                      infoTerm="valorShadow"
                    />
                    <MetricTile
                      label="Costo de oportunidad"
                      value={fmt(moneda === 'usd' ? costo.costo_oportunidad_usd : costo.costo_oportunidad_ars)}
                      tone={(costo.costo_oportunidad_usd || 0) > 0 ? 'neg' : 'pos'}
                      infoTerm="costoOportunidad"
                    />
                    <MetricTile label="Benchmark usado" value={costo.benchmark_usado || '—'} />
                  </div>
                ) : (
                  <EmptyState
                    title={
                      costo.estado === 'sin_benchmark'
                        ? 'No hay benchmark configurado'
                        : 'Datos insuficientes para comparar'
                    }
                  />
                )}
              </div>

              {costo.estado === 'ok' && costo.por_posicion.length > 0 && (
                <div>
                  <h3 className="text-body font-bold text-app-text mb-3">Por posición</h3>
                  <Card className="p-3 overflow-x-auto">
                    <table className="w-full text-label">
                      <thead>
                        <tr className="border-b border-app-border">
                          <th scope="col" className="text-left py-2 px-2 text-app-text-faint font-bold">Ticker</th>
                          <th scope="col" className="text-right py-2 px-2 text-app-text-faint font-bold">Actual</th>
                          <th scope="col" className="text-right py-2 px-2 text-app-text-faint font-bold">Shadow</th>
                          <th scope="col" className="text-right py-2 px-2 text-app-text-faint font-bold">Costo (USD)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {costo.por_posicion.map(pos => (
                          <tr key={pos.ticker} className="border-b border-app-border hover:bg-app-bg">
                            <td className="py-1.5 px-2 font-semibold">{pos.ticker}</td>
                            <td className="py-1.5 px-2 text-right font-mono text-app-text-dim">
                              {fmtUsd(pos.valor_actual_usd)}
                            </td>
                            <td className="py-1.5 px-2 text-right font-mono text-app-text-dim">
                              {fmtUsd(pos.valor_shadow_usd)}
                            </td>
                            <td
                              className={`py-1.5 px-2 text-right font-mono ${
                                pos.costo_oportunidad_usd > 0 ? 'text-app-neg' : 'text-app-pos'
                              }`}
                            >
                              {fmtUsd(pos.costo_oportunidad_usd)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Card>
                </div>
              )}
            </div>
          )}
        </QueryBoundary>
      )}
    </div>
  )
}
