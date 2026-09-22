"""Tests de los endpoints de Descomposición de cartera (routers/inversiones.py:
/descomposicion)."""
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
    db.add(InstrumentoInversion(ticker="AAPL", nombre="Apple", tipo_instrumento="CEDEAR",
                                 mercado="Global", moneda="USD", sector="Tecnologia", pais="AR"))
    db.add(InstrumentoInversion(ticker="AL30", nombre="Bono AL30", tipo_instrumento="Bono",
                                 mercado="MERVAL", moneda="USD", sector="Soberano", pais="AR"))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="AAPL",
                                tipo_movimiento="compra", cantidad=10, precio=100.0,
                                moneda="USD", comision=0.0))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="otra", ticker="AL30",
                                tipo_movimiento="compra", cantidad=10, precio=50.0,
                                moneda="USD", comision=0.0))
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AAPL", precio=110.0, moneda="USD", fuente="sheet"))
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


def test_descomposicion_cartera_ok(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/descomposicion")
    assert r.status_code == 200
    data = r.json()
    assert data["niveles"] == ["Familia", "País", "Sector", "Ticker"]
    assert data["instrumentos"] == 1
    etiquetas = {n["etiqueta"] for n in data["raiz"]}
    assert etiquetas == {"Renta variable"}


def test_descomposicion_cartera_inexistente_404(client: TestClient):
    r = client.get("/api/inversiones/carteras/no-existe/descomposicion")
    assert r.status_code == 404


def test_descomposicion_consolidado_incluye_ambas_carteras(client: TestClient):
    r = client.get("/api/inversiones/consolidado/descomposicion")
    assert r.status_code == 200
    data = r.json()
    assert data["instrumentos"] == 2
    etiquetas = {n["etiqueta"] for n in data["raiz"]}
    assert etiquetas == {"Renta variable", "Renta fija"}


def test_descomposicion_arbol_completo_llega_hasta_ticker(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/descomposicion")
    data = r.json()
    familia = data["raiz"][0]
    pais = familia["hijos"][0]
    sector = pais["hijos"][0]
    ticker = sector["hijos"][0]
    assert ticker["nivel"] == "Ticker"
    assert ticker["etiqueta"] == "AAPL"
    assert ticker["tipo_instrumento"] == "CEDEAR"
    assert ticker["hijos"] == []
