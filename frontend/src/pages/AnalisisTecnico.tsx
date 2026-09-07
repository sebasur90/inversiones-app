import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../api/queryClient'
import {
  getTickersTecnicos, getSerieTecnica, getPresetsEstrategia, listarEstrategias,
  guardarEstrategia, actualizarEstrategia, duplicarEstrategia, eliminarEstrategiaTecnica,
  backtestEstrategia,
  type EstrategiaDsl, type EstrategiaOut, type BacktestOut, type VarianteSerie,
} from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import { Skeleton } from '../components/ui/Skeleton'
import Modal from '../components/ui/Modal'
import Button from '../components/ui/Button'
import { Icon } from '../components/icons/Icons'
import InfoTooltip from '../help/components/InfoTooltip'
import { calcularDesde, type PeriodoEvolucion } from '../utils'
import { claveIndicador, paramsPorDefecto } from '../components/tecnico/indicadoresConfig'
import SelectorIndicadores from '../components/tecnico/SelectorIndicadores'
import GraficoTecnico from '../components/tecnico/GraficoTecnico'
import GraficoFullscreen from '../components/tecnico/GraficoFullscreen'
import EditorEstrategia from '../components/tecnico/EditorEstrategia'
import ResultadoBacktest from '../components/tecnico/ResultadoBacktest'
import { parseApiError } from '../help/errors/apiErrors'

type Vista = 'grafico' | 'estrategias'
const PERIODOS: PeriodoEvolucion[] = ['1M', '3M', '6M', '1Y', '3Y', 'YTD', 'ALL']

