from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
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
    serie_ohlcv: int = 0
    iol_llamadas: int = 0        # llamadas a la API de IOL que gastó esta corrida
    iol_llamadas_mes: int = 0    # acumulado del mes calendario en curso
    iol_limite_mes: int = 0      # tope mensual configurado (IOL_LIMITE_MENSUAL)
    health_score: int
    resultado: str
    duration_ms: int
    timestamp: datetime
    issues: list[SyncIssueOut]


class IolEstadoOut(BaseModel):
    """Consumo de la API de IOL sin necesidad de correr un sync. `restante` es contra el cupo
    mensual bonificado (25.000); `limite`/`limite_por_sync` son los topes configurados."""
    periodo: str            # "YYYY-MM" (UTC)
    llamadas: int           # acumulado del mes calendario en curso
    limite: int             # IOL_LIMITE_MENSUAL
    restante: int           # max(0, limite - llamadas)
    limite_por_sync: int    # IOL_MAX_LLAMADAS_POR_SYNC (0 = sin cota por corrida)
    habilitada: bool        # IOL_ENABLED


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


class HistorialSyncItem(BaseModel):
    timestamp: datetime
    health_score: int
    resultado: str
    filas_advertencia: int
    filas_error: int


class ReglaRecurrenteItem(BaseModel):
    regla: str
    tab: str
    severidad: str
    mensaje_muestra: str
    apariciones: int
    en_ultimo_sync: bool


class CalidadDatosOut(BaseModel):
    ultimo_sync: Optional[SyncRunResumenOut] = None
    issues: list[SyncIssueOut]
    issues_por_tab: dict[str, list[SyncIssueOut]]
    historial: list[HistorialSyncItem] = []
    reglas_recurrentes: list[ReglaRecurrenteItem] = []
    total_syncs: int = 0


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
    # XIRR reexpresado como retorno acumulado del período, comparable contra el TWR
    # (que no viene anualizado).
    xirr_usd_periodo: Optional[float] = None
    xirr_ars_periodo: Optional[float] = None
    xirr_ars_real_periodo: Optional[float] = None
    dias_periodo: int = 0
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


# --- Descomposición de cartera (árbol Familia → País → Sector → Ticker) ---

class DescomposicionNodo(BaseModel):
    clave: str
    etiqueta: str
    nivel: str
    valor_usd: float
    valor_ars: float
    porcentaje: float          # sobre el total de la cartera (estable al bajar de nivel)
    porcentaje_padre: float    # sobre el nodo padre (suma 100% entre hermanos)
    instrumentos: int
    sin_clasificar: bool = False
    tipo_instrumento: Optional[str] = None  # sólo en hojas (nivel Ticker)
    nombre: Optional[str] = None            # sólo en hojas (nivel Ticker)
    hijos: list["DescomposicionNodo"] = Field(default_factory=list)


class DescomposicionOut(BaseModel):
    niveles: list[str]
    total_usd: float
    total_ars: float
    instrumentos: int
    raiz: list[DescomposicionNodo]
    posiciones_sin_precio: list[str] = Field(default_factory=list)


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


# ─── Escenarios de vida (Simulador sencillo) ──────────────────────────────

class SupuestosVidaIn(BaseModel):
    patrimonio_inicial: float = Field(..., ge=0.0, le=1e12)
    aporte_mensual: float = Field(0.0, ge=0.0, le=1e9)
    crecimiento_anual_pct: float = Field(0.0, ge=-95.0, le=100.0)
    horizonte_meses: int = Field(120, ge=1, le=600)
    moneda: str = Field("USD")
    inflacion_anual_pct: Optional[float] = Field(None, ge=0.0, le=1000.0)


class EscenarioVidaIn(BaseModel):
    tipo: str
    monto: Optional[float] = Field(None, ge=0.0, le=1e12)
    pct: Optional[float] = Field(None, ge=0.0, le=500.0)
    mes: Optional[int] = Field(None, ge=1, le=600)


