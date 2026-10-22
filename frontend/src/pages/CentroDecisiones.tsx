import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  explorarDecisiones, getAprendizajeDecisiones, getDecisiones, getDecisionesPendientes, getFacetasDecision,
  getPreferenciasDecision, type DecisionGuardada, type ExplorarItem, type PatronAprendizaje,
} from '../api'
import { qk } from '../api/queryClient'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import { SkeletonFilas } from '../components/ui/Skeleton'
import AvatarTicker from '../components/ui/AvatarTicker'
import SelectorInstrumento from '../components/inversiones/SelectorInstrumento'
import InfoTooltip from '../help/components/InfoTooltip'
import PreferenciasDecisionModal from '../components/decisiones/PreferenciasDecision'
import { BarraDimension, ConclusionBadge, num } from '../components/decisiones/comun'
import { TEXTO_ACCION } from '../components/decisiones/GuardarDecision'

type Pestana = 'oportunidades' | 'cartera' | 'historial'
type Filtro = { tipo: 'sector' | 'region' | 'pais' | 'tematica'; valor: string; etiqueta: string }

const TEXTO_HORIZONTE: Record<string, string> = { corto: 'corto plazo', mediano: 'mediano plazo', largo: 'largo plazo' }
const TEXTO_OBJETIVO: Record<string, string> = {
  crecimiento: 'crecimiento', valor: 'valoración', ingresos: 'ingresos', diversificacion: 'diversificación',
}

/**
 * Centro de Decisiones: buscar oportunidades, evaluar posiciones y revisar decisiones guardadas.
 * Todo es análisis y registro explícito: nada de acá escribe movimientos ni opera.
 */
export default function CentroDecisiones() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const pestana = (params.get('tab') as Pestana) || 'oportunidades'
  const prefs = useQuery({ queryKey: qk.de('decisiones-preferencias'), queryFn: getPreferenciasDecision })
  const [prefsAbiertas, setPrefsAbiertas] = useState(false)

  return (
    <div className="pb-4">
      <ScreenHeader title="Centro de Decisiones" />
      <div className="flex flex-col gap-3">
        <Segmented
          options={[{ value: 'oportunidades', label: 'Oportunidades' }, { value: 'cartera', label: 'Mi cartera' }, { value: 'historial', label: 'Historial' }]}
          value={pestana} onChange={v => setParams({ tab: v }, { replace: true })}
        />
        {prefs.data && (
          <button type="button" onClick={() => setPrefsAbiertas(true)}
                  className="text-left rounded-xl bg-app-surface border border-app-border px-3 py-2 text-caption text-app-text-dim">
            Analizando a <b className="text-app-text">{TEXTO_HORIZONTE[prefs.data.horizonte]}</b>, objetivo{' '}
            <b className="text-app-text">{TEXTO_OBJETIVO[prefs.data.objetivo]}</b>, enfoque <b className="text-app-text">{prefs.data.enfoque}</b>
            {prefs.data.tolerancia ? <>, tolerancia <b className="text-app-text">{prefs.data.tolerancia}</b></> : ', tolerancia sin definir'}.
            <span className="text-app-accent font-bold ml-1">Cambiar</span>
          </button>
        )}
        {pestana === 'oportunidades' && <Oportunidades onAbrir={t => navigate(`/decisiones/analisis/${encodeURIComponent(t)}`)} />}
        {pestana === 'cartera' && <MiCartera onAbrir={t => navigate(`/decisiones/posicion/${encodeURIComponent(t)}`)} />}
        {pestana === 'historial' && <Historial onAbrir={id => navigate(`/decisiones/${id}`)} />}
      </div>
      {prefs.data && <PreferenciasDecisionModal abierto={prefsAbiertas} onClose={() => setPrefsAbiertas(false)} actuales={prefs.data} />}
    </div>
  )
}

