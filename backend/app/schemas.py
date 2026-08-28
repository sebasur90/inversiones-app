from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import date, datetime

# --- Inversiones: Sincronización ---

class SyncIssueOut(BaseModel):
    tab: str
    fila: Optional[int] = None
    campo: Optional[str] = None
    regla: str
    severidad: str
    mensaje: str
    impacto: str


class SyncResult(BaseModel):
    movimientos: int
    instrumentos: int
    precios: int
    indices_mercado: int
    objetivos: int
    rebalanceo: int
    benchmarks: int
    configuracion: int
    health_score: int
    resultado: str
    duration_ms: int
    timestamp: datetime
    issues: list[SyncIssueOut]


class SyncRunResumenOut(BaseModel):
    id: int
    timestamp: datetime
    duration_ms: int
    filas_procesadas: int
    filas_validas: int
    filas_advertencia: int
    filas_error: int
    health_score: int
    resultado: str


class CalidadDatosOut(BaseModel):
    ultimo_sync: Optional[SyncRunResumenOut] = None
    issues: list[SyncIssueOut]
    issues_por_tab: dict[str, list[SyncIssueOut]]


class CarteraInfo(BaseModel):
    nombre: str
    ultimo_sync: Optional[str] = None


class InversionesResumen(BaseModel):
    valor_actual_usd: float
    valor_actual_ars: float
    total_invertido_usd: float
    total_invertido_ars: float
    total_invertido_ars_real: Optional[float] = None
    ingresos_recibidos_usd: float
    ingresos_recibidos_ars: float
    rendimiento_simple_usd: Optional[float] = None
    rendimiento_simple_ars: Optional[float] = None
    rendimiento_simple_ars_real: Optional[float] = None
    xirr_usd: Optional[float] = None
    xirr_ars: Optional[float] = None
    xirr_ars_real: Optional[float] = None
    twr_usd: Optional[float] = None
    twr_ars: Optional[float] = None
    twr_ars_real: Optional[float] = None
    twr_usd_bruto: Optional[float] = None
    twr_ars_bruto: Optional[float] = None
    valor_benchmark_usd_ars: Optional[float] = None
    tiene_precios_desactualizados: bool = False


class ExposicionItem(BaseModel):
    etiqueta: str
    valor_usd: float
    valor_ars: float
    porcentaje: float


class ExposicionEje(BaseModel):
    eje: str
    items: list[ExposicionItem]


class ExposicionOut(BaseModel):
    ejes: list[ExposicionEje]


class RebalanceoItem(BaseModel):
    etiqueta: str
    porcentaje_actual: float
    porcentaje_objetivo: float
    valor_actual_usd: float
    valor_actual_ars: float
    valor_objetivo_usd: float
    valor_objetivo_ars: float
    delta_pp: float
    delta_valor_usd: float
    delta_valor_ars: float


class RebalanceoEje(BaseModel):
    eje: str
    total_usd: float
    total_ars: float
    items: list[RebalanceoItem]
    sin_objetivo: list[ExposicionItem]


class RebalanceoOut(BaseModel):
    ejes: list[RebalanceoEje]


class ConfiguracionCarteraOut(BaseModel):
    cartera: Optional[str] = None
    benchmark: Optional[str] = None
    rendimiento_objetivo: Optional[float] = None
    peso_maximo: Optional[float] = None
    peso_minimo: Optional[float] = None
    tolerancia: float  # ya resuelto con fallback (nunca None)


class RebalanceoSimulacionRequest(BaseModel):
    eje: str  # "Cartera" | "Tipo" | "Sector" | "Ticker"
    modo: str = "completo"  # "completo" | "solo_aportes"
    aporte_usd: float = 0.0
    tasa_comision_pct: Optional[float] = None  # None => usar estimación histórica


# ─── Escenarios (Simulador) ───────────────────────────────────────────────

