import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { useInversiones } from '../hooks/useInversiones'
import type { SyncErrorItem } from '../api'

interface ToastState {
  message: string
  tone: 'success' | 'error'
}

interface InversionesContextValue extends ReturnType<typeof useInversiones> {
  triggerSync: () => Promise<void>
  toast: ToastState | null
  showToast: (message: string, tone?: 'success' | 'error') => void
  dismissToast: () => void
  syncSheetOpen: boolean
  closeSyncSheet: () => void
  syncErrors: SyncErrorItem[]
  syncWarnings: SyncErrorItem[]
  syncResumenTexto: string
}

const InversionesContext = createContext<InversionesContextValue | null>(null)

export function InversionesProvider({ children }: { children: ReactNode }) {
  const inversiones = useInversiones()
  const [toast, setToast] = useState<ToastState | null>(null)
  const [syncSheetOpen, setSyncSheetOpen] = useState(false)
  const [syncErrors, setSyncErrors] = useState<SyncErrorItem[]>([])
  const [syncWarnings, setSyncWarnings] = useState<SyncErrorItem[]>([])
  const [syncResumenTexto, setSyncResumenTexto] = useState('')

  const triggerSync = useCallback(async () => {
    try {
      const resultado = await inversiones.sincronizar()
      const advertencias = resultado.errores.filter(e => e.motivo.startsWith('Advertencia:'))
      const errores = resultado.errores.filter(e => !e.motivo.startsWith('Advertencia:'))
      const resumenTexto = `${resultado.movimientos} movimientos, ${resultado.instrumentos} instrumentos, ${resultado.precios} precios, ${resultado.indices_mercado} fechas con CER/MEP`
      setSyncErrors(errores)
      setSyncWarnings(advertencias)
      setSyncResumenTexto(resumenTexto)
      if (errores.length > 0 || advertencias.length > 0) {
        setSyncSheetOpen(true)
      } else {
        setToast({ message: `Sincronizado: ${resumenTexto}.`, tone: 'success' })
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setToast({ message: detail || 'Error al sincronizar el Google Sheet', tone: 'error' })
    }
  }, [inversiones])

  const value: InversionesContextValue = {
    ...inversiones,
    triggerSync,
    toast,
    showToast: (message: string, tone: 'success' | 'error' = 'success') => setToast({ message, tone }),
    dismissToast: () => setToast(null),
    syncSheetOpen,
    closeSyncSheet: () => setSyncSheetOpen(false),
    syncErrors,
    syncWarnings,
    syncResumenTexto,
  }

  return <InversionesContext.Provider value={value}>{children}</InversionesContext.Provider>
}

export function useInversionesContext() {
  const ctx = useContext(InversionesContext)
  if (!ctx) throw new Error('useInversionesContext debe usarse dentro de <InversionesProvider>')
  return ctx
}
