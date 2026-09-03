import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import ScreenHeader from '../components/layout/ScreenHeader'
import { Icon } from '../components/icons/Icons'
import { GRUPOS_PANTALLAS } from '../data/pantallas'
import { useInversionesContext } from '../context/InversionesContext'
import { contarAlertasCompra } from '../utils/alertasPrecio'

// Mismo criterio que `claseContador` de BottomNav: el color lo fija la alerta más grave.
function claseContador(criticas: number, advertencias: number): string {
  if (criticas > 0) return 'bg-app-coral text-app-bg'
  if (advertencias > 0) return 'bg-app-gold text-app-bg'
  return 'bg-app-teal text-app-bg'
}

export default function Mas() {
  const navigate = useNavigate()
  const { watchlist, umbralProximidad } = useInversionesContext()

  const conteoWatchlist = useMemo(
    () => contarAlertasCompra(watchlist, umbralProximidad),
    [watchlist, umbralProximidad],
  )

  return (
    <div className="pb-4">
      <ScreenHeader title="Más" />

      <div className="flex flex-col gap-5">
        {GRUPOS_PANTALLAS.map(grupo => (
          <div key={grupo.titulo}>
            <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-2 px-0.5">
              {grupo.titulo}
            </div>
            <div className="flex flex-col gap-1.5">
              {grupo.items.map(item => {
                const alertas = item.to === '/watchlist' ? conteoWatchlist.total : 0
                return (
                  <button
                    key={item.to}
                    onClick={() => navigate(item.to)}
                    className="flex items-center gap-3 text-left px-3.5 py-3 rounded-xl bg-app-surface-2 border border-app-border hover:border-app-gold/40 transition-colors"
                  >
                    <div className="w-9 h-9 rounded-lg bg-app-gold-soft text-app-gold flex items-center justify-center shrink-0">
                      <Icon name={item.icon} className="w-[18px] h-[18px]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-body font-semibold text-app-text">{item.label}</div>
                      <div className="text-caption text-app-text-dim truncate">{item.desc}</div>
                    </div>
                    {alertas > 0 && (
                      <span
                        aria-label={`${alertas} alerta${alertas !== 1 ? 's' : ''} de compra`}
                        className={`min-w-[20px] h-5 px-1.5 rounded-full flex items-center justify-center font-bold text-[11px] leading-none tabular-nums shrink-0 ${claseContador(conteoWatchlist.criticas, conteoWatchlist.advertencias)}`}
                      >
                        {alertas > 9 ? '9+' : alertas}
                      </span>
                    )}
                    <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90 shrink-0" />
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
