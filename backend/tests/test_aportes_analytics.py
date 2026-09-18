"""Integración del ritmo de aportes: serie mensual desde movimientos reales (con MEP), servicio
cacheado y endpoints. La lógica de métricas está cubierta en `test_aportes_engine.py`."""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, MovimientoInversion, InstrumentoInversion, IndiceMercado, get_db
from app.main import app
from app.services.aportes_analytics import get_ritmo_aportes
from app.services.cache import estadisticas
from app.services.inversiones_analytics import (
    _movimientos_ordenados,
    get_aportes_historicos,
    serie_mensual_aportes,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _instrumento(db: Session, ticker="AAPL", moneda="USD"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=f"{ticker} SA", tipo_instrumento="Accion", mercado="TEST", moneda=moneda))
    db.commit()


def _mov(db: Session, fecha, tipo, cantidad, precio, ticker="AAPL", moneda="USD", comision=0.0, cartera="test"):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento=tipo,
        cantidad=cantidad, precio=precio, moneda=moneda, comision=comision,
    ))
    db.commit()


def test_serie_mensual_criterio_de_aporte(db: Session):
    _instrumento(db)
    _instrumento(db, ticker="GGAL", moneda="ARS")
    db.add(IndiceMercado(fecha=date(2024, 1, 1), cer=100.0, mep=1000.0))
    db.commit()

    _mov(db, date(2024, 1, 5), "compra", 10.0, 10.0)                       # +100
    _mov(db, date(2024, 2, 1), "dividendo", 0.0, 50.0)                     # no cuenta, pero el mes aparece
    _mov(db, date(2024, 2, 10), "venta", 3.0, 10.0, comision=1.0)          # salida 29 (comisión resta)
    _mov(db, date(2024, 3, 1), "amortizacion", 2.0, 10.0)                  # salida 20
    _mov(db, date(2024, 4, 1), "compra", 1.0, 50_000.0, ticker="GGAL", moneda="ARS")  # 50 USD al MEP 1000

    serie, omitidos = serie_mensual_aportes(_movimientos_ordenados(db, "test"), db, {})

    assert omitidos == 0
    assert serie["2024-01"] == {"neto": 100.0, "compras": 100.0, "salidas": 0.0}
    assert serie["2024-02"]["compras"] == 0.0
    assert serie["2024-02"]["salidas"] == pytest.approx(29.0)
    assert serie["2024-02"]["neto"] == pytest.approx(-29.0)
    assert serie["2024-03"]["neto"] == pytest.approx(-20.0)
    assert serie["2024-04"]["neto"] == pytest.approx(50.0)


def test_movimiento_sin_mep_se_omite_y_se_cuenta(db: Session):
    _instrumento(db, ticker="GGAL", moneda="ARS")
    _mov(db, date(2024, 4, 1), "compra", 1.0, 50_000.0, ticker="GGAL", moneda="ARS")
    _mov(db, date(2024, 5, 1), "dividendo", 0.0, 1_000.0, ticker="GGAL", moneda="ARS")

    serie, omitidos = serie_mensual_aportes(_movimientos_ordenados(db, "test"), db, {})

    assert serie == {}
    assert omitidos == 1  # el dividendo sin MEP no cuenta como omitido: nunca era aporte


def test_aportes_historicos_conserva_la_curva(db: Session):
    """Objetivo sigue viendo la misma curva acumulada, incluido el punto plano del mes con sólo dividendos."""
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 10.0, 10.0)
    _mov(db, date(2024, 2, 1), "dividendo", 0.0, 100.0)
    _mov(db, date(2024, 6, 1), "venta", 5.0, 10.0)

    curva = get_aportes_historicos("test", db)["curva"]

    assert curva == [
        {"mes": "2024-01", "aportes_netos_acumulados": 100.0},
        {"mes": "2024-02", "aportes_netos_acumulados": 100.0},
        {"mes": "2024-06", "aportes_netos_acumulados": 50.0},
    ]


def test_ritmo_consolidado_suma_carteras_y_cachea(db: Session):
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 10.0, 10.0, cartera="a")
    _mov(db, date(2024, 1, 15), "compra", 20.0, 10.0, cartera="b")

    hits_antes = estadisticas()["hits"]
    res = get_ritmo_aportes(None, db)
    assert res["estado"] == "ok"
    assert res["serie_mensual"][0] ["neto_usd"] == 300.0
    assert res["movimientos_omitidos_sin_mep"] == 0
    assert get_ritmo_aportes("a", db)["serie_mensual"][0]["neto_usd"] == 100.0

    get_ritmo_aportes(None, db)
    assert estadisticas()["hits"] == hits_antes + 1


# ── Endpoints ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    session = TestingSession()
    session.add(InstrumentoInversion(ticker="AAPL", nombre="AAPL SA", tipo_instrumento="Accion", mercado="TEST", moneda="USD"))
    session.add(MovimientoInversion(
        fecha=date(2024, 1, 1), cartera="test", ticker="AAPL", tipo_movimiento="compra",
        cantidad=1.0, precio=100.0, moneda="USD", comision=0.0,
    ))
    session.commit()
    session.close()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_cartera(client):
    r = client.get("/api/inversiones/carteras/test/aportes/ritmo")
    assert r.status_code == 200
    body = r.json()
    assert body["estado"] == "ok"
    assert body["primer_mes"] == "2024-01"
    assert body["serie_mensual"][-1]["en_curso"] is True
    assert body["este_mes"]["mes"] == date.today().strftime("%Y-%m")
    assert isinstance(body["mensajes"], list)


def test_endpoint_cartera_inexistente(client):
    assert client.get("/api/inversiones/carteras/nope/aportes/ritmo").status_code == 404


def test_endpoint_consolidado_sin_datos():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    try:
        r = TestClient(app).get("/api/inversiones/consolidado/aportes/ritmo")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["estado"] == "sin_datos"
    assert body["serie_mensual"] == [] and body["este_mes"] is None
