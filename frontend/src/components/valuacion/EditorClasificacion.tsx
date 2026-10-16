import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  borrarCorreccionClasificacion, corregirClasificacion, getClasificacionTicker,
  type CampoClasificacion, type ClasificacionTicker,
} from '../../api'
import { qk } from '../../api/queryClient'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import { SkeletonFilas } from '../ui/Skeleton'
import ErrorBanner from '../../help/components/ErrorBanner'
import { parseApiError } from '../../help/errors/apiErrors'
import { FuenteBadge } from './comun'

const CAMPOS: { campo: CampoClasificacion; label: string; tipo: 'select' | 'texto' }[] = [
  { campo: 'tipo', label: 'Tipo', tipo: 'select' },
  { campo: 'sector', label: 'Sector', tipo: 'select' },
  { campo: 'industria', label: 'Industria', tipo: 'texto' },
  { campo: 'pais', label: 'País', tipo: 'texto' },
  { campo: 'region', label: 'Región', tipo: 'select' },
]

function opcionesDe(campo: CampoClasificacion, data: ClasificacionTicker): string[] {
  if (campo === 'tipo') return data.opciones.tipo
  if (campo === 'region') return data.opciones.region
  if (campo === 'sector') {
    const actual = data.resuelta.sector
    return actual && !data.opciones.sector.includes(actual) ? [...data.opciones.sector, actual] : data.opciones.sector
  }
  return []
}

/**
 * Corrige a mano la clasificación de un emisor. La corrección gana sobre Yahoo y el Sheet en
 * todas las pantallas (Exposición, Descomposición, Balance, Salud y la valuación contra pares) y
 * vale para todas las variantes de moneda del ticker.
 */
export default function EditorClasificacion({ ticker, open, onClose }: { ticker: string; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: qk.de('clasificacion-ticker', ticker),
    queryFn: () => getClasificacionTicker(ticker),
    enabled: open,
  })
  const data = query.data
  const [borrador, setBorrador] = useState<Partial<Record<CampoClasificacion, string>>>({})

  useEffect(() => {
    if (open) setBorrador({})
  }, [open, ticker])

  // Una corrección cambia etiquetas en muchas pantallas: se invalida todo, como tras un sync.
  const invalidarTodo = () => queryClient.invalidateQueries()

  const guardar = useMutation({
    mutationFn: () => corregirClasificacion(ticker, borrador),
    onSuccess: () => {
      void invalidarTodo()
      onClose()
    },
  })
  const restaurar = useMutation({
    mutationFn: (campo: CampoClasificacion) => borrarCorreccionClasificacion(ticker, campo),
    onSuccess: () => void invalidarTodo(),
  })

  const cambios = Object.entries(borrador).filter(([c, v]) => v !== undefined && v !== (data?.resuelta[c as CampoClasificacion] ?? ''))

  return (
    <Modal open={open} onClose={onClose} title={`Clasificación de ${ticker}`}>
      {query.isLoading || !data ? (
        <SkeletonFilas filas={5} />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-caption text-app-text-dim">
            Lo que corrijas acá manda sobre Yahoo y sobre el Sheet en todas las pantallas
            {data.ticker_base !== data.ticker ? ` y vale también para ${data.ticker_base} y sus otras variantes` : ''}.
          </p>
          {CAMPOS.map(({ campo, label, tipo }) => {
            const valorActual = data.resuelta[campo] ?? ''
            const valor = borrador[campo] ?? valorActual
            const corregido = data.correcciones[campo] !== undefined
            const automatico = data.automatica[campo]
            return (
              <div key={campo}>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <label htmlFor={`clasif-${campo}`} className="text-label font-bold text-app-text-dim uppercase">{label}</label>
                  <FuenteBadge fuente={data.resuelta.fuentes[campo]} />
                </div>
                {tipo === 'select' ? (
                  <select
                    id={`clasif-${campo}`}
                    value={valor}
                    onChange={e => setBorrador(b => ({ ...b, [campo]: e.target.value }))}
                    className="w-full h-10 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text"
                  >
                    {!valorActual && <option value="">Sin dato</option>}
                    {opcionesDe(campo, data).map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    id={`clasif-${campo}`}
                    value={valor}
                    onChange={e => setBorrador(b => ({ ...b, [campo]: e.target.value }))}
                    placeholder="Sin dato"
                    className="w-full h-10 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text"
                  />
                )}
                {corregido && (
                  <button
                    onClick={() => restaurar.mutate(campo)}
                    className="text-label text-app-accent font-semibold mt-1"
                  >
                    Volver al automático{automatico ? ` (${automatico})` : ''}
                  </button>
                )}
              </div>
            )
          })}
          {(guardar.error || restaurar.error) && <ErrorBanner error={parseApiError(guardar.error ?? restaurar.error)} />}
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={cambios.length === 0}>
            Guardar corrección
          </Button>
        </div>
      )}
    </Modal>
  )
}
