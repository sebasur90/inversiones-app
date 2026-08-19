import { formatARS, formatPctRatio, formatUSD } from '../../utils'
import Card from '../../components/ui/Card'
import MetricTile from '../../components/ui/MetricTile'
import type { TickerPerformanceOut, TickerPositionOut } from '../../api'

function toneFor(v: number | null | undefined): 'pos' | 'neg' | undefined {
  if (v == null) return undefined
  return v >= 0 ? 'pos' : 'neg'
}

export default function TickerRendimientoTab({ performance, position, monedaSeleccionada }: { performance: TickerPerformanceOut; position: TickerPositionOut; monedaSeleccionada: 'ARS' | 'USD' }) {
  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD

  const realizado = esARS ? performance.realizado_ars : performance.realizado_usd
  const noRealizado = esARS ? performance.no_realizado_ars : performance.no_realizado_usd
  const ingresos = esARS ? performance.ingresos_ars : performance.ingresos_usd
  const total = esARS ? performance.total_ars : performance.total_usd
  const comisiones = esARS ? performance.comisiones_ars : performance.comisiones_usd

  return (
    <div className="pb-4">
      <div className="grid grid-cols-2 gap-2 mb-4">
        <MetricTile
          label="Realizado"
          infoTerm="realizado"
          value={formatMoneda(realizado)}
          tone={toneFor(realizado)}
        />
        <MetricTile
          label="No realizado"
          infoTerm="noRealizado"
          value={noRealizado != null ? formatMoneda(noRealizado) : 'N/A'}
          tone={toneFor(noRealizado)}
        />
        <MetricTile
          label="Ingresos"
          infoTerm="ingresos"
          value={formatMoneda(ingresos)}
          tone={toneFor(ingresos)}
        />
        <MetricTile
          label="Total P&L"
          value={total != null ? formatMoneda(total) : 'N/A'}
          tone={toneFor(total)}
        />
        <MetricTile
          label="Comisiones"
          value={formatMoneda(comisiones)}
          tone={comisiones === 0 ? undefined : 'neg'}
        />
      </div>

      <Card>
        <h3 className="text-[12px] font-bold text-app-text mb-3">Desglose por moneda</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-app-border">
                <th className="text-left py-2 px-2 text-app-text-dim font-semibold">Moneda</th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Realizado</th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">No realizado</th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-app-border/50">
                <td className="py-2 px-2 text-app-text font-semibold">USD</td>
                <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${performance.realizado_usd >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                  {formatUSD(performance.realizado_usd)}
                </td>
                <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${toneFor(performance.no_realizado_usd) === 'pos' ? 'text-app-teal' : toneFor(performance.no_realizado_usd) === 'neg' ? 'text-app-coral' : 'text-app-text'}`}>
                  {performance.no_realizado_usd != null ? formatUSD(performance.no_realizado_usd) : '—'}
                </td>
                <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${toneFor(performance.total_usd) === 'pos' ? 'text-app-teal' : toneFor(performance.total_usd) === 'neg' ? 'text-app-coral' : 'text-app-text'}`}>
                  {formatUSD(performance.total_usd)}
                </td>
              </tr>
              <tr className="border-b border-app-border/50">
                <td className="py-2 px-2 text-app-text font-semibold">ARS</td>
                <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${performance.realizado_ars >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                  {formatARS(performance.realizado_ars)}
                </td>
                <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${toneFor(performance.no_realizado_ars) === 'pos' ? 'text-app-teal' : toneFor(performance.no_realizado_ars) === 'neg' ? 'text-app-coral' : 'text-app-text'}`}>
                  {performance.no_realizado_ars != null ? formatARS(performance.no_realizado_ars) : '—'}
                </td>
                <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${toneFor(performance.total_ars) === 'pos' ? 'text-app-teal' : toneFor(performance.total_ars) === 'neg' ? 'text-app-coral' : 'text-app-text'}`}>
                  {performance.total_ars != null ? formatARS(performance.total_ars) : '—'}
                </td>
              </tr>
              {position.rendimiento_simple_ars_real != null && (
                <tr>
                  <td className="py-2 px-2 text-app-text font-semibold">ARS Real</td>
                  <td className="text-right py-2 px-2 text-app-text-dim">—</td>
                  <td className="text-right py-2 px-2 text-app-text-dim">—</td>
                  <td className={`text-right py-2 px-2 font-mono font-bold tabular-nums ${position.rendimiento_simple_ars_real >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                    {formatPctRatio(position.rendimiento_simple_ars_real)}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
