import { useNavigate } from 'react-router-dom'
import ScreenHeader from '../components/layout/ScreenHeader'
import { Icon, type IconName } from '../components/icons/Icons'

type Item = { to: string; label: string; desc: string; icon: IconName }
type Grupo = { titulo: string; items: Item[] }

// Estas pantallas ya existen y están completas, pero antes de este menú sólo se llegaba a ellas
// por links contextuales desde otras pantallas (o, en el caso de "Comparar benchmarks", por un
// único link). Este índice las agrupa por tema para que sean alcanzables directamente.
const GRUPOS: Grupo[] = [
  {
    titulo: 'Rendimiento y riesgo',
    items: [
      { to: '/riesgo', label: 'Riesgo', desc: 'Drawdown, volatilidad, Sharpe, Sortino, Calmar', icon: 'trend' },
      { to: '/performance-relativa', label: 'Performance relativa', desc: 'Cartera vs. un benchmark: alpha, beta, tracking error', icon: 'up' },
      { to: '/benchmarks-comparacion', label: 'Comparar benchmarks', desc: 'Varios benchmarks y tickers a la vez', icon: 'pie' },
      { to: '/contribucion', label: 'Contribución', desc: 'Qué aportó cada posición, concentración y correlaciones', icon: 'pie' },
    ],
  },
  {
    titulo: 'Cartera',
    items: [
      { to: '/posiciones', label: 'Posiciones', desc: 'Tenencias actuales con precio y objetivo/stop-loss', icon: 'list' },
      { to: '/precios', label: 'Precios', desc: 'Evolución histórica por ticker', icon: 'trend' },
      { to: '/vencimientos', label: 'Vencimientos', desc: 'Calendario de vencimientos de bonos', icon: 'alert' },
      { to: '/flujo-caja', label: 'Flujo de caja proyectado', desc: 'Cupones y amortizaciones a cobrar mes a mes', icon: 'trend' },
      { to: '/comisiones', label: 'Comisiones', desc: 'Desglose por cartera, ticker, mes y año', icon: 'scale' },
      { to: '/vista-fiscal', label: 'Vista fiscal por año', desc: 'Realizado, dividendos/cupones y comisiones por año calendario', icon: 'scale' },
    ],
  },
  {
    titulo: 'Herramientas',
    items: [
      { to: '/simulador', label: 'Simulador', desc: 'Escenarios "¿qué pasaría si…?"', icon: 'edit' },
      { to: '/comparar', label: 'Comparador', desc: 'Hasta 5 tickers, series normalizadas', icon: 'search' },
    ],
  },
  {
    titulo: 'Sistema',
    items: [
      { to: '/diagnostico', label: 'Diagnóstico', desc: 'Score de salud de la cartera y hallazgos', icon: 'check' },
      { to: '/calidad-datos', label: 'Calidad de datos', desc: 'Estado del último sync y problemas detectados', icon: 'info' },
      { to: '/indicadores', label: 'Indicadores macro', desc: 'Evolución de CER y MEP', icon: 'trend' },
    ],
  },
]

export default function Mas() {
  const navigate = useNavigate()

  return (
    <div className="pb-4">
      <ScreenHeader title="Más" />

      <div className="flex flex-col gap-5">
        {GRUPOS.map(grupo => (
          <div key={grupo.titulo}>
            <div className="text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2 px-0.5">
              {grupo.titulo}
            </div>
            <div className="flex flex-col gap-1.5">
              {grupo.items.map(item => (
                <button
                  key={item.to}
                  onClick={() => navigate(item.to)}
                  className="flex items-center gap-3 text-left px-3.5 py-3 rounded-xl bg-app-surface-2 border border-app-border hover:border-app-gold/40 transition-colors"
                >
                  <div className="w-9 h-9 rounded-lg bg-app-gold-soft text-app-gold flex items-center justify-center shrink-0">
                    <Icon name={item.icon} className="w-[18px] h-[18px]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] font-semibold text-app-text">{item.label}</div>
                    <div className="text-[11.5px] text-app-text-dim truncate">{item.desc}</div>
                  </div>
                  <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-faint -rotate-90 shrink-0" />
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
