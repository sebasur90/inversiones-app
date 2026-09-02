import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CalidadDatosOut, DiagnosticoOut, RendimientoPorTickerItem } from '../../api'
import { priorizarHallazgos } from '../../utils/hallazgos'
import { alertasDePrecio, type EstadoAlerta } from '../../utils/alertasPrecio'
import { Icon, type IconName } from '../icons/Icons'
import SeverityBadge, { type Severidad } from './SeverityBadge'
import AlertaPrecioBadge from './AlertaPrecioBadge'

const MAX_HALLAZGOS = 3
const MAX_TICKERS = 4

// Los cruces consumados llevan la flecha de la dirección del precio; los avisos de
// proximidad, el triángulo de atención: todavía no pasó nada, sólo falta poco.
function iconoDeEstado(estado: EstadoAlerta): IconName {
  if (estado === 'stop_loss_disparado') return 'down'
  if (estado === 'objetivo_alcanzado') return 'up'
  return 'alert'
}

const FONDO_SEVERIDAD: Record<Severidad, string> = {
  critico: 'bg-app-coral-soft text-app-coral',
  advertencia: 'bg-app-gold-soft text-app-gold',
  info: 'bg-app-teal-soft text-app-teal',
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
  umbralProximidad,
}: {
  diagnostico: DiagnosticoOut | null
  calidad: CalidadDatosOut | null
  posiciones: RendimientoPorTickerItem[]
  umbralProximidad: number
}) {
  const navigate = useNavigate()

  const alertas = useMemo(() => alertasDePrecio(posiciones, umbralProximidad), [posiciones, umbralProximidad])

  // Los hallazgos de precio ya se muestran ticker por ticker acá arriba: repetirlos como
  // hallazgo agregado ("2 posiciones alcanzaron su stop-loss") sería decir lo mismo dos veces.
  // Se compara contra los cruces consumados, no contra las alertas de proximidad: el
  // diagnóstico sólo emite estos hallazgos cuando el precio ya cruzó el nivel, así que un
  // "cerca del stop" no debe tapar un "stop-loss disparado" agregado.
  const hayCruce = useMemo(
    () => ({
      stop_loss_disparado: alertas.some(a => a.estado === 'stop_loss_disparado'),
      objetivo_precio_alcanzado: alertas.some(a => a.estado === 'objetivo_alcanzado'),
    }),
    [alertas],
  )

  const hallazgos = useMemo(() => {
    const items = diagnostico?.hallazgos ?? []
    const relevantes = items.filter(
      h => h.severidad !== 'info' && !hayCruce[h.tipo as keyof typeof hayCruce],
    )
    return priorizarHallazgos(relevantes).slice(0, MAX_HALLAZGOS)
  }, [diagnostico, hayCruce])

  const issuesCriticos = calidad?.issues.filter(i => i.severidad === 'critico').length ?? 0

  const total = alertas.length + hallazgos.length + (issuesCriticos > 0 ? 1 : 0)
  if (total === 0) return null

  return (
    <section className="mb-4" aria-label="Requiere atención">
      <h3 className="text-strong font-bold text-app-text mb-2">Requiere atención</h3>

      {alertas.slice(0, MAX_TICKERS).map(a => (
        <button
          key={`${a.estado}-${a.ticker}`}
          onClick={() => navigate(`/ticker/${encodeURIComponent(a.ticker)}`)}
          className="w-full flex items-center gap-2.5 text-left bg-app-surface border border-app-border rounded-2xl p-3 mb-2"
        >
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${FONDO_SEVERIDAD[a.severidad]}`}>
            <Icon name={iconoDeEstado(a.estado)} className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-body font-semibold text-app-text truncate">{a.ticker}</div>
            <div className="text-caption text-app-text-dim truncate">{a.nombre}</div>
          </div>
          <AlertaPrecioBadge estado={a.estado} pct={a.pct} />
        </button>
      ))}

      {alertas.length > MAX_TICKERS && (
        <button
          onClick={() => navigate('/posiciones?alerta=con_alerta')}
          className="text-caption font-semibold text-app-text-dim mb-2"
        >
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
