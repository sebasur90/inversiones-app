import axios from 'axios'

// Sin `timeout` una request colgada del backend (nginx permite hasta 300s de proxy_read_timeout)
// nunca rechaza: el skeleton gira para siempre, `retry` no se dispara y QueryBoundary jamás
// muestra el error. 30s cubre de sobra al endpoint legítimo más lento salvo el sync.
//
// `indexes: null`: axios serializa los arrays de query como `indicadores[]=SMA(50)` y FastAPI
// sólo lee `indicadores=SMA(50)&indicadores=RSI(14)` (el `[]` lo convierte en otro parámetro que
// nadie declara y la lista llega vacía). Sin esto el gráfico técnico pide indicadores y el backend
// devuelve `indicadores: {}`, así que nunca se dibujan.
const api = axios.create({
  baseURL: '/api', timeout: 30_000, paramsSerializer: { indexes: null },
})

// El sync recolecta de Google Sheets + IOL + yfinance y puede tardar varios minutos por diseño
// (ver DESARROLLO.md). Timeout propio y más holgado para no cortarlo antes de tiempo.
export const SYNC_TIMEOUT_MS = 300_000

export default api

// ---- Inversiones: Sincronización ----
export interface SyncIssueOut {
  tab: string
  fila: number | null
  campo: string | null
  regla: string
  severidad: string
  mensaje: string
  impacto: string
}

export interface SyncResult {
  movimientos: number
  instrumentos: number
  precios: number
  indices_mercado: number
  objetivos: number
  rebalanceo: number
  benchmarks: number
  configuracion: number
  health_score: number
  resultado: string
  duration_ms: number
  timestamp: string
  issues: SyncIssueOut[]
}

export interface SyncRunResumenOut {
  id: number
  timestamp: string
  duration_ms: number
  filas_procesadas: number
  filas_validas: number
  filas_advertencia: number
  filas_error: number
  health_score: number
  resultado: string
}

export interface HistorialSyncItem {
  timestamp: string
  health_score: number
  resultado: string
  filas_advertencia: number
  filas_error: number
}

export interface ReglaRecurrenteItem {
  regla: string
  tab: string
  severidad: string
  mensaje_muestra: string
  apariciones: number
  en_ultimo_sync: boolean
}

export interface CalidadDatosOut {
  ultimo_sync: SyncRunResumenOut | null
  issues: SyncIssueOut[]
  issues_por_tab: Record<string, SyncIssueOut[]>
  historial: HistorialSyncItem[]
  reglas_recurrentes: ReglaRecurrenteItem[]
  syncs_en_ventana: number
}

export interface CarteraInfo {
  nombre: string
  ultimo_sync: string | null
}

export interface WatchlistItemOut {
  ticker: string
  nombre: string
  tipo_instrumento: string
  mercado: string
  moneda: string
  pais: string | null
  sector: string | null
  precio_actual: number | null
  fecha_precio: string | null
  moneda_precio: string | null
  fuente_precio: string | null
  precio_objetivo: number | null
  pct_a_objetivo: number | null
  en_zona: boolean | null
  en_cartera: boolean
  notas: string | null
  agregado_en: string | null
}

/** Un instrumento del catálogo de IOL: el universo que se puede agregar a la watchlist. */
export interface CatalogoInstrumentoOut {
  simbolo: string
  descripcion: string
  tipo: string
  moneda: string
  mercado: string
  paneles: string[]
}

export interface CatalogoBusquedaOut {
  /** Cuántos matchean la búsqueda + el tipo, antes del límite. */
  total: number
  /** Conteo por familia sobre la búsqueda SIN el filtro de tipo: es lo que muestran los chips. */
  conteos_por_tipo: Record<string, number>
  items: CatalogoInstrumentoOut[]
}

export interface InversionesResumen {
  valor_actual_usd: number
  valor_actual_ars: number
  total_invertido_usd: number
  total_invertido_ars: number
  total_invertido_ars_real: number | null
  ingresos_recibidos_usd: number
  ingresos_recibidos_ars: number
  rendimiento_simple_usd: number | null
  rendimiento_simple_ars: number | null
  rendimiento_simple_ars_real: number | null
  xirr_usd: number | null
  xirr_ars: number | null
  xirr_ars_real: number | null
  // XIRR reexpresado como retorno acumulado del período (comparable contra el TWR).
  xirr_usd_periodo: number | null
  xirr_ars_periodo: number | null
  xirr_ars_real_periodo: number | null
  dias_periodo: number
  twr_usd: number | null
  twr_ars: number | null
  twr_ars_real: number | null
  twr_usd_bruto: number | null
  twr_ars_bruto: number | null
  valor_benchmark_usd_ars: number | null
  tiene_precios_desactualizados: boolean
}

export interface ExposicionItem {
  etiqueta: string
  valor_usd: number
  valor_ars: number
  porcentaje: number
}

export interface ExposicionEje {
  eje: string
  items: ExposicionItem[]
}

export interface ExposicionOut {
  ejes: ExposicionEje[]
}

export interface DescomposicionNodo {
  clave: string
  etiqueta: string
  nivel: string
  valor_usd: number
  valor_ars: number
  porcentaje: number
  porcentaje_padre: number
  instrumentos: number
  sin_clasificar: boolean
  tipo_instrumento: string | null
  nombre: string | null
  hijos: DescomposicionNodo[]
}

export interface DescomposicionOut {
  niveles: string[]
  total_usd: number
  total_ars: number
  instrumentos: number
  raiz: DescomposicionNodo[]
  posiciones_sin_precio: string[]
}

export interface RebalanceoItem {
  etiqueta: string
  porcentaje_actual: number
  porcentaje_objetivo: number
  valor_actual_usd: number
  valor_actual_ars: number
  valor_objetivo_usd: number
  valor_objetivo_ars: number
  delta_pp: number
  delta_valor_usd: number
  delta_valor_ars: number
}

export interface RebalanceoEje {
  eje: string
  total_usd: number
  total_ars: number
  items: RebalanceoItem[]
  sin_objetivo: ExposicionItem[]
}

export interface RebalanceoOut {
  ejes: RebalanceoEje[]
}

export interface ConfiguracionCartera {
  cartera: string | null
  benchmark: string | null
  rendimiento_objetivo: number | null
  peso_maximo: number | null
  peso_minimo: number | null
  tolerancia: number
}

export type ModoSimulacion = 'completo' | 'solo_aportes'

export interface RebalanceoSimulacionRequest {
  eje: string
  modo: ModoSimulacion
  aporte_usd: number
  tasa_comision_pct: number | null
}

export interface PropuestaRebalanceoItem {
  tipo: 'ticker' | 'categoria_sin_instrumento'
  posicion: string | null
  categoria: string
  peso_actual_pct: number
  peso_objetivo_pct: number
  delta_pp: number
  valor_actual_usd: number
  valor_objetivo_usd: number
  importe_sugerido_usd: number
  accion: 'comprar' | 'vender' | 'mantener'
  necesidad: 'necesario' | 'opcional'
  comision_estimada_usd: number
  motivo: string
}

export interface RebalanceoSimulacionOut {
  eje: string
  modo: ModoSimulacion
  total_usd: number
  aporte_usd: number
  tasa_comision_pct: number
  tolerancia_pp: number
  peso_maximo_pp: number | null
  peso_minimo_pp: number | null
  items: PropuestaRebalanceoItem[]
  total_comision_estimada_usd: number
  total_a_comprar_usd: number
  total_a_vender_usd: number
  sobrante_usd: number
}

export interface MovimientoInversion {
  id: number
  fecha: string
  cartera: string
  ticker: string
  tipo_movimiento: string
  cantidad: number | null
  precio: number
  moneda: string
  comision: number
}

export interface RendimientoPorTickerItem {
  ticker: string
  nombre: string
  tipo_instrumento: string
  mercado: string
  moneda: string
  pais: string | null
  sector: string | null
  cantidad_actual: number
  precio_promedio: number
  precio_actual: number
  valor_invertido_usd: number
  valor_actual_usd: number
  valor_invertido_ars: number
  valor_actual_ars: number
  rendimiento_simple_usd: number | null
  rendimiento_simple_ars: number | null
  rendimiento_simple_ars_real: number | null
  precio_promedio_ars_ajustado_cer: number | null
  precio_actual_ars_ajustado_cer: number | null
  objetivo_modo: string | null
  objetivo_valor: number | null
  precio_objetivo: number | null
  pct_a_objetivo: number | null
  objetivo_alcanzado: boolean | null
  stop_loss_modo: string | null
  stop_loss_valor: number | null
  precio_stop_loss: number | null
  pct_a_stop_loss: number | null
  stop_loss_disparado: boolean | null
}

const carteraPath = (cartera: string | null) =>
  cartera ? `/inversiones/carteras/${encodeURIComponent(cartera)}` : '/inversiones/consolidado'

export const syncInversiones = () =>
  api.post<SyncResult>('/inversiones/sync', undefined, { timeout: SYNC_TIMEOUT_MS }).then(r => r.data)

export const getCalidadDatos = () =>
  api.get<CalidadDatosOut>('/inversiones/calidad-datos').then(r => r.data)

export const getWatchlist = () =>
  api.get<WatchlistItemOut[]>('/inversiones/watchlist').then(r => r.data)

