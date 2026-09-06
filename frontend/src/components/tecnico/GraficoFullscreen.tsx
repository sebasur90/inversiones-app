import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from '../icons/Icons'

const FOCUSABLES =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Overlay `fixed inset-0` de pantalla completa para el gráfico técnico: mismo patrón de foco
 * atrapado + Escape que `Modal.tsx`, pero sin usar `Modal` (está limitado a `max-w-md` y
 * `max-h-[85vh]`, pensado para hojas de acción, no para un gráfico a ancho completo). */
export default function GraficoFullscreen({
  open, onClose, title, children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const disparadorRef = useRef<HTMLElement | null>(null)

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
    const primero = panelRef.current?.querySelector<HTMLElement>(FOCUSABLES)
    if (primero && !panelRef.current?.contains(document.activeElement)) primero.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      disparadorRef.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div ref={panelRef} role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 bg-app-bg flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-app-border shrink-0">
        <h2 className="font-display text-heading font-semibold text-app-text">{title}</h2>
        <button onClick={onClose} aria-label="Cerrar" className="w-8 h-8 rounded-full flex items-center justify-center bg-app-surface-2 text-app-text-dim">
          <Icon name="close" className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">{children}</div>
    </div>
  )
}