class EscenarioParamsIn(BaseModel):
    horizonte_meses: int = Field(..., ge=1, le=600)
    variacion_dolar_pct: float = Field(0.0, ge=-90.0, le=500.0)
    variacion_por_instrumento: dict[str, float] = Field(default_factory=dict)
    variacion_por_defecto_pct: float = Field(0.0, ge=-95.0, le=500.0)
    aporte_mensual_usd: float = Field(0.0, ge=0.0)
    crecimiento_aporte_anual_pct: float = Field(0.0, ge=-50.0, le=100.0)
    retiro_mensual_usd: float = Field(0.0, ge=0.0)
    modo_dividendos: str = Field("reinvertir_total")
    dividend_yield_anual_pct: float = Field(0.0, ge=0.0, le=50.0)
    pct_dividendo_reinvertido: Optional[float] = Field(None, ge=0.0, le=100.0)
    comision_pct: float = Field(0.0, ge=0.0, le=10.0)
    inflacion_anual_pct: Optional[float] = Field(None, ge=0.0, le=1000.0)


class EscenarioSimulacionItem(BaseModel):
    tipo_preset: str
    nombre: Optional[str] = None
    parametros: Optional[EscenarioParamsIn] = None


class EscenarioSimulacionRequest(BaseModel):
    escenarios: list[EscenarioSimulacionItem] = Field(..., min_length=1, max_length=5)


class EscenarioPuntoOut(BaseModel):
    mes: int
    fecha: date
    valor_usd: float
    capital_aportado_acum_usd: float
    dividendos_acum_usd: float


class EscenarioResultadoOut(BaseModel):
    nombre: str
    tipo_preset: str
    puntos: list[EscenarioPuntoOut]
    patrimonio_inicial_usd: float
    patrimonio_final_usd: float
    ganancia_perdida_usd: float
    rendimiento_pct: float
    capital_aportado_usd: float
    efecto_mercado_usd: float
    efecto_dolar_usd: float
    dividendos_usd: float
    comisiones_usd: float
    patrimonio_final_real_usd: Optional[float] = None
    diferencia_vs_actual_usd: float
    es_simulado: bool = True


class EscenarioSimulacionOut(BaseModel):
    cartera: Optional[str]
    fecha_simulacion: datetime
    actual_valor_usd: float
    resultados: list[EscenarioResultadoOut]
    advertencias: list[str] = Field(default_factory=list)


class EscenarioGuardarRequest(BaseModel):
    cartera: Optional[str] = None
    nombre: str = Field(..., min_length=1, max_length=80)
    tipo_preset: str
    parametros: EscenarioParamsIn


class EscenarioOut(BaseModel):
    id: int
    cartera: Optional[str]
    nombre: str
    tipo_preset: str
    parametros: EscenarioParamsIn
    fecha_creacion: datetime
    fecha_actualizacion: datetime


class PropuestaRebalanceoItem(BaseModel):
    tipo: str  # "ticker" | "categoria_sin_instrumento"
    posicion: Optional[str] = None
    categoria: str
    peso_actual_pct: float
    peso_objetivo_pct: float
    delta_pp: float
    valor_actual_usd: float
    valor_objetivo_usd: float
    importe_sugerido_usd: float
    accion: str  # "comprar" | "vender" | "mantener"
    necesidad: str  # "necesario" | "opcional"
    comision_estimada_usd: float
    motivo: str


class RebalanceoSimulacionOut(BaseModel):
    eje: str
    modo: str
    total_usd: float
    aporte_usd: float
    tasa_comision_pct: float
    tolerancia_pp: float
    peso_maximo_pp: Optional[float] = None
    peso_minimo_pp: Optional[float] = None
    items: list[PropuestaRebalanceoItem]
    total_comision_estimada_usd: float
    total_a_comprar_usd: float
    total_a_vender_usd: float
    sobrante_usd: float = 0.0


class MovimientoInversionOut(BaseModel):
    id: int
    fecha: date
    cartera: str
    ticker: str
    tipo_movimiento: str
    cantidad: Optional[float] = None
    precio: float
    moneda: str
    comision: float

    model_config = {"from_attributes": True}


class EvolucionPunto(BaseModel):
    fecha: date
    valor_usd: float
    valor_ars: float
    valor_ars_real: Optional[float] = None
    capital_aportado_usd: float = 0.0
    capital_aportado_ars: float = 0.0
    capital_aportado_ars_real: Optional[float] = None


class EvolucionOut(BaseModel):
    puntos: list[EvolucionPunto]


class RendimientoMensualItem(BaseModel):
    anio: int
    mes: int
    twr_ars: Optional[float] = None
    twr_usd: Optional[float] = None
    en_curso: bool = False