function Oportunidades({ onAbrir }: { onAbrir: (ticker: string) => void }) {
  const [filtro, setFiltro] = useState<Filtro | null>(null)
  const [eje, setEje] = useState<'tematica' | 'sector' | 'region' | 'pais'>('tematica')
  const facetas = useQuery({ queryKey: qk.de('decisiones-facetas'), queryFn: getFacetasDecision })
  const explorar = useQuery({
    queryKey: qk.de('decisiones-explorar', filtro?.tipo, filtro?.valor),
    queryFn: () => explorarDecisiones(filtro ? { [filtro.tipo]: filtro.valor } : {}),
    enabled: filtro != null,
  })
  const opciones: Filtro[] = useMemo(() => {
    const f = facetas.data
    if (!f) return []
    if (eje === 'tematica') return f.tematicas.map(t => ({ tipo: 'tematica' as const, valor: t.clave, etiqueta: t.nombre }))
    const lista = eje === 'sector' ? f.sectores : eje === 'region' ? f.regiones : f.paises
    return lista.map(x => ({ tipo: eje, valor: x.valor, etiqueta: `${x.valor} (${x.n})` }))
  }, [facetas.data, eje])

  return (
    <>
      <Card>
        <div className="text-strong font-bold text-app-text flex items-center gap-1 mb-2">
          Analizar un activo <InfoTooltip term="decisiones_que_es" label="" />
        </div>
        <SelectorInstrumento onElegir={i => onAbrir(i.simbolo)} yaSeguidos={new Set()} etiquetaYaElegido="" />
      </Card>

      <Card>
        <div className="text-strong font-bold text-app-text mb-2">Explorar</div>
        <Segmented options={[{ value: 'tematica', label: 'Temática' }, { value: 'sector', label: 'Sector' },
          { value: 'region', label: 'Región' }, { value: 'pais', label: 'País' }]} value={eje} onChange={setEje} />
        <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4 mt-2">
          {opciones.map(o => (
            <button key={o.tipo + o.valor} type="button" onClick={() => setFiltro(o)}
                    className={`shrink-0 font-semibold text-caption px-3 py-1.5 rounded-[10px] border ${
                      filtro?.valor === o.valor && filtro?.tipo === o.tipo ? 'bg-app-accent-soft border-app-accent text-app-accent' : 'bg-app-surface border-app-border text-app-text-dim'}`}>
              {o.etiqueta}
            </button>
          ))}
        </div>
        {facetas.data && (
          <p className="text-label text-app-text-faint mt-2">
            {facetas.data.cobertura.texto} {eje === 'tematica' && facetas.data.tematicas_no_cubiertas}
          </p>
        )}
      </Card>

      {filtro && (
        <QueryBoundary isLoading={explorar.isLoading} error={explorar.error} onRetry={() => void explorar.refetch()} fallback={<SkeletonFilas filas={5} />}>
          {explorar.data && (
            <div className="flex flex-col gap-2">
              {explorar.data.tematica && <p className="text-label text-app-text-faint">Regla: {explorar.data.tematica.regla}.</p>}
              <p className="text-label text-app-text-faint">{explorar.data.nota}</p>
              {explorar.data.items.length === 0 ? (
                <EmptyState ilustracion="lupa" title="Ningún activo cumple ese filtro" description={
                  explorar.data.sin_dato_tematica ? `${explorar.data.sin_dato_tematica} quedaron afuera por falta de datos.` : undefined} />
              ) : explorar.data.items.map(it => <FilaExplorar key={it.ticker_base} it={it} onAbrir={() => onAbrir(it.ticker)} />)}
              {explorar.data.truncado && <p className="text-label text-app-text-faint">Se muestran los primeros {explorar.data.items.length} de {explorar.data.total}.</p>}
            </div>
          )}
        </QueryBoundary>
      )}
      <Recientes />
    </>
  )
}

