import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Icon, type IconName } from '../icons/Icons'

/** Acceso a una pantalla relacionada: botón redondeado con ícono y flecha que avanza al pasar el mouse. */
export default function BotonAcceso({
  icono,
  colorIcono = 'text-app-accent',
  children,
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { icono: IconName; colorIcono?: string; children: ReactNode }) {
  return (
    <button
      className={`group inline-flex items-center gap-2 min-h-10 px-3.5 rounded-full bg-app-surface border border-app-border text-caption font-semibold text-app-text-dim transition-[background-color,border-color,color,transform] duration-150 hover:border-app-accent/50 hover:bg-app-surface-2 hover:text-app-text active:scale-[0.97] ${className}`}
      {...rest}
    >
      <Icon name={icono} className={`w-4 h-4 ${colorIcono}`} />
      {children}
      <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90 text-app-text-faint transition-transform duration-150 group-hover:translate-x-0.5" />
    </button>
  )
}
