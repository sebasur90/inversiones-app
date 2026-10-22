import type { CarteraInfo } from '../../api'

const CHIP = 'shrink-0 min-h-9 px-3.5 rounded-full text-body whitespace-nowrap transition-colors'

/**
 * Selector de cartera en una fila de chips, arriba de todo: cambia todo lo que hay en la pantalla,
 * así que no puede estar a mitad de camino. Con una sola cartera no se muestra: no hay qué elegir.
 */
export default function CarterasChips({
  carteras,
  seleccionada,
  onSelect,
}: {
  carteras: CarteraInfo[]
  /** `null` es el consolidado. */
  seleccionada: string | null
  onSelect: (nombre: string | null) => void
}) {
  if (carteras.length < 2) return null

  return (
    <div role="group" aria-label="Cartera" className="flex gap-2 overflow-x-auto no-scrollbar -mx-0.5 px-0.5 mb-3.5">
      <button
        onClick={() => onSelect(null)}
        aria-pressed={seleccionada === null}
        className={`${CHIP} font-semibold ${
          seleccionada === null ? 'bg-app-text text-app-bg' : 'border border-app-border text-app-text-dim'
        }`}
      >
        Todas
      </button>
      {carteras.map(c => (
        <button
          key={c.nombre}
          onClick={() => onSelect(c.nombre)}
          aria-pressed={seleccionada === c.nombre}
          className={`${CHIP} font-medium ${
            seleccionada === c.nombre ? 'bg-app-text text-app-bg font-semibold' : 'border border-app-border text-app-text-dim'
          }`}
        >
          {c.nombre}
        </button>
      ))}
    </div>
  )
}
