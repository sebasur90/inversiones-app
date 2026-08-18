import type { ComparacionBenchmarkOut } from '../../api'
import { formatPctRatio } from '../../utils'

interface BenchmarkComparisonTableProps {
  filas: ComparacionBenchmarkOut[]
}

function EstadoBadge({ estado }: { estado: string }) {
  const baseClasses = 'inline-block px-2 py-1 rounded text-[11px] font-semibold'
  switch (estado) {
    case 'ok':
      return <span className={`${baseClasses} bg-app-teal text-app-bg`}>OK</span>
    case 'datos_insuficientes':
      return <span className={`${baseClasses} bg-app-text-faint text-app-bg`}>Insuficientes</span>
    case 'sin_benchmark':
      return <span className={`${baseClasses} bg-app-border text-app-text-dim`}>Sin benchmark</span>
    default:
      return <span className={`${baseClasses} bg-app-surface text-app-text`}>{estado}</span>
  }
}

export default function BenchmarkComparisonTable({ filas }: BenchmarkComparisonTableProps) {
  const formatValue = (value: number | null) => {
    if (value === null) return '—'
    return formatPctRatio(value)
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-app-border">
            <th className="text-left py-2 px-3 text-app-text-faint font-bold uppercase">Fuente</th>
            <th className="text-left py-2 px-3 text-app-text-faint font-bold uppercase">Tipo</th>
            <th className="text-left py-2 px-3 text-app-text-faint font-bold uppercase">Estado</th>
            <th className="text-right py-2 px-3 text-app-text-faint font-bold uppercase">Rendimiento</th>
            <th className="text-right py-2 px-3 text-app-text-faint font-bold uppercase">Δ pp</th>
            <th className="text-right py-2 px-3 text-app-text-faint font-bold uppercase">Ranking</th>
            <th className="text-center py-2 px-3 text-app-text-faint font-bold uppercase">Meses</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((fila) => (
            <tr key={fila.fuente} className="border-b border-app-border hover:bg-app-surface">
              <td className="py-2.5 px-3 font-semibold text-app-text">{fila.fuente}</td>
              <td className="py-2.5 px-3 text-app-text-dim text-[11px]">{fila.tipo}</td>
              <td className="py-2.5 px-3"><EstadoBadge estado={fila.estado} /></td>
              <td className="py-2.5 px-3 text-right font-mono">
                {fila.estado === 'ok' ? formatValue(fila.retorno_pct) : '—'}
              </td>
              <td className="py-2.5 px-3 text-right font-mono">
                {fila.estado === 'ok' && fila.delta_pp !== null ? (
                  <span className={fila.delta_pp > 0 ? 'text-app-teal' : 'text-app-coral'}>
                    {fila.delta_pp > 0 ? '+' : ''}{fila.delta_pp.toFixed(2)}pp
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="py-2.5 px-3 text-right">
                {fila.ranking ? `${fila.ranking}°` : '—'}
              </td>
              <td className="py-2.5 px-3 text-center">
                {fila.n_meses_historia}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
