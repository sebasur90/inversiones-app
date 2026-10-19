"""GET /api/inversiones/mapa-mercado: lista plana del universo con clasificación, tamaño,
variación y relación con el usuario. SQLite en memoria y catálogo fijo."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, ClasificacionAuto, FundamentalesSnapshot, IndiceMercado, InstrumentoInversion,
    MovimientoInversion, PrecioInstrumento, VariacionMercado, WatchlistItem, get_db,
)
from app.main import app
from app.services import clasificacion_analytics as ca
from app.services import fundamentales_ingesta as fi

CATALOGO = [
    {"simbolo": "KO", "descripcion": "Cedear Coca Cola", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "KOD", "descripcion": "Cedear Coca Cola", "moneda": "USD", "tipo": "CEDEAR"},
    {"simbolo": "PEP", "descripcion": "Cedear Pepsico", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "MSFT", "descripcion": "Cedear Microsoft", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "ZZZZ", "descripcion": "Cedear Desconocido", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "ALUA", "descripcion": "Aluar", "moneda": "ARS", "tipo": "Acción"},
    {"simbolo": "AL30", "descripcion": "Bono AL30", "moneda": "ARS", "tipo": "Bono"},
]
SEED = {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}}
HOY = date.today()


def _auto(base, simbolo, nombre, sector, industria, pais, region, tipo="CEDEAR-acción", estado="ok"):
    return ClasificacionAuto(
        ticker_base=base, tipo_catalogo="CEDEAR", simbolo_yahoo=simbolo, nombre=nombre, tipo=tipo,
        sector=sector, industria=industria, pais=pais, region=region, estado=estado,
        intentos_fallidos=0, metodo_mapeo="identidad",
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(fi, "cargar_catalogo", lambda: CATALOGO)
    monkeypatch.setattr(fi, "cargar_seed", lambda: SEED)
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: CATALOGO)
    monkeypatch.setattr(ca, "cargar_seed", lambda: SEED)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(IndiceMercado(fecha=HOY, mep=1000.0))
    db.add_all([
        _auto("KO", "KO", "Coca-Cola", "Consumo defensivo", "Bebidas sin alcohol", "Estados Unidos", "EEUU"),
        _auto("PEP", "PEP", "PepsiCo", "Consumo defensivo", "Bebidas sin alcohol", "Estados Unidos", "EEUU"),
        _auto("MSFT", "MSFT", "Microsoft", "Tecnología", "Software", "Estados Unidos", "EEUU"),
        _auto("ZZZZ", "ZZZZ", None, None, None, None, None, estado="no_encontrado"),
    ])
    db.add(FundamentalesSnapshot(simbolo_yahoo="KO", fecha=HOY, moneda="USD", market_cap_usd=3.0e11, metricas={}))
    db.add(FundamentalesSnapshot(simbolo_yahoo="PEP", fecha=HOY, moneda="USD", market_cap_usd=2.0e11, metricas={}))
    db.add(VariacionMercado(
        simbolo_yahoo="KO", fecha_cierre=HOY, cierre=63.0, moneda="USD",
        var_1d=0.05, var_1s=0.1, var_1m=None, var_1a=None, actualizado=datetime.utcnow(),
    ))
    # KO en cartera por su variante en dólares; PEP en watchlist.
    db.add(InstrumentoInversion(ticker="KOD", nombre="Coca-Cola", tipo_instrumento="CEDEAR",
                                mercado="Global", moneda="USD", sector="Consumo", pais="US"))
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="KOD", tipo_movimiento="compra",
                               cantidad=10, precio=50.0, moneda="USD", comision=0.0))
    db.add(PrecioInstrumento(fecha=HOY, ticker="KOD", precio=60.0, moneda="USD", fuente="sheet"))
    db.add(WatchlistItem(ticker="PEP", nombre="PepsiCo", tipo_instrumento="CEDEAR", sector="Consumo", pais="US"))
    db.commit()
    db.close()

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _items(client):
    r = client.get("/api/inversiones/mapa-mercado")
    assert r.status_code == 200
    return r.json(), {i["ticker_base"]: i for i in r.json()["items"]}


def test_incluye_renta_variable_y_excluye_renta_fija(client):
    _, items = _items(client)
    assert "AL30" not in items
    assert {"KO", "PEP", "MSFT"} <= set(items)


def test_un_emisor_que_yahoo_no_conoce_y_no_es_del_usuario_no_aparece(client):
    _, items = _items(client)
    assert "ZZZZ" not in items


def test_trae_clasificacion_tamano_y_variacion(client):
    _, items = _items(client)
    ko = items["KO"]
    assert ko["sector"] == "Consumo defensivo" and ko["industria"] == "Bebidas sin alcohol"
    assert ko["region"] == "EEUU" and ko["pais"] == "Estados Unidos"
    assert ko["tamano_empresa"].startswith("Mega")
    assert ko["market_cap_usd"] == 3.0e11
    assert ko["var_1d"] == pytest.approx(0.05) and ko["var_1s"] == pytest.approx(0.1)
    assert ko["var_1m"] is None
    assert ko["moneda_variacion"] == "USD"


def test_sin_variacion_ni_market_cap_queda_con_none_y_tamano_sin_dato(client):
    _, items = _items(client)
    msft = items["MSFT"]
    assert msft["var_1d"] is None and msft["market_cap_usd"] is None
    assert msft["tamano_empresa"] == "Sin dato"


def test_la_variante_en_dolares_cuenta_como_el_emisor_base(client):
    _, items = _items(client)
    assert items["KO"]["en_cartera"] is True        # la cartera tiene KOD
    assert items["KO"]["ticker"] == "KO"
    assert items["PEP"]["en_cartera"] is False
    assert items["PEP"]["en_watchlist"] is True


def test_el_peso_en_cartera_es_un_porcentaje_sin_montos(client):
    data, items = _items(client)
    assert items["KO"]["peso_cartera"] == pytest.approx(100.0)
    assert items["PEP"]["peso_cartera"] is None
    assert "valor_usd" not in items["KO"] and "valor_ars" not in items["KO"]


def test_cobertura_y_avisos(client):
    data, _ = _items(client)
    cob = data["cobertura"]
    assert cob["total"] == 3
    assert cob["con_variacion"] == 1
    assert cob["con_market_cap"] == 2
    assert cob["con_sector"] == 3
    assert any("sin variación" in a or "no tienen variación" in a for a in data["avisos"])
    assert data["actualizado"] is not None


def test_refrescar_responde_202_y_arranca_en_segundo_plano(client, monkeypatch):
    from app.routers import mapa_mercado as router_mm

    llamado = []
    monkeypatch.setattr(router_mm, "_corrida_en_segundo_plano", lambda: llamado.append(1))
    r = client.post("/api/inversiones/mapa-mercado/refrescar")
    assert r.status_code == 202 and r.json() == {"resultado": "iniciado"}
