import { NavLink } from 'react-router-dom'
import { Icon, type IconName } from '../icons/Icons'

// Cinco destinos, con el label completo. Con ocho no entraban los nombres y había que
// abreviarlos ("Patrim.", "Rendim.", "Rebal."); el resto de las pantallas se alcanza desde
// "Más" y desde el buscador del header.
const ITEMS: { to: string; label: string; icon: IconName }[] = [
  { to: '/resumen', label: 'Resumen', icon: 'home' },
  { to: '/posiciones', label: 'Posiciones', icon: 'list' },
  { to: '/rendimiento', label: 'Rendimiento', icon: 'up' },
  { to: '/movimientos', label: 'Movimientos', icon: 'trend' },
  { to: '/mas', label: 'Más', icon: 'more' },
]

export default function BottomNav() {
  return (
    <nav className="flex border-t border-app-border bg-app-surface px-1 pt-2 safe-bottom shrink-0">
      {ITEMS.map(item => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center justify-center gap-1 min-h-[44px] pb-2 text-label font-semibold ${
              isActive ? 'text-app-gold' : 'text-app-text-dim'
            }`
          }
        >
          <Icon name={item.icon} className="w-[18px] h-[18px]" />
          <span className="text-center leading-[1.1]">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