export const buscarCatalogo = (q: string, tipo: string, limite = 100) =>
  api.get<CatalogoBusquedaOut>('/inversiones/catalogo', { params: { q, tipo, limite } })
    .then(r => r.data)

export const agregarAWatchlist = (body: { ticker: string; objetivo?: number | null; notas?: string | null }) =>
  api.post<WatchlistItemOut>('/inversiones/watchlist', body).then(r => r.data)

export const actualizarWatchlist = (ticker: string, body: { objetivo?: number | null; notas?: string | null }) =>
  api.put<WatchlistItemOut>(`/inversiones/watchlist/${encodeURIComponent(ticker)}`, body).then(r => r.data)

export const eliminarDeWatchlist = (ticker: string) =>
  api.delete<void>(`/inversiones/watchlist/${encodeURIComponent(ticker)}`).then(r => r.data)

export const refrescarPrecioWatchlist = (ticker: string) =>
  api.post<WatchlistItemOut>(`/inversiones/watchlist/${encodeURIComponent(ticker)}/precio`)
    .then(r => r.data)

export const getCarterasInversion = () =>
  api.get<CarteraInfo[]>('/inversiones/carteras').then(r => r.data)

export const getResumenInversiones = (cartera: string | null) =>
  api.get<InversionesResumen>(`${carteraPath(cartera)}/resumen`).then(r => r.data)

export const getExposicionInversiones = (cartera: string | null) =>
  api.get<ExposicionOut>(`${carteraPath(cartera)}/exposicion`).then(r => r.data)

export const getDescomposicion = (cartera: string | null) =>
  api.get<DescomposicionOut>(`${carteraPath(cartera)}/descomposicion`).then(r => r.data)

export const getRebalanceoInversiones = (cartera: string | null) =>
  api.get<RebalanceoOut>(`${carteraPath(cartera)}/rebalanceo`).then(r => r.data)

export const getConfiguracionCartera = (cartera: string | null) =>
  api.get<ConfiguracionCartera>(`${carteraPath(cartera)}/configuracion`).then(r => r.data)

export const simularRebalanceo = (cartera: string | null, body: RebalanceoSimulacionRequest) =>
  api.post<RebalanceoSimulacionOut>(`${carteraPath(cartera)}/rebalanceo/simular`, body).then(r => r.data)

export const getMovimientosInversion = (params: { cartera?: string; ticker?: string }) =>
  api.get<MovimientoInversion[]>('/inversiones/movimientos', { params }).then(r => r.data)

export const getRendimientoPorTicker = (cartera: string | null) =>
  api.get<RendimientoPorTickerItem[]>(`${carteraPath(cartera)}/rendimiento-por-ticker`).then(r => r.data)

export interface EvolucionPunto {
  fecha: string
  valor_usd: number
  valor_ars: number
  valor_ars_real: number | null
  capital_aportado_usd: number
  capital_aportado_ars: number
  capital_aportado_ars_real: number | null
}

export interface EvolucionOut {
  puntos: EvolucionPunto[]
}

export const getEvolucionInversiones = (cartera: string | null, desde?: string) =>
  api.get<EvolucionOut>(`${carteraPath(cartera)}/evolucion`, { params: desde ? { desde } : undefined }).then(r => r.data)

export interface PatrimonioPunto {
  fecha: string
  valor_usd: number
  valor_ars: number
  valor_ars_real: number | null
  aportes_acumulados_usd: number
  aportes_acumulados_ars: number
  aportes_acumulados_ars_real: number | null
  dividendos_acumulados_usd: number
  dividendos_acumulados_ars: number
  dividendos_acumulados_ars_real: number | null
  otros_ajustes_acumulados_usd: number
  otros_ajustes_acumulados_ars: number
  otros_ajustes_acumulados_ars_real: number | null
  ganancia_usd: number
  ganancia_ars: number
  ganancia_ars_real: number | null
}

export interface PatrimonioHistoryOut {
  puntos: PatrimonioPunto[]
}

export interface PatrimonioMaximoOut {
  valor_usd: number | null
  valor_ars: number | null
  valor_ars_real: number | null
  fecha: string | null
  fecha_ars: string | null
  fecha_ars_real: string | null
  valor_actual_usd: number | null
  valor_actual_ars: number | null
  valor_actual_ars_real: number | null
  drawdown_usd: number | null
  drawdown_ars: number | null
  drawdown_ars_real: number | null
}

export interface PatrimonioDescomposicionOut {
  aportes_usd: number
  aportes_ars: number
  aportes_ars_real: number | null
  rendimiento_usd: number
  rendimiento_ars: number
  rendimiento_ars_real: number | null
  dividendos_usd: number
  dividendos_ars: number
  dividendos_ars_real: number | null
  otros_ajustes_usd: number
  otros_ajustes_ars: number
  otros_ajustes_ars_real: number | null
}

export interface PatrimonioSummaryOut {
  maximo: PatrimonioMaximoOut
  descomposicion: PatrimonioDescomposicionOut
}

export const getPatrimonioHistory = (cartera: string | null, desde?: string) =>
  api.get<PatrimonioHistoryOut>(`${carteraPath(cartera)}/patrimonio/history`, { params: desde ? { desde } : undefined }).then(r => r.data)

export const getPatrimonioSummary = (cartera: string | null, desde?: string) =>
  api.get<PatrimonioSummaryOut>(`${carteraPath(cartera)}/patrimonio/summary`, { params: desde ? { desde } : undefined }).then(r => r.data)

export interface RendimientoMensualItem {
  anio: number
  mes: number
  twr_ars: number | null
  twr_usd: number | null
  en_curso: boolean
}

export interface RendimientoAnualItem {
  anio: number
  twr_ars: number | null
  twr_usd: number | null
  en_curso: boolean
}

export interface RendimientoMensualOut {
  meses: RendimientoMensualItem[]
  anios: RendimientoAnualItem[]
}

export const getRendimientoMensual = (cartera: string | null) =>
  api.get<RendimientoMensualOut>(`${carteraPath(cartera)}/rendimiento-mensual`).then(r => r.data)

export interface PrecioPunto {
  fecha: string
  precio: number
  moneda: string
}

export interface PrecioSerieOut {
  ticker: string
  puntos: PrecioPunto[]
}

export const getPreciosTicker = (ticker: string, dias = 365) =>
  api.get<PrecioSerieOut>(`/inversiones/ticker/${encodeURIComponent(ticker)}/precios`, { params: { dias } }).then(r => r.data)

export interface PrecioHistoricoPunto {
  fecha: string
  precio_nominal: number
  precio_usd: number | null
  precio_cer: number | null
}

export interface PrecioHistoricoOut {
  ticker: string
  moneda: string
  puntos: PrecioHistoricoPunto[]
}

export interface TickerConPrecio {
  ticker: string
  nombre: string
  moneda: string
}

export const getTickersConPrecios = () =>
  api.get<TickerConPrecio[]>('/inversiones/tickers-con-precios').then(r => r.data)

export const getPreciosHistoricos = (ticker: string, dias = 3650) =>
  api.get<PrecioHistoricoOut>(`/inversiones/ticker/${encodeURIComponent(ticker)}/precios-historicos`, { params: { dias } }).then(r => r.data)

// --- Indicadores macro (CER/MEP) ---

export interface IndiceMercadoPunto {
  fecha: string
  cer: number | null
  mep: number | null
  riesgo_pais: number | null
}

export interface InflacionMensualPunto {
  fecha: string
  valor_pct: number
}

export interface IndicesMercadoOut {
  puntos: IndiceMercadoPunto[]
  variacion_cer_pct: number | null
  variacion_mep_pct: number | null
  variacion_riesgo_pais_pct: number | null
  inflacion_mensual: InflacionMensualPunto[]
}

export const getIndicesMercado = (dias = 3650) =>
  api.get<IndicesMercadoOut>('/inversiones/indices-mercado', { params: { dias } }).then(r => r.data)

// --- Vencimientos ---

export interface VencimientoItem {
  ticker: string
  nombre: string
  fecha_vencimiento: string
  dias_restantes: number
  vencido: boolean
  cantidad_actual: number
  // null si el instrumento no tiene cotización cargada
  valor_actual_usd: number | null
  valor_actual_ars: number | null
  moneda: string
  // Métricas de bono estimadas sobre el flujo de caja inferido. null si falta historial/precio.
  tir_vencimiento: number | null      // TIR anual (decimal) al vencimiento
  duration_macaulay: number | null    // años
  duration_modificada: number | null  // años
  paridad: number | null              // precio / valor técnico (base par = 1)
  par_asumido: number | null          // 1 | 100 si la escala se infirió del precio; null si es dato duro
  valor_tecnico: number | null        // por unidad, en moneda_metricas
  interes_corrido: number | null      // por unidad
  valor_residual: number | null       // por unidad, base par = 1
  moneda_metricas: string | null
  metricas_estimadas: boolean
  metricas_nota: string | null
}

export interface VencimientoAnioItem {
  anio: number
  valor_usd: number
  valor_ars: number
  pct_cartera_usd: number | null
  pct_cartera_ars: number | null
  cantidad_instrumentos: number
  instrumentos_sin_valuar: number
  tickers: string[]
}