class EscenarioVidaRequest(BaseModel):
    supuestos: SupuestosVidaIn
    escenarios: list[EscenarioVidaIn] = Field(..., min_length=1, max_length=6)


class PuntoVidaOut(BaseModel):
    mes: int
    fecha: date
    valor: float
    valor_real: Optional[float] = None
    aportado_acum: float


class MetricasVidaOut(BaseModel):
    patrimonio_final: float
    patrimonio_final_real: Optional[float] = None
    aportes_periodo: float
    crecimiento_estimado: float
    diferencia_vs_base: float
    diferencia_vs_base_pct: Optional[float] = None


class EscenarioVidaResultadoOut(BaseModel):
    tipo: str
    nombre: str
    descripcion: str
    es_base: bool
    aporte_mensual_efectivo: float
    crecimiento_aporte_anual_pct: float
    mes_flujo_extraordinario: Optional[int] = None
    monto_flujo_extraordinario: Optional[float] = None
    se_agota_en_mes: Optional[int] = None
    puntos: list[PuntoVidaOut]
    metricas: MetricasVidaOut
    advertencias: list[str] = Field(default_factory=list)
    es_simulado: bool = True


class EscenarioVidaOut(BaseModel):
    cartera: Optional[str]
    fecha_simulacion: datetime
    moneda: str
    supuestos: SupuestosVidaIn
    resultados: list[EscenarioVidaResultadoOut]  # resultados[0] es siempre la base
    disclaimer: str
    advertencias: list[str] = Field(default_factory=list)


class DefaultsVidaOut(BaseModel):
    cartera: Optional[str]
    patrimonio_inicial_usd: float
    aporte_mensual_usd: Optional[float]
    origen_aporte: str  # "promedio_12m" | "promedio_historico" | "sin_datos"
    meses_historia: int
    moneda_sugerida: str = "USD"
    crecimiento_anual_pct_sugerido: float = 0.0
    horizonte_meses_sugerido: int = 120
    advertencias: list[str] = Field(default_factory=list)


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



# --- Watchlist ---

class WatchlistItemOut(BaseModel):
    """Un instrumento seguido y su distancia a la zona de compra.

    `pct_a_objetivo` es `(objetivo - precio_actual) / precio_actual`, el mismo criterio que
    `pct_a_stop_loss`: negativo mientras el precio esté por encima del objetivo (todavía caro),
    cero o positivo una vez que entró en zona. El frontend usa el valor absoluto como distancia.
    """
    ticker: str
    nombre: str
    tipo_instrumento: str
    mercado: str
    moneda: str
    pais: Optional[str] = None
    sector: Optional[str] = None
    precio_actual: Optional[float] = None
    fecha_precio: Optional[date] = None
    moneda_precio: Optional[str] = None
    fuente_precio: Optional[str] = None  # "cartera" | "iol" | "api"
    precio_objetivo: Optional[float] = None
    pct_a_objetivo: Optional[float] = None
    en_zona: Optional[bool] = None
    en_cartera: bool = False
    notas: Optional[str] = None
    agregado_en: Optional[date] = None


class WatchlistItemIn(BaseModel):
    """Alta: `ticker` tiene que ser un símbolo del catálogo de IOL (404 si no está)."""
    ticker: str
    objetivo: Optional[float] = Field(default=None, gt=0)
    notas: Optional[str] = Field(default=None, max_length=500)


class WatchlistItemUpdate(BaseModel):
    """Edición: sólo lo que controla el usuario. El resto lo define el catálogo."""
    objetivo: Optional[float] = Field(default=None, gt=0)
    notas: Optional[str] = Field(default=None, max_length=500)


class RefrescoPreciosOut(BaseModel):
    actualizados: int
    issues: list[str] = []


# --- Catálogo de instrumentos (IOL) ---

class CatalogoInstrumentoOut(BaseModel):
    simbolo: str
    descripcion: str
    tipo: str  # "Acción" | "CEDEAR" | "Bono" | "ON" | "Letra" | "FCI" | ""
    moneda: str
    mercado: str
    paneles: list[str] = []


