import type { ReactNode } from 'react'
import { Icon } from '../icons/Icons'

export default function Chip({ children, onRemove }: { children: ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1.5 bg-app-gold-soft text-app-gold rounded-[9px] px-2.5 py-1.5 text-label font-bold">
      {children}
      {onRemove && (
        <button onClick={onRemove} aria-label="Quitar filtro" className="flex items-center">
          <Icon name="close" className="w-3.5 h-3.5" />
        </button>
      )}
    </span>
  )
}
