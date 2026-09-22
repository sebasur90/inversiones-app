import type { EscenarioVidaOut } from '../../../api'
import { formatUSD, formatARS, heatmapIntensity } from '../../../utils'
import BotonExportarCsv from '../../ui/BotonExportarCsv'
import InfoTooltip from '../../../help/components/InfoTooltip'

interface Props {
  resultado: EscenarioVidaOut
}

export default function VidaComparacionTable({ resultado }: Props) {
  const formatMonto = resultado.moneda === 'ARS' ? formatARS : formatUSD
  const hayInflacion = resultado.resultados.some(r => r.metricas.patrimonio_final_real != null)

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-xs tabular-nums">
          <thead>
            <tr className="border-b border-app-border">
              <th className="text-left py-2 px-2 text-app-text-dim font-medium">Escenario</th>
              <th className="text-right py-2 px-2 text-app-text-dim font-medium">Patrimonio proyectado</th>
              <th className="text-right py-2 px-2 text-app-text-dim font-medium">
                <InfoTooltip term="vida_aportes_periodo" label="Aportes netos" />
              </th>
              <th className="text-right py-2 px-2 text-app-text-dim font-medium">
                <InfoTooltip term="vida_crecimiento_estimado" label="Crecimiento" />
              </th>
              <th className="text-right py-2 px-2 text-app-text-dim font-medium">
                <InfoTooltip term="vida_diferencia_vs_base" label='Dif. vs "Continuar igual"' />
              </th>
              {hayInflacion && (
                <th className="text-right py-2 px-2 text-app-text-dim font-medium">
                  <InfoTooltip term="vida_poder_compra" label="En plata de hoy" />
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {resultado.resultados.map(r => (
              <tr
                key={r.tipo}
                className={`border-b border-app-border ${r.es_base ? 'bg-app-surface-2/60' : 'hover:bg-app-surface-2'}`}
              >
                <td className="text-left py-2 px-2 text-app-text">
                  <div className="font-semibold">{r.nombre}</div>
                  {r.se_agota_en_mes != null && (
                    <div className="text-label text-app-neg">se agota en el mes {r.se_agota_en_mes}</div>
                  )}
                </td>
                <td className="text-right py-2 px-2 text-app-text">
                  {formatMonto(r.metricas.patrimonio_final)}
                </td>
                <td className={`text-right py-2 px-2 ${r.metricas.aportes_periodo < 0 ? 'text-app-neg' : 'text-app-text'}`}>
                  {formatMonto(r.metricas.aportes_periodo)}
                </td>
                <td className="text-right py-2 px-2 text-app-text">
                  {formatMonto(r.metricas.crecimiento_estimado)}
                </td>
                <td
                  className="text-right py-2 px-2 text-app-text"
                  style={r.es_base ? undefined : heatmapIntensity((r.metricas.diferencia_vs_base_pct ?? 0) / 100)}
                >
                  {r.es_base ? '—' : `${r.metricas.diferencia_vs_base >= 0 ? '+' : ''}${formatMonto(r.metricas.diferencia_vs_base)}`}
                </td>
                {hayInflacion && (
                  <td className="text-right py-2 px-2 text-app-text-dim">
                    {r.metricas.patrimonio_final_real != null ? formatMonto(r.metricas.patrimonio_final_real) : '—'}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-label text-app-text-faint">{resultado.disclaimer}</div>
        <BotonExportarCsv
          nombre="escenarios-de-vida"
          encabezados={['Escenario', 'Patrimonio proyectado', 'Aportes netos', 'Crecimiento estimado', 'Diferencia vs base']}
          filas={() => resultado.resultados.map(r => [
            r.nombre,
            r.metricas.patrimonio_final,
            r.metricas.aportes_periodo,
            r.metricas.crecimiento_estimado,
            r.es_base ? 0 : r.metricas.diferencia_vs_base,
          ])}
        />
      </div>
    </div>
  )
}
