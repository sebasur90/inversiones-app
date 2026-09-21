"""Tests de los endpoints de Salud de cartera (routers/inversiones.py: /salud)."""
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


def test_salud_consolidado_ok(client: TestClient):
    r = client.get("/api/inversiones/consolidado/salud")
    assert r.status_code == 200
    data = r.json()
    assert data["cartera"] is None
    assert len(data["dimensiones"]) == 8
    assert {"n_revisar", "n_atencion", "n_normal", "n_sin_datos"} == set(data["resumen"].keys())


def test_salud_cartera_ok(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/salud")
    assert r.status_code == 200
    data = r.json()
    assert data["cartera"] == "test"
    claves = {d["clave"] for d in data["dimensiones"]}
    assert claves == {
        "riesgo", "concentracion", "diversificacion", "liquidez",
        "costos", "vencimientos", "balance_objetivo", "calidad_datos",
    }
    for dim in data["dimensiones"]:
        assert dim["estado"] in ("normal", "atencion", "revisar", "sin_datos")
        assert dim["regla"]
        assert dim["fuente"]


def test_salud_cartera_inexistente_404(client: TestClient):
    r = client.get("/api/inversiones/carteras/no-existe/salud")
    assert r.status_code == 404


def test_salud_observaciones_tienen_drilldown(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/salud")
    data = r.json()
    for obs in data["observaciones"]:
        assert obs["pantalla"].startswith("/")
        assert obs["accion"]