export default function AnalisisTecnico() {
  const [tickerSel, setTickerSel] = useState<string | null>(null)
  const [periodo, setPeriodo] = useState<PeriodoEvolucion>('1Y')
  const [activos, setActivos] = useState<Record<string, Record<string, number>>>({})
  const [fullscreen, setFullscreen] = useState(false)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [vista, setVista] = useState<Vista>('grafico')
  // Preferencia de variante; la efectiva se deriva contra las variantes reales del ticker actual
  // (sin useEffect, para que no haya flash al cambiar de ticker).
  const [varianteSel, setVarianteSel] = useState<VarianteSerie | null>(null)

  const tickersQuery = useQuery({ queryKey: qk.de('tecnico-tickers'), queryFn: getTickersTecnicos })
  const tickers = tickersQuery.data ?? []
  const ticker = tickerSel ?? tickers[0]?.ticker ?? null
  const tickerMeta = tickers.find(t => t.ticker === ticker)
  const seriesDisponibles = tickerMeta?.series ?? []
  const variante: VarianteSerie =
    varianteSel && seriesDisponibles.some(s => s.variante === varianteSel) ? varianteSel : 'local'
  const monedaSerie =
    seriesDisponibles.find(s => s.variante === variante)?.moneda || tickerMeta?.moneda || ''

  // Ordenada para que reordenar el mismo conjunto de indicadores no invalide la caché de react-query.
  const claves = useMemo(
    () => Object.entries(activos).map(([tipo, params]) => claveIndicador(tipo, params)).sort(),
    [activos],
  )
  const desde = calcularDesde(periodo)

  const serieQuery = useQuery({
    queryKey: qk.de('tecnico-serie', ticker, desde, claves.join(','), variante),
    queryFn: () => getSerieTecnica(ticker as string, { desde, indicadores: claves, variante }),
    enabled: ticker !== null,
  })
  const serie = serieQuery.data
  const monedaMostrada = serie?.moneda || monedaSerie

  function toggleIndicador(tipo: string) {
    setActivos(prev => {
      const next = { ...prev }
      if (tipo in next) delete next[tipo]
      else next[tipo] = paramsPorDefecto(tipo)
      return next
    })
  }
  function cambiarParamIndicador(tipo: string, nombre: string, valor: number) {
    setActivos(prev => ({ ...prev, [tipo]: { ...prev[tipo], [nombre]: valor } }))
  }

  if (tickersQuery.isLoading || tickersQuery.error) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Análisis técnico" />
        <QueryBoundary isLoading={tickersQuery.isLoading} error={tickersQuery.error} onRetry={() => void tickersQuery.refetch()}>
          {null}
        </QueryBoundary>
      </div>
    )
  }

  if (tickers.length === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Análisis técnico" />
        <EmptyState title="Sin tickers para analizar" description="Agregá instrumentos a tu cartera o a la watchlist para ver velas, indicadores y estrategias." />
      </div>
    )
  }

  const tieneGrafico = !!serie && serie.barras.length > 0

  return (
    <div className="pb-4">
      <ScreenHeader title="Análisis técnico" />

      <div className="mb-3 flex items-center gap-2">
        <Segmented
          options={[{ value: 'grafico', label: 'Gráfico' }, { value: 'estrategias', label: 'Estrategias' }]}
          value={vista} onChange={setVista}
        />
        <InfoTooltip term="analisis_tecnico_titulo" />
      </div>

      <div className="flex gap-2 overflow-x-auto no-scrollbar pb-2 mb-3 -mx-4 px-4">
        {tickers.map(t => (
          <button
            key={t.ticker} onClick={() => setTickerSel(t.ticker)}
            className={`shrink-0 font-semibold text-caption px-3 py-1.5 rounded-[10px] border transition-colors ${
              t.ticker === ticker ? 'bg-app-gold-soft border-app-gold text-app-gold' : 'bg-app-surface border-app-border text-app-text-dim'
            }`}
          >
            {t.ticker}
          </button>
        ))}
      </div>

      {vista === 'grafico' ? (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Segmented options={PERIODOS.map(p => ({ value: p, label: p }))} value={periodo} onChange={setPeriodo} />
            {seriesDisponibles.length > 1 && (
              <Segmented
                options={seriesDisponibles.map(s => ({
                  value: s.variante,
                  label: s.variante === 'local' ? `Local (${s.moneda})` : `Subyacente (${s.moneda})`,
                }))}
                value={variante}
                onChange={v => setVarianteSel(v as VarianteSerie)}
              />
            )}
            {monedaMostrada && (
              <span className="text-label font-semibold px-1.5 py-0.5 rounded border border-app-border text-app-text-dim">
                {monedaMostrada}
              </span>
            )}
          </div>
          <div className="mb-3">
            <SelectorIndicadores
              activos={activos} onToggle={toggleIndicador} onCambiarParam={cambiarParamIndicador}
              tieneVolumen={serie?.tiene_volumen ?? true}
            />
          </div>

          <QueryBoundary
            isLoading={serieQuery.isLoading} error={serieQuery.error}
            onRetry={() => void serieQuery.refetch()} fallback={<Skeleton className="h-[240px] rounded-xl" />}
          >
            {serie && serie.barras.length === 0 ? (
              <EmptyState
                title="Sin serie suficiente"
                description={
                  serie.advertencias.includes('un_solo_punto')
                    ? 'Este ticker recién se agregó: todavía tiene un solo precio registrado, no alcanza para graficar.'
                    : 'Todavía no hay datos históricos para este ticker.'
                }
              />
            ) : serie ? (
              <GraficoTecnico
                barras={serie.barras} indicadores={serie.indicadores} activos={activos}
                tieneVelas={serie.tiene_velas} tieneVolumen={serie.tiene_volumen}
                moneda={monedaMostrada}
                onToggleFullscreen={() => setFullscreen(true)}
                hoverIndex={hoverIndex} onHover={setHoverIndex}
              />
            ) : null}
          </QueryBoundary>

          {serie && serie.barras.length > 0 && serie.advertencias.length > 0 && (
            <div className="mt-2 text-label text-app-text-dim">{serie.advertencias.join(' · ')}</div>
          )}
        </>
      ) : (
        ticker && (
          <SeccionEstrategias
            ticker={ticker} desde={desde} variante={variante} moneda={monedaSerie}
            seriesDisponibles={seriesDisponibles} onVariante={setVarianteSel}
          />
        )
      )}

      {tieneGrafico && serie && (
        <GraficoFullscreen
          open={fullscreen} onClose={() => setFullscreen(false)}
          title={`${ticker} · Análisis técnico${monedaMostrada ? ` (${monedaMostrada})` : ''}`}
        >
          <GraficoTecnico
            barras={serie.barras} indicadores={serie.indicadores} activos={activos}
            tieneVelas={serie.tiene_velas} tieneVolumen={serie.tiene_volumen}
            moneda={monedaMostrada}
            fullscreen onToggleFullscreen={() => setFullscreen(false)}
            hoverIndex={hoverIndex} onHover={setHoverIndex}
          />
        </GraficoFullscreen>
      )}
    </div>
  )
}

