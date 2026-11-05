import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { borrarRecordatorio, editarRecordatorio, posponerRecordatorio, type Recordatorio } from '../api'
import { qk } from '../api/queryClient'
import { useInversionesContext } from '../context/InversionesContext'
import { parseApiError } from '../help/errors/apiErrors'
import ScreenHeader from '../components/layout/ScreenHeader'
import RecordatorioForm from '../components/recordatorios/RecordatorioForm'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Modal from '../components/ui/Modal'
import QueryBoundary from '../components/ui/QueryBoundary'
import Segmented from '../components/ui/Segmented'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Icon } from '../components/icons/Icons'
import { fechaCorta, fechaHora } from '../utils/fechas'
import { consultaRecordatorios, textoPlazo } from '../utils/recordatorios'

type Pestana = 'pendientes' | 'hechos'

function Tarjeta({ r, onEditar }: { r: Recordatorio; onEditar: () => void }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { showToast } = useInversionesContext()
  const alListo = (texto: string) => () => {
    void qc.invalidateQueries({ queryKey: qk.de('recordatorios') })
    showToast(texto, 'success')
  }
  const alFallar = (err: unknown) => showToast(parseApiError(err).message, 'error')
  const estado = useMutation({
    mutationFn: (nuevo: Recordatorio['estado']) => editarRecordatorio(r.id, { estado: nuevo }),
    onSuccess: (_, nuevo) => alListo(nuevo === 'hecho' ? 'Marcado como hecho' : 'Recordatorio reabierto')(),
    onError: alFallar,
  })
  const posponer = useMutation({
    mutationFn: (dias: 1 | 7) => posponerRecordatorio(r.id, dias),
    onSuccess: d => alListo(`Pospuesto al ${fechaCorta(d.fecha)}`)(),
    onError: alFallar,
  })
  const borrar = useMutation({
    mutationFn: () => borrarRecordatorio(r.id),
    onSuccess: alListo('Recordatorio borrado'),
    onError: alFallar,
  })
  const pendiente = r.estado === 'pendiente'
  const ocupado = estado.isPending || posponer.isPending || borrar.isPending
  const seguimiento = r.hecho_en
    ? `Hecho el ${fechaHora(r.hecho_en + 'Z')}`
    : r.aviso_enviado_en
      ? `Aviso enviado el ${fechaHora(r.aviso_enviado_en + 'Z')}`
      : r.vencido ? 'Aviso todavía sin enviar: sale apenas se pueda.' : null

  return (
    <article className={`rounded-2xl border bg-app-surface p-3.5 ${r.vencido ? 'border-app-accent/50' : 'border-app-border'}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 break-words text-body font-semibold text-app-text">{r.titulo}</h3>
        {pendiente && (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-label font-bold ${r.vencido ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-dim'}`}>
            {textoPlazo(r)}
          </span>
        )}
      </div>
      <div className="mt-0.5 font-mono text-caption tabular-nums text-app-text-dim">
        {r.hora ? fechaHora(r.vence_en) : fechaCorta(r.fecha)}
      </div>
      {r.nota && <p className="mt-2 whitespace-pre-line break-words text-caption text-app-text">{r.nota}</p>}
      {r.tickers.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {r.tickers.map(t => (
            <button key={t} onClick={() => navigate(`/analisis-tecnico?ticker=${encodeURIComponent(t)}`)}
              aria-label={`Ver análisis técnico de ${t}`}
              className="min-h-8 rounded-[9px] bg-app-accent-soft px-2.5 font-mono text-label font-bold text-app-accent transition-transform duration-150 active:scale-95">
              {t}
            </button>
          ))}
        </div>
      )}
      {r.evento_titulo && <p className="mt-2 text-label text-app-text-faint">Evento: {r.evento_titulo}</p>}
      {seguimiento && <p className="mt-2 text-label text-app-text-faint">{seguimiento}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        {pendiente ? (
          <>
            <Button variant="outline" className="h-9 flex-1 whitespace-nowrap" disabled={ocupado} icon={<Icon name="check" className="w-4 h-4" />} onClick={() => estado.mutate('hecho')}>Hecho</Button>
            <Button variant="outline" className="h-9 flex-1 whitespace-nowrap" disabled={ocupado} onClick={() => posponer.mutate(1)}>+1 día</Button>
            <Button variant="outline" className="h-9 flex-1 whitespace-nowrap" disabled={ocupado} onClick={() => posponer.mutate(7)}>+1 semana</Button>
            <Button variant="ghost" className="h-9 flex-1 whitespace-nowrap" disabled={ocupado} icon={<Icon name="edit" className="w-4 h-4" />} onClick={onEditar}>Editar</Button>
          </>
        ) : (
          <Button variant="outline" className="h-9 flex-1" disabled={ocupado} onClick={() => estado.mutate('pendiente')}>Reabrir</Button>
        )}
        <Button variant="ghost" className="h-9 flex-1 whitespace-nowrap" disabled={ocupado} icon={<Icon name="trash" className="w-4 h-4" />}
          onClick={() => { if (window.confirm('¿Borrar este recordatorio?')) borrar.mutate() }}>
          Borrar
        </Button>
      </div>
    </article>
  )
}

