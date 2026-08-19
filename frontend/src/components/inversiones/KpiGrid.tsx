import type { InversionesResumen } from '../../api'
import { formatPctRatio } from '../../utils'
import MetricTile from '../ui/MetricTile'
import type { HelpKey } from '../../help/content/index'

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
      <MetricTile
        label="Invertido"
        infoTerm="invertido"
        value={invertido != null ? (esARS ? `$${Math.round(invertido).toLocaleString('es-AR')}` : `$${Math.round(invertido).toLocaleString('en-US')}`) : '—'}
        suffix={esARS ? 'ARS' : 'USD'}
        size="md"
      />
      <MetricTile label="XIRR" infoTerm="xirr" value={formatPctRatio(xirr)} tone={toneFor(xirr)} size="md" />
      <MetricTile label="TWR" infoTerm="twr" value={formatPctRatio(twr)} tone={toneFor(twr)} size="md" />
    </div>
  )
}
