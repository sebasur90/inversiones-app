from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db, MovimientoInversion, InstrumentoInversion
from ..schemas import (
    SyncResult,
    CalidadDatosOut,
    CarteraInfo,
    InversionesResumen,
    ExposicionOut,
    RebalanceoOut,
    ConfiguracionCarteraOut,
    RebalanceoSimulacionRequest,
    RebalanceoSimulacionOut,
    MovimientoInversionOut,
    RendimientoPorTickerItem,
    EvolucionOut,
    PatrimonioHistoryOut,
    PatrimonioSummaryOut,
    PrecioSerieOut,
    PrecioHistoricoOut,
    TickerConPrecioItem,
    IndicesMercadoOut,
    VencimientosOut,
    FlujoCajaProyectadoOut,
    ComisionesOut,
    PnlRealizadoNoRealizadoOut,
    VistaFiscalPorAnioOut,
    RendimientoMensualOut,
    RiesgoOut,
    PerformanceRelativaOut,
    PerformanceCompareOut,
    OpportunityCostOut,
    ContribucionOut,
    CorrelacionesOut,
    DiagnosticoOut,
    DescomposicionFxOut,
    DescomposicionFxPosicionOut,
    TickerAnalysisOut,
    TickerHistoricoOut,
    TickerRiesgoOut,
    TickerPerformanceRelativaOut,
)
from ..services.sheets_client import SheetsClientError
from ..services.inversiones_sync import sync_from_sheet
from ..services.calidad_datos import get_calidad_datos
from ..services.inversiones_analytics import (
    get_carteras,
    get_resumen,
    get_exposicion,
    get_rebalanceo,
    get_configuracion_cartera,
    simular_rebalanceo,
    get_evolucion,
    get_precios_ticker,
    get_tickers_con_precios,
    get_precios_historicos_ticker,
    get_indices_mercado,
    get_comisiones,
    get_pnl_realizado_no_realizado,
    get_vista_fiscal_por_anio,
    get_rendimiento_mensual,
)
from ..services.flujo_caja_analytics import get_flujo_caja_proyectado, get_vencimientos_completo
from ..services.patrimonio_analytics import get_patrimonio_history, get_patrimonio_summary
from ..services.riesgo_analytics import get_riesgo, get_benchmarks_disponibles, MONEDAS_VALIDAS
from ..services.benchmarks_analytics import get_performance_relativa, get_performance_compare
from ..services.opportunity_cost_analytics import get_opportunity_cost
from ..services.contribucion_analytics import get_contribucion, get_correlaciones, UNIVERSOS_VALIDOS
from ..services.diagnostico_analytics import get_diagnostico
from ..services.fx_decomposition_analytics import (
    get_descomposicion_fx,
    get_descomposicion_fx_por_posicion,
)
from ..services.ticker_analytics import (
    get_ticker_position,
    get_ticker_performance,
    get_ticker_riesgo,
    get_ticker_performance_relativa,
    get_ticker_historico,
)

router = APIRouter(prefix="/api/inversiones", tags=["inversiones"])


@router.post("/sync", response_model=SyncResult)
def sync(db: Session = Depends(get_db)):
    try:
        result = sync_from_sheet(db)
    except SheetsClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/carteras", response_model=list[CarteraInfo])
def list_carteras(db: Session = Depends(get_db)):
    from ..database import SyncRun
    ultimo_sync = db.query(SyncRun).order_by(SyncRun.timestamp.desc()).first()
    ultimo_sync_str = ultimo_sync.timestamp.isoformat() if ultimo_sync else None
    return [CarteraInfo(nombre=nombre, ultimo_sync=ultimo_sync_str) for nombre in get_carteras(db)]


def _validar_cartera(nombre: str, db: Session) -> None:
    existe = db.query(MovimientoInversion).filter(MovimientoInversion.cartera == nombre).first()
    if not existe:
        raise HTTPException(status_code=404, detail=f"Cartera '{nombre}' no encontrada")


@router.get("/carteras/{nombre}/resumen", response_model=InversionesResumen)
def resumen_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_resumen(nombre, db)


