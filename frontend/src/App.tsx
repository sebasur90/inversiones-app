import { useEffect, useRef } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { InversionesProvider, useInversionesContext } from './context/InversionesContext'
import { IconSprite } from './components/icons/Icons'
import Splash from './components/layout/Splash'
import AppShell from './components/layout/AppShell'
import Toast from './components/ui/Toast'
import Modal from './components/ui/Modal'
import Resumen from './pages/Resumen'
import Exposicion from './pages/Exposicion'
import Movimientos from './pages/Movimientos'
import Posiciones from './pages/Posiciones'
import TickerDetalle from './pages/TickerDetalle'
import Objetivo from './pages/Objetivo'
import Precios from './pages/Precios'
import IndicadoresMacro from './pages/IndicadoresMacro'
import Vencimientos from './pages/Vencimientos'
import Comparador from './pages/Comparador'
import Comisiones from './pages/Comisiones'
import Patrimonio from './pages/Patrimonio'
import Rendimiento from './pages/Rendimiento'

function SyncResultModal() {
  const { syncSheetOpen, closeSyncSheet, syncErrors, syncWarnings, syncResumenTexto } = useInversionesContext()
  const titulo = syncErrors.length > 0 ? `Sincronización con ${syncErrors.length} fila${syncErrors.length > 1 ? 's' : ''} inválida${syncErrors.length > 1 ? 's' : ''}` : 'Sincronización completada'

  return (
    <Modal open={syncSheetOpen} onClose={closeSyncSheet} title={titulo}>
      <p className="text-[13px] text-app-text mb-4">
        Se cargaron: <strong>{syncResumenTexto}</strong>
      </p>
      {syncErrors.length > 0 && (
        <div className="mb-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Filas con errores</div>
          <ul className="flex flex-col gap-1.5">
            {syncErrors.map((e, i) => (
              <li key={i} className="text-[12.5px] text-app-text bg-app-coral-soft rounded-lg px-3 py-2">
                <strong>Fila {e.fila}:</strong> {e.motivo}
              </li>
            ))}
          </ul>
        </div>
      )}
      {syncWarnings.length > 0 && (
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Advertencias</div>
          <ul className="flex flex-col gap-1.5">
            {syncWarnings.map((e, i) => (
              <li key={i} className="text-[12.5px] text-app-text bg-app-gold-soft rounded-lg px-3 py-2">
                {e.motivo}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  )
}

function useVolverAInicioAlReabrir() {
  const navigate = useNavigate()
  const salioDeLaApp = useRef(false)

  useEffect(() => {
    function onVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        salioDeLaApp.current = true
      } else if (document.visibilityState === 'visible' && salioDeLaApp.current) {
        salioDeLaApp.current = false
        navigate('/resumen', { replace: true })
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [navigate])
}

function Root() {
  const { sinDatos, toast, dismissToast } = useInversionesContext()
  useVolverAInicioAlReabrir()

  return (
    <>
      {sinDatos ? (
        <Splash />
      ) : (
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/resumen" replace />} />
            <Route path="resumen" element={<Resumen />} />
            <Route path="exposicion" element={<Exposicion />} />
            <Route path="movimientos" element={<Movimientos />} />
            <Route path="posiciones" element={<Posiciones />} />
            <Route path="ticker/:ticker" element={<TickerDetalle />} />
            <Route path="objetivo" element={<Objetivo />} />
            <Route path="precios" element={<Precios />} />
            <Route path="indicadores" element={<IndicadoresMacro />} />
            <Route path="vencimientos" element={<Vencimientos />} />
            <Route path="comparar" element={<Comparador />} />
            <Route path="comisiones" element={<Comisiones />} />
            <Route path="patrimonio" element={<Patrimonio />} />
            <Route path="rendimiento" element={<Rendimiento />} />
            <Route path="*" element={<Navigate to="/resumen" replace />} />
          </Route>
        </Routes>
      )}
      <Toast message={toast?.message ?? null} tone={toast?.tone} onDone={dismissToast} />
      <SyncResultModal />
    </>
  )
}

export default function App() {
  return (
    <InversionesProvider>
      <IconSprite />
      <Root />
    </InversionesProvider>
  )
}