class CatalogoBusquedaOut(BaseModel):
    """`total` y `conteos_por_tipo` se calculan sobre todo lo que matchea la búsqueda, sin aplicar
    el filtro de tipo ni el límite: son lo que los chips del frontend muestran como conteo."""
    total: int
    conteos_por_tipo: dict[str, int]
    items: list[CatalogoInstrumentoOut]


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
    riesgo_pais: Optional[float] = None


class InflacionMensualPunto(BaseModel):
    fecha: date
    valor_pct: float


class IndicesMercadoOut(BaseModel):
    puntos: list[IndiceMercadoPunto]
    variacion_cer_pct: Optional[float] = None
    variacion_mep_pct: Optional[float] = None
    variacion_riesgo_pais_pct: Optional[float] = None
    inflacion_mensual: list[InflacionMensualPunto] = []


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


# --- Ritmo de aportes (services/aportes_engine.py) ---

class AporteMesItem(BaseModel):
    mes: str  # "YYYY-MM"
    neto_usd: float
    compras_usd: float
    salidas_usd: float
    en_curso: bool
    futuro: bool = False
    con_aporte: bool
    promedio_movil_3_usd: Optional[float] = None


class AporteComparacion(BaseModel):
    referencia_usd: float
    delta_usd: float
    delta_pct: Optional[float] = None
    delta_proyectado_usd: Optional[float] = None
    delta_proyectado_pct: Optional[float] = None


class AporteEsteMes(BaseModel):
    mes: str
    neto_usd: float
    compras_usd: float
    salidas_usd: float
    dia: int
    dias_mes: int
    dias_restantes: int
    proyeccion_usd: float
    proyeccion_fiable: bool
    es_record_parcial: bool
    vs_mes_anterior: Optional[AporteComparacion] = None
    vs_promedio_3: Optional[AporteComparacion] = None
    vs_promedio_6: Optional[AporteComparacion] = None
    vs_promedio_12: Optional[AporteComparacion] = None
    vs_mismo_mes_anio_anterior: Optional[AporteComparacion] = None


class AporteProyeccionAnual(BaseModel):
    clave: Literal["este_mes", "promedio_3", "promedio_ytd"]
    etiqueta: str
    ritmo_mensual_usd: Optional[float] = None
    total_fin_anio_usd: Optional[float] = None


class AporteAnioEnCurso(BaseModel):
    anio: int
    ytd_usd: float
    meses_cerrados: int
    meses_restantes: int
    promedio_mensual_ytd_usd: Optional[float] = None
    anio_anterior_total_usd: Optional[float] = None
    vs_mismo_periodo_anio_anterior: Optional[AporteComparacion] = None
    proyecciones: list[AporteProyeccionAnual]


class AporteRacha(BaseModel):
    meses: int
    desde: Optional[str] = None
    hasta: Optional[str] = None
    incluye_mes_en_curso: bool = False


class AporteRachas(BaseModel):
    aportando_actual: AporteRacha
    aportando_record: AporteRacha
    sin_aportar_actual: int
    sobre_promedio_12_actual: Optional[int] = None
    direccion: Literal["subiendo", "bajando", "ninguna"]
    direccion_meses: int
    meses_sin_aportar_ultimos_12: int
    meses_considerados_ultimos_12: int


class AporteMesRef(BaseModel):
    mes: str
    neto_usd: float


class AporteNivel(BaseModel):
    nivel: Literal["bien", "atencion", "riesgo"]
    etiqueta: str


class AporteEstadisticas(BaseModel):
    meses_historia: int
    meses_con_aporte: int
    meses_con_retiro: int
    total_neto_usd: float
    total_compras_usd: float
    total_salidas_usd: float
    promedio_usd: Optional[float] = None
    mediana_usd: Optional[float] = None
    desvio_usd: Optional[float] = None
    coef_variacion: Optional[float] = None
    constancia: Optional[AporteNivel] = None
    promedio_3_usd: Optional[float] = None
    promedio_6_usd: Optional[float] = None
    promedio_12_usd: Optional[float] = None
    mejor_mes: Optional[AporteMesRef] = None
    peor_mes: Optional[AporteMesRef] = None
    mejor_mes_anio: Optional[AporteMesRef] = None
    peor_mes_anio: Optional[AporteMesRef] = None


