import InfoTerm from './InfoTerm'
import type { HelpKey } from '../../help/content/index'

interface MetricCardProps {
  label: string
  infoTerm: HelpKey
  value: string
  subtitulo?: string
  insuficiente?: boolean
  tone?: string
}

export default function MetricCard({
  label,
  infoTerm,
  value,
  subtitulo,
  insuficiente,
  tone,
}: MetricCardProps) {
  return (
    <div className="bg-app-surface border border-app-border rounded-[13px] px-2.5 py-2.5">
      <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">
        <InfoTerm term={infoTerm} label={label} />
      </div>
      {insuficiente ? (
        <div className="text-caption text-app-text-faint">Datos insuficientes</div>
      ) : (
        <div className={`font-mono text-strong font-bold tabular-nums ${tone ?? 'text-app-text'}`}>{value}</div>
      )}
      {subtitulo && !insuficiente && <div className="text-label text-app-text-dim mt-0.5">{subtitulo}</div>}
    </div>
  )
}
