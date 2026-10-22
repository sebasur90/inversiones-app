import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

type Variant = 'primary' | 'outline' | 'ghost' | 'danger'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  icon?: ReactNode
  loading?: boolean
  children: ReactNode
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-app-accent text-white font-bold hover:bg-blue-600 active:bg-blue-700',
  outline: 'bg-app-surface border border-app-border text-app-text font-bold hover:bg-app-surface-2 hover:border-white/20',
  ghost: 'bg-transparent text-app-text-dim font-semibold hover:bg-white/5 hover:text-app-text',
  danger: 'bg-app-neg-soft text-app-neg font-bold hover:bg-app-neg/20',
}

export default function Button({ variant = 'primary', icon, loading, children, className = '', disabled, ...rest }: Props) {
  return (
    <button
      className={`h-11 px-4 rounded-2xl flex items-center justify-center gap-2 text-body transition-[background-color,border-color,color,transform,opacity] duration-150 active:scale-[0.97] disabled:active:scale-100 disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 aria-hidden="true" className="w-4 h-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}
