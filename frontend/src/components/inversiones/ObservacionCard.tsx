import { useNavigate } from 'react-router-dom'
import type { SaludObservacion } from '../../api'
import SeverityBadge, { type Severidad } from './SeverityBadge'

const SEVERIDAD_A_BADGE: Record<SaludObservacion['severidad'], Severidad> = {
  revisar: 'critico',
  atencion: 'advertencia',
  info: 'info',
}

/** Una "cosa para revisar" de Salud de cartera: qué detectó, con qué valor, contra qué umbral,
 *  de dónde sale el dato, y un botón para ir directo a la pantalla correspondiente.
 *  Misma estética que `HallazgoCard`, con más detalle porque acá no hay un score que ya haya
 *  resumido la severidad. */
export default function ObservacionCard({ item }: { item: SaludObservacion }) {
  const navigate = useNavigate()

  return (
    <div className="bg-app-surface border border-app-border rounded-2xl p-3.5 mb-2.5">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="font-bold text-body text-app-text">{item.titulo}</div>
        <SeverityBadge severidad={SEVERIDAD_A_BADGE[item.severidad]} />
      </div>
      <div className="text-caption text-app-text-dim mb-2.5">{item.detecto}</div>

      <div className="grid grid-cols-3 gap-2 mb-3">
        <div>
          <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Valor</div>
          <div className="text-caption font-mono font-semibold text-app-text">{item.valor}</div>
        </div>
        <div>
          <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Umbral</div>
          <div className="text-caption font-mono text-app-text-dim">{item.umbral}</div>
        </div>
        <div>
          <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Fuente</div>
          <div className="text-caption text-app-text-dim">{item.fuente}</div>
        </div>
      </div>

      <button
        onClick={() => navigate(item.pantalla)}
        className="w-full h-9 rounded-xl border border-app-border text-caption font-bold text-app-text hover:border-app-border-soft transition-colors"
      >
        {item.accion}
      </button>
    </div>
  )
}
