import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { getEventos, type Evento, type FiltrosEventos } from '../../api'
import { qk } from '../../api/queryClient'
import QueryBoundary from '../ui/QueryBoundary'
import { SkeletonFilas } from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import Button from '../ui/Button'
import Segmented from '../ui/Segmented'
import TarjetaEvento from './TarjetaEvento'
import { isoDia } from '../../utils/eventos'

const POR_PAGINA = 40
const ORDENES = [
  { value: 'desc' as const, label: 'Más recientes' },
  { value: 'asc' as const, label: 'Más antiguos' },
]

/** Separador "Hoy": entre lo que viene y lo que ya pasó. */
function SeparadorHoy() {
  return (
    <div className="flex items-center gap-2 my-1 text-label font-bold uppercase tracking-wide text-app-accent">
      <span className="h-px flex-1 bg-app-accent/40" /> Hoy <span className="h-px flex-1 bg-app-accent/40" />
    </div>
  )
}

export default function TimelineEventos({ parametros, onAbrir }: { parametros: FiltrosEventos; onAbrir: (id: number) => void }) {
  const [orden, setOrden] = useState<'asc' | 'desc'>('desc')
  const [paginas, setPaginas] = useState(1)
  const clave = JSON.stringify(parametros)
  useEffect(() => setPaginas(1), [clave, orden])

  const query = useQuery({
    queryKey: qk.de('eventos', 'timeline', clave, orden, paginas),
    queryFn: () => getEventos({ ...parametros, orden, page: 1, limite: POR_PAGINA * paginas }),
    placeholderData: prev => prev,
  })
  const datos = query.data
  const hoy = isoDia(dayjs())
  const eventos: Evento[] = datos?.eventos ?? []

  // Dónde va el separador de hoy: entre el último futuro y el primer pasado (o al revés en orden ascendente).
  const corte = eventos.findIndex(e => (orden === 'desc' ? e.fecha_evento < hoy && !e.fijado : e.fecha_evento >= hoy))
  const hayAmbos = corte > 0 && corte < eventos.length

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-caption text-app-text-dim">{datos ? `${datos.total} evento${datos.total === 1 ? '' : 's'}` : ''}</span>
        <Segmented options={ORDENES} value={orden} onChange={setOrden} />
      </div>
      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<SkeletonFilas filas={4} />}>
        {eventos.length === 0 ? (
          <EmptyState
            ilustracion="lupa"
            title="No hay eventos con estos filtros"
            description="Probá sacar algún filtro, o cargá un evento con «+ Evento»."
          />
        ) : (
          <>
            {eventos.map((e, i) => (
              <div key={e.id} className="flex flex-col gap-2">
                {hayAmbos && i === corte && <SeparadorHoy />}
                <TarjetaEvento evento={e} onAbrir={onAbrir} />
              </div>
            ))}
            {datos && datos.total > eventos.length && (
              <Button variant="outline" loading={query.isFetching} onClick={() => setPaginas(p => p + 1)}>
                Cargar más ({datos.total - eventos.length} restantes)
              </Button>
            )}
          </>
        )}
      </QueryBoundary>
    </div>
  )
}
