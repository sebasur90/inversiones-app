import { formatARSCrudo, formatPrecio, formatUSDCrudo } from '../../utils'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import Card from '../../components/ui/Card'
import Sparkline from '../../components/charts/Sparkline'
import VariacionDia from '../../components/ui/VariacionDia'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { TickerHistoricoOut } from '../../api'

// Días que pueden separar dos registros para seguir llamando "diaria" a la variación entre ellos
// (cubre un fin de semana largo). Con un hueco mayor la celda queda en "—" en vez de mentir.
const MAX_DIAS_ENTRE_REGISTROS = 5

function variacionContraAnterior(
  actual: { fecha: string; precio_nominal: number | null },
  anterior: { fecha: string; precio_nominal: number | null } | undefined,
): number | null {
  if (!anterior || !actual.precio_nominal || !anterior.precio_nominal || anterior.precio_nominal <= 0) return null
  const dias = (Date.parse(actual.fecha) - Date.parse(anterior.fecha)) / 86_400_000
  if (!(dias > 0) || dias > MAX_DIAS_ENTRE_REGISTROS) return null
  return actual.precio_nominal / anterior.precio_nominal - 1
}

export default function TickerHistoricoTab({ historico, monedaSeleccionada }: { historico: TickerHistoricoOut; monedaSeleccionada: 'ARS' | 'USD' }) {
  const { puntos } = historico

  const moneda = monedaSeleccionada === 'ARS'
  // Las columnas de precio son cotizaciones del instrumento y quedan visibles; sólo el valor de
  // la posición es dinero tuyo, y siempre viene en dólares.
  const { monto: montoPosicion } = useFormatoFijo('USD')
  const precios = puntos.map(p => p.precio_nominal || 0)
  const esCreciente = precios.length > 1 && precios[precios.length - 1] >= precios[0]

  return (
    <div className="pb-4">
      {precios.length > 0 && (
        <Card className="mb-4">
          <h3 className="text-caption font-bold text-app-text mb-3">Precio histórico</h3>
          <Sparkline
            data={precios}
            color={esCreciente ? '#10b981' : '#ef4444'}
            className="w-full h-20"
          />
        </Card>
      )}

      <Card>
        <h3 className="text-caption font-bold text-app-text mb-3">Detalle por fecha</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-label">
            <thead>
              <tr className="border-b border-app-border">
                <th className="text-left py-2 px-2 text-app-text-dim font-semibold">Fecha</th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold flex items-center justify-end gap-1.5">
                  <span>Precio nominal</span>
                  <InfoTooltip term="tickerdetalle_precio_nominal" />
                </th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold flex items-center justify-end gap-1.5">
                  <span>Precio USD</span>
                  <InfoTooltip term="mep" />
                </th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Var. día</th>
                {moneda && <th className="text-right py-2 px-2 text-app-text-dim font-semibold flex items-center justify-end gap-1.5">
                  <span>Precio CER</span>
                  <InfoTooltip term="cer" />
                </th>}
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold flex items-center justify-end gap-1.5">
                  <span>Valor posición</span>
                  <InfoTooltip term="tickerdetalle_valor_posicion" />
                </th>
              </tr>
            </thead>
            <tbody>
              {puntos.map((p, i) => (
                <tr key={i} className="border-b border-app-border/50">
                  <td className="py-2 px-2 text-app-text font-mono text-label">{p.fecha}</td>
                  <td className="text-right py-2 px-2 font-mono font-semibold tabular-nums text-app-text">
                    {formatPrecio(p.precio_nominal)}
                  </td>
                  <td className="text-right py-2 px-2 font-mono font-semibold tabular-nums text-app-text">
                    {p.precio_usd != null ? formatUSDCrudo(p.precio_usd) : '—'}
                  </td>
                  <td className="text-right py-2 px-2">
                    <VariacionDia pct={variacionContraAnterior(p, puntos[i - 1])} />
                  </td>
                  {moneda && (
                    <td className="text-right py-2 px-2 font-mono font-semibold tabular-nums text-app-text">
                      {p.precio_cer != null ? formatARSCrudo(p.precio_cer) : '—'}
                    </td>
                  )}
                  <td className={`text-right py-2 px-2 font-mono font-semibold tabular-nums ${p.valor_posicion_usd ? 'text-app-text' : 'text-app-text-dim'}`}>
                    {p.valor_posicion_usd ? montoPosicion(p.valor_posicion_usd) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