export interface VencimientosOut {
  generado: string
  items: VencimientoItem[]
  por_anio: VencimientoAnioItem[]
  cartera_valor_usd: number
  cartera_valor_ars: number
}

export const getVencimientos = (cartera: string | null) =>
  api.get<VencimientosOut>(`${carteraPath(cartera)}/vencimientos`).then(r => r.data)

// --- Flujo de caja proyectado (renta fija) ---

export interface FlujoCajaCobroDetalle {
  ticker: string
  nombre: string
  tipo: 'cupon' | 'amortizacion'
  moneda: string
  monto_nativo: number
  monto_usd: number
  monto_ars: number
}

export interface FlujoCajaMes {
  periodo: string
  cupones_usd: number
  cupones_ars: number
  amortizaciones_usd: number
  amortizaciones_ars: number
  total_usd: number
  total_ars: number
  detalle: FlujoCajaCobroDetalle[]
}

export interface FlujoCajaProximoCobro {
  fecha: string
  tipo: 'cupon' | 'amortizacion'
  monto_usd: number
  monto_ars: number
}

export interface FlujoCajaInstrumento {
  ticker: string
  nombre: string
  moneda: string
  cantidad_actual: number
  fecha_vencimiento: string
  periodicidad_meses: number | null
  periodicidad_label: string | null
  cupon_por_unidad: number | null
  confianza: 'alta' | 'media' | 'baja' | null
  metodo_capital: 'bullet' | 'amortizacion_inferida' | 'sin_estimacion'
  amort_historicas: number
  amort_futuras: number
  cobros_proyectados: number
  proximo_cobro: FlujoCajaProximoCobro | null
  total_proyectado_usd: number
  total_proyectado_ars: number
  notas: string[]
}

export interface FlujoCajaSinProyeccion {
  ticker: string
  nombre: string
  fecha_vencimiento: string
  motivo: string
}

export interface FlujoCajaProyectadoOut {
  horizonte_meses: number
  generado: string
  total_cupones_usd: number
  total_cupones_ars: number
  total_amortizaciones_usd: number
  total_amortizaciones_ars: number
  total_usd: number
  total_ars: number
  meses: FlujoCajaMes[]
  instrumentos: FlujoCajaInstrumento[]
  sin_proyeccion: FlujoCajaSinProyeccion[]
}

export const getFlujoCajaProyectado = (cartera: string | null, meses = 24) =>
  api
    .get<FlujoCajaProyectadoOut>(`${carteraPath(cartera)}/flujo-caja-proyectado`, { params: { meses } })
    .then(r => r.data)

// --- Comisiones ---

export interface ComisionPorCarteraItem {
  etiqueta: string
  total_usd: number
  total_ars: number
}

export interface ComisionPorTickerItem {
  ticker: string
  nombre: string
  total_usd: number
  total_ars: number
}

export interface ComisionPeriodoItem {
  periodo: string
  total_usd: number
  total_ars: number
}

export interface ComisionesOut {
  total_usd: number
  total_ars: number
  movimientos_con_comision: number
  por_cartera: ComisionPorCarteraItem[]
  por_ticker: ComisionPorTickerItem[]
  por_mes: ComisionPeriodoItem[]
  por_anio: ComisionPeriodoItem[]
}

export const getComisiones = (cartera: string | null) =>
  api.get<ComisionesOut>(`${carteraPath(cartera)}/comisiones`).then(r => r.data)

// --- Ritmo de aportes (espejo de schemas.RitmoAportesOut) ---

export interface AporteMesItem {
  mes: string // "YYYY-MM"
  neto_usd: number
  compras_usd: number
  salidas_usd: number
  en_curso: boolean
  futuro: boolean
  con_aporte: boolean
  promedio_movil_3_usd: number | null
  // Objetivo vigente ese mes. `null` = no había objetivo vigente, que no es lo mismo que
  // haberlo incumplido.
  objetivo_usd: number | null
  cumplimiento_pct: number | null
  cumple_objetivo: boolean | null
}

export interface AporteComparacion {
  referencia_usd: number
  delta_usd: number
  delta_pct: number | null
  delta_proyectado_usd: number | null
  delta_proyectado_pct: number | null
}

export interface AporteEsteMes {
  mes: string
  neto_usd: number
  compras_usd: number
  salidas_usd: number
  dia: number
  dias_mes: number
  dias_restantes: number
  proyeccion_usd: number
  proyeccion_fiable: boolean
  es_record_parcial: boolean
  vs_mes_anterior: AporteComparacion | null
  vs_promedio_3: AporteComparacion | null
  vs_promedio_6: AporteComparacion | null
  vs_promedio_12: AporteComparacion | null
  vs_mismo_mes_anio_anterior: AporteComparacion | null
}

export type AporteProyeccionClave = 'este_mes' | 'promedio_3' | 'promedio_ytd'

export interface AporteProyeccionAnual {
  clave: AporteProyeccionClave
  etiqueta: string
  ritmo_mensual_usd: number | null
  total_fin_anio_usd: number | null
}

export interface AporteAnioEnCurso {
  anio: number
  ytd_usd: number
  meses_cerrados: number
  meses_restantes: number
  promedio_mensual_ytd_usd: number | null
  anio_anterior_total_usd: number | null
  vs_mismo_periodo_anio_anterior: AporteComparacion | null
  proyecciones: AporteProyeccionAnual[]
}

export interface AporteRacha {
  meses: number
  desde: string | null
  hasta: string | null
  incluye_mes_en_curso: boolean
}

export interface AporteRachas {
  aportando_actual: AporteRacha
  aportando_record: AporteRacha
  sin_aportar_actual: number
  sobre_promedio_12_actual: number | null
  direccion: 'subiendo' | 'bajando' | 'ninguna'
  direccion_meses: number
  meses_sin_aportar_ultimos_12: number
  meses_considerados_ultimos_12: number
}

export interface AporteMesRef {
  mes: string
  neto_usd: number
}

export interface AporteNivel {
  nivel: 'bien' | 'atencion' | 'riesgo'
  etiqueta: string
}

export interface AporteEstadisticas {
  meses_historia: number
  meses_con_aporte: number
  meses_con_retiro: number
  total_neto_usd: number
  total_compras_usd: number
  total_salidas_usd: number
  promedio_usd: number | null
  mediana_usd: number | null
  desvio_usd: number | null
  coef_variacion: number | null
  constancia: AporteNivel | null
  promedio_3_usd: number | null
  promedio_6_usd: number | null
  promedio_12_usd: number | null
  mejor_mes: AporteMesRef | null
  peor_mes: AporteMesRef | null
  mejor_mes_anio: AporteMesRef | null
  peor_mes_anio: AporteMesRef | null
}

export type AporteEstado = 'arrancando' | 'acelerando' | 'sostenido' | 'frenando' | 'parado'

export interface AporteEstadoRitmo {
  estado: AporteEstado
  etiqueta: string
  nivel: 'bien' | 'atencion' | 'riesgo'
  detalle: string
  tendencia_3v3_pct: number | null
  tendencia_6v6_pct: number | null
  promedio_3_usd: number | null
  promedio_3_anterior_usd: number | null
  promedio_6_usd: number | null
  promedio_6_anterior_usd: number | null
}

export interface AporteAnioItem {
  anio: number
  total_usd: number
  compras_usd: number
  salidas_usd: number
  promedio_mensual_usd: number | null
  meses_con_aporte: number
  meses_en_rango: number
  var_vs_anio_anterior_pct: number | null
  en_curso: boolean
  mejor_mes: AporteMesRef | null
}

export interface AporteAnioRef {
  anio: number
  total_usd: number
}

export interface AporteHito {
  clave: string
  titulo: string
  descripcion: string
  fecha: string
  reciente: boolean
}

export interface AporteProximoHito {
  clave: string
  titulo: string
  unidad: 'usd' | 'meses'
  valor_objetivo: number
  valor_actual: number
  falta: number
  progreso_pct: number
}

export interface AporteMensaje {
  clave: string
  tono: 'positivo' | 'neutro' | 'negativo'
  titulo: string
  detalle: string
}

// --- Progreso: niveles, objetivo, logros, récords, misión
//     (espejo de schemas.ProgresoAportes) ---

export interface AporteNivelRequisito {
  clave: string
  etiqueta: string
  actual: number
  objetivo: number
  cumple: boolean
}

export interface AporteNivelSiguiente {
  clave: string
  nombre: string
  emoji: string
  requisitos: AporteNivelRequisito[]
  progreso_pct: number
  falta_texto: string
}

export interface AporteNivelConstancia {
  clave: string
  nombre: string
  emoji: string
  orden: number
  total_niveles: number
  motivos: string[]
  siguiente: AporteNivelSiguiente | null
  sello_objetivo: { etiqueta: string; meses: number } | null
}

export interface AporteObjetivoMesActual {
  objetivo_usd: number
  aportado_usd: number
  cumplimiento_pct: number | null
  restante_usd: number
  cumplido: boolean
  vigente: boolean
  dias_restantes: number
  ritmo_necesario_diario_usd: number | null
  ritmo_necesario_semanal_usd: number | null
  alcanzable_al_ritmo_actual: boolean
}

