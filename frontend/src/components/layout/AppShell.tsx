import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import BottomNav from './BottomNav'
import SkeletonPantalla from '../ui/Skeleton'

export default function AppShell() {
  return (
    <div className="h-screen flex justify-center bg-app-bg">
      <div className="w-full max-w-md flex flex-col h-full">
        <div className="flex-1 overflow-y-auto px-4 pt-4 safe-top">
          {/* Cada pantalla se carga por separado (React.lazy): el shell queda fijo y sólo
              el contenido muestra el skeleton mientras baja el chunk. */}
          <Suspense fallback={<SkeletonPantalla />}>
            <Outlet />
          </Suspense>
        </div>
        <BottomNav />
      </div>
    </div>
  )
}
