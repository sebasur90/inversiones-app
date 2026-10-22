import { Icon } from '../icons/Icons'

/**
 * Campo de búsqueda de las listas: aro azul al enfocarlo, borde al pasar el mouse y una ✕ para
 * borrar lo escrito sin tener que seleccionar el texto en el celular.
 */
export default function CampoBusqueda({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className = '',
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  ariaLabel: string
  className?: string
}) {
  return (
    <label
      className={`flex-1 min-w-0 flex items-center gap-2.5 bg-app-surface border border-app-border rounded-xl h-11 pl-3 pr-1.5 text-app-text-faint transition-[border-color,box-shadow] duration-150 hover:border-white/20 focus-within:border-app-accent focus-within:shadow-[0_0_0_3px_rgba(59,130,246,0.25)] ${className}`}
    >
      <Icon name="search" className="w-4 h-4 shrink-0" />
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        aria-label={ariaLabel}
        placeholder={placeholder}
        className="flex-1 min-w-0 bg-transparent outline-none text-caption text-app-text placeholder:text-app-text-faint"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Borrar búsqueda"
          className="w-7 h-7 rounded-full flex items-center justify-center text-app-text-dim shrink-0 transition-[background-color,color,transform] duration-150 hover:bg-white/10 hover:text-app-text active:scale-90"
        >
          <Icon name="close" className="w-3.5 h-3.5" />
        </button>
      )}
    </label>
  )
}
