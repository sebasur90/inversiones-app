import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react'
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
  /**
   * Se incrementa después de cada sincronización. Las pantallas que todavía traen sus datos
   * con `useEffect` propio lo usan como dependencia para volver a pedirlos; las migradas a
   * React Query no lo necesitan (`sincronizar` invalida la caché de queries).
   */
  syncVersion: number
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
  const [syncVersion, setSyncVersion] = useState(0)

  const { sincronizar } = inversiones

  const triggerSync = useCallback(async () => {
    try {
      const resultado = await sincronizar()
      const resumenTexto = `${resultado.movimientos} movimientos, ${resultado.instrumentos} instrumentos, ${resultado.precios} precios`
      setSyncIssues(resultado.issues)
      setSyncHealthScore(resultado.health_score)
      setSyncResultado(resultado.resultado)
      setSyncResumenTexto(resumenTexto)
      // Avisa a las pantallas que todavía no usan React Query que vuelvan a pedir sus datos
      setSyncVersion(v => v + 1)
      if (resultado.issues.length > 0) {
        setSyncSheetOpen(true)
      } else {
        setToast({ message: `Sincronizado: ${resumenTexto}.`, tone: 'success' })
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setToast({ message: detail || 'Error al sincronizar el Google Sheet', tone: 'error' })
    }
  }, [sincronizar])

  const showToast = useCallback(
    (message: string, tone: 'success' | 'error' = 'success') => setToast({ message, tone }),
    [],
  )
  const dismissToast = useCallback(() => setToast(null), [])
  const closeSyncSheet = useCallback(() => setSyncSheetOpen(false), [])

  // Memoizado: sin esto el value se recreaba en cada render y hacía re-renderizar a todos
  // los consumidores (21 pantallas, varias con gráficos de recharts).
  const value: InversionesContextValue = useMemo(
    () => ({
      ...inversiones,
      triggerSync,
      toast,
      showToast,
      dismissToast,
      syncSheetOpen,
      closeSyncSheet,
      syncIssues,
      syncHealthScore,
      syncResultado,
      syncResumenTexto,
      syncVersion,
    }),
    [
      inversiones, triggerSync, toast, showToast, dismissToast, syncSheetOpen, closeSyncSheet,
      syncIssues, syncHealthScore, syncResultado, syncResumenTexto, syncVersion,
    ],
  )

  return <InversionesContext.Provider value={value}>{children}</InversionesContext.Provider>
}

export function useInversionesContext() {
  const ctx = useContext(InversionesContext)
  if (!ctx) throw new Error('useInversionesContext debe usarse dentro de <InversionesProvider>')
  return ctx
}
