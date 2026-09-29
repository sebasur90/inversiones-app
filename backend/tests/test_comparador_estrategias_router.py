"""Endpoint del comparador de estrategias (POST /tecnico/{ticker}/comparar)."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, EstrategiaTecnica, InstrumentoInversion, PrecioInstrumento, get_db
from app.main import app

CIERRES = [100] * 10 + [100 + (i - 9) * 2 for i in range(10, 20)] + [120 - (i - 19) * 3 for i in range(20, 30)]
BASE_FECHA = date.today() - timedelta(days=len(CIERRES))


def _dsl(entrada, salida=None):
    return {
        "version": 1, "indicadores": [], "entrada": entrada, "salida": salida,
        "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0},
    }


DSL_A = _dsl(
    {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 110}},
    {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 95}},
)
DSL_B = _dsl(
    {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 100}},
    {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 100}},
)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    db.add(InstrumentoInversion(ticker="AAA", nombre="AAA", tipo_instrumento="Accion", mercado="NYSE", moneda="USD"))
    for i, c in enumerate(CIERRES):
        db.add(PrecioInstrumento(ticker="AAA", fecha=BASE_FECHA + timedelta(days=i), precio=float(c), moneda="USD", fuente="sheet"))

    ahora = datetime.utcnow()
    ids = {}
    for nombre, dsl in (("A", DSL_A), ("B", DSL_B)):
        e = EstrategiaTecnica(
            nombre=nombre, ticker=None, tipo_preset=None, definicion=dsl, variante="local",
            fecha_creacion=ahora, fecha_actualizacion=ahora,
        )
        db.add(e)
        db.flush()
        ids[nombre] = e.id
    # 8 estrategias extra idénticas a A, para el tope de MAX_ESTRATEGIAS (8): con A y B ya guardadas,
    # elegir las 8 extra + 1 más suma 9 y tiene que dar 422.
    extra_ids = []
    for i in range(8):
        e = EstrategiaTecnica(
            nombre=f"Extra {i}", ticker=None, tipo_preset=None, definicion=DSL_A, variante="local",
            fecha_creacion=ahora, fecha_actualizacion=ahora,
        )
        db.add(e)
        db.flush()
        extra_ids.append(e.id)
    db.commit()
    db.close()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app), ids, extra_ids
    app.dependency_overrides.clear()


def test_comparar_end_to_end_200(client):
    tc, ids, _ = client
    r = tc.post("/api/inversiones/tecnico/AAA/comparar", json={"estrategia_ids": [ids["A"], ids["B"]]})
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "AAA"
    assert data["estado"] == "ok"
    assert len(data["filas"]) == 3  # Comprar y mantener + A + B
    assert len(data["fechas"]) > 0
    for fila in data["filas"]:
        assert len(fila["curva"]) == len(data["fechas"])


def test_comparar_ticker_no_encontrado_404(client):
    tc, ids, _ = client
    r = tc.post("/api/inversiones/tecnico/NOEXISTE/comparar", json={"estrategia_ids": [ids["A"]]})
    assert r.status_code == 404


def test_comparar_variante_invalida_422(client):
    tc, ids, _ = client
    r = tc.post("/api/inversiones/tecnico/AAA/comparar", json={"estrategia_ids": [ids["A"]], "variante": "nominal"})
    assert r.status_code == 422


def test_comparar_mas_de_max_estrategias_422(client):
    tc, ids, extra_ids = client
    todas = list(extra_ids) + [ids["A"]]  # 9 ids
    r = tc.post("/api/inversiones/tecnico/AAA/comparar", json={"estrategia_ids": todas})
    assert r.status_code == 422


def test_comparar_ocho_estrategias_pasa(client):
    tc, _, extra_ids = client
    r = tc.post("/api/inversiones/tecnico/AAA/comparar", json={"estrategia_ids": extra_ids})
    assert r.status_code == 200


def test_comparar_referencia_no_seleccionada_422(client):
    tc, ids, _ = client
    r = tc.post(
        "/api/inversiones/tecnico/AAA/comparar",
        json={"estrategia_ids": [ids["A"]], "referencia_id": ids["B"]},
    )
    assert r.status_code == 422


def test_comparar_referencia_seleccionada_200(client):
    tc, ids, _ = client
    r = tc.post(
        "/api/inversiones/tecnico/AAA/comparar",
        json={"estrategia_ids": [ids["A"], ids["B"]], "referencia_id": ids["B"]},
    )
    assert r.status_code == 200
    fila_b = next(f for f in r.json()["filas"] if f["estrategia_id"] == ids["B"])
    assert fila_b["es_referencia"] is True
    assert fila_b["diferencia_pp"] == pytest.approx(0.0, abs=1e-6)


def test_comparar_estrategia_ids_vacio_422(client):
    tc, _, _ = client
    r = tc.post("/api/inversiones/tecnico/AAA/comparar", json={"estrategia_ids": []})
    assert r.status_code == 422


def test_comparar_capital_inicial_invalido_422(client):
    tc, ids, _ = client
    r = tc.post(
        "/api/inversiones/tecnico/AAA/comparar",
        json={"estrategia_ids": [ids["A"]], "capital_inicial": -1},
    )
    assert r.status_code == 422


def test_comparar_no_acepta_parametro_cartera(client):
    # El comparador es "1 ticker × N estrategias": no depende de ninguna cartera. El endpoint no
    # declara el parámetro, así que mandarlo no cambia nada (FastAPI lo ignora si no está en el
    # schema del body).
    tc, ids, _ = client
    r1 = tc.post("/api/inversiones/tecnico/AAA/comparar", json={"estrategia_ids": [ids["A"]]})
    r2 = tc.post(
        "/api/inversiones/tecnico/AAA/comparar",
        json={"estrategia_ids": [ids["A"]], "cartera": "Alguna Cartera Inexistente"},
    )
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["filas"] == r2.json()["filas"]