export interface AporteObjetivo {
  configurado: boolean
  monto_usd: number | null
  /** Mes desde el que se mide de hecho (con `retroactivo`, el primero del historial). */
  vigente_desde: string | null
  /** Mes en que se creó el objetivo: a él se vuelve si se desmarca la retroactividad. */
  fijado_en: string | null
  retroactivo: boolean
  sugerido_usd: number | null
  sugerido_origen: string | null
  mes_actual: AporteObjetivoMesActual | null
  meses_evaluados: number | null
  meses_cumplidos: number | null
  meses_cumplidos_pct: number | null
  racha_cumplimiento: number | null
  record_cumplimiento: number | null
}

export interface AporteLogro {
  clave: string
  titulo: string
  descripcion: string
  categoria: 'inicio' | 'constancia' | 'capital' | 'mejora' | 'objetivo'
  emoji: string
  unidad: 'meses' | 'usd' | 'conteo'
  objetivo: number
  actual: number | null
  progreso_pct: number | null
  desbloqueado: boolean
  fecha: string | null
  bloqueado_por_falta_objetivo: boolean
}

export interface AporteRecords {
  mayor_aporte_mensual: AporteMesRef | null
  mejor_racha: { meses: number; desde: string | null; hasta: string | null }
  mayor_aporte_anual: { anio: number; total_usd: number } | null
  mayor_promedio_mensual_anual: { anio: number; promedio_usd: number } | null
  mas_meses_cumpliendo_objetivo: { anio: number; meses: number } | null
}

export interface AporteEvolucion {
  clave: 'sube' | 'baja' | 'estable' | 'sin_historial'
  frase: string
  delta_pct: number | null
  promedio_actual_usd: number | null
  promedio_anterior_usd: number | null
}

export interface AporteHorizonte {
  anios: number
  meses: number
  total_usd: number
  extra_usd: number | null
}

export interface AporteEscenarioAumento {
  clave: string
  delta_mensual_usd: number
  ritmo_resultante_usd: number
  horizontes: AporteHorizonte[]
}

export interface AporteProyeccionRitmo {
  ritmo_mensual_usd: number | null
  origen: 'promedio_12' | 'promedio_6' | 'promedio_3' | 'promedio_historico' | 'insuficiente'
  horizontes: AporteHorizonte[]
  escenarios_aumento: AporteEscenarioAumento[]
  disclaimer: string
}

export interface AporteMision {
  clave: string
  titulo: string
  detalle: string
  unidad: 'meses' | 'usd' | 'conteo'
  actual: number
  objetivo: number
  progreso_pct: number
  por_que: string
}

export interface ProgresoAportes {
  nivel: AporteNivelConstancia
  objetivo: AporteObjetivo
  logros: AporteLogro[]
  records: AporteRecords
  evolucion: AporteEvolucion
  proyeccion_ritmo: AporteProyeccionRitmo
  mision: AporteMision | null
}

export interface RitmoAportesOut {
  estado: 'ok' | 'sin_datos'
  hoy: string
  primer_mes: string | null
  movimientos_omitidos_sin_mep: number
  serie_mensual: AporteMesItem[]
  por_anio: AporteAnioItem[]
  mejor_anio: AporteAnioRef | null
  este_mes: AporteEsteMes | null
  anio_en_curso: AporteAnioEnCurso | null
  rachas: AporteRachas | null
  estadisticas: AporteEstadisticas | null
  estado_ritmo: AporteEstadoRitmo | null
  hitos_alcanzados: AporteHito[]
  proximos_hitos: AporteProximoHito[]
  mensajes: AporteMensaje[]
  progreso: ProgresoAportes | null
}

export const getRitmoAportes = (cartera: string | null) =>
  api.get<RitmoAportesOut>(`${carteraPath(cartera)}/aportes/ritmo`).then(r => r.data)

// --- Objetivo de aporte mensual ---

export interface ObjetivoAporteOut {
  cartera: string | null
  monto_usd: number
  vigente_desde: string
  retroactivo: boolean
}

/** `null` cuando todavía no hay objetivo configurado (el backend responde 204, sin cuerpo). */
export const getObjetivoAporte = (cartera: string | null) =>
  api.get<ObjetivoAporteOut | ''>(`${carteraPath(cartera)}/aportes/objetivo`)
    .then(r => (r.status === 204 || !r.data ? null : (r.data as ObjetivoAporteOut)))

export const guardarObjetivoAporte = (cartera: string | null, monto_usd: number, retroactivo = false) =>
  api.put<ObjetivoAporteOut>(`${carteraPath(cartera)}/aportes/objetivo`, { monto_usd, retroactivo })
    .then(r => r.data)

export const eliminarObjetivoAporte = (cartera: string | null) =>
  api.delete<void>(`${carteraPath(cartera)}/aportes/objetivo`).then(() => undefined)

// --- P&L Realizado vs No Realizado ---

export interface PnlConsolidado {
  realizado_usd: number
  no_realizado_usd: number
  ingresos_usd: number
  total_usd: number
  realizado_ars: number
  no_realizado_ars: number
  ingresos_ars: number
  total_ars: number
  realizado_ars_real: number | null
  no_realizado_ars_real: number | null
  ingresos_ars_real: number | null
  total_ars_real: number | null
}

export interface PnlPorTickerItem {
  ticker: string
  nombre: string
  realizado_usd: number
  no_realizado_usd: number | null
  ingresos_usd: number
  total_usd: number | null
  realizado_ars: number
  no_realizado_ars: number | null
  ingresos_ars: number
  total_ars: number | null
}

export interface PnlRealizadoNoRealizadoOut {
  consolidado: PnlConsolidado
  por_ticker: PnlPorTickerItem[]
}

export const getPnlRealizadoNoRealizado = (cartera: string | null) =>
  api.get<PnlRealizadoNoRealizadoOut>(`${carteraPath(cartera)}/pnl-realizado`).then(r => r.data)

// --- Vista fiscal por año ---

export interface VistaFiscalTickerItem {
  ticker: string
  nombre: string
  realizado_usd: number
  realizado_ars: number
  ingresos_usd: number
  ingresos_ars: number
  comisiones_usd: number
  comisiones_ars: number
}

export interface VistaFiscalAnioItem {
  anio: number
  realizado_usd: number
  realizado_ars: number
  ingresos_usd: number
  ingresos_ars: number
  comisiones_usd: number
  comisiones_ars: number
  resultado_usd: number
  resultado_ars: number
  por_ticker: VistaFiscalTickerItem[]
}

export interface VistaFiscalTotal {
  realizado_usd: number
  realizado_ars: number
  ingresos_usd: number
  ingresos_ars: number
  comisiones_usd: number
  comisiones_ars: number
  resultado_usd: number
  resultado_ars: number
}

export interface VistaFiscalPorAnioOut {
  por_anio: VistaFiscalAnioItem[]
  total: VistaFiscalTotal
}

export const getVistaFiscalPorAnio = (cartera: string | null) =>
  api.get<VistaFiscalPorAnioOut>(`${carteraPath(cartera)}/vista-fiscal`).then(r => r.data)

// --- Objetivos de Inversión ---

export interface AportePunto {
  mes: string
  aportes_netos_acumulados: number
}

export interface AportesHistoricosOut {
  curva: AportePunto[]
  valor_actual_usd: number
}

export interface ObjetivoInversion {
  id: number
  cartera: string
  nombre: string
  icono: string
  monto_usd: number
  fecha_limite: string
  valor_actual_usd: number
  aporte_mensual_promedio_usd: number
  aporte_mensual_necesario_usd: number | null
  aporte_mensual_esperado_usd: number | null
  meses_restantes: number
  proyeccion_usd: number
  alcanzable: boolean
  deficit_usd: number
  desviacion_usd: number | null
  desviacion_pct: number | null
  adelantado: boolean | null
  aportado_a_la_fecha_usd: number | null
  esperado_a_la_fecha_usd: number | null
}

export const getObjetivoInversion = async (cartera: string): Promise<ObjetivoInversion | null> => {
  try {
    const response = await api.get<ObjetivoInversion>(`/inversiones/carteras/${encodeURIComponent(cartera)}/objetivo`)
    return response.data
  } catch (err: any) {
    if (err.response?.status === 404) {
      return null
    }
    throw err
  }
}

export const getAportesHistoricos = (cartera: string) =>
  api.get<AportesHistoricosOut>(`/inversiones/carteras/${encodeURIComponent(cartera)}/aportes-historicos`).then(r => r.data)

// --- Riesgo ---

export type MonedaRiesgo = 'ars_nominal' | 'ars_real' | 'usd'

export interface DrawdownPunto {
  fecha: string
  drawdown: number
}

export interface DrawdownOut {
  estado: 'ok' | 'datos_insuficientes'
  actual: number | null
  maximo: number | null
  fecha_pico: string | null
  fecha_valle: string | null
  en_recuperacion: boolean | null
  tiempo_recuperacion_meses: number | null
  serie: DrawdownPunto[]
}

export interface VolatilidadOut {
  estado: 'ok' | 'datos_insuficientes'
  mensual: number | null
  anualizada: number | null
  n_obs: number
}

export interface SharpeOut {
  estado: 'ok' | 'datos_insuficientes' | 'sin_benchmark'
  valor: number | null
  benchmark: string | null
  n_obs: number
}

export interface SortinoOut {
  estado: 'ok' | 'datos_insuficientes'
  valor: number | null
  n_obs: number
}

