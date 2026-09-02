import { useMemo } from 'react'
import { NavLink } from 'react-router-dom'
import { useInversionesContext } from '../../context/InversionesContext'
import { contarAlertas, type ConteoAlertas } from '../../utils/alertasPrecio'
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

/** El color lo fija la alerta más grave, no la más numerosa: un stop-loss disparado entre
 *  cinco avisos de proximidad sigue siendo lo urgente. */
function claseContador(conteo: ConteoAlertas): string {
  if (conteo.criticas > 0) return 'bg-app-coral text-app-bg'
  if (conteo.advertencias > 0) return 'bg-app-gold text-app-bg'
  return 'bg-app-teal text-app-bg'
}

export default function BottomNav() {
  const { rendimientoPorTicker, umbralProximidad } = useInversionesContext()

  const conteo = useMemo(
    () => contarAlertas(rendimientoPorTicker, umbralProximidad),
    [rendimientoPorTicker, umbralProximidad],
  )

  return (
    <nav className="flex border-t border-app-border bg-app-surface px-1 pt-2 safe-bottom shrink-0">
      {ITEMS.map(item => {
        // Las alertas de precio se resuelven en Posiciones: el contador va ahí y no en un
        // sexto destino que no entraría.
        const alertas = item.to === '/posiciones' ? conteo.total : 0
        return (
          <NavLink
            key={item.to}
            to={item.to}
            aria-label={alertas > 0 ? `${item.label}, ${alertas} alerta${alertas !== 1 ? 's' : ''} de precio` : undefined}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center gap-1 min-h-[44px] pb-2 text-label font-semibold ${
                isActive ? 'text-app-gold' : 'text-app-text-dim'
              }`
            }
          >
            <span className="relative">
              <Icon name={item.icon} className="w-[18px] h-[18px]" />
              {alertas > 0 && (
                <span
                  aria-hidden="true"
                  className={`absolute -top-1.5 -right-2.5 min-w-[15px] h-[15px] px-1 rounded-full flex items-center justify-center font-bold text-[9px] leading-none tabular-nums ${claseContador(conteo)}`}
                >
                  {alertas > 9 ? '9+' : alertas}
                </span>
              )}
            </span>
            <span className="text-center leading-[1.1]">{item.label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
