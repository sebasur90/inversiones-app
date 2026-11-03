import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getCicloDetalle, getCiclosCatalogo, getCiclosInstrumentos, type CicloMoneda } from '../api'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import Segmented from '../components/ui/Segmented'
import TituloSeccion from '../components/ui/TituloSeccion'
import BadgeCuadrante from '../components/ciclos/BadgeCuadrante'
import EfectividadEstados from '../components/ciclos/EfectividadEstados'
import GraficoBase100 from '../components/ciclos/GraficoBase100'
import HistorialRotacion from '../components/ciclos/HistorialRotacion'
import InstrumentosGrupo from '../components/ciclos/InstrumentosGrupo'
import MetricasGrupo from '../components/ciclos/MetricasGrupo'
import PieDatos from '../components/ciclos/PieDatos'
import SelectorGrupos from '../components/ciclos/SelectorGrupos'
import { ETIQUETA_TIPO, fmtPct, tonoDe } from '../components/ciclos/constantes'
import InfoTooltip from '../help/components/InfoTooltip'
import { fechaCorta } from '../utils/fechas'

type Horizonte = '1A' | '3A' | '5A' | '10A' | 'max' | 'periodo' | 'fechas'

const OPCIONES: { value: Horizonte; label: string }[] = [
  { value: '1A', label: '1A' },
  { value: '3A', label: '3A' },
  { value: '5A', label: '5A' },
  { value: '10A', label: '10A' },
  { value: 'max', label: 'Todo' },
  { value: 'periodo', label: 'Período' },
  { value: 'fechas', label: 'Fechas' },
]