class AporteEstadoRitmo(BaseModel):
    estado: Literal["arrancando", "acelerando", "sostenido", "frenando", "parado"]
    etiqueta: str
    nivel: Literal["bien", "atencion", "riesgo"]
    detalle: str
    tendencia_3v3_pct: Optional[float] = None
    tendencia_6v6_pct: Optional[float] = None
    promedio_3_usd: Optional[float] = None
    promedio_3_anterior_usd: Optional[float] = None
    promedio_6_usd: Optional[float] = None
    promedio_6_anterior_usd: Optional[float] = None


class AporteAnioItem(BaseModel):
    anio: int
    total_usd: float
    compras_usd: float
    salidas_usd: float
    promedio_mensual_usd: Optional[float] = None
    meses_con_aporte: int
    meses_en_rango: int
    var_vs_anio_anterior_pct: Optional[float] = None
    en_curso: bool
    mejor_mes: Optional[AporteMesRef] = None


class AporteAnioRef(BaseModel):
    anio: int
    total_usd: float


class AporteHito(BaseModel):
    clave: str
    titulo: str
    descripcion: str
    fecha: str  # "YYYY-MM"
    reciente: bool


class AporteProximoHito(BaseModel):
    clave: str
    titulo: str
    unidad: Literal["usd", "meses"]
    valor_objetivo: float
    valor_actual: float
    falta: float
    progreso_pct: float


class AporteMensaje(BaseModel):
    clave: str
    tono: Literal["positivo", "neutro", "negativo"]
    titulo: str
    detalle: str


class RitmoAportesOut(BaseModel):
    estado: Literal["ok", "sin_datos"]
    hoy: date
    primer_mes: Optional[str] = None
    movimientos_omitidos_sin_mep: int = 0
    serie_mensual: list[AporteMesItem]
    por_anio: list[AporteAnioItem]
    mejor_anio: Optional[AporteAnioRef] = None
    este_mes: Optional[AporteEsteMes] = None
    anio_en_curso: Optional[AporteAnioEnCurso] = None
    rachas: Optional[AporteRachas] = None
    estadisticas: Optional[AporteEstadisticas] = None
    estado_ritmo: Optional[AporteEstadoRitmo] = None
    hitos_alcanzados: list[AporteHito]
    proximos_hitos: list[AporteProximoHito]
    mensajes: list[AporteMensaje]


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
    no_realizado_usd: Optional[float] = None
    ingresos_usd: float
    total_usd: Optional[float] = None
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


# --- Matriz de correlaciones (services/correlaciones_analytics.py) ---
# Pantalla dedicada, distinta de CorrelacionesOut (que sigue sirviendo a Contribución): soporta
# frecuencia diaria/semanal/mensual, período e instrumentos elegibles. `estado` + `advertencias`
# siguen la misma convención que CostoOportunidadOut: la falta de datos nunca es un error HTTP.

class MatrizCorrelacionParItem(BaseModel):
    ticker_a: str
    ticker_b: str
    valor: Optional[float] = None
    n_obs: int
    solapamiento_pct: Optional[float] = None
    estado: str
    motivo: str  # "ok" | "sin_solapamiento" | "menos_de_min_obs" | "serie_constante"


class MatrizCorrelacionTickerItem(BaseModel):
    ticker: str
    n_retornos: int
    cobertura_pct: Optional[float] = None
    primer_periodo: Optional[date] = None
    ultimo_periodo: Optional[date] = None


class MatrizCorrelacionDescartadoItem(BaseModel):
    ticker: str
    motivo: str  # "sin_precios" | "tope_tickers"