function FilaExplorar({ it, onAbrir }: { it: ExplorarItem; onAbrir: () => void }) {
  return (
    <button type="button" onClick={onAbrir} className="text-left rounded-xl bg-app-surface border border-app-border p-3 flex flex-col gap-2 active:scale-[0.99] transition-transform">
      <div className="flex items-center gap-2.5">
        <AvatarTicker ticker={it.ticker_base} className="border-app-border text-app-text" />
        <div className="min-w-0 flex-1">
          <div className="text-caption font-bold text-app-text">{it.ticker} <span className="font-normal text-app-text-dim">{it.nombre}</span></div>
          <div className="text-label text-app-text-faint truncate">{[it.tipo, it.sector, it.region].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-strong font-bold font-mono tabular-nums text-app-text">{it.orden != null ? num(it.orden) : '—'}</div>
          <div className="text-label text-app-text-faint">{it.incompleto ? 'incompleto' : 'orden'}</div>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        {it.dimensiones.map(d => <BarraDimension key={d.clave} compacta d={{ ...d, clave: d.clave as never, estado: d.estado as never }} />)}
      </div>
      {it.banderas.length > 0 && <p className="text-label text-app-warn">⚠ {it.banderas[0]}{it.banderas.length > 1 ? ` (+${it.banderas.length - 1})` : ''}</p>}
    </button>
  )
}

function Recientes() {
  const navigate = useNavigate()
  const q = useQuery({ queryKey: qk.de('decisiones'), queryFn: () => getDecisiones() })
  const lista = (q.data ?? []).slice(0, 5)
  if (!lista.length) return null
  return (
    <Card>
      <div className="text-strong font-bold text-app-text mb-2">Decisiones recientes</div>
      <div className="flex flex-col divide-y divide-app-border">
        {lista.map(d => <FilaDecision key={d.id} d={d} onAbrir={() => navigate(`/decisiones/${d.id}`)} />)}
      </div>
    </Card>
  )
}

function MiCartera({ onAbrir }: { onAbrir: (ticker: string) => void }) {
  const { rendimientoPorTicker, carteraSeleccionada } = useInversionesContext()
  const total = rendimientoPorTicker.reduce((s, r) => s + (r.valor_actual_usd || 0), 0)
  const filas = [...rendimientoPorTicker].filter(r => r.cantidad_actual > 0).sort((a, b) => b.valor_actual_usd - a.valor_actual_usd)
  if (!filas.length) {
    return <EmptyState ilustracion="planta" title="No hay posiciones abiertas" description="Cuando tengas tenencias vas a poder evaluar acá mantener, aumentar, reducir o salir." />
  }
  return (
    <Card>
      <div className="text-strong font-bold text-app-text flex items-center gap-1 mb-1">
        Evaluar una posición <InfoTooltip term="decisiones_posicion" label="" />
      </div>
      <p className="text-label text-app-text-dim mb-2">{carteraSeleccionada ? `Cartera ${carteraSeleccionada}` : 'Consolidado'}. Elegí una posición para ver sus cuatro opciones.</p>
      <div className="flex flex-col divide-y divide-app-border">
        {filas.map(r => (
          <button key={r.ticker} type="button" onClick={() => onAbrir(r.ticker)} className="flex items-center gap-2.5 py-2 text-left">
            <AvatarTicker ticker={r.ticker} className="border-app-border text-app-text" />
            <div className="min-w-0 flex-1">
              <div className="text-caption font-bold text-app-text">{r.ticker}</div>
              <div className="text-label text-app-text-faint truncate">{r.nombre}</div>
            </div>
            <span className="text-caption font-mono tabular-nums text-app-text-dim">{total > 0 ? `${num((r.valor_actual_usd / total) * 100, 1)} %` : '—'}</span>
            <span className="text-app-accent text-caption font-bold">Evaluar</span>
          </button>
        ))}
      </div>
    </Card>
  )
}

function Historial({ onAbrir }: { onAbrir: (id: number) => void }) {
  const pendientes = useQuery({ queryKey: qk.de('decisiones-pendientes'), queryFn: getDecisionesPendientes })
  const todas = useQuery({ queryKey: qk.de('decisiones'), queryFn: () => getDecisiones() })
  const aprendizaje = useQuery({ queryKey: qk.de('decisiones-aprendizaje'), queryFn: getAprendizajeDecisiones })
  return (
    <>
      {(pendientes.data?.length ?? 0) > 0 && (
        <Card>
          <div className="text-strong font-bold text-app-warn mb-2">Para revisar</div>
          <div className="flex flex-col divide-y divide-app-border">
            {pendientes.data!.map(d => <FilaDecision key={d.id} d={d} onAbrir={() => onAbrir(d.id)} motivo={d.motivos[0]} />)}
          </div>
        </Card>
      )}
      <QueryBoundary isLoading={todas.isLoading} error={todas.error} onRetry={() => void todas.refetch()} fallback={<SkeletonFilas filas={4} />}>
        {todas.data && todas.data.length === 0 ? (
          <EmptyState ilustracion="planta" title="Todavía no guardaste decisiones"
                      description="Desde el análisis de un activo o de una posición, «Guardar decisión» la deja acá con lo que la app concluía ese día." />
        ) : (
          <Card>
            <div className="text-strong font-bold text-app-text flex items-center gap-1 mb-2">Diario de decisiones <InfoTooltip term="decisiones_diario" label="" /></div>
            <div className="flex flex-col divide-y divide-app-border">
              {(todas.data ?? []).map(d => <FilaDecision key={d.id} d={d} onAbrir={() => onAbrir(d.id)} />)}
            </div>
          </Card>
        )}
      </QueryBoundary>
      {aprendizaje.data && (
        <Card>
          <div className="text-strong font-bold text-app-text flex items-center gap-1 mb-1">Aprendizaje <InfoTooltip term="decisiones_aprendizaje" label="" /></div>
          <p className="text-label text-app-text-dim mb-2">{aprendizaje.data.salvedad}</p>
          <Patrones items={aprendizaje.data.patrones} />
          {aprendizaje.data.operaciones.length > 0 && (
            <>
              <div className="text-label font-bold uppercase text-app-text-faint mt-3 mb-1">Tus operaciones reales</div>
              <Patrones items={aprendizaje.data.operaciones} />
            </>
          )}
        </Card>
      )}
    </>
  )
}

function Patrones({ items }: { items: PatronAprendizaje[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map(p => (
        <li key={p.clave}>
          <div className="text-caption font-semibold text-app-text flex items-center gap-2">
            {p.titulo}
            <span className={`text-label px-1.5 py-0.5 rounded-[6px] ${p.tono === 'insuficiente' ? 'bg-app-surface-2 text-app-text-faint' : p.tono === 'patron_repetido' ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-dim'}`}>
              {p.tono === 'insuficiente' ? 'pocos casos' : p.tono === 'patron_repetido' ? 'se repite' : 'descriptivo'}
            </span>
          </div>
          <p className={`text-caption ${p.tono === 'insuficiente' ? 'text-app-text-faint' : 'text-app-text-dim'}`}>{p.texto}</p>
        </li>
      ))}
    </ul>
  )
}

export function FilaDecision({ d, onAbrir, motivo }: { d: DecisionGuardada; onAbrir: () => void; motivo?: string }) {
  return (
    <button type="button" onClick={onAbrir} className="flex items-start gap-2.5 py-2 text-left">
      <AvatarTicker ticker={d.ticker_base ?? d.ticker} className="border-app-border text-app-text" />
      <div className="min-w-0 flex-1">
        <div className="text-caption font-bold text-app-text flex items-center gap-2 flex-wrap">
          {d.ticker}
          <span className="font-normal text-app-text-dim">{TEXTO_ACCION[d.accion_elegida] ?? d.accion_elegida}</span>
          {d.ejecutada && <span className="text-label text-app-pos">ejecutada</span>}
          {d.estado === 'cerrada' && <span className="text-label text-app-text-faint">cerrada</span>}
        </div>
        <div className="mt-1"><ConclusionBadge tipo={d.conclusion.tipo} titulo={d.conclusion.titulo} /></div>
        <div className="text-label text-app-text-faint mt-1">
          {d.creada_en.slice(0, 10)}{d.revisar_el ? ` · revisar el ${d.revisar_el}` : ''}{d.n_revisiones ? ` · ${d.n_revisiones} revisión(es)` : ''}
        </div>
        {motivo && <div className="text-label text-app-warn mt-0.5">{motivo}</div>}
      </div>
      <span className="text-caption font-bold text-app-accent shrink-0">Abrir</span>
    </button>
  )
}
