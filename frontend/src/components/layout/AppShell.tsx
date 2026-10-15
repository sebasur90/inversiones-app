import { Suspense } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import BottomNav from './BottomNav'
import ErrorBoundary from '../ui/ErrorBoundary'
import SkeletonPantalla from '../ui/Skeleton'

export default function AppShell() {
  const { pathname } = useLocation()
  return (
    <div className="h-screen flex justify-center bg-app-bg">
      <div className="w-full max-w-md flex flex-col h-full">
        <div className="flex-1 overflow-y-auto px-4 pt-4 safe-top">
          {/* Cada pantalla se carga por separado (React.lazy): el shell queda fijo y sólo
              el contenido muestra el skeleton mientras baja el chunk. */}
          {/* El boundary va por fuera del Suspense (también atrapa un chunk que no baja) y con
              `key` por ruta: un error en una pantalla no sigue colgado al navegar a otra. */}
          <ErrorBoundary key={pathname}>
            <Suspense fallback={<SkeletonPantalla />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
        <BottomNav />
      </div>
    </div>
  )
}