class MatrizCorrelacionRankingOut(BaseModel):
    mas_correlacionados: list[MatrizCorrelacionParItem] = Field(default_factory=list)
    menos_correlacionados: list[MatrizCorrelacionParItem] = Field(default_factory=list)
    mas_negativos: list[MatrizCorrelacionParItem] = Field(default_factory=list)


class MatrizCorrelacionesOut(BaseModel):
    estado: str  # "ok" | "sin_tickers" | "sin_suficientes_tickers" | "datos_insuficientes"
    moneda: str = "USD"
    frecuencia_pedida: str
    frecuencia_efectiva: str
    min_obs: int
    periodo_pedido_desde: Optional[date] = None
    periodo_pedido_hasta: Optional[date] = None
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    n_periodos: int = 0
    n_periodos_posibles: int = 0
    tickers: list[str] = Field(default_factory=list)
    n_tickers: int = 0
    tickers_detalle: list[MatrizCorrelacionTickerItem] = Field(default_factory=list)
    tickers_descartados: list[MatrizCorrelacionDescartadoItem] = Field(default_factory=list)
    matriz: list[list[Optional[float]]] = Field(default_factory=list)
    pares: list[MatrizCorrelacionParItem] = Field(default_factory=list)
    n_pares: int = 0
    n_pares_ok: int = 0
    correlacion_promedio: Optional[float] = None
    nivel_diversificacion: Optional[str] = None  # "alta" | "media" | "baja"
    ranking: MatrizCorrelacionRankingOut = Field(default_factory=MatrizCorrelacionRankingOut)
    pocos_datos: bool = False
    advertencias: list[str] = Field(default_factory=list)


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


# --- Salud de cartera (services/salud_engine.py) ---
# A propósito no hay un score único acá (ver SaludCarteraOut arriba, que sí lo tiene): esta
# pantalla muestra un estado explicable por dimensión, sin combinarlos en un solo número.

class SaludIndicadorOut(BaseModel):
    clave: str
    nombre: str
    texto: str
    pantalla: str
    ayuda: str
    valor_usd: Optional[float] = None
    valor_ars: Optional[float] = None
    valor_pct: Optional[float] = None


class SaludDimensionOut(BaseModel):
    clave: str
    nombre: str
    estado: str
    etiqueta: str
    valor: str
    regla: str
    explicacion: str
    fuente: str
    pantalla: str
    ayuda: str


class SaludObservacionOut(BaseModel):
    id: str
    dimension: str
    severidad: str
    titulo: str
    detecto: str
    valor: str
    umbral: str
    fuente: str
    pantalla: str
    accion: str


class SaludResumenOut(BaseModel):
    n_revisar: int
    n_atencion: int
    n_normal: int
    n_sin_datos: int


class SaludCarteraEstadoOut(BaseModel):
    cartera: Optional[str] = None
    indicadores: list[SaludIndicadorOut]
    dimensiones: list[SaludDimensionOut]
    observaciones: list[SaludObservacionOut]
    exposicion_moneda: list[ExposicionItem]
    exposicion_tipo: list[ExposicionItem]
    resumen: SaludResumenOut
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


# --- Costo de oportunidad ---
# Comparación histórica de la cartera contra una referencia, en la misma moneda, en
# porcentaje y en dinero. A diferencia de OpportunityCostOut (sólo el valor final) y de
# PerformanceRelativaOut (no normaliza la moneda de la referencia), este schema es el de
# `/costo-oportunidad`. Vocabulario deliberado: "referencia", "resultado_*" — nada de
# "shadow" ni "hubieras", porque el vocabulario del payload termina filtrándose a la UI.

class CostoOportunidadIndicePuntoOut(BaseModel):
    fecha: date
    indice_cartera: Optional[float] = None
    indice_referencia: Optional[float] = None


class CostoOportunidadValorPuntoOut(BaseModel):
    fecha: date
    valor_cartera: Optional[float] = None
    valor_referencia: Optional[float] = None
    diferencia: Optional[float] = None


