"""`GET /inversiones/valuacion/{ticker}/comparador` sobre una DB con clasificación y snapshots cargados."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, ClasificacionAuto, FundamentalesSnapshot, IndiceMercado, InstrumentoInversion, get_db,
)
from app.main import app
from app.services import clasificacion_analytics as ca

HOY = date.today()
URL = "/api/inversiones/valuacion"

# (val, fund, mcap): val > 1 = más cara; fund > 1 = mejores fundamentos
EMISORES = {
    "KO": (1.0, 1.0, 3.0e11),
    "PEP": (1.3, 1.2, 2.0e11),
    "MNST": (0.8, 0.9, 1.5e11),
    "KDP": (1.1, 0.8, 1.2e11),
    "CELH": (1.5, 1.4, 1.0e11),
}


def _metricas(val, fund, mcap):
    return {
        "trailingPE": 20 * val, "forwardPE": 18 * val, "enterpriseToEbitda": 12 * val,
        "priceToSalesTrailing12Months": 3 * val, "priceToBook": 3 * val, "dividendYield": 2.0,
        "grossMargins": 0.4 * fund, "operatingMargins": 0.2 * fund, "profitMargins": 0.12 * fund,
        "returnOnEquity": 0.15 * fund, "returnOnAssets": 0.06 * fund, "debtToEquity": 60 / fund,
        "revenueGrowth": 0.06 * fund, "earningsGrowth": 0.08 * fund, "currency": "USD",
        "_usd": {"market_cap": mcap, "freeCashflow": mcap * 0.04 / val},
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
    for t, (val, fund, mcap) in EMISORES.items():
        db.add(ClasificacionAuto(
            ticker_base=t, simbolo_yahoo=t, estado="ok", tipo="CEDEAR-acción", nombre=f"{t} Inc",
            quote_type="EQUITY", sector="Consumo básico", industria="Bebidas sin alcohol",
            industria_raw="Beverages - Non-Alcoholic", pais="Estados Unidos", region="EEUU",
            intentos_fallidos=0, fecha_fundamentales=HOY,
        ))
        db.add(FundamentalesSnapshot(
            simbolo_yahoo=t, fecha=HOY, moneda="USD", market_cap_usd=mcap, ratios_precio_confiables=1,
            metricas=_metricas(val, fund, mcap),
            serie_semanal=[{"fecha": (HOY - timedelta(weeks=52 - i)).isoformat(), "cierre": 50.0 + i} for i in range(53)],
        ))
    db.add(InstrumentoInversion(ticker="KOD", nombre="KO", tipo_instrumento="CEDEAR", mercado="BCBA",
                                moneda="USD", sector="Consumo Masivo", pais="AR"))
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


def _bases(lista):
    return [a["ticker_base"] for a in lista]


def test_comparador_por_defecto_usa_el_grupo_de_pares(client):
    r = client.get(f"{URL}/KO/comparador")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["estado"] == "ok" and b["ticker_base"] == "KO" and b["elegido_por_usuario"] is False
    assert sorted(b["seleccion"]) == ["CELH", "KDP", "MNST", "PEP"]
    assert all(a["origen"] == "grupo" and a["nivel"] == "alta" for a in b["alternativas"])
    assert [c["ticker_base"] for c in b["tabla"]["columnas"]][0] == "KO"
    assert {d["clave"] for d in b["ranking"]} == {"valuacion", "calidad", "crecimiento", "solidez"}
    assert b["conclusion"]["regla_aplicada"] in {"R1", "R2", "R3", "R4", "R5"}
    assert b["version_reglas"] == 1 and b["minimo"] == 2 and b["faltan"] == 0
    fila = next(f for f in b["tabla"]["filas"] if f["clave"] == "pe")
    assert fila["celdas"]["KO"]["valor"] == 20.0 and fila["unidad"] == "veces (x)" and fila["periodo"]
    assert b["fuerza_relativa"] and set(b["fuerza_relativa"][-1]["pares"]) == {"PEP", "MNST", "KDP", "CELH"}


def test_comparador_por_variante_de_moneda_resuelve_el_mismo_emisor(client):
    b = client.get(f"{URL}/KOD/comparador").json()
    assert b["ticker_base"] == "KO" and b["estado"] == "ok"


def test_con_elige_las_alternativas_y_cambia_el_resultado(client):
    defecto = client.get(f"{URL}/KO/comparador").json()
    elegido = client.get(f"{URL}/KO/comparador", params={"con": "PEP,MNST"}).json()
    assert elegido["seleccion"] == ["PEP", "MNST"] and elegido["elegido_por_usuario"] is True
    assert all(a["origen"] == "elegida" for a in elegido["alternativas"])
    assert elegido["tabla"]["columnas"][1]["ticker_base"] == "PEP"
    assert elegido["seleccion"] != defecto["seleccion"]
    assert {a["ticker_base"] for a in elegido["sugeridas"]} == {"KDP", "CELH"}


def test_la_variante_del_propio_instrumento_no_es_una_alternativa(client):
    b = client.get(f"{URL}/KO/comparador", params={"con": "KOD,PEP,MNST"}).json()
    assert b["seleccion"] == ["PEP", "MNST"]
    assert b["rechazadas"][0]["ticker_base"] == "KO" and "mismo instrumento" in b["rechazadas"][0]["motivo"]


def test_con_una_sola_alternativa_no_concluye_y_dice_cuanto_falta(client):
    b = client.get(f"{URL}/KO/comparador", params={"con": "PEP"}).json()
    assert b["estado"] == "insuficiente" and b["faltan"] == 1
    assert b["conclusion"] is None and b["ranking"] == [] and b["tabla"] is not None
    assert "faltan 1" in b["mensaje"]


def test_quitar_un_par_cambia_la_seleccion_y_el_cache_no_devuelve_lo_viejo(client):
    antes = client.get(f"{URL}/KO/comparador").json()
    assert "PEP" in antes["seleccion"]
    r = client.post("/api/inversiones/pares/KO", json={"par": "PEP", "accion": "quitar"})
    assert r.status_code == 200, r.text
    despues = client.get(f"{URL}/KO/comparador").json()
    assert "PEP" not in despues["seleccion"] and "PEP" not in {a["ticker_base"] for a in despues["sugeridas"]}
    assert sorted(despues["seleccion"]) == ["CELH", "KDP", "MNST"]


def test_agregar_un_par_a_mano_lo_marca_en_el_comparador(client):
    client.post("/api/inversiones/pares/KO", json={"par": "PEP", "accion": "quitar"})
    client.delete("/api/inversiones/pares/KO/PEP")
    b = client.get(f"{URL}/KO/comparador").json()
    assert "PEP" in b["seleccion"]


def test_ticker_sin_datos_o_desconocido_responde_sin_datos_no_404(client):
    r = client.get(f"{URL}/ZZZZ/comparador")
    assert r.status_code == 200
    b = r.json()
    assert b["estado"] == "sin_datos" and b["estado_datos"] == "pendiente" and b["tabla"] is None


def test_ticker_que_no_esta_en_la_planilla_igual_se_compara(client):
    b = client.get(f"{URL}/KDP/comparador").json()       # KDP no está en InstrumentoInversion
    assert b["estado"] == "ok" and "KDP" not in b["seleccion"]


def test_alternativa_desconocida_se_informa_como_rechazada(client):
    b = client.get(f"{URL}/KO/comparador", params={"con": "ZZZZ,PEP,MNST"}).json()
    assert b["seleccion"] == ["PEP", "MNST"]
    assert any(x["ticker_base"] == "ZZZZ" for x in b["rechazadas"])


def test_demasiadas_alternativas_es_un_error_de_validacion(client):
    r = client.get(f"{URL}/KO/comparador", params={"con": ",".join(f"T{i}" for i in range(7))})
    assert r.status_code == 422


def test_con_mal_formado_se_ignora(client):
    b = client.get(f"{URL}/KO/comparador", params={"con": " pep , ,mnst,PEP"}).json()
    assert b["seleccion"] == ["PEP", "MNST"]
