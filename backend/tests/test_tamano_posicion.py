"""Calculadora de tamaño de posición: insumos del servidor (services/tamano_posicion.py)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, BarraOHLCV, EstadoMarketDataTicker, IndiceMercado, InstrumentoInversion,
    MovimientoInversion, PrecioInstrumento, WatchlistItem, get_db,
)
from app.main import app
from app.services import indicadores_engine as ind
from app.services import tamano_posicion as tp

HOY = date.today()
MEP = 1000.0


def _poblar(db):
    db.add(IndiceMercado(fecha=HOY - timedelta(days=400), mep=MEP, fuente="sheet"))
    for ticker, nombre, tipo, moneda in (("MSFT", "Microsoft CEDEAR", "CEDEAR", "ARS"), ("GGAL", "Galicia", "Accion", "ARS")):
        db.add(InstrumentoInversion(ticker=ticker, nombre=nombre, tipo_instrumento=tipo, mercado="BCBA", moneda=moneda))
        db.add(MovimientoInversion(fecha=HOY - timedelta(days=100), cartera="c", ticker=ticker, tipo_movimiento="compra",
                                   cantidad=10, precio=20000.0 if ticker == "MSFT" else 5000.0, moneda="ARS", comision=0.0))
        db.add(PrecioInstrumento(ticker=ticker, fecha=HOY, precio=22000.0 if ticker == "MSFT" else 6000.0,
                                 moneda="ARS", fuente="sheet"))
    db.add(WatchlistItem(ticker="NVDA", nombre="Nvidia CEDEAR", tipo_instrumento="CEDEAR", mercado="BCBA", moneda="ARS"))
    db.add(EstadoMarketDataTicker(ticker="MSFT", simbolo_subyacente="MSFT", mercado_subyacente="NMS",
                                  moneda_subyacente="USD", resolucion_estado="ok"))
    for i in range(120):
        f = HOY - timedelta(days=119 - i)
        c = 500.0 + (i % 5)
        db.add(BarraOHLCV(ticker="MSFT@SUB", fecha=f, apertura=c, maximo=c + 2, minimo=c - 2, cierre=c,
                          volumen=1e6, moneda="USD", fuente="yahoo"))
        c2 = 5000.0 + i
        db.add(BarraOHLCV(ticker="GGAL", fecha=f, apertura=c2, maximo=c2 + 50, minimo=c2 - 50, cierre=c2,
                          volumen=1e5, moneda="ARS", fuente="yahoo"))
    db.commit()


@pytest.fixture
def fabrica():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)
    db = sesion()
    _poblar(db)
    db.close()
    return sesion


@pytest.fixture
def client(fabrica):
    def override():
        s = fabrica()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_cedear_trae_subyacente_en_usd_y_precio_local_en_pesos(fabrica):
    db = fabrica()
    r = tp.get_tamano_posicion("MSFT", "subyacente", db)
    assert r["moneda"] == "USD" and r["variante"] == "subyacente"
    assert r["ultimo_cierre"] == pytest.approx(500.0 + (119 % 5))
    assert r["atr"] is not None and r["atr"] > 0
    assert r["precio_local"] == 22000.0 and r["moneda_local"] == "ARS"
    assert r["mep"] == MEP
    # 10 MSFT a 22000 + 10 GGAL a 6000, a MEP 1000.
    assert r["valor_cartera_usd"] == pytest.approx(220.0 + 60.0)


def test_atr_coincide_con_el_motor(fabrica):
    db = fabrica()
    r = tp.get_tamano_posicion("GGAL", "local", db)
    barras = tp.ohlcv_analytics.get_serie_barras("GGAL", date.min, HOY, db, max_barras=300, variante="local")["barras"]
    assert r["atr"] == pytest.approx(ind.atr(barras, 14)[-1])


def test_accion_local_mide_en_pesos(fabrica):
    r = tp.get_tamano_posicion("GGAL", "local", fabrica())
    assert r["moneda"] == "ARS" and r["ultimo_cierre"] == pytest.approx(5000.0 + 119)
    assert r["precio_local"] == 6000.0


def test_ticker_sin_serie_ni_cartera_deja_todo_opcional_en_none(fabrica):
    db = fabrica()
    db.query(MovimientoInversion).delete()
    db.query(IndiceMercado).delete()
    db.commit()
    r = tp.get_tamano_posicion("NVDA", "local", db)
    assert r["ultimo_cierre"] is None and r["atr"] is None and r["precio_local"] is None
    assert r["mep"] is None and r["valor_cartera_usd"] is None


def test_endpoint_usa_la_referencia_sin_variante(client):
    r = client.get("/api/inversiones/tecnico/MSFT/tamano-posicion")
    assert r.status_code == 200
    d = r.json()
    assert d["variante"] == "subyacente" and d["moneda"] == "USD" and d["precio_local"] == 22000.0


def test_endpoint_variante_local_y_validaciones(client):
    assert client.get("/api/inversiones/tecnico/GGAL/tamano-posicion?variante=local").json()["moneda"] == "ARS"
    assert client.get("/api/inversiones/tecnico/GGAL/tamano-posicion?variante=otra").status_code == 422
    assert client.get("/api/inversiones/tecnico/NOEXISTE/tamano-posicion").status_code == 404
