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

function fmtPct(ratio: number | null): string {
  if (ratio == null) return '—'
  return `${(ratio * 100).toFixed(2)}%`
}

function fmtDuration(anios: number | null): string {
  if (anios == null) return '—'
  return `${anios.toFixed(2)} a`
}

function Metrica({ label, valor }: { label: string; valor: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-label uppercase tracking-wide text-app-text-faint">{label}</span>
      <span className="font-mono text-caption font-semibold text-app-text tabular-nums">{valor}</span>
    </div>
  )
}

export default function VencimientoRow({ item, moneda }: { item: VencimientoItem; moneda: 'USD' | 'ARS' }) {
  const esARS = moneda === 'ARS'
  const valor = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const formatMoneda = esARS ? formatARS : formatUSD

  const hayMetricas =
    item.paridad != null || item.tir_vencimiento != null || item.duration_modificada != null

  return (
    <div className="py-2.5 border-b border-app-border-soft last:border-b-0">
      <div className="flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-[11px] bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-label font-bold text-app-text shrink-0">
          {item.ticker.slice(0, 4)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-caption font-bold text-app-text truncate">{item.nombre}</div>
          <div className="text-label text-app-text-dim mt-0.5 truncate">
            Vence: {dayjs(item.fecha_vencimiento).format('D MMM YYYY')}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-mono text-caption font-bold text-app-text tabular-nums">{formatMoneda(valor)}</div>
          <span className={`inline-block font-bold text-label tracking-wide px-1.5 py-0.5 rounded-[6px] mt-0.5 ${badgeClase(item)}`}>
            {badgeLabel(item)}
          </span>
        </div>
      </div>

      {hayMetricas && (
        <div className="mt-2 ml-[46px] flex items-center gap-4 flex-wrap">
          <Metrica label="Paridad" valor={fmtPct(item.paridad)} />
          <Metrica label="TIR vto." valor={fmtPct(item.tir_vencimiento)} />
          <Metrica label="Dur. mod." valor={fmtDuration(item.duration_modificada)} />
          {item.metricas_estimadas && (
            <span
              className="text-label uppercase tracking-wide px-1.5 py-0.5 rounded bg-app-surface-2 text-app-text-faint self-end"
              title={item.metricas_nota ?? 'Estimado sobre el flujo de caja inferido'}
            >
              est.
            </span>
          )}
        </div>
      )}
      {!hayMetricas && !item.vencido && item.metricas_nota && (
        <div className="mt-1.5 ml-[46px] text-label text-app-text-faint">{item.metricas_nota}</div>
      )}
    </div>
  )
}