export interface CalmarOut {
  estado: 'ok' | 'datos_insuficientes'
  valor: number | null
  retorno_anualizado: number | null
}

export interface PeriodoRetorno {
  anio: number
  mes: number
  retorno: number
}

export interface FrecuenciaOut {
  estado: 'ok' | 'datos_insuficientes'
  pct_positivos: number | null
  pct_negativos: number | null
  n_obs: number
}

export interface RiesgoOut {
  frecuencia: string
  moneda: MonedaRiesgo
  benchmark_usado: string | null
  n_meses_historia: number
  drawdown: DrawdownOut
  volatilidad: VolatilidadOut
  sharpe: SharpeOut
  sortino: SortinoOut
  calmar: CalmarOut
  benchmark_retorno_anualizado: number | null
  mejores_periodos: PeriodoRetorno[]
  peores_periodos: PeriodoRetorno[]
  frecuencia_positivos_negativos: FrecuenciaOut
}

export const getBenchmarksDisponibles = () =>
  api.get<string[]>('/inversiones/benchmarks').then(r => r.data)

export const getRiesgo = (cartera: string | null, moneda: MonedaRiesgo, benchmark: string | null) =>
  api
    .get<RiesgoOut>(`${carteraPath(cartera)}/riesgo`, { params: { moneda, benchmark: benchmark ?? undefined } })
    .then(r => r.data)

export interface MetricaRelativa {
  estado: string
  valor: number | null
  n_obs: number
}

export interface PerformanceRelativaPunto {
  fecha: string
  indice_cartera: number
  indice_benchmark: number
}

export interface PerformanceRelativaOut {
  estado: string
  moneda: string
  benchmark_usado: string | null
  periodo_desde: string | null
  periodo_hasta: string | null
  n_meses_historia: number
  retorno_cartera_pct: number | null
  retorno_benchmark_pct: number | null
  delta_pp: number | null
  costo_oportunidad_pp: number | null
  exceso_retorno: MetricaRelativa
  alpha: MetricaRelativa
  beta: MetricaRelativa
  tracking_error: MetricaRelativa
  information_ratio: MetricaRelativa
  serie: PerformanceRelativaPunto[]
}

export const getPerformanceRelativa = (cartera: string | null, moneda: MonedaRiesgo, benchmark: string | null, desde?: string) =>
  api.get<PerformanceRelativaOut>(`${carteraPath(cartera)}/performance-relativa`, { params: { moneda, benchmark: benchmark ?? undefined, desde: desde ?? undefined } }).then(r => r.data)

export interface ComparacionBenchmarkOut {
  fuente: string
  tipo: string
  estado: string
  retorno_pct: number | null
  delta_pp: number | null
  valor_final_equivalente_usd: number | null
  valor_final_equivalente_ars: number | null
  ranking: number | null
  n_meses_historia: number
}

export interface PerformanceCompareOut {
  estado: string
  moneda: string
  periodo_desde: string | null
  periodo_hasta: string | null
  filas: ComparacionBenchmarkOut[]
  serie: Record<string, any>[]
}

export const getPerformanceCompare = (
  cartera: string | null,
  moneda: MonedaRiesgo,
  desde?: string,
  benchmarks?: string[],
  tickers?: string[]
) =>
  api
    .get<PerformanceCompareOut>(`${carteraPath(cartera)}/performance/compare`, {
      params: {
        moneda,
        desde: desde ?? undefined,
        benchmarks: benchmarks?.join(',') ?? undefined,
        tickers: tickers?.join(',') ?? undefined,
      },
    })
    .then(r => r.data)

export interface OpportunityCostPosicionOut {
  ticker: string
  nombre: string
  valor_actual_usd: number
  valor_shadow_usd: number
  costo_oportunidad_usd: number
  costo_oportunidad_ars: number
}

export interface OpportunityCostOut {
  estado: string
  benchmark_usado: string | null
  moneda_nativa_benchmark: string | null
  valor_actual_usd: number | null
  valor_actual_ars: number | null
  valor_shadow_usd: number | null
  valor_shadow_ars: number | null
  costo_oportunidad_usd: number | null
  costo_oportunidad_ars: number | null
  por_posicion: OpportunityCostPosicionOut[]
}

export const getOpportunityCost = (
  cartera: string | null,
  benchmark?: string,
  desde?: string
) =>
  api
    .get<OpportunityCostOut>(`${carteraPath(cartera)}/opportunity-cost`, {
      params: { benchmark: benchmark ?? undefined, desde: desde ?? undefined },
    })
    .then(r => r.data)

// --- Costo de oportunidad (comparación histórica cartera vs. referencia, en la misma moneda) ---
// A diferencia de OpportunityCostOut (sólo el valor final, sin normalizar moneda) y de
// PerformanceRelativaOut (no toca la moneda de la referencia), este endpoint normaliza la
// referencia a `moneda` y da la evolución completa, en porcentaje y en dinero.

export interface CostoOportunidadIndicePunto {
  fecha: string
  indice_cartera: number | null
  indice_referencia: number | null
}

export interface CostoOportunidadValorPunto {
  fecha: string
  valor_cartera: number | null
  valor_referencia: number | null
  diferencia: number | null
}

export interface CostoOportunidadOut {
  estado: 'ok' | 'sin_benchmark' | 'sin_movimientos' | 'datos_insuficientes'
  moneda: MonedaRiesgo
  referencia: string | null
  moneda_nativa_referencia: string | null
  periodo_pedido_desde: string | null
  periodo_desde: string | null
  periodo_hasta: string | null
  n_meses: number
  resultado_cartera_pct: number | null
  resultado_referencia_pct: number | null
  diferencia_pp: number | null
  valor_inicial: number | null
  aportes_netos_periodo: number | null
  valor_final_cartera: number | null
  valor_final_referencia: number | null
  diferencia_monetaria: number | null
  serie_indices: CostoOportunidadIndicePunto[]
  serie_valores: CostoOportunidadValorPunto[]
  advertencias: string[]
}

export const getCostoOportunidad = (
  cartera: string | null,
  moneda: MonedaRiesgo,
  benchmark: string | null,
  desde?: string
) =>
  api
    .get<CostoOportunidadOut>(`${carteraPath(cartera)}/costo-oportunidad`, {
      params: { moneda, benchmark: benchmark ?? undefined, desde: desde ?? undefined },
    })
    .then(r => r.data)

// --- Contribución, concentración y correlaciones ---

export interface ContribucionItem {
  etiqueta: string
  peso_promedio_pct: number
  pnl_usd: number
  costo_total_usd: number
  rentabilidad_pct: number | null
  contribucion_pct: number
}

export interface ContribucionEje {
  eje: string
  items: ContribucionItem[]
}

export interface ConcentracionItem {
  eje: string
  estado: 'ok' | 'sin_datos'
  hhi: number | null
  hhi_normalizado: number | null
  effective_n: number | null
  n_componentes: number
}

export interface ContribucionOut {
  contribucion: ContribucionEje[]
  concentracion: ConcentracionItem[]
}

export const getContribucion = (cartera: string | null) =>
  api.get<ContribucionOut>(`${carteraPath(cartera)}/contribucion`).then(r => r.data)

export type UniversoCorrelacion = 'tenencias' | 'todos'

export interface CorrelacionParItem {
  ticker_a: string
  ticker_b: string
  valor: number | null
  n_obs: number
  estado: 'ok' | 'datos_insuficientes'
}

export interface CorrelacionesOut {
  universo: UniversoCorrelacion
  n_tickers: number
  tickers: string[]
  matriz: (number | null)[][]
  pares: CorrelacionParItem[]
  advertencia_historial_corto: boolean
}

export const getCorrelaciones = (cartera: string | null, universo: UniversoCorrelacion = 'tenencias') =>
  api.get<CorrelacionesOut>(`${carteraPath(cartera)}/correlaciones`, { params: { universo } }).then(r => r.data)

// --- Matriz de correlaciones (pantalla dedicada, distinta de CorrelacionesOut de Contribución) ---

export type FrecuenciaCorrelacion = 'diaria' | 'semanal' | 'mensual'

export interface MatrizCorrelacionParItem {
  ticker_a: string
  ticker_b: string
  valor: number | null
  n_obs: number
  solapamiento_pct: number | null
  estado: 'ok' | 'datos_insuficientes'
  motivo: 'ok' | 'sin_solapamiento' | 'menos_de_min_obs' | 'serie_constante'
}

export interface MatrizCorrelacionTickerItem {
  ticker: string
  n_retornos: number
  cobertura_pct: number | null
  primer_periodo: string | null
  ultimo_periodo: string | null
}

export interface MatrizCorrelacionDescartadoItem {
  ticker: string
  motivo: 'sin_precios' | 'tope_tickers'
}

export interface MatrizCorrelacionRankingOut {
  mas_correlacionados: MatrizCorrelacionParItem[]
  menos_correlacionados: MatrizCorrelacionParItem[]
  mas_negativos: MatrizCorrelacionParItem[]
}

