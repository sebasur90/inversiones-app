"""Tests de los endpoints de Matriz de correlaciones (routers/inversiones.py:
/matriz-correlaciones), incluyendo no-regresión de /correlaciones (la pantalla Contribución)."""
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
    db.add(InstrumentoInversion(ticker="AAA", nombre="AAA", tipo_instrumento="CEDEAR",
                                 mercado="Global", moneda="USD", sector="Tecnologia", pais="AR"))
    db.add(InstrumentoInversion(ticker="BBB", nombre="BBB", tipo_instrumento="CEDEAR",
                                 mercado="Global", moneda="USD", sector="Tecnologia", pais="AR"))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="AAA",
                                tipo_movimiento="compra", cantidad=10, precio=100.0,
                                moneda="USD", comision=0.0))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="BBB",
                                tipo_movimiento="compra", cantidad=10, precio=200.0,
                                moneda="USD", comision=0.0))
    for i, mes in enumerate(range(1, 9)):
        fecha = date(2024, mes, 28)
        db.add(PrecioInstrumento(fecha=fecha, ticker="AAA", precio=100.0 + i, moneda="USD", fuente="sheet"))
        db.add(PrecioInstrumento(fecha=fecha, ticker="BBB", precio=200.0 + i * 2, moneda="USD", fuente="sheet"))
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


BASE_PARAMS = {"desde": "2024-01-01", "hasta": "2024-09-01", "tickers": ["AAA", "BBB"]}


def test_cartera_ok_200_shape_completo(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=BASE_PARAMS)
    assert r.status_code == 200
    data = r.json()
    for campo in (
        "estado", "moneda", "frecuencia_pedida", "frecuencia_efectiva", "min_obs",
        "tickers", "n_tickers", "tickers_detalle", "tickers_descartados", "matriz", "pares",
        "n_pares", "n_pares_ok", "correlacion_promedio", "nivel_diversificacion", "ranking",
        "pocos_datos", "advertencias",
    ):
        assert campo in data, f"falta {campo}"
    assert data["estado"] == "ok"
    assert data["moneda"] == "USD"
    assert data["tickers"] == ["AAA", "BBB"]


def test_consolidado_ok_200(client: TestClient):
    r = client.get("/api/inversiones/consolidado/matriz-correlaciones", params=BASE_PARAMS)
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


def test_cartera_inexistente_404(client: TestClient):
    r = client.get("/api/inversiones/carteras/no-existe/matriz-correlaciones", params=BASE_PARAMS)
    assert r.status_code == 404


def test_frecuencia_invalida_422(client: TestClient):
    params = {**BASE_PARAMS, "frecuencia": "trimestral"}
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=params)
    assert r.status_code == 422


def test_mas_de_max_tickers_422(client: TestClient):
    params = {**BASE_PARAMS, "tickers": [f"T{i}" for i in range(13)]}
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=params)
    assert r.status_code == 422


def test_min_obs_fuera_de_rango_422(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones",
                    params={**BASE_PARAMS, "min_obs": 1})
    assert r.status_code == 422
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones",
                    params={**BASE_PARAMS, "min_obs": 999})
    assert r.status_code == 422


def test_desde_mayor_a_hasta_422(client: TestClient):
    params = {**BASE_PARAMS, "desde": "2024-09-01", "hasta": "2024-01-01"}
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=params)
    assert r.status_code == 422


def test_tickers_repetidos_deduplicados(client: TestClient):
    params = {**BASE_PARAMS, "tickers": ["AAA", "aaa", "AAA", "BBB"]}
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=params)
    assert r.status_code == 200
    assert r.json()["tickers"] == ["AAA", "BBB"]


def test_sin_tickers_usa_tenencias_por_defecto(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones",
                    params={"desde": "2024-01-01", "hasta": "2024-09-01"})
    assert r.status_code == 200
    assert r.json()["n_tickers"] > 0


def test_un_solo_ticker_da_estado_sin_suficientes_tickers(client: TestClient):
    params = {**BASE_PARAMS, "tickers": ["AAA"]}
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=params)
    assert r.status_code == 200
    assert r.json()["estado"] == "sin_suficientes_tickers"


@pytest.mark.parametrize("frecuencia", ["diaria", "semanal", "mensual"])
def test_las_tres_frecuencias_devuelven_200(client: TestClient, frecuencia):
    params = {**BASE_PARAMS, "frecuencia": frecuencia}
    r = client.get("/api/inversiones/carteras/test/matriz-correlaciones", params=params)
    assert r.status_code == 200
    data = r.json()
    assert data["frecuencia_pedida"] == frecuencia
    assert data["frecuencia_efectiva"] == frecuencia


# ── No-regresión de /correlaciones (Contribución): esta pantalla no la toca ──

def test_correlaciones_viejo_cartera_sigue_200_con_su_shape(client: TestClient):
    r = client.get("/api/inversiones/carteras/test/correlaciones")
    assert r.status_code == 200
    data = r.json()
    for campo in ("universo", "n_tickers", "tickers", "matriz", "pares", "advertencia_historial_corto"):
        assert campo in data


def test_correlaciones_viejo_consolidado_sigue_200(client: TestClient):
    r = client.get("/api/inversiones/consolidado/correlaciones")
    assert r.status_code == 200
