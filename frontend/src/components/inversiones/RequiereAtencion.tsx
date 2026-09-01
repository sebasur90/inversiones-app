import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CalidadDatosOut, DiagnosticoOut, RendimientoPorTickerItem } from '../../api'
import { priorizarHallazgos } from '../../utils/hallazgos'
import { Icon } from '../icons/Icons'
import SeverityBadge, { type Severidad } from './SeverityBadge'

const MAX_HALLAZGOS = 3
const MAX_TICKERS = 4

interface AlertaTicker {
  ticker: string
  nombre: string
  clase: 'stop_loss' | 'objetivo'
  pct: number | null
}

/** Posiciones con el stop-loss disparado o el objetivo de precio alcanzado. */
export function alertasDePrecio(items: RendimientoPorTickerItem[]): AlertaTicker[] {
  const alertas: AlertaTicker[] = []
  for (const it of items) {
    // El stop-loss manda: si una posición disparó ambos, lo urgente es el stop.
    if (it.stop_loss_disparado) {
      alertas.push({ ticker: it.ticker, nombre: it.nombre, clase: 'stop_loss', pct: it.pct_a_stop_loss })
    } else if (it.objetivo_alcanzado) {
      alertas.push({ ticker: it.ticker, nombre: it.nombre, clase: 'objetivo', pct: it.pct_a_objetivo })
    }
  }
  return alertas.sort((a, b) => (a.clase === b.clase ? 0 : a.clase === 'stop_loss' ? -1 : 1))
}

/**
 * Lo que el usuario necesita mirar hoy, junto y en el Resumen. Antes había que entrar a
 * Diagnóstico para ver los hallazgos, a Calidad de datos para los problemas del sync, y al
 * detalle de cada ticker para enterarse de que había saltado un stop-loss.
 *
 * No hace ningún fetch: los tres insumos ya están cargados en la pantalla.
 */
export default function RequiereAtencion({
  diagnostico,
  calidad,
  posiciones,
}: {
  diagnostico: DiagnosticoOut | null
  calidad: CalidadDatosOut | null
  posiciones: RendimientoPorTickerItem[]
}) {
  const navigate = useNavigate()

  const alertas = useMemo(() => alertasDePrecio(posiciones), [posiciones])

  // Los hallazgos de precio ya se muestran ticker por ticker acá arriba: repetirlos como
  // hallazgo agregado ("2 posiciones alcanzaron su stop-loss") sería decir lo mismo dos veces.
  const hallazgos = useMemo(() => {
    const items = diagnostico?.hallazgos ?? []
    const relevantes = items.filter(
      h =>
        h.severidad !== 'info' &&
        !(alertas.length > 0 && (h.tipo === 'stop_loss_disparado' || h.tipo === 'objetivo_precio_alcanzado')),
    )
    return priorizarHallazgos(relevantes).slice(0, MAX_HALLAZGOS)
  }, [diagnostico, alertas.length])

  const issuesCriticos = calidad?.issues.filter(i => i.severidad === 'critico').length ?? 0

  const total = alertas.length + hallazgos.length + (issuesCriticos > 0 ? 1 : 0)
  if (total === 0) return null

  return (
    <section className="mb-4" aria-label="Requiere atención">
      <h3 className="text-strong font-bold text-app-text mb-2">Requiere atención</h3>

      {alertas.slice(0, MAX_TICKERS).map(a => (
        <button
          key={`${a.clase}-${a.ticker}`}
          onClick={() => navigate(`/ticker/${encodeURIComponent(a.ticker)}`)}
          className="w-full flex items-center gap-2.5 text-left bg-app-surface border border-app-border rounded-2xl p-3 mb-2"
        >
          <div
            className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
              a.clase === 'stop_loss' ? 'bg-app-coral-soft text-app-coral' : 'bg-app-teal-soft text-app-teal'
            }`}
          >
            <Icon name={a.clase === 'stop_loss' ? 'down' : 'up'} className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-body font-semibold text-app-text truncate">
              {a.clase === 'stop_loss' ? 'Stop-loss disparado' : 'Objetivo alcanzado'} · {a.ticker}
            </div>
            <div className="text-caption text-app-text-dim truncate">
              {a.nombre}
              {a.pct != null && ` · ${a.pct <= 0 ? 'superado por' : 'falta'} ${Math.abs(a.pct * 100).toFixed(1)}%`}
            </div>
          </div>
          <SeverityBadge severidad={a.clase === 'stop_loss' ? 'critico' : 'info'} />
        </button>
      ))}

      {alertas.length > MAX_TICKERS && (
        <button onClick={() => navigate('/posiciones')} className="text-caption font-semibold text-app-text-dim mb-2">
          Ver las {alertas.length - MAX_TICKERS} alertas restantes →
        </button>
      )}

      {hallazgos.map(h => (
        <button
          key={`${h.tipo}-${h.titulo}`}
          onClick={() => navigate(h.pantalla || '/diagnostico')}
          className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3 mb-2"
        >
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <div className="text-body font-semibold text-app-text truncate">{h.titulo}</div>
            <SeverityBadge severidad={h.severidad as Severidad} />
          </div>
          <div className="text-caption text-app-text-dim line-clamp-2">{h.explicacion}</div>
        </button>
      ))}

      {issuesCriticos > 0 && (
        <button
          onClick={() => navigate('/calidad-datos')}
          className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3 mb-2"
        >
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <div className="text-body font-semibold text-app-text">Errores en el último sync</div>
            <SeverityBadge severidad="critico" />
          </div>
          <div className="text-caption text-app-text-dim">
            {issuesCriticos} problema{issuesCriticos !== 1 ? 's' : ''} crítico{issuesCriticos !== 1 ? 's' : ''} en los
            datos: los números de esta pantalla pueden estar incompletos.
          </div>
        </button>
      )}
    </section>
  )
}