class RendimientoAnualItem(BaseModel):
    anio: int
    twr_ars: Optional[float] = None
    twr_usd: Optional[float] = None
    en_curso: bool = False


class RendimientoMensualOut(BaseModel):
    meses: list[RendimientoMensualItem]
    anios: list[RendimientoAnualItem]


class PatrimonioPunto(BaseModel):
    fecha: date
    valor_usd: float
    valor_ars: float
    valor_ars_real: Optional[float] = None
    aportes_acumulados_usd: float
    aportes_acumulados_ars: float
    aportes_acumulados_ars_real: Optional[float] = None
    dividendos_acumulados_usd: float
    dividendos_acumulados_ars: float
    dividendos_acumulados_ars_real: Optional[float] = None
    otros_ajustes_acumulados_usd: float
    otros_ajustes_acumulados_ars: float
    otros_ajustes_acumulados_ars_real: Optional[float] = None
    ganancia_usd: float
    ganancia_ars: float
    ganancia_ars_real: Optional[float] = None


class PatrimonioHistoryOut(BaseModel):
    puntos: list[PatrimonioPunto]


class PatrimonioMaximoOut(BaseModel):
    valor_usd: Optional[float] = None
    valor_ars: Optional[float] = None
    valor_ars_real: Optional[float] = None
    fecha: Optional[date] = None
    fecha_ars: Optional[date] = None
    fecha_ars_real: Optional[date] = None
    valor_actual_usd: Optional[float] = None
    valor_actual_ars: Optional[float] = None
    valor_actual_ars_real: Optional[float] = None
    drawdown_usd: Optional[float] = None
    drawdown_ars: Optional[float] = None
    drawdown_ars_real: Optional[float] = None


class PatrimonioDescomposicionOut(BaseModel):
    aportes_usd: float
    aportes_ars: float
    aportes_ars_real: Optional[float] = None
    rendimiento_usd: float
    rendimiento_ars: float
    rendimiento_ars_real: Optional[float] = None
    dividendos_usd: float
    dividendos_ars: float
    dividendos_ars_real: Optional[float] = None
    otros_ajustes_usd: float
    otros_ajustes_ars: float
    otros_ajustes_ars_real: Optional[float] = None


class PatrimonioSummaryOut(BaseModel):
    maximo: PatrimonioMaximoOut
    descomposicion: PatrimonioDescomposicionOut


class PrecioPunto(BaseModel):
    fecha: date
    precio: float
    moneda: str


class PrecioSerieOut(BaseModel):
    ticker: str
    puntos: list[PrecioPunto]


class RendimientoPorTickerItem(BaseModel):
    ticker: str
    nombre: str
    tipo_instrumento: str
    mercado: str
    moneda: str
    pais: Optional[str] = None
    sector: Optional[str] = None
    cantidad_actual: float
    precio_promedio: float
    precio_actual: float
    valor_invertido_usd: float
    valor_actual_usd: float
    valor_invertido_ars: float
    valor_actual_ars: float
    rendimiento_simple_usd: Optional[float] = None
    rendimiento_simple_ars: Optional[float] = None
    rendimiento_simple_ars_real: Optional[float] = None
    precio_promedio_ars_ajustado_cer: Optional[float] = None
    precio_actual_ars_ajustado_cer: Optional[float] = None
    objetivo_modo: Optional[str] = None
    objetivo_valor: Optional[float] = None
    precio_objetivo: Optional[float] = None
    pct_a_objetivo: Optional[float] = None
    objetivo_alcanzado: Optional[bool] = None
    stop_loss_modo: Optional[str] = None
    stop_loss_valor: Optional[float] = None
    precio_stop_loss: Optional[float] = None
    pct_a_stop_loss: Optional[float] = None
    stop_loss_disparado: Optional[bool] = None


# --- Objetivos de Inversión ---

class ObjetivoInversionOut(BaseModel):
    id: int
    cartera: str
    nombre: str
    icono: str
    monto_usd: float
    fecha_limite: date
    valor_actual_usd: float
    aporte_mensual_promedio_usd: float
    aporte_mensual_necesario_usd: Optional[float]
    aporte_mensual_esperado_usd: Optional[float]
    meses_restantes: int
    proyeccion_usd: float
    alcanzable: bool
    deficit_usd: float
    desviacion_usd: Optional[float]
    desviacion_pct: Optional[float]
    adelantado: Optional[bool]
    aportado_a_la_fecha_usd: Optional[float]
    esperado_a_la_fecha_usd: Optional[float]

    model_config = {"from_attributes": True}


