import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../api/queryClient'
import {
  getTickersTecnicos, listarEstrategias, compararEstrategias,
  type VarianteSerie,
} from '../api'
import { usePreferencia, usePreferenciaNumerica } from '../hooks/usePreferencia'
import { calcularDesde, type PeriodoEvolucion } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import InfoTooltip from '../help/components/InfoTooltip'
import { Icon } from '../components/icons/Icons'
import ListaComparadorEstrategias from '../components/tecnico/ListaComparadorEstrategias'
import GraficoComparadorCapital from '../components/tecnico/GraficoComparadorCapital'
import PanelDiferenciaEstrategias from '../components/tecnico/PanelDiferenciaEstrategias'
import RiesgoComparadorCards from '../components/tecnico/RiesgoComparadorCards'
import DivergenciasEstrategias from '../components/tecnico/DivergenciasEstrategias'
import DetalleEstrategiaBacktest from '../components/tecnico/DetalleEstrategiaBacktest'

const CLAVE_CAPITAL = 'inversiones-comparador-capital'
const CLAVE_ESTRATEGIAS = 'inversiones-comparador-estrategias'
const CAPITAL_DEFAULT = 1_000_000
// Espejo de `comparador_estrategias_engine.MAX_ESTRATEGIAS` en el backend.
const MAX_ESTRATEGIAS = 8

const PERIODOS: PeriodoEvolucion[] = ['1M', '3M', '6M', '1Y', '3Y', '5Y', 'ALL']
const OPCIONES_PERIODO = [...PERIODOS.map(p => ({ value: p as string, label: p })), { value: 'custom', label: 'Personalizado' }]

