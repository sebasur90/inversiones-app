import type { ReactNode } from 'react'
import ErrorBanner from '../../help/components/ErrorBanner'
import { parseApiError } from '../../help/errors/apiErrors'
import Button from './Button'
import SkeletonPantalla from './Skeleton'

/**
 * Estado de carga y de error de un bloque de datos, en un solo lugar.
 *
 * Antes cada pantalla resolvía esto a mano y 17 de 24 no mostraban nada cuando el fetch
 * fallaba: el `.catch()` dejaba el estado vacío y la pantalla parecía "sin datos".
 */
export default function QueryBoundary({
  isLoading,
  error,
  onRetry,
  fallback,
  children,
}: {
  isLoading?: boolean
  error?: unknown
  onRetry?: () => void
  /** Qué mostrar mientras carga. Por defecto, el skeleton de pantalla completa. */
  fallback?: ReactNode
  children: ReactNode
}) {
  if (error) {
    return (
      <div className="py-2">
        <ErrorBanner error={parseApiError(error)} />
        {onRetry && (
          <Button variant="outline" onClick={onRetry} className="mt-1">
            Reintentar
          </Button>
        )}
      </div>
    )
  }

  if (isLoading) return <>{fallback ?? <SkeletonPantalla />}</>

  return <>{children}</>
}
