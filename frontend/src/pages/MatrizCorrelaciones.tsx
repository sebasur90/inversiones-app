import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import {
  getMatrizCorrelaciones,
  getTickersConPrecios,
  type FrecuenciaCorrelacion,
  type MatrizCorrelacionParItem,
  type TickerConPrecio,
} from '../api'
import { calcularDesde, type PeriodoEvolucion } from '../utils'
import { qk } from '../api/queryClient'
import { nivelCorrelacion } from '../utils/niveles'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import MetricTile from '../components/ui/MetricTile'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import Chip from '../components/ui/Chip'
import TablaOrdenable, { type ColumnaOrdenable } from '../components/ui/TablaOrdenable'
import MatrizCorrelacionHeatmap, { type CeldaSeleccionada } from '../components/charts/MatrizCorrelacionHeatmap'
import DetalleParCorrelacion from '../components/charts/DetalleParCorrelacion'
import InfoTooltip from '../help/components/InfoTooltip'
import { Icon } from '../components/icons/Icons'

type Periodo = Exclude<PeriodoEvolucion, '1M'>

const OPCIONES_PERIODO: { value: Periodo; label: string }[] = [
  { value: '3M', label: '3M' },
  { value: '6M', label: '6M' },
  { value: '1Y', label: '1A' },
  { value: '3Y', label: '3A' },
  { value: 'YTD', label: 'YTD' },
  { value: 'ALL', label: 'Todo' },
]

const OPCIONES_FRECUENCIA: { value: FrecuenciaCorrelacion; label: string }[] = [
  { value: 'diaria', label: 'Diaria' },
  { value: 'semanal', label: 'Semanal' },
  { value: 'mensual', label: 'Mensual' },
]

const MAX_TICKERS = 12

const MOTIVO_DESCARTE_TEXTO: Record<string, string> = {
  sin_precios: 'sin precios cargados',
  tope_tickers: `por encima del máximo de ${MAX_TICKERS}`,
}

function fmtFecha(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso + 'T00:00:00').toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtPar(p: MatrizCorrelacionParItem): string {
  return `${p.ticker_a} / ${p.ticker_b}`
}

