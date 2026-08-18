import type { PatrimonioPunto } from '../../api'
import Card from '../ui/Card'

interface PatrimonioMensualTableProps {
  puntos: PatrimonioPunto[]
  esUSD: boolean
}

function formatCompact(v: number, esUSD: boolean): string {
  const abs = Math.abs(v)
  const signo = v < 0 ? '-' : ''
  if (esUSD) {
    if (abs >= 1_000_000) return `${signo}U$S ${(abs / 1_000_000).toFixed(1)}M`
    if (abs >= 1000) return `${signo}U$S ${(abs / 1000).toFixed(0)}K`
    return `${signo}U$S ${abs.toFixed(2)}`
  }
  if (abs >= 1_000_000) return `${signo}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1000) return `${signo}$${(abs / 1000).toFixed(0)}K`
  return `${signo}$${abs.toFixed(0)}`
}

function formatFecha(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { year: 'numeric', month: 'short', day: '2-digit' })
}

function formatPctRatio(v: number | null): string {
  if (v === null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

export default function PatrimonioMensualTable({ puntos, esUSD }: PatrimonioMensualTableProps) {
  if (puntos.length === 0) {
    return <div className="text-[12px] text-app-text-dim text-center py-4">Sin datos para mostrar</div>
  }

  const datos = puntos.map((p, i) => {
    const valor_actual = esUSD ? p.valor_usd : p.valor_ars
    const aportes = esUSD ? p.aportes_acumulados_usd : p.aportes_acumulados_ars
    const ganancia = esUSD ? p.ganancia_usd : p.ganancia_ars

    const rendimiento_pct = aportes !== 0 ? (ganancia / Math.abs(aportes)) : (i === 0 ? 0 : null)

    return {
      fecha: formatFecha(p.fecha),
      valor: valor_actual,
      aportes_delta: i === 0 ? aportes : aportes - (esUSD ? puntos[i - 1].aportes_acumulados_usd : puntos[i - 1].aportes_acumulados_ars),
      ganancia,
      rendimiento: rendimiento_pct,
    }
  })

  return (
    <Card className="mb-4 overflow-x-auto">
      <table className="w-full text-[11px] border-separate border-spacing-0">
        <thead>
          <tr className="border-b border-app-border">
            <th className="text-left text-app-text-faint font-bold uppercase text-[9.5px] pb-2 px-2">Fecha</th>
            <th className="text-right text-app-text-faint font-bold uppercase text-[9.5px] pb-2 px-2">Aportes</th>
            <th className="text-right text-app-text-faint font-bold uppercase text-[9.5px] pb-2 px-2">Patrimonio</th>
            <th className="text-right text-app-text-faint font-bold uppercase text-[9.5px] pb-2 px-2">Ganancia</th>
            <th className="text-right text-app-text-faint font-bold uppercase text-[9.5px] pb-2 px-2">Rendimiento</th>
          </tr>
        </thead>
        <tbody>
          {datos.map((d, idx) => (
            <tr key={idx} className="border-b border-app-border-soft last:border-b-0 hover:bg-app-surface-hover">
              <td className="text-left text-app-text-dim py-2 px-2">{d.fecha}</td>
              <td className="text-right text-app-text font-mono py-2 px-2 tabular-nums">{formatCompact(d.aportes_delta, esUSD)}</td>
              <td className="text-right text-app-text font-mono py-2 px-2 tabular-nums font-semibold">{formatCompact(d.valor, esUSD)}</td>
              <td className={`text-right font-mono py-2 px-2 tabular-nums ${d.ganancia >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                {formatCompact(d.ganancia, esUSD)}
              </td>
              <td className={`text-right font-mono py-2 px-2 tabular-nums ${d.rendimiento === null ? 'text-app-text-dim' : d.rendimiento >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                {formatPctRatio(d.rendimiento)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
