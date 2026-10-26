import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from '../icons/Icons'
import { esDialogoDeArriba } from '../ui/Modal'

const FOCUSABLES =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** `lock`/`unlock` no están en todos los navegadores (ni en todos los `lib.dom` de TypeScript). */
type OrientacionBloqueable = ScreenOrientation & {
  lock?: (orientacion: 'landscape') => Promise<void>
  unlock?: () => void
}

function orientacion(): OrientacionBloqueable | undefined {
  return typeof screen !== 'undefined' ? (screen.orientation as OrientacionBloqueable | undefined) : undefined
}

/** Girar a horizontal sólo se ofrece donde puede funcionar: pantalla táctil con Fullscreen API y
 * bloqueo de orientación (Chrome en Android). En iPhone no existe: ahí se gira el teléfono y los
 * paneles se reacomodan solos (`useAltosGrafico`). */
const PUEDE_GIRAR = typeof window !== 'undefined'
  && !!window.matchMedia?.('(pointer: coarse)').matches
  && typeof document.documentElement.requestFullscreen === 'function'
  && typeof orientacion()?.lock === 'function'

async function salirDePantallaCompleta() {
  orientacion()?.unlock?.()
  if (document.fullscreenElement) await document.exitFullscreen().catch(() => {})
}

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
  const [girado, setGirado] = useState(false)
  // Igual que en `Modal`: con `onClose` como dependencia, cada render de la pantalla re-corría el
  // efecto del foco y se lo sacaba al input del selector de indicadores abierto encima.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  async function alternarGiro() {
    if (girado) {
      await salirDePantallaCompleta()
      setGirado(false)
      return
    }
    try {
      // El bloqueo de orientación exige que el documento esté en pantalla completa.
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen()
      await orientacion()?.lock?.('landscape')
      setGirado(true)
    } catch {
      await salirDePantallaCompleta()
      setGirado(false)
    }
  }

  // Con "atrás" o el gesto del sistema se sale de la pantalla completa del navegador sin pasar por
  // el botón: el estado tiene que enterarse.
  useEffect(() => {
    if (!girado) return
    const alCambiar = () => { if (!document.fullscreenElement) setGirado(false) }
    document.addEventListener('fullscreenchange', alCambiar)
    return () => document.removeEventListener('fullscreenchange', alCambiar)
  }, [girado])

  // Cerrar el gráfico deja el teléfono como estaba.
  useEffect(() => {
    if (open || !girado) return
    void salirDePantallaCompleta()
    setGirado(false)
  }, [open, girado])
  useEffect(() => () => { if (document.fullscreenElement) void salirDePantallaCompleta() }, [])

  useEffect(() => {
    if (!open) return
    disparadorRef.current = document.activeElement as HTMLElement | null

    function onKeyDown(e: KeyboardEvent) {
      if (!esDialogoDeArriba(panelRef.current)) return
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCloseRef.current()
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
  }, [open])

  if (!open) return null

  return (
    <div ref={panelRef} role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 bg-app-bg flex flex-col">
      {/* En el teléfono horizontal cada píxel de alto cuenta: encabezado y márgenes más chicos. */}
      <div className="flex items-center justify-between gap-2 px-4 py-3 [@media(max-height:500px)]:py-1.5 border-b border-app-border shrink-0">
        <h2 className="min-w-0 truncate font-display text-heading [@media(max-height:500px)]:text-title font-semibold text-app-text">{title}</h2>
        <div className="flex items-center gap-2 shrink-0">
          {PUEDE_GIRAR && (
            <button
              type="button" onClick={() => void alternarGiro()}
              className="h-8 px-3 rounded-full bg-app-surface-2 text-label font-semibold text-app-text-dim"
            >
              {girado ? 'Vertical' : 'Girar ↻'}
            </button>
          )}
          <button onClick={onClose} aria-label="Cerrar" className="w-8 h-8 rounded-full flex items-center justify-center bg-app-surface-2 text-app-text-dim">
            <Icon name="close" className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 [@media(max-height:500px)]:px-3 [@media(max-height:500px)]:py-2">{children}</div>
    </div>
  )
}
