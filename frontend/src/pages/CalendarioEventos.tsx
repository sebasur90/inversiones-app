import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { isAxiosError } from 'axios'
import { getEventos, getFuentesEventos, getOpcionesEventos, sincronizarEventos } from '../api'
import { qk } from '../api/queryClient'
import { useInversionesContext } from '../context/InversionesContext'
import { usePreferencia } from '../hooks/usePreferencia'
import InfoTooltip from '../help/components/InfoTooltip'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Modal from '../components/ui/Modal'
import Button from '../components/ui/Button'
import QueryBoundary from '../components/ui/QueryBoundary'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Icon } from '../components/icons/Icons'
import CalendarioMes from '../components/eventos/CalendarioMes'
import TimelineEventos from '../components/eventos/TimelineEventos'
import TarjetaEvento from '../components/eventos/TarjetaEvento'
import FiltrosEventos from '../components/eventos/FiltrosEventos'
import EventoDetalle from '../components/eventos/EventoDetalle'
import EventoForm from '../components/eventos/EventoForm'
import BandejaNoticias from '../components/eventos/BandejaNoticias'
import FuentesEventos from '../components/eventos/FuentesEventos'
import ImpactoActivos from '../components/eventos/ImpactoActivos'
import { fechaHora, fechaLarga } from '../utils/fechas'
import { aParametros, FILTROS_VACIOS, grillaMes, isoDia, parseFiltros, serializarFiltros } from '../utils/eventos'

type Pestana = 'calendario' | 'timeline' | 'impacto'
const PESTANAS: { value: Pestana; label: string }[] = [
  { value: 'calendario', label: 'Calendario' },
  { value: 'timeline', label: 'Timeline' },
  { value: 'impacto', label: 'Impacto en activos' },
]
const esPestana = (v: string | null): v is Pestana => v === 'calendario' || v === 'timeline' || v === 'impacto'
const CLAVE_FILTROS = 'inversiones-eventos-filtros'

function VistaCalendario({ parametros, onAbrir }: { parametros: ReturnType<typeof aParametros>; onAbrir: (id: number) => void }) {
  const [mes, setMes] = useState(dayjs().format('YYYY-MM'))
  const [dia, setDia] = useState<string | null>(isoDia(dayjs()))
  const { desde, hasta } = useMemo(() => grillaMes(mes), [mes])
  const clave = JSON.stringify(parametros)
  // El rango lo pone la grilla; el resto de los filtros se respeta. La temporalidad sí aplica: con
  // "futuros" los días pasados quedan vacíos.
  const delMes = useQuery({
    queryKey: qk.de('eventos', 'mes', mes, clave),
    queryFn: () => getEventos({ ...parametros, desde, hasta, limite: 500, orden: 'asc' }),
    placeholderData: prev => prev,
  })
  const proximos = useQuery({
    queryKey: qk.de('eventos', 'proximos', clave),
    queryFn: () => getEventos({ ...parametros, temporalidad: 'futuros', orden: 'asc', limite: 5 }),
  })
  const delDia = (delMes.data?.eventos ?? []).filter(e => e.fecha_evento === dia)

  return (
    <div className="flex flex-col gap-3">
      <QueryBoundary isLoading={delMes.isLoading} error={delMes.error} onRetry={() => void delMes.refetch()} fallback={<SkeletonCard lineas={6} />}>
        <CalendarioMes mes={mes} eventos={delMes.data?.eventos ?? []} diaElegido={dia} onElegirDia={setDia} onCambiarMes={m => { setMes(m); setDia(null) }} />
      </QueryBoundary>
      {dia && (
        <div className="flex flex-col gap-2">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">{fechaLarga(dia)}</div>
          {delDia.length === 0 ? (
            <p className="text-caption text-app-text-dim">Sin eventos ese día.</p>
          ) : (
            delDia.map(e => <TarjetaEvento key={e.id} evento={e} onAbrir={onAbrir} />)
          )}
        </div>
      )}
      <div className="flex flex-col gap-2">
        <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">Lo que viene</div>
        <QueryBoundary isLoading={proximos.isLoading} error={proximos.error} onRetry={() => void proximos.refetch()} fallback={<SkeletonCard lineas={3} />}>
          {(proximos.data?.eventos ?? []).length === 0 ? (
            <p className="text-caption text-app-text-dim">No hay eventos futuros cargados. Las fechas de balances llegan solas; las elecciones y reuniones de bancos centrales se cargan a mano o importando un calendario.</p>
          ) : (
            proximos.data!.eventos.map(e => <TarjetaEvento key={e.id} evento={e} onAbrir={onAbrir} />)
          )}
        </QueryBoundary>
      </div>
    </div>
  )
}

