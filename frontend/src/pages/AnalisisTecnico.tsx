import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { qk } from '../api/queryClient'
import {
  getTickersTecnicos, getSerieTecnica, getPresetsEstrategia, listarEstrategias,
  guardarEstrategia, actualizarEstrategia, duplicarEstrategia, eliminarEstrategiaTecnica,
  backtestEstrategia, sembrarPresetsEstrategia, getZonasTicker, guardarZonasTicker, getOperacionesTicker, getFuerzaRelativa,
  getLecturaTecnica,
  type CategoriaPreset, type EstrategiaDsl, type EstrategiaOut, type BacktestOut,
  type PresetEstrategiaOut, type BenchmarkFR, type IntervaloSerie, type VarianteSerie, type VarianteEstrategia, type TipoZona, type ZonaPrecioIn,
  type ZonaPrecioOut,
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
import {
  MAX_INDICADORES, claveIndicador, paramsPorDefecto, type IndicadorActivo,
} from '../components/tecnico/indicadoresConfig'
import SelectorIndicadores from '../components/tecnico/SelectorIndicadores'
import GraficoTecnico from '../components/tecnico/GraficoTecnico'
import GraficoFullscreen from '../components/tecnico/GraficoFullscreen'
import ResumenOperaciones from '../components/tecnico/ResumenOperaciones'
import EditorEstrategia from '../components/tecnico/EditorEstrategia'
import EditorZonas, {
  borradorADibujo, borradorDesdeOut, borradorInvalido, parsearBorde, zonaSugerida,
  type BorradorZonas,
} from '../components/tecnico/EditorZonas'
import ResumenZonas from '../components/tecnico/ResumenZonas'
import CalculadoraPosicion from '../components/tecnico/CalculadoraPosicion'
import EncabezadoTicker from '../components/tecnico/EncabezadoTicker'
import LecturaGrafico from '../components/tecnico/LecturaGrafico'
import { useDibujos } from '../components/tecnico/useDibujos'
import { guardarVerOperaciones, leerVerOperaciones } from '../components/tecnico/operacionesPropias'
import type { BordeZona, ZonasDibujo } from '../components/tecnico/ZonasPrecio'
import { textoBorde } from '../components/tecnico/formatoEjes'
import EstrategiaAvanzadaJson from '../components/tecnico/EstrategiaAvanzadaJson'
import ResultadoBacktest from '../components/tecnico/ResultadoBacktest'
import FichaEstrategia from '../components/tecnico/FichaEstrategia'
import { esEditableVisual } from '../components/tecnico/dslEditable'
import { parseApiError } from '../help/errors/apiErrors'
import { descargarArchivo } from '../utils/descargar'
import {
  nombreArchivoEstrategia, parsearArchivoEstrategia, serializarEstrategia,
} from '../utils/estrategiaArchivo'
import { textosAdvertenciasSerie } from '../utils/advertenciasSerie'

/** El backend une los errores del validador con "; ". Se listan uno por línea, truncando a los
 * primeros 5 con "y N más". */
function erroresDesde(e: unknown): string[] {
  const partes = parseApiError(e).message.split(';').map(s => s.trim()).filter(Boolean)
  if (partes.length <= 5) return partes
  return [...partes.slice(0, 5), `y ${partes.length - 5} más`]
}

type Vista = 'grafico' | 'estrategias'
const PERIODOS: PeriodoEvolucion[] = ['1M', '3M', '6M', '1Y', '3Y', 'YTD', 'ALL']
// En castellano y cortos: los siete tienen que entrar en una fila junto al D / S / M.
const ETIQUETA_PERIODO: Partial<Record<PeriodoEvolucion, string>> = { '1Y': '1A', '3Y': '3A', ALL: 'Todo' }
const NOMBRE_INTERVALO: Record<IntervaloSerie, string> = { D: 'Velas diarias', S: 'Velas semanales', M: 'Velas mensuales' }

// Ids de instancias de indicador: sólo tienen que ser únicos y crecientes dentro de la sesión
// (`colorIndicador` ordena por id para asignar el color de las repetidas).
let proximoIdIndicador = 1

const CLAVE_ESCALA_LOG = 'tecnico-escala-log'
const INTERVALOS: { value: IntervaloSerie; label: string }[] = [
  { value: 'D', label: 'D' }, { value: 'S', label: 'S' }, { value: 'M', label: 'M' },
]

function leerEscalaLog(): boolean {
  try {
    return localStorage.getItem(CLAVE_ESCALA_LOG) === '1'
  } catch {
    return false
  }
}

export default function AnalisisTecnico() {
  // El ticker puede llegar en la URL (`/analisis-tecnico?ticker=AL30`): es como entra la watchlist.
  // Se deriva sin `useEffect` de sincronización: la elección de esta sesión manda sobre el
  // parámetro, el parámetro sobre el primero del universo, y un ticker que no está en el universo
  // (se dejó de seguir, se vendió) cae al default en vez de pedir una serie que daría 404.
  const [searchParams, setSearchParams] = useSearchParams()
  const [tickerSel, setTickerSel] = useState<string | null>(null)
  const [periodo, setPeriodo] = useState<PeriodoEvolucion>('1Y')
  // Lista y no mapa por tipo: se permiten varias instancias del mismo indicador con distintos
  // parámetros (SMA 50 + SMA 200).
  const [activos, setActivos] = useState<IndicadorActivo[]>([])
  const [fullscreen, setFullscreen] = useState(false)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [vista, setVista] = useState<Vista>('grafico')
  const [verOperaciones, setVerOperaciones] = useState<boolean>(leerVerOperaciones)
  const [escalaLog, setEscalaLog] = useState<boolean>(leerEscalaLog)
  const [intervalo, setIntervalo] = useState<IntervaloSerie>('D')
  // Stop que está probando la calculadora de tamaño: se dibuja como una línea provisoria.
  const [verNiveles, setVerNiveles] = useState(false)
  const [verFuerzaRelativa, setVerFuerzaRelativa] = useState(false)
  // `null` = el que corresponde a la moneda de la serie (S&P 500 en dólares, Merval en pesos).
  const [benchmarkSel, setBenchmarkSel] = useState<BenchmarkFR | null>(null)
  const [stopProvisorio, setStopProvisorio] = useState<number | null>(null)
  // Preferencia de variante; la efectiva se deriva contra las variantes reales del ticker actual
  // (sin useEffect, para que no haya flash al cambiar de ticker).
  const [varianteSel, setVarianteSel] = useState<VarianteSerie | null>(null)
  // `null` = no se está editando. El borrador vive acá y no en el editor para que el gráfico pueda
  // dibujarlo mientras se arrastra: son dos vistas del mismo valor.
  const [borrador, setBorrador] = useState<BorradorZonas | null>(null)
  const [errorZonas, setErrorZonas] = useState<string | null>(null)
  // Ocultar zonas y niveles despeja el gráfico; mientras se editan se ven igual (es lo que se mueve).
  const [verZonas, setVerZonas] = useState(true)
  const [indicadoresAbierto, setIndicadoresAbierto] = useState(false)
  const graficoRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  const queryClient = useQueryClient()
  const tickersQuery = useQuery({ queryKey: qk.de('tecnico-tickers'), queryFn: getTickersTecnicos })
  const tickers = tickersQuery.data ?? []
  const tickerPedido = tickerSel ?? searchParams.get('ticker')
  const ticker =
    tickerPedido && tickers.some(t => t.ticker === tickerPedido)
      ? tickerPedido
      : tickers[0]?.ticker ?? null

  /** Elegir un ticker lo refleja en la URL, así el gráfico se puede compartir y sobrevive a un
   * refresco. `replace` para no llenar el historial de atrás con cada ticker mirado. */
  function elegirTicker(nuevo: string) {
    setTickerSel(nuevo)
    setBenchmarkSel(null)
    setVarianteSel(null)   // cada ticker abre en su propia referencia, no en la serie del anterior
    setBorrador(null)   // el borrador era de otro instrumento
    setErrorZonas(null)
    const params = new URLSearchParams(searchParams)
    params.set('ticker', nuevo)
    setSearchParams(params, { replace: true })
  }
  const tickerMeta = tickers.find(t => t.ticker === ticker)
  const seriesDisponibles = tickerMeta?.series ?? []
  // Sin elección de esta sesión, cada ticker abre en su serie de referencia: el precio en USD del
  // subyacente para un CEDEAR (es el que sirve para decidir), el local para el resto.
  const referencia: VarianteSerie = tickerMeta?.variante_referencia ?? 'local'
  const variante: VarianteSerie =
    varianteSel && seriesDisponibles.some(s => s.variante === varianteSel) ? varianteSel : referencia
  const monedaSerie =
    seriesDisponibles.find(s => s.variante === variante)?.moneda || tickerMeta?.moneda || ''

  // Ordenada y sin repetidos para que reordenar el mismo conjunto de indicadores (o tener dos
  // instancias iguales) no invalide la caché de react-query ni pida la misma serie dos veces.
  const claves = useMemo(
    () => [...new Set(activos.map(a => claveIndicador(a.tipo, a.params)))].sort(),
    [activos],
  )
  const desde = calcularDesde(periodo)

  // Con `ventana === 0` (EXTREMOS/PERCENTIL en modo histórico acumulado) hay que traer toda la
  // serie disponible: si no, el "máximo histórico" sería el de las últimas 750 ruedas y la
  // etiqueta engañaría. Lo mismo con el período `ALL`: ahí `desde` va vacío y el backend sirve
  // todo lo que tenga, pero el tope de 750 barras lo recortaría a ~3 años. Entra en la clave de
  // react-query para que el cambio dispare refetch.
  const maxBarras = useMemo(
    () => (periodo === 'ALL' || activos.some(a => a.params.ventana === 0) ? 3000 : undefined),
    [activos, periodo],
  )

  const serieQuery = useQuery({
    queryKey: qk.de('tecnico-serie', ticker, desde, claves.join(','), variante, maxBarras ?? 0, intervalo),
    queryFn: () => getSerieTecnica(ticker as string, {
      desde, indicadores: claves, variante, max_barras: maxBarras, intervalo, niveles_auto: true,
    }),
    enabled: ticker !== null,
    // Cambiar un indicador (o el período) del mismo ticker deja el gráfico anterior a la vista
    // mientras llega el nuevo: si no, el gráfico se cambiaba por el esqueleto, perdía el zoom y la
    // pantalla completa se cerraba sola. Otro ticker u otra serie sí esperan vacíos: sus zonas y
    // dibujos no van sobre las velas de la anterior. (La clave es [nombre, ticker, desde, claves,
    // variante, …].)
    placeholderData: (previa, consultaPrevia) =>
      consultaPrevia?.queryKey[1] === ticker && consultaPrevia?.queryKey[4] === variante ? previa : undefined,
  })
  const serie = serieQuery.data
  const ultimoCierre = serie?.barras[serie.barras.length - 1]?.cierre ?? null
  const monedaMostrada = serie?.moneda || monedaSerie

  // La fuerza relativa se pide con la misma ventana que la serie (mismos `desde`, `intervalo` y
  // `max_barras`) y se alinea por fecha. Sólo con el panel prendido.
  const fuerzaRelativaQuery = useQuery({
    queryKey: qk.de('tecnico-fuerza-relativa', ticker, serie?.variante, benchmarkSel, desde, intervalo, maxBarras ?? 0),
    queryFn: () => getFuerzaRelativa(ticker as string, {
      variante: serie!.variante, benchmark: benchmarkSel ?? undefined, desde, intervalo, max_barras: maxBarras,
    }),
    enabled: ticker !== null && serie != null && verFuerzaRelativa,
    staleTime: 5 * 60_000,
  })

  // La lectura va sobre la serie que el gráfico efectivamente muestra (la referencia puede haber
  // degradado a la local) y siempre en diario, sin importar período ni intervalo: no los lleva en
  // la clave para no volver a pedirla al cambiarlos.
  const lecturaQuery = useQuery({
    queryKey: qk.de('tecnico-lectura', ticker, serie?.variante),
    queryFn: () => getLecturaTecnica(ticker as string, serie!.variante),
    enabled: ticker !== null && serie != null,
    staleTime: 5 * 60_000,
  })
  // La lectura no sale a bajar el índice; el panel de fuerza relativa sí. Cuando el panel termina,
  // la lectura ya puede tener su fila de fuerza relativa.
  const fuerzaRelativaLista = fuerzaRelativaQuery.isSuccess
  useEffect(() => {
    if (fuerzaRelativaLista) void queryClient.invalidateQueries({ queryKey: qk.de('tecnico-lectura', ticker) })
  }, [fuerzaRelativaLista, ticker, queryClient])

  // Sólo hay operaciones propias que mostrar si el ticker está (o estuvo) en la cartera.
  const puedeVerOperaciones = tickerMeta != null && tickerMeta.origen !== 'watchlist'
  // Se pide sobre la serie que el gráfico efectivamente muestra (`serie.variante`): la referencia
  // puede haber degradado a la local, y las marcas tienen que estar en la moneda de esa serie.
  const operacionesQuery = useQuery({
    queryKey: qk.de('tecnico-operaciones', ticker, serie?.variante, intervalo),
    queryFn: () => getOperacionesTicker(ticker as string, serie!.variante, intervalo),
    enabled: ticker !== null && serie != null && verOperaciones && puedeVerOperaciones,
  })
  const misOperaciones = verOperaciones && puedeVerOperaciones ? operacionesQuery.data ?? null : null

  function alternarOperaciones() {
    const nuevo = !verOperaciones
    setVerOperaciones(nuevo)
    guardarVerOperaciones(nuevo)
  }
  function alternarEscalaLog() {
    const nuevo = !escalaLog
    setEscalaLog(nuevo)
    try {
      localStorage.setItem(CLAVE_ESCALA_LOG, nuevo ? '1' : '0')
    } catch {
      /* sin almacenamiento: queda sólo para esta visita */
    }
  }
  const dibujos = useDibujos(ticker, serie?.variante)
  const propsOperaciones = {
    intervalo,
    dibujos,
    // El servidor los calcula siempre (es barato); el botón sólo decide si se dibujan.
    nivelesAuto: serie?.niveles_auto ?? null,
    nivelesActivos: verNiveles,
    onToggleNiveles: () => setVerNiveles(v => !v),
    fuerzaRelativa: {
      activa: verFuerzaRelativa,
      onToggle: () => setVerFuerzaRelativa(v => !v),
      benchmark: benchmarkSel,
      onBenchmark: setBenchmarkSel,
      datos: fuerzaRelativaQuery.data,
      cargando: fuerzaRelativaQuery.isFetching,
      error: fuerzaRelativaQuery.isError,
    },
    escalaLog,
    onToggleEscalaLog: alternarEscalaLog,
    misOperaciones,
    operacionesActivas: verOperaciones && puedeVerOperaciones,
    onToggleOperaciones: puedeVerOperaciones ? alternarOperaciones : undefined,
  }

  const zonasQuery = useQuery({
    queryKey: qk.de('tecnico-zonas', ticker),
    queryFn: () => getZonasTicker(ticker as string),
    enabled: ticker !== null,
  })
  const zonasGuardadas = zonasQuery.data

  const guardarZonasMut = useMutation({
    mutationFn: (cambios: { compra?: ZonaPrecioIn | null; venta?: ZonaPrecioIn | null }) =>
      guardarZonasTicker(ticker as string, cambios),
    onSuccess: async () => {
      // La watchlist muestra la zona de compra en su badge: si no se invalida, queda mostrando el
      // valor anterior hasta el próximo refetch.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.de('tecnico-zonas', ticker) }),
        queryClient.invalidateQueries({ queryKey: qk.watchlist }),
      ])
      setBorrador(null)
      setErrorZonas(null)
    },
    onError: (e) => setErrorZonas(parseApiError(e).message),
  })

  /** ¿Esta zona se dibuja sobre la serie que se está viendo?
   *
   * Sólo si fue medida sobre **esta** serie. Una zona local está en pesos (26.000) y la del
   * subyacente en dólares (170): dibujar la primera sobre el gráfico de la segunda metía ese
   * 26.000 en la escala vertical y aplastaba las velas contra el borde inferior. Son dos
   * instrumentos, no el mismo precio en dos monedas.
   */
  const zonaDeEstaSerie = (zona: ZonaPrecioOut | null | undefined): ZonaPrecioOut | null =>
    zona && zona.activa && zona.variante === variante ? zona : null

  // Los niveles de la posición (stop-loss y objetivo) salen del Sheet o de un porcentaje sobre el
  // precio promedio de compra: están siempre en la moneda local, así que sobre la serie del
  // subyacente no significan nada.
  const nivelesDeLaPosicion = variante === 'local'
    ? { stopLoss: zonasGuardadas?.nivel_stop_loss, objetivo: zonasGuardadas?.nivel_objetivo }
    : { stopLoss: null, objetivo: null }

  /** Lo que el gráfico dibuja: el borrador mientras se edita, lo guardado si no. */
  const zonasDibujo: ZonasDibujo | undefined = borrador
    ? borradorADibujo(borrador, nivelesDeLaPosicion.stopLoss, nivelesDeLaPosicion.objetivo)
    : zonasGuardadas
      ? {
          compra: zonaDeEstaSerie(zonasGuardadas.compra),
          venta: zonaDeEstaSerie(zonasGuardadas.venta),
          ...nivelesDeLaPosicion,
        }
      : undefined

  /** Lo que se le pasa al gráfico: las zonas (si están a la vista o se están editando) más, si lo
   * hay, el stop de la calculadora, que se ve siempre: es lo que se está probando. */
  const zonasVisibles = verZonas || borrador !== null
  const zonasMostradas = zonasVisibles ? zonasDibujo : undefined
  const zonasEnGrafico: ZonasDibujo | undefined = stopProvisorio != null
    ? { ...zonasMostradas, stopProvisorio }
    : zonasMostradas

  function empezarAEditarZonas() {
    setErrorZonas(null)
    // Se siembra sólo con las zonas de **esta** serie: arrancar la edición en dólares con los
    // números en pesos de la zona local dibujaría la banda fuera de escala y, al guardar,
    // convertiría la zona a esta serie con valores de la otra.
    const inicial = borradorDesdeOut(
      zonaDeEstaSerie(zonasGuardadas?.compra), zonaDeEstaSerie(zonasGuardadas?.venta),
    )
    // "Dibujar zona" sin ninguna zona: arranca con una de compra a la vista para arrastrarla, en
    // vez de un editor vacío con un gráfico sin nada que mover.
    if (!inicial.compra && !inicial.venta) inicial.compra = zonaSugerida('compra', ultimoCierre)
    setBorrador(inicial)
    // El botón está debajo del gráfico: en el celular el gráfico puede haber quedado fuera de la
    // pantalla, y lo que se edita es lo que está dibujado ahí.
    requestAnimationFrame(() => graficoRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  /** Arrastrar un borde escribe el borrador, no la DB: el guardado es explícito. `ZonasPrecio` ya
   * redondea a un paso acorde a la escala (el píxel da una precisión falsa); el número exacto se
   * escribe en el input. */
  function arrastrarZona(tipo: TipoZona, borde: BordeZona, valor: number) {
    setBorrador(prev => {
      if (!prev) return prev
      const actual = prev[tipo]
      if (!actual) return prev
      return { ...prev, [tipo]: { ...actual, [borde]: textoBorde(valor) } }
    })
  }

  function cancelarZonas() {
    setBorrador(null)
    setErrorZonas(null)
  }

  function guardarZonas() {
    if (!borrador || borradorInvalido(borrador)) return
    const una = (tipo: TipoZona): ZonaPrecioIn | null => {
      const z = borrador[tipo]
      if (!z) return null
      return {
        variante, moneda: monedaMostrada || null,
        piso: parsearBorde(z.piso), techo: parsearBorde(z.techo), activa: true,
      }
    }
    guardarZonasMut.mutate({ compra: una('compra'), venta: una('venta') })
  }

  function agregarIndicador(tipo: string) {
    setActivos(prev => (
      prev.length >= MAX_INDICADORES
        ? prev
        : [...prev, { id: proximoIdIndicador++, tipo, params: paramsPorDefecto(tipo) }]
    ))
  }
  function quitarIndicador(id: number) {
    setActivos(prev => prev.filter(a => a.id !== id))
  }
  function quitarTipoIndicador(tipo: string) {
    setActivos(prev => prev.filter(a => a.tipo !== tipo))
  }
  function cambiarParamIndicador(id: number, nombre: string, valor: number) {
    setActivos(prev => prev.map(a => (a.id === id ? { ...a, params: { ...a.params, [nombre]: valor } } : a)))
  }
  /** Desde la leyenda del gráfico: dos instancias con la misma clave se dibujan como una, así que
   * la ✕ saca las dos. */
  function quitarIndicadorPorClave(clave: string) {
    setActivos(prev => prev.filter(a => claveIndicador(a.tipo, a.params) !== clave))
  }

  const edicionZonas = {
    onGuardar: guardarZonas,
    onCancelar: cancelarZonas,
    guardando: guardarZonasMut.isPending,
    problema: borrador ? borradorInvalido(borrador) ?? errorZonas : null,
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
        <EmptyState ilustracion="lupa" emoji="📈" title="Sin tickers para analizar" description="Agregá instrumentos a tu cartera o a la watchlist para ver velas, indicadores y estrategias." />
      </div>
    )
  }

  const tieneGrafico = !!serie && serie.barras.length > 0

  // Notas que explican cómo leer la serie, no problemas de los datos: van plegadas para no empujar
  // el gráfico. Las advertencias de la serie (huecos, splits…) siguen a la vista.
  const notasSerie = [
    ...(intervalo !== 'D'
      ? [`Velas ${intervalo === 'S' ? 'semanales' : 'mensuales'}: los indicadores se calculan sobre esas barras. Las estrategias, el backtest, las alertas y la lectura siguen corriendo en diario.`]
      : []),
    ...(variante === 'subyacente' && (zonasGuardadas?.nivel_stop_loss != null || zonasGuardadas?.nivel_objetivo != null)
      ? ['El stop loss y el objetivo de tu posición están en pesos, sobre el precio al que compraste el CEDEAR: se ven en la serie Local. Para vigilar una venta en dólares, dibujá una zona de venta acá.']
      : []),
  ]

  return (
    <div className="pb-4">
      <ScreenHeader title="Análisis técnico" />

      {ticker && (
        <EncabezadoTicker
          tickers={tickers} ticker={ticker} onElegir={elegirTicker}
          barras={serie?.barras} moneda={monedaMostrada} intervalo={intervalo}
          seriesDisponibles={seriesDisponibles} variante={variante} referencia={referencia}
          onVariante={v => { setVarianteSel(v); setBorrador(null); setBenchmarkSel(null) }}
        />
      )}

      <div className="mb-3 flex items-center border-b border-app-border">
        <div role="tablist" aria-label="Vista" className="flex flex-[2]">
          {(['grafico', 'estrategias'] as const).map(v => (
            <button
              key={v} type="button" role="tab" aria-selected={vista === v} onClick={() => setVista(v)}
              className={`flex-1 h-11 inline-flex items-center justify-center gap-1.5 text-body font-semibold transition-[color,box-shadow,background-color] duration-150 hover:bg-white/[0.03] ${
                vista === v ? 'text-app-text shadow-[inset_0_-2px_0_var(--color-app-accent)]' : 'text-app-text-dim hover:text-app-text'
              }`}
            >
              <Icon name={v === 'grafico' ? 'trend' : 'target'} className="w-4 h-4" />
              {v === 'grafico' ? 'Gráfico' : 'Estrategias'}
            </button>
          ))}
        </div>
        {/* El diario es una pantalla aparte (todas tus operaciones, no las de este ticker): es un
            link, no una pestaña. */}
        <button
          type="button" onClick={() => navigate('/diario-operaciones')}
          className="group flex-1 h-11 inline-flex items-center justify-center gap-1 text-body font-semibold text-app-text-dim transition-colors duration-150 hover:text-app-text hover:bg-white/[0.03]"
        >
          Diario
          <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90 transition-transform duration-150 group-hover:translate-x-0.5" />
        </button>
        {/* Los eventos de este ticker sobre su precio: otra pantalla, que conserva el ticker. */}
        <button
          type="button" onClick={() => navigate(`/eventos?tab=impacto${ticker ? `&ticker=${encodeURIComponent(ticker)}` : ''}`)}
          className="group flex-1 h-11 inline-flex items-center justify-center gap-1 text-body font-semibold text-app-text-dim transition-colors duration-150 hover:text-app-text hover:bg-white/[0.03]"
        >
          Eventos
          <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90 transition-transform duration-150 group-hover:translate-x-0.5" />
        </button>
        <InfoTooltip term="analisis_tecnico_titulo" />
      </div>

      {vista === 'grafico' ? (
        <>
          <div className="mb-3 flex items-center justify-between gap-2">
            <div role="group" aria-label="Período" className="flex gap-0.5 min-w-0 overflow-x-auto no-scrollbar">
              {PERIODOS.map(p => (
                <button
                  key={p} type="button" onClick={() => setPeriodo(p)} aria-pressed={periodo === p}
                  className={`shrink-0 h-9 min-w-[32px] px-1 rounded-lg font-mono text-caption font-semibold transition-[background-color,color,transform] duration-150 active:scale-95 ${
                    periodo === p ? 'bg-app-accent-soft text-app-accent' : 'text-app-text-dim hover:text-app-text hover:bg-white/5'
                  }`}
                >
                  {ETIQUETA_PERIODO[p] ?? p}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Velas" className="shrink-0 flex p-0.5 rounded-[10px] bg-app-surface border border-app-border">
              {INTERVALOS.map(i => (
                <button
                  key={i.value} type="button" aria-label={NOMBRE_INTERVALO[i.value]} title={NOMBRE_INTERVALO[i.value]}
                  aria-pressed={intervalo === i.value}
                  onClick={() => { setIntervalo(i.value); setHoverIndex(null) }}
                  className={`w-8 h-8 rounded-lg font-mono text-caption font-bold transition-[background-color,color,transform] duration-150 active:scale-95 ${
                    intervalo === i.value ? 'bg-app-surface-2 text-app-text' : 'text-app-text-dim hover:text-app-text'
                  }`}
                >
                  {i.label}
                </button>
              ))}
            </div>
          </div>

          <QueryBoundary
            isLoading={serieQuery.isLoading} error={serieQuery.error}
            onRetry={() => void serieQuery.refetch()} fallback={<Skeleton className="h-[320px] rounded-2xl" />}
          >
            {serie && serie.barras.length === 0 ? (
              <EmptyState
                ilustracion="lupa"
                title="Sin serie suficiente"
                description={
                  serie.advertencias.includes('un_solo_punto')
                    ? 'Este ticker recién se agregó: todavía tiene un solo precio registrado, no alcanza para graficar.'
                    : // El backend agrega el motivo concreto (sin fuente, escala descartada…) cuando
                      // lo tiene anotado; si no, queda el texto genérico de `sin_serie`.
                      textosAdvertenciasSerie(serie.advertencias).join(' ')
                }
              />
            ) : serie ? (
              <div ref={graficoRef} className="scroll-mt-16 -mx-1 rounded-2xl border border-app-border bg-app-surface p-2">
                <GraficoTecnico
                  barras={serie.barras} indicadores={serie.indicadores} activos={activos}
                  tieneVelas={serie.tiene_velas} tieneVolumen={serie.tiene_volumen}
                  moneda={monedaMostrada}
                  onToggleFullscreen={() => setFullscreen(true)}
                  zonas={zonasEnGrafico} editandoZonas={borrador !== null}
                  onArrastrarZona={arrastrarZona} edicionZonas={edicionZonas}
                  zonasVisibles={zonasVisibles} onToggleZonas={borrador ? undefined : () => setVerZonas(v => !v)}
                  onAbrirIndicadores={() => setIndicadoresAbierto(true)} onQuitarIndicador={quitarIndicadorPorClave}
                  {...propsOperaciones}
                  hoverIndex={hoverIndex} onHover={setHoverIndex}
                />
              </div>
            ) : null}
          </QueryBoundary>

          {serie && serie.barras.length > 0 && serie.advertencias.length > 0 && (
            <ul className="mt-2 text-label text-app-text-dim list-disc pl-4 space-y-0.5">
              {textosAdvertenciasSerie(serie.advertencias).map(texto => (
                <li key={texto}>{texto}</li>
              ))}
            </ul>
          )}

          {ticker && tieneGrafico && (
            <div className="mt-4">
              <LecturaGrafico
                lectura={lecturaQuery.data} cargando={lecturaQuery.isLoading} error={lecturaQuery.isError}
                onActivarFuerzaRelativa={verFuerzaRelativa ? undefined : () => setVerFuerzaRelativa(true)}
              />
            </div>
          )}

          {/* Las zonas se dibujan sobre el precio, así que el editor vive cerca del gráfico y no en
              una pantalla aparte: arrastrar el borde y escribir el número son dos vistas de lo
              mismo. Sólo con serie: una zona sobre un gráfico vacío no se puede ubicar. */}
          {ticker && tieneGrafico && (
            <div className="mt-3">
              {borrador ? (
                <EditorZonas
                  borrador={borrador} moneda={monedaMostrada} variante={variante}
                  precioReferencia={ultimoCierre}
                  onCambiar={setBorrador}
                  onGuardar={guardarZonas}
                  onCancelar={cancelarZonas}
                  guardando={guardarZonasMut.isPending}
                  error={errorZonas}
                />
              ) : (
                <div className="rounded-2xl border border-app-border bg-app-surface p-3.5">
                  <ResumenZonas
                    zonas={zonasGuardadas} variante={variante} moneda={monedaMostrada}
                    ultimoCierre={ultimoCierre}
                    onEditar={empezarAEditarZonas}
                  />
                </div>
              )}
            </div>
          )}

          {ticker && serie && tieneGrafico && (
            <div className="mt-3">
              <CalculadoraPosicion
                key={`${ticker}-${serie.variante}`} ticker={ticker} variante={serie.variante}
                onStopProvisorio={setStopProvisorio}
              />
            </div>
          )}

          {verOperaciones && puedeVerOperaciones && tieneGrafico && (
            <div className="mt-3">
              {operacionesQuery.isError ? (
                <p className="text-label text-app-neg">No se pudieron cargar tus operaciones de este ticker.</p>
              ) : misOperaciones ? (
                <ResumenOperaciones datos={misOperaciones} />
              ) : (
                <Skeleton className="h-16 w-full" />
              )}
            </div>
          )}

          {tieneGrafico && notasSerie.length > 0 && (
            <details className="mt-3 rounded-xl border border-app-border px-3.5">
              <summary className="min-h-[44px] flex items-center cursor-pointer text-caption font-semibold text-app-text-dim">
                {notasSerie.length === 1 ? '1 nota sobre esta serie' : `${notasSerie.length} notas sobre esta serie`}
              </summary>
              <ul className="pb-3 pl-4 list-disc text-label text-app-text-dim space-y-1">
                {notasSerie.map(t => <li key={t}>{t}</li>)}
              </ul>
            </details>
          )}

        </>
      ) : (
        ticker && (
          <SeccionEstrategias
            ticker={ticker} desde={desde} variante={variante} varianteElegida={varianteSel}
            moneda={monedaSerie}
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
            zonas={zonasEnGrafico} editandoZonas={borrador !== null}
            onArrastrarZona={arrastrarZona} edicionZonas={edicionZonas}
            zonasVisibles={zonasVisibles} onToggleZonas={borrador ? undefined : () => setVerZonas(v => !v)}
            onAbrirIndicadores={() => setIndicadoresAbierto(true)} onQuitarIndicador={quitarIndicadorPorClave}
            {...propsOperaciones}
            hoverIndex={hoverIndex} onHover={setHoverIndex}
          />
        </GraficoFullscreen>
      )}

      {/* Después de la pantalla completa: con la misma capa, el que va último en el DOM queda
          arriba, así el selector se abre sobre el gráfico a pantalla completa. */}
      <Modal open={indicadoresAbierto} onClose={() => setIndicadoresAbierto(false)} title="Indicadores">
        <div className="flex flex-col gap-2">
          <InfoTooltip term="analisis_tecnico_indicadores" label="Qué es un indicador" />
          <SelectorIndicadores
            activos={activos} onAgregar={agregarIndicador} onQuitar={quitarIndicador}
            onQuitarTipo={quitarTipoIndicador} onCambiarParam={cambiarParamIndicador}
            tieneVolumen={serie?.tiene_volumen ?? true}
          />
        </div>
      </Modal>
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
  ticker, desde, variante, varianteElegida, moneda, seriesDisponibles, onVariante, tieneVelas, tieneVolumen,
}: {
  ticker: string
  desde?: string
  /** La serie sobre la que corre el backtest ahora (la elegida, o si no, la de referencia). */
  variante: VarianteSerie
  /** Lo que el usuario fijó con el selector; `null` = no tocó nada y rige la de referencia. Es lo
   * que se guarda con la estrategia: sin esto, guardar la dejaría clavada en USD o en pesos. */
  varianteElegida: VarianteSerie | null
  moneda: string
  seriesDisponibles: { variante: VarianteSerie; moneda: string; mercado: string }[]
  onVariante: (v: VarianteSerie | null) => void
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
    // Sincronizar el toggle de variante con la que trae la estrategia guardada; `referencia` no
    // fija nada: rige la serie de referencia del ticker.
    onVariante(e.variante === 'referencia' ? null : e.variante)
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
    if (archivo.variante === 'referencia') {
      onVariante(null)
    } else if (seriesDisponibles.some(s => s.variante === archivo.variante)) {
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
      nombre: nombreActual || null, descripcion: descripcionActual, ticker: null,
      variante: varianteElegida ?? 'referencia',
    })
    descargarArchivo(nombreArchivoEstrategia(nombreActual || 'estrategia'), contenido, 'application/json')
  }

  async function guardar() {
    if (!dsl || !nombreParaGuardar.trim()) return
    const tickerAGuardar = reutilizable ? null : ticker
    const varianteAGuardar: VarianteEstrategia = varianteElegida ?? 'referencia'
    const cuerpo = {
      nombre: nombreParaGuardar, descripcion: descripcionActual, ticker: tickerAGuardar,
      tipo_preset: presetActual, definicion: dsl, variante: varianteAGuardar,
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
                          ? 'border-app-accent text-app-accent bg-app-accent-soft'
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
                    estrategiaActualId === e.id ? 'border-app-accent bg-app-accent-soft' : 'border-app-border bg-app-surface'
                  }`}
                >
                  <button onClick={() => cargarGuardada(e)} className={`font-semibold text-caption ${estrategiaActualId === e.id ? 'text-app-accent' : 'text-app-text-dim'}`}>
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
        <div className="bg-app-accent-soft border border-app-accent/40 rounded-xl px-3 py-2 text-caption text-app-text-dim">
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
