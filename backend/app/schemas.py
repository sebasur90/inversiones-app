from pydantic import BaseModel
from typing import Optional
from datetime import date

# --- Inversiones ---

class SyncErrorItem(BaseModel):
    fila: int
    motivo: str


class SyncResult(BaseModel):
    movimientos: int
    instrumentos: int
    precios: int
    indices_mercado: int
    objetivos: int
    rebalanceo: int
    errores: list[SyncErrorItem]


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
    meses_restantes: int
    proyeccion_usd: float
    alcanzable: bool
    deficit_usd: float

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
    valor_actual_usd: float
    valor_actual_ars: float
    moneda: str


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