class AportePunto(BaseModel):
    mes: str
    aportes_netos_acumulados: float


class AportesHistoricosOut(BaseModel):
    curva: list[AportePunto]
    valor_actual_usd: float


class PrecioHistoricoPunto(BaseModel):
    fecha: date
    precio_nominal: float
    precio_usd: Optional[float] = None
    precio_cer: Optional[float] = None


class PrecioHistoricoOut(BaseModel):
    ticker: str
    moneda: str
    puntos: list[PrecioHistoricoPunto]


class TickerConPrecioItem(BaseModel):
    ticker: str
    nombre: str
    moneda: str


# --- Indicadores macro (CER/MEP) ---

class IndiceMercadoPunto(BaseModel):
    fecha: date
    cer: Optional[float] = None
    mep: Optional[float] = None


class IndicesMercadoOut(BaseModel):
    puntos: list[IndiceMercadoPunto]
    variacion_cer_pct: Optional[float] = None
    variacion_mep_pct: Optional[float] = None


# --- Vencimientos ---

class VencimientoItem(BaseModel):
    ticker: str
    nombre: str
    fecha_vencimiento: date
    dias_restantes: int
    vencido: bool
    cantidad_actual: float
    # None cuando el instrumento no tiene cotización cargada: el vencimiento igual se informa.
    valor_actual_usd: float | None = None
    valor_actual_ars: float | None = None
    moneda: str
    # Métricas de bono estimadas sobre el flujo de caja inferido (ver flujo_caja_analytics).
    # Todas None si no hay cupones cobrados de los que inferir, o si falta precio.
    tir_vencimiento: float | None = None       # TIR anual (decimal) al vencimiento
    duration_macaulay: float | None = None     # años
    duration_modificada: float | None = None   # años
    paridad: float | None = None               # precio / valor técnico
    valor_tecnico: float | None = None          # por unidad, en moneda_metricas
    interes_corrido: float | None = None        # por unidad
    valor_residual: float | None = None         # por unidad, base par = 1
    moneda_metricas: str | None = None
    metricas_estimadas: bool = False
    metricas_nota: str | None = None


class VencimientoAnioItem(BaseModel):
    anio: int
    valor_usd: float
    valor_ars: float
    pct_cartera_usd: float | None = None
    pct_cartera_ars: float | None = None
    cantidad_instrumentos: int
    instrumentos_sin_valuar: int
    tickers: list[str]


class VencimientosOut(BaseModel):
    generado: date
    items: list[VencimientoItem]
    por_anio: list[VencimientoAnioItem]
    cartera_valor_usd: float
    cartera_valor_ars: float


# --- Flujo de caja proyectado (renta fija) ---

class FlujoCajaCobroDetalle(BaseModel):
    ticker: str
    nombre: str
    tipo: str  # "cupon" | "amortizacion"
    moneda: str
    monto_nativo: float
    monto_usd: float
    monto_ars: float


class FlujoCajaMes(BaseModel):
    periodo: str  # "YYYY-MM"
    cupones_usd: float
    cupones_ars: float
    amortizaciones_usd: float
    amortizaciones_ars: float
    total_usd: float
    total_ars: float
    detalle: list[FlujoCajaCobroDetalle]


class FlujoCajaProximoCobro(BaseModel):
    fecha: date
    tipo: str
    monto_usd: float
    monto_ars: float


class FlujoCajaInstrumento(BaseModel):
    ticker: str
    nombre: str
    moneda: str
    cantidad_actual: float
    fecha_vencimiento: date
    periodicidad_meses: int | None = None
    periodicidad_label: str | None = None
    cupon_por_unidad: float | None = None
    confianza: str | None = None  # "alta" | "media" | "baja"
    metodo_capital: str  # "bullet" | "amortizacion_inferida" | "sin_estimacion"
    cobros_proyectados: int
    proximo_cobro: FlujoCajaProximoCobro | None = None
    total_proyectado_usd: float
    total_proyectado_ars: float
    notas: list[str]


