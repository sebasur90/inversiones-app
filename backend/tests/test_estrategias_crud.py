"""Tests de CRUD de estrategias técnicas (services/estrategias_analytics.py + router)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base, get_db
from app.main import app
from app.services import estrategias_analytics as ea
from app.services.estrategia_engine import PRESETS
from fastapi.testclient import TestClient


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def client():
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
    yield TestClient(app)
    app.dependency_overrides.clear()


_DSL = PRESETS["rsi_sobreventa"]


# ── analytics: CRUD + round-trip del JSON ─────────────────────────────────────

def test_crear_y_obtener_round_trip_del_dsl(db):
    creada = ea.crear_estrategia("Mi RSI", _DSL, db, descripcion="test", ticker="AL30", tipo_preset="rsi_sobreventa")
    obtenida = ea.obtener_estrategia(creada.id, db)
    assert obtenida is not None
    assert obtenida.definicion == _DSL  # round-trip exacto por la columna JSON
    assert obtenida.ticker == "AL30"


def test_listar_estrategias_devuelve_todas_sin_filtrar_por_ticker(db):
    ea.crear_estrategia("A", _DSL, db, ticker="AL30")
    ea.crear_estrategia("B", _DSL, db, ticker="GGAL")
    ea.crear_estrategia("C", _DSL, db, ticker=None)  # reusable en cualquier ticker

    todas = ea.listar_estrategias(None, db)
    assert len(todas) == 3
    # a diferencia de escenarios (cartera=None filtra por IS NULL), acá "todas" incluye las que
    # tienen ticker asignado.
    con_ticker = ea.listar_estrategias("AL30", db)
    assert len(con_ticker) == 3


def test_actualizar_estrategia(db):
    creada = ea.crear_estrategia("Original", _DSL, db)
    actualizada = ea.actualizar_estrategia(creada.id, db, nombre="Renombrada")
    assert actualizada.nombre == "Renombrada"
    assert actualizada.definicion == _DSL


def test_duplicar_estrategia(db):
    creada = ea.crear_estrategia("Original", _DSL, db, ticker="AL30")
    dup = ea.duplicar_estrategia(creada.id, None, db)
    assert dup.nombre == "Original (copia)"
    assert dup.definicion == _DSL
    assert dup.id != creada.id


def test_variante_roundtrip_y_se_arrastra_al_duplicar(db):
    creada = ea.crear_estrategia("Sub", _DSL, db, ticker="MSFT", variante="subyacente")
    assert ea.obtener_estrategia(creada.id, db).variante == "subyacente"

    ea.actualizar_estrategia(creada.id, db, variante="local")
    assert ea.obtener_estrategia(creada.id, db).variante == "local"

    ea.actualizar_estrategia(creada.id, db, variante="subyacente")
    dup = ea.duplicar_estrategia(creada.id, None, db)
    assert dup.variante == "subyacente"


def test_variante_default_es_local(db):
    creada = ea.crear_estrategia("Def", _DSL, db)
    assert ea.obtener_estrategia(creada.id, db).variante == "local"


def test_eliminar_estrategia(db):
    creada = ea.crear_estrategia("Borrar", _DSL, db)
    assert ea.eliminar_estrategia(creada.id, db) is True
    assert ea.obtener_estrategia(creada.id, db) is None
    assert ea.eliminar_estrategia(creada.id, db) is False


# ── router: CRUD end-to-end ────────────────────────────────────────────────────

def test_router_crud_completo(client):
    r = client.post("/api/inversiones/estrategias", json={"nombre": "RSI test", "definicion": _DSL})
    assert r.status_code == 201
    estrategia = r.json()
    assert estrategia["nombre"] == "RSI test"

    r = client.get(f"/api/inversiones/estrategias/{estrategia['id']}")
    assert r.status_code == 200
    assert r.json()["definicion"] == _DSL

    r = client.get("/api/inversiones/estrategias")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.put(f"/api/inversiones/estrategias/{estrategia['id']}", json={"nombre": "Renombrada", "definicion": _DSL})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Renombrada"

    r = client.post(f"/api/inversiones/estrategias/{estrategia['id']}/duplicate")
    assert r.status_code == 201
    assert r.json()["id"] != estrategia["id"]

    r = client.delete(f"/api/inversiones/estrategias/{estrategia['id']}")
    assert r.status_code == 204
    r = client.get(f"/api/inversiones/estrategias/{estrategia['id']}")
    assert r.status_code == 404


def test_router_rechaza_dsl_invalido(client):
    dsl_invalido = {"version": 99, "entrada": {"op": "y", "condiciones": []}}
    r = client.post("/api/inversiones/estrategias", json={"nombre": "Mala", "definicion": dsl_invalido})
    assert r.status_code == 422