export interface MatrizCorrelacionesOut {
  estado: 'ok' | 'sin_tickers' | 'sin_suficientes_tickers' | 'datos_insuficientes'
  moneda: string
  frecuencia_pedida: FrecuenciaCorrelacion
  frecuencia_efectiva: FrecuenciaCorrelacion
  min_obs: number
  periodo_pedido_desde: string | null
  periodo_pedido_hasta: string | null
  periodo_desde: string | null
  periodo_hasta: string | null
  n_periodos: number
  n_periodos_posibles: number
  tickers: string[]
  n_tickers: number
  tickers_detalle: MatrizCorrelacionTickerItem[]
  tickers_descartados: MatrizCorrelacionDescartadoItem[]
  matriz: (number | null)[][]
  pares: MatrizCorrelacionParItem[]
  n_pares: number
  n_pares_ok: number
  correlacion_promedio: number | null
  nivel_diversificacion: 'alta' | 'media' | 'baja' | null
  ranking: MatrizCorrelacionRankingOut
  pocos_datos: boolean
  advertencias: string[]
}

export interface MatrizCorrelacionesOpts {
  tickers: string[]
  frecuencia: FrecuenciaCorrelacion
  desde?: string
}

export const getMatrizCorrelaciones = (cartera: string | null, opts: MatrizCorrelacionesOpts) =>
  api.get<MatrizCorrelacionesOut>(`${carteraPath(cartera)}/matriz-correlaciones`, {
    params: { tickers: opts.tickers, frecuencia: opts.frecuencia, desde: opts.desde ?? undefined },
  }).then(r => r.data)

// --- Diagnóstico ---

export interface HallazgoItem {
  tipo: string
  severidad: 'critico' | 'advertencia' | 'info'
  titulo: string
  explicacion: string
  dato_disparador: Record<string, number | string | boolean | null>
  pantalla: string
  fecha_calculo: string
}

export interface DimensionScore {
  nombre: 'riesgo' | 'concentracion' | 'diversificacion' | 'performance' | 'objetivo'
  score: number | null
  peso: number
  estado: 'ok' | 'excluida'
  detalle: string
}

export interface SaludCarteraOut {
  score_total: number | null
  dimensiones: DimensionScore[]
  fecha_calculo: string
}

export interface DiagnosticoOut {
  cartera: string | null
  salud: SaludCarteraOut
  hallazgos: HallazgoItem[]
  fecha_calculo: string
}

export const getDiagnostico = (cartera: string | null) =>
  api.get<DiagnosticoOut>(`${carteraPath(cartera)}/diagnostico`).then(r => r.data)

// --- Salud de cartera ---
// A propósito no hay un score único acá (a diferencia de `SaludCarteraOut` de Diagnóstico, arriba):
// esta pantalla muestra un estado explicable por dimensión ("normal" | "atencion" | "revisar"),
// sin combinarlos en un solo número.

export type EstadoSalud = 'normal' | 'atencion' | 'revisar' | 'sin_datos'

export interface SaludIndicador {
  clave: string
  nombre: string
  texto: string
  pantalla: string
  ayuda: string
  valor_usd: number | null
  valor_ars: number | null
  valor_pct: number | null
}

export interface SaludDimension {
  clave: string
  nombre: string
  estado: EstadoSalud
  etiqueta: string
  valor: string
  regla: string
  explicacion: string
  fuente: string
  pantalla: string
  ayuda: string
}

export interface SaludObservacion {
  id: string
  dimension: string
  severidad: 'revisar' | 'atencion' | 'info'
  titulo: string
  detecto: string
  valor: string
  umbral: string
  fuente: string
  pantalla: string
  accion: string
}

export interface SaludResumen {
  n_revisar: number
  n_atencion: number
  n_normal: number
  n_sin_datos: number
}

export interface SaludCarteraEstadoOut {
  cartera: string | null
  indicadores: SaludIndicador[]
  dimensiones: SaludDimension[]
  observaciones: SaludObservacion[]
  exposicion_moneda: ExposicionItem[]
  exposicion_tipo: ExposicionItem[]
  resumen: SaludResumen
  fecha_calculo: string
}

export const getSaludCartera = (cartera: string | null) =>
  api.get<SaludCarteraEstadoOut>(`${carteraPath(cartera)}/salud`).then(r => r.data)

// --- Explicación del resultado ("¿Por qué ganó o perdió mi cartera?") ---
// Ver backend/app/services/explicacion_resultado_engine.py para la fórmula: pnl = precio +
// dividendos + cupones + comisiones (comisiones ya viene negativo). Todo lo que dependa de un
// precio de mercado es `| null`: un instrumento sin cotización no se estima, se lista en
// `no_disponibles`.

export interface ExplicacionPeriodo {
  desde: string | null
  hasta: string
}

export interface ExplicacionResultadoResumen {
  v0: number | null
  v1: number | null
  pnl: number | null
  twr_pct: number | null
  xirr_pct: number | null
  rendimiento_simple_pct: number | null
  aportes: number | null
  retiros: number | null
  amortizaciones: number | null
  ingresos: number | null
}

export interface ExplicacionComponentes {
  precio: number | null
  dividendos: number | null
  cupones: number | null
  comisiones: number | null
}

export interface ExplicacionItem {
  ticker?: string | null
  nombre?: string | null
  etiqueta?: string | null
  v0: number | null
  v1: number | null
  pnl: number | null
  precio: number | null
  dividendos: number | null
  cupones: number | null
  comisiones: number | null
  aportes: number | null
  retiros: number | null
  amortizaciones: number | null
  contribucion_pct: number | null
  disponible?: boolean | null
  n_no_disponibles?: number | null
}

export interface ExplicacionNoDisponible {
  ticker: string
  nombre: string
  motivo: string
}

export interface ExplicacionFx {
  estado: 'ok' | 'no_disponible' | 'no_aplica'
  resultado_activos_ars: number | null
  efecto_mep_ars: number | null
  efecto_fx_pct: number | null
  identidad_verificada: boolean
}

export interface ExplicacionTexto {
  titulo: string
  frases: string[]
}

export interface ExplicacionResultadoOut {
  estado: 'ok' | 'parcial' | 'sin_datos'
  periodo: ExplicacionPeriodo
  resultado: ExplicacionResultadoResumen
  componentes: ExplicacionComponentes
  por_tipo: ExplicacionItem[]
  por_mercado: ExplicacionItem[]
  por_ticker: ExplicacionItem[]
  contribuyentes: ExplicacionItem[]
  detractores: ExplicacionItem[]
  no_disponibles: ExplicacionNoDisponible[]
  fx: ExplicacionFx
  explicacion: ExplicacionTexto
  advertencias: string[]
}

export const getExplicacionResultado = (cartera: string | null, desde: string | undefined, moneda: 'usd' | 'ars') =>
  api
    .get<ExplicacionResultadoOut>(`${carteraPath(cartera)}/explicacion-resultado`, { params: { desde, moneda } })
    .then(r => r.data)

// --- Descomposición FX ---

export interface DescomposicionFxOut {
  estado: 'ok' | 'datos_insuficientes' | 'mep_faltante'
  periodo_desde: string | null
  periodo_hasta: string | null
  retorno_total_ars_pct: number | null
  retorno_activo_pct: number | null
  efecto_fx_pct: number | null
  mep_inicio: number | null
  mep_fin: number | null
  mep_aproximado: boolean
  identidad_verificada: boolean
}

export interface DescomposicionFxPosicionItem {
  ticker: string
  moneda: string
  estado: 'ok' | 'datos_insuficientes' | 'mep_faltante' | 'moneda_desconocida'
  rendimiento_simple_ars_pct: number | null
  rendimiento_simple_usd_pct: number | null
  efecto_fx_pct: number | null
  retorno_activo_pct: number | null
  aproximado: boolean
}

export interface DescomposicionFxPosicionOut {
  posiciones: DescomposicionFxPosicionItem[]
}

export const getDescomposicionFx = (cartera: string | null, desde?: string) =>
  api.get<DescomposicionFxOut>(`${carteraPath(cartera)}/descomposicion-fx`, { params: desde ? { desde } : undefined }).then(r => r.data)

export const getDescomposicionFxPorPosicion = (cartera: string | null) =>
  api.get<DescomposicionFxPosicionOut>(`${carteraPath(cartera)}/descomposicion-fx-por-posicion`).then(r => r.data)

// --- Análisis profundo por ticker ---

export interface TickerPositionOut extends InversionesResumen {
  ticker: string
  nombre: string
  tipo_instrumento: string
  mercado: string
  moneda: string
  pais: string | null
  sector: string | null
  cantidad_actual: number
  precio_promedio: number
  precio_actual: number | null
  primera_fecha_movimiento: string | null
  ultima_fecha_movimiento: string | null
  posicion_cerrada: boolean
  objetivo_modo: string | null
  objetivo_valor: number | null
  precio_objetivo: number | null
  pct_a_objetivo: number | null
  objetivo_alcanzado: boolean | null
  stop_loss_modo: string | null
  stop_loss_valor: number | null
  precio_stop_loss: number | null
  pct_a_stop_loss: number | null
  stop_loss_disparado: boolean | null
}

export interface TickerPerformanceOut extends PnlPorTickerItem {
  comisiones_usd: number
  comisiones_ars: number
  precio_actual_faltante: boolean
}

export interface TickerAnalysisOut {
  position: TickerPositionOut
  performance: TickerPerformanceOut
}

