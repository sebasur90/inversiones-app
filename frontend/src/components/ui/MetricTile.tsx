import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content/index'

interface MetricTileProps {
  label: string
  value: string
  infoTerm?: HelpKey
  tone?: 'pos' | 'neg'
  suffix?: string
  sub?: string
  insuficiente?: boolean
  size?: 'sm' | 'md'
}

export default function MetricTile({
  label,
  value,
  infoTerm,
  tone,
  suffix,
  sub,
  insuficiente,
  size = 'sm',
}: MetricTileProps) {
  const fontSize = size === 'md' ? 'text-[15px]' : 'text-[14px]'
  const toneClass =
    tone === 'pos' ? 'text-app-teal' : tone === 'neg' ? 'text-app-coral' : 'text-app-text'

  return (
    <div className="bg-app-surface border border-app-border rounded-[13px] px-2.5 py-2.5">
      <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
        {infoTerm ? <InfoTooltip term={infoTerm} label={label} /> : label}
      </div>
      {insuficiente ? (
        <div className="text-[12px] text-app-text-faint">Datos insuficientes</div>
      ) : (
        <div className={`font-mono ${fontSize} font-bold tabular-nums ${toneClass}`}>
          {value}
          {suffix && <span className="text-[10px] font-semibold text-app-text-faint ml-1">{suffix}</span>}
        </div>
      )}
      {sub && !insuficiente && <div className="text-[10px] text-app-text-dim mt-0.5">{sub}</div>}
    </div>
  )
}
