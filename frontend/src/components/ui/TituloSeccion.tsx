import type { ReactNode } from 'react'
import { Icon, type IconName } from '../icons/Icons'

export type TonoSeccion = 'accent' | 'pos' | 'neg' | 'warn' | 'violet' | 'cyan'

const TONO: Record<TonoSeccion, string> = {
  accent: 'bg-app-accent-soft text-app-accent',
  pos: 'bg-app-pos-soft text-app-pos',
  neg: 'bg-app-neg-soft text-app-neg',
  warn: 'bg-app-warn/15 text-app-warn',
  violet: 'bg-app-violet/15 text-app-violet',
  cyan: 'bg-app-cyan/15 text-app-cyan',
}

/** Título de sección con un ícono en un cuadradito de color: ancla la lectura en pantallas largas. */
export default function TituloSeccion({
  icono,
  tono = 'accent',
  className = 'mb-2.5',
  children,
}: {
  icono: IconName
  tono?: TonoSeccion
  className?: string
  children: ReactNode
}) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <span aria-hidden="true" className={`w-7 h-7 rounded-[9px] flex items-center justify-center shrink-0 ${TONO[tono]}`}>
        <Icon name={icono} className="w-4 h-4" />
      </span>
      <h2 className="text-strong font-bold text-app-text">{children}</h2>
    </div>
  )
}
