import { useNavigate } from 'react-router-dom'
import type { CalidadDatosOut, DiagnosticoOut } from '../../api'
import { nivelScore, type Nivel, type NivelInfo } from '../../utils/niveles'
import { Icon } from '../icons/Icons'
import Semaforo from '../ui/Semaforo'

const FILA =
  'group w-full flex items-center gap-3 text-left px-3.5 py-3 border-b border-app-border-soft last:border-b-0 transition-colors duration-150 hover:bg-white/[0.035] active:bg-white/[0.06]'

function Fila({
  titulo,
  nivel,
  detalle,
  score,
  onClick,
}: {
  titulo: string
  nivel: NivelInfo | null
  detalle: string
  score: number | null
  onClick: () => void
}) {
  return (
    <button onClick={onClick} className={FILA}>
      <div className="min-w-0 flex-1">
        <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-0.5">{titulo}</div>
        {nivel && <Semaforo nivel={nivel.nivel as Nivel} etiqueta={nivel.etiqueta} className="mb-0.5" />}
        <div className="text-caption text-app-text-dim">{detalle}</div>
      </div>
      <div className="font-display text-metric font-semibold text-app-text shrink-0">
        {score !== null ? Math.round(score) : '—'}
        <span className="text-body text-app-text-dim">/100</span>
      </div>
      <Icon name="chevron" className="w-4 h-4 -rotate-90 text-app-text-dim shrink-0 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-app-text" />
    </button>
  )
}

/**
 * Los dos scores de 0 a 100 en una sola tarjeta, con el estado en palabras. El detalle de lo que
 * los mueve ya está en "Para mirar hoy"; esto es el termómetro, no el listado.
 */
export default function EstadoGeneral({
  diagnostico,
  calidad,
}: {
  diagnostico: DiagnosticoOut | null
  calidad: CalidadDatosOut | null
}) {
  const navigate = useNavigate()
  if (!diagnostico && !calidad?.ultimo_sync) return null

  const hallazgos = diagnostico?.hallazgos.length ?? 0
  const problemas = calidad?.issues.length ?? 0

  return (
    <section className="mb-4" aria-label="Estado general">
      <h3 className="flex items-center gap-1.5 text-strong font-bold text-app-text mb-2">
        <Icon name="shield" className="w-4 h-4 text-app-accent" />
        Estado general
      </h3>
      <div className="bg-app-surface border border-app-border rounded-2xl overflow-hidden">
        {diagnostico && (
          // "Diagnóstico", no "Salud de cartera": el score y los hallazgos salen de `getDiagnostico`
          // y la fila lleva a /diagnostico. Con el nombre de la otra pantalla (/salud, que no tiene
          // score) el destino contradecía la etiqueta.
          <Fila
            titulo="Diagnóstico"
            nivel={nivelScore(diagnostico.salud.score_total)}
            detalle={`${hallazgos} hallazgo${hallazgos !== 1 ? 's' : ''}`}
            score={diagnostico.salud.score_total}
            onClick={() => navigate('/diagnostico')}
          />
        )}
        {calidad?.ultimo_sync && (
          <Fila
            titulo="Calidad de datos"
            nivel={nivelScore(calidad.ultimo_sync.health_score)}
            detalle={`${problemas} problema${problemas !== 1 ? 's' : ''}`}
            score={calidad.ultimo_sync.health_score}
            onClick={() => navigate('/calidad-datos')}
          />
        )}
      </div>
    </section>
  )
}
