import type { RendimientoAnualItem, RendimientoMensualItem } from '../../api'
import { formatPctRatio, heatmapIntensity } from '../../utils'
import Card from '../ui/Card'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

interface RendimientoHeatmapProps {
  meses: RendimientoMensualItem[]
  anios: RendimientoAnualItem[]
  esARS: boolean
}

export default function RendimientoHeatmap({ meses, anios, esARS }: RendimientoHeatmapProps) {
  const porClave = new Map<string, RendimientoMensualItem>()
  for (const item of meses) {
    porClave.set(`${item.anio}-${item.mes}`, item)
  }
  const aniosOrdenados = [...anios].sort((a, b) => b.anio - a.anio)
  const hayMesEnCurso = meses.some(m => m.en_curso)

  return (
    <Card className="mb-4 overflow-x-auto">
      <table className="w-full text-[11px] border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-app-surface text-left text-app-text-faint font-bold uppercase text-[9.5px] pb-2 pr-2">
              Año
            </th>
            {MESES.map(m => (
              <th key={m} className="text-center text-app-text-faint font-bold uppercase text-[9.5px] pb-2 px-0.5 min-w-[40px]">
                {m}
              </th>
            ))}
            <th className="text-center text-app-text-faint font-bold uppercase text-[9.5px] pb-2 pl-2 border-l border-app-border min-w-[52px]">
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {aniosOrdenados.map(anio => (
            <tr key={anio.anio}>
              <td className="sticky left-0 z-10 bg-app-surface font-semibold text-app-text py-1 pr-2">
                {anio.anio}
              </td>
              {MESES.map((_, idx) => {
                const item = porClave.get(`${anio.anio}-${idx + 1}`)
                const valor = item ? (esARS ? item.twr_ars : item.twr_usd) : null
                return (
                  <td
                    key={idx}
                    className="text-center font-mono tabular-nums text-app-text py-1.5 px-0.5 rounded-[4px]"
                    style={heatmapIntensity(valor)}
                  >
                    {valor == null ? '—' : formatPctRatio(valor)}
                    {item?.en_curso ? '*' : ''}
                  </td>
                )
              })}
              {(() => {
                const valorAnual = esARS ? anio.twr_ars : anio.twr_usd
                return (
                  <td
                    className="text-center font-mono font-bold tabular-nums text-app-text py-1.5 pl-2 border-l border-app-border rounded-[4px]"
                    style={heatmapIntensity(valorAnual)}
                  >
                    {valorAnual == null ? '—' : formatPctRatio(valorAnual)}
                    {anio.en_curso ? '*' : ''}
                  </td>
                )
              })()}
            </tr>
          ))}
        </tbody>
      </table>
      {hayMesEnCurso && <div className="text-[9.5px] text-app-text-faint mt-2">* mes en curso</div>}
    </Card>
  )
}