class FlujoCajaSinProyeccion(BaseModel):
    ticker: str
    nombre: str
    fecha_vencimiento: date
    motivo: str


class FlujoCajaProyectadoOut(BaseModel):
    horizonte_meses: int
    generado: date
    total_cupones_usd: float
    total_cupones_ars: float
    total_amortizaciones_usd: float
    total_amortizaciones_ars: float
    total_usd: float
    total_ars: float
    meses: list[FlujoCajaMes]
    instrumentos: list[FlujoCajaInstrumento]
    sin_proyeccion: list[FlujoCajaSinProyeccion]


# --- Comisiones ---

class ComisionPorCarteraItem(BaseModel):
    etiqueta: str
    total_usd: float
    total_ars: float


class ComisionPorTickerItem(BaseModel):
    ticker: str
    nombre: str
    total_usd: float
    total_ars: float


class ComisionPeriodoItem(BaseModel):
    periodo: str
    total_usd: float
    total_ars: float


class ComisionesOut(BaseModel):
    total_usd: float
    total_ars: float
    movimientos_con_comision: int
    por_cartera: list[ComisionPorCarteraItem]
    por_ticker: list[ComisionPorTickerItem]
    por_mes: list[ComisionPeriodoItem]
    por_anio: list[ComisionPeriodoItem]


# --- P&L Realizado vs No Realizado ---

class PnlConsolidado(BaseModel):
    realizado_usd: float
    no_realizado_usd: float
    ingresos_usd: float
    total_usd: float
    realizado_ars: float
    no_realizado_ars: float
    ingresos_ars: float
    total_ars: float
    realizado_ars_real: Optional[float] = None
    no_realizado_ars_real: Optional[float] = None
    ingresos_ars_real: Optional[float] = None
    total_ars_real: Optional[float] = None


class PnlPorTickerItem(BaseModel):
    ticker: str
    nombre: str
    realizado_usd: float
    no_realizado_usd: float
    ingresos_usd: float
    total_usd: float
    realizado_ars: float
    no_realizado_ars: Optional[float] = None
    ingresos_ars: float
    total_ars: Optional[float] = None


class PnlRealizadoNoRealizadoOut(BaseModel):
    consolidado: PnlConsolidado
    por_ticker: list[PnlPorTickerItem]


# --- Vista fiscal por año ---

class VistaFiscalTickerItem(BaseModel):
    ticker: str
    nombre: str
    realizado_usd: float
    realizado_ars: float
    ingresos_usd: float
    ingresos_ars: float
    comisiones_usd: float
    comisiones_ars: float


class VistaFiscalAnioItem(BaseModel):
    anio: int
    realizado_usd: float
    realizado_ars: float
    ingresos_usd: float
    ingresos_ars: float
    comisiones_usd: float
    comisiones_ars: float
    resultado_usd: float
    resultado_ars: float
    por_ticker: list[VistaFiscalTickerItem]


class VistaFiscalTotal(BaseModel):
    realizado_usd: float
    realizado_ars: float
    ingresos_usd: float
    ingresos_ars: float
    comisiones_usd: float
    comisiones_ars: float
    resultado_usd: float
    resultado_ars: float


class VistaFiscalPorAnioOut(BaseModel):
    por_anio: list[VistaFiscalAnioItem]
    total: VistaFiscalTotal


# --- Riesgo ---

class DrawdownPunto(BaseModel):
    fecha: date
    drawdown: float


class DrawdownOut(BaseModel):
    estado: str
    actual: Optional[float] = None
    maximo: Optional[float] = None
    fecha_pico: Optional[date] = None
    fecha_valle: Optional[date] = None
    en_recuperacion: Optional[bool] = None
    tiempo_recuperacion_meses: Optional[int] = None
    serie: list[DrawdownPunto] = []


class VolatilidadOut(BaseModel):
    estado: str
    mensual: Optional[float] = None
    anualizada: Optional[float] = None
    n_obs: int


class SharpeOut(BaseModel):
    estado: str
    valor: Optional[float] = None
    benchmark: Optional[str] = None
    n_obs: int


class SortinoOut(BaseModel):
    estado: str
    valor: Optional[float] = None
    n_obs: int


