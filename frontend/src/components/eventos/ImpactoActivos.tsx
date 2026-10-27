import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { isAxiosError } from 'axios'
import {
  getAnalisisEvento, getImpactoEventos, getPatronEventos, getUniversoImpacto, prepararTecnicoDecision,
  type BenchmarkEventos, type CategoriaEvento, type MarcaEvento,
} from '../../api'
import { qk } from '../../api/queryClient'
import InfoTooltip from '../../help/components/InfoTooltip'
import { usePreferencia } from '../../hooks/usePreferencia'
import { fechaCorta } from '../../utils/fechas'
import { COLOR_CATEGORIA, ETIQUETA_CATEGORIA, pct, tonoPct } from '../../utils/eventos'
import Button from '../ui/Button'
import EmptyState from '../ui/EmptyState'
import QueryBoundary from '../ui/QueryBoundary'
import Segmented from '../ui/Segmented'
import { SkeletonCard } from '../ui/Skeleton'
import AnalisisEvento from './AnalisisEvento'
import GraficoEventos from './GraficoEventos'

type Rango = '6m' | '1a' | '3a' | '5a' | 'todo'
const RANGOS: { value: Rango; label: string }[] = [
  { value: '6m', label: '6M' }, { value: '1a', label: '1A' }, { value: '3a', label: '3A' }, { value: '5a', label: '5A' }, { value: 'todo', label: 'Todo' },
]
const BENCHMARKS: { value: BenchmarkEventos; label: string }[] = [
  { value: 'auto', label: 'Índice natural' }, { value: 'SPY', label: 'S&P 500' }, { value: '^MERV', label: 'Merval' }, { value: 'ninguno', label: 'Sin índice' },
]
const IMPORTANCIAS = [{ value: '1', label: 'Todas' }, { value: '2', label: 'Media+' }, { value: '3', label: 'Alta' }]

const parseRango = (s: string): Rango | null => (RANGOS.some(r => r.value === s) ? (s as Rango) : null)
const id = (s: string) => s

function desdeDe(r: Rango): string | undefined {
  const meses = { '6m': 6, '1a': 12, '3a': 36, '5a': 60, todo: 0 }[r]
  return meses ? dayjs().subtract(meses, 'month').format('YYYY-MM-DD') : undefined
}

