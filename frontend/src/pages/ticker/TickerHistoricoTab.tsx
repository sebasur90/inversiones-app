import { formatARS, formatPrecio, formatUSD } from '../../utils'
import Card from '../../components/ui/Card'
import Sparkline from '../../components/charts/Sparkline'
import type { TickerHistoricoOut } from '../../api'

export default function TickerHistoricoTab({ historico, monedaSeleccionada }: { historico: TickerHistoricoOut; monedaSeleccionada: 'ARS' | 'USD' }) {
  const { puntos } = historico

  const moneda = monedaSeleccionada === 'ARS'
  const formatMoneda = moneda ? formatARS : formatUSD
  const precios = puntos.map(p => p.precio_nominal || 0)
  const esCreciente = precios.length > 1 && precios[precios.length - 1] >= precios[0]

  return (
    <div className="pb-4">
      {precios.length > 0 && (
        <Card className="mb-4">
          <h3 className="text-[12px] font-bold text-app-text mb-3">Precio histórico</h3>
          <Sparkline
            data={precios}
            color={esCreciente ? '#4fd1ae' : '#e2665a'}
            className="w-full h-20"
          />
        </Card>
      )}

      <Card>
        <h3 className="text-[12px] font-bold text-app-text mb-3">Detalle por fecha</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="border-b border-app-border">
                <th className="text-left py-2 px-2 text-app-text-dim font-semibold">Fecha</th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Precio nominal</th>
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Precio USD</th>
                {moneda && <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Precio CER</th>}
                <th className="text-right py-2 px-2 text-app-text-dim font-semibold">Valor posición</th>
              </tr>
            </thead>
            <tbody>
              {puntos.map((p, i) => (
                <tr key={i} className="border-b border-app-border/50">
                  <td className="py-2 px-2 text-app-text font-mono text-[9px]">{p.fecha}</td>
                  <td className="text-right py-2 px-2 font-mono font-semibold tabular-nums text-app-text">
                    {formatPrecio(p.precio_nominal)}
                  </td>
                  <td className="text-right py-2 px-2 font-mono font-semibold tabular-nums text-app-text">
                    {p.precio_usd != null ? formatUSD(p.precio_usd) : '—'}
                  </td>
                  {moneda && (
                    <td className="text-right py-2 px-2 font-mono font-semibold tabular-nums text-app-text">
                      {p.precio_cer != null ? formatARS(p.precio_cer) : '—'}
                    </td>
                  )}
                  <td className={`text-right py-2 px-2 font-mono font-semibold tabular-nums ${p.valor_posicion_usd ? 'text-app-text' : 'text-app-text-dim'}`}>
                    {p.valor_posicion_usd ? formatUSD(p.valor_posicion_usd) : '—'}
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
