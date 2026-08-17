import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { useInversiones } from '../hooks/useInversiones'
import type { SyncIssueOut } from '../api'

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
  syncIssues: SyncIssueOut[]
  syncHealthScore: number | null
  syncResultado: string
  syncResumenTexto: string
}

const InversionesContext = createContext<InversionesContextValue | null>(null)

export function InversionesProvider({ children }: { children: ReactNode }) {
  const inversiones = useInversiones()
  const [toast, setToast] = useState<ToastState | null>(null)
  const [syncSheetOpen, setSyncSheetOpen] = useState(false)
  const [syncIssues, setSyncIssues] = useState<SyncIssueOut[]>([])
  const [syncHealthScore, setSyncHealthScore] = useState<number | null>(null)
  const [syncResultado, setSyncResultado] = useState('')
  const [syncResumenTexto, setSyncResumenTexto] = useState('')

  const triggerSync = useCallback(async () => {
    try {
      const resultado = await inversiones.sincronizar()
      const resumenTexto = `${resultado.movimientos} movimientos, ${resultado.instrumentos} instrumentos, ${resultado.precios} precios`
      setSyncIssues(resultado.issues)
      setSyncHealthScore(resultado.health_score)
      setSyncResultado(resultado.resultado)
      setSyncResumenTexto(resumenTexto)
      if (resultado.issues.length > 0) {
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
    syncIssues,
    syncHealthScore,
    syncResultado,
    syncResumenTexto,
  }

  return <InversionesContext.Provider value={value}>{children}</InversionesContext.Provider>
}

export function useInversionesContext() {
  const ctx = useContext(InversionesContext)
  if (!ctx) throw new Error('useInversionesContext debe usarse dentro de <InversionesProvider>')
  return ctx
}
