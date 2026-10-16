"""Endpoints de valuación contra pares (`/valuacion`, `/valuacion/{ticker}`) sobre una DB con
clasificación y snapshots de fundamentales ya cargados."""
from datetime import date, datetime, timedelta

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
    # Precios en USD sin normalizar: el re-base lo hace el gráfico desde la fecha elegida.
    assert b["fuerza_relativa"][0]["propio"] == pytest.approx(50.0)
    assert b["fuerza_relativa"][-1]["propio"] == pytest.approx(60.0)
    ultimo = b["fuerza_relativa"][-1]
    assert set(ultimo["pares"]) == {"PEP", "MNST", "KDP", "CELH"}
    assert ultimo["pares"]["CELH"] == pytest.approx(20.0)
    assert b["fuerza_relativa"][0]["pares"]["PEP"] == pytest.approx(150.0)


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


def test_contra_un_solo_par_compara_directo(client):
    r = client.post("/api/inversiones/pares/KO", json={"par": "MNST", "accion": "quitar"})
    for p in ("KDP", "CELH", "PEP"):
        r = client.post("/api/inversiones/pares/KO", json={"par": p, "accion": "quitar"})
    r = client.post("/api/inversiones/pares/KO", json={"par": "PEP", "accion": "agregar"})
    b = r.json()
    assert [p["ticker_base"] for p in b["pares"]["items"]] == ["PEP"]
    assert b["lectura"] != "datos_insuficientes"
    fila_pe = next(f for f in b["tabla"]["filas"] if f["clave"] == "pe")
    assert fila_pe["metodo"] == "directo" and fila_pe["diferencia"] == pytest.approx(14 / 24 - 1, abs=1e-3)
    assert set(b["fuerza_relativa"][-1]["pares"]) == {"PEP"}


# ── regresiones de la auditoría ───────────────────────────────────────────

def test_la_serie_se_toma_del_snapshot_mas_nuevo_que_la_tenga(client, sesion):
    """Si la descarga de hoy trajo fundamentales pero no la serie, el rendimiento y el gráfico no se pierden."""
    db = sesion()
    hoy = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="PEP", fecha=HOY).one()
    serie = hoy.serie_semanal
    hoy.serie_semanal = None
    db.add(FundamentalesSnapshot(simbolo_yahoo="PEP", fecha=HOY - timedelta(days=3), moneda="USD",
                                 market_cap_usd=2.0e11, metricas={"trailingPE": 24.0}, ratios_precio_confiables=1,
                                 serie_semanal=serie))
    db.commit()
    db.close()

    b = client.get("/api/inversiones/valuacion/KOD").json()
    assert "PEP" in b["fuerza_relativa"][-1]["pares"]
    fila = next(f for f in b["tabla"]["filas"] if f["clave"] == "rend_12m")
    assert fila["valores"]["PEP"] is not None
    # Los fundamentales siguen siendo los del snapshot de hoy.
    fila_pe = next(f for f in b["tabla"]["filas"] if f["clave"] == "pe")
    assert fila_pe["valores"]["PEP"] == 24.0 and b["fecha_dato"] == HOY.isoformat()


def test_serie_atrasada_se_avisa(client, sesion):
    db = sesion()
    ko = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO", fecha=HOY).one()
    serie = ko.serie_semanal
    ko.serie_semanal = None
    db.add(FundamentalesSnapshot(simbolo_yahoo="KO", fecha=HOY - timedelta(days=12), moneda="USD",
                                 market_cap_usd=3.0e11, metricas={"trailingPE": 14.0}, ratios_precio_confiables=1,
                                 serie_semanal=serie))
    db.commit()
    db.close()
    b = client.get("/api/inversiones/valuacion/KOD").json()
    assert any("serie de precios llega hasta" in a for a in b["advertencias"])


def test_correccion_manual_de_industria_en_castellano_encuentra_pares(client, sesion):
    from app.database import ClasificacionOverride

    db = sesion()
    # Un emisor de otra industria que el usuario reclasifica a mano con el nombre en castellano.
    db.add(ClasificacionAuto(
        ticker_base="ZZ", simbolo_yahoo="ZZ", estado="ok", tipo="CEDEAR-acción", nombre="ZZ Inc",
        quote_type="EQUITY", sector="Consumo básico", industria="Tabaco", industria_raw="Tobacco",
        pais="Estados Unidos", region="EEUU", intentos_fallidos=0, fecha_fundamentales=HOY,
    ))
    db.add(FundamentalesSnapshot(simbolo_yahoo="ZZ", fecha=HOY, moneda="USD", market_cap_usd=2.0e11,
                                 metricas={"trailingPE": 18.0, "_usd": {"market_cap": 2.0e11}},
                                 ratios_precio_confiables=1))
    db.add(ClasificacionOverride(ticker_base="ZZ", campo="industria", valor="Bebidas sin alcohol",
                                  fecha_actualizacion=datetime.utcnow()))
    db.commit()
    db.close()
    b = client.get("/api/inversiones/valuacion/ZZ").json()
    assert "misma industria" in b["pares"]["criterio"]
    assert {"KO", "PEP"} <= {p["ticker_base"] for p in b["pares"]["items"]}


# ── diagnóstico integral en la API ────────────────────────────────────────

DIMENSIONES = ["valuacion", "calidad", "crecimiento", "solidez", "confianza"]


