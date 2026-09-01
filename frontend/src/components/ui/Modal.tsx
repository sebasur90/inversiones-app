import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from '../icons/Icons'

const FOCUSABLES =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

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
  const panelRef = useRef<HTMLDivElement>(null)
  const disparadorRef = useRef<HTMLElement | null>(null)

  // Escape para cerrar y foco atrapado dentro del panel: con el modal abierto, tabular no
  // debe llevar a los controles de la pantalla que quedó atrás.
  useEffect(() => {
    if (!open) return

    disparadorRef.current = document.activeElement as HTMLElement | null

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panelRef.current) return

      const focusables = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLES))
      if (focusables.length === 0) return

      const primero = focusables[0]
      const ultimo = focusables[focusables.length - 1]
      const activo = document.activeElement

      if (e.shiftKey && (activo === primero || !panelRef.current.contains(activo))) {
        e.preventDefault()
        ultimo.focus()
      } else if (!e.shiftKey && activo === ultimo) {
        e.preventDefault()
        primero.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    // El primer control del panel arranca enfocado (salvo que el contenido ya pidió el foco,
    // como el input del buscador con autoFocus).
    const primero = panelRef.current?.querySelector<HTMLElement>(FOCUSABLES)
    if (primero && !panelRef.current?.contains(document.activeElement)) primero.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      disparadorRef.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full sm:max-w-md bg-app-surface border border-app-border rounded-t-3xl sm:rounded-3xl max-h-[85vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-app-border sticky top-0 bg-app-surface">
          <h2 className="font-display text-heading font-semibold text-app-text">{title}</h2>
          <button onClick={onClose} aria-label="Cerrar" className="w-8 h-8 rounded-full flex items-center justify-center bg-app-surface-2 text-app-text-dim">
            <Icon name="close" className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
