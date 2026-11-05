import type { ReactNode } from 'react'

export const CLASE_INPUT = 'w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-body text-app-text outline-none focus:border-app-accent/60'
export const CLASE_AREA = 'w-full rounded-xl bg-app-surface-2 border border-app-border px-3.5 py-2.5 text-body text-app-text outline-none focus:border-app-accent/60'

/** Una etiqueta con su control y, si hace falta, una línea de ayuda abajo. */
export default function Campo({ etiqueta, children, ayuda }: { etiqueta: string; children: ReactNode; ayuda?: string }) {
  return (
    <label className="flex flex-col gap-1 mb-3">
      <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">{etiqueta}</span>
      {children}
      {ayuda && <span className="text-label text-app-text-faint">{ayuda}</span>}
    </label>
  )
}
