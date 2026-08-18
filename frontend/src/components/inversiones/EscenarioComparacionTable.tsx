import { EscenarioSimulacionOut } from '../../api'

interface EscenarioComparacionTableProps {
  resultado: EscenarioSimulacionOut
}

function heatmapIntensity(ratio: number): string {
  // Mapea un ratio (ganancia/capital) a un color de fondo
  // Negativo (rojo), cero (gris), positivo (verde/teal)
  if (ratio < 0) {
    const intensity = Math.min(Math.abs(ratio) * 0.2, 1)
    return `rgba(229, 102, 90, ${intensity * 0.4})`
  } else if (ratio > 0) {
    const intensity = Math.min(ratio * 0.2, 1)
    return `rgba(79, 209, 174, ${intensity * 0.4})`
  }
  return 'transparent'
}

function formatUSD(val: number): string {
  return `$${val.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function EscenarioComparacionTable({ resultado }: EscenarioComparacionTableProps) {
  const metricas = [
    { key: 'patrimonio_inicial_usd', label: 'Patrimonio inicial', format: formatUSD },
    { key: 'patrimonio_final_usd', label: 'Patrimonio final', format: formatUSD },
    { key: 'ganancia_perdida_usd', label: 'Ganancia/Pérdida', format: formatUSD },
    { key: 'rendimiento_pct', label: 'Rendimiento', format: (v: number) => `${v.toFixed(1)}%` },
    { key: 'capital_aportado_usd', label: 'Capital aportado', format: formatUSD },
    { key: 'efecto_mercado_usd', label: 'Efecto mercado', format: formatUSD },
    { key: 'efecto_dolar_usd', label: 'Efecto dólar', format: formatUSD },
    { key: 'dividendos_usd', label: 'Dividendos', format: formatUSD },
    { key: 'comisiones_usd', label: 'Comisiones', format: formatUSD },
  ]

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-app-border">
            <th className="text-left py-2 px-2 text-app-text-secondary font-medium">Métrica</th>
            {resultado.resultados.map((esc, idx) => (
              <th
                key={idx}
                className="text-right py-2 px-2 font-medium text-app-text tabular-nums"
              >
                <div className="text-xs font-semibold">{esc.nombre}</div>
                <div className="text-[10px] text-app-text-secondary">({esc.tipo_preset})</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricas.map((metrica) => (
            <tr key={metrica.key} className="border-b border-app-border hover:bg-app-surface-2">
              <td className="text-left py-2 px-2 text-app-text-secondary">
                {metrica.label}
              </td>
              {resultado.resultados.map((esc, idx) => {
                const valor = (esc as any)[metrica.key]
                const esGanancia = metrica.key === 'rendimiento_pct'
                const bgcolor = esGanancia ? heatmapIntensity(valor / 100) : ''

                return (
                  <td
                    key={idx}
                    className="text-right py-2 px-2 text-app-text tabular-nums"
                    style={{ backgroundColor: bgcolor }}
                  >
                    {metrica.format(valor)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
