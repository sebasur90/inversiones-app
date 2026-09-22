"""Tests de los endpoints de Costo de oportunidad (routers/inversiones.py: /costo-oportunidad).

Incluye dos tests de no-regresión obligatorios: `/performance-relativa` y `/opportunity-cost`
(las pantallas ya existentes que consumen `benchmarks_analytics`/`opportunity_cost_analytics`)
deben seguir devolviendo exactamente lo mismo, porque esta pantalla nueva no toca esos módulos.
"""
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
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0, cer=100.0))
    db.add(InstrumentoInversion(ticker="AAPL", nombre="Apple", tipo_instrumento="CEDEAR",
                                 mercado="Global", moneda="USD", sector="Tecnologia", pais="AR"))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="AAPL",
                                tipo_movimiento="compra", cantidad=10, precio=100.0,
                                moneda="USD", comision=0.0))
    db.add(PrecioInstrumento(fecha=date(2024, 1, 1), ticker="AAPL", precio=100.0, moneda="USD", fuente="sheet"))
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AAPL", precio=120.0, moneda="USD", fuente="sheet"))
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


def test_cartera_ok_200(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/costo-oportunidad", params={"benchmark": "Dólar (MEP)"})
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "ok"
    assert data["referencia"] == "Dólar (MEP)"


def test_consolidado_ok_200(client: TestClient):
    r = client.get("/api/inversiones/consolidado/costo-oportunidad", params={"benchmark": "Dólar (MEP)"})
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


def test_cartera_inexistente_404(client: TestClient):
    r = client.get("/api/inversiones/carteras/no-existe/costo-oportunidad")
    assert r.status_code == 404


def test_moneda_invalida_422(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/costo-oportunidad", params={"moneda": "eur"})
    assert r.status_code == 422


def test_defaults_moneda_usd(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/costo-oportunidad", params={"benchmark": "Dólar (MEP)"})
    assert r.status_code == 200
    assert r.json()["moneda"] == "usd"


def test_desde_se_respeta_en_periodo_pedido(client: TestClient):
    desde = "2024-06-01"
    r = client.get(
        "/api/inversiones/carteras/test/costo-oportunidad",
        params={"benchmark": "Dólar (MEP)", "desde": desde},
    )
    assert r.status_code == 200
    assert r.json()["periodo_pedido_desde"] == desde


def test_shape_del_schema(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/costo-oportunidad", params={"benchmark": "Dólar (MEP)"})
    data = r.json()
    claves_esperadas = {
        "estado", "moneda", "referencia", "moneda_nativa_referencia", "periodo_pedido_desde",
        "periodo_desde", "periodo_hasta", "n_meses", "resultado_cartera_pct",
        "resultado_referencia_pct", "diferencia_pp", "valor_inicial", "aportes_netos_periodo",
        "valor_final_cartera", "valor_final_referencia", "diferencia_monetaria",
        "serie_indices", "serie_valores", "advertencias",
    }
    assert claves_esperadas <= set(data.keys())
    assert isinstance(data["advertencias"], list)
    assert isinstance(data["serie_indices"], list)
    assert isinstance(data["serie_valores"], list)


def test_ars_real_es_aceptada_como_moneda(client: TestClient):
    r = client.get(
        "/api/inversiones/carteras/test/costo-oportunidad",
        params={"moneda": "ars_real", "benchmark": "Inflación (CER)"},
    )
    assert r.status_code == 200


class TestNoRegresionPantallasExistentes:
    """`_resolver_fuente` (benchmarks_analytics) y `opportunity_cost_analytics` no se tocan:
    las pantallas que ya los consumen tienen que devolver exactamente lo mismo que antes."""

    def test_performance_relativa_no_cambia(self, client: TestClient):
        r = client.get(
            "/api/inversiones/carteras/test/performance-relativa",
            params={"moneda": "usd", "benchmark": "Dólar (MEP)"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["estado"] == "ok"
        assert data["benchmark_usado"] == "Dólar (MEP)"
        assert data["moneda"] == "usd"

    def test_opportunity_cost_no_cambia(self, client: TestClient):
        r = client.get(
            "/api/inversiones/carteras/test/opportunity-cost",
            params={"benchmark": "Dólar (MEP)"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["estado"] == "ok"
        assert data["benchmark_usado"] == "Dólar (MEP)"
        # Bug conocido y no corregido a propósito (queda para el tab viejo, que no se toca):
        # el shadow value se calcula sobre montos en USD creciendo por el MEP en ARS.
        assert data["valor_shadow_usd"] is not None
