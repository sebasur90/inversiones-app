export type Severidad = 'critico' | 'advertencia' | 'info'

const SEVERIDAD_CLASSES: Record<Severidad, string> = {
  critico: 'bg-app-neg-soft text-app-neg',
  advertencia: 'bg-app-accent-soft text-app-accent',
  info: 'bg-app-pos-soft text-app-pos',
}

const SEVERIDAD_LABELS: Record<Severidad, string> = {
  critico: 'Crítico',
  advertencia: 'Atención',
  info: 'Info',
}

export default function SeverityBadge({ severidad, className = '' }: { severidad: Severidad; className?: string }) {
  return (
    <span
      className={`inline-block font-bold text-label tracking-wide px-1.5 py-0.5 rounded-[6px] shrink-0 ${SEVERIDAD_CLASSES[severidad]} ${className}`}
    >
      {SEVERIDAD_LABELS[severidad].toUpperCase()}
    </span>
  )
}
