import { useMutation, useQueryClient } from '@tanstack/react-query'
import { borrarCorreccionPar, corregirPar, type ValuacionTicker } from '../../api'
import { qk } from '../../api/queryClient'
import Modal from '../ui/Modal'
import SelectorInstrumento from '../inversiones/SelectorInstrumento'
import ErrorBanner from '../../help/components/ErrorBanner'
import { parseApiError } from '../../help/errors/apiErrors'
import { Icon } from '../icons/Icons'

/**
 * Agregar y quitar competidores del grupo de comparación de un emisor. Los automáticos salen de
 * la misma industria y un tamaño parecido; esto corrige lo que el criterio no ve (KO ↔ PEP).
 * Un par agregado que todavía no tiene datos aparece "pendiente" hasta la próxima ingesta.
 */
export default function EditorPares({ valuacion, open, onClose }: { valuacion: ValuacionTicker; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const ticker = valuacion.ticker
  const { pares } = valuacion

  const alActualizar = (nueva: ValuacionTicker) => {
    queryClient.setQueryData(qk.de('valuacion-ticker', ticker), nueva)
    void queryClient.invalidateQueries({ queryKey: ['valuacion-lista'] })
  }
  const corregir = useMutation({
    mutationFn: ({ par, accion }: { par: string; accion: 'agregar' | 'quitar' }) => corregirPar(ticker, par, accion),
    onSuccess: alActualizar,
  })
  const deshacer = useMutation({
    mutationFn: (par: string) => borrarCorreccionPar(ticker, par),
    onSuccess: alActualizar,
  })

  const actuales = new Set([valuacion.ticker_base, ticker, ...pares.items.map(p => p.ticker_base)])
  const ocupado = corregir.isPending || deshacer.isPending

  return (
    <Modal open={open} onClose={onClose} title={`Pares de ${valuacion.ticker_base}`}>
      <div className="flex flex-col gap-4">
        <div>
          <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">En el grupo</div>
          {pares.items.length === 0 ? (
            <p className="text-caption text-app-text-dim">Todavía no hay pares. Agregá alguno desde el buscador.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {pares.items.map(p => (
                <span key={p.ticker_base} className="inline-flex items-center gap-1.5 bg-app-surface-2 border border-app-border rounded-[9px] px-2.5 py-1.5 text-label font-bold text-app-text">
                  {p.ticker_base}
                  {p.agregado && <span className="text-app-accent">· a mano</span>}
                  {!p.tiene_datos && <span className="text-app-text-faint">· pendiente</span>}
                  <button
                    disabled={ocupado}
                    aria-label={`Quitar ${p.ticker_base}`}
                    onClick={() => (p.agregado ? deshacer.mutate(p.ticker_base) : corregir.mutate({ par: p.ticker_base, accion: 'quitar' }))}
                    className="flex items-center"
                  >
                    <Icon name="close" className="w-3.5 h-3.5 text-app-text-dim" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {pares.quitados.length > 0 && (
          <div>
            <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Quitados a mano</div>
            <div className="flex flex-wrap gap-1.5">
              {pares.quitados.map(q => (
                <button
                  key={q}
                  disabled={ocupado}
                  onClick={() => deshacer.mutate(q)}
                  className="inline-flex items-center gap-1 bg-app-surface border border-app-border rounded-[9px] px-2.5 py-1.5 text-label font-bold text-app-text-dim line-through"
                  title="Volver a incluirlo"
                >
                  {q}
                </button>
              ))}
            </div>
            <p className="text-label text-app-text-faint mt-1">Tocá uno para devolverlo al criterio automático.</p>
          </div>
        )}

        {(corregir.error || deshacer.error) && <ErrorBanner error={parseApiError(corregir.error ?? deshacer.error)} />}

        <div>
          <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Agregar un competidor</div>
          <SelectorInstrumento
            yaSeguidos={actuales}
            deshabilitado={ocupado}
            etiquetaYaElegido="Ya está"
            onElegir={inst => corregir.mutate({ par: inst.simbolo, accion: 'agregar' })}
          />
        </div>
      </div>
    </Modal>
  )
}
