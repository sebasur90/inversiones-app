"""Tests del paginado de GET /api/inversiones/movimientos."""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, MovimientoInversion, get_db
from app.main import app


@pytest.fixture
def client():
    # StaticPool: sin él cada conexión abriría su propia SQLite en memoria, y la sesión
    # del override no vería las tablas creadas acá.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    for i in range(10):
        db.add(MovimientoInversion(
            fecha=date(2024, 1, i + 1), cartera="test", ticker=f"T{i}",
            tipo_movimiento="compra", cantidad=1.0, precio=100.0 + i, moneda="USD", comision=0.0,
        ))
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


def test_sin_limit_devuelve_todo(client):
    r = client.get("/api/inversiones/movimientos")
    assert r.status_code == 200
    assert len(r.json()) == 10


def test_limit_respeta_el_orden_descendente(client):
    r = client.get("/api/inversiones/movimientos", params={"limit": 3})
    assert r.status_code == 200
    fechas = [m["fecha"] for m in r.json()]
    assert fechas == ["2024-01-10", "2024-01-09", "2024-01-08"]


def test_offset_continua_donde_termino_el_limit(client):
    primera = client.get("/api/inversiones/movimientos", params={"limit": 3}).json()
    segunda = client.get("/api/inversiones/movimientos", params={"limit": 3, "offset": 3}).json()

    assert [m["fecha"] for m in segunda] == ["2024-01-07", "2024-01-06", "2024-01-05"]
    assert {m["id"] for m in primera}.isdisjoint({m["id"] for m in segunda})


def test_desde_filtra_por_fecha(client):
    r = client.get("/api/inversiones/movimientos", params={"desde": "2024-01-08"})
    assert [m["fecha"] for m in r.json()] == ["2024-01-10", "2024-01-09", "2024-01-08"]


def test_limit_invalido_es_rechazado(client):
    assert client.get("/api/inversiones/movimientos", params={"limit": 0}).status_code == 422
    assert client.get("/api/inversiones/movimientos", params={"offset": -1}).status_code == 422
