import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getPerformanceRelativa, type PerformanceRelativaOut, type MonedaRiesgo } from '../api'
import { useBenchmarkSeleccionado } from '../hooks/useBenchmarkSeleccionado'
import { formatPctRatio, calcularDesde, type PeriodoEvolucion } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import MetricCard from '../components/ui/MetricCard'
import PerformanceRelativaChart from '../components/charts/PerformanceRelativaChart'
import InfoTerm from '../components/ui/InfoTerm'

const OPCIONES_VISTA: { value: MonedaRiesgo; label: string }[] = [
  { value: 'ars_nominal', label: 'ARS Nominal' },
  { value: 'ars_real', label: 'ARS Real (CER)' },
  { value: 'usd', label: 'USD (MEP)' },
]

const OPCIONES_PERIODO: { value: PeriodoEvolucion; label: string }[] = [
  { value: '1M', label: '1M' },
  { value: '3M', label: '3M' },
  { value: '6M', label: '6M' },
  { value: '1Y', label: '1Y' },
  { value: 'YTD', label: 'YTD' },
  { value: 'ALL', label: 'ALL' },
]

function toneClass(v: number | null | undefined): string {
  if (v == null) return 'text-app-text'
  return v >= 0 ? 'text-app-teal' : 'text-app-coral'
}

export default function PerformanceRelativa() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const [periodo, setPeriodo] = useState<PeriodoEvolucion>('1Y')
  const [vista, setVista] = useState<MonedaRiesgo>('usd')
  const { benchmarks, benchmarkSeleccionado, setBenchmarkSeleccionado } = useBenchmarkSeleccionado(carteraSeleccionada)
  const [perfRelativa, setPerfRelativa] = useState<PerformanceRelativaOut | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getPerformanceRelativa(carteraSeleccionada, vista, benchmarkSeleccionado, calcularDesde(periodo))
      .then(data => {
        if (!cancelado) setPerfRelativa(data)
      })
      .catch(() => {
        if (!cancelado) setPerfRelativa(null)
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, vista, benchmarkSeleccionado, periodo])

  const sinHistorialSuficiente = perfRelativa != null && perfRelativa.n_meses_historia === 0

  return (
    <div className="pb-4">
      <ScreenHeader title="Performance vs benchmark" onBack={() => navigate(-1)} />

      <div className="mb-3">
        <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
      </div>

      <div className="mb-3">
        <Segmented options={OPCIONES_VISTA} value={vista} onChange={setVista} />
      </div>

      {benchmarks.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-1.5">Benchmark</div>
          <Segmented
            options={benchmarks.map(b => ({ value: b, label: b }))}
            value={benchmarkSeleccionado ?? benchmarks[0]}
            onChange={setBenchmarkSeleccionado}
          />
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !perfRelativa || perfRelativa.estado === 'sin_benchmark' ? (
        <EmptyState title="Sin benchmark configurado" description="Configura un benchmark para esta cartera para poder comparar su performance." />
      ) : perfRelativa.estado === 'datos_insuficientes' ? (
        <EmptyState title="Datos insuficientes" description="No hay suficiente historial común entre la cartera y el benchmark para este período." />
      ) : (
        <>
          <Card className="mb-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Cartera</div>
                <div className={`font-mono font-bold text-[18px] tabular-nums ${toneClass(perfRelativa.retorno_cartera_pct)}`}>
                  {formatPctRatio(perfRelativa.retorno_cartera_pct)}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Benchmark</div>
                <div className={`font-mono font-bold text-[18px] tabular-nums ${toneClass(perfRelativa.retorno_benchmark_pct)}`}>
                  {formatPctRatio(perfRelativa.retorno_benchmark_pct)}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Diferencia</div>
                <div className={`font-mono font-bold text-[16px] tabular-nums ${toneClass(perfRelativa.delta_pp)}`}>
                  {(perfRelativa.delta_pp ?? 0) >= 0 ? '+' : ''}{perfRelativa.delta_pp?.toFixed(1)} pp
                </div>
              </div>
            </div>
            <div className="text-[11px] text-app-text-dim">
              {(perfRelativa.retorno_cartera_pct ?? 0) >= (perfRelativa.retorno_benchmark_pct ?? 0)
                ? '✓ Superaste el benchmark'
                : '✗ Quedaste por debajo del benchmark'}
            </div>
          </Card>

          <Card className="mb-4">
            <div className="mb-3">
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Costo de oportunidad vs {perfRelativa.benchmark_usado}</div>
              <div className={`font-mono font-bold text-[16px] tabular-nums ${toneClass(perfRelativa.costo_oportunidad_pp)}`}>
                {(perfRelativa.costo_oportunidad_pp ?? 0) >= 0 ? '+' : ''}{perfRelativa.costo_oportunidad_pp?.toFixed(1)} pp
              </div>
            </div>
            <div className="text-[10px] text-app-text-dim">
              ⓘ Esta métrica no constituye una recomendación de inversión. Refleja únicamente la diferencia de rentabilidad respecto al benchmark seleccionado.
            </div>
          </Card>

          <div className="text-[11px] text-app-text-dim mb-3">
            Basado en {perfRelativa.n_meses_historia} mes{perfRelativa.n_meses_historia === 1 ? '' : 'es'} de historial común.
          </div>

          <Card className="mb-4 overflow-x-auto">
            <PerformanceRelativaChart serie={perfRelativa.serie} />
          </Card>

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">Métricas de performance relativa</h3>
          <div className="grid grid-cols-2 gap-2 mb-4">
            <MetricCard
              label="Exceso de retorno"
              infoTerm="benchmark"
              value={formatPctRatio(perfRelativa.exceso_retorno.valor)}
              insuficiente={perfRelativa.exceso_retorno.estado !== 'ok'}
              tone={toneClass(perfRelativa.exceso_retorno.valor)}
            />
            <MetricCard
              label="Alpha"
              infoTerm="alpha"
              value={formatPctRatio(perfRelativa.alpha.valor)}
              insuficiente={perfRelativa.alpha.estado !== 'ok'}
              tone={toneClass(perfRelativa.alpha.valor)}
            />
            <MetricCard
              label="Beta"
              infoTerm="beta"
              value={perfRelativa.beta.valor?.toFixed(2) ?? '—'}
              insuficiente={perfRelativa.beta.estado !== 'ok'}
            />
            <MetricCard
              label="Tracking error"
              infoTerm="trackingError"
              value={formatPctRatio(perfRelativa.tracking_error.valor)}
              insuficiente={perfRelativa.tracking_error.estado !== 'ok'}
            />
            <MetricCard
              label="Information ratio"
              infoTerm="informationRatio"
              value={perfRelativa.information_ratio.valor?.toFixed(2) ?? '—'}
              insuficiente={perfRelativa.information_ratio.estado !== 'ok'}
              tone={toneClass(perfRelativa.information_ratio.valor)}
            />
          </div>
        </>
      )}
    </div>
  )
}
