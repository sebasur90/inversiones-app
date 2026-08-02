import type { HTMLAttributes, ReactNode } from 'react'

export default function Card({ children, className = '', ...rest }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <div className={`bg-app-surface border border-app-border rounded-2xl p-4 ${className}`} {...rest}>
      {children}
    </div>
  )
}
