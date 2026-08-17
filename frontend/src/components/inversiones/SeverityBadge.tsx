"""Shared severity badge component for data quality issues."""

export type Severidad = 'critico' | 'advertencia' | 'info'

const SEVERIDAD_CLASSES: Record<Severidad, string> = {
  critico: 'bg-app-coral-soft text-app-coral',
  advertencia: 'bg-app-gold-soft text-app-gold',
  info: 'bg-app-teal-soft text-app-teal',
}

const SEVERIDAD_LABELS: Record<Severidad, string> = {
  critico: 'Crítico',
  advertencia: 'Atención',
  info: 'Info',
}

export default function SeverityBadge({ severidad, className = '' }: { severidad: Severidad; className?: string }) {
  return (
    <span
      className={`inline-block font-bold text-[9.5px] tracking-wide px-1.5 py-0.5 rounded-[6px] shrink-0 ${SEVERIDAD_CLASSES[severidad]} ${className}`}
    >
      {SEVERIDAD_LABELS[severidad].toUpperCase()}
    </span>
  )
}