class CostoOportunidadOut(BaseModel):
    estado: str  # "ok" | "sin_benchmark" | "sin_movimientos" | "datos_insuficientes"
    moneda: str
    referencia: Optional[str] = None
    moneda_nativa_referencia: Optional[str] = None  # "ARS" | "USD" | "mixta"
    periodo_pedido_desde: Optional[date] = None
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    n_meses: int = 0
    resultado_cartera_pct: Optional[float] = None
    resultado_referencia_pct: Optional[float] = None
    diferencia_pp: Optional[float] = None  # (cartera - referencia) * 100
    valor_inicial: Optional[float] = None
    aportes_netos_periodo: Optional[float] = None
    valor_final_cartera: Optional[float] = None
    valor_final_referencia: Optional[float] = None
    diferencia_monetaria: Optional[float] = None  # cartera - referencia
    serie_indices: list[CostoOportunidadIndicePuntoOut] = []
    serie_valores: list[CostoOportunidadValorPuntoOut] = []
    advertencias: list[str] = []


# --- Análisis técnico ---

class SerieVarianteOut(BaseModel):
    variante: str  # "local" | "subyacente"
    moneda: str
    mercado: str = ""


class TickerTecnicoOut(BaseModel):
    ticker: str
    nombre: str
    moneda: str
    tipo_instrumento: str
    origen: str  # "cartera" | "watchlist" | "ambos"
    # Siempre incluye "local"; "subyacente" (USD) sólo si hay serie del subyacente bajada.
    series: list[SerieVarianteOut] = Field(default_factory=list)


class BarraOut(BaseModel):
    fecha: date
    cierre: float
    apertura: Optional[float] = None
    maximo: Optional[float] = None
    minimo: Optional[float] = None
    volumen: Optional[float] = None


class SerieTecnicaOut(BaseModel):
    ticker: str
    nombre: str
    moneda: str
    variante: str = "local"      # "local" | "subyacente"
    mercado: Optional[str] = None
    origen: Optional[str] = None
    fuente_serie: str  # "velas" | "mixta" | "sin_datos"
    tiene_velas: bool
    tiene_volumen: bool
    indice_desde: int
    barras: list[BarraOut]
    # clave = clave() del indicador (p.ej "SMA(50)"), valor = {salida: [valores...]}
    indicadores: dict[str, dict[str, list[Optional[float]]]] = Field(default_factory=dict)
    advertencias: list[str] = Field(default_factory=list)


class SenalOut(BaseModel):
    indice: int
    fecha: date
    tipo: str  # "compra" | "venta"
    precio: float
    motivo: str


class OperacionOut(BaseModel):
    indice_entrada: int
    indice_salida: Optional[int] = None
    fecha_entrada: date
    fecha_salida: Optional[date] = None
    precio_entrada: float
    precio_salida: Optional[float] = None
    barras: int
    retorno_bruto_pct: float
    retorno_neto_pct: float
    motivo_salida: Optional[str] = None
    abierta: bool
    # Niveles de riesgo vigentes durante la operación, calculados por el motor para que el gráfico
    # los dibuje sin reimplementar la regla. `trailing` arranca en `indice_entrada` y trae un valor
    # por barra consecutiva (puede terminar antes de `indice_salida` si la salida se ejecutó con
    # demora); `None` cuando la estrategia no configuró ese límite.
    nivel_stop_loss: Optional[float] = None
    nivel_take_profit: Optional[float] = None
    trailing: Optional[list[float]] = None


class BacktestMetricasOut(BaseModel):
    estado: str
    retorno_total_pct: float
    retorno_anualizado_pct: Optional[float] = None
    retorno_buy_hold_pct: float
    exceso_vs_buy_hold_pp: float
    operaciones: int
    operaciones_cerradas: int = 0
    retorno_abierta_pct: Optional[float] = None  # P&L no realizado de la operación abierta al final
    ganadoras: int
    perdedoras: int
    win_rate_pct: Optional[float] = None
    retorno_medio_operacion_pct: Optional[float] = None
    mejor_operacion_pct: Optional[float] = None
    peor_operacion_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    fecha_pico: Optional[date] = None
    fecha_valle: Optional[date] = None
    duracion_media_barras: Optional[float] = None
    exposicion_pct: float
    comisiones_pct_acum: float


