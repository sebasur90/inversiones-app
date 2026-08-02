import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'outline' | 'ghost' | 'danger'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  icon?: ReactNode
  loading?: boolean
  children: ReactNode
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-app-gold text-[#1a1406] font-bold',
  outline: 'bg-app-surface border border-app-border text-app-text font-bold',
  ghost: 'bg-transparent text-app-text-dim font-semibold',
  danger: 'bg-app-coral-soft text-app-coral font-bold',
}

export default function Button({ variant = 'primary', icon, loading, children, className = '', disabled, ...rest }: Props) {
  return (
    <button
      className={`h-11 px-4 rounded-2xl flex items-center justify-center gap-2 text-[13.5px] transition-opacity disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}
