"""Endpoints de valuación contra pares (`/valuacion`, `/valuacion/{ticker}`) sobre una DB con
clasificación y snapshots de fundamentales ya cargados."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, ClasificacionAuto, FundamentalesSnapshot, IndiceMercado, InstrumentoInversion,
    MovimientoInversion, WatchlistItem, get_db,
)
from app.main import app
from app.services import clasificacion_analytics as ca

HOY = date.today()
INDUSTRIA = "Beverages - Non-Alcoholic"


def _serie(inicio, fin):
    pasos = 53
    return [{"fecha": (HOY - timedelta(weeks=pasos - 1 - i)).isoformat(),
             "cierre": inicio + (fin - inicio) * i / (pasos - 1)} for i in range(pasos)]


EMISORES = {
    #       pe,  ev/ebitda, ps, margen op, mcap,  serie
    "KO":   (14.0, 9.0, 2.0, 0.30, 3.0e11, (50, 60)),
    "PEP":  (24.0, 15.0, 3.0, 0.15, 2.0e11, (150, 160)),
    "MNST": (30.0, 20.0, 4.0, 0.28, 1.5e11, (50, 55)),
    "KDP":  (26.0, 14.0, 3.5, 0.20, 1.2e11, (30, 31)),
    "CELH": (35.0, 25.0, 5.0, 0.10, 1.0e11, (40, 20)),
}


@pytest.fixture
def sesion(monkeypatch):
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: [
        {"simbolo": t, "descripcion": t, "moneda": "ARS", "tipo": "CEDEAR"} for t in EMISORES
    ] + [{"simbolo": "KOD", "descripcion": "KO", "moneda": "USD", "tipo": "CEDEAR"}])
    monkeypatch.setattr(ca, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    for t, (pe, ev, ps, mop, mcap, (s0, s1)) in EMISORES.items():
        db.add(ClasificacionAuto(
            ticker_base=t, simbolo_yahoo=t, estado="ok", tipo="CEDEAR-acción", nombre=f"{t} Inc",
            quote_type="EQUITY", sector="Consumo básico", industria="Bebidas sin alcohol",
            industria_raw=INDUSTRIA, pais="Estados Unidos", region="EEUU", intentos_fallidos=0,
            fecha_fundamentales=HOY,
        ))
        db.add(FundamentalesSnapshot(
            simbolo_yahoo=t, fecha=HOY, moneda="USD", market_cap_usd=mcap, ratios_precio_confiables=1,
            metricas={"trailingPE": pe, "enterpriseToEbitda": ev, "priceToSalesTrailing12Months": ps,
                      "operatingMargins": mop, "currency": "USD", "_usd": {"market_cap": mcap}},
            serie_semanal=_serie(s0, s1),
        ))
    # Un snapshot viejo de KO que no tiene que pesar.
    db.add(FundamentalesSnapshot(simbolo_yahoo="KO", fecha=HOY - timedelta(days=30), moneda="USD",
                                 market_cap_usd=1.0, metricas={"trailingPE": 99.0}, ratios_precio_confiables=1))
    db.add(InstrumentoInversion(ticker="KOD", nombre="KO", tipo_instrumento="CEDEAR", mercado="BCBA",
                                moneda="USD", sector="Cosumo Masivo", pais="AR"))
    db.add(MovimientoInversion(fecha=date(2024, 1, 2), cartera="c", ticker="KOD", tipo_movimiento="compra",
                               cantidad=10, precio=10.0, moneda="USD", comision=0.0))
    db.add(WatchlistItem(ticker="CELH", nombre="Celsius", tipo_instrumento="CEDEAR"))
    db.commit()
    db.close()
    return Sesion


@pytest.fixture
def client(sesion):
    def override():
        s = sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ficha_de_valuacion(client):
    r = client.get("/api/inversiones/valuacion/KOD")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ticker_base"] == "KO" and b["estado_datos"] == "ok"
    assert b["clasificacion"]["sector"] == "Consumo básico"
    assert b["clasificacion"]["fuentes"]["sector"] == "yahoo"
    assert [p["ticker_base"] for p in b["pares"]["items"]] == ["PEP", "MNST", "KDP", "CELH"]
    assert b["lectura"] == "barata"
    assert any("Más barata" in f["texto"] for f in b["frases"])
    fila_pe = next(f for f in b["tabla"]["filas"] if f["clave"] == "pe")
    assert fila_pe["valores"]["KO"] == 14.0          # el snapshot nuevo, no el viejo
    assert fila_pe["valores"]["PEP"] == 24.0
    assert fila_pe["banda"] == "mejor"
    assert b["tabla"]["columnas"][0] == "KO"
    assert b["fuerza_relativa"][0]["propio"] == 100.0
    assert b["fuerza_relativa"][-1]["propio"] == pytest.approx(120.0)
    assert b["fuerza_relativa"][-1]["mediana_pares"] is not None


def test_ficha_de_ticker_sin_datos(client):
    r = client.get("/api/inversiones/valuacion/ZZZZ")
    assert r.status_code == 200
    b = r.json()
    assert b["estado_datos"] == "pendiente"
    assert b["lectura"] == "datos_insuficientes"


def test_lista_por_universo(client):
    cartera = client.get("/api/inversiones/valuacion", params={"universo": "cartera"}).json()
    assert [it["ticker"] for it in cartera["items"]] == ["KOD"]
    assert cartera["items"][0]["en_cartera"] and cartera["items"][0]["lectura"] == "barata"

    watch = client.get("/api/inversiones/valuacion", params={"universo": "watchlist"}).json()
    assert [it["ticker"] for it in watch["items"]] == ["CELH"]
    assert watch["items"][0]["lectura"] in ("cara", "mixta")

    cat = client.get("/api/inversiones/valuacion", params={"universo": "catalogo"}).json()
    assert cat["total"] == 5
    assert sum(cat["conteos"].values()) == 5

    filtrado = client.get("/api/inversiones/valuacion", params={"universo": "catalogo", "lectura": "barata"}).json()
    assert all(it["lectura"] == "barata" for it in filtrado["items"])


def test_universo_invalido(client):
    assert client.get("/api/inversiones/valuacion", params={"universo": "x"}).status_code == 422
