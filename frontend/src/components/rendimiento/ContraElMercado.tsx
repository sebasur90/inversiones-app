import { useNavigate } from 'react-router-dom'
import type { InversionesResumen, PerformanceRelativaOut } from '../../api'
import { formatPctRatio } from '../../utils'
import { Icon } from '../icons/Icons'
import Card from '../ui/Card'
import EmptyState from '../ui/EmptyState'

interface FilaBarra {
  label: string
  valor: number
  propia?: boolean
}

function ListaBarras({ filas }: { filas: FilaBarra[] }) {
  const maximo = Math.max(...filas.map(f => Math.abs(f.valor)), 0)
  return (
    <div className="flex flex-col">
      {filas.map(f => (
        <div key={f.label} className="flex flex-col gap-1.5 py-2.5 border-b border-app-border-soft last:border-b-0">
          <div className="flex justify-between items-baseline gap-3 text-body">
            <span className={f.propia ? 'font-bold text-app-text' : 'font-medium text-app-text-dim'}>{f.label}</span>
            <span className={`font-mono font-bold tabular-nums shrink-0 ${f.propia ? 'text-app-text' : 'text-app-text-dim'}`}>
              {formatPctRatio(f.valor)}
            </span>
          </div>
          <div aria-hidden="true" className="h-1.5 rounded-[3px] bg-app-surface-2">
            <div
              className={`h-1.5 rounded-[3px] ${f.propia ? 'bg-app-accent' : 'bg-app-slate'}`}
              style={{ width: `${maximo > 0 ? (Math.abs(f.valor) / maximo) * 100 : 0}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Tu cartera contra la referencia elegida para la cartera, en la moneda del encabezado. */
export function BenchmarkCard({ perf }: { perf: PerformanceRelativaOut | null }) {
  const navigate = useNavigate()

  if (perf?.estado !== 'ok' || perf.retorno_cartera_pct == null || perf.retorno_benchmark_pct == null) {
    return (
      <Card>
        <EmptyState title="Sin referencia" description="No hay un benchmark configurado, o falta historia para compararte con él." />
      </Card>
    )
  }

  return (
    <Card className="flex flex-col gap-1 pb-4">
      <ListaBarras
        filas={[
          { label: 'Tu cartera', valor: perf.retorno_cartera_pct, propia: true },
          { label: perf.benchmark_usado ?? 'Benchmark', valor: perf.retorno_benchmark_pct },
        ]}
      />
      <div className="grid grid-cols-2 gap-2 pt-2">
        <button
          onClick={() => navigate('/performance-relativa')}
          className="flex items-center justify-center gap-1 min-h-11 rounded-[10px] bg-app-surface-2 text-body font-semibold text-app-text"
        >
          <Icon name="trend" className="w-3.5 h-3.5" /> Ver en el tiempo
        </button>
        <button
          onClick={() => navigate('/benchmarks-comparacion')}
          className="flex items-center justify-center min-h-11 rounded-[10px] bg-app-surface-2 text-body font-semibold text-app-text"
        >
          Comparar más
        </button>
      </div>
    </Card>
  )
}

/**
 * "¿Y si hubieras hecho otra cosa con la misma plata?": el rendimiento simple de la cartera contra
 * comprar dólares o ajustar por inflación. Siempre en pesos (así vienen los datos), con la misma
 * cuenta que usaba el gráfico de barras que esto reemplaza.
 */
export function AlternativasCard({ resumen }: { resumen: InversionesResumen }) {
  const invertido = resumen.total_invertido_ars

  if (invertido <= 0) {
    return (
      <Card>
        <EmptyState title="Sin comparación" description="Vendiste más de lo que invertiste en neto: los % sobre lo invertido no se calculan." />
      </Card>
    )
  }

  const sobreInvertido = (valor: number) => (valor - invertido) / invertido
  const filas: FilaBarra[] = [
    { label: 'Tu cartera', valor: sobreInvertido(resumen.valor_actual_ars + resumen.ingresos_recibidos_ars), propia: true },
  ]
  if (resumen.valor_benchmark_usd_ars != null) {
    filas.push({ label: 'Si hubieras comprado dólares', valor: sobreInvertido(resumen.valor_benchmark_usd_ars) })
  }
  if (resumen.total_invertido_ars_real != null) {
    filas.push({ label: 'Si hubieras ajustado por inflación', valor: sobreInvertido(resumen.total_invertido_ars_real) })
  }

  return (
    <Card>
      <ListaBarras filas={filas} />
      <div className="mt-2 text-label text-app-text-faint space-y-0.5">
        {resumen.valor_benchmark_usd_ars == null && <div>Sin dólar MEP disponible para hoy.</div>}
        {resumen.total_invertido_ars_real == null && <div>Sin inflación (CER) disponible para algunos períodos.</div>}
      </div>
    </Card>
  )
}
