import { NavLink } from 'react-router-dom'
import { Icon, type IconName } from '../icons/Icons'

const ITEMS: { to: string; label: string; icon: IconName }[] = [
  { to: '/resumen', label: 'Resumen', icon: 'home' },
  { to: '/exposicion', label: 'Exposición', icon: 'pie' },
  { to: '/movimientos', label: 'Movim.', icon: 'list' },
  { to: '/precios', label: 'Precios', icon: 'trend' },
  { to: '/objetivo', label: 'Objetivo', icon: 'target' },
]

export default function BottomNav() {
  return (
    <nav className="flex border-t border-app-border bg-app-surface px-1.5 pt-2 safe-bottom shrink-0">
      {ITEMS.map(item => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center gap-1 pb-2 text-[9.5px] font-semibold ${
              isActive ? 'text-app-gold' : 'text-app-text-faint'
            }`
          }
        >
          <Icon name={item.icon} />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