export default function CalendarioEventos() {
  const qc = useQueryClient()
  const { showToast } = useInversionesContext()
  const [params, setParams] = useSearchParams()
  const pestana: Pestana = esPestana(params.get('tab')) ? (params.get('tab') as Pestana) : 'calendario'
  const tickerImpacto = params.get('ticker')
  const cambiarParam = (clave: string, valor: string | null) => {
    const p = new URLSearchParams(params)
    if (valor) p.set(clave, valor)
    else p.delete(clave)
    setParams(p, { replace: true })
  }

  const [filtros, setFiltros] = usePreferencia(CLAVE_FILTROS, FILTROS_VACIOS, parseFiltros, serializarFiltros)
  const [q, setQ] = useState('')
  const [qDiferida, setQDiferida] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setQDiferida(q), 300)
    return () => clearTimeout(t)
  }, [q])
  const parametros = useMemo(() => aParametros(filtros, qDiferida), [filtros, qDiferida])

  const [abierto, setAbierto] = useState<number | null>(null)
  const [creando, setCreando] = useState(false)
  const [verBandeja, setVerBandeja] = useState(false)
  const [verFuentes, setVerFuentes] = useState(false)

  const opciones = useQuery({ queryKey: qk.de('eventos', 'opciones'), queryFn: getOpcionesEventos })
  const fuentes = useQuery({
    queryKey: qk.de('eventos', 'fuentes'),
    queryFn: getFuentesEventos,
    refetchInterval: query => (query.state.data?.en_curso ? 3000 : false),
  })
  // Cuando termina una sincronización, se refresca todo lo de la pantalla.
  const enCursoAntes = useRef(false)
  useEffect(() => {
    const ahora = !!fuentes.data?.en_curso
    if (enCursoAntes.current && !ahora) {
      void qc.invalidateQueries({ queryKey: qk.de('eventos') })
      showToast('Fuentes de eventos actualizadas', 'success')
    }
    enCursoAntes.current = ahora
  }, [fuentes.data?.en_curso, qc, showToast])
  const sincronizar = useMutation({
    mutationFn: sincronizarEventos,
    onSuccess: () => void fuentes.refetch(),
    onError: err => showToast(isAxiosError(err) && err.response?.status === 409 ? 'Ya se están actualizando las fuentes' : 'No se pudo iniciar la actualización', 'error'),
  })

  const f = fuentes.data
  const conProblema = (f?.fuentes ?? []).filter(x => x.estado && ['error', 'rate_limited', 'cupo_agotado', 'parcial'].includes(x.estado))
  const sinConfigurar = (f?.fuentes ?? []).filter(x => !x.configurado)
  const actualizando = sincronizar.isPending || !!f?.en_curso

  return (
    <div className="pb-4">
      <ScreenHeader title="Calendario de eventos" />
      <p className="-mt-1 mb-3 flex items-center gap-1 text-caption text-app-text-dim">
        Acontecimientos pasados y futuros y qué hizo el mercado alrededor de cada uno.
        <InfoTooltip term="eventos_que_es" label="" />
      </p>

      <div className="mb-2 flex gap-2">
        <Button className="flex-1" icon={<Icon name="plus" className="w-4 h-4" />} onClick={() => setCreando(true)}>Evento</Button>
        <Button variant="outline" className="flex-1" loading={actualizando} icon={<Icon name="sync" className="w-4 h-4" />} onClick={() => sincronizar.mutate()}>
          {actualizando ? 'Actualizando' : 'Actualizar'}
        </Button>
        <Button variant="outline" onClick={() => setVerBandeja(true)} aria-label="Noticias para revisar">
          Revisar{f?.por_revisar ? ` (${f.por_revisar})` : ''}
        </Button>
      </div>
      <button onClick={() => setVerFuentes(true)} className="mb-3 w-full text-left text-label text-app-text-faint hover:text-app-text-dim">
        {f?.ultima_sincronizacion ? `Fuentes consultadas ${fechaHora(f.ultima_sincronizacion + 'Z')}` : 'Las fuentes todavía no se consultaron'}
        {sinConfigurar.length > 0 && <span className="text-app-text-dim"> · {sinConfigurar.map(s => s.etiqueta.split(' (')[0]).join(', ')} sin configurar</span>}
        {conProblema.length > 0 && <span className="text-app-warn"> · {conProblema.length} con problemas</span>}
        <span className="text-app-accent"> · ver fuentes</span>
      </button>

      <div className="mb-3">
        <Segmented options={PESTANAS} value={pestana} onChange={v => cambiarParam('tab', v)} />
      </div>

      {pestana !== 'impacto' && (
        <FiltrosEventos filtros={filtros} onCambiar={setFiltros} q={q} onBuscar={setQ} opciones={opciones.data} />
      )}
      {pestana === 'calendario' && <VistaCalendario parametros={parametros} onAbrir={setAbierto} />}
      {pestana === 'timeline' && <TimelineEventos parametros={parametros} onAbrir={setAbierto} />}
      {pestana === 'impacto' && <ImpactoActivos ticker={tickerImpacto} onTicker={t => cambiarParam('ticker', t)} onAbrir={setAbierto} />}

      <p className="mt-4 text-label text-app-text-faint">
        Lo que se ve acá es contexto para investigar, no una recomendación: que un evento esté cerca de un movimiento no prueba que lo haya causado.
      </p>

      <Modal open={abierto != null} onClose={() => setAbierto(null)} title="Evento">
        {abierto != null && <EventoDetalle key={abierto} id={abierto} onCerrar={() => setAbierto(null)} onAbrir={setAbierto} />}
      </Modal>
      <Modal open={creando} onClose={() => setCreando(false)} title="Nuevo evento">
        {creando && <EventoForm onCancelar={() => setCreando(false)} onListo={e => { setCreando(false); showToast('Evento creado', 'success'); setAbierto(e.id) }} />}
      </Modal>
      <Modal open={verBandeja} onClose={() => setVerBandeja(false)} title="Para revisar">
        <p className="mb-2 flex items-center gap-1 text-caption text-app-text-dim">
          Noticias que no se convirtieron solas en evento. <InfoTooltip term="eventos_bandeja" label="" />
        </p>
        {verBandeja && <BandejaNoticias onAbrirEvento={id => { setVerBandeja(false); setAbierto(id) }} />}
      </Modal>
      <Modal open={verFuentes} onClose={() => setVerFuentes(false)} title="Fuentes de datos">
        {f && <FuentesEventos fuentes={f} />}
      </Modal>
    </div>
  )
}
