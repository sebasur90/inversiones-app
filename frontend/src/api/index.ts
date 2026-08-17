import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export default api

// ---- Inversiones ----
export interface SyncErrorItem {
  fila: number
  motivo: string
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
  errores: SyncErrorItem[]
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
}

export interface IndicesMercadoOut {
  puntos: IndiceMercadoPunto[]
  variacion_cer_pct: number | null
  variacion_mep_pct: number | null
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
  valor_actual_usd: number
  valor_actual_ars: number
  moneda: string
}

export const getVencimientos = (cartera: string | null) =>
  api.get<VencimientoItem[]>(`${carteraPath(cartera)}/vencimientos`).then(r => r.data)

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
  meses_restantes: number
  proyeccion_usd: number
  alcanzable: boolean
  deficit_usd: number
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