class CurvaPuntoOut(BaseModel):
    fecha: date
    valor: float


class BacktestRequest(BaseModel):
    definicion: dict[str, Any]
    desde: Optional[date] = None
    hasta: Optional[date] = None
    # Variante de serie sobre la que correr el backtest. Va en el body (no en el path) para que la
    # clave `@SUB` nunca salga del backend y `_validar_ticker_tecnico` siga intacto.
    variante: str = "local"


class BacktestOut(BaseModel):
    ticker: str
    variante: str = "local"
    moneda: str = ""
    senales: list[SenalOut]
    operaciones: list[OperacionOut]
    metricas: BacktestMetricasOut
    curva_equity: list[CurvaPuntoOut]
    curva_buy_hold: list[CurvaPuntoOut]
    primera_barra_evaluable: Optional[int] = None
    # Serie de barras usada por el backtest (incluye el warm-up previo a `desde`) y las series de
    # indicadores ya calculadas, keyed por el `id` del indicador en la definición. Alineadas 1:1
    # con `curva_equity` y con `senales[].indice`, para poder dibujar velas + indicadores + señales.
    barras: list[BarraOut] = Field(default_factory=list)
    indicadores: dict[str, dict[str, list[Optional[float]]]] = Field(default_factory=dict)
    # Índice en `barras` donde arranca el rango pedido (`desde`); lo previo es warm-up de indicadores.
    indice_desde: int = 0
    advertencias: list[str] = Field(default_factory=list)


class PresetEstrategiaOut(BaseModel):
    nombre: str                 # slug estable, el que viaja en `EstrategiaOut.tipo_preset`
    etiqueta: str               # nombre legible, el que se muestra en el selector
    categoria: str              # "tendencia" | "reversion" | "ruptura" | "momentum"
    definicion: dict[str, Any]
    # El motor degrada solo si faltan: son para avisar en la UI que sobre esta serie la estrategia
    # no mide lo que promete (sin OHLC el canal usa cierres; sin volumen el filtro nunca se cumple).
    requiere_velas: bool = False
    requiere_volumen: bool = False


class SiembraPresetsOut(BaseModel):
    creadas: int
    actualizadas: int
    sin_cambios: int


class SenalTickerOut(BaseModel):
    ticker: str
    estrategia_id: int
    estrategia_nombre: str
    tipo: str  # "compra" | "venta"
    fecha: date
    precio: float
    motivo: str
    barras_desde: int
    variante: str = "local"
    moneda: str = ""


class EstrategiaGuardarRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=80)
    descripcion: Optional[str] = None
    ticker: Optional[str] = None
    tipo_preset: Optional[str] = None
    definicion: dict[str, Any]
    variante: str = "local"


class EstrategiaOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    ticker: Optional[str] = None
    tipo_preset: Optional[str] = None
    definicion: dict[str, Any]
    variante: str = "local"
    fecha_creacion: datetime
    fecha_actualizacion: datetime


# ─── Screener ───────────────────────────────────────────────────────────────

class ScreenerRequest(BaseModel):
    # Vacío = todas las estrategias guardadas.
    estrategia_ids: list[int] = Field(default_factory=list)
    umbral_pct: float = Field(3.0, gt=0, le=15)
    origen: str = "todos"  # "todos" | "cartera" | "watchlist" — filtra el universo de tickers


class ScreenerCondicionOut(BaseModel):
    op: str
    cumple: bool
    izq_etiqueta: str
    izq_valor: Optional[float] = None
    der_etiqueta: str
    der_valor: Optional[float] = None


