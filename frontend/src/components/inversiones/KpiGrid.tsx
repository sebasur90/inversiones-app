import type { InversionesResumen } from '../../api'
import { formatPctRatio } from '../../utils'

function Kpi({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  return (
    <div className="bg-app-surface border border-app-border rounded-[13px] px-2.5 py-2.5">
      <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">{label}</div>
      <div className={`font-mono text-[15px] font-bold tabular-nums ${tone === 'pos' ? 'text-app-teal' : tone === 'neg' ? 'text-app-coral' : 'text-app-text'}`}>
        {value}
      </div>
    </div>
  )
}

function toneFor(v: number | null | undefined): 'pos' | 'neg' | undefined {
  if (v == null) return undefined
  return v >= 0 ? 'pos' : 'neg'
}

export default function KpiGrid({ resumen, moneda }: { resumen: InversionesResumen | null; moneda: 'USD' | 'ARS' }) {
  const esARS = moneda === 'ARS'
  const invertido = esARS ? resumen?.total_invertido_ars : resumen?.total_invertido_usd
  const xirr = esARS ? resumen?.xirr_ars ?? null : resumen?.xirr_usd ?? null
  const twr = esARS ? resumen?.twr_ars ?? null : resumen?.twr_usd ?? null

  return (
    <div className="grid grid-cols-3 gap-2 mb-3.5">
      <Kpi label="Invertido" value={invertido != null ? (esARS ? `$${Math.round(invertido).toLocaleString('es-AR')}` : `$${Math.round(invertido).toLocaleString('en-US')}`) : '—'} />
      <Kpi label="XIRR" value={formatPctRatio(xirr)} tone={toneFor(xirr)} />
      <Kpi label="TWR" value={formatPctRatio(twr)} tone={toneFor(twr)} />
    </div>
  )
}
