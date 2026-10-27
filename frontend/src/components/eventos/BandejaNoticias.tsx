import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  asociarNoticiaEvento, crearEventoDesdeNoticia, descartarNoticiaEvento, getEventos, getNoticiasEventos, type NoticiaEvento,
} from '../../api'
import { qk } from '../../api/queryClient'
import { useInversionesContext } from '../../context/InversionesContext'
import { parseApiError } from '../../help/errors/apiErrors'
import { fechaCorta, fechaHora } from '../../utils/fechas'
import { ETIQUETA_CATEGORIA } from '../../utils/eventos'
import type { CategoriaEvento } from '../../api'
import Button from '../ui/Button'
import EmptyState from '../ui/EmptyState'
import QueryBoundary from '../ui/QueryBoundary'
import { SkeletonFilas } from '../ui/Skeleton'
import { dominio, EnlaceFuente } from './comun'

function Asociar({ noticia, onListo }: { noticia: NoticiaEvento; onListo: () => void }) {
  const qc = useQueryClient()
  const dia = noticia.fecha_publicacion.slice(0, 10)
  const desde = new Date(new Date(dia).getTime() - 3 * 86_400_000).toISOString().slice(0, 10)
  const hasta = new Date(new Date(dia).getTime() + 3 * 86_400_000).toISOString().slice(0, 10)
  const cercanos = useQuery({ queryKey: qk.de('eventos', 'cercanos', dia), queryFn: () => getEventos({ desde, hasta, limite: 20 }) })
  const asociar = useMutation({
    mutationFn: (eventoId: number) => asociarNoticiaEvento(noticia.id, eventoId),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.de('eventos') }); onListo() },
  })
  const lista = cercanos.data?.eventos ?? []
  return (
    <div className="mt-2 rounded-lg bg-app-surface-2 p-2">
      <div className="text-label text-app-text-faint mb-1">Eventos cercanos a esa fecha</div>
      {lista.length === 0 && <div className="text-caption text-app-text-dim">No hay eventos entre el {fechaCorta(desde)} y el {fechaCorta(hasta)}.</div>}
      <ul className="flex flex-col gap-1">
        {lista.map(e => (
          <li key={e.id}>
            <button onClick={() => asociar.mutate(e.id)} className="w-full text-left text-caption text-app-text hover:text-app-accent">
              {fechaCorta(e.fecha_evento)} · {e.titulo}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Noticias que no superaron las reglas para incorporarse solas: el usuario decide qué hacer con cada una. */
export default function BandejaNoticias({ onAbrirEvento }: { onAbrirEvento: (id: number) => void }) {
  const qc = useQueryClient()
  const { showToast } = useInversionesContext()
  const [asociando, setAsociando] = useState<number | null>(null)
  const query = useQuery({ queryKey: qk.de('eventos', 'bandeja'), queryFn: () => getNoticiasEventos('por_revisar') })
  const invalidar = () => void qc.invalidateQueries({ queryKey: qk.de('eventos') })
  const crear = useMutation({
    mutationFn: (id: number) => crearEventoDesdeNoticia(id),
    onSuccess: e => { invalidar(); onAbrirEvento(e.id) },
    onError: err => showToast(parseApiError(err).message, 'error'),
  })
  const descartar = useMutation({ mutationFn: (id: number) => descartarNoticiaEvento(id), onSuccess: invalidar })

  return (
    <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<SkeletonFilas filas={3} />}>
      {query.data && query.data.noticias.length === 0 ? (
        <EmptyState ilustracion="escudo" title="Nada para revisar" description="Las noticias que la app no se anima a convertir sola en evento aparecen acá." />
      ) : (
        <ul className="flex flex-col gap-2">
          {query.data?.noticias.map(n => {
            const tickers = n.entidades.map(x => x.simbolo).filter(Boolean)
            return (
              <li key={n.id} className="rounded-xl border border-app-border p-2.5">
                <div className="text-caption font-semibold text-app-text"><EnlaceFuente url={n.url}>{n.titulo}</EnlaceFuente></div>
                <div className="text-label text-app-text-faint">
                  {n.medio || dominio(n.url)} · {fechaHora(n.fecha_publicacion + 'Z')} · vía {n.proveedor}
                  {n.categoria_sugerida && n.categoria_sugerida !== 'otro' ? ` · parece ${ETIQUETA_CATEGORIA[n.categoria_sugerida as CategoriaEvento]?.toLowerCase() ?? n.categoria_sugerida}` : ''}
                </div>
                {n.fragmento && <p className="mt-1 text-label text-app-text-dim line-clamp-3">{n.fragmento}</p>}
                {tickers.length > 0 && <div className="mt-1 font-mono text-label text-app-text-dim">{tickers.slice(0, 8).join(' · ')}</div>}
                <div className="mt-2 flex gap-1.5">
                  <Button variant="outline" className="h-9 flex-1" loading={crear.isPending && crear.variables === n.id} onClick={() => crear.mutate(n.id)}>Crear evento</Button>
                  <Button variant="outline" className="h-9 flex-1" onClick={() => setAsociando(asociando === n.id ? null : n.id)}>Sumar a uno</Button>
                  <Button variant="ghost" className="h-9" onClick={() => descartar.mutate(n.id)}>Descartar</Button>
                </div>
                {asociando === n.id && <Asociar noticia={n} onListo={() => setAsociando(null)} />}
              </li>
            )
          })}
        </ul>
      )}
    </QueryBoundary>
  )
}