def test_la_ficha_trae_el_diagnostico_en_cinco_dimensiones(client):
    b = client.get("/api/inversiones/valuacion/KOD").json()
    d = b["diagnostico"]
    assert d["version_reglas"] >= 2
    assert [x["clave"] for x in d["dimensiones"]] == DIMENSIONES
    por = {x["clave"]: x for x in d["dimensiones"]}
    assert por["valuacion"]["estado"] == b["lectura_texto"]            # la lectura de siempre, sin cambios
    assert all(x["regla"] and x["nivel"] for x in d["dimensiones"])
    # Cada fila de la tabla dice de dónde sale el dato
    assert {f["origen"] for f in b["tabla"]["filas"]} <= {"observado", "estimado", "calculado"}
    assert next(f for f in b["tabla"]["filas"] if f["clave"] == "rend_12m")["origen"] == "calculado"
    # Con pocos fundamentales en el fixture la confianza no puede ser "alta" ni lo oculta
    assert por["confianza"]["estado"] in ("Media", "Baja") and por["confianza"]["faltantes"]


def test_ticker_sin_datos_no_inventa_diagnostico(client):
    d = client.get("/api/inversiones/valuacion/ZZZZ").json()["diagnostico"]
    assert d["confianza"] == "sin_datos"
    assert all(x["nivel"] == "sin_datos" and x["razones"] == [] for x in d["dimensiones"])


def test_la_lista_trae_las_dimensiones_de_cada_tarjeta(client):
    items = client.get("/api/inversiones/valuacion", params={"universo": "catalogo"}).json()["items"]
    assert items and all([d["clave"] for d in it["dimensiones"]] == DIMENSIONES for it in items)
    ko = next(it for it in items if it["ticker_base"] == "KO")
    assert next(d for d in ko["dimensiones"] if d["clave"] == "valuacion")["percentil"] is not None


def test_ticker_en_cartera_y_en_watchlist_figura_una_vez_en_cada_universo(client, sesion):
    db = sesion()
    db.add(WatchlistItem(ticker="KOD", nombre="Coca", tipo_instrumento="CEDEAR"))
    db.commit()
    db.close()
    cartera = client.get("/api/inversiones/valuacion", params={"universo": "cartera"}).json()["items"]
    assert [it["ticker"] for it in cartera] == ["KOD"] and cartera[0]["en_cartera"] and cartera[0]["en_watchlist"]
    watch = client.get("/api/inversiones/valuacion", params={"universo": "watchlist"}).json()["items"]
    assert sorted(it["ticker"] for it in watch) == ["CELH", "KOD"]


def test_un_snapshot_nuevo_invalida_el_diagnostico_anterior(client, sesion):
    antes = client.get("/api/inversiones/valuacion/KOD").json()
    pe_antes = next(f for f in antes["tabla"]["filas"] if f["clave"] == "pe")["valores"]["KO"]
    db = sesion()
    db.add(FundamentalesSnapshot(
        simbolo_yahoo="KO", fecha=HOY + timedelta(days=1), moneda="USD", market_cap_usd=3.0e11, ratios_precio_confiables=1,
        metricas={"trailingPE": 60.0, "enterpriseToEbitda": 40.0, "priceToSalesTrailing12Months": 9.0,
                  "operatingMargins": 0.30, "currency": "USD", "_usd": {"market_cap": 3.0e11}},
        serie_semanal=_serie(50, 60)))
    db.commit()
    db.close()
    despues = client.get("/api/inversiones/valuacion/KOD").json()
    pe_despues = next(f for f in despues["tabla"]["filas"] if f["clave"] == "pe")["valores"]["KO"]
    assert pe_antes == 14.0 and pe_despues == 60.0
    assert antes["lectura"] == "barata" and despues["lectura"] == "cara"
    assert next(d for d in despues["diagnostico"]["dimensiones"] if d["clave"] == "valuacion")["estado"] == despues["lectura_texto"]


def test_cambiar_los_pares_cambia_el_diagnostico(client):
    antes = client.get("/api/inversiones/valuacion/KOD").json()
    n_antes = next(d for d in antes["diagnostico"]["dimensiones"] if d["clave"] == "confianza")
    # Se quitan tres de los cuatro pares: queda uno solo (comparación directa) y la confianza lo dice.
    for par in ("MNST", "KDP", "CELH"):
        r = client.post("/api/inversiones/pares/KOD", json={"par": par, "accion": "quitar"})
        assert r.status_code == 200, r.text
    despues = client.get("/api/inversiones/valuacion/KOD").json()
    conf = next(d for d in despues["diagnostico"]["dimensiones"] if d["clave"] == "confianza")
    assert despues["n_pares_con_datos"] == 1 and conf["estado"] == "Baja"
    assert any("1 par con datos" in r["texto"] for r in conf["razones"])
    assert n_antes["razones"] != conf["razones"]


def test_cambio_de_sector_a_financiero_cambia_las_familias(client, sesion):
    from app.database import ClasificacionOverride

    antes = client.get("/api/inversiones/valuacion/KOD").json()
    assert {v["familia"] for v in antes["diagnostico"]["dimensiones"][0]["votos"]} == {"ganancias", "ventas_ebitda"}
    db = sesion()
    db.add(ClasificacionOverride(ticker_base="KO", campo="sector", valor="Financiero",
                                 fecha_actualizacion=datetime.utcnow()))
    db.commit()
    db.close()
    despues = client.get("/api/inversiones/valuacion/KOD").json()
    assert despues["clasificacion"]["sector"] == "Financiero"
    familias = {v["familia"] for v in despues["diagnostico"]["dimensiones"][0]["votos"]}
    assert "ventas_ebitda" not in familias        # un banco no se valúa por EV/EBITDA ni P/Ventas
