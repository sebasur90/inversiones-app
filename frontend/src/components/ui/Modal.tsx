import type { ReactNode } from 'react'
import { Icon } from '../icons/Icons'

export default function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-app-surface border border-app-border rounded-t-3xl sm:rounded-3xl max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-app-border sticky top-0 bg-app-surface">
          <h2 className="font-display text-[18px] font-semibold text-app-text">{title}</h2>
          <button onClick={onClose} aria-label="Cerrar" className="w-8 h-8 rounded-full flex items-center justify-center bg-app-surface-2 text-app-text-dim">
            <Icon name="close" className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
