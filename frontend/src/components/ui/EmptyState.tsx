import type { ReactNode } from 'react'

export type IlustracionVacia = 'planta' | 'escudo' | 'lupa'

/** Ilustraciones de línea con los colores de la app; decorativas (`aria-hidden`). */
function Ilustracion({ tipo }: { tipo: IlustracionVacia }) {
  const base = { viewBox: '0 0 120 96', 'aria-hidden': true, className: 'w-[120px] h-24' } as const
  if (tipo === 'planta') {
    return (
      <svg {...base}>
        <ellipse cx="60" cy="84" rx="40" ry="6" fill="rgba(255,255,255,.04)" />
        <ellipse cx="60" cy="72" rx="26" ry="7" fill="#1c1f2a" stroke="#475569" strokeWidth="2" />
        <path d="M34 72v-8M86 72v-8" stroke="#475569" strokeWidth="2" />
        <ellipse cx="60" cy="64" rx="26" ry="7" fill="#262a35" stroke="#64748b" strokeWidth="2" />
        <path d="M60 62C60 48 60 40 60 34" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M60 44C48 44 42 36 42 28c10 0 18 6 18 16z" fill="rgba(16,185,129,.2)" stroke="#10b981" strokeWidth="2" strokeLinejoin="round" />
        <path d="M60 38c10 0 18-8 18-18-12 0-18 8-18 18z" fill="rgba(16,185,129,.2)" stroke="#10b981" strokeWidth="2" strokeLinejoin="round" />
      </svg>
    )
  }
  if (tipo === 'escudo') {
    return (
      <svg {...base}>
        <ellipse cx="60" cy="86" rx="34" ry="5" fill="rgba(255,255,255,.04)" />
        <path d="M60 12c10 8 20 10 28 10v24c0 18-12 28-28 34-16-6-28-16-28-34V22c8 0 18-2 28-10z" fill="rgba(16,185,129,.12)" stroke="#10b981" strokeWidth="2.5" strokeLinejoin="round" />
        <path d="M48 46l8 8 16-16" fill="none" stroke="#34d399" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M98 18v8M94 22h8M20 40v6M17 43h6" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg {...base}>
      <ellipse cx="60" cy="86" rx="40" ry="5" fill="rgba(255,255,255,.04)" />
      <rect x="20" y="20" width="70" height="52" rx="10" fill="#1c1f2a" stroke="#475569" strokeWidth="2" />
      <path d="M30 58l14-12 10 6 16-18 10 6" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="28" y="40" width="54" height="12" rx="3" fill="rgba(16,185,129,.12)" />
      <circle cx="84" cy="62" r="13" fill="#0a0e18" stroke="#94a3b8" strokeWidth="2.5" />
      <path d="M94 72l10 10" stroke="#94a3b8" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export default function EmptyState({
  title,
  description,
  action,
  ilustracion,
  emoji,
}: {
  title: string
  description?: string
  action?: ReactNode
  /** Dibujo de línea arriba del título. Sin él la pantalla queda como antes. */
  ilustracion?: IlustracionVacia
  /** Un solo emoji al final del título, para darle un tono cercano. */
  emoji?: string
}) {
  return (
    <div className="animate-fade-in flex flex-col items-center text-center gap-3 py-16 px-6">
      {ilustracion && <Ilustracion tipo={ilustracion} />}
      <div className="text-strong font-bold text-app-text">
        {title}
        {emoji && <span aria-hidden="true"> {emoji}</span>}
      </div>
      {description && <div className="text-caption text-app-text-dim max-w-[260px]">{description}</div>}
      {action}
    </div>
  )
}
