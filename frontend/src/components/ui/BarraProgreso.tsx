type Tono = 'accent' | 'pos' | 'neg' | 'warn'

const RELLENO: Record<Tono, string> = {
  accent: 'bg-app-accent',
  pos: 'bg-app-pos',
  neg: 'bg-app-neg',
  warn: 'bg-app-warn',
}

/** Barra de progreso horizontal. El mismo patrón que ya se armaba a mano con `div`s en varias
 *  pantallas; acá vive una sola vez.
 *
 *  `pct` se satura visualmente en 100 para que un sobrecumplimiento no desborde la barra, pero
 *  quien la usa sigue mostrando el número real al lado: la barra se acota, el dato no se toca. */
export default function BarraProgreso({
  pct,
  tono = 'accent',
  alto = 'normal',
  className = '',
}: {
  pct: number | null | undefined
  tono?: Tono
  alto?: 'fino' | 'normal'
  className?: string
}) {
  const ancho = Math.max(0, Math.min(100, pct ?? 0))
  return (
    <div
      className={`${alto === 'fino' ? 'h-1' : 'h-1.5'} rounded-full bg-app-surface-2 overflow-hidden ${className}`}
      role="progressbar"
      aria-valuenow={Math.round(ancho)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={`h-full rounded-full ${RELLENO[tono]} transition-[width]`} style={{ width: `${ancho}%` }} />
    </div>
  )
}
