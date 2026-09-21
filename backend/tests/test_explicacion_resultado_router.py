"""Tests de los endpoints de "¿por qué ganó o perdió mi cartera?"
(routers/inversiones.py: /explicacion-resultado)."""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado, get_db,
)
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    db.add(InstrumentoInversion(ticker="AL30", nombre="Bono AL30", tipo_instrumento="Bono",
                                 mercado="MERVAL", moneda="USD"))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="AL30",
                                tipo_movimiento="compra", cantidad=100, precio=50.0,
                                moneda="USD", comision=0.0))
    db.add(PrecioInstrumento(fecha=date(2024, 1, 1), ticker="AL30", precio=50.0, moneda="USD", fuente="sheet"))
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=55.0, moneda="USD", fuente="sheet"))
    db.commit()
    db.close()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_consolidado_ok(client: TestClient):
    r = client.get("/api/inversiones/consolidado/explicacion-resultado")
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "ok"
    assert data["resultado"]["pnl"] == pytest.approx(500.0)
    assert data["fx"]["estado"] == "no_aplica"


def test_cartera_ok(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/explicacion-resultado")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


def test_cartera_inexistente_404(client: TestClient):
    r = client.get("/api/inversiones/carteras/no-existe/explicacion-resultado")
    assert r.status_code == 404


def test_moneda_ars_trae_bloque_fx(client: TestClient):
    r = client.get("/api/inversiones/consolidado/explicacion-resultado", params={"moneda": "ars"})
    assert r.status_code == 200
    assert r.json()["fx"]["estado"] in ("ok", "no_disponible")


def test_moneda_invalida_422(client: TestClient):
    r = client.get("/api/inversiones/consolidado/explicacion-resultado", params={"moneda": "eur"})
    assert r.status_code == 422


def test_desde_filtra_el_periodo(client: TestClient):
    r = client.get("/api/inversiones/consolidado/explicacion-resultado", params={"desde": "2024-06-01"})
    assert r.status_code == 200
    assert r.json()["periodo"]["desde"] == "2024-06-01"
