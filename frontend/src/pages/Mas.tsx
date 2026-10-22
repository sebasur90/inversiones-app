import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import ScreenHeader from '../components/layout/ScreenHeader'
import { Icon, type IconName } from '../components/icons/Icons'
import { GRUPOS_PANTALLAS } from '../data/pantallas'
import { useInversionesContext } from '../context/InversionesContext'
import { contarAlertasCompra } from '../utils/alertasPrecio'

// Mismo criterio que `claseContador` de BottomNav: el color lo fija la alerta más grave.
function claseContador(criticas: number, advertencias: number): string {
  if (criticas > 0) return 'bg-app-neg text-app-bg'
  if (advertencias > 0) return 'bg-app-accent text-app-bg'
  return 'bg-app-pos text-app-bg'
}

// Cada grupo tiene su ícono y su tono: con unas treinta pantallas, el color ayuda a ubicar el tema
// antes de leer los nombres.
const ESTILO_GRUPO: Record<string, { icono: IconName; tono: string }> = {
  Ayuda: { icono: 'info', tono: 'bg-app-cyan/15 text-app-cyan' },
  Decisiones: { icono: 'compass', tono: 'bg-app-violet/15 text-app-violet' },
  Cartera: { icono: 'wallet', tono: 'bg-app-accent-soft text-app-accent' },
  'Rendimiento y riesgo': { icono: 'trend', tono: 'bg-app-pos-soft text-app-pos' },
  Herramientas: { icono: 'grid', tono: 'bg-app-violet/15 text-app-violet' },
  Sistema: { icono: 'shield', tono: 'bg-app-warn/15 text-app-warn' },
}
const ESTILO_POR_DEFECTO = { icono: 'more' as IconName, tono: 'bg-app-accent-soft text-app-accent' }

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

      <div className="flex flex-col gap-6">
        {GRUPOS_PANTALLAS.map(grupo => {
          const estilo = ESTILO_GRUPO[grupo.titulo] ?? ESTILO_POR_DEFECTO
          return (
            <section key={grupo.titulo} aria-label={grupo.titulo}>
              <div className="flex items-center gap-2.5 mb-2 px-0.5">
                <span aria-hidden="true" className={`w-7 h-7 rounded-[9px] flex items-center justify-center shrink-0 ${estilo.tono}`}>
                  <Icon name={estilo.icono} className="w-4 h-4" />
                </span>
                <h2 className="flex-1 text-strong font-bold text-app-text">{grupo.titulo}</h2>
                <span className="text-label text-app-text-faint">{grupo.items.length}</span>
              </div>
              <div className="bg-app-surface border border-app-border rounded-2xl px-1.5">
                {grupo.items.map(item => {
                  const alertas = item.to === '/watchlist' ? conteoWatchlist.total : 0
                  return (
                    <button
                      key={item.to}
                      onClick={() => navigate(item.to)}
                      className="group w-full flex items-center gap-3 text-left px-2.5 py-3 border-b border-app-border-soft last:border-b-0 rounded-xl transition-colors duration-150 hover:bg-white/[0.035] active:bg-white/[0.06]"
                    >
                      <div className={`w-9 h-9 rounded-[11px] flex items-center justify-center shrink-0 transition-transform duration-150 group-hover:scale-105 ${estilo.tono}`}>
                        <Icon name={item.icon} className="w-[18px] h-[18px]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-body font-semibold text-app-text">{item.label}</div>
                        <div className="text-caption text-app-text-dim truncate">{item.desc}</div>
                      </div>
                      {alertas > 0 && (
                        <span
                          aria-label={`${alertas} alerta${alertas !== 1 ? 's' : ''} de compra`}
                          className={`min-w-[20px] h-5 px-1.5 rounded-full flex items-center justify-center font-bold text-label leading-none tabular-nums shrink-0 ${claseContador(conteoWatchlist.criticas, conteoWatchlist.advertencias)}`}
                        >
                          {alertas > 9 ? '9+' : alertas}
                        </span>
                      )}
                      <Icon
                        name="chevron"
                        className="w-3.5 h-3.5 text-app-text-faint -rotate-90 shrink-0 transition-[transform,color] duration-150 group-hover:translate-x-0.5 group-hover:text-app-text"
                      />
                    </button>
                  )
                })}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
