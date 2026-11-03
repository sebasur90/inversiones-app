import type { CicloCambioLiderazgo } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import BadgeCuadrante from './BadgeCuadrante'

/** Cambios de cuadrante confirmados (sostenidos varias semanas) de las últimas semanas. Los transitorios no figuran. */
export default function CambiosLiderazgo({ cambios, onSeleccionar }: { cambios: CicloCambioLiderazgo[]; onSeleccionar: (id: string) => void }) {
  if (cambios.length === 0) {
    return (
      <p className="text-caption text-app-text-dim">
        Ningún grupo tuvo un <InfoTooltip term="ciclos_cambio_confirmado" label="cambio confirmado" /> de cuadrante en las últimas semanas.
      </p>
    )
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {cambios.map(c => (
        <li key={`${c.grupo_id}-${c.desde}`}>
          <button
            type="button"
            onClick={() => onSeleccionar(c.grupo_id)}
            className="w-full flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-app-border bg-app-surface px-3 py-2 text-left active:scale-[0.99]"
          >
            <span className="text-caption font-semibold text-app-text">{c.nombre}</span>
            <span className="flex items-center gap-1 text-label">
              <BadgeCuadrante cuadrante={c.de} />
              <span aria-hidden="true" className="text-app-text-faint">→</span>
              <BadgeCuadrante cuadrante={c.a} />
            </span>
            <span className="text-label text-app-text-faint ml-auto whitespace-nowrap">
              desde {fechaCorta(c.desde)} · {c.semanas} sem.
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
