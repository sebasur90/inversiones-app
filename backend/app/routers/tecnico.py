"""Endpoints de análisis técnico: universo de tickers, serie de barras + indicadores, backtest y
CRUD de estrategias guardadas.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db, InstrumentoInversion, WatchlistItem
from ..schemas import (
    TickerTecnicoOut, SerieTecnicaOut,
    BacktestRequest, BacktestOut, PresetEstrategiaOut, SenalTickerOut,
    EstrategiaGuardarRequest, EstrategiaOut,
    ScreenerRequest, ScreenerOut,
)
from ..services import ohlcv_analytics, estrategias_analytics, screener_analytics
from ..services import indicadores_engine, estrategia_engine

router = APIRouter(prefix="/api/inversiones", tags=["tecnico"])

_MAX_INDICADORES = 8
_RANGO_DEFAULT_DIAS = 365
_VARIANTES = ("local", "subyacente")


def _validar_variante(variante: str) -> None:
    if variante not in _VARIANTES:
        raise HTTPException(status_code=422, detail=f"variante desconocida: '{variante}'")


def _validar_ticker_tecnico(ticker: str, db: Session) -> None:
    """`_validar_ticker` de `inversiones.py` exige `InstrumentoInversion` y dejaría afuera la
    watchlist: el universo de análisis técnico es cartera ∪ watchlist."""
    en_cartera = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    en_watchlist = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    if not en_cartera and not en_watchlist:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' no encontrado en cartera ni en watchlist")


def _estrategia_out(e) -> EstrategiaOut:
    return EstrategiaOut(
        id=e.id, nombre=e.nombre, descripcion=e.descripcion, ticker=e.ticker,
        tipo_preset=e.tipo_preset, definicion=e.definicion,
        variante=getattr(e, "variante", None) or "local",
        fecha_creacion=e.fecha_creacion, fecha_actualizacion=e.fecha_actualizacion,
    )


# ─── Tickers y serie ──────────────────────────────────────────────────────────

@router.get("/tecnico/tickers", response_model=list[TickerTecnicoOut])
def listar_tickers_tecnicos(db: Session = Depends(get_db)):
    return ohlcv_analytics.listar_tickers_tecnicos(db)


@router.get("/tecnico/presets", response_model=list[PresetEstrategiaOut])
def listar_presets():
    return [{"nombre": nombre, "definicion": definicion} for nombre, definicion in estrategia_engine.PRESETS.items()]


@router.get("/tecnico/senales", response_model=list[SenalTickerOut])
def listar_senales_recientes(db: Session = Depends(get_db)):
    """Última señal de cada estrategia guardada con ticker asignado, si es reciente. La consume
    la watchlist para mostrar un badge sin tener que abrir el gráfico de cada ticker."""
    return estrategias_analytics.senales_recientes(db)


_ORIGENES_SCREENER = ("todos", "cartera", "watchlist")


@router.post("/tecnico/screener", response_model=ScreenerOut)
def correr_screener(body: ScreenerRequest, db: Session = Depends(get_db)):
    """Qué pares (estrategia guardada, ticker de cartera ∪ watchlist) están a menos de
    `umbral_pct` de disparar compra o venta. `estrategia_ids` vacío corre todas las guardadas."""
    if body.origen not in _ORIGENES_SCREENER:
        raise HTTPException(status_code=422, detail=f"origen desconocido: '{body.origen}'")
    return screener_analytics.escanear(
        db, tuple(sorted(set(body.estrategia_ids))), body.umbral_pct, body.origen,
    )


@router.get("/tecnico/{ticker}/serie", response_model=SerieTecnicaOut)
def serie_tecnica(
    ticker: str,
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    indicadores: list[str] = Query([]),
    max_barras: int = Query(ohlcv_analytics.MAX_BARRAS_DEFAULT, ge=1, le=3000),
    variante: str = Query("local"),
    db: Session = Depends(get_db),
):
    _validar_ticker_tecnico(ticker, db)
    _validar_variante(variante)
    if len(indicadores) > _MAX_INDICADORES:
        raise HTTPException(status_code=422, detail=f"máximo {_MAX_INDICADORES} indicadores por pedido")

    hasta = hasta or date.today()
    desde = desde or (hasta - timedelta(days=_RANGO_DEFAULT_DIAS))

    especificaciones: list[tuple[str, str, dict]] = []  # (clave_original, nombre, params)
    for clave_raw in indicadores:
        try:
            nombre, params = indicadores_engine.parsear_clave(clave_raw)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        especificaciones.append((clave_raw, nombre, params))

    barras_previas = max(
        (indicadores_engine.warm_up_barras(nombre, params) for _, nombre, params in especificaciones),
        default=0,
    )

    serie = ohlcv_analytics.get_serie_barras(
        ticker, desde, hasta, db, barras_previas=barras_previas, max_barras=max_barras,
        variante=variante,
    )

    # `variante=subyacente` sobre un ticker sin serie del subyacente bajada -> 404 (a diferencia de
    # `local` sin datos, que devuelve 200 con la serie vacía: la local siempre "existe").
    if variante == "subyacente" and not serie["barras"]:
        raise HTTPException(status_code=404, detail=f"'{ticker}' no tiene serie del subyacente en USD")

    resultado_indicadores: dict[str, dict[str, list]] = {}
    if serie["barras"]:
        for clave_raw, nombre, params in especificaciones:
            resultado_indicadores[clave_raw] = indicadores_engine.calcular(nombre, serie["barras"], params)

    return {
        "ticker": serie["ticker"], "nombre": serie["nombre"], "moneda": serie["moneda"],
        "variante": serie["variante"], "mercado": serie["mercado"],
        "origen": serie["origen"], "fuente_serie": serie["fuente_serie"],
        "tiene_velas": serie["tiene_velas"], "tiene_volumen": serie["tiene_volumen"],
        "indice_desde": serie["indice_desde"], "barras": serie["barras"],
        "indicadores": resultado_indicadores, "advertencias": serie["advertencias"],
    }


# ─── Backtest ─────────────────────────────────────────────────────────────────

@router.post("/tecnico/{ticker}/backtest", response_model=BacktestOut)
def backtest_tecnico(ticker: str, body: BacktestRequest, db: Session = Depends(get_db)):
    _validar_ticker_tecnico(ticker, db)
    _validar_variante(body.variante)
    errores = estrategia_engine.validar_estrategia(body.definicion)
    if errores:
        raise HTTPException(status_code=422, detail="; ".join(errores))
    return estrategias_analytics.ejecutar_backtest(
        ticker, body.definicion, db, body.desde, body.hasta, variante=body.variante,
    )


# ─── CRUD de estrategias guardadas ────────────────────────────────────────────

@router.get("/estrategias", response_model=list[EstrategiaOut])
def listar_estrategias(ticker: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return [_estrategia_out(e) for e in estrategias_analytics.listar_estrategias(ticker, db)]


@router.post("/estrategias", response_model=EstrategiaOut, status_code=201)
def crear_estrategia_endpoint(body: EstrategiaGuardarRequest, db: Session = Depends(get_db)):
    if body.ticker is not None:
        _validar_ticker_tecnico(body.ticker, db)
    errores = estrategia_engine.validar_estrategia(body.definicion)
    if errores:
        raise HTTPException(status_code=422, detail="; ".join(errores))

    _validar_variante(body.variante)
    e = estrategias_analytics.crear_estrategia(
        nombre=body.nombre, definicion=body.definicion, db=db,
        descripcion=body.descripcion, ticker=body.ticker, tipo_preset=body.tipo_preset,
        variante=body.variante,
    )
    return _estrategia_out(e)


@router.get("/estrategias/{estrategia_id}", response_model=EstrategiaOut)
def obtener_estrategia_endpoint(estrategia_id: int, db: Session = Depends(get_db)):
    e = estrategias_analytics.obtener_estrategia(estrategia_id, db)
    if e is None:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada")
    return _estrategia_out(e)


@router.put("/estrategias/{estrategia_id}", response_model=EstrategiaOut)
def actualizar_estrategia_endpoint(estrategia_id: int, body: EstrategiaGuardarRequest, db: Session = Depends(get_db)):
    if body.ticker is not None:
        _validar_ticker_tecnico(body.ticker, db)
    errores = estrategia_engine.validar_estrategia(body.definicion)
    if errores:
        raise HTTPException(status_code=422, detail="; ".join(errores))

    _validar_variante(body.variante)
    e = estrategias_analytics.actualizar_estrategia(
        estrategia_id, db, nombre=body.nombre, descripcion=body.descripcion,
        ticker=body.ticker, definicion=body.definicion, variante=body.variante,
    )
    if e is None:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada")
    return _estrategia_out(e)


@router.post("/estrategias/{estrategia_id}/duplicate", response_model=EstrategiaOut, status_code=201)
def duplicar_estrategia_endpoint(
    estrategia_id: int, nuevo_nombre: Optional[str] = None, db: Session = Depends(get_db),
):
    e = estrategias_analytics.duplicar_estrategia(estrategia_id, nuevo_nombre, db)
    if e is None:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada")
    return _estrategia_out(e)


@router.delete("/estrategias/{estrategia_id}", status_code=204)
def eliminar_estrategia_endpoint(estrategia_id: int, db: Session = Depends(get_db)):
    if not estrategias_analytics.eliminar_estrategia(estrategia_id, db):
        raise HTTPException(status_code=404, detail="Estrategia no encontrada")
