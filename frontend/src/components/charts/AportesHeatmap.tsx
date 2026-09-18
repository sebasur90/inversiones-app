import type { AporteAnioItem, AporteMesItem } from '../../api'
import { heatmapIntensity } from '../../utils'
import Card from '../ui/Card'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

/** `$1.2k` para que las 13 columnas entren en el ancho de un teléfono. */
export function formatCompactUSD(v: number): string {
  const abs = Math.abs(v)
  const signo = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${signo}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `${signo}$${(abs / 1000).toFixed(0)}k`
  if (abs >= 1000) return `${signo}$${(abs / 1000).toFixed(1)}k`
  return `${signo}$${abs.toFixed(0)}`
}

/** Calendario año × mes del aporte neto. Misma tabla que `RendimientoHeatmap`, pero la
 *  intensidad es relativa al mejor mes cerrado (el récord satura, el resto escala), no un % fijo. */
export default function AportesHeatmap({ meses, anios }: { meses: AporteMesItem[]; anios: AporteAnioItem[] }) {
  const porClave = new Map<string, AporteMesItem>()
  let maxAbs = 0
  for (const item of meses) {
    if (item.futuro) continue
    porClave.set(item.mes, item)
    if (!item.en_curso) maxAbs = Math.max(maxAbs, Math.abs(item.neto_usd))
  }
  const aniosOrdenados = [...anios].sort((a, b) => b.anio - a.anio)
  const maxAnual = Math.max(...aniosOrdenados.map(a => Math.abs(a.total_usd)), 0)
  const hayMesEnCurso = meses.some(m => m.en_curso)
  // heatmapIntensity espera un ratio y satura en capPct=100 → ratio 1 = el máximo.
  const ratio = (v: number, max: number) => (max > 0 ? v / max : 0)

  return (
    <Card className="mb-4 overflow-x-auto">
      <table className="w-full text-label border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-app-surface text-left text-app-text-faint font-bold uppercase text-label pb-2 pr-2">
              Año
            </th>
            {MESES.map(m => (
              <th key={m} className="text-center text-app-text-faint font-bold uppercase text-label pb-2 px-0.5 min-w-[44px]">
                {m}
              </th>
            ))}
            <th className="text-center text-app-text-faint font-bold uppercase text-label pb-2 pl-2 border-l border-app-border min-w-[56px]">
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {aniosOrdenados.map(anio => (
            <tr key={anio.anio}>
              <td className="sticky left-0 z-10 bg-app-surface font-semibold text-app-text py-1 pr-2">{anio.anio}</td>
              {MESES.map((_, idx) => {
                const item = porClave.get(`${anio.anio}-${String(idx + 1).padStart(2, '0')}`)
                return (
                  <td
                    key={idx}
                    className="text-center font-mono tabular-nums text-app-text py-1.5 px-0.5 rounded-[4px]"
                    style={item ? heatmapIntensity(ratio(item.neto_usd, maxAbs), 100) : undefined}
                    title={item ? `${item.mes}: ${item.neto_usd.toFixed(2)} USD` : undefined}
                  >
                    {item ? formatCompactUSD(item.neto_usd) : '—'}
                    {item?.en_curso ? '*' : ''}
                  </td>
                )
              })}
              <td
                className="text-center font-mono font-bold tabular-nums text-app-text py-1.5 pl-2 border-l border-app-border rounded-[4px]"
                style={heatmapIntensity(ratio(anio.total_usd, maxAnual), 100)}
              >
                {formatCompactUSD(anio.total_usd)}
                {anio.en_curso ? '*' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hayMesEnCurso && <div className="text-label text-app-text-faint mt-2">* mes en curso</div>}
    </Card>
  )
}
