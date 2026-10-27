import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  borrarEvento, editarEvento, fusionarEvento, getAnalisisEventoTodos, getEventoDetalle, getEventos, guardarVinculoEvento,
  quitarVinculoEvento, type EventoDetalle as EventoDetalleT, type EventoVinculo,
} from '../../api'
import { qk } from '../../api/queryClient'
import { useInversionesContext } from '../../context/InversionesContext'
import { parseApiError } from '../../help/errors/apiErrors'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta, fechaHora } from '../../utils/fechas'
import { ETIQUETA_CONFIANZA, ETIQUETA_ORIGEN, ETIQUETA_RELACION } from '../../utils/eventos'
import Button from '../ui/Button'
import CampoBusqueda from '../ui/CampoBusqueda'
import QueryBoundary from '../ui/QueryBoundary'
import { SkeletonCard } from '../ui/Skeleton'
import AnalisisEvento from './AnalisisEvento'
import EventoForm from './EventoForm'
import {
  dominio, EnlaceFuente, Etiqueta, EtiquetaCategoria, EtiquetaImportancia, EtiquetasEstado, EtiquetaVerificacion,
  textoConocimiento, textoFechaEvento,
} from './comun'

function Vinculo({ v, onConfirmar, onDescartar, onQuitar }: { v: EventoVinculo; onConfirmar: () => void; onDescartar: () => void; onQuitar: () => void }) {
  return (
    <li className={`flex items-start justify-between gap-2 py-2 ${v.estado_revision === 'descartada' ? 'opacity-50' : ''}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-mono text-caption font-bold text-app-text">{v.ticker}</span>
          <Etiqueta>{ETIQUETA_RELACION[v.tipo_relacion] ?? v.tipo_relacion}</Etiqueta>
          {v.relevancia != null && <span className="text-label text-app-text-faint">relevancia {v.relevancia.toFixed(2).replace('.', ',')}</span>}
          {v.estado_revision === 'propuesta' && <Etiqueta tono="warn">Propuesta</Etiqueta>}
          {v.estado_revision === 'descartada' && <Etiqueta tono="neg">No relevante</Etiqueta>}
          {v.metodo === 'automatico' && <span className="text-label text-app-text-faint">automático</span>}
        </div>
        {v.justificacion && <div className="text-label text-app-text-dim">{v.justificacion}</div>}
      </div>
      <div className="flex gap-1 shrink-0">
        {v.estado_revision !== 'confirmada' && (
          <button onClick={onConfirmar} className="text-label font-bold text-app-pos px-2 py-1 rounded-lg hover:bg-app-pos-soft">Confirmar</button>
        )}
        {v.estado_revision !== 'descartada' && (
          <button onClick={onDescartar} className="text-label font-bold text-app-text-dim px-2 py-1 rounded-lg hover:bg-white/5">No aplica</button>
        )}
        {v.metodo === 'manual' && v.estado_revision !== 'descartada' && (
          <button onClick={onQuitar} aria-label={`Quitar ${v.ticker}`} className="text-label font-bold text-app-neg px-2 py-1 rounded-lg hover:bg-app-neg-soft">Quitar</button>
        )}
      </div>
    </li>
  )
}

function Fusionar({ evento, onListo }: { evento: EventoDetalleT; onListo: (destino: number) => void }) {
  const [q, setQ] = useState('')
  const qc = useQueryClient()
  const candidatos = useQuery({
    queryKey: qk.de('eventos', 'fusion', evento.id, q),
    queryFn: () => getEventos({ q: q || undefined, categoria: q ? undefined : [evento.categoria], limite: 12 }),
  })
  const fusion = useMutation({
    mutationFn: (destino: number) => fusionarEvento(evento.id, destino),
    onSuccess: d => {
      void qc.invalidateQueries({ queryKey: qk.de('eventos') })
      onListo(d.id)
    },
  })
  const lista = (candidatos.data?.eventos ?? []).filter(e => e.id !== evento.id)
  return (
    <div className="flex flex-col gap-2">
      <p className="text-caption text-app-text-dim">Elegí el evento que queda. Este se absorbe: sus noticias y tickers pasan al elegido.</p>
      <CampoBusqueda value={q} onChange={setQ} placeholder="Buscar el duplicado…" ariaLabel="Buscar evento destino" />
      <ul className="flex flex-col divide-y divide-app-border-soft">
        {lista.map(e => (
          <li key={e.id} className="flex items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <div className="text-caption text-app-text truncate">{e.titulo}</div>
              <div className="text-label text-app-text-faint">{fechaCorta(e.fecha_evento)} · {ETIQUETA_ORIGEN[e.origen] ?? e.origen}</div>
            </div>
            <Button variant="outline" className="h-9 shrink-0" loading={fusion.isPending && fusion.variables === e.id} onClick={() => fusion.mutate(e.id)}>
              Fusionar
            </Button>
          </li>
        ))}
        {lista.length === 0 && <li className="py-2 text-caption text-app-text-faint">Sin candidatos.</li>}
      </ul>
      {fusion.error && <p className="text-caption text-app-neg">{parseApiError(fusion.error).message}</p>}
    </div>
  )
}

/** Ficha completa de un evento, dentro de un modal: no saca al usuario de lo que estaba mirando. */
export default function EventoDetalle({ id, onCerrar, onAbrir }: { id: number; onCerrar: () => void; onAbrir: (id: number) => void }) {
  const qc = useQueryClient()
  const { showToast } = useInversionesContext()
  const [modo, setModo] = useState<'ver' | 'editar' | 'fusionar'>('ver')
  const [verAnalisis, setVerAnalisis] = useState(false)
  const [nuevoTicker, setNuevoTicker] = useState('')

  const query = useQuery({ queryKey: qk.de('eventos', 'detalle', id), queryFn: () => getEventoDetalle(id) })
  const analisis = useQuery({
    queryKey: qk.de('eventos', 'analisis', id),
    queryFn: () => getAnalisisEventoTodos(id),
    enabled: verAnalisis,
  })
  const invalidar = () => void qc.invalidateQueries({ queryKey: qk.de('eventos') })

  const marcar = useMutation({
    mutationFn: (cambio: { fijado?: boolean; descartado?: boolean }) => editarEvento(id, cambio),
    onSuccess: invalidar,
  })
  const vinculo = useMutation({
    mutationFn: (v: { ticker: string; estado_revision?: 'confirmada' | 'descartada'; tipo_relacion?: string; relevancia?: number | null; justificacion?: string | null }) =>
      guardarVinculoEvento(id, { ...v, relevancia: v.relevancia ?? undefined }),
    onSuccess: invalidar,
    onError: err => showToast(parseApiError(err).message, 'error'),
  })
  const quitar = useMutation({ mutationFn: (ticker: string) => quitarVinculoEvento(id, ticker), onSuccess: invalidar })
  const borrar = useMutation({
    mutationFn: () => borrarEvento(id),
    onSuccess: r => {
      showToast(r === 'borrado' ? 'Evento borrado' : 'Evento descartado: la sincronización no lo vuelve a traer', 'success')
      invalidar()
      onCerrar()
    },
  })

  return (
    <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<SkeletonCard lineas={6} />}>
      {query.data && (() => {
        const e = query.data
        if (modo === 'editar') {
          return <EventoForm evento={e} onCancelar={() => setModo('ver')} onListo={() => { setModo('ver'); showToast('Evento guardado', 'success') }} />
        }
        if (modo === 'fusionar') {
          return <Fusionar evento={e} onListo={destino => { setModo('ver'); onAbrir(destino) }} />
        }
        const conocimiento = textoConocimiento(e)
        const editados = e.campos_editados.filter(c => c !== 'descartado')
        return (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <EtiquetaCategoria categoria={e.categoria} />
                <span className={`font-mono tabular-nums text-caption ${e.es_futuro ? 'text-app-accent' : 'text-app-text-dim'}`}>{textoFechaEvento(e)}</span>
              </div>
              <h3 className="font-display text-title font-semibold text-app-text leading-snug">{e.titulo}</h3>
              {e.subcategoria && <div className="text-caption text-app-text-dim">{e.subcategoria}</div>}
              {conocimiento && <div className="text-label text-app-text-faint">{conocimiento}</div>}
              <div className="flex flex-wrap items-center gap-1">
                <EtiquetaImportancia importancia={e.importancia} />
                <EtiquetasEstado evento={e} />
                <EtiquetaVerificacion verificacion={e.verificacion} />
                <Etiqueta>{ETIQUETA_CONFIANZA[e.confianza_datos]}</Etiqueta>
                <InfoTooltip term="eventos_confianza" label="" />
              </div>
            </div>

            {(e.resumen || e.descripcion) && <p className="text-body text-app-text-dim whitespace-pre-line">{e.resumen || e.descripcion}</p>}
            {e.notas && (
              <div className="rounded-xl bg-app-surface-2 p-2.5 text-caption text-app-text">
                <span className="font-bold text-app-text-faint">Tus notas: </span>{e.notas}
              </div>
            )}

            <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-caption">
              {(e.pais || e.region) && (<><dt className="text-app-text-faint">Lugar</dt><dd className="text-app-text">{[e.pais, e.region].filter(Boolean).join(' · ')}</dd></>)}
              {(e.entidades.empresas?.length ?? 0) > 0 && (<><dt className="text-app-text-faint">Empresas</dt><dd className="text-app-text">{e.entidades.empresas!.join(', ')}</dd></>)}
              {(e.entidades.organismos?.length ?? 0) > 0 && (<><dt className="text-app-text-faint">Organismos</dt><dd className="text-app-text">{e.entidades.organismos!.join(', ')}</dd></>)}
              {(e.entidades.sectores?.length ?? 0) > 0 && (<><dt className="text-app-text-faint">Sectores</dt><dd className="text-app-text">{e.entidades.sectores!.join(', ')}</dd></>)}
              <dt className="text-app-text-faint">Origen</dt>
              <dd className="text-app-text">{ETIQUETA_ORIGEN[e.origen] ?? e.origen}{e.proveedor && e.origen !== 'manual' ? ` (${e.proveedor})` : ''}</dd>
              <dt className="text-app-text-faint">Fuente</dt>
              <dd className="text-app-text min-w-0"><EnlaceFuente url={e.url_fuente}>{e.fuente_principal || dominio(e.url_fuente) || '—'}</EnlaceFuente></dd>
              <dt className="text-app-text-faint">Actualizado</dt>
              <dd className="text-app-text">{fechaHora(e.fecha_actualizacion + 'Z')}</dd>
            </dl>
            {editados.length > 0 && (
              <p className="text-label text-app-text-faint">Corregiste {editados.length} campo{editados.length === 1 ? '' : 's'}: la sincronización no los pisa.</p>
            )}

            <div>
              <div className="mb-1 flex items-center gap-1 text-label font-bold uppercase tracking-wide text-app-text-faint">
                Instrumentos relacionados <InfoTooltip term="eventos_relevancia" label="" />
              </div>
              {e.instrumentos.length === 0 && <p className="text-caption text-app-text-dim">Sin tickers: es un evento general.</p>}
              <ul className="divide-y divide-app-border-soft">
                {e.instrumentos.map(v => (
                  <Vinculo key={v.ticker} v={v}
                    onConfirmar={() => vinculo.mutate({ ticker: v.ticker, estado_revision: 'confirmada', tipo_relacion: v.tipo_relacion, relevancia: v.relevancia, justificacion: v.justificacion })}
                    onDescartar={() => vinculo.mutate({ ticker: v.ticker, estado_revision: 'descartada', tipo_relacion: v.tipo_relacion, relevancia: v.relevancia, justificacion: v.justificacion })}
                    onQuitar={() => quitar.mutate(v.ticker)} />
                ))}
              </ul>
              <form className="mt-1 flex gap-2" onSubmit={ev => {
                ev.preventDefault()
                const t = nuevoTicker.trim().toUpperCase()
                if (t) vinculo.mutate({ ticker: t, estado_revision: 'confirmada', tipo_relacion: 'directa', relevancia: 1 }, { onSuccess: () => setNuevoTicker('') })
              }}>
                <input value={nuevoTicker} onChange={ev => setNuevoTicker(ev.target.value.toUpperCase())} maxLength={16} placeholder="Agregar ticker"
                  aria-label="Agregar ticker" className="flex-1 h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-caption text-app-text outline-none focus:border-app-accent/60" />
                <Button type="submit" variant="outline" className="h-9" disabled={!nuevoTicker.trim()} loading={vinculo.isPending}>Agregar</Button>
              </form>
            </div>

            {e.noticias.length > 0 && (
              <div>
                <div className="mb-1 text-label font-bold uppercase tracking-wide text-app-text-faint">Noticias y fuentes ({e.noticias.length})</div>
                <ul className="flex flex-col gap-1.5">
                  {e.noticias.map(n => (
                    <li key={n.id} className="rounded-lg bg-app-surface-2 p-2 text-caption">
                      <EnlaceFuente url={n.url}>{n.titulo}</EnlaceFuente>
                      <div className="text-label text-app-text-faint">{n.medio || dominio(n.url)} · {fechaHora(n.fecha_publicacion + 'Z')} · vía {n.proveedor}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {e.instrumentos.some(v => v.estado_revision !== 'descartada') && (
              <div className="rounded-xl border border-app-border p-2.5">
                {!verAnalisis ? (
                  <Button variant="outline" className="w-full" onClick={() => setVerAnalisis(true)}>Ver qué hizo el precio alrededor del evento</Button>
                ) : (
                  <QueryBoundary isLoading={analisis.isLoading} error={analisis.error} onRetry={() => void analisis.refetch()} fallback={<SkeletonCard lineas={4} />}>
                    <div className="flex flex-col gap-4">
                      {(analisis.data ?? []).map(a => <AnalisisEvento key={a.ticker} analisis={a} />)}
                    </div>
                  </QueryBoundary>
                )}
              </div>
            )}

            {e.reglas_aplicadas.length > 0 && (
              <details className="text-label text-app-text-faint">
                <summary className="cursor-pointer">Por qué se clasificó así</summary>
                <ul className="mt-1 list-disc pl-4">{e.reglas_aplicadas.slice(0, 20).map((r, i) => <li key={i}>{r}</li>)}</ul>
              </details>
            )}

            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => setModo('editar')}>Editar</Button>
              <Button variant="outline" onClick={() => marcar.mutate({ fijado: !e.fijado })}>{e.fijado ? 'Desfijar' : 'Fijar arriba'}</Button>
              <Button variant="outline" onClick={() => setModo('fusionar')}>Fusionar duplicado</Button>
              {e.descartado ? (
                <Button variant="outline" onClick={() => marcar.mutate({ descartado: false })}>Restaurar</Button>
              ) : (
                <Button variant="danger" loading={borrar.isPending} onClick={() => {
                  const texto = e.origen === 'manual' ? '¿Borrar este evento?' : '¿Descartar este evento? No se borra: queda oculto y la sincronización no lo vuelve a traer.'
                  if (window.confirm(texto)) borrar.mutate()
                }}>
                  {e.origen === 'manual' ? 'Borrar' : 'Descartar'}
                </Button>
              )}
            </div>
          </div>
        )
      })()}
    </QueryBoundary>
  )
}
