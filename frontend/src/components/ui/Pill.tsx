import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
}

export default function Pill({ children, className = '', ...rest }: Props) {
  return (
    <button
      className={`h-9 px-3 rounded-[11px] bg-app-surface border border-app-border inline-flex items-center gap-1.5 text-caption font-semibold text-app-text ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
