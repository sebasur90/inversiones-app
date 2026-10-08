import { formatPctRatio } from '../../utils'
import { Icon } from '../icons/Icons'

/** Variación del día: la que informa IOL o, si no la hay, contra el registro del día hábil anterior. Sin dato, muestra "—". */
export default function VariacionDia({ pct, className = '' }: { pct: number | null | undefined; className?: string }) {
  if (pct == null) {
    return <span className={`font-mono text-label text-app-text-dim tabular-nums ${className}`} title="Sin dato del día anterior para comparar">—</span>
  }
  const color = pct > 0 ? 'text-app-pos' : pct < 0 ? 'text-app-neg' : 'text-app-text-dim'
  return (
    <span
      className={`inline-flex items-center gap-0.5 font-mono text-label font-bold tabular-nums ${color} ${className}`}
      title="Variación del día respecto del cierre anterior"
    >
      {pct !== 0 && <Icon name={pct > 0 ? 'up' : 'down'} className="w-2.5 h-2.5" />}
      {formatPctRatio(pct)}
    </span>
  )
}
