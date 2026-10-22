import type { ButtonHTMLAttributes } from 'react'

type Tone = 'default' | 'accent' | 'danger'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  accent?: boolean
  tone?: Tone
}

const TONE_CLASSES: Record<Tone, string> = {
  default: 'bg-app-surface border-app-border text-app-text hover:bg-app-surface-2 hover:border-white/15',
  accent: 'bg-app-accent-soft border-transparent text-app-accent hover:bg-app-accent/25',
  danger: 'bg-app-neg-soft border-transparent text-app-neg hover:bg-app-neg/20',
}

export default function IconButton({ accent, tone, className = '', children, ...rest }: Props) {
  const resolvedTone: Tone = tone ?? (accent ? 'accent' : 'default')
  return (
    <button
      className={`w-9 h-9 rounded-[11px] flex items-center justify-center border transition-[background-color,border-color,color,transform] duration-150 active:scale-90 disabled:active:scale-100 disabled:opacity-60 ${TONE_CLASSES[resolvedTone]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
