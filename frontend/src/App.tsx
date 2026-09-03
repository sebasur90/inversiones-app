import { Suspense, lazy, useEffect, useRef } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { InversionesProvider, useInversionesContext } from './context/InversionesContext'
import { queryClient } from './api/queryClient'
import { IconSprite } from './components/icons/Icons'
import Splash from './components/layout/Splash'
import AppShell from './components/layout/AppShell'
import Toast from './components/ui/Toast'
import { useAutoSync } from './hooks/useAutoSync'
import Modal from './components/ui/Modal'
const Resumen = lazy(() => import('./pages/Resumen'))
const Exposicion = lazy(() => import('./pages/Exposicion'))
const Movimientos = lazy(() => import('./pages/Movimientos'))
const Posiciones = lazy(() => import('./pages/Posiciones'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const TickerDetalle = lazy(() => import('./pages/TickerDetalle'))
const Objetivo = lazy(() => import('./pages/Objetivo'))
const Precios = lazy(() => import('./pages/Precios'))
const IndicadoresMacro = lazy(() => import('./pages/IndicadoresMacro'))
const Vencimientos = lazy(() => import('./pages/Vencimientos'))
const FlujoCaja = lazy(() => import('./pages/FlujoCaja'))
const Comparador = lazy(() => import('./pages/Comparador'))
const Comisiones = lazy(() => import('./pages/Comisiones'))
const VistaFiscal = lazy(() => import('./pages/VistaFiscal'))
const Patrimonio = lazy(() => import('./pages/Patrimonio'))
const Rendimiento = lazy(() => import('./pages/Rendimiento'))
const Rebalanceo = lazy(() => import('./pages/Rebalanceo'))
const Riesgo = lazy(() => import('./pages/Riesgo'))
const PerformanceRelativa = lazy(() => import('./pages/PerformanceRelativa'))
const Contribucion = lazy(() => import('./pages/Contribucion'))
const Diagnostico = lazy(() => import('./pages/Diagnostico'))
const CalidadDatos = lazy(() => import('./pages/CalidadDatos'))
const Simulador = lazy(() => import('./pages/Simulador'))
const BenchmarksComparacion = lazy(() => import('./pages/BenchmarksComparacion'))
const Mas = lazy(() => import('./pages/Mas'))
const Ajustes = lazy(() => import('./pages/Ajustes'))

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
      <p className="text-body text-app-text mb-3">
        Se cargaron: <strong>{syncResumenTexto}</strong>
      </p>
      {syncHealthScore !== null && (
        <div className="mb-4 p-3 bg-app-surface-2 rounded-lg">
          <div className="text-caption font-semibold text-app-text">
            Calidad: <span className="text-heading">{syncHealthScore}</span>/100
          </div>
          {syncResultado !== 'ok' && (
            <div className="text-label text-app-text-dim mt-1">
              {criticalCount > 0 && <div>{criticalCount} error(es) crítico(s)</div>}
              {warningCount > 0 && <div>{warningCount} advertencia(s)</div>}
            </div>
          )}
        </div>
      )}
      {syncIssues.length > 0 && (
        <div className="mb-4">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-2">Problemas detectados</div>
          <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
            {syncIssues.slice(0, 8).map((issue, i) => (
              <div key={i} className="text-caption text-app-text bg-app-surface-2 rounded-lg px-3 py-2">
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
              className="mt-2 text-caption text-app-link hover:underline"
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
  useAutoSync()

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
            <Route path="watchlist" element={<Watchlist />} />
            <Route path="ticker/:ticker" element={<TickerDetalle />} />
            <Route path="objetivo" element={<Objetivo />} />
            <Route path="precios" element={<Precios />} />
            <Route path="indicadores" element={<IndicadoresMacro />} />
            <Route path="vencimientos" element={<Vencimientos />} />
            <Route path="flujo-caja" element={<FlujoCaja />} />
            <Route path="comparar" element={<Comparador />} />
            <Route path="comisiones" element={<Comisiones />} />
            <Route path="vista-fiscal" element={<VistaFiscal />} />
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
            <Route path="ajustes" element={<Ajustes />} />
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
    <QueryClientProvider client={queryClient}>
      <InversionesProvider>
        <IconSprite />
        <Root />
      </InversionesProvider>
    </QueryClientProvider>
  )
}