export interface TickerHistoricoPunto {
  fecha: string
  precio_nominal: number
  precio_usd: number | null
  precio_cer: number | null
  valor_posicion_usd: number | null
  valor_posicion_ars: number | null
  rendimiento_acumulado_pct: number | null
}

export interface TickerHistoricoOut {
  ticker: string
  moneda: string
  puntos: TickerHistoricoPunto[]
}

export type TickerRiesgoOut = RiesgoOut
export type TickerPerformanceRelativaOut = PerformanceRelativaOut

export const getAnalisisTicker = (ticker: string, cartera: string | null = null) =>
  api.get<TickerAnalysisOut>(`/inversiones/ticker/${encodeURIComponent(ticker)}/analysis`, { params: cartera ? { cartera } : undefined }).then(r => r.data)

export const getRiesgoTicker = (ticker: string, cartera: string | null = null, moneda: MonedaRiesgo = 'usd', benchmark: string | null = null) =>
  api.get<TickerRiesgoOut>(`/inversiones/ticker/${encodeURIComponent(ticker)}/riesgo`, { params: { ...(cartera && { cartera }), moneda, ...(benchmark && { benchmark }) } }).then(r => r.data)

export const getHistoricoTicker = (ticker: string, cartera: string | null = null, desde?: string) =>
  api.get<TickerHistoricoOut>(`/inversiones/ticker/${encodeURIComponent(ticker)}/historico`, { params: { ...(cartera && { cartera }), ...(desde && { desde }) } }).then(r => r.data)

export const getPerformanceRelativaTicker = (ticker: string, cartera: string | null = null, moneda: MonedaRiesgo = 'usd', benchmark: string | null = null, desde?: string) =>
  api.get<TickerPerformanceRelativaOut>(`/inversiones/ticker/${encodeURIComponent(ticker)}/performance-relativa`, { params: { ...(cartera && { cartera }), moneda, ...(benchmark && { benchmark }), ...(desde && { desde }) } }).then(r => r.data)

// ── Escenarios (Simulador) ──────────────────────────────────────────────

export interface EscenarioParamsIn {
  horizonte_meses: number
  variacion_dolar_pct: number
  variacion_por_instrumento: Record<string, number>
  variacion_por_defecto_pct: number
  aporte_mensual_usd: number
  crecimiento_aporte_anual_pct: number
  retiro_mensual_usd: number
  modo_dividendos: 'reinvertir_total' | 'reinvertir_parcial' | 'retirar'
  dividend_yield_anual_pct: number
  pct_dividendo_reinvertido?: number | null
  comision_pct: number
  inflacion_anual_pct?: number | null
}

export interface EscenarioSimulacionItem {
  tipo_preset: 'alcista' | 'bajista' | 'crisis' | 'personalizado'
  nombre?: string
  parametros?: EscenarioParamsIn
}

export interface EscenarioSimulacionRequest {
  escenarios: EscenarioSimulacionItem[]
}

export interface EscenarioPunto {
  mes: number
  fecha: string
  valor_usd: number
  capital_aportado_acum_usd: number
  dividendos_acum_usd: number
}

export interface EscenarioResultado {
  nombre: string
  tipo_preset: string
  puntos: EscenarioPunto[]
  patrimonio_inicial_usd: number
  patrimonio_final_usd: number
  ganancia_perdida_usd: number
  rendimiento_pct: number
  capital_aportado_usd: number
  efecto_mercado_usd: number
  efecto_dolar_usd: number
  dividendos_usd: number
  comisiones_usd: number
  patrimonio_final_real_usd?: number | null
  diferencia_vs_actual_usd: number
  es_simulado: boolean
}

export interface EscenarioSimulacionOut {
  cartera: string | null
  fecha_simulacion: string
  actual_valor_usd: number
  resultados: EscenarioResultado[]
  advertencias: string[]
}

export interface EscenarioGuardarRequest {
  cartera?: string | null
  nombre: string
  tipo_preset: string
  parametros: EscenarioParamsIn
}

export interface Escenario {
  id: number
  cartera: string | null
  nombre: string
  tipo_preset: string
  parametros: EscenarioParamsIn
  fecha_creacion: string
  fecha_actualizacion: string
}

export const simularEscenarios = (cartera: string | null, body: EscenarioSimulacionRequest) =>
  api.post<EscenarioSimulacionOut>(`/inversiones/scenarios/simulate${cartera ? `?cartera=${encodeURIComponent(cartera)}` : ''}`, body).then(r => r.data)

export const listarEscenarios = (cartera: string | null) =>
  api.get<Escenario[]>('/inversiones/scenarios', { params: cartera ? { cartera } : {} }).then(r => r.data)

export const guardarEscenario = (body: EscenarioGuardarRequest) =>
  api.post<Escenario>('/inversiones/scenarios', body).then(r => r.data)

export const duplicarEscenario = (id: number, nuevoNombre?: string) =>
  api.post<Escenario>(`/inversiones/scenarios/${id}/duplicate`, null, { params: nuevoNombre ? { nuevo_nombre: nuevoNombre } : {} }).then(r => r.data)

export const eliminarEscenario = (id: number) =>
  api.delete(`/inversiones/scenarios/${id}`).then(() => undefined)

// ── Escenarios de vida (Simulador sencillo) ──────────────────────────────

export type TipoEscenarioVida =
  | 'continuar_igual'
  | 'aumentar_aporte'
  | 'disminuir_aporte'
  | 'dejar_de_aportar'
  | 'aporte_extraordinario'
  | 'retiro_extraordinario'
  | 'aumentar_aportes_anualmente'

export interface SupuestosVidaIn {
  patrimonio_inicial: number
  aporte_mensual: number
  crecimiento_anual_pct: number
  horizonte_meses: number
  moneda: 'USD' | 'ARS'
  inflacion_anual_pct?: number | null
}

export interface EscenarioVidaIn {
  tipo: TipoEscenarioVida
  monto?: number | null
  pct?: number | null
  mes?: number | null
}

export interface EscenarioVidaRequest {
  supuestos: SupuestosVidaIn
  escenarios: EscenarioVidaIn[]
}

export interface PuntoVida {
  mes: number
  fecha: string
  valor: number
  valor_real?: number | null
  aportado_acum: number
}

export interface MetricasVida {
  patrimonio_final: number
  patrimonio_final_real?: number | null
  aportes_periodo: number
  crecimiento_estimado: number
  diferencia_vs_base: number
  diferencia_vs_base_pct?: number | null
}

export interface EscenarioVidaResultado {
  tipo: TipoEscenarioVida
  nombre: string
  descripcion: string
  es_base: boolean
  aporte_mensual_efectivo: number
  crecimiento_aporte_anual_pct: number
  mes_flujo_extraordinario?: number | null
  monto_flujo_extraordinario?: number | null
  se_agota_en_mes?: number | null
  puntos: PuntoVida[]
  metricas: MetricasVida
  advertencias: string[]
  es_simulado: boolean
}

export interface EscenarioVidaOut {
  cartera: string | null
  fecha_simulacion: string
  moneda: 'USD' | 'ARS'
  supuestos: SupuestosVidaIn
  resultados: EscenarioVidaResultado[]  // resultados[0] es siempre la base
  disclaimer: string
  advertencias: string[]
}

export interface DefaultsVida {
  cartera: string | null
  patrimonio_inicial_usd: number
  aporte_mensual_usd: number | null
  origen_aporte: 'promedio_12m' | 'promedio_historico' | 'sin_datos'
  meses_historia: number
  moneda_sugerida: 'USD' | 'ARS'
  crecimiento_anual_pct_sugerido: number
  horizonte_meses_sugerido: number
  advertencias: string[]
}

export const simularVida = (cartera: string | null, body: EscenarioVidaRequest) =>
  api.post<EscenarioVidaOut>(`/inversiones/scenarios/vida/simulate${cartera ? `?cartera=${encodeURIComponent(cartera)}` : ''}`, body).then(r => r.data)

export const getDefaultsVida = (cartera: string | null) =>
  api.get<DefaultsVida>('/inversiones/scenarios/vida/defaults', { params: cartera ? { cartera } : {} }).then(r => r.data)

// ---- Análisis técnico ----

export type VarianteSerie = 'local' | 'subyacente'

export interface SerieVarianteOut {
  variante: VarianteSerie
  moneda: string
  mercado: string
}

export interface TickerTecnicoOut {
  ticker: string
  nombre: string
  moneda: string
  tipo_instrumento: string
  origen: 'cartera' | 'watchlist' | 'ambos'
  series: SerieVarianteOut[]
}

export interface BarraOut {
  fecha: string
  cierre: number
  apertura?: number | null
  maximo?: number | null
  minimo?: number | null
  volumen?: number | null
}

export interface SerieTecnicaOut {
  ticker: string
  nombre: string
  moneda: string
  variante: VarianteSerie
  mercado: string | null
  origen: 'cartera' | 'watchlist' | 'ambos' | null
  fuente_serie: 'velas' | 'mixta' | 'sin_datos'
  tiene_velas: boolean
  tiene_volumen: boolean
  indice_desde: number
  barras: BarraOut[]
  indicadores: Record<string, Record<string, (number | null)[]>>
  advertencias: string[]
}

export const getTickersTecnicos = () =>
  api.get<TickerTecnicoOut[]>('/inversiones/tecnico/tickers').then(r => r.data)