class CalmarOut(BaseModel):
    estado: str
    valor: Optional[float] = None
    retorno_anualizado: Optional[float] = None


class PeriodoRetorno(BaseModel):
    anio: int
    mes: int
    retorno: float


class FrecuenciaOut(BaseModel):
    estado: str
    pct_positivos: Optional[float] = None
    pct_negativos: Optional[float] = None
    n_obs: int


class RiesgoOut(BaseModel):
    frecuencia: str = "mensual"
    moneda: str
    benchmark_usado: Optional[str] = None
    n_meses_historia: int
    drawdown: DrawdownOut
    volatilidad: VolatilidadOut
    sharpe: SharpeOut
    sortino: SortinoOut
    calmar: CalmarOut
    benchmark_retorno_anualizado: Optional[float] = None
    mejores_periodos: list[PeriodoRetorno]
    peores_periodos: list[PeriodoRetorno]
    frecuencia_positivos_negativos: FrecuenciaOut


# --- Performance Relativa (vs Benchmark) ---

class MetricaRelativaOut(BaseModel):
    estado: str
    valor: Optional[float] = None
    n_obs: int = 0


class PerformanceRelativaPunto(BaseModel):
    fecha: date
    indice_cartera: float
    indice_benchmark: float


class PerformanceRelativaOut(BaseModel):
    estado: str
    moneda: str
    benchmark_usado: Optional[str] = None
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    n_meses_historia: int
    retorno_cartera_pct: Optional[float] = None
    retorno_benchmark_pct: Optional[float] = None
    delta_pp: Optional[float] = None
    costo_oportunidad_pp: Optional[float] = None
    exceso_retorno: MetricaRelativaOut
    alpha: MetricaRelativaOut
    beta: MetricaRelativaOut
    tracking_error: MetricaRelativaOut
    information_ratio: MetricaRelativaOut
    serie: list[PerformanceRelativaPunto] = []


# --- Contribución, concentración y correlaciones ---

class ContribucionItem(BaseModel):
    etiqueta: str
    peso_promedio_pct: float
    pnl_usd: float
    costo_total_usd: float
    rentabilidad_pct: Optional[float] = None
    contribucion_pct: float


class ContribucionEje(BaseModel):
    eje: str
    items: list[ContribucionItem]


class ConcentracionItem(BaseModel):
    eje: str
    estado: str
    hhi: Optional[float] = None
    hhi_normalizado: Optional[float] = None
    effective_n: Optional[float] = None
    n_componentes: int


class ContribucionOut(BaseModel):
    contribucion: list[ContribucionEje]
    concentracion: list[ConcentracionItem]


class CorrelacionParItem(BaseModel):
    ticker_a: str
    ticker_b: str
    valor: Optional[float] = None
    n_obs: int
    estado: str


class CorrelacionesOut(BaseModel):
    universo: str
    n_tickers: int
    tickers: list[str]
    matriz: list[list[Optional[float]]]
    pares: list[CorrelacionParItem]
    advertencia_historial_corto: bool


# --- Diagnóstico ---

class HallazgoItem(BaseModel):
    tipo: str
    severidad: str
    titulo: str
    explicacion: str
    dato_disparador: dict[str, float | int | str | bool | None]
    pantalla: str
    fecha_calculo: date


class DimensionScore(BaseModel):
    nombre: str
    score: Optional[float] = None
    peso: float
    estado: str
    detalle: str


class SaludCarteraOut(BaseModel):
    score_total: Optional[float] = None
    dimensiones: list[DimensionScore]
    fecha_calculo: date


class DiagnosticoOut(BaseModel):
    cartera: Optional[str] = None
    salud: SaludCarteraOut
    hallazgos: list[HallazgoItem]
    fecha_calculo: date


# --- Descomposición FX ---

class DescomposicionFxOut(BaseModel):
    estado: str  # "ok" | "datos_insuficientes" | "mep_faltante"
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    retorno_total_ars_pct: Optional[float] = None
    retorno_activo_pct: Optional[float] = None
    efecto_fx_pct: Optional[float] = None
    mep_inicio: Optional[float] = None
    mep_fin: Optional[float] = None
    mep_aproximado: bool = False
    identidad_verificada: bool = True