function PatronCategoria({ ticker, categoria }: { ticker: string; categoria: CategoriaEvento }) {
  const q = useQuery({ queryKey: qk.de('eventos', 'patron', ticker, categoria), queryFn: () => getPatronEventos(ticker, categoria, 5) })
  const d = q.data
  return (
    <div className="rounded-xl border border-app-border p-2.5">
      <div className="mb-1 flex items-center gap-1 text-caption font-semibold text-app-text">
        {ticker} en {ETIQUETA_CATEGORIA[categoria].toLowerCase()} (5 ruedas después) <InfoTooltip term="eventos_patron" label="" />
      </div>
      <QueryBoundary isLoading={q.isLoading} error={q.error} onRetry={() => void q.refetch()} fallback={<SkeletonCard lineas={2} />}>
        {d && (
          <div className="flex flex-col gap-1 text-caption">
            {d.suficiente ? (
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-app-surface-2 p-2">
                  <div className="text-label text-app-text-faint">Mediana tras {d.casos_validos} eventos</div>
                  <div className={`font-mono tabular-nums text-strong ${tonoPct(d.mediana_posterior_pct)}`}>{pct(d.mediana_posterior_pct)}</div>
                  <div className="text-label text-app-text-faint">subió en {d.positivos_pct?.toFixed(0)} % de los casos</div>
                </div>
                <div className="rounded-lg bg-app-surface-2 p-2">
                  <div className="text-label text-app-text-faint">En cualquier tramo de 5 ruedas</div>
                  <div className={`font-mono tabular-nums text-strong ${tonoPct(d.mediana_base_pct)}`}>{pct(d.mediana_base_pct)}</div>
                  <div className="text-label text-app-text-faint">subió en {d.positivos_base_pct?.toFixed(0)} % de los casos</div>
                </div>
              </div>
            ) : (
              <p className="text-app-text-dim">
                {d.casos_validos} caso{d.casos_validos === 1 ? '' : 's'} con datos: hacen falta al menos {d.minimo} para resumir sin que sea anécdota.
              </p>
            )}
            {d.casos.length > 0 && (
              <ul className="mt-1 flex flex-col divide-y divide-app-border-soft">
                {d.casos.slice(-8).reverse().map(c => (
                  <li key={c.evento_id} className="flex items-center justify-between gap-2 py-1">
                    <span className="truncate text-app-text-dim">{fechaCorta(c.fecha_evento)} · {c.titulo}</span>
                    <span className={`font-mono tabular-nums shrink-0 ${tonoPct(c.posterior_pct)}`}>{pct(c.posterior_pct)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}

/**
 * Un ticker con sus eventos sobre el gráfico. Cambiar de ticker conserva el rango y los filtros. Al
 * tocar una marca se ve, debajo, lo que hizo el precio alrededor de ese evento; la ficha completa
 * abre en un modal sin perder el gráfico.
 */
export default function ImpactoActivos({ ticker, onTicker, onAbrir }: { ticker: string | null; onTicker: (t: string) => void; onAbrir: (id: number) => void }) {
  const qc = useQueryClient()
  const [rango, setRango] = usePreferencia<Rango>('inversiones-eventos-rango', '3a', parseRango, id)
  const [benchmark, setBenchmark] = useState<BenchmarkEventos>('auto')
  const [importancia, setImportancia] = useState('1')
  const [ocultas, setOcultas] = useState<CategoriaEvento[]>([])
  const [grupo, setGrupo] = useState<MarcaEvento[] | null>(null)
  const [elegido, setElegido] = useState<MarcaEvento | null>(null)

  const universo = useQuery({ queryKey: qk.de('eventos', 'universo'), queryFn: getUniversoImpacto })
  const activo = ticker ?? universo.data?.[0]?.ticker ?? null
  const impacto = useQuery({
    queryKey: qk.de('eventos', 'impacto', activo, rango, benchmark, importancia),
    queryFn: () => getImpactoEventos(activo!, { desde: desdeDe(rango), benchmark, importancia_min: Number(importancia) > 1 ? Number(importancia) : undefined }),
    enabled: !!activo,
    placeholderData: prev => prev,
  })
  const analisis = useQuery({
    queryKey: qk.de('eventos', 'analisis', elegido?.evento_id, activo, benchmark),
    queryFn: () => getAnalisisEvento(elegido!.evento_id, activo!, benchmark),
    enabled: !!elegido && !!activo && !elegido.futuro,
  })
  const preparar = useMutation({
    mutationFn: () => prepararTecnicoDecision(activo!),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.de('eventos') }),
  })

  const d = impacto.data
  const marcas = useMemo(() => (d?.marcas ?? []).filter(m => !ocultas.includes(m.categoria)), [d, ocultas])
  const presentes = useMemo(() => [...new Set((d?.marcas ?? []).map(m => m.categoria))], [d])
  const futuras = (d?.marcas ?? []).filter(m => m.futuro)
  const sinSerie = isAxiosError(impacto.error) && impacto.error.response?.status === 404

  const elegirTicker = (t: string) => {
    setElegido(null)
    setGrupo(null)
    onTicker(t)
  }
  const elegirMarcas = (ms: MarcaEvento[]) => {
    if (ms.length === 1) { setElegido(ms[0]); setGrupo(null) } else { setGrupo(ms); setElegido(null) }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <select value={activo ?? ''} onChange={e => elegirTicker(e.target.value)} aria-label="Instrumento"
          className="flex-1 min-w-0 h-11 rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text">
          {(universo.data ?? []).map(u => (
            <option key={u.ticker} value={u.ticker}>{u.ticker} · {u.nombre}{u.origen === 'benchmark' ? ' (índice)' : ''}</option>
          ))}
          {activo && universo.data && !universo.data.some(u => u.ticker === activo) && <option value={activo}>{activo}</option>}
        </select>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented options={RANGOS} value={rango} onChange={setRango} />
        <Segmented options={IMPORTANCIAS} value={importancia} onChange={setImportancia} />
      </div>
      <Segmented options={BENCHMARKS} value={benchmark} onChange={setBenchmark} />

      {!activo ? (
        <EmptyState ilustracion="planta" title="Todavía no seguís ningún instrumento" description="Agregá algo a la watchlist o sincronizá la cartera para ver sus eventos sobre el precio." />
      ) : sinSerie ? (
        <EmptyState ilustracion="lupa" title={`${activo} no tiene serie todavía`}
          description="No está en tu cartera ni en la watchlist. Se puede agregar a la watchlist y bajar sus velas."
          action={<Button loading={preparar.isPending} onClick={() => preparar.mutate()}>Agregar y descargar velas</Button>} />
      ) : (
        <QueryBoundary isLoading={impacto.isLoading} error={impacto.error} onRetry={() => void impacto.refetch()} fallback={<SkeletonCard lineas={6} />}>
          {d && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2 text-label text-app-text-faint">
                <span>{d.nombre} · {d.moneda}{d.variante === 'subyacente' ? ' (acción en EE.UU.)' : ''} · {d.mercado}</span>
                {d.ultima_fecha && <span>Último cierre {fechaCorta(d.ultima_fecha)}</span>}
              </div>
              {d.serie.length < 2 ? (
                <EmptyState ilustracion="lupa" title="Sin cotizaciones en este rango" description="Probá un rango más largo, o esperá al próximo sync." />
              ) : (
                <div className="rounded-2xl border border-app-border bg-app-surface p-2">
                  <GraficoEventos serie={d.serie} benchmark={d.benchmark} marcas={marcas} onElegir={elegirMarcas} elegido={elegido?.evento_id ?? null} />
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-label text-app-text-faint">
                    <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 bg-app-accent" /> {d.ticker}</span>
                    {d.benchmark && <span className="flex items-center gap-1"><span className="inline-block h-0 w-4 border-t border-dashed border-slate-400" /> {d.benchmark.nombre} (normalizado)</span>}
                    <span>● pasado · ○ futuro · número = varios juntos</span>
                  </div>
                </div>
              )}
              {presentes.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {presentes.map(c => {
                    const visible = !ocultas.includes(c)
                    return (
                      <button key={c} aria-pressed={visible}
                        onClick={() => setOcultas(visible ? [...ocultas, c] : ocultas.filter(x => x !== c))}
                        className={`inline-flex items-center gap-1.5 rounded-[9px] border px-2 py-1 text-label font-bold transition-opacity ${visible ? 'border-app-border text-app-text-dim' : 'border-transparent text-app-text-faint opacity-50'}`}>
                        <span className="w-2 h-2 rounded-full" style={{ background: COLOR_CATEGORIA[c] }} />
                        {ETIQUETA_CATEGORIA[c]}
                      </button>
                    )
                  })}
                </div>
              )}
              {d.marcas.length === 0 && <p className="text-caption text-app-text-dim">No hay eventos vinculados a {d.ticker} en este rango (ni generales de importancia alta).</p>}
              {futuras.length > 0 && (
                <p className="text-label text-app-text-faint">
                  {futuras.length} evento{futuras.length === 1 ? '' : 's'} por venir: la línea de precio termina en el último cierre; a la derecha sólo hay fechas.
                </p>
              )}
              {d.advertencias.includes('posible_split') && (
                <p className="text-label text-app-warn">La serie local no está ajustada y tiene un salto que parece un split: los retornos que lo crucen no son reales.</p>
              )}

              {grupo && (
                <div className="rounded-xl border border-app-border p-2.5">
                  <div className="mb-1 text-caption font-semibold text-app-text">{grupo.length} eventos juntos</div>
                  <ul className="flex flex-col divide-y divide-app-border-soft">
                    {grupo.map(m => (
                      <li key={m.evento_id}>
                        <button onClick={() => { setElegido(m); setGrupo(null) }} className="flex w-full items-center gap-2 py-1.5 text-left text-caption text-app-text">
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: COLOR_CATEGORIA[m.categoria] }} />
                          <span className="font-mono text-label text-app-text-faint shrink-0">{fechaCorta(m.fecha_evento)}</span>
                          <span className="truncate">{m.titulo}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {elegido && (
                <div className="rounded-xl border border-app-border p-2.5 flex flex-col gap-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-label text-app-text-faint">
                        {fechaCorta(elegido.fecha_evento)}{elegido.precision_fecha !== 'exacta' ? ' (estimada)' : ''} · {ETIQUETA_CATEGORIA[elegido.categoria]}
                        {elegido.relacion !== 'general' ? ` · relación ${elegido.relacion}` : ' · evento general'}
                      </div>
                      <div className="text-body font-semibold text-app-text">{elegido.titulo}</div>
                    </div>
                    <Button variant="ghost" className="h-9 shrink-0" onClick={() => onAbrir(elegido.evento_id)}>Ficha</Button>
                  </div>
                  {elegido.futuro ? (
                    <p className="text-caption text-app-text-dim">Todavía no ocurrió: no hay precios después para medir.</p>
                  ) : (
                    <QueryBoundary isLoading={analisis.isLoading} error={analisis.error} onRetry={() => void analisis.refetch()} fallback={<SkeletonCard lineas={4} />}>
                      {analisis.data && <AnalisisEvento analisis={analisis.data} />}
                    </QueryBoundary>
                  )}
                </div>
              )}
              {elegido && <PatronCategoria ticker={d.ticker} categoria={elegido.categoria} />}
            </div>
          )}
        </QueryBoundary>
      )}
    </div>
  )
}
