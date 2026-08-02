import type { CarteraInfo } from '../../api'

export default function CarterasScroll({
  carteras,
  seleccionada,
  onSelect,
}: {
  carteras: CarteraInfo[]
  seleccionada: string | null
  onSelect: (nombre: string) => void
}) {
  if (carteras.length === 0) return null
  return (
    <div className="flex gap-2.5 overflow-x-auto no-scrollbar pb-1 -mx-0.5 px-0.5">
      {carteras.map(c => (
        <button
          key={c.nombre}
          onClick={() => onSelect(c.nombre)}
          className={`shrink-0 w-[132px] text-left rounded-[14px] p-3 border transition-colors ${
            seleccionada === c.nombre ? 'bg-app-gold-soft border-app-gold/40' : 'bg-app-surface border-app-border'
          }`}
        >
          <div className="text-[11.5px] font-bold text-app-text-dim mb-1.5 truncate">{c.nombre}</div>
          <div className="font-mono text-[11px] text-app-text-faint tabular-nums">
            {c.ultimo_sync ? `sync ${new Date(c.ultimo_sync).toLocaleDateString('es-AR')}` : 'sin sync'}
          </div>
        </button>
      ))}
    </div>
  )
}
