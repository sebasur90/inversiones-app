import type { RebalanceoItem } from '../../api'
import { formatARS, formatPct, formatUSD } from '../../utils'

export default function RebalanceoRow({
  item,
  moneda,
  toleranciaPp,
}: {
  item: RebalanceoItem
  moneda: 'USD' | 'ARS'
  toleranciaPp: number
}) {
  const esARS = moneda === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD
  const valorActual = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const dentroDeTolerancia = Math.abs(item.delta_pp) <= toleranciaPp

  return (
    <div>
      <div className="flex justify-between items-baseline text-caption mb-1.5">
        <span className="text-app-text">{item.etiqueta}</span>
        <span className="font-mono font-bold text-app-text tabular-nums">{formatMoneda(valorActual)}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-app-surface-2">
        <div
          className="h-full rounded-full bg-app-gold"
          style={{ width: `${Math.min(item.porcentaje_actual, 100)}%` }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-[2px] h-3 rounded-full bg-app-text"
          style={{ left: `${Math.min(item.porcentaje_objetivo, 100)}%` }}
          title={`Objetivo: ${item.porcentaje_objetivo}%`}
        />
      </div>
      <div className="flex justify-between items-center text-label text-app-text-dim mt-1">
        <span>Objetivo {item.porcentaje_objetivo.toFixed(1)}%</span>
        <span className={`font-mono font-bold tabular-nums ${dentroDeTolerancia ? 'text-app-teal' : 'text-app-coral'}`}>
          {formatPct(item.delta_pp)} pp
        </span>
      </div>
    </div>
  )
}
