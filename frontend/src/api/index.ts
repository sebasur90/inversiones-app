import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

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
  api.post<SyncResult>('/inversiones/sync').then(r => r.data)

export const getCalidadDatos = () =>
  api.get<CalidadDatosOut>('/inversiones/calidad-datos').then(r => r.data)

export const getCarterasInversion = () =>
  api.get<CarteraInfo[]>('/inversiones/carteras').then(r => r.data)

export const getResumenInversiones = (cartera: string | null) =>
  api.get<InversionesResumen>(`${carteraPath(cartera)}/resumen`).then(r => r.data)

export const getExposicionInversiones = (cartera: string | null) =>
  api.get<ExposicionOut>(`${carteraPath(cartera)}/exposicion`).then(r => r.data)

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
  no_realizado_usd: number
  ingresos_usd: number
  total_usd: number
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
