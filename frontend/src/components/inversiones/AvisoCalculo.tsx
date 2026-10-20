import { useNavigate } from 'react-router-dom'
import { Icon } from '../icons/Icons'

/**
 * Pie de aviso para un número que no se puede calcular bien o que se calculó con un dato
 * incompleto. Mismo estilo que `AvisosValuacion`; `linkCalidad` agrega el atajo a Calidad de datos.
 */
export default function AvisoCalculo({
  mensajes,
  linkCalidad = false,
  className = 'mt-2',
}: {
  mensajes: (string | null | undefined)[]
  linkCalidad?: boolean
  className?: string
}) {
  const navigate = useNavigate()
  const lineas = mensajes.filter((m): m is string => !!m)
  if (lineas.length === 0) return null

  return (
    <div className={`${className} flex items-start gap-1.5 text-label text-app-text-faint`}>
      <Icon name="alert" className="w-3.5 h-3.5 shrink-0 mt-0.5" />
      <div className="flex flex-col gap-0.5">
        {lineas.map(linea => <span key={linea}>{linea}</span>)}
        {linkCalidad && (
          <button onClick={() => navigate('/calidad-datos')} className="self-start font-semibold text-app-accent">
            Ver calidad de datos
          </button>
        )}
      </div>
    </div>
  )
}
