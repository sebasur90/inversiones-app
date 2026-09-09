import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../api/queryClient'
import {
  getTickersTecnicos, getSerieTecnica, getPresetsEstrategia, listarEstrategias,
  guardarEstrategia, actualizarEstrategia, duplicarEstrategia, eliminarEstrategiaTecnica,
  backtestEstrategia, sembrarPresetsEstrategia,
  type CategoriaPreset, type EstrategiaDsl, type EstrategiaOut, type BacktestOut,
  type PresetEstrategiaOut, type VarianteSerie,
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
import EstrategiaAvanzadaJson from '../components/tecnico/EstrategiaAvanzadaJson'
import ResultadoBacktest from '../components/tecnico/ResultadoBacktest'
import FichaEstrategia from '../components/tecnico/FichaEstrategia'
import { esEditableVisual } from '../components/tecnico/dslEditable'
import { parseApiError } from '../help/errors/apiErrors'
import { descargarArchivo } from '../utils/descargar'
import {
  nombreArchivoEstrategia, parsearArchivoEstrategia, serializarEstrategia,
} from '../utils/estrategiaArchivo'

/** El backend une los errores del validador con "; ". Se listan uno por línea, truncando a los
 * primeros 5 con "y N más". */
function erroresDesde(e: unknown): string[] {
  const partes = parseApiError(e).message.split(';').map(s => s.trim()).filter(Boolean)
  if (partes.length <= 5) return partes
  return [...partes.slice(0, 5), `y ${partes.length - 5} más`]
}

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

  // Con `ventana === 0` (EXTREMOS/PERCENTIL en modo histórico acumulado) hay que traer toda la
  // serie disponible: si no, el "máximo histórico" sería el de las últimas 750 ruedas y la
  // etiqueta engañaría. Entra en la clave de react-query para que el cambio dispare refetch.
  const maxBarras = useMemo(
    () => (Object.values(activos).some(p => p.ventana === 0) ? 3000 : undefined),
    [activos],
  )

  const serieQuery = useQuery({
    queryKey: qk.de('tecnico-serie', ticker, desde, claves.join(','), variante, maxBarras ?? 0),
    queryFn: () => getSerieTecnica(ticker as string, { desde, indicadores: claves, variante, max_barras: maxBarras }),
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
            <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase mb-1.5">
              Indicadores
              <InfoTooltip term="analisis_tecnico_indicadores" />
            </div>
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
            tieneVelas={serie?.tiene_velas ?? true} tieneVolumen={serie?.tiene_volumen ?? true}
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

const ETIQUETA_CATEGORIA: Record<CategoriaPreset, string> = {
  tendencia: 'Seguir la tendencia',
  reversion: 'Comprar la baja (reversión)',
  ruptura: 'Rupturas',
  momentum: 'Momentum',
}

function SeccionEstrategias({
  ticker, desde, variante, moneda, seriesDisponibles, onVariante, tieneVelas, tieneVolumen,
}: {
  ticker: string
  desde?: string
  variante: VarianteSerie
  moneda: string
  seriesDisponibles: { variante: VarianteSerie; moneda: string; mercado: string }[]
  onVariante: (v: VarianteSerie) => void
  tieneVelas: boolean
  tieneVolumen: boolean
}) {
  const presetsQuery = useQuery({ queryKey: qk.de('tecnico-presets'), queryFn: getPresetsEstrategia })
  const guardadasQuery = useQuery({ queryKey: qk.de('estrategias'), queryFn: () => listarEstrategias() })

  const [dsl, setDsl] = useState<EstrategiaDsl | null>(null)
  // Cambia solo al elegir preset / cargar guardada: fuerza el re-montaje de EditorEstrategia para
  // que re-inicialice su estado interno desde el nuevo DSL (sin re-sincronizar en cada edición).
  const [semillaEditor, setSemillaEditor] = useState(0)
  const [estrategiaActualId, setEstrategiaActualId] = useState<number | null>(null)
  const [nombreActual, setNombreActual] = useState('')
  // Slug del preset del que salió lo que está en el editor: viaja como `tipo_preset` al guardar y
  // es lo que enlaza la estrategia con su ficha explicativa.
  const [presetActual, setPresetActual] = useState<string | null>(null)
  const [descripcionActual, setDescripcionActual] = useState<string | null>(null)
  // Se activa desde el panel avanzado ("Editar igual"): fuerza el editor visual aunque el DSL
  // tenga condiciones no representables (que se van a perder al guardar).
  const [forzarVisual, setForzarVisual] = useState(false)
  const [resultado, setResultado] = useState<BacktestOut | null>(null)
  const [errores, setErrores] = useState<string[]>([])
  const [avisoImport, setAvisoImport] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)
  const [modalGuardarOpen, setModalGuardarOpen] = useState(false)
  const [nombreParaGuardar, setNombreParaGuardar] = useState('')
  // Guardar sin ticker fijo: la estrategia queda reusable en cualquier instrumento y el screener
  // la corre sobre todo el universo (cartera ∪ watchlist), no sólo sobre un ticker.
  const [reutilizable, setReutilizable] = useState(false)
  const [modalImportarOpen, setModalImportarOpen] = useState(false)
  const [textoImportar, setTextoImportar] = useState('')
  const [avisoGuardado, setAvisoGuardado] = useState<string | null>(null)
  const [modalRestaurarOpen, setModalRestaurarOpen] = useState(false)
  const [restaurando, setRestaurando] = useState(false)

  useEffect(() => {
    if (dsl === null && presetsQuery.data && presetsQuery.data.length > 0) {
      const primero = presetsQuery.data[0]
      setDsl(primero.definicion)
      setNombreActual(primero.etiqueta)
      setPresetActual(primero.nombre)
      setSemillaEditor(s => s + 1)
    }
    // sólo para inicializar una vez que llegan los presets
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetsQuery.data])

  async function correrBacktestCon(definicion: EstrategiaDsl) {
    setCargando(true)
    setErrores([])
    try {
      const r = await backtestEstrategia(ticker, definicion, desde, undefined, variante)
      setResultado(r)
    } catch (e) {
      setErrores(erroresDesde(e))
      setResultado(null)
    } finally {
      setCargando(false)
    }
  }

  const correrBacktest = () => { if (dsl) void correrBacktestCon(dsl) }

  function elegirPreset(nombre: string) {
    const preset = presetsQuery.data?.find(p => p.nombre === nombre)
    if (preset) {
      setDsl(preset.definicion)
      setSemillaEditor(s => s + 1)
      setForzarVisual(false)
      setEstrategiaActualId(null)
      setNombreActual(preset.etiqueta)
      setPresetActual(preset.nombre)
      setDescripcionActual(null)
      setReutilizable(false)
      setResultado(null)
      setErrores([])
      setAvisoImport(null)
      setAvisoGuardado(null)
    }
  }

  function cargarGuardada(e: EstrategiaOut) {
    setDsl(e.definicion)
    setSemillaEditor(s => s + 1)
    setForzarVisual(false)
    setEstrategiaActualId(e.id)
    setNombreActual(e.nombre)
    setPresetActual(e.tipo_preset ?? null)
    setAvisoGuardado(null)
    setDescripcionActual(e.descripcion)
    setReutilizable(e.ticker === null)
    setResultado(null)
    setErrores([])
    setAvisoImport(null)
    // Sincronizar el toggle de variante con la que trae la estrategia guardada.
    onVariante(e.variante)
  }

  function importarTexto(texto: string) {
    setErrores([])
    setAvisoImport(null)
    let archivo
    try {
      archivo = parsearArchivoEstrategia(texto)
    } catch (e) {
      setErrores([e instanceof Error ? e.message : 'No se pudo leer el archivo.'])
      return
    }
    // Estrategia nueva (no un update): id en null y adoptamos sus metadatos.
    setDsl(archivo.definicion)
    setSemillaEditor(s => s + 1)
    setForzarVisual(false)
    setEstrategiaActualId(null)
    setNombreActual(archivo.nombre ?? 'Estrategia importada')
    setPresetActual(null)
    setAvisoGuardado(null)
    setDescripcionActual(archivo.descripcion)
    setReutilizable(!archivo.ticker)
    setResultado(null)
    if (archivo.variante && seriesDisponibles.some(s => s.variante === archivo.variante)) {
      onVariante(archivo.variante)
    }
    // No cambiamos el ticker de la página (podría no estar en cartera ni watchlist -> 404):
    // sólo avisamos si difiere.
    if (archivo.ticker && archivo.ticker !== ticker) {
      setAvisoImport(`El archivo se exportó para ${archivo.ticker}; el backtest corre sobre ${ticker}.`)
    }
    setModalImportarOpen(false)
    setTextoImportar('')
    // Correr el backtest ya: un DSL inválido dispara el 422 al toque.
    void correrBacktestCon(archivo.definicion)
  }

  function exportar() {
    if (!dsl) return
    const contenido = serializarEstrategia(dsl, {
      nombre: nombreActual || null, descripcion: descripcionActual, ticker: null, variante,
    })
    descargarArchivo(nombreArchivoEstrategia(nombreActual || 'estrategia'), contenido, 'application/json')
  }

  async function guardar() {
    if (!dsl || !nombreParaGuardar.trim()) return
    const tickerAGuardar = reutilizable ? null : ticker
    const cuerpo = {
      nombre: nombreParaGuardar, descripcion: descripcionActual, ticker: tickerAGuardar,
      tipo_preset: presetActual, definicion: dsl, variante,
    }
    try {
      if (estrategiaActualId) {
        await actualizarEstrategia(estrategiaActualId, cuerpo)
        setAvisoGuardado(`Estrategia «${nombreParaGuardar}» actualizada.`)
      } else {
        // El nombre identifica a la estrategia: si ya existía una con ese nombre, el backend la
        // pisa en vez de dejar dos homónimas, y `sobrescrita` es cómo lo avisamos.
        const guardada = await guardarEstrategia(cuerpo)
        setEstrategiaActualId(guardada.id)
        setAvisoGuardado(
          guardada.sobrescrita
            ? `Ya existía una estrategia llamada «${guardada.nombre}»: se sobrescribió con esta definición.`
            : `Estrategia «${guardada.nombre}» guardada.`,
        )
      }
      setNombreActual(nombreParaGuardar)
      setModalGuardarOpen(false)
      void guardadasQuery.refetch()
    } catch (e) {
      setErrores(erroresDesde(e))
    }
  }

  async function restaurarCatalogo() {
    setRestaurando(true)
    try {
      const r = await sembrarPresetsEstrategia(true)
      setAvisoGuardado(
        `Catálogo restaurado: ${r.creadas} nueva(s), ${r.actualizadas} devuelta(s) a su definición original.`,
      )
      setModalRestaurarOpen(false)
      void guardadasQuery.refetch()
    } catch (e) {
      setErrores(erroresDesde(e))
    } finally {
      setRestaurando(false)
    }
  }

  async function duplicar() {
    if (!estrategiaActualId) return
    try {
      const dup = await duplicarEstrategia(estrategiaActualId)
      void guardadasQuery.refetch()
      cargarGuardada(dup)
    } catch (e) {
      setErrores(erroresDesde(e))
    }
  }

  async function eliminar(id: number) {
    try {
      await eliminarEstrategiaTecnica(id)
      if (estrategiaActualId === id) setEstrategiaActualId(null)
      void guardadasQuery.refetch()
    } catch (e) {
      setErrores(erroresDesde(e))
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase">
        Estrategias
        <InfoTooltip term="analisis_tecnico_estrategias" />
      </div>
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
        <div className="text-label text-app-text-faint mb-1">Empezar desde una estrategia del catálogo</div>
        <div className="flex flex-col gap-2 mb-2">
          {agruparPorCategoria(presetsQuery.data ?? []).map(([categoria, presets]) => (
            <div key={categoria}>
              <div className="text-label text-app-text-faint mb-1">{ETIQUETA_CATEGORIA[categoria]}</div>
              <div className="flex flex-wrap gap-1.5">
                {presets.map(p => {
                  // La estrategia igual corre: el motor degrada (sin velas, el canal usa cierres;
                  // sin volumen, el filtro nunca se cumple). El aviso es para que el resultado no
                  // se lea como si estuviera midiendo lo que promete.
                  const faltaDato = (p.requiere_volumen && !tieneVolumen) || (p.requiere_velas && !tieneVelas)
                  return (
                    <button
                      key={p.nombre} onClick={() => elegirPreset(p.nombre)}
                      title={faltaDato
                        ? `${ticker} no tiene ${p.requiere_volumen && !tieneVolumen ? 'volumen' : 'velas'} en esta serie`
                        : undefined}
                      className={`font-semibold text-caption px-2.5 py-1.5 rounded-[10px] border transition-colors ${
                        presetActual === p.nombre && estrategiaActualId === null
                          ? 'border-app-gold text-app-gold bg-app-gold-soft'
                          : 'border-app-border text-app-text-dim bg-app-surface'
                      }`}
                    >
                      {p.etiqueta}
                      {faltaDato && <span className="ml-1 text-app-text-faint">·⚠</span>}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        {(guardadasQuery.data ?? []).length > 0 && (
          <>
            <div className="flex items-center justify-between mb-1">
              <span className="text-label text-app-text-faint">Mis estrategias guardadas</span>
              <button
                onClick={() => setModalRestaurarOpen(true)}
                className="text-label text-app-text-faint underline"
              >
                Restaurar catálogo
              </button>
            </div>
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

      {avisoImport && (
        <div className="bg-app-gold-soft border border-app-gold/40 rounded-xl px-3 py-2 text-caption text-app-text-dim">
          {avisoImport}
        </div>
      )}

      {avisoGuardado && (
        <div className="bg-app-surface-2 rounded-xl px-3 py-2 text-caption text-app-text-dim">
          {avisoGuardado}
        </div>
      )}

      <FichaEstrategia preset={presetActual} />

      {dsl && (esEditableVisual(dsl) || forzarVisual ? (
        <EditorEstrategia key={semillaEditor} dslInicial={dsl} onCambiar={setDsl} erroresValidacion={errores} />
      ) : (
        <EstrategiaAvanzadaJson
          dsl={dsl} onCambiar={setDsl} erroresValidacion={errores}
          onEditarIgual={() => { setForzarVisual(true); setSemillaEditor(s => s + 1) }}
        />
      ))}

      <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase">
        Backtest
        <InfoTooltip term="analisis_tecnico_backtest" />
      </div>
      <div className="flex gap-2 flex-wrap">
        <Button onClick={correrBacktest} disabled={cargando || !dsl}>{cargando ? 'Corriendo…' : 'Correr backtest'}</Button>
        <Button variant="outline" onClick={() => { setNombreParaGuardar(nombreActual); setModalGuardarOpen(true) }} disabled={!dsl}>
          Guardar
        </Button>
        {estrategiaActualId && <Button variant="outline" onClick={duplicar}>Duplicar</Button>}
        <Button variant="outline" onClick={() => { setTextoImportar(''); setModalImportarOpen(true) }}>Importar JSON</Button>
        <Button variant="outline" onClick={exportar} disabled={!dsl}>Exportar JSON</Button>
      </div>

      {resultado && dsl && <ResultadoBacktest resultado={resultado} dsl={dsl} />}

      <Modal open={modalGuardarOpen} onClose={() => setModalGuardarOpen(false)} title="Guardar estrategia">
        <div className="flex flex-col gap-3">
          <input
            autoFocus value={nombreParaGuardar} onChange={e => setNombreParaGuardar(e.target.value)}
            placeholder="Nombre de la estrategia"
            className="bg-app-surface-2 border border-app-border rounded-lg px-3 py-2 text-body text-app-text"
          />
          <label className="flex items-start gap-2 text-caption text-app-text-dim cursor-pointer">
            <input
              type="checkbox" className="mt-0.5"
              checked={reutilizable} onChange={e => setReutilizable(e.target.checked)}
            />
            <span>
              Reutilizable en todo el universo (sin ticker fijo).{' '}
              {reutilizable
                ? 'El screener la evalúa sobre toda la cartera y watchlist.'
                : `Queda atada a ${ticker}.`}
            </span>
          </label>
          <Button onClick={guardar} disabled={!nombreParaGuardar.trim()}>Guardar</Button>
        </div>
      </Modal>

      <Modal open={modalImportarOpen} onClose={() => setModalImportarOpen(false)} title="Importar estrategia (JSON)">
        <div className="flex flex-col gap-3">
          <p className="text-caption text-app-text-dim">
            Elegí un archivo <span className="font-mono">.json</span> exportado desde acá o desde el
            laboratorio, o pegá el JSON directamente. También se acepta el DSL crudo (el
            <span className="font-mono"> definicion</span> de un preset o de la API).
          </p>
          <input
            type="file" accept="application/json,.json"
            onChange={e => {
              const f = e.target.files?.[0]
              if (f) void f.text().then(importarTexto)
              e.target.value = ''  // permitir reimportar el mismo archivo
            }}
            className="text-caption text-app-text-dim file:mr-2 file:rounded-lg file:border file:border-app-border file:bg-app-surface-2 file:px-3 file:py-1.5 file:text-app-text"
          />
          <textarea
            value={textoImportar} onChange={e => setTextoImportar(e.target.value)}
            placeholder='{ "formato": "inversiones-app/estrategia", ... }  o  { "version": 1, "entrada": ... }'
            rows={8}
            className="bg-app-surface-2 border border-app-border rounded-lg px-3 py-2 font-mono text-label text-app-text"
          />
          <Button onClick={() => importarTexto(textoImportar)} disabled={!textoImportar.trim()}>
            Importar desde el texto
          </Button>
        </div>
      </Modal>

      <Modal open={modalRestaurarOpen} onClose={() => setModalRestaurarOpen(false)} title="Restaurar catálogo">
        <div className="flex flex-col gap-3">
          <p className="text-caption text-app-text-dim">
            Vuelve a guardar todas las estrategias del catálogo con su definición original, como
            reutilizables (sin ticker fijo), para que el screener y la watchlist las evalúen.
          </p>
          <p className="text-caption text-app-text-dim">
            Las que tengan el mismo nombre <strong>se sobrescriben</strong>: si le ajustaste el stop
            loss o las reglas a alguna, esos cambios se pierden. Tus estrategias con otro nombre no
            se tocan.
          </p>
          <Button onClick={restaurarCatalogo} disabled={restaurando}>
            {restaurando ? 'Restaurando…' : 'Restaurar catálogo'}
          </Button>
        </div>
      </Modal>
    </div>
  )
}

/** Presets por categoría, en el orden en que se muestran. El orden es deliberado: de lo más
 * conocido y direccional (tendencia) a lo más específico (momentum). */
function agruparPorCategoria(presets: PresetEstrategiaOut[]): [CategoriaPreset, PresetEstrategiaOut[]][] {
  const orden: CategoriaPreset[] = ['tendencia', 'reversion', 'ruptura', 'momentum']
  return orden
    .map(c => [c, presets.filter(p => p.categoria === c)] as [CategoriaPreset, PresetEstrategiaOut[]])
    .filter(([, ps]) => ps.length > 0)
}
