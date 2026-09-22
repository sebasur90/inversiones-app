"""Tests de los endpoints de 'Escenarios de vida' (routers/escenarios.py: /scenarios/vida/*)."""
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


def _supuestos(**overrides):
    base = dict(
        patrimonio_inicial=10000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=6.0, horizonte_meses=24, moneda="USD",
    )
    base.update(overrides)
    return base


# ─── POST /scenarios/vida/simulate ─────────────────────────────────────────

def test_simulate_vida_ok(client: TestClient):
    body = {
        "supuestos": _supuestos(),
        "escenarios": [{"tipo": "aumentar_aporte", "monto": 150.0}],
    }
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 200
    data = r.json()

    assert data["disclaimer"] == "Simulación matemática basada en los supuestos ingresados."
    assert len(data["resultados"]) == 2
    assert data["resultados"][0]["es_base"] is True
    assert data["resultados"][0]["tipo"] == "continuar_igual"
    assert data["resultados"][1]["es_base"] is False
    assert "puntos" in data["resultados"][0]
    assert "metricas" in data["resultados"][0]


def test_se_agrega_la_base_sola_si_no_vino_en_el_body(client: TestClient):
    body = {"supuestos": _supuestos(), "escenarios": [{"tipo": "dejar_de_aportar"}]}
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["resultados"]) == 2
    assert data["resultados"][0]["tipo"] == "continuar_igual"
    assert data["resultados"][1]["tipo"] == "dejar_de_aportar"


def test_extraordinario_sin_mes_es_422(client: TestClient):
    body = {"supuestos": _supuestos(), "escenarios": [{"tipo": "aporte_extraordinario", "monto": 500.0}]}
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 422


def test_mes_mayor_al_horizonte_es_422(client: TestClient):
    body = {
        "supuestos": _supuestos(horizonte_meses=12),
        "escenarios": [{"tipo": "retiro_extraordinario", "monto": 500.0, "mes": 13}],
    }
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 422


def test_tipo_desconocido_es_422(client: TestClient):
    body = {"supuestos": _supuestos(), "escenarios": [{"tipo": "no_existe"}]}
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 422


def test_moneda_invalida_es_422(client: TestClient):
    body = {"supuestos": _supuestos(moneda="EUR"), "escenarios": [{"tipo": "continuar_igual"}]}
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 422


def test_lista_vacia_de_escenarios_es_422(client: TestClient):
    body = {"supuestos": _supuestos(), "escenarios": []}
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 422


def test_mas_de_6_escenarios_es_422(client: TestClient):
    body = {
        "supuestos": _supuestos(),
        "escenarios": [{"tipo": "continuar_igual"} for _ in range(7)],
    }
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 422


def test_ruta_vida_no_colisiona_con_scenarios_id(client: TestClient):
    """POST /scenarios/vida/simulate no debe caer en la ruta paramétrica de duplicate."""
    body = {"supuestos": _supuestos(), "escenarios": [{"tipo": "continuar_igual"}]}
    r = client.post("/api/inversiones/scenarios/vida/simulate", json=body)
    assert r.status_code == 200  # no 404/422 de "escenario 'vida' no encontrado"


# ─── GET /scenarios/vida/defaults ──────────────────────────────────────────

def test_defaults_vida_endpoint_200_y_shape(client: TestClient):
    r = client.get("/api/inversiones/scenarios/vida/defaults")
    assert r.status_code == 200
    data = r.json()
    assert "patrimonio_inicial_usd" in data
    assert "aporte_mensual_usd" in data
    assert "origen_aporte" in data


def test_defaults_vida_cartera_inexistente_404(client: TestClient):
    r = client.get("/api/inversiones/scenarios/vida/defaults", params={"cartera": "no-existe"})
    assert r.status_code == 404


# ─── No-regresión: el simulador Avanzado sigue funcionando ────────────────

def test_simulador_avanzado_sigue_funcionando(client: TestClient):
    body = {"escenarios": [{"tipo_preset": "alcista", "nombre": "Alcista"}]}
    r = client.post("/api/inversiones/scenarios/simulate", json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["resultados"]) == 1
    assert data["resultados"][0]["tipo_preset"] == "alcista"