class DescomposicionFxPosicionItem(BaseModel):
    ticker: str
    moneda: str
    estado: str  # "ok" | "datos_insuficientes" | "mep_faltante" | "moneda_desconocida"
    rendimiento_simple_ars_pct: Optional[float] = None
    rendimiento_simple_usd_pct: Optional[float] = None
    efecto_fx_pct: Optional[float] = None
    retorno_activo_pct: Optional[float] = None
    aproximado: bool = True


class DescomposicionFxPosicionOut(BaseModel):
    posiciones: list[DescomposicionFxPosicionItem]


# --- Análisis profundo por ticker ---

class TickerPositionOut(InversionesResumen):
    """Resumen + metadata de posición por ticker."""
    ticker: str
    nombre: str
    tipo_instrumento: str
    mercado: str
    moneda: str
    pais: Optional[str] = None
    sector: Optional[str] = None
    cantidad_actual: float
    precio_promedio: float
    precio_actual: Optional[float] = None
    primera_fecha_movimiento: Optional[date] = None
    ultima_fecha_movimiento: Optional[date] = None
    posicion_cerrada: bool
    objetivo_modo: Optional[str] = None
    objetivo_valor: Optional[float] = None
    precio_objetivo: Optional[float] = None
    pct_a_objetivo: Optional[float] = None
    objetivo_alcanzado: Optional[bool] = None
    stop_loss_modo: Optional[str] = None
    stop_loss_valor: Optional[float] = None
    precio_stop_loss: Optional[float] = None
    pct_a_stop_loss: Optional[float] = None
    stop_loss_disparado: Optional[bool] = None


class TickerPerformanceOut(PnlPorTickerItem):
    """PnL + comisiones por ticker."""
    comisiones_usd: float
    comisiones_ars: float
    precio_actual_faltante: bool = False


class TickerAnalysisOut(BaseModel):
    """Response del endpoint /ticker/{ticker}/analysis (eager)."""
    position: TickerPositionOut
    performance: TickerPerformanceOut


class TickerHistoricoPunto(BaseModel):
    fecha: date
    precio_nominal: float
    precio_usd: Optional[float] = None
    precio_cer: Optional[float] = None
    valor_posicion_usd: Optional[float] = None
    valor_posicion_ars: Optional[float] = None
    rendimiento_acumulado_pct: Optional[float] = None


class TickerHistoricoOut(BaseModel):
    """Response del endpoint /ticker/{ticker}/historico (lazy)."""
    ticker: str
    moneda: str
    puntos: list[TickerHistoricoPunto]


class TickerRiesgoOut(RiesgoOut):
    """Response del endpoint /ticker/{ticker}/riesgo (lazy). Reusa RiesgoOut tal cual."""
    pass


class TickerPerformanceRelativaOut(PerformanceRelativaOut):
    """Response del endpoint /ticker/{ticker}/performance-relativa (lazy). Reusa PerformanceRelativaOut tal cual."""
    pass


# --- Comparación de Benchmarks y Costo de Oportunidad ---

class ComparacionBenchmarkOut(BaseModel):
    fuente: str
    tipo: str
    estado: str
    retorno_pct: Optional[float] = None
    delta_pp: Optional[float] = None
    valor_final_equivalente_usd: Optional[float] = None
    valor_final_equivalente_ars: Optional[float] = None
    ranking: Optional[int] = None
    n_meses_historia: int = 0


class PerformanceCompareOut(BaseModel):
    estado: str
    moneda: str
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    filas: list[ComparacionBenchmarkOut] = []
    serie: list[dict[str, Any]] = []


class OpportunityCostPosicionOut(BaseModel):
    ticker: str
    nombre: str
    valor_actual_usd: float
    valor_shadow_usd: float
    costo_oportunidad_usd: float
    costo_oportunidad_ars: float


class OpportunityCostOut(BaseModel):
    estado: str
    benchmark_usado: Optional[str] = None
    moneda_nativa_benchmark: Optional[str] = None
    valor_actual_usd: Optional[float] = None
    valor_actual_ars: Optional[float] = None
    valor_shadow_usd: Optional[float] = None
    valor_shadow_ars: Optional[float] = None
    costo_oportunidad_usd: Optional[float] = None
    costo_oportunidad_ars: Optional[float] = None
    por_posicion: list[OpportunityCostPosicionOut] = []
