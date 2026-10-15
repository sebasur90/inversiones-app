import { Component, type ErrorInfo, type ReactNode } from 'react'
import Button from './Button'

const CLAVE_RECARGA = 'chunk-recarga-ts'
// Si la recarga automática ya se hizo hace menos de esto y el chunk sigue sin bajar, el
// problema no es una versión vieja en caché: se muestra el error en vez de entrar en un bucle.
const MS_ENTRE_RECARGAS = 30_000

/** Falla al bajar el JS de una pantalla (`React.lazy`): casi siempre es una versión vieja en caché. */
function esErrorDeChunk(error: Error): boolean {
  const texto = `${error.name} ${error.message}`
  return /dynamically imported module|Importing a module script failed|error loading dynamically|Loading chunk|Unable to preload CSS|is not a valid JavaScript MIME type/i.test(
    texto,
  )
}

function recargarUnaVez(): boolean {
  try {
    const ultima = Number(sessionStorage.getItem(CLAVE_RECARGA) ?? 0)
    if (Date.now() - ultima < MS_ENTRE_RECARGAS) return false
    sessionStorage.setItem(CLAVE_RECARGA, String(Date.now()))
  } catch {
    return false
  }
  window.location.reload()
  return true
}

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
  detalle: string | null
}

/**
 * Sin esto, un error al renderizar una pantalla desmonta toda la app y queda en blanco, sin
 * ninguna pista de qué pasó. Se monta dentro del shell para que la navegación inferior siga
 * viva, y con `key` por ruta para que cambiar de pantalla lo reinicie.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, detalle: null }

  static getDerivedStateFromError(error: Error): State {
    return { error, detalle: null }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Error al renderizar la pantalla:', error, info.componentStack)
    this.setState({ detalle: info.componentStack?.trim().split('\n').slice(0, 6).join('\n') ?? null })
    if (esErrorDeChunk(error)) recargarUnaVez()
  }

  render() {
    const { error, detalle } = this.state
    if (!error) return this.props.children

    const deChunk = esErrorDeChunk(error)
    return (
      <div className="py-6 flex flex-col gap-3">
        <div className="text-heading font-bold text-app-text">
          {deChunk ? 'No se pudo cargar esta pantalla' : 'Esta pantalla tuvo un error'}
        </div>
        <p className="text-body text-app-text-dim">
          {deChunk
            ? 'Probablemente la app se actualizó mientras la tenías abierta. Recargá para traer la versión nueva.'
            : 'El resto de la app sigue funcionando: podés volver a intentar o ir a otra pantalla.'}
        </p>
        <div className="flex gap-2">
          <Button onClick={() => window.location.reload()}>Recargar</Button>
          {!deChunk && (
            <Button variant="outline" onClick={() => this.setState({ error: null, detalle: null })}>
              Reintentar
            </Button>
          )}
        </div>
        <details className="text-label text-app-text-dim">
          <summary className="cursor-pointer">Detalle técnico</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words">
            {error.name}: {error.message}
            {detalle ? `\n${detalle}` : ''}
          </pre>
        </details>
      </div>
    )
  }
}
