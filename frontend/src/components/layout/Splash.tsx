import { useInversionesContext } from '../../context/InversionesContext'
import { Icon } from '../icons/Icons'
import Button from '../ui/Button'

const BARS = [
  { x: 24, h: 26, color: '#5b8ba0', delay: '0s' },
  { x: 35, h: 36, color: '#7e9c90', delay: '0.18s' },
  { x: 46, h: 46, color: '#4fd1ae', delay: '0.36s' },
  { x: 57, h: 54, color: '#d8b14a', delay: '0.54s' },
]

export default function Splash() {
  const { syncing, error, triggerSync } = useInversionesContext()

  return (
    <div className="h-screen flex flex-col items-center justify-center gap-0 px-8 text-center bg-app-bg relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(120% 60% at 50% -10%, rgba(216,177,74,0.14), transparent 60%)' }}
      />

      <div className="relative w-[92px] h-[92px] mb-7">
        <svg viewBox="0 0 88 88" className="w-full h-full overflow-visible">
          <circle
            className="motion-safe:animate-spin-slow origin-[44px_44px]"
            cx="44"
            cy="44"
            r="40"
            fill="none"
            stroke="#223028"
            strokeWidth={1.5}
            strokeDasharray="3 7"
          />
          <g>
            {BARS.map(b => (
              <rect
                key={b.x}
                className="motion-safe:animate-rise origin-bottom"
                x={b.x}
                y={66 - b.h}
                width={7}
                height={b.h}
                rx={2}
                fill={b.color}
                style={{ animationDelay: b.delay }}
              />
            ))}
          </g>
        </svg>
      </div>

      <h1 className="font-display text-metric-lg font-semibold text-app-text mb-1.5">Inversiones</h1>
      <p className="text-body text-app-text-dim mb-9">Tu cartera, sincronizada.</p>

      <Button onClick={triggerSync} loading={syncing} icon={<Icon name="sync" className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />} className="w-full max-w-[280px]">
        {syncing ? 'Sincronizando…' : 'Sincronizar Google Sheet'}
      </Button>

      {error && <p className="mt-3 text-caption text-app-coral max-w-[280px]">{error}</p>}

      <div className="mt-4 flex items-center gap-1.5 text-label text-app-text-faint">
        <Icon name="lock" className="w-3 h-3" />
        Solo lectura · tus datos no salen de tu Sheet
      </div>
    </div>
  )
}