export default function Recordatorios() {
  const { showToast } = useInversionesContext()
  const query = useQuery(consultaRecordatorios)
  const [pestana, setPestana] = useState<Pestana>('pendientes')
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<Recordatorio | null>(null)

  const items = query.data?.items ?? []
  const pendientes = items.filter(r => r.estado === 'pendiente')
  const hechos = items.filter(r => r.estado !== 'pendiente')
  const visibles = pestana === 'pendientes' ? pendientes : hechos

  return (
    <div className="pb-4">
      <ScreenHeader title="Recordatorios" />
      <p className="-mt-1 mb-3 text-caption text-app-text-dim">
        Dejate un aviso para una fecha: llega al celular por Telegram y también aparece en el Resumen.
      </p>
      <Button className="mb-3 w-full" icon={<Icon name="plus" className="w-4 h-4" />} onClick={() => setCreando(true)}>Recordatorio</Button>

      {query.data && !query.data.avisos_activos && (
        <div role="alert" className="mb-3 rounded-2xl border border-app-accent/40 bg-app-accent-soft p-3 text-caption text-app-text">
          <span className="font-semibold">Los avisos no van a llegar al celular</span> porque {query.data.motivo_inactivo}. Los recordatorios se guardan igual, se ven en la app y salen cuando se resuelva.
        </div>
      )}

      <div className="mb-3">
        <Segmented
          options={[
            { value: 'pendientes', label: `Pendientes (${pendientes.length})` },
            { value: 'hechos', label: `Hechos (${hechos.length})` },
          ]}
          value={pestana}
          onChange={setPestana}
        />
      </div>

      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<SkeletonCard lineas={4} />}>
        {visibles.length === 0 ? (
          <EmptyState
            title={pestana === 'pendientes' ? 'Sin recordatorios pendientes' : 'Todavía no marcaste ninguno como hecho'}
            description={pestana === 'pendientes' ? 'Sirven para acordarte de mirar algo en una fecha: un balance, una elección, una entrada que estás esperando.' : 'Lo que marques como hecho queda acá.'}
          />
        ) : (
          <div className="flex flex-col gap-2">
            {visibles.map(r => <Tarjeta key={r.id} r={r} onEditar={() => setEditando(r)} />)}
          </div>
        )}
      </QueryBoundary>

      <Modal open={creando} onClose={() => setCreando(false)} title="Nuevo recordatorio">
        {creando && <RecordatorioForm onCancelar={() => setCreando(false)} onListo={() => { setCreando(false); showToast('Recordatorio creado', 'success') }} />}
      </Modal>
      <Modal open={editando != null} onClose={() => setEditando(null)} title="Editar recordatorio">
        {editando && <RecordatorioForm key={editando.id} recordatorio={editando} onCancelar={() => setEditando(null)} onListo={() => { setEditando(null); showToast('Recordatorio guardado', 'success') }} />}
      </Modal>
    </div>
  )
}