@router.get("/consolidado/resumen", response_model=InversionesResumen)
def resumen_consolidado(db: Session = Depends(get_db)):
    return get_resumen(None, db)


@router.get("/carteras/{nombre}/exposicion", response_model=ExposicionOut)
def exposicion_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_exposicion(nombre, db)


@router.get("/consolidado/exposicion", response_model=ExposicionOut)
def exposicion_consolidado(db: Session = Depends(get_db)):
    return get_exposicion(None, db)


@router.get("/carteras/{nombre}/rebalanceo", response_model=RebalanceoOut)
def rebalanceo_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_rebalanceo(nombre, db)


@router.get("/consolidado/rebalanceo", response_model=RebalanceoOut)
def rebalanceo_consolidado(db: Session = Depends(get_db)):
    return get_rebalanceo(None, db)


@router.get("/carteras/{nombre}/configuracion", response_model=ConfiguracionCarteraOut)
def configuracion_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_configuracion_cartera(nombre, db)


@router.get("/consolidado/configuracion", response_model=ConfiguracionCarteraOut)
def configuracion_consolidado(db: Session = Depends(get_db)):
    return get_configuracion_cartera(None, db)


@router.post("/carteras/{nombre}/rebalanceo/simular", response_model=RebalanceoSimulacionOut)
def simular_rebalanceo_cartera(nombre: str, body: RebalanceoSimulacionRequest, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return simular_rebalanceo(nombre, db, body.eje, body.modo, body.aporte_usd, body.tasa_comision_pct)


@router.post("/consolidado/rebalanceo/simular", response_model=RebalanceoSimulacionOut)
def simular_rebalanceo_consolidado(body: RebalanceoSimulacionRequest, db: Session = Depends(get_db)):
    return simular_rebalanceo(None, db, body.eje, body.modo, body.aporte_usd, body.tasa_comision_pct)


@router.get("/movimientos", response_model=list[MovimientoInversionOut])
def list_movimientos(
    cartera: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    desde: Optional[date] = Query(None, description="Sólo movimientos con fecha >= desde"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Máximo de movimientos a devolver"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Movimientos, del más reciente al más viejo.

    `limit`/`offset` paginan sobre ese orden: la app pide los últimos N al arrancar y va
    trayendo el resto a medida que hace falta, en vez de cargar el historial completo.
    """
    q = db.query(MovimientoInversion)
    if cartera:
        q = q.filter(MovimientoInversion.cartera == cartera)
    if ticker:
        q = q.filter(MovimientoInversion.ticker == ticker)
    if desde:
        q = q.filter(MovimientoInversion.fecha >= desde)

    q = q.order_by(MovimientoInversion.fecha.desc(), MovimientoInversion.id.desc())
    if offset:
        q = q.offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


@router.get("/carteras/{nombre}/rendimiento-por-ticker", response_model=list[RendimientoPorTickerItem])
def rendimiento_por_ticker(nombre: str, db: Session = Depends(get_db)):
    """Rendimiento individual por ticker en una cartera."""
    from ..services.inversiones_analytics import get_rendimiento_por_ticker

    _validar_cartera(nombre, db)
    return get_rendimiento_por_ticker(nombre, db)


@router.get("/consolidado/rendimiento-por-ticker", response_model=list[RendimientoPorTickerItem])
def rendimiento_por_ticker_consolidado(db: Session = Depends(get_db)):
    """Rendimiento individual por ticker consolidado."""
    from ..services.inversiones_analytics import get_rendimiento_por_ticker

    return get_rendimiento_por_ticker(None, db)


@router.get("/carteras/{nombre}/evolucion", response_model=EvolucionOut)
def evolucion_cartera(nombre: str, desde: Optional[date] = Query(None), db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    max_puntos = 180 if desde is not None else 24
    return get_evolucion(nombre, db, desde=desde, max_puntos=max_puntos)


@router.get("/consolidado/evolucion", response_model=EvolucionOut)
def evolucion_consolidado(desde: Optional[date] = Query(None), db: Session = Depends(get_db)):
    max_puntos = 180 if desde is not None else 24
    return get_evolucion(None, db, desde=desde, max_puntos=max_puntos)


@router.get("/carteras/{nombre}/rendimiento-mensual", response_model=RendimientoMensualOut)
def rendimiento_mensual_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_rendimiento_mensual(nombre, db)


@router.get("/consolidado/rendimiento-mensual", response_model=RendimientoMensualOut)
def rendimiento_mensual_consolidado(db: Session = Depends(get_db)):
    return get_rendimiento_mensual(None, db)


@router.get("/carteras/{nombre}/patrimonio/history", response_model=PatrimonioHistoryOut)
def patrimonio_history_cartera(nombre: str, desde: Optional[date] = Query(None), db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    max_puntos = 180 if desde is not None else 24
    return get_patrimonio_history(nombre, db, desde=desde, max_puntos=max_puntos)


@router.get("/consolidado/patrimonio/history", response_model=PatrimonioHistoryOut)
def patrimonio_history_consolidado(desde: Optional[date] = Query(None), db: Session = Depends(get_db)):
    max_puntos = 180 if desde is not None else 24
    return get_patrimonio_history(None, db, desde=desde, max_puntos=max_puntos)


@router.get("/carteras/{nombre}/patrimonio/summary", response_model=PatrimonioSummaryOut)
def patrimonio_summary_cartera(nombre: str, desde: Optional[date] = Query(None), db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_patrimonio_summary(nombre, db, desde=desde)


@router.get("/consolidado/patrimonio/summary", response_model=PatrimonioSummaryOut)
def patrimonio_summary_consolidado(desde: Optional[date] = Query(None), db: Session = Depends(get_db)):
    return get_patrimonio_summary(None, db, desde=desde)


@router.get("/ticker/{ticker}/precios", response_model=PrecioSerieOut)
def precios_ticker(ticker: str, dias: int = Query(365, ge=1, le=3650), db: Session = Depends(get_db)):
    existe = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    if not existe:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' no encontrado")
    return get_precios_ticker(ticker, dias, db)


@router.get("/tickers-con-precios", response_model=list[TickerConPrecioItem])
def tickers_con_precios(db: Session = Depends(get_db)):
    return get_tickers_con_precios(db)


@router.get("/ticker/{ticker}/precios-historicos", response_model=PrecioHistoricoOut)
def precios_historicos_ticker(ticker: str, dias: int = Query(3650, ge=1, le=3650), db: Session = Depends(get_db)):
    existe = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    if not existe:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' no encontrado")
    return get_precios_historicos_ticker(ticker, dias, db)


@router.get("/indices-mercado", response_model=IndicesMercadoOut)
def indices_mercado(dias: int = Query(3650, ge=1, le=3650), db: Session = Depends(get_db)):
    return get_indices_mercado(dias, db)


@router.get("/carteras/{nombre}/vencimientos", response_model=VencimientosOut)
def vencimientos_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_vencimientos_completo(nombre, db)


@router.get("/consolidado/vencimientos", response_model=VencimientosOut)
def vencimientos_consolidado(db: Session = Depends(get_db)):
    return get_vencimientos_completo(None, db)


@router.get("/carteras/{nombre}/flujo-caja-proyectado", response_model=FlujoCajaProyectadoOut)
def flujo_caja_proyectado_cartera(
    nombre: str,
    meses: int = Query(24, ge=6, le=48),
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    return get_flujo_caja_proyectado(nombre, db, meses)


@router.get("/consolidado/flujo-caja-proyectado", response_model=FlujoCajaProyectadoOut)
def flujo_caja_proyectado_consolidado(
    meses: int = Query(24, ge=6, le=48),
    db: Session = Depends(get_db),
):
    return get_flujo_caja_proyectado(None, db, meses)


@router.get("/carteras/{nombre}/comisiones", response_model=ComisionesOut)
def comisiones_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_comisiones(nombre, db)


@router.get("/consolidado/comisiones", response_model=ComisionesOut)
def comisiones_consolidado(db: Session = Depends(get_db)):
    return get_comisiones(None, db)


@router.get("/carteras/{nombre}/pnl-realizado", response_model=PnlRealizadoNoRealizadoOut)
def pnl_realizado_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_pnl_realizado_no_realizado(nombre, db)


@router.get("/consolidado/pnl-realizado", response_model=PnlRealizadoNoRealizadoOut)
def pnl_realizado_consolidado(db: Session = Depends(get_db)):
    return get_pnl_realizado_no_realizado(None, db)


@router.get("/carteras/{nombre}/vista-fiscal", response_model=VistaFiscalPorAnioOut)
def vista_fiscal_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_vista_fiscal_por_anio(nombre, db)


@router.get("/consolidado/vista-fiscal", response_model=VistaFiscalPorAnioOut)
def vista_fiscal_consolidado(db: Session = Depends(get_db)):
    return get_vista_fiscal_por_anio(None, db)


@router.get("/benchmarks", response_model=list[str])
def benchmarks_disponibles(db: Session = Depends(get_db)):
    return get_benchmarks_disponibles(db)


def _validar_moneda(moneda: str) -> None:
    if moneda not in MONEDAS_VALIDAS:
        raise HTTPException(status_code=422, detail=f"moneda inválida: {moneda}. Válidas: {MONEDAS_VALIDAS}")


@router.get("/carteras/{nombre}/riesgo", response_model=RiesgoOut)
def riesgo_cartera(
    nombre: str,
    moneda: str = Query("usd"),
    benchmark: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    _validar_moneda(moneda)
    return get_riesgo(nombre, moneda, benchmark, db)


@router.get("/consolidado/riesgo", response_model=RiesgoOut)
def riesgo_consolidado(
    moneda: str = Query("usd"),
    benchmark: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_moneda(moneda)
    return get_riesgo(None, moneda, benchmark, db)


@router.get("/carteras/{nombre}/contribucion", response_model=ContribucionOut)
def contribucion_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_contribucion(nombre, db)


@router.get("/consolidado/contribucion", response_model=ContribucionOut)
def contribucion_consolidado(db: Session = Depends(get_db)):
    return get_contribucion(None, db)


def _validar_universo(universo: str) -> None:
    if universo not in UNIVERSOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"universo inválido: {universo}. Válidos: {UNIVERSOS_VALIDOS}")


@router.get("/carteras/{nombre}/correlaciones", response_model=CorrelacionesOut)
def correlaciones_cartera(nombre: str, universo: str = Query("tenencias"), db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    _validar_universo(universo)
    return get_correlaciones(nombre, db, universo)


@router.get("/consolidado/correlaciones", response_model=CorrelacionesOut)
def correlaciones_consolidado(universo: str = Query("tenencias"), db: Session = Depends(get_db)):
    _validar_universo(universo)
    return get_correlaciones(None, db, universo)


@router.get("/carteras/{nombre}/diagnostico", response_model=DiagnosticoOut)
def diagnostico_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_diagnostico(nombre, db)


@router.get("/consolidado/diagnostico", response_model=DiagnosticoOut)
def diagnostico_consolidado(db: Session = Depends(get_db)):
    return get_diagnostico(None, db)


@router.get("/carteras/{nombre}/performance-relativa", response_model=PerformanceRelativaOut)
def performance_relativa_cartera(
    nombre: str,
    moneda: str = Query("usd"),
    benchmark: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    _validar_moneda(moneda)
    return get_performance_relativa(nombre, moneda, benchmark, desde, db)


@router.get("/consolidado/performance-relativa", response_model=PerformanceRelativaOut)
def performance_relativa_consolidado(
    moneda: str = Query("usd"),
    benchmark: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_moneda(moneda)
    return get_performance_relativa(None, moneda, benchmark, desde, db)


@router.get("/carteras/{nombre}/performance/compare", response_model=PerformanceCompareOut)
def performance_compare_cartera(
    nombre: str,
    moneda: str = Query("usd"),
    desde: Optional[date] = Query(None),
    benchmarks: Optional[str] = Query(None),
    tickers: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    _validar_moneda(moneda)
    benchmarks_list = benchmarks.split(",") if benchmarks else []
    tickers_list = tickers.split(",") if tickers else []
    return get_performance_compare(nombre, moneda, desde, benchmarks_list, tickers_list, db)


@router.get("/consolidado/performance/compare", response_model=PerformanceCompareOut)
def performance_compare_consolidado(
    moneda: str = Query("usd"),
    desde: Optional[date] = Query(None),
    benchmarks: Optional[str] = Query(None),
    tickers: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_moneda(moneda)
    benchmarks_list = benchmarks.split(",") if benchmarks else []
    tickers_list = tickers.split(",") if tickers else []
    return get_performance_compare(None, moneda, desde, benchmarks_list, tickers_list, db)


@router.get("/carteras/{nombre}/opportunity-cost", response_model=OpportunityCostOut)
def opportunity_cost_cartera(
    nombre: str,
    benchmark: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    return get_opportunity_cost(nombre, benchmark, desde, db)


@router.get("/consolidado/opportunity-cost", response_model=OpportunityCostOut)
def opportunity_cost_consolidado(
    benchmark: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    return get_opportunity_cost(None, benchmark, desde, db)


@router.get("/carteras/{nombre}/descomposicion-fx", response_model=DescomposicionFxOut)
def descomposicion_fx_cartera(
    nombre: str,
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    return get_descomposicion_fx(nombre, desde, db)


@router.get("/consolidado/descomposicion-fx", response_model=DescomposicionFxOut)
def descomposicion_fx_consolidado(
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    return get_descomposicion_fx(None, desde, db)


@router.get("/carteras/{nombre}/descomposicion-fx-por-posicion", response_model=DescomposicionFxPosicionOut)
def descomposicion_fx_por_posicion_cartera(
    nombre: str,
    db: Session = Depends(get_db),
):
    _validar_cartera(nombre, db)
    return get_descomposicion_fx_por_posicion(nombre, db)


@router.get("/consolidado/descomposicion-fx-por-posicion", response_model=DescomposicionFxPosicionOut)
def descomposicion_fx_por_posicion_consolidado(
    db: Session = Depends(get_db),
):
    return get_descomposicion_fx_por_posicion(None, db)


@router.get("/calidad-datos", response_model=CalidadDatosOut)
def calidad_datos(db: Session = Depends(get_db)):
    """Obtiene el estado de calidad de datos del último sync."""
    return get_calidad_datos(db)


# ── Análisis profundo por ticker ──────────────────────────────────────────────

def _validar_ticker(ticker: str, db: Session) -> None:
    existe = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    if not existe:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' no encontrado")


@router.get("/ticker/{ticker}/analysis", response_model=TickerAnalysisOut)
def ticker_analysis(ticker: str, cartera: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Análisis profundo: position + performance (eager, barato)."""
    _validar_ticker(ticker, db)
    if cartera is not None:
        _validar_cartera(cartera, db)
    return {
        "position": get_ticker_position(ticker, cartera, db),
        "performance": get_ticker_performance(ticker, cartera, db),
    }


@router.get("/ticker/{ticker}/riesgo", response_model=TickerRiesgoOut)
def ticker_riesgo(
    ticker: str,
    cartera: Optional[str] = Query(None),
    moneda: str = Query("usd"),
    benchmark: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Riesgo y metrics vs benchmark por ticker (lazy)."""
    _validar_ticker(ticker, db)
    if cartera is not None:
        _validar_cartera(cartera, db)
    _validar_moneda(moneda)
    return get_ticker_riesgo(ticker, cartera, moneda, benchmark, db)


@router.get("/ticker/{ticker}/performance-relativa", response_model=TickerPerformanceRelativaOut)
def ticker_performance_relativa(
    ticker: str,
    cartera: Optional[str] = Query(None),
    moneda: str = Query("usd"),
    benchmark: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Performance relativa vs benchmark por ticker (lazy)."""
    _validar_ticker(ticker, db)
    if cartera is not None:
        _validar_cartera(cartera, db)
    _validar_moneda(moneda)
    return get_ticker_performance_relativa(ticker, cartera, moneda, benchmark, db)


@router.get("/ticker/{ticker}/historico", response_model=TickerHistoricoOut)
def ticker_historico(
    ticker: str,
    cartera: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Serie histórica: precio + valor de posición + rendimiento acumulado (lazy)."""
    _validar_ticker(ticker, db)
    if cartera is not None:
        _validar_cartera(cartera, db)
    return get_ticker_historico(ticker, cartera, desde, db)
