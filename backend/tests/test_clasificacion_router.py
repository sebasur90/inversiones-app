"""Endpoints de clasificación y valuación contra pares (routers/clasificacion.py)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, ClasificacionAuto, get_db
from app.main import app
from app.services import fundamentales_ingesta as fi


@pytest.fixture
def sesion():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def client(sesion, monkeypatch):
    monkeypatch.setattr(fi, "cargar_catalogo", lambda: [
        {"simbolo": "KO", "descripcion": "Coca Cola", "moneda": "ARS", "tipo": "CEDEAR"},
        {"simbolo": "PEP", "descripcion": "Pepsico", "moneda": "ARS", "tipo": "CEDEAR"},
    ])
    monkeypatch.setattr(fi, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})

    def override():
        s = sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_estado_sin_corridas(client, sesion):
    db = sesion()
    db.add(ClasificacionAuto(ticker_base="KO", simbolo_yahoo="KO", estado="ok", intentos_fallidos=0))
    db.commit()
    r = client.get("/api/inversiones/clasificacion/estado")
    assert r.status_code == 200
    body = r.json()
    assert body["cobertura"]["aptos"] == 2
    assert body["cobertura"]["con_datos"] == 1
    assert body["cobertura"]["cobertura_pct"] == 50.0
    assert body["ultima_corrida"] is None


def test_actualizar_sin_apis_externas(client):
    r = client.post("/api/inversiones/clasificacion/actualizar", json={"tickers": ["KO"]})
    assert r.status_code == 200
    assert r.json()["resultado"] == "sin_fuentes"


def test_actualizar_rechaza_mas_de_cinco(client):
    r = client.post("/api/inversiones/clasificacion/actualizar", json={"tickers": list("ABCDEF")})
    assert r.status_code == 422


def test_actualizar_sin_tickers(client):
    r = client.post("/api/inversiones/clasificacion/actualizar", json={"tickers": []})
    assert r.json()["resultado"] == "sin_tickers"
