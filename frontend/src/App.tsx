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
import Rebalanceo from './pages/Rebalanceo'
import Riesgo from './pages/Riesgo'
import PerformanceRelativa from './pages/PerformanceRelativa'
import Contribucion from './pages/Contribucion'
import Diagnostico from './pages/Diagnostico'
import CalidadDatos from './pages/CalidadDatos'
import Simulador from './pages/Simulador'
import BenchmarksComparacion from './pages/BenchmarksComparacion'
import Mas from './pages/Mas'

function SyncResultModal() {
  const { syncSheetOpen, closeSyncSheet, syncIssues, syncHealthScore, syncResultado, syncResumenTexto } = useInversionesContext()
  const navigate = useNavigate()

  const titulo =
    syncResultado === 'con_errores'
      ? 'Sincronización con errores'
      : syncResultado === 'con_advertencias'
        ? 'Sincronización con advertencias'
        : 'Sincronización completada'

  const criticalCount = syncIssues.filter(i => i.severidad === 'critico').length
  const warningCount = syncIssues.filter(i => i.severidad === 'advertencia').length

  return (
    <Modal open={syncSheetOpen} onClose={closeSyncSheet} title={titulo}>
      <p className="text-[13px] text-app-text mb-3">
        Se cargaron: <strong>{syncResumenTexto}</strong>
      </p>
      {syncHealthScore !== null && (
        <div className="mb-4 p-3 bg-app-surface-2 rounded-lg">
          <div className="text-[12px] font-semibold text-app-text">
            Calidad: <span className="text-[18px]">{syncHealthScore}</span>/100
          </div>
          {syncResultado !== 'ok' && (
            <div className="text-[11px] text-app-text-dim mt-1">
              {criticalCount > 0 && <div>{criticalCount} error(es) crítico(s)</div>}
              {warningCount > 0 && <div>{warningCount} advertencia(s)</div>}
            </div>
          )}
        </div>
      )}
      {syncIssues.length > 0 && (
        <div className="mb-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Problemas detectados</div>
          <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
            {syncIssues.slice(0, 8).map((issue, i) => (
              <div key={i} className="text-[12px] text-app-text bg-app-surface-2 rounded-lg px-3 py-2">
                <strong>{issue.tab}</strong> {issue.fila && `/ fila ${issue.fila}`}: {issue.mensaje}
              </div>
            ))}
          </div>
          {syncIssues.length > 8 && (
            <button
              onClick={() => {
                closeSyncSheet()
                navigate('/calidad-datos')
              }}
              className="mt-2 text-[12px] text-app-link hover:underline"
            >
              Ver detalle completo ({syncIssues.length - 8} más) →
            </button>
          )}
        </div>
      )}
    </Modal>
  )
}

// Volver a la app después de un rato equivale a abrirla de nuevo, y ahí el Resumen es el
// mejor punto de partida. Pero cambiar de app unos segundos (mirar una cotización, responder
// un mensaje) no debería costar el lugar donde estabas.
const MS_PARA_VOLVER_AL_INICIO = 5 * 60 * 1000

function useVolverAInicioAlReabrir() {
  const navigate = useNavigate()
  const salidaEnMs = useRef<number | null>(null)

  useEffect(() => {
    function onVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        salidaEnMs.current = Date.now()
      } else if (document.visibilityState === 'visible' && salidaEnMs.current !== null) {
        const ausente = Date.now() - salidaEnMs.current
        salidaEnMs.current = null
        if (ausente >= MS_PARA_VOLVER_AL_INICIO) {
          navigate('/resumen', { replace: true })
        }
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
            <Route path="rebalanceo" element={<Rebalanceo />} />
            <Route path="riesgo" element={<Riesgo />} />
            <Route path="performance-relativa" element={<PerformanceRelativa />} />
            <Route path="contribucion" element={<Contribucion />} />
            <Route path="diagnostico" element={<Diagnostico />} />
            <Route path="calidad-datos" element={<CalidadDatos />} />
            <Route path="simulador" element={<Simulador />} />
            <Route path="benchmarks-comparacion" element={<BenchmarksComparacion />} />
            <Route path="mas" element={<Mas />} />
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
