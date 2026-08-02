import { Outlet } from 'react-router-dom'
import BottomNav from './BottomNav'

export default function AppShell() {
  return (
    <div className="h-screen flex justify-center bg-app-bg">
      <div className="w-full max-w-md flex flex-col h-full">
        <div className="flex-1 overflow-y-auto px-4 pt-4 safe-top">
          <Outlet />
        </div>
        <BottomNav />
      </div>
    </div>
  )
}
