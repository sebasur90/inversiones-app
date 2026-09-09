import { useState } from 'react'
import { HELP } from '../../help/content'
import type { HelpKey } from '../../help/content'
import { Icon } from '../icons/Icons'

/** Ficha explicativa de una estrategia del catálogo: qué mira, cuándo compra, cuándo vende y cómo
 * corta pérdidas. Bloque desplegable y no modal como `InfoTooltip`, a propósito: acá el texto es
 * el contexto con el que se lee el backtest que está justo abajo, no una aclaración de un término
 * suelto — conviene poder dejarlo abierto mientras se miran las métricas.
 *
 * El contenido sale de `help/content/estrategias.ts` (clave `estrategia_<slug>`), así que una
 * estrategia propia sin preset de origen simplemente no renderiza nada. */
export default function FichaEstrategia({ preset }: { preset: string | null }) {
  const [abierta, setAbierta] = useState(false)
  const entry = preset ? HELP[`estrategia_${preset}` as HelpKey] : undefined
  if (!entry) return null

  const secciones: [string, string | undefined][] = [
    ['Cuándo compra, cuándo vende y cómo corta pérdidas', entry.howItIsCalculated],
    ['Cuándo suele funcionar', entry.howToInterpret],
    ['Dónde pierde y qué datos necesita', entry.limitations],
  ]

  return (
    <div className="bg-app-surface-2 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setAbierta(a => !a)}
        aria-expanded={abierta}
        className="w-full flex items-start gap-2 px-3 py-2.5 text-left"
      >
        <Icon name="info" className="w-4 h-4 shrink-0 mt-0.5 text-app-text-faint" />
        <span className="flex-1 min-w-0">
          <span className="block font-semibold text-caption text-app-text">{entry.title}</span>
          <span className="block text-label text-app-text-dim mt-0.5">{entry.shortDescription}</span>
        </span>
        <span className="text-label text-app-text-faint shrink-0 mt-0.5">{abierta ? 'Ocultar' : 'Ver más'}</span>
      </button>

      {abierta && (
        <div className="px-3 pb-3 pt-1 space-y-2.5 text-label text-app-text-dim leading-relaxed">
          {secciones.map(([titulo, texto]) =>
            texto ? (
              <div key={titulo}>
                <div className="font-semibold text-app-text mb-0.5">{titulo}</div>
                <p>{texto}</p>
              </div>
            ) : null,
          )}
        </div>
      )}
    </div>
  )
}
