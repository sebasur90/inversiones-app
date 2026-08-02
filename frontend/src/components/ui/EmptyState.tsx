import type { ReactNode } from 'react'

export default function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center gap-3 py-16 px-6">
      <div className="text-[14.5px] font-bold text-app-text">{title}</div>
      {description && <div className="text-[12.5px] text-app-text-dim max-w-[260px]">{description}</div>}
      {action}
    </div>
  )
}
