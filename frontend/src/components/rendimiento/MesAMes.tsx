import type { RendimientoMensualOut } from '../../api'
import { formatPctRatio, heatmapIntensity } from '../../utils'
import { MESES_CORTOS } from '../../utils/fechas'
import Card from '../ui/Card'

/**
 * Mapa de calor mensual pensado para el ancho del teléfono: un bloque por año con los meses en dos
 * filas de seis (la tabla de 14 columnas anterior obligaba a deslizar de costado). Cada celda lleva
 * el valor escrito, así que el color es un refuerzo y no la única señal.
 */
export default function MesAMes({ datos, esARS }: { datos: RendimientoMensualOut; esARS: boolean }) {
  const valorDe = (m: { twr_ars: number | null; twr_usd: number | null }) => (esARS ? m.twr_ars : m.twr_usd)

  const porClave = new Map(datos.meses.map(m => [`${m.anio}-${m.mes}`, m]))
  const anios = [...datos.anios].sort((a, b) => b.anio - a.anio)
  const conValor = datos.meses.filter(m => valorDe(m) != null)
  const mejor = conValor.length ? conValor.reduce((a, b) => (valorDe(b)! > valorDe(a)! ? b : a)) : null
  const peor = conValor.length ? conValor.reduce((a, b) => (valorDe(b)! < valorDe(a)! ? b : a)) : null
  const etiqueta = (m: { anio: number; mes: number }) => `${MESES_CORTOS[m.mes - 1].toLowerCase()} ${m.anio}`

  return (
    <Card className="flex flex-col gap-4">
      {anios.map(anio => {
        const total = valorDe(anio)
        return (
          <div key={anio.anio} className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <span className="text-body font-bold text-app-text">{anio.anio}</span>
              <span className="text-caption text-app-text-dim">
                En el año{' '}
                <strong className={`font-mono tabular-nums ${total == null ? 'text-app-text' : total >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
                  {formatPctRatio(total)}{anio.en_curso ? '*' : ''}
                </strong>
              </span>
            </div>
            <div className="grid grid-cols-6 gap-1">
              {MESES_CORTOS.map((mes, idx) => {
                const item = porClave.get(`${anio.anio}-${idx + 1}`)
                const valor = item ? valorDe(item) : null
                return (
                  <div
                    key={mes}
                    className={`h-[52px] rounded-lg flex flex-col items-center justify-center gap-0.5 ${valor == null ? 'border border-dashed border-app-border' : ''}`}
                    style={heatmapIntensity(valor)}
                  >
                    <span className={`text-label ${valor == null ? 'text-app-text-faint' : 'text-app-text'}`}>{mes}</span>
                    {valor != null && (
                      <span className="font-mono text-label font-bold tabular-nums text-app-text">
                        {formatPctRatio(valor).replace('%', '')}{item?.en_curso ? '*' : ''}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {mejor && peor && (
        <div className="flex justify-between gap-3 text-caption text-app-text-dim">
          <span>Mejor mes: <strong className="text-app-text">{etiqueta(mejor)}</strong></span>
          <span>Peor mes: <strong className="text-app-text">{etiqueta(peor)}</strong></span>
        </div>
      )}
      {datos.meses.some(m => m.en_curso) && <div className="text-label text-app-text-faint">* período en curso</div>}
    </Card>
  )
}
