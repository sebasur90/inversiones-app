import type { HallazgoItem } from '../../api'

const SEVERIDAD_CLASSES: Record<string, string> = {
  critico: 'bg-app-coral-soft text-app-coral',
  advertencia: 'bg-app-gold-soft text-app-gold',
  info: 'bg-app-teal-soft text-app-teal',
}
const SEVERIDAD_LABELS: Record<string, string> = { critico: 'Crítico', advertencia: 'Atención', info: 'Info' }

export default function HallazgoCard({ item, onClick }: { item: HallazgoItem; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3.5 mb-2.5 hover:border-app-border-soft transition-colors"
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="font-bold text-[13px] text-app-text truncate">{item.titulo}</div>
        <span
          className={`inline-block font-bold text-[9.5px] tracking-wide px-1.5 py-0.5 rounded-[6px] shrink-0 ${SEVERIDAD_CLASSES[item.severidad]}`}
        >
          {SEVERIDAD_LABELS[item.severidad].toUpperCase()}
        </span>
      </div>
      <div className="text-[11.5px] text-app-text-dim">{item.explicacion}</div>
    </button>
  )
}
