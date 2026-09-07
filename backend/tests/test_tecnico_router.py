"""Tests de los endpoints de análisis técnico (routers/tecnico.py)."""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base, BarraOHLCV, EstadoMarketDataTicker, InstrumentoInversion, PrecioInstrumento,
    WatchlistItem, get_db,
)
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    db.add(InstrumentoInversion(ticker="AL30", nombre="Bono AL30", tipo_instrumento="Bono",
                                 mercado="MERVAL", moneda="USD"))
    db.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion",
                          mercado="BCBA", moneda="ARS"))
    base = date.today() - timedelta(days=120)
    for i in range(100):
        db.add(PrecioInstrumento(ticker="AL30", fecha=base + timedelta(days=i),
                                  precio=100.0 + i * 0.1, moneda="USD", fuente="sheet"))
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


@pytest.fixture
def client_msft():
    """Como `client` pero con un CEDEAR (MSFT) que además tiene serie del subyacente en USD."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    db.add(WatchlistItem(ticker="MSFT", nombre="Microsoft CEDEAR", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS"))
    db.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion",
                         mercado="BCBA", moneda="ARS"))
    db.add(EstadoMarketDataTicker(ticker="MSFT", simbolo_subyacente="MSFT",
                                  mercado_subyacente="NMS", moneda_subyacente="USD",
                                  resolucion_estado="ok"))
    base = date.today() - timedelta(days=200)
    for i in range(150):
        f = base + timedelta(days=i)
        db.add(BarraOHLCV(ticker="MSFT@SUB", fecha=f, apertura=498 + i * 0.1, maximo=501 + i * 0.1,
                          minimo=497 + i * 0.1, cierre=500 + i * 0.1, volumen=1e7,
                          moneda="USD", fuente="yahoo"))
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


def test_listar_tickers_tecnicos(client):
    r = client.get("/api/inversiones/tecnico/tickers")
    assert r.status_code == 200
    tickers = {t["ticker"] for t in r.json()}
    assert tickers == {"AL30", "GGAL"}
    # `series` siempre trae al menos la variante local.
    por_ticker = {t["ticker"]: t for t in r.json()}
    assert [s["variante"] for s in por_ticker["AL30"]["series"]] == ["local"]


def test_tickers_incluye_serie_del_subyacente(client_msft):
    r = client_msft.get("/api/inversiones/tecnico/tickers")
    assert r.status_code == 200
    por_ticker = {t["ticker"]: t for t in r.json()}
    assert [s["variante"] for s in por_ticker["MSFT"]["series"]] == ["local", "subyacente"]
    sub = por_ticker["MSFT"]["series"][1]
    assert sub["moneda"] == "USD" and sub["mercado"] == "NMS"
    assert [s["variante"] for s in por_ticker["GGAL"]["series"]] == ["local"]


def test_serie_variante_subyacente_200(client_msft):
    r = client_msft.get("/api/inversiones/tecnico/MSFT/serie", params={"variante": "subyacente"})
    assert r.status_code == 200
    data = r.json()
    assert data["variante"] == "subyacente"
    assert data["moneda"] == "USD"
    assert data["mercado"] == "NMS"
    assert len(data["barras"]) > 100
    assert all(490 < b["cierre"] < 540 for b in data["barras"])


def test_serie_variante_subyacente_404_si_no_hay_serie(client_msft):
    r = client_msft.get("/api/inversiones/tecnico/GGAL/serie", params={"variante": "subyacente"})
    assert r.status_code == 404


def test_serie_variante_invalida_422(client_msft):
    r = client_msft.get("/api/inversiones/tecnico/MSFT/serie", params={"variante": "pesos"})
    assert r.status_code == 422


def test_backtest_variante_en_el_body(client_msft):
    dsl = {
        "version": 1,
        "indicadores": [{"id": "sma20", "tipo": "SMA", "params": {"periodo": 20}}],
        "entrada": {"op": "y", "condiciones": [
            {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"ref": "sma20"}}]},
        "salida": None,
        "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": {"lado": "long", "comision_pct": 0.5, "precio_ejecucion": "cierre", "demora_barras": 0},
    }
    r = client_msft.post("/api/inversiones/tecnico/MSFT/backtest",
                         json={"definicion": dsl, "variante": "subyacente"})
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "MSFT"
    assert data["variante"] == "subyacente"
    assert data["moneda"] == "USD"


def test_backtest_variante_invalida_422(client_msft):
    r = client_msft.post("/api/inversiones/tecnico/MSFT/backtest",
                         json={"definicion": {"version": 1}, "variante": "pesos"})
    assert r.status_code == 422


def test_listar_presets(client):
    r = client.get("/api/inversiones/tecnico/presets")
    assert r.status_code == 200
    nombres = {p["nombre"] for p in r.json()}
    assert "cruce_medias" in nombres


def test_ticker_no_encontrado_404(client):
    r = client.get("/api/inversiones/tecnico/NOEXISTE/serie")
    assert r.status_code == 404


def test_serie_sin_indicadores(client):
    r = client.get("/api/inversiones/tecnico/AL30/serie")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente_serie"] == "mixta"
    assert len(data["barras"]) == 100
    assert data["indicadores"] == {}


def test_serie_con_indicadores_agrega_warmup(client):
    r = client.get("/api/inversiones/tecnico/AL30/serie", params={"indicadores": ["SMA(50)"]})
    assert r.status_code == 200
    data = r.json()
    assert "SMA(50)" in data["indicadores"]
    assert len(data["indicadores"]["SMA(50)"]["valor"]) == len(data["barras"])
    # con warm-up de 50, el índice 49 ya tiene SMA definida
    assert data["indicadores"]["SMA(50)"]["valor"][49] is not None
    assert data["indicadores"]["SMA(50)"]["valor"][48] is None


def test_serie_con_clave_de_indicador_invalida_da_422(client):
    r = client.get("/api/inversiones/tecnico/AL30/serie", params={"indicadores": ["NOEXISTE(1)"]})
    assert r.status_code == 422


def test_serie_con_demasiados_indicadores_da_422(client):
    r = client.get("/api/inversiones/tecnico/AL30/serie", params={"indicadores": [f"SMA({i})" for i in range(1, 10)]})
    assert r.status_code == 422


def test_backtest_end_to_end(client):
    dsl = {
        "version": 1,
        "indicadores": [{"id": "rsi14", "tipo": "RSI", "params": {"periodo": 14}}],
        "entrada": {"op": "y", "condiciones": [{"op": "menor", "izq": {"ref": "rsi14"}, "der": {"const": 90}}]},
        "salida": None,
        "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": {"lado": "long", "comision_pct": 0.5, "precio_ejecucion": "cierre", "demora_barras": 0},
    }
    r = client.post("/api/inversiones/tecnico/AL30/backtest", json={"definicion": dsl})
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "AL30"
    assert "metricas" in data
    assert len(data["curva_equity"]) == len(data["curva_buy_hold"])


def test_backtest_con_dsl_invalido_da_422(client):
    r = client.post("/api/inversiones/tecnico/AL30/backtest", json={"definicion": {"version": 1}})
    assert r.status_code == 422


# --- Señales recientes (badge de la watchlist) ------------------------------------------------

def _dsl_compra_siempre_que_cruce(umbral: float):
    return {
        "version": 1,
        "indicadores": [],
        "entrada": {"op": "y", "condiciones": [
            {"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": umbral}},
        ]},
        "salida": None,
        "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0},
    }


def test_senales_vacias_sin_estrategias_guardadas(client):
    r = client.get("/api/inversiones/tecnico/senales")
    assert r.status_code == 200
    assert r.json() == []


def test_senal_reciente_se_reporta_con_ticker_y_antiguedad(client):
    # La serie de AL30 sube 0.1 por rueda desde 100: cruza 109.75 cerca del final.
    dsl = _dsl_compra_siempre_que_cruce(109.75)
    creada = client.post("/api/inversiones/estrategias",
                         json={"nombre": "Cruce tardío", "ticker": "AL30", "definicion": dsl})
    assert creada.status_code == 201

    r = client.get("/api/inversiones/tecnico/senales")
    assert r.status_code == 200
    senales = r.json()
    assert len(senales) == 1
    assert senales[0]["ticker"] == "AL30"
    assert senales[0]["tipo"] == "compra"
    assert senales[0]["estrategia_nombre"] == "Cruce tardío"
    assert senales[0]["barras_desde"] <= 5


def test_senal_vieja_no_se_reporta(client):
    # Cruza 100.05 en la segunda rueda de 100: demasiado vieja para ser accionable.
    dsl = _dsl_compra_siempre_que_cruce(100.05)
    client.post("/api/inversiones/estrategias",
                json={"nombre": "Cruce viejo", "ticker": "AL30", "definicion": dsl})

    r = client.get("/api/inversiones/tecnico/senales")
    assert r.json() == []


def test_estrategia_sin_ticker_no_genera_senal(client):
    dsl = _dsl_compra_siempre_que_cruce(109.75)
    client.post("/api/inversiones/estrategias", json={"nombre": "Reusable", "definicion": dsl})

    r = client.get("/api/inversiones/tecnico/senales")
    assert r.json() == []
