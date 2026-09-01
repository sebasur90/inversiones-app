import type { HallazgoItem } from '../../api'
import SeverityBadge, { type Severidad } from './SeverityBadge'

export default function HallazgoCard({ item, onClick }: { item: HallazgoItem; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3.5 mb-2.5 hover:border-app-border-soft transition-colors"
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="font-bold text-body text-app-text truncate">{item.titulo}</div>
        <SeverityBadge severidad={item.severidad as Severidad} />
      </div>
      <div className="text-caption text-app-text-dim">{item.explicacion}</div>
    </button>
  )
}