/** Ficha de un grupo: rendimiento normalizado contra la referencia, fortaleza relativa, historial de rotación y sus instrumentos en tu cartera. */
export default function CicloDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()
  const moneda: CicloMoneda = monedaSeleccionada
  const [horizonte, setHorizonte] = useState<Horizonte>('3A')
  const [benchmark, setBenchmark] = useState<string | null>(null)
  const [extras, setExtras] = useState<string[]>([])
  const [periodoId, setPeriodoId] = useState<string>('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')

  const catalogo = useQuery({ queryKey: qk.de('ciclos-catalogo'), queryFn: getCiclosCatalogo })

  const usaPeriodo = horizonte === 'periodo' && periodoId !== ''
  const usaFechas = horizonte === 'fechas' && desde !== '' && hasta !== '' && desde < hasta
  const query = useQuery({
    queryKey: qk.de('ciclos-detalle', id, moneda, benchmark, horizonte, periodoId, desde, hasta, extras.join(',')),
    queryFn: () =>
      getCicloDetalle(id, {
        benchmark,
        moneda,
        horizonte: horizonte === 'periodo' || horizonte === 'fechas' ? undefined : horizonte,
        periodo_id: usaPeriodo ? periodoId : undefined,
        desde: usaFechas ? desde : undefined,
        hasta: usaFechas ? hasta : undefined,
        con: extras,
      }),
    enabled: id !== '' && (horizonte !== 'periodo' || usaPeriodo) && (horizonte !== 'fechas' || usaFechas),
  })
  const d = query.data

  const instrumentos = useQuery({
    queryKey: qk.de('ciclos-instrumentos', carteraSeleccionada, id, benchmark),
    queryFn: () => getCiclosInstrumentos(carteraSeleccionada, id, benchmark),
    enabled: id !== '',
  })

  const grupos = catalogo.data?.grupos ?? []
  const benchmarks = useMemo(() => grupos.filter(g => g.activo && g.es_benchmark && g.id !== id), [grupos, id])
  const rot = d?.rotacion ?? null

  return (
    <div className="pb-4">
      <ScreenHeader title={d?.grupo.nombre ?? 'Ciclo de mercado'} onBack={() => navigate(-1)} />

      <div className="flex flex-col gap-2 mb-4">
        <Segmented options={OPCIONES} value={horizonte} onChange={setHorizonte} />
        {horizonte === 'periodo' && (
          <select
            aria-label="Período histórico"
            value={periodoId}
            onChange={e => setPeriodoId(e.target.value)}
            className="h-11 w-full rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text"
          >
            <option value="">Elegí un período histórico…</option>
            {(d?.periodos ?? []).map(p => (
              <option key={p.id} value={p.id}>
                {p.nombre} ({fechaCorta(p.desde)} → {p.hasta ? fechaCorta(p.hasta) : 'hoy'})
              </option>
            ))}
          </select>
        )}
        {horizonte === 'fechas' && (
          <div className="grid grid-cols-2 gap-2">
            <input type="date" aria-label="Desde" value={desde} onChange={e => setDesde(e.target.value)} className="h-11 rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text" />
            <input type="date" aria-label="Hasta" value={hasta} onChange={e => setHasta(e.target.value)} className="h-11 rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text" />
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {benchmarks.map(b => (
            <button
              key={b.id}
              type="button"
              onClick={() => setBenchmark(benchmark === b.id ? null : b.id)}
              className={`px-2.5 py-1.5 rounded-lg text-caption font-semibold whitespace-nowrap active:scale-95 ${
                (benchmark ?? d?.benchmark?.id) === b.id ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface border border-app-border text-app-text-dim'
              }`}
            >
              vs. {b.nombre}
            </button>
          ))}
        </div>
        <details className="rounded-xl border border-app-border bg-app-surface px-3 py-2">
          <summary className="text-caption font-semibold text-app-text-dim cursor-pointer">Comparar con otros grupos ({extras.length})</summary>
          <div className="pt-2">
            <SelectorGrupos grupos={grupos.filter(g => g.id !== id)} seleccion={extras} onChange={setExtras} max={5} />
          </div>
        </details>
      </div>

      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {!d || d.estado === 'sin_datos' ? (
          <EmptyState
            ilustracion="lupa"
            emoji="🔭"
            title="Sin datos de este grupo"
            description={d?.motivo ?? 'Todavía no se descargó la serie. Las series se bajan solas después del cierre; también podés pedirlo desde el panorama.'}
          />
        ) : (
          <div className="flex flex-col gap-5">
            <Card>
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <BadgeCuadrante cuadrante={rot?.actual?.cuadrante} pendiente={!!rot?.pendiente && rot.pendiente.cuadrante === rot.actual?.cuadrante} />
                <span className="text-label font-bold uppercase text-app-text-faint">{ETIQUETA_TIPO[d.grupo.tipo]}</span>
                {d.grupo.padre && <span className="text-label text-app-text-faint">dentro de {grupos.find(g => g.id === d.grupo.padre)?.nombre ?? d.grupo.padre}</span>}
              </div>
              <p className="text-caption text-app-text-dim">{d.grupo.descripcion}</p>
              <p className="text-label text-app-text-faint mt-1">
                Medido con {d.grupo.proxy ?? 'su serie'} <InfoTooltip term="ciclos_proxy" /> · contra {d.benchmark?.nombre ?? 'sin referencia'} <InfoTooltip term="ciclos_benchmark" />
                {d.grupo.nota ? ` · ${d.grupo.nota}` : ''}
              </p>
              {rot && rot.estado !== 'ok' && <p className="text-caption text-app-warn mt-1">{rot.motivo}</p>}
              {d.grupo.hijos.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {d.grupo.hijos.map(h => (
                    <button key={h.id} type="button" onClick={() => navigate(`/ciclos/grupo/${h.id}`)} className="px-2 py-1 rounded-lg bg-app-surface-2 border border-app-border text-label font-semibold text-app-text-dim active:scale-95">
                      {h.nombre} ›
                    </button>
                  ))}
                </div>
              )}
            </Card>

            <section>
              <TituloSeccion icono="trend">Fortaleza relativa y riesgo</TituloSeccion>
              <MetricasGrupo rrg={rot} rendimientos={d.rendimientos} riesgo={d.riesgo} tendencia={d.tendencia} />
            </section>

            <section>
              <TituloSeccion icono="trend" tono="cyan">
                Rendimiento acumulado (base 100)
              </TituloSeccion>
              <Card>
                {d.filas.length === 0 ? (
                  <p className="text-caption text-app-text-dim">No hay fechas en común entre las series elegidas en este rango.</p>
                ) : (
                  <>
                    <GraficoBase100 filas={d.filas} series={d.series} />
                    {d.rango && (
                      <p className="text-label text-app-text-faint mt-1">
                        {d.rango.etiqueta}: del {fechaCorta(d.rango.desde_efectivo)} al {fechaCorta(d.rango.hasta_efectivo)}
                        {d.rango.paso === 'S' ? ' · puntos semanales' : ''}. Todas las series arrancan en 100 en la primera fecha en la que todas tienen datos.
                      </p>
                    )}
                  </>
                )}
              </Card>
              {d.benchmark && d.filas.length > 0 && (
                <Card className="mt-3">
                  <div className="text-label font-bold uppercase text-app-text-faint mb-1">Cociente grupo ÷ referencia (base 100)</div>
                  <GraficoBase100 filas={d.filas} series={[{ id: 'relativo', nombre: `${d.grupo.nombre} ÷ ${d.benchmark.nombre}`, rol: 'grupo' }]} alto={170} />
                  <p className="text-label text-app-text-faint">Sube cuando el grupo le gana a la referencia, sin importar si los dos suben o bajan.</p>
                </Card>
              )}
            </section>

            {d.periodo_analizado && (
              <section>
                <TituloSeccion icono="calendar" tono="violet">
                  Período analizado
                </TituloSeccion>
                <Card>
                  <p className="text-caption text-app-text-dim mb-2">
                    Del <b className="text-app-text">{fechaCorta(d.periodo_analizado.desde)}</b> al <b className="text-app-text">{fechaCorta(d.periodo_analizado.hasta)}</b>
                    {d.periodo_analizado.periodo_ajustado ? ' (acortado a la historia común de todas las series)' : ''}.
                  </p>
                  <ul className="flex flex-col gap-2">
                    {d.series.map(s => {
                      const g = d.periodo_analizado?.grupos[s.id]
                      if (!g) return null
                      return (
                        <li key={s.id} className="rounded-lg border border-app-border px-2.5 py-2">
                          <div className="text-caption font-semibold text-app-text">{s.nombre}</div>
                          {g.retorno == null ? (
                            <div className="text-label text-app-text-faint">Sin datos suficientes en este período.</div>
                          ) : (
                            <div className="grid grid-cols-4 gap-2 mt-1 text-label">
                              {[
                                ['Rend.', fmtPct(g.retorno), tonoDe(g.retorno)],
                                ['vs. ref.', fmtPct(g.relativo), tonoDe(g.relativo)],
                                ['Volat.', fmtPct(g.volatilidad?.anualizada, 1, false), undefined],
                                ['Caída', fmtPct(g.drawdown?.maximo, 1, false), g.drawdown?.maximo ? ('neg' as const) : undefined],
                              ].map(([k, v, t]) => (
                                <div key={String(k)}>
                                  <div className="text-app-text-faint">{k}</div>
                                  <div className={`font-mono tabular-nums font-bold ${t === 'pos' ? 'text-app-pos' : t === 'neg' ? 'text-app-neg' : 'text-app-text'}`}>{v}</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                  <p className="text-label text-app-text-faint mt-2">Describe lo observado en esas fechas exactas; no implica que se repita ni explica sus causas.</p>
                </Card>
              </section>
            )}

            {rot && rot.puntos.length > 0 && (
              <section>
                <TituloSeccion icono="swap" tono="warn">
                  Historial de rotación
                </TituloSeccion>
                <Card>
                  <HistorialRotacion puntos={rot.puntos} transiciones={rot.transiciones} />
                </Card>
              </section>
            )}

            {rot && d.benchmark && (
              <section>
                <TituloSeccion icono="trend" tono="violet">
                  Qué pasó después de cada estado
                </TituloSeccion>
                <Card>
                  <EfectividadEstados grupoId={d.grupo.id} tipo={d.grupo.tipo} benchmark={benchmark} />
                </Card>
              </section>
            )}

            <section>
              <TituloSeccion icono="wallet" tono="pos">
                En tu cartera
              </TituloSeccion>
              <Card>
                <QueryBoundary isLoading={instrumentos.isLoading} error={instrumentos.error} onRetry={() => void instrumentos.refetch()} fallback={<p className="text-caption text-app-text-dim">Cargando…</p>}>
                  {instrumentos.data && <InstrumentosGrupo data={instrumentos.data} />}
                </QueryBoundary>
              </Card>
            </section>

            <PieDatos meta={d.meta} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
