import type { AporteAnioItem, AporteMesItem } from '../../api'
import { heatmapIntensity } from '../../utils'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { MASCARA } from '../../utils/formatoMonto'
import Card from '../ui/Card'
import { MESES_CORTOS } from '../../utils/fechas'

/**
 * Texto del tooltip de una celda: monto y, si había objetivo vigente, cuánto se cumplió.
 * Con el modo privacidad los dos importes se tapan; el cumplimiento en % y el estado quedan.
 */
function detalleMes(item: AporteMesItem, conObjetivo: boolean, ocultos: boolean): string {
  const importe = (v: number) => (ocultos ? MASCARA : v.toFixed(2))
  const base = `${item.mes}: ${importe(item.neto_usd)} USD`
  if (!conObjetivo || item.objetivo_usd == null) return base
  const pct = item.cumplimiento_pct != null ? ` (${item.cumplimiento_pct.toFixed(0)}%)` : ''
  const estado = item.cumple_objetivo == null ? 'en curso' : item.cumple_objetivo ? 'cumplido' : 'no alcanzado'
  return `${base}\nObjetivo ${ocultos ? MASCARA : item.objetivo_usd.toFixed(0)} USD${pct} · ${estado}`
}

/** Calendario año × mes del aporte neto. Misma tabla que `RendimientoHeatmap`, pero la
 *  intensidad es relativa al mejor mes cerrado (el récord satura, el resto escala), no un % fijo.
 *
 *  Con `mostrarObjetivo`, los meses que alcanzaron el objetivo vigente llevan un anillo: la
 *  pestaña Análisis lo omite y se ve exactamente igual que siempre. */
export default function AportesHeatmap({
  meses,
  anios,
  mostrarObjetivo = false,
}: {
  meses: AporteMesItem[]
  anios: AporteAnioItem[]
  mostrarObjetivo?: boolean
}) {
  // El tinte de las celdas se mantiene con el modo privacidad: es magnitud relativa al mejor mes,
  // sin el tinte esto deja de ser un heatmap.
  const { compactoFino, ocultos } = useFormatoFijo('USD')
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
  const hayObjetivo = meses.some(m => m.cumple_objetivo === true)
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
            {MESES_CORTOS.map(m => (
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
              {MESES_CORTOS.map((_, idx) => {
                const item = porClave.get(`${anio.anio}-${String(idx + 1).padStart(2, '0')}`)
                const cumplio = mostrarObjetivo && item?.cumple_objetivo === true
                return (
                  <td
                    key={idx}
                    className={`text-center font-mono tabular-nums text-app-text py-1.5 px-0.5 rounded-[4px] ${
                      cumplio ? 'ring-1 ring-inset ring-app-pos' : ''
                    }`}
                    style={item ? heatmapIntensity(ratio(item.neto_usd, maxAbs), 100) : undefined}
                    title={item ? detalleMes(item, mostrarObjetivo, ocultos) : undefined}
                  >
                    {item ? compactoFino(item.neto_usd) : '—'}
                    {item?.en_curso ? '*' : ''}
                  </td>
                )
              })}
              <td
                className="text-center font-mono font-bold tabular-nums text-app-text py-1.5 pl-2 border-l border-app-border rounded-[4px]"
                style={heatmapIntensity(ratio(anio.total_usd, maxAnual), 100)}
              >
                {compactoFino(anio.total_usd)}
                {anio.en_curso ? '*' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-label text-app-text-faint mt-2 flex flex-wrap gap-x-3">
        {hayMesEnCurso && <span>* mes en curso</span>}
        {mostrarObjetivo && hayObjetivo && (
          <span>
            <span className="inline-block w-2.5 h-2.5 rounded-[3px] ring-1 ring-inset ring-app-pos align-middle mr-1" />
            objetivo cumplido
          </span>
        )}
      </div>
    </Card>
  )
}
