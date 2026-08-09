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

export const getMovimientosInversion = (params: { cartera?: string; ticker?: string }) =>
  api.get<MovimientoInversion[]>('/inversiones/movimientos', { params }).then(r => r.data)

export const getRendimientoPorTicker = (cartera: string | null) =>
  api.get<RendimientoPorTickerItem[]>(`${carteraPath(cartera)}/rendimiento-por-ticker`).then(r => r.data)

export interface EvolucionPunto {
  fecha: string
  valor_usd: number
  valor_ars: number
  valor_ars_real: number | null
}

export interface EvolucionOut {
  puntos: EvolucionPunto[]
}

export const getEvolucionInversiones = (cartera: string | null, desde?: string) =>
  api.get<EvolucionOut>(`${carteraPath(cartera)}/evolucion`, { params: desde ? { desde } : undefined }).then(r => r.data)

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

export interface ObjetivoInversionPayload {
  nombre: string
  icono: string
  monto_usd: number
  fecha_limite: string
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

export const crearObjetivoInversion = (cartera: string, payload: ObjetivoInversionPayload) =>
  api.post<ObjetivoInversion>(`/inversiones/carteras/${encodeURIComponent(cartera)}/objetivo`, payload).then(r => r.data)

export const editarObjetivoInversion = (objetivoId: number, payload: ObjetivoInversionPayload) =>
  api.put<ObjetivoInversion>(`/inversiones/objetivos-inversion/${objetivoId}`, payload).then(r => r.data)

export const eliminarObjetivoInversion = (objetivoId: number) =>
  api.delete(`/inversiones/objetivos-inversion/${objetivoId}`).then(r => r.data)
