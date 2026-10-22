import { useNavigate } from 'react-router-dom'
import { formatPctRatio } from '../../utils'
import { mayoresMovimientos, type VariacionDiaCartera } from '../../utils/resumenCartera'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { Icon } from '../icons/Icons'

/**
 * Las posiciones que más movieron la cartera en el último día, para los dos lados. Ordenadas por
 * efecto en plata, no por porcentaje: ver `mayoresMovimientos`. No hace fetch: sale de la
 * variación diaria que ya trae cada posición.
 */
export default function QueSeMovioHoy({
  variacionDia,
  moneda,
}: {
  variacionDia: VariacionDiaCartera | null
  moneda: 'USD' | 'ARS'
}) {
  const navigate = useNavigate()
  const fmt = useFormatoFijo(moneda)
  if (!variacionDia) return null

  const { suben, bajan } = mayoresMovimientos(variacionDia.movimientos)
  const items = [...suben, ...bajan]
  if (items.length === 0) return null

  return (
    <section className="mb-4" aria-label="Qué se movió hoy">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-strong font-bold text-app-text">Qué se movió hoy</h3>
        <span className="text-label text-app-text-dim">vs. cierre anterior</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {items.map(m => {
          const sube = m.efecto > 0
          return (
            <button
              key={m.ticker}
              onClick={() => navigate(`/ticker/${encodeURIComponent(m.ticker)}`)}
              aria-label={`Ver detalle de ${m.ticker} — ${m.nombre}`}
              className="text-left bg-app-surface border border-app-border rounded-[14px] p-3 hover:border-app-border-soft transition-colors"
            >
              <div className="flex items-center justify-between gap-1.5 mb-1.5">
                <span className="font-mono text-body font-bold text-app-text truncate">{m.ticker}</span>
                <span
                  className={`inline-flex items-center gap-0.5 font-mono text-caption font-bold tabular-nums px-1.5 py-0.5 rounded-full shrink-0 ${
                    sube ? 'text-app-pos bg-app-pos-soft' : 'text-app-neg bg-app-neg-soft'
                  }`}
                >
                  <Icon name={sube ? 'up' : 'down'} className="w-2.5 h-2.5" />
                  {formatPctRatio(m.pct)}
                </span>
              </div>
              {/* Con los importes ocultos el efecto en plata se reemplaza por una palabra: un
                  "••••" con signo no dice nada, y sin él se perdería el sentido del movimiento. */}
              <div className="font-mono text-label text-app-text-dim tabular-nums">
                {fmt.ocultos ? (sube ? 'Sube' : 'Baja') : fmt.montoConSigno(m.efecto)}
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}