export default function ComparadorEstrategias() {
  const navigate = useNavigate()

  const [tickerSel, setTickerSel] = useState<string | null>(null)
  const [filtroTicker, setFiltroTicker] = useState('')
  const [varianteSel, setVarianteSel] = useState<VarianteSerie | null>(null)
  const [periodo, setPeriodo] = useState<PeriodoEvolucion>('3Y')
  const [personalizado, setPersonalizado] = useState(false)
  const [desdeCustom, setDesdeCustom] = useState('')
  const [hastaCustom, setHastaCustom] = useState('')
  const [referenciaId, setReferenciaId] = useState<number | null>(null)
  const [sinCostos, setSinCostos] = useState(false)
  const [mostrarRiesgo, setMostrarRiesgo] = useState(false)
  const [detalleId, setDetalleId] = useState<number | null>(null)

  const [capitalInicial, setCapitalInicial] = usePreferenciaNumerica(CLAVE_CAPITAL, CAPITAL_DEFAULT, 1, 1e12)
  const [estrategiaIds, setEstrategiaIds] = usePreferencia<number[]>(
    CLAVE_ESTRATEGIAS, [],
    crudo => {
      try {
        const arr = JSON.parse(crudo)
        return Array.isArray(arr) && arr.every(x => typeof x === 'number') ? arr : null
      } catch {
        return null
      }
    },
    arr => JSON.stringify(arr),
  )

  const tickersQuery = useQuery({ queryKey: qk.de('tecnico-tickers'), queryFn: getTickersTecnicos })
  const tickers = tickersQuery.data ?? []
  const ticker = tickerSel ?? tickers[0]?.ticker ?? null
  const tickerMeta = tickers.find(t => t.ticker === ticker)
  const seriesDisponibles = tickerMeta?.series ?? []
  const variante: VarianteSerie =
    varianteSel && seriesDisponibles.some(s => s.variante === varianteSel) ? varianteSel : 'local'

  const tickersFiltrados = filtroTicker.trim()
    ? tickers.filter(t => t.ticker.toLowerCase().includes(filtroTicker.trim().toLowerCase()))
    : tickers

  const estrategiasQuery = useQuery({ queryKey: qk.de('estrategias'), queryFn: () => listarEstrategias() })
  const estrategias = estrategiasQuery.data ?? []

  const desde = personalizado ? (desdeCustom || undefined) : calcularDesde(periodo)
  const hasta = personalizado ? (hastaCustom || undefined) : undefined

  const idsOrdenados = useMemo(() => [...estrategiaIds].sort((a, b) => a - b), [estrategiaIds])
  const referenciaValida = referenciaId != null && idsOrdenados.includes(referenciaId) ? referenciaId : null

  const comparadorQuery = useQuery({
    queryKey: qk.de(
      'comparador-estrategias', ticker, variante, desde, hasta, idsOrdenados, capitalInicial, referenciaValida, sinCostos,
    ),
    queryFn: () => compararEstrategias(ticker as string, {
      estrategia_ids: idsOrdenados, desde, hasta, variante, capital_inicial: capitalInicial,
      referencia_id: referenciaValida, sin_costos: sinCostos,
    }),
    enabled: !!ticker && idsOrdenados.length > 0,
  })
  const resultado = comparadorQuery.data

  function toggleEstrategia(id: number) {
    setEstrategiaIds(
      estrategiaIds.includes(id)
        ? estrategiaIds.filter(x => x !== id)
        : (estrategiaIds.length >= MAX_ESTRATEGIAS ? estrategiaIds : [...estrategiaIds, id]),
    )
  }

  useEffect(() => {
    if (referenciaId != null && !idsOrdenados.includes(referenciaId)) setReferenciaId(null)
  }, [idsOrdenados, referenciaId])

  useEffect(() => {
    if (idsOrdenados.length === 0) { setDetalleId(null); return }
    if (detalleId == null || !idsOrdenados.includes(detalleId)) setDetalleId(idsOrdenados[0])
  }, [idsOrdenados, detalleId])

  const detalleEstrategia = detalleId != null ? estrategias.find(e => e.id === detalleId) ?? null : null

  if (tickersQuery.isLoading || tickersQuery.error) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Comparador de estrategias" onBack={() => navigate(-1)} />
        <QueryBoundary isLoading={tickersQuery.isLoading} error={tickersQuery.error} onRetry={() => void tickersQuery.refetch()}>
          {null}
        </QueryBoundary>
      </div>
    )
  }

  if (tickers.length === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Comparador de estrategias" onBack={() => navigate(-1)} />
        <EmptyState
          title="Sin tickers para comparar"
          description="Agregá instrumentos a tu cartera o a la watchlist para poder correr un backtest."
        />
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Comparador de estrategias" onBack={() => navigate(-1)} />

      <Card className="mb-3">
        <div className="flex items-start gap-2">
          <Icon name="info" className="w-4 h-4 text-app-text-dim shrink-0 mt-0.5" />
          <div className="text-caption text-app-text-dim">
            Este análisis usa el histórico del instrumento y no depende de tus posiciones ni de la
            cartera seleccionada.{' '}
            <span className="inline-flex items-center gap-1 align-middle">
              <span className="text-label font-bold px-1.5 py-0.5 rounded border border-app-accent/40 text-app-accent bg-app-accent-soft">
                SIMULADO
              </span>
              <InfoTooltip term="comparador_simulado" label="" />
            </span>
          </div>
        </div>
      </Card>

      <div className="mb-3">
        <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Instrumento</div>
        <input
          value={filtroTicker} onChange={e => setFiltroTicker(e.target.value)}
          placeholder="Filtrar por ticker…"
          className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-3 text-caption text-app-text outline-none focus:border-app-accent/60 mb-2"
        />
        <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1 -mx-4 px-4">
          {tickersFiltrados.map(t => (
            <button
              key={t.ticker} onClick={() => setTickerSel(t.ticker)}
              className={`shrink-0 font-semibold text-caption px-3 py-1.5 rounded-[10px] border transition-colors ${
                t.ticker === ticker ? 'bg-app-accent-soft border-app-accent text-app-accent' : 'bg-app-surface border-app-border text-app-text-dim'
              }`}
            >
              {t.ticker}
            </button>
          ))}
          {tickersFiltrados.length === 0 && <div className="text-caption text-app-text-dim py-1.5">Sin resultados</div>}
        </div>
      </div>

      {seriesDisponibles.length > 1 && (
        <div className="mb-3">
          <Segmented
            options={seriesDisponibles.map(s => ({
              value: s.variante, label: s.variante === 'local' ? `Local (${s.moneda})` : `Subyacente (${s.moneda})`,
            }))}
            value={variante} onChange={v => setVarianteSel(v as VarianteSerie)}
          />
        </div>
      )}

      <div className="mb-3">
        <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Período</div>
        <Segmented
          options={OPCIONES_PERIODO}
          value={personalizado ? 'custom' : periodo}
          onChange={v => {
            if (v === 'custom') { setPersonalizado(true) }
            else { setPersonalizado(false); setPeriodo(v as PeriodoEvolucion) }
          }}
        />
        {personalizado && (
          <div className="flex items-center gap-2 mt-2">
            <input
              type="date" value={desdeCustom} onChange={e => setDesdeCustom(e.target.value)}
              className="h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-caption text-app-text"
            />
            <span className="text-app-text-faint text-caption">→</span>
            <input
              type="date" value={hastaCustom} onChange={e => setHastaCustom(e.target.value)}
              className="h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-caption text-app-text"
            />
          </div>
        )}
      </div>

      <div className="mb-3">
        <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Capital inicial</div>
        <input
          type="number" min={1} step={10000} value={capitalInicial}
          onChange={e => setCapitalInicial(Number(e.target.value) || CAPITAL_DEFAULT)}
          className="w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-body text-app-text outline-none focus:border-app-accent/60 tabular-nums"
        />
      </div>

      <div className="mb-3">
        <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">
          Estrategias ({estrategiaIds.length}/{MAX_ESTRATEGIAS})
        </div>
        {estrategiasQuery.isLoading ? (
          <div className="text-caption text-app-text-dim">Cargando…</div>
        ) : estrategias.length === 0 ? (
          <div className="text-caption text-app-text-dim">No hay estrategias guardadas. Creá una desde Análisis técnico.</div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {estrategias.map(e => (
              <button
                key={e.id} onClick={() => toggleEstrategia(e.id)}
                disabled={!estrategiaIds.includes(e.id) && estrategiaIds.length >= MAX_ESTRATEGIAS}
                className={`text-label font-bold px-2.5 py-1.5 rounded-lg border truncate max-w-[160px] disabled:opacity-40 ${
                  estrategiaIds.includes(e.id)
                    ? 'bg-app-accent-soft text-app-accent border-app-accent/40'
                    : 'bg-app-surface text-app-text-dim border-app-border'
                }`}
              >
                {e.nombre}
              </button>
            ))}
          </div>
        )}
      </div>

      {idsOrdenados.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <InfoTooltip term="comparador_referencia" label="Referencia" />
            <select
              value={referenciaValida ?? ''} onChange={e => setReferenciaId(e.target.value ? Number(e.target.value) : null)}
              className="h-9 rounded-lg bg-app-surface-2 border border-app-border px-2 text-caption text-app-text"
            >
              <option value="">Comprar y mantener</option>
              {idsOrdenados.map(id => {
                const e = estrategias.find(x => x.id === id)
                return e ? <option key={id} value={id}>{e.nombre}</option> : null
              })}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <Segmented
              options={[{ value: 'con', label: 'Con costos' }, { value: 'sin', label: 'Sin costos' }]}
              value={sinCostos ? 'sin' : 'con'} onChange={v => setSinCostos(v === 'sin')}
            />
            <InfoTooltip term="comparador_costos" label="" />
          </div>
        </div>
      )}

      {idsOrdenados.length === 0 ? (
        <EmptyState
          title="Elegí al menos una estrategia"
          description="Tocá los chips de arriba para agregarlas a la comparación."
        />
      ) : (
        <QueryBoundary isLoading={comparadorQuery.isLoading} error={comparadorQuery.error} onRetry={() => void comparadorQuery.refetch()}>
          {resultado && resultado.estado !== 'ok' ? (
            <EmptyState
              title={resultado.estado === 'sin_serie' ? 'Sin serie disponible' : 'Datos insuficientes'}
              description={
                resultado.estado === 'sin_serie'
                  ? 'Este ticker todavía no tiene historial de precios cargado.'
                  : 'No hay datos suficientes para evaluar este período: probá un rango más largo.'
              }
            />
          ) : resultado ? (
            <div className="flex flex-col gap-5">
              {resultado.advertencias.length > 0 && (
                <div className="text-label text-app-text-dim">{resultado.advertencias.join(' · ')}</div>
              )}

              <div>
                <h3 className="text-body font-bold text-app-text mb-2">Comparación</h3>
                <Card>
                  <ListaComparadorEstrategias
                    filas={resultado.filas} moneda={resultado.moneda}
                    onFilaClick={f => { if (f.estrategia_id != null) setDetalleId(f.estrategia_id) }}
                  />
                </Card>
              </div>

              <div>
                <h3 className="text-body font-bold text-app-text mb-2">Evolución del capital</h3>
                <Card>
                  <GraficoComparadorCapital
                    fechas={resultado.fechas} filas={resultado.filas} moneda={resultado.moneda}
                    capitalInicial={resultado.capital_inicial}
                  />
                </Card>
              </div>

              <div>
                <h3 className="text-body font-bold text-app-text mb-2">La diferencia</h3>
                <PanelDiferenciaEstrategias mejor={resultado.mejor} />
              </div>

              <div>
                <button
                  onClick={() => setMostrarRiesgo(v => !v)}
                  className="text-body font-bold text-app-text mb-2 flex items-center gap-1.5"
                >
                  Riesgo
                  <Icon name="chevron" className={`w-4 h-4 text-app-text-dim transition-transform ${mostrarRiesgo ? '' : '-rotate-90'}`} />
                </button>
                {mostrarRiesgo && <RiesgoComparadorCards filas={resultado.filas} />}
              </div>

              <div>
                <h3 className="text-body font-bold text-app-text mb-2">¿Por qué fueron diferentes?</h3>
                <DivergenciasEstrategias filas={resultado.filas} />
              </div>

              <div>
                <h3 className="text-body font-bold text-app-text mb-2">Detalle de una estrategia</h3>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {resultado.filas.filter(f => f.estrategia_id != null).map(f => (
                    <button
                      key={f.estrategia_id} onClick={() => setDetalleId(f.estrategia_id)}
                      className={`text-label font-bold px-2.5 py-1.5 rounded-lg border ${
                        detalleId === f.estrategia_id
                          ? 'bg-app-accent-soft text-app-accent border-app-accent/40'
                          : 'bg-app-surface text-app-text-dim border-app-border'
                      }`}
                    >
                      {f.nombre}
                    </button>
                  ))}
                </div>
                {detalleEstrategia && ticker ? (
                  <DetalleEstrategiaBacktest ticker={ticker} estrategia={detalleEstrategia} desde={desde} hasta={hasta} variante={variante} />
                ) : (
                  <div className="text-caption text-app-text-dim">Elegí una estrategia para ver su gráfico de velas, señales y operaciones.</div>
                )}
              </div>

              <Card>
                <h3 className="text-caption font-bold text-app-text mb-2">Qué no representa este backtest</h3>
                <ul className="list-disc list-inside text-label text-app-text-dim space-y-1.5">
                  <li>DCA (aportes periódicos) no es representable: el motor es long-only y todo-o-nada, sin sizing ni compras parciales.</li>
                  <li>Spread y slippage no están simulados: sólo la comisión por lado que configuró cada estrategia.</li>
                  <li>La serie del subyacente (USD) viene ajustada por dividendos/splits; la serie local, no.</li>
                  <li>No hay calendario de feriados: un hueco largo en la serie se avisa, nunca se rellena.</li>
                </ul>
                <div className="mt-2">
                  <InfoTooltip term="comparador_limitaciones" label="Ver todas las limitaciones" />
                </div>
              </Card>
            </div>
          ) : null}
        </QueryBoundary>
      )}
    </div>
  )
}