export const getSerieTecnica = (
  ticker: string,
  params: { desde?: string; hasta?: string; indicadores?: string[]; max_barras?: number; variante?: VarianteSerie },
) =>
  api.get<SerieTecnicaOut>(`/inversiones/tecnico/${encodeURIComponent(ticker)}/serie`, { params }).then(r => r.data)

// --- Estrategias: DSL ---

export type OperandoDsl =
  | { ref: string; salida?: string }
  | { const: number }
  | { campo: 'cierre' | 'apertura' | 'maximo' | 'minimo' | 'volumen' }

export type CondicionDsl =
  | { op: 'y' | 'o'; condiciones: CondicionDsl[] }
  | { op: 'no'; condicion: CondicionDsl }
  | { op: 'mayor' | 'menor' | 'mayor_igual' | 'menor_igual' | 'cruce_arriba' | 'cruce_abajo'; izq: OperandoDsl; der: OperandoDsl }
  | { op: 'entre'; valor: OperandoDsl; minimo: OperandoDsl; maximo: OperandoDsl }
  | { op: 'subiendo' | 'bajando'; operando: OperandoDsl; barras?: number }

export interface IndicadorDsl {
  id: string
  tipo: string
  params: Record<string, number>
}

export interface RiesgoDsl {
  stop_loss_pct: number | null
  take_profit_pct: number | null
  trailing_stop_pct: number | null
  max_barras: number | null
}

export interface EjecucionDsl {
  lado: 'long'
  comision_pct: number
  precio_ejecucion: 'cierre' | 'apertura_siguiente'
  demora_barras: number
}

export interface EstrategiaDsl {
  version: 1
  indicadores: IndicadorDsl[]
  entrada: CondicionDsl
  salida?: CondicionDsl | null
  riesgo: RiesgoDsl
  ejecucion: EjecucionDsl
}

export interface SenalOut {
  indice: number
  fecha: string
  tipo: 'compra' | 'venta'
  precio: number
  motivo: string
}

export interface OperacionOut {
  indice_entrada: number
  indice_salida: number | null
  fecha_entrada: string
  fecha_salida: string | null
  precio_entrada: number
  precio_salida: number | null
  barras: number
  retorno_bruto_pct: number
  retorno_neto_pct: number
  motivo_salida: string | null
  abierta: boolean
  /** Niveles de riesgo vigentes durante la operación, calculados por el motor de backtest para
   * que el gráfico los dibuje sin reimplementar la regla. `trailing` arranca en `indice_entrada`
   * y trae un valor por barra consecutiva; `null` cuando la estrategia no configuró ese límite. */
  nivel_stop_loss?: number | null
  nivel_take_profit?: number | null
  trailing?: number[] | null
}

/** Los motivos que emite `estrategia_engine`. `entrada` sólo aparece en `SenalOut`. */
export type MotivoSalida = 'regla_salida' | 'stop_loss' | 'take_profit' | 'trailing_stop' | 'max_barras'

export interface BacktestMetricasOut {
  estado: 'ok' | 'datos_insuficientes'
  retorno_total_pct: number
  retorno_anualizado_pct: number | null
  retorno_buy_hold_pct: number
  exceso_vs_buy_hold_pp: number
  operaciones: number
  operaciones_cerradas: number
  retorno_abierta_pct: number | null
  ganadoras: number
  perdedoras: number
  win_rate_pct: number | null
  retorno_medio_operacion_pct: number | null
  mejor_operacion_pct: number | null
  peor_operacion_pct: number | null
  profit_factor: number | null
  max_drawdown_pct: number | null
  fecha_pico: string | null
  fecha_valle: string | null
  duracion_media_barras: number | null
  exposicion_pct: number
  comisiones_pct_acum: number
}

export interface CurvaPuntoOut {
  fecha: string
  valor: number
}

export interface BacktestOut {
  ticker: string
  variante: VarianteSerie
  moneda: string
  senales: SenalOut[]
  operaciones: OperacionOut[]
  metricas: BacktestMetricasOut
  curva_equity: CurvaPuntoOut[]
  curva_buy_hold: CurvaPuntoOut[]
  primera_barra_evaluable: number | null
  // Serie de barras del backtest (con warm-up) + series de indicadores keyed por `id` de la
  // definición. Alineadas 1:1 con `curva_equity` y `senales[].indice`.
  barras: BarraOut[]
  indicadores: Record<string, Record<string, (number | null)[]>>
  indice_desde: number
  advertencias: string[]
}

export type CategoriaPreset = 'tendencia' | 'reversion' | 'ruptura' | 'momentum'

export interface PresetEstrategiaOut {
  /** Slug estable: es el `tipo_preset` de las guardadas y la clave de su ficha de ayuda. */
  nombre: string
  /** Nombre legible; también el `nombre` con el que la siembra las guarda en la DB. */
  etiqueta: string
  categoria: CategoriaPreset
  definicion: EstrategiaDsl
  requiere_velas: boolean
  requiere_volumen: boolean
}

export interface SiembraPresetsOut {
  creadas: number
  actualizadas: number
  sin_cambios: number
}

export interface EstrategiaGuardarRequest {
  nombre: string
  descripcion?: string | null
  ticker?: string | null
  tipo_preset?: string | null
  definicion: EstrategiaDsl
  variante?: VarianteSerie
}

export interface EstrategiaOut {
  id: number
  nombre: string
  descripcion: string | null
  ticker: string | null
  tipo_preset: string | null
  definicion: EstrategiaDsl
  variante: VarianteSerie
  fecha_creacion: string
  fecha_actualizacion: string
}

export interface SenalTickerOut {
  ticker: string
  estrategia_id: number
  estrategia_nombre: string
  tipo: 'compra' | 'venta'
  fecha: string
  precio: number
  motivo: string
  barras_desde: number
  variante: VarianteSerie
  moneda: string
}

export const getPresetsEstrategia = () =>
  api.get<PresetEstrategiaOut[]>('/inversiones/tecnico/presets').then(r => r.data)

export const getSenalesTecnicas = () =>
  api.get<SenalTickerOut[]>('/inversiones/tecnico/senales').then(r => r.data)

export const backtestEstrategia = (
  ticker: string, definicion: EstrategiaDsl, desde?: string, hasta?: string, variante: VarianteSerie = 'local',
) =>
  api.post<BacktestOut>(`/inversiones/tecnico/${encodeURIComponent(ticker)}/backtest`, { definicion, desde, hasta, variante }).then(r => r.data)

export const listarEstrategias = (ticker?: string) =>
  api.get<EstrategiaOut[]>('/inversiones/estrategias', { params: ticker ? { ticker } : {} }).then(r => r.data)

export const sembrarPresetsEstrategia = (forzar = false) =>
  api.post<SiembraPresetsOut>('/inversiones/tecnico/presets/sembrar', null, { params: { forzar } }).then(r => r.data)

/** El nombre identifica a la estrategia: si ya existía una con ese nombre, el backend la pisa y
 * responde 200 en vez de 201. `sobrescrita` traduce ese status para que la UI pueda avisarlo. */
export const guardarEstrategia = (body: EstrategiaGuardarRequest) =>
  api.post<EstrategiaOut>('/inversiones/estrategias', body)
    .then(r => ({ ...r.data, sobrescrita: r.status === 200 }))

export const actualizarEstrategia = (id: number, body: EstrategiaGuardarRequest) =>
  api.put<EstrategiaOut>(`/inversiones/estrategias/${id}`, body).then(r => r.data)

export const duplicarEstrategia = (id: number, nuevoNombre?: string) =>
  api.post<EstrategiaOut>(`/inversiones/estrategias/${id}/duplicate`, null, { params: nuevoNombre ? { nuevo_nombre: nuevoNombre } : {} }).then(r => r.data)

export const eliminarEstrategiaTecnica = (id: number) =>
  api.delete(`/inversiones/estrategias/${id}`).then(() => undefined)

// ---- Screener ----

export type OrigenScreener = 'todos' | 'cartera' | 'watchlist'

export interface ScreenerRequest {
  estrategia_ids?: number[]
  umbral_pct?: number
  origen?: OrigenScreener
}

export interface ScreenerCondicionOut {
  op: string
  cumple: boolean
  izq_etiqueta: string
  izq_valor: number | null
  der_etiqueta: string
  der_valor: number | null
}

export interface ScreenerFilaOut {
  ticker: string
  nombre: string
  origen: 'cartera' | 'watchlist' | 'ambos'
  estrategia_id: number
  estrategia_nombre: string
  variante: VarianteSerie
  moneda: string
  tipo: 'compra' | 'venta'
  motivo: string
  distancia_pct: number
  precio_actual: number
  precio_gatillo: number
  fecha_precio: string
  dispara_ahora: boolean
  posicion_abierta: boolean
  retorno_abierta_pct: number | null
  condiciones: ScreenerCondicionOut[]
}

export interface ScreenerOut {
  filas: ScreenerFilaOut[]
  tickers_evaluados: number
  pares_evaluados: number
  umbral_pct: number
  fecha: string
  advertencias: string[]
}

export const correrScreener = (body: ScreenerRequest) =>
  api.post<ScreenerOut>('/inversiones/tecnico/screener', body).then(r => r.data)