class ScreenerFilaOut(BaseModel):
    ticker: str
    nombre: str
    origen: str  # "cartera" | "watchlist" | "ambos"
    estrategia_id: int
    estrategia_nombre: str
    variante: str = "local"
    moneda: str = ""
    tipo: str  # "compra" | "venta"
    motivo: str  # "entrada" | "regla_salida" | "stop_loss" | "take_profit" | "trailing_stop"
    distancia_pct: float
    precio_actual: float
    precio_gatillo: float
    fecha_precio: date
    dispara_ahora: bool
    posicion_abierta: bool
    retorno_abierta_pct: Optional[float] = None
    condiciones: list[ScreenerCondicionOut] = Field(default_factory=list)


class ScreenerOut(BaseModel):
    filas: list[ScreenerFilaOut]
    tickers_evaluados: int
    pares_evaluados: int
    umbral_pct: float
    fecha: date
    advertencias: list[str] = Field(default_factory=list)


# --- Explicación del resultado ("¿Por qué ganó o perdió mi cartera?", services/
#     explicacion_resultado_engine.py + explicacion_resultado_analytics.py) ---
# Todo lo que depende de un precio de mercado va Optional: un ticker sin cotización en el
# período no se estima, se lista en `no_disponibles` y sus campos numéricos quedan en None
# (ver docstring de `explicacion_resultado_engine.descomponer_ticker`).

class ExplicacionPeriodoOut(BaseModel):
    desde: Optional[date] = None
    hasta: date


class ExplicacionResultadoResumenOut(BaseModel):
    v0: Optional[float] = None
    v1: Optional[float] = None
    pnl: Optional[float] = None
    twr_pct: Optional[float] = None
    xirr_pct: Optional[float] = None
    rendimiento_simple_pct: Optional[float] = None
    aportes: Optional[float] = None
    retiros: Optional[float] = None
    amortizaciones: Optional[float] = None
    ingresos: Optional[float] = None


class ExplicacionComponentesOut(BaseModel):
    precio: Optional[float] = None
    dividendos: Optional[float] = None
    cupones: Optional[float] = None
    comisiones: Optional[float] = None


class ExplicacionItemOut(BaseModel):
    """Descomposición del P&L de un ticker, o de un grupo (tipo/mercado) cuando `ticker` es None."""
    ticker: Optional[str] = None
    nombre: Optional[str] = None
    etiqueta: Optional[str] = None
    v0: Optional[float] = None
    v1: Optional[float] = None
    pnl: Optional[float] = None
    precio: Optional[float] = None
    dividendos: Optional[float] = None
    cupones: Optional[float] = None
    comisiones: Optional[float] = None
    aportes: Optional[float] = None
    retiros: Optional[float] = None
    amortizaciones: Optional[float] = None
    contribucion_pct: Optional[float] = None
    disponible: Optional[bool] = None
    n_no_disponibles: Optional[int] = None


class ExplicacionNoDisponibleOut(BaseModel):
    ticker: str
    nombre: str
    motivo: str


class ExplicacionFxOut(BaseModel):
    estado: str  # "ok" | "no_disponible" | "no_aplica"
    resultado_activos_ars: Optional[float] = None
    efecto_mep_ars: Optional[float] = None
    efecto_fx_pct: Optional[float] = None
    identidad_verificada: bool = True


class ExplicacionTextoOut(BaseModel):
    titulo: str
    frases: list[str] = Field(default_factory=list)


class ExplicacionResultadoOut(BaseModel):
    estado: str  # "ok" | "parcial" | "sin_datos"
    periodo: ExplicacionPeriodoOut
    resultado: ExplicacionResultadoResumenOut
    componentes: ExplicacionComponentesOut
    por_tipo: list[ExplicacionItemOut] = Field(default_factory=list)
    por_mercado: list[ExplicacionItemOut] = Field(default_factory=list)
    por_ticker: list[ExplicacionItemOut] = Field(default_factory=list)
    contribuyentes: list[ExplicacionItemOut] = Field(default_factory=list)
    detractores: list[ExplicacionItemOut] = Field(default_factory=list)
    no_disponibles: list[ExplicacionNoDisponibleOut] = Field(default_factory=list)
    fx: ExplicacionFxOut
    explicacion: ExplicacionTextoOut
    advertencias: list[str] = Field(default_factory=list)
