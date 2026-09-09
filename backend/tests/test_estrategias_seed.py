"""Tests de la siembra del catálogo de presets (services/estrategias_seed.py)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.services import estrategias_analytics as ea
from app.services import estrategias_seed as seed
from app.services.estrategia_engine import PRESETS, resolver_preset
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


def test_siembra_crea_todo_el_catalogo_como_reusable(db):
    resumen = seed.sembrar_presets(db)

    assert resumen == {"creadas": len(PRESETS), "actualizadas": 0, "sin_cambios": 0}
    guardadas = ea.listar_estrategias(None, db)
    assert len(guardadas) == len(PRESETS)
    # Sin ticker fijo: es lo que hace que el screener las corra sobre todo el universo.
    assert all(e.ticker is None for e in guardadas)
    # El `tipo_preset` es lo que después enlaza cada guardada con su ficha explicativa.
    assert {e.tipo_preset for e in guardadas} == set(PRESETS)


def test_siembra_es_idempotente(db):
    seed.sembrar_presets(db)
    resumen = seed.sembrar_presets(db)

    assert resumen == {"creadas": 0, "actualizadas": 0, "sin_cambios": len(PRESETS)}
    assert len(ea.listar_estrategias(None, db)) == len(PRESETS)


def test_siembra_de_arranque_no_pisa_los_ajustes_del_usuario(db):
    seed.sembrar_presets(db)
    etiqueta = PRESETS["cruce_medias"].etiqueta
    propia = ea.buscar_por_nombre(etiqueta, db)
    dsl_tocado = resolver_preset("cruce_medias")
    dsl_tocado["riesgo"]["stop_loss_pct"] = 3.0
    ea.actualizar_estrategia(propia.id, db, definicion=dsl_tocado)

    seed.sembrar_presets(db, forzar=False)

    assert ea.obtener_estrategia(propia.id, db).definicion["riesgo"]["stop_loss_pct"] == 3.0


def test_siembra_forzada_restaura_la_definicion_de_fabrica(db):
    seed.sembrar_presets(db)
    etiqueta = PRESETS["cruce_medias"].etiqueta
    propia = ea.buscar_por_nombre(etiqueta, db)
    dsl_tocado = resolver_preset("cruce_medias")
    dsl_tocado["riesgo"]["stop_loss_pct"] = 3.0
    ea.actualizar_estrategia(propia.id, db, definicion=dsl_tocado)

    resumen = seed.sembrar_presets(db, forzar=True)

    assert resumen["actualizadas"] == len(PRESETS)
    restaurada = ea.obtener_estrategia(propia.id, db)
    assert restaurada.definicion == PRESETS["cruce_medias"].definicion
    assert len(ea.listar_estrategias(None, db)) == len(PRESETS)


def test_siembra_adopta_una_estrategia_propia_que_ya_usaba_ese_nombre(db):
    # El usuario ya tenía una llamada igual (con acentos/mayúsculas distintas): la siembra tiene
    # que reconocerla como la misma, no dejar dos entradas con el mismo texto en el selector.
    etiqueta = PRESETS["rsi_sobreventa"].etiqueta
    ea.crear_estrategia(etiqueta.upper(), resolver_preset("macd_cruce"), db, ticker="AL30")

    seed.sembrar_presets(db, forzar=True)

    assert len(ea.listar_estrategias(None, db)) == len(PRESETS)


def test_deduplicar_deja_la_fila_mas_reciente(db):
    vieja = ea.crear_estrategia("Mínimo histórico", resolver_preset("macd_cruce"), db)
    nueva = ea.crear_estrategia("minimo  historico", resolver_preset("cruce_medias"), db)

    borradas = seed.deduplicar_por_nombre(db)

    assert borradas == 1
    assert ea.obtener_estrategia(vieja.id, db) is None
    assert ea.obtener_estrategia(nueva.id, db) is not None


def test_endpoint_de_siembra(client):
    r = client.post("/api/inversiones/tecnico/presets/sembrar")
    assert r.status_code == 200, r.text
    assert r.json()["creadas"] == len(PRESETS)

    r = client.post("/api/inversiones/tecnico/presets/sembrar")
    assert r.json() == {"creadas": 0, "actualizadas": 0, "sin_cambios": len(PRESETS)}

    r = client.post("/api/inversiones/tecnico/presets/sembrar?forzar=true")
    assert r.json()["actualizadas"] == len(PRESETS)

    assert len(client.get("/api/inversiones/estrategias").json()) == len(PRESETS)