function SeccionEstrategias({
  ticker, desde, variante, moneda, seriesDisponibles, onVariante,
}: {
  ticker: string
  desde?: string
  variante: VarianteSerie
  moneda: string
  seriesDisponibles: { variante: VarianteSerie; moneda: string; mercado: string }[]
  onVariante: (v: VarianteSerie) => void
}) {
  const presetsQuery = useQuery({ queryKey: qk.de('tecnico-presets'), queryFn: getPresetsEstrategia })
  const guardadasQuery = useQuery({ queryKey: qk.de('estrategias'), queryFn: () => listarEstrategias() })

  const [dsl, setDsl] = useState<EstrategiaDsl | null>(null)
  // Cambia solo al elegir preset / cargar guardada: fuerza el re-montaje de EditorEstrategia para
  // que re-inicialice su estado interno desde el nuevo DSL (sin re-sincronizar en cada edición).
  const [semillaEditor, setSemillaEditor] = useState(0)
  const [estrategiaActualId, setEstrategiaActualId] = useState<number | null>(null)
  const [nombreActual, setNombreActual] = useState('')
  const [resultado, setResultado] = useState<BacktestOut | null>(null)
  const [errores, setErrores] = useState<string[]>([])
  const [cargando, setCargando] = useState(false)
  const [modalGuardarOpen, setModalGuardarOpen] = useState(false)
  const [nombreParaGuardar, setNombreParaGuardar] = useState('')

  useEffect(() => {
    if (dsl === null && presetsQuery.data && presetsQuery.data.length > 0) {
      setDsl(presetsQuery.data[0].definicion)
      setNombreActual(presetsQuery.data[0].nombre)
      setSemillaEditor(s => s + 1)
    }
    // sólo para inicializar una vez que llegan los presets
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetsQuery.data])

  async function correrBacktest() {
    if (!dsl) return
    setCargando(true)
    setErrores([])
    try {
      const r = await backtestEstrategia(ticker, dsl, desde, undefined, variante)
      setResultado(r)
    } catch (e) {
      setErrores([parseApiError(e).message])
      setResultado(null)
    } finally {
      setCargando(false)
    }
  }

  function elegirPreset(nombre: string) {
    const preset = presetsQuery.data?.find(p => p.nombre === nombre)
    if (preset) {
      setDsl(preset.definicion)
      setSemillaEditor(s => s + 1)
      setEstrategiaActualId(null)
      setNombreActual(preset.nombre)
      setResultado(null)
      setErrores([])
    }
  }

  function cargarGuardada(e: EstrategiaOut) {
    setDsl(e.definicion)
    setSemillaEditor(s => s + 1)
    setEstrategiaActualId(e.id)
    setNombreActual(e.nombre)
    setResultado(null)
    setErrores([])
    // Sincronizar el toggle de variante con la que trae la estrategia guardada.
    onVariante(e.variante)
  }

  async function guardar() {
    if (!dsl || !nombreParaGuardar.trim()) return
    try {
      if (estrategiaActualId) {
        await actualizarEstrategia(estrategiaActualId, { nombre: nombreParaGuardar, ticker, definicion: dsl, variante })
      } else {
        const creada = await guardarEstrategia({ nombre: nombreParaGuardar, ticker, definicion: dsl, variante })
        setEstrategiaActualId(creada.id)
      }
      setNombreActual(nombreParaGuardar)
      setModalGuardarOpen(false)
      void guardadasQuery.refetch()
    } catch (e) {
      setErrores([parseApiError(e).message])
    }
  }

  async function duplicar() {
    if (!estrategiaActualId) return
    try {
      const dup = await duplicarEstrategia(estrategiaActualId)
      void guardadasQuery.refetch()
      cargarGuardada(dup)
    } catch (e) {
      setErrores([parseApiError(e).message])
    }
  }

  async function eliminar(id: number) {
    try {
      await eliminarEstrategiaTecnica(id)
      if (estrategiaActualId === id) setEstrategiaActualId(null)
      void guardadasQuery.refetch()
    } catch (e) {
      setErrores([parseApiError(e).message])
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {seriesDisponibles.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-label text-app-text-faint">Serie</span>
          <Segmented
            options={seriesDisponibles.map(s => ({
              value: s.variante,
              label: s.variante === 'local' ? `Local (${s.moneda})` : `Subyacente (${s.moneda})`,
            }))}
            value={variante}
            onChange={v => onVariante(v as VarianteSerie)}
          />
          <span className="text-label text-app-text-dim">
            El backtest corre sobre esta serie ({moneda || '—'}).
          </span>
        </div>
      )}
      <div>
        <div className="text-label text-app-text-faint mb-1">Empezar desde un preset</div>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {(presetsQuery.data ?? []).map(p => (
            <button
              key={p.nombre} onClick={() => elegirPreset(p.nombre)}
              className={`font-semibold text-caption px-2.5 py-1.5 rounded-[10px] border transition-colors ${
                nombreActual === p.nombre && estrategiaActualId === null
                  ? 'border-app-gold text-app-gold bg-app-gold-soft'
                  : 'border-app-border text-app-text-dim bg-app-surface'
              }`}
            >
              {p.nombre}
            </button>
          ))}
        </div>
        {(guardadasQuery.data ?? []).length > 0 && (
          <>
            <div className="text-label text-app-text-faint mb-1">Mis estrategias guardadas</div>
            <div className="flex flex-wrap gap-1.5">
              {(guardadasQuery.data ?? []).map(e => (
                <div
                  key={e.id}
                  className={`flex items-center gap-1.5 rounded-[10px] border px-2.5 py-1.5 ${
                    estrategiaActualId === e.id ? 'border-app-gold bg-app-gold-soft' : 'border-app-border bg-app-surface'
                  }`}
                >
                  <button onClick={() => cargarGuardada(e)} className={`font-semibold text-caption ${estrategiaActualId === e.id ? 'text-app-gold' : 'text-app-text-dim'}`}>
                    {e.nombre}
                    {e.variante === 'subyacente' && <span className="ml-1 text-label text-app-text-faint">· USD</span>}
                  </button>
                  <button onClick={() => eliminar(e.id)} aria-label={`Eliminar ${e.nombre}`} className="text-app-text-faint">
                    <Icon name="trash" className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {dsl && <EditorEstrategia key={semillaEditor} dslInicial={dsl} onCambiar={setDsl} erroresValidacion={errores} />}

      <div className="flex gap-2 flex-wrap">
        <Button onClick={correrBacktest} disabled={cargando || !dsl}>{cargando ? 'Corriendo…' : 'Correr backtest'}</Button>
        <Button variant="outline" onClick={() => { setNombreParaGuardar(nombreActual); setModalGuardarOpen(true) }} disabled={!dsl}>
          Guardar
        </Button>
        {estrategiaActualId && <Button variant="outline" onClick={duplicar}>Duplicar</Button>}
      </div>

      {resultado && dsl && <ResultadoBacktest resultado={resultado} dsl={dsl} />}

      <Modal open={modalGuardarOpen} onClose={() => setModalGuardarOpen(false)} title="Guardar estrategia">
        <div className="flex flex-col gap-3">
          <input
            autoFocus value={nombreParaGuardar} onChange={e => setNombreParaGuardar(e.target.value)}
            placeholder="Nombre de la estrategia"
            className="bg-app-surface-2 border border-app-border rounded-lg px-3 py-2 text-body text-app-text"
          />
          <Button onClick={guardar} disabled={!nombreParaGuardar.trim()}>Guardar</Button>
        </div>
      </Modal>
    </div>
  )
}
