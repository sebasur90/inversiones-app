/**
 * Placeholder de carga. Reemplaza al "Cargando…" en texto plano: mantiene la forma de lo que
 * va a aparecer, así la pantalla no salta cuando llegan los datos.
 */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-app-surface-2 rounded-lg animate-pulse ${className}`} aria-hidden="true" />
}

/** Bloque genérico con forma de tarjeta: título corto + líneas de contenido. */
export function SkeletonCard({ lineas = 3, className = '' }: { lineas?: number; className?: string }) {
  return (
    <div className={`bg-app-surface border border-app-border rounded-2xl p-4 ${className}`} aria-hidden="true">
      <Skeleton className="h-3 w-24 mb-3" />
      {Array.from({ length: lineas }).map((_, i) => (
        <Skeleton key={i} className={`h-3 mb-2 last:mb-0 ${i === lineas - 1 ? 'w-2/3' : 'w-full'}`} />
      ))}
    </div>
  )
}

/** Lista de filas tipo posición/movimiento. */
export function SkeletonFilas({ filas = 5 }: { filas?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: filas }).map((_, i) => (
        <div key={i} className="flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0">
          <Skeleton className="w-9 h-9 rounded-[11px] shrink-0" />
          <div className="flex-1 min-w-0">
            <Skeleton className="h-3 w-2/3 mb-1.5" />
            <Skeleton className="h-2.5 w-1/3" />
          </div>
          <div className="text-right shrink-0">
            <Skeleton className="h-3 w-16 mb-1.5" />
            <Skeleton className="h-2.5 w-10 ml-auto" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Estado de carga de una pantalla entera (fallback del lazy loading y del primer fetch). */
export default function SkeletonPantalla() {
  return (
    <div className="pt-2" role="status" aria-label="Cargando">
      <Skeleton className="h-[132px] rounded-[18px] mb-3.5" />
      <div className="grid grid-cols-2 gap-2 mb-4">
        <Skeleton className="h-16 rounded-2xl" />
        <Skeleton className="h-16 rounded-2xl" />
      </div>
      <SkeletonFilas filas={4} />
    </div>
  )
}
