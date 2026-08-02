import type { ButtonHTMLAttributes } from 'react'

type Tone = 'default' | 'accent' | 'danger'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  accent?: boolean
  tone?: Tone
}

const TONE_CLASSES: Record<Tone, string> = {
  default: 'bg-app-surface border-app-border text-app-text',
  accent: 'bg-app-gold-soft border-transparent text-app-gold',
  danger: 'bg-app-coral-soft border-transparent text-app-coral',
}

export default function IconButton({ accent, tone, className = '', children, ...rest }: Props) {
  const resolvedTone: Tone = tone ?? (accent ? 'accent' : 'default')
  return (
    <button
      className={`w-9 h-9 rounded-[11px] flex items-center justify-center border transition-colors ${TONE_CLASSES[resolvedTone]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
