import type { Cuadrante } from '../../api'
import { INFO_CUADRANTE } from './constantes'

/** El estado en palabras Y en color: el color solo no alcanza para quien no distingue rojo de verde. */
export default function BadgeCuadrante({ cuadrante, pendiente = false }: { cuadrante: Cuadrante | null | undefined; pendiente?: boolean }) {
  if (!cuadrante) {
    return <span className="text-label font-semibold text-app-text-faint">Sin estado</span>
  }
  const info = INFO_CUADRANTE[cuadrante]
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-label font-bold whitespace-nowrap"
      style={{ color: info.color, backgroundColor: `${info.color}22` }}
      title={pendiente ? `${info.nombre}: cambio todavía sin confirmar` : info.frase}
    >
      <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: info.color }} />
      {info.nombre}
      {pendiente && <span className="font-semibold opacity-80">· sin confirmar</span>}
    </span>
  )
}
