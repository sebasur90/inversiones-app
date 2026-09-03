import { QueryClient } from '@tanstack/react-query'

/**
 * Los datos sólo cambian cuando el usuario sincroniza con el Sheet, y esa acción invalida
 * todo explícitamente (ver `triggerSync` en InversionesContext). Entre syncs no tiene sentido
 * revalidar: por eso `staleTime` infinito y refetches automáticos apagados.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: Infinity,
      gcTime: 30 * 60 * 1000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      // Un reintento: cubre el corte momentáneo sin dejar la pantalla colgada si el backend
      // está caído de verdad.
      retry: 1,
    },
  },
})

/** Claves de query. Centralizadas para que invalidar por prefijo sea confiable. */
export const qk = {
  carteras: ['carteras'] as const,
  resumen: (cartera: string | null) => ['resumen', cartera] as const,
  exposicion: (cartera: string | null) => ['exposicion', cartera] as const,
  rebalanceo: (cartera: string | null) => ['rebalanceo', cartera] as const,
  movimientos: (cartera: string | null) => ['movimientos', cartera] as const,
  rendimientoPorTicker: (cartera: string | null) => ['rendimiento-por-ticker', cartera] as const,
  evolucion: (cartera: string | null) => ['evolucion', cartera] as const,
  diagnostico: (cartera: string | null) => ['diagnostico', cartera] as const,
  calidadDatos: ['calidad-datos'] as const,
  watchlist: ['watchlist'] as const,
  /**
   * Clave genérica para las pantallas: `qk.de('vencimientos', cartera)`. Todas las queries
   * cuelgan de un nombre + sus parámetros, así que invalidar todo tras un sync alcanza y
   * no hace falta declarar cada una acá arriba.
   */
  de: (nombre: string, ...params: unknown[]) => [nombre, ...params] as const,
}
