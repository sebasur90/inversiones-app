import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  borrarDecision, calificarRevision, editarDecision, getDecision, revisarDecision, type DecisionDetalle as Detalle,
  type RevisionDecision,
} from '../../api'
import { qk } from '../../api/queryClient'
import ScreenHeader from '../../components/layout/ScreenHeader'
import Card from '../../components/ui/Card'
import Button from '../../components/ui/Button'
import Segmented from '../../components/ui/Segmented'
import QueryBoundary from '../../components/ui/QueryBoundary'
import { SkeletonCard } from '../../components/ui/Skeleton'
import InfoTooltip from '../../help/components/InfoTooltip'
import { parseApiError } from '../../help/errors/apiErrors'
import ErrorBanner from '../../help/components/ErrorBanner'
import { TEXTO_ACCION } from '../../components/decisiones/GuardarDecision'
import { ConclusionBadge, Lista, num, pct, precio } from '../../components/decisiones/comun'

type Proceso = 'bien' | 'regular' | 'mal'

/** Una decisión guardada: lo que la app concluía ese día (congelado) y sus revisiones. */
export default function DecisionDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const n = Number(id)
  const q = useQuery({ queryKey: qk.de('decision', n), queryFn: () => getDecision(n), enabled: Number.isFinite(n) })
  const d = q.data
  const refrescar = () => {
    void queryClient.invalidateQueries({ queryKey: qk.de('decision', n) })
    void queryClient.invalidateQueries({ queryKey: qk.de('decisiones') })
    void queryClient.invalidateQueries({ queryKey: qk.de('decisiones-pendientes') })
    void queryClient.invalidateQueries({ queryKey: qk.de('decisiones-aprendizaje') })
  }
  const revisar = useMutation({ mutationFn: () => revisarDecision(n, {}), onSuccess: refrescar })
  const editar = useMutation({ mutationFn: (b: Parameters<typeof editarDecision>[1]) => editarDecision(n, b), onSuccess: refrescar })
  const borrar = useMutation({ mutationFn: () => borrarDecision(n), onSuccess: () => { refrescar(); navigate('/decisiones?tab=historial') } })
  const [nota, setNota] = useState<string | null>(null)

  return (
    <div className="pb-4">
      <ScreenHeader title="Decisión" onBack={() => navigate(-1)} />
      <QueryBoundary isLoading={q.isLoading} error={q.error} onRetry={() => void q.refetch()} fallback={<SkeletonCard lineas={6} />}>
        {d && (
          <div className="flex flex-col gap-3">
            <Card>
              <div className="text-title font-bold text-app-text">{d.ticker} <span className="text-body font-normal text-app-text-dim">{d.nombre}</span></div>
              <div className="text-label text-app-text-faint">{d.creada_en.slice(0, 16).replace('T', ' ')} UTC · {d.modo === 'posicion' ? 'posición' : 'oportunidad'} · {d.cartera ?? 'consolidado'}</div>
              <div className="text-caption text-app-text mt-2">Decidiste: <b>{TEXTO_ACCION[d.accion_elegida] ?? d.accion_elegida}</b></div>
              <div className="mt-1"><ConclusionBadge tipo={d.conclusion.tipo} titulo={d.conclusion.titulo} /></div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-caption mt-2">
                <span className="text-app-text-faint">Orden al decidir</span><span className="text-right font-mono">{d.orden != null ? num(d.orden) : 'incompleto'}</span>
                <span className="text-app-text-faint">Precio de referencia</span><span className="text-right font-mono">{precio(d.precio_ref, d.moneda)}</span>
                <span className="text-app-text-faint">Incertidumbre</span><span className="text-right">{d.calidad.incertidumbre}</span>
                <span className="text-app-text-faint">Revisar el</span><span className="text-right font-mono">{d.revisar_el ?? '—'}</span>
              </div>
              {d.calidad.advertencias_fechas.map(w => <p key={w} className="text-label text-app-warn mt-1">⚠ {w}</p>)}
              <div className="flex flex-wrap gap-2 mt-3">
                <Button variant={d.ejecutada ? 'primary' : 'outline'} onClick={() => editar.mutate({ ejecutada: !d.ejecutada })}>
                  {d.ejecutada ? '✓ La llevé a cabo' : 'Marcar como ejecutada'}
                </Button>
                <Button variant="outline" onClick={() => editar.mutate({ estado: d.estado === 'abierta' ? 'cerrada' : 'abierta' })}>
                  {d.estado === 'abierta' ? 'Cerrar' : 'Reabrir'}
                </Button>
              </div>
              {editar.error && <div className="mt-2"><ErrorBanner error={parseApiError(editar.error)} /></div>}
            </Card>

            <Card>
              <div className="text-label font-bold uppercase text-app-text-faint mb-1">Tu nota</div>
              <textarea value={nota ?? d.nota ?? ''} onChange={e => setNota(e.target.value)} rows={3} maxLength={2000}
                        className="w-full px-3 py-2 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text" />
              {nota != null && nota !== (d.nota ?? '') && (
                <Button variant="outline" onClick={() => { editar.mutate({ nota }); setNota(null) }}>Guardar nota</Button>
              )}
            </Card>

            <Card>
              <div className="text-label font-bold uppercase text-app-text-faint mb-1">Lo que se veía ese día</div>
              <div className="text-label font-bold text-app-pos mt-1">A favor</div><Lista items={d.argumentos.a_favor} vacio="—" />
              <div className="text-label font-bold text-app-neg mt-2">En contra</div><Lista items={d.argumentos.en_contra} vacio="—" />
              <div className="text-label font-bold text-app-text-faint mt-2">Condiciones de invalidación</div>
              <Lista items={d.condiciones.invalidacion.map(c => c.texto)} vacio="—" />
              {d.condiciones.entrada?.texto && <p className="text-caption text-app-text mt-1">Entrada: {d.condiciones.entrada.texto}</p>}
              <details className="text-label text-app-text-faint mt-2">
                <summary className="cursor-pointer">Supuestos y versiones de las reglas</summary>
                <Lista items={d.supuestos} />
                <p className="mt-1">{Object.entries(d.versiones).map(([k, v]) => `${k} v${v ?? '—'}`).join(' · ')}</p>
              </details>
              <p className="text-label text-app-text-faint mt-2">Alternativas evaluadas: {d.alternativas.map(a => `${a.ticker}${a.rol === 'elegida' ? ' (elegida)' : ''}`).join(', ') || '—'}.</p>
            </Card>

            <div className="flex items-center justify-between px-0.5">
              <span className="text-strong font-bold text-app-text flex items-center gap-1">Revisiones <InfoTooltip term="decisiones_revision" label="" /></span>
              <Button onClick={() => revisar.mutate()} loading={revisar.isPending}>Revisar ahora</Button>
            </div>
            {revisar.error && <ErrorBanner error={parseApiError(revisar.error)} />}
            {d.revisiones.length === 0 && <p className="text-caption text-app-text-dim px-0.5">Todavía no la revisaste.</p>}
            {[...d.revisiones].reverse().map(r => <TarjetaRevision key={r.id} r={r} d={d} onCambio={refrescar} />)}

            <Button variant="danger" onClick={() => { if (window.confirm('¿Borrar esta decisión y sus revisiones? No se puede deshacer.')) borrar.mutate() }}>
              Borrar decisión
            </Button>
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}

const TEXTO_SUPUESTO: Record<string, string> = {
  confirmado: 'se confirmó', refutado: 'no se cumplió', pendiente: 'pendiente', sin_dato: 'sin dato', a_tu_juicio: 'a tu juicio',
}

function TarjetaRevision({ r, d, onCambio }: { r: RevisionDecision; d: Detalle; onCambio: () => void }) {
  const c = r.comparacion
  const calificar = useMutation({ mutationFn: (p: Proceso) => calificarRevision(r.id, { evaluacion_proceso: p }), onSuccess: onCambio })
  return (
    <Card>
      <div className="text-caption font-bold text-app-text">{r.creada_en.slice(0, 10)} · {c.dias ?? '—'} días después</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-caption mt-2">
        <span className="text-app-text-faint">Precio</span>
        <span className="text-right font-mono">{precio(c.precio.referencia, c.precio.moneda)} → {precio(c.precio.actual, c.precio.moneda)} ({pct(c.precio.variacion, 1, true)})</span>
        <span className="text-app-text-faint">{c.benchmark?.nombre ?? 'Índice'}</span>
        <span className="text-right font-mono">{c.benchmark ? pct(c.benchmark.variacion, 1, true) : 'sin dato'}</span>
        <span className="text-app-text-faint">Orden</span>
        <span className="text-right font-mono">{num(c.orden.antes)} → {num(c.orden.ahora)}</span>
        <span className="text-app-text-faint">Conclusión</span>
        <span className="text-right">{c.conclusion.ahora ?? '—'}</span>
      </div>
      {c.precio.nota && <p className="text-label text-app-warn">{c.precio.nota}</p>}
      {c.benchmark_nota && <p className="text-label text-app-text-faint">{c.benchmark_nota}</p>}
      {c.alternativas.length > 0 && (
        <p className="text-label text-app-text-dim mt-1">Alternativas: {c.alternativas.map(a => `${a.ticker} ${pct(a.variacion, 1, true)}`).join(' · ')}</p>
      )}
      <div className="text-label font-bold uppercase text-app-text-faint mt-2">Dimensiones</div>
      <ul className="text-caption text-app-text">
        {c.dimensiones.map(x => <li key={x.dimension}>{x.nombre}: {num(x.antes)} → {num(x.ahora)}{x.delta != null ? ` (${x.delta > 0 ? '+' : ''}${num(x.delta, 1)})` : ''}</li>)}
      </ul>
      {c.banderas_nuevas.length > 0 && <p className="text-label text-app-warn mt-1">Riesgos que aparecieron: {c.banderas_nuevas.map(b => b.texto).join(' · ')}</p>}
      <div className="text-label font-bold uppercase text-app-text-faint mt-2">Supuestos</div>
      <ul className="text-caption text-app-text flex flex-col gap-0.5">
        {c.supuestos.map(s => <li key={s.supuesto}>{s.supuesto}: <b>{TEXTO_SUPUESTO[s.estado] ?? s.estado}</b></li>)}
      </ul>
      {c.condiciones.some(x => x.cumplida) && (
        <p className="text-caption text-app-warn mt-1">Se cumplió: {c.condiciones.filter(x => x.cumplida).map(x => x.texto).join(' · ')}</p>
      )}
      {c.riesgo.texto && <p className="text-label text-app-text-dim mt-1">{c.riesgo.texto}.</p>}
      {c.resultado && <p className="text-caption text-app-text mt-1">Resultado aproximado: {pct(c.resultado.variacion_precio, 1, true)}{c.resultado.contra_indice != null ? ` (${pct(c.resultado.contra_indice, 1, true)} contra el índice)` : ''}. {c.resultado.nota}</p>}
      {!d.ejecutada && c.sugerencia && <p className="text-label text-app-accent mt-1">{c.sugerencia}</p>}
      <div className="mt-3">
        <div className="text-label font-bold uppercase text-app-text-faint mb-1">¿Cómo fue tu proceso? (no el resultado)</div>
        <Segmented<Proceso | 'sin'>
          options={[{ value: 'sin', label: 'Sin calificar' }, { value: 'bien', label: 'Bien' }, { value: 'regular', label: 'Regular' }, { value: 'mal', label: 'Mal' }]}
          value={r.evaluacion_proceso ?? 'sin'} onChange={v => { if (v !== 'sin') calificar.mutate(v) }}
        />
      </div>
      <p className="text-label text-app-text-faint mt-2">{c.salvedad}</p>
    </Card>
  )
}
