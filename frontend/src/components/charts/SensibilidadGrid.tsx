import { heatmapIntensity, formatUSD } from '../../utils'
import Card from '../ui/Card'

interface CeldaData {
  mesesResultado: number | null
  fecha: string | null
}

interface SensibilidadGridProps {
  grilla: CeldaData[][]
  tasas: number[]
  aportes: number[]
  mesesRestantesAlFinal: number
}

function calcularIntensidad(mesesResultado: number | null, mesesRestantes: number): number | null {
  if (mesesResultado == null) return null
  const ratio = (mesesRestantes - mesesResultado) / mesesRestantes
  return Math.max(-1, Math.min(1, ratio))
}

export default function SensibilidadGrid({
  grilla,
  tasas,
  aportes,
  mesesRestantesAlFinal,
}: SensibilidadGridProps) {
  if (grilla.length === 0 || grilla[0].length === 0) {
    return (
      <div className="text-center py-8 text-app-text-dim text-[12.5px]">
        Sin datos para la grilla de sensibilidad
      </div>
    )
  }

  return (
    <Card className="mb-4 overflow-x-auto">
      <table className="w-full text-[10px] border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-app-surface text-left text-app-text-faint font-bold uppercase text-[9px] pb-2 pr-2 min-w-[50px]">
              Tasa
            </th>
            {aportes.map((aporte, idx) => (
              <th
                key={idx}
                className="text-center text-app-text-faint font-bold uppercase text-[9px] pb-2 px-0.5 min-w-[60px]"
              >
                <div>{formatUSD(aporte)}</div>
                <div className="text-[8px] font-normal">/mes</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grilla.map((fila, idxFila) => (
            <tr key={idxFila}>
              <td className="sticky left-0 z-10 bg-app-surface font-semibold text-app-text py-1.5 pr-2 text-[9px]">
                {tasas[idxFila] >= 0 ? '+' : ''}{tasas[idxFila].toFixed(1)}%
              </td>
              {fila.map((celda, idxCol) => {
                const intensidad = calcularIntensidad(celda.mesesResultado, mesesRestantesAlFinal)
                return (
                  <td
                    key={idxCol}
                    className="text-center font-mono tabular-nums text-app-text py-1.5 px-0.5 rounded-[4px]"
                    style={heatmapIntensity(intensidad)}
                  >
                    {celda.mesesResultado == null ? '∞' : `${celda.mesesResultado}m`}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="text-[9px] text-app-text-faint mt-3">
        <div className="mb-1">Celda = meses para alcanzar la meta</div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: 'rgba(79, 209, 174, 0.45)' }} />
            Antes del límite
          </div>
          <div className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: 'rgba(226, 102, 90, 0.45)' }} />
            Después / Nunca
          </div>
        </div>
      </div>
    </Card>
  )
}
