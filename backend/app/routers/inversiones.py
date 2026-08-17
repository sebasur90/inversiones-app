from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db, MovimientoInversion, InstrumentoInversion
from ..schemas import (
    SyncResult,
    CarteraInfo,
    InversionesResumen,
    ExposicionOut,
    RebalanceoOut,
    MovimientoInversionOut,
    RendimientoPorTickerItem,
    EvolucionOut,
    PrecioSerieOut,
    PrecioHistoricoOut,
    TickerConPrecioItem,
    IndicesMercadoOut,
    VencimientoItem,
    ComisionesOut,
    PnlRealizadoNoRealizadoOut,
    RendimientoMensualOut,
    RiesgoOut,
)
from ..services.sheets_client import SheetsClientError
from ..services.inversiones_sync import sync_from_sheet, get_ultimo_sync
from ..services.inversiones_analytics import (
    get_carteras,
    get_resumen,
    get_exposicion,
    get_rebalanceo,
    get_evolucion,
    get_precios_ticker,
    get_tickers_con_precios,
    get_precios_historicos_ticker,
    get_indices_mercado,
    get_vencimientos,
    get_comisiones,
    get_pnl_realizado_no_realizado,
    get_rendimiento_mensual,
)
from ..services.riesgo_analytics import get_riesgo, get_benchmarks_disponibles, MONEDAS_VALIDAS

router = APIRouter(prefix="/api/inversiones", tags=["inversiones"])


@router.post("/sync", response_model=SyncResult)
def sync(db: Session = Depends(get_db)):
    try:
        result = sync_from_sheet(db)
    except SheetsClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/carteras", response_model=list[CarteraInfo])
def list_carteras(db: Session = Depends(get_db)):
    ultimo_sync = get_ultimo_sync()
    ultimo_sync_str = ultimo_sync.isoformat() if ultimo_sync else None
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


@router.get("/movimientos", response_model=list[MovimientoInversionOut])
def list_movimientos(
    cartera: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(MovimientoInversion)
    if cartera:
        q = q.filter(MovimientoInversion.cartera == cartera)
    if ticker:
        q = q.filter(MovimientoInversion.ticker == ticker)
    return q.order_by(MovimientoInversion.fecha.desc(), MovimientoInversion.id.desc()).all()


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


@router.get("/carteras/{nombre}/vencimientos", response_model=list[VencimientoItem])
def vencimientos_cartera(nombre: str, db: Session = Depends(get_db)):
    _validar_cartera(nombre, db)
    return get_vencimientos(nombre, db)


@router.get("/consolidado/vencimientos", response_model=list[VencimientoItem])
def vencimientos_consolidado(db: Session = Depends(get_db)):
    return get_vencimientos(None, db)


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
