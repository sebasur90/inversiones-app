import { Icon } from '../icons/Icons'
import { descargarCSV, sufijoFechaHoy, type ValorCelda } from '../../utils/csv'

interface Props {
  /** Nombre base del archivo; se le agrega la fecha de hoy y la extensión. */
  nombre: string
  encabezados: string[]
  /** Se evalúa al hacer click, no en cada render: armar el CSV puede recorrer muchas filas. */
  filas: () => ValorCelda[][]
  className?: string
}

export default function BotonExportarCsv({ nombre, encabezados, filas, className = '' }: Props) {
  return (
    <button
      onClick={() => descargarCSV(`${nombre}-${sufijoFechaHoy()}`, encabezados, filas())}
      className={`inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim ${className}`}
    >
      <Icon name="download" className="w-3.5 h-3.5" />
      Exportar CSV
    </button>
  )
}