export default function MatrizCorrelaciones() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()

  const [periodo, setPeriodo] = useState<Periodo>('1Y')
  const [frecuencia, setFrecuencia] = useState<FrecuenciaCorrelacion>('mensual')
  const [tickersSel, setTickersSel] = useState<string[] | null>(null)
  const [buscarTicker, setBuscarTicker] = useState('')
  const [explicacionAbierta, setExplicacionAbierta] = useState(true)
  const [seleccion, setSeleccion] = useState<CeldaSeleccionada | null>(null)

  // Cambiar de cartera vuelve a arrancar desde las tenencias de la cartera nueva.
  useEffect(() => {
    setTickersSel(null)
    setSeleccion(null)
  }, [carteraSeleccionada])

  const desde = calcularDesde(periodo)
  const tickersQuery = useQuery({
    queryKey: qk.de('tickers-con-precios'),
    queryFn: () => getTickersConPrecios(),
  })
  const tickersDisponibles: TickerConPrecio[] = tickersQuery.data ?? []

  const sinInstrumentos = tickersSel !== null && tickersSel.length === 0

  const query = useQuery({
    queryKey: qk.de('matriz-correlaciones', carteraSeleccionada, frecuencia, desde ?? 'all', tickersSel ?? []),
    queryFn: () => getMatrizCorrelaciones(carteraSeleccionada, { tickers: tickersSel ?? [], frecuencia, desde }),
    enabled: !sinInstrumentos,
  })
  const data = query.data ?? null

  // Primer resultado con tickersSel aún no elegido explícitamente: hidrata los chips con lo
  // que decidió el backend (las tenencias de la cartera), para que queden editables.
  useEffect(() => {
    if (tickersSel === null && data && data.tickers.length > 0) {
      setTickersSel(data.tickers)
    }
  }, [data, tickersSel])

  useEffect(() => {
    setSeleccion(null)
  }, [data?.tickers.join(',')])

  const opcionesAgregar = useMemo(
    () =>
      tickersDisponibles.filter(
        t => !(tickersSel ?? []).includes(t.ticker) && t.ticker.toLowerCase().includes(buscarTicker.toLowerCase())
      ),
    [tickersDisponibles, tickersSel, buscarTicker]
  )

  function quitarTicker(ticker: string) {
    setTickersSel(prev => (prev ?? []).filter(t => t !== ticker))
  }

  function agregarTicker(ticker: string) {
    setTickersSel(prev => {
      const base = prev ?? []
      if (base.includes(ticker) || base.length >= MAX_TICKERS) return base
      return [...base, ticker]
    })
    setBuscarTicker('')
  }

  const columnasPares: ColumnaOrdenable<MatrizCorrelacionParItem>[] = [
    { key: 'par', label: 'Par', align: 'left', valor: fmtPar },
    {
      key: 'valor',
      label: 'Correlación',
      valor: p => p.valor,
      render: p => (p.valor == null ? '—' : p.valor.toFixed(2)),
    },
    { key: 'n_obs', label: 'Obs.', valor: p => p.n_obs },
    {
      key: 'solapamiento_pct',
      label: 'Solapam.',
      valor: p => p.solapamiento_pct,
      render: p => (p.solapamiento_pct == null ? '—' : `${p.solapamiento_pct.toFixed(0)}%`),
    },
  ]

  const nivelDiv = data?.estado === 'ok' ? nivelCorrelacion(data.correlacion_promedio) : null
  const tickerA = seleccion && data ? data.tickers[seleccion.i] : null
  const tickerB = seleccion && data ? data.tickers[seleccion.j] : null
  const parSeleccionado =
    tickerA && tickerB ? data?.pares.find(p => (p.ticker_a === tickerA && p.ticker_b === tickerB) || (p.ticker_a === tickerB && p.ticker_b === tickerA)) : undefined

  return (
    <div className="pb-4">
      <ScreenHeader title="Matriz de correlaciones" onBack={() => navigate(-1)} />

      <div className="flex flex-col gap-2 mb-4">
        <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
        <Segmented options={OPCIONES_FRECUENCIA} value={frecuencia} onChange={setFrecuencia} />
      </div>

      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <div className="text-label font-bold uppercase text-app-text-faint">Instrumentos</div>
          {tickersSel !== null && (
            <button onClick={() => setTickersSel(null)} className="text-label font-semibold text-app-accent">
              Volver a mis tenencias
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {(tickersSel ?? []).map(t => (
            <Chip key={t} onRemove={() => quitarTicker(t)}>{t}</Chip>
          ))}
          {(tickersSel ?? []).length === 0 && (
            <span className="text-caption text-app-text-faint">Sin instrumentos seleccionados.</span>
          )}
        </div>
        {(tickersSel ?? []).length < MAX_TICKERS && (
          <>
            <input
              value={buscarTicker}
              onChange={e => setBuscarTicker(e.target.value)}
              placeholder="Buscar instrumento para agregar…"
              className="w-full bg-app-surface border border-app-border rounded-[10px] px-3 py-2 text-caption text-app-text mb-2"
            />
            <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 -mx-4 px-4">
              {opcionesAgregar.slice(0, 20).map(t => (
                <button
                  key={t.ticker}
                  onClick={() => agregarTicker(t.ticker)}
                  className="shrink-0 font-semibold text-caption px-3 py-1.5 rounded-[10px] border border-app-border bg-app-surface text-app-text-dim"
                >
                  {t.ticker}
                </button>
              ))}
            </div>
          </>
        )}
        {(tickersSel ?? []).length >= MAX_TICKERS && (
          <div className="text-label text-app-text-faint">Máximo {MAX_TICKERS} instrumentos.</div>
        )}
        {data && data.tickers_descartados.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {data.tickers_descartados.map(d => (
              <span
                key={d.ticker}
                title={MOTIVO_DESCARTE_TEXTO[d.motivo] ?? d.motivo}
                className="text-label text-app-text-faint bg-app-surface border border-app-border rounded-[9px] px-2 py-1"
              >
                {d.ticker} ({MOTIVO_DESCARTE_TEXTO[d.motivo] ?? d.motivo})
              </span>
            ))}
          </div>
        )}
      </div>

      {sinInstrumentos ? (
        <EmptyState
          title="Elegí al menos dos instrumentos"
          description="Agregá instrumentos de la lista de arriba, o volvé a tus tenencias."
        />
      ) : (
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {!data || data.estado !== 'ok' ? (
            <EmptyState
              title={
                data?.estado === 'sin_suficientes_tickers'
                  ? 'Hace falta al menos un segundo instrumento'
                  : data?.estado === 'sin_tickers'
                  ? 'No hay instrumentos para calcular'
                  : 'Todavía no hay suficientes datos'
              }
              description="Agregá otro instrumento con precios cargados, o probá un período o una frecuencia más amplia."
            />
          ) : (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-2">
                <MetricTile
                  label="Correlación promedio"
                  value={data.correlacion_promedio == null ? '—' : data.correlacion_promedio.toFixed(2)}
                  infoTerm="matrizcorr_diversificacion"
                  nivel={nivelDiv}
                />
                <MetricTile label="Pares calculados" value={`${data.n_pares_ok}/${data.n_pares}`} />
                <MetricTile
                  label="Período cubierto"
                  value={data.periodo_desde ? fmtFecha(data.periodo_desde) : '—'}
                  sub={data.periodo_hasta ? `hasta ${fmtFecha(data.periodo_hasta)}` : undefined}
                />
              </div>

              <Card>
                <button
                  onClick={() => setExplicacionAbierta(v => !v)}
                  className="w-full flex items-center justify-between"
                >
                  <span className="font-semibold text-app-text">Cómo leer la matriz</span>
                  <Icon
                    name="chevron"
                    className={`w-4 h-4 text-app-text-faint transition-transform ${explicacionAbierta ? 'rotate-180' : ''}`}
                  />
                </button>
                {explicacionAbierta && (
                  <div className="mt-3 flex flex-col gap-3">
                    <div>
                      <div
                        className="h-2 rounded-full mb-1"
                        style={{ background: 'linear-gradient(to right, rgba(239,68,68,0.45), rgba(148,163,184,0.15), rgba(16,185,129,0.45))' }}
                      />
                      <div className="flex justify-between text-label text-app-text-faint">
                        <span>−1</span>
                        <span>0</span>
                        <span>+1</span>
                      </div>
                    </div>
                    <ul className="text-body text-app-text-dim space-y-1 list-disc pl-4">
                      <li><strong className="text-app-text">+1</strong>: se movieron de manera muy similar.</li>
                      <li><strong className="text-app-text">0</strong>: no se observa relación lineal clara.</li>
                      <li><strong className="text-app-text">−1</strong>: se movieron en direcciones opuestas.</li>
                    </ul>
                    <div className="flex items-start gap-2 bg-app-accent-soft rounded-xl px-3 py-2.5">
                      <Icon name="alert" className="w-4 h-4 text-app-accent shrink-0 mt-0.5" />
                      <span className="text-caption text-app-text">
                        Correlación no es causalidad: dos instrumentos pueden moverse juntos por un factor común,
                        sin que uno influya sobre el otro.
                      </span>
                    </div>
                    <div className="text-label text-app-text-faint">
                      Todo se calcula en USD (MEP). Los precios en pesos se convierten a la fecha de cada punto.{' '}
                      <InfoTooltip term="matrizcorr_moneda" label="" />
                    </div>
                  </div>
                )}
              </Card>

              {data.advertencias.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  {data.advertencias.map((a, i) => (
                    <div key={i} className="flex items-start gap-2 bg-app-accent-soft rounded-xl px-3 py-2.5">
                      <Icon name="alert" className="w-4 h-4 text-app-accent shrink-0 mt-0.5" />
                      <span className="text-caption text-app-text">{a}</span>
                    </div>
                  ))}
                </div>
              )}

              <MatrizCorrelacionHeatmap
                tickers={data.tickers}
                matriz={data.matriz}
                pares={data.pares}
                seleccion={seleccion}
                onSeleccionar={setSeleccion}
              />

              {tickerA && tickerB && <DetalleParCorrelacion tickerA={tickerA} tickerB={tickerB} par={parSeleccionado} />}

              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold text-app-text">Todos los pares</div>
                  <BotonExportarCsv
                    nombre={`correlaciones-pares-${frecuencia}`}
                    encabezados={['Ticker A', 'Ticker B', 'Correlación', 'Observaciones', 'Solapamiento %', 'Estado', 'Motivo']}
                    filas={() => data.pares.map(p => [p.ticker_a, p.ticker_b, p.valor, p.n_obs, p.solapamiento_pct, p.estado, p.motivo])}
                  />
                </div>
                <Card>
                  <TablaOrdenable
                    columnas={columnasPares}
                    filas={data.pares}
                    getKey={fmtPar}
                    ordenInicial={{ key: 'valor', dir: 'desc' }}
                    onFilaClick={p => {
                      const i = data.tickers.indexOf(p.ticker_a)
                      const j = data.tickers.indexOf(p.ticker_b)
                      if (i >= 0 && j >= 0) setSeleccion({ i, j })
                    }}
                  />
                </Card>
              </div>

              {(data.ranking.mas_correlacionados.length > 0 || data.ranking.mas_negativos.length > 0) && (
                <div className="grid grid-cols-1 gap-3">
                  {data.ranking.mas_correlacionados.length > 0 && (
                    <Card>
                      <div className="font-semibold text-app-text mb-2">Más correlacionados</div>
                      <div className="flex flex-col gap-1">
                        {data.ranking.mas_correlacionados.map(p => (
                          <div key={fmtPar(p)} className="flex justify-between text-caption">
                            <span className="text-app-text-dim">{fmtPar(p)}</span>
                            <span className="font-mono tabular-nums text-app-text">{p.valor?.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}
                  {data.ranking.mas_negativos.length > 0 && (
                    <Card>
                      <div className="font-semibold text-app-text mb-2">Más negativos (se compensan)</div>
                      <div className="flex flex-col gap-1">
                        {data.ranking.mas_negativos.map(p => (
                          <div key={fmtPar(p)} className="flex justify-between text-caption">
                            <span className="text-app-text-dim">{fmtPar(p)}</span>
                            <span className="font-mono tabular-nums text-app-neg">{p.valor?.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}
                </div>
              )}

              <BotonExportarCsv
                nombre={`correlaciones-matriz-${frecuencia}`}
                encabezados={['Instrumento', ...data.tickers]}
                filas={() => data.tickers.map((t, i) => [t, ...data.matriz[i].map(v => v)])}
              />
            </div>
          )}
        </QueryBoundary>
      )}
    </div>
  )
}
