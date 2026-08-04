import dayjs from 'dayjs'
import type { VencimientoItem } from '../../api'
import { formatARS, formatUSD } from '../../utils'

function badgeClase(item: VencimientoItem): string {
  if (item.vencido || item.dias_restantes < 30) return 'bg-app-coral-soft text-app-coral'
  if (item.dias_restantes < 180) return 'bg-app-gold-soft text-app-gold'
  return 'bg-app-surface-2 text-app-text-dim'
}

function badgeLabel(item: VencimientoItem): string {
  if (item.vencido) return 'Vencido'
  if (item.dias_restantes === 0) return 'Hoy'
  return `${item.dias_restantes} días`
}

export default function VencimientoRow({ item, moneda }: { item: VencimientoItem; moneda: 'USD' | 'ARS' }) {
  const esARS = moneda === 'ARS'
  const valor = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const formatMoneda = esARS ? formatARS : formatUSD

  return (
    <div className="flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0">
      <div className="w-9 h-9 rounded-[11px] bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-[10px] font-bold text-app-text shrink-0">
        {item.ticker.slice(0, 4)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-bold text-app-text truncate">{item.nombre}</div>
        <div className="text-[10.5px] text-app-text-dim mt-0.5 truncate">
          Vence: {dayjs(item.fecha_vencimiento).format('D MMM YYYY')}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="font-mono text-[12.5px] font-bold text-app-text tabular-nums">{formatMoneda(valor)}</div>
        <span className={`inline-block font-bold text-[9.5px] tracking-wide px-1.5 py-0.5 rounded-[6px] mt-0.5 ${badgeClase(item)}`}>
          {badgeLabel(item)}
        </span>
      </div>
    </div>
  )
}
