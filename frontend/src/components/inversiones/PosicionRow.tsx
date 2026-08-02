import type { RendimientoPorTickerItem } from '../../api'
import { formatARS, formatPctRatio, formatUSD } from '../../utils'
import { Icon } from '../icons/Icons'

export default function PosicionRow({
  item,
  moneda,
  onClick,
}: {
  item: RendimientoPorTickerItem
  moneda: 'USD' | 'ARS'
  onClick: () => void
}) {
  const esARS = moneda === 'ARS'
  const valor = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const rendimiento = esARS ? item.rendimiento_simple_ars : item.rendimiento_simple_usd
  const formatMoneda = esARS ? formatARS : formatUSD
  const positivo = (rendimiento ?? 0) >= 0

  return (
    <button onClick={onClick} className="w-full flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0 text-left">
      <div className="w-9 h-9 rounded-[11px] bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-[10px] font-bold text-app-text shrink-0">
        {item.ticker.slice(0, 4)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-bold text-app-text truncate">{item.nombre}</div>
        <div className="text-[10.5px] text-app-text-dim mt-0.5 truncate">
          {item.tipo_instrumento} · {item.mercado}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="font-mono text-[12.5px] font-bold text-app-text tabular-nums">{formatMoneda(valor)}</div>
        {rendimiento != null && (
          <div className={`inline-flex items-center gap-0.5 font-mono text-[11px] font-bold mt-0.5 tabular-nums ${positivo ? 'text-app-teal' : 'text-app-coral'}`}>
            <Icon name={positivo ? 'up' : 'down'} className="w-2.5 h-2.5" />
            {formatPctRatio(rendimiento)}
          </div>
        )}
      </div>
    </button>
  )
}
