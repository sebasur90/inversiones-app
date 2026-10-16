"""Historial de diagnósticos: se registra sólo lo que cambió, point-in-time, sin tumbar nada."""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, ClasificacionAuto, DiagnosticoHistorial, FundamentalesSnapshot, IndiceMercado, WatchlistItem, get_db,
)
from app.main import app
from app.services import clasificacion_analytics as ca
from app.services import diagnostico_empresa_engine as de
from app.services import historial_diagnosticos as hd
from app.services import scheduler

HOY = date.today()
AYER = HOY - timedelta(days=1)
URL = "/api/inversiones/valuacion"

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
        "currentPrice": 100.0, "marketCap": mcap, "enterpriseValue": mcap,
        "mostRecentQuarter": 1_700_000_000,
        "_usd": {"market_cap": mcap, "freeCashflow": mcap * 0.04 / val},
    }


def _snapshot(t, fecha, val, fund, mcap):
    return FundamentalesSnapshot(
        simbolo_yahoo=t, fecha=fecha, moneda="USD", market_cap_usd=mcap, ratios_precio_confiables=1,
        metricas=_metricas(val, fund, mcap),
        serie_semanal=[{"fecha": (fecha - timedelta(weeks=52 - i)).isoformat(), "cierre": 50.0 + i} for i in range(53)],
    )


@pytest.fixture
def sesion(monkeypatch):
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: [
        {"simbolo": t, "descripcion": t, "moneda": "ARS", "tipo": "CEDEAR"} for t in EMISORES
    ])
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
            intentos_fallidos=0, fecha_fundamentales=AYER,
        ))
        db.add(_snapshot(t, AYER, val, fund, mcap))
    for t in ("KO", "PEP"):
        db.add(WatchlistItem(ticker=t, nombre=t, tipo_instrumento="CEDEAR"))
    db.commit()
    db.close()
    return Sesion


@pytest.fixture
def db(sesion):
    s = sesion()
    yield s
    s.close()


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


def _filas(db, ticker=None):
    q = db.query(DiagnosticoHistorial).order_by(DiagnosticoHistorial.id)
    return q.filter_by(ticker_base=ticker).all() if ticker else q.all()


# ── Registro ────────────────────────────────────────────────────────────────

def test_registra_una_foto_por_emisor_del_universo(db):
    r = hd.registrar(db, HOY, ("watchlist",))
    assert r["nuevas"] == 2 and r["errores"] == 0 and r["emisores"] == 2
    ko = _filas(db, "KO")[0]
    assert ko.version_diagnostico == de.VERSION_REGLAS and ko.fecha == HOY and ko.fecha_dato == AYER
    assert set(ko.estados) == {"valuacion", "calidad", "crecimiento", "solidez", "confianza"}
    assert ko.estados["valuacion"]["estado"] and ko.estados["valuacion"]["regla"] and ko.estados["valuacion"]["razon"]
    assert ko.lectura and ko.confianza and ko.precio == 100 and ko.moneda == "USD"
    assert set(ko.pares) == {"PEP", "MNST", "KDP", "CELH"} and ko.huella


def test_sin_cambios_no_agrega_filas(db):
    hd.registrar(db, HOY, ("watchlist",))
    r = hd.registrar(db, HOY + timedelta(days=1), ("watchlist",))
    assert r["nuevas"] == 0 and r["sin_cambios"] == 2
    assert len(_filas(db)) == 2


def test_un_snapshot_nuevo_agrega_una_fila_y_conserva_la_anterior(db):
    hd.registrar(db, HOY, ("watchlist",))
    antes = _filas(db, "KO")[0]
    antes_estados = json.dumps(antes.estados, sort_keys=True)
    db.add(_snapshot("KO", HOY, 1.0, 1.0, 3.0e11))
    db.commit()
    r = hd.registrar(db, HOY, ("watchlist",))
    assert r["nuevas"] == 1 and r["sin_cambios"] == 1
    filas = _filas(db, "KO")
    assert len(filas) == 2 and filas[1].fecha_dato == HOY
    assert json.dumps(filas[0].estados, sort_keys=True) == antes_estados        # la foto vieja no se toca


def test_un_cambio_de_reglas_registra_una_foto_marcada_y_no_cuenta_como_cambio_de_la_empresa(db, monkeypatch):
    hd.registrar(db, HOY, ("watchlist",))
    monkeypatch.setattr(de, "VERSION_REGLAS", de.VERSION_REGLAS + 1)
    hd.registrar(db, HOY, ("watchlist",))
    filas = _filas(db, "KO")
    assert [f.version_diagnostico for f in filas] == [de.VERSION_REGLAS - 1, de.VERSION_REGLAS]
    linea = hd.lista_historial(db, "KO")
    nueva = linea["items"][0]                                 # la más reciente primero
    assert nueva["cambio_de_reglas"] is True and nueva["cambios"] == []


def test_lista_historial_marca_los_cambios_de_estado_entre_fotos(db):
    hd.registrar(db, HOY, ("watchlist",))
    # la empresa se encarece mucho: cambia su lectura de valuación
    snap = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO").one()
    snap.metricas = _metricas(2.5, 1.0, 3.0e11)
    db.commit()
    db.add(_snapshot("KO", HOY, 2.5, 1.0, 3.0e11))
    db.commit()
    hd.registrar(db, HOY, ("watchlist",))
    linea = hd.lista_historial(db, "KO")
    assert linea["total"] == 2
    cambios = linea["items"][0]["cambios"]
    assert any(c["dimension"] == "valuacion" and c["de"] != c["a"] for c in cambios)
    assert linea["items"][1]["cambios"] == []


def test_todo_lo_guardado_es_json_serializable_y_las_fechas_van_en_iso(db):
    hd.registrar(db, HOY, ("watchlist",))
    for f in _filas(db):
        for col in (f.estados, f.metricas, f.pares, f.comparador, f.valor_razonable):
            json.dumps(col)
        assert isinstance(f.metricas["periodo_contable"], str)         # epoch → fecha ISO


def test_cartera_y_watchlist_llevan_comparador_y_valor_razonable_resumidos(db):
    hd.registrar(db, HOY, ("watchlist",))
    ko = _filas(db, "KO")[0]
    assert ko.version_comparador == 1 and ko.version_valor == 1
    assert ko.comparador["estado"] == "ok" and ko.comparador["conclusion"]["regla_aplicada"]
    assert "tabla" not in ko.comparador and "pares" not in ko.comparador and "rechazadas" not in ko.comparador
    assert ko.comparador["ranking"] and set(ko.comparador["ranking"][0]) >= {"clave", "tercio", "estado_objetivo"}
    assert ko.valor_razonable["estado"] == "ok" and len(ko.valor_razonable["escenarios"]) == 3


def test_el_catalogo_registra_el_diagnostico_sin_comparador_ni_valor(db):
    r = hd.registrar(db, HOY, ("catalogo",))
    assert r["nuevas"] == 5
    mnst = _filas(db, "MNST")[0]
    assert mnst.comparador is None and mnst.valor_razonable is None and mnst.version_comparador is None
    assert _filas(db, "KO")[0].comparador is not None          # lo que está en la watchlist sí


def test_un_emisor_sin_datos_no_genera_foto(db):
    db.add(WatchlistItem(ticker="ZZZ", nombre="ZZZ", tipo_instrumento="CEDEAR"))
    db.commit()
    r = hd.registrar(db, HOY, ("watchlist",))
    assert r["sin_datos"] == 1 and not _filas(db, "ZZZ")


def test_un_emisor_que_falla_no_tumba_a_los_demas(db, monkeypatch):
    original = hd.construir_fila

    def rota(u, ticker, extras, hoy):
        if ticker == "KO":
            raise RuntimeError("dato raro")
        return original(u, ticker, extras, hoy)

    monkeypatch.setattr(hd, "construir_fila", rota)
    r = hd.registrar(db, HOY, ("watchlist",))
    assert r["errores"] == 1 and r["nuevas"] == 1 and _filas(db, "PEP") and not _filas(db, "KO")


def test_si_falla_el_comparador_igual_se_registra_el_diagnostico(db, monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("comparador roto")

    monkeypatch.setattr(hd.comparador_analytics, "calcular", explota)
    r = hd.registrar(db, HOY, ("watchlist",))
    assert r["nuevas"] == 2 and r["errores"] == 0 and _filas(db, "KO")[0].comparador is None


def test_universo_configurable_por_entorno(monkeypatch):
    monkeypatch.delenv("HISTORIAL_UNIVERSO", raising=False)
    assert hd.universos_configurados() == ("cartera", "watchlist")
    monkeypatch.setenv("HISTORIAL_UNIVERSO", "catalogo, watchlist ,nada")
    assert hd.universos_configurados() == ("catalogo", "watchlist")
    monkeypatch.setenv("HISTORIAL_UNIVERSO", "nada")
    assert hd.universos_configurados() == ("cartera", "watchlist")


def test_registrar_no_escribe_otras_tablas(db):
    antes = db.query(FundamentalesSnapshot).count()
    hd.registrar(db, HOY, ("watchlist",))
    assert db.query(FundamentalesSnapshot).count() == antes


# ── Scheduler ───────────────────────────────────────────────────────────────

def test_un_historial_que_falla_no_propaga(monkeypatch):
    def explota(db):
        raise RuntimeError("DB bloqueada")

    monkeypatch.setattr(hd, "registrar", explota)
    scheduler._registrar_historial_diagnosticos()          # no debe lanzar


def test_el_job_de_fundamentales_registra_el_historial_aunque_la_ingesta_falle(monkeypatch):
    from app.services import fundamentales_ingesta

    llamado = {"historial": 0}
    monkeypatch.setattr(fundamentales_ingesta, "correr", lambda db: (_ for _ in ()).throw(RuntimeError("Yahoo caído")))
    monkeypatch.setattr(scheduler, "_registrar_historial_diagnosticos", lambda: llamado.__setitem__("historial", 1))
    scheduler.correr_fundamentales()
    assert llamado["historial"] == 1


# ── API ─────────────────────────────────────────────────────────────────────

def test_endpoint_historial(client, sesion):
    db = sesion()
    hd.registrar(db, HOY, ("watchlist",))
    db.close()
    b = client.get(f"{URL}/KO/historial").json()
    assert b["ticker_base"] == "KO" and b["total"] == 1
    item = b["items"][0]
    assert item["version_diagnostico"] == de.VERSION_REGLAS and item["estados"]["valuacion"]["estado"]
    assert client.get(f"{URL}/ZZZ/historial").json()["total"] == 0


def test_endpoint_backtest_sin_muestra_lo_dice(client, sesion):
    db = sesion()
    hd.registrar(db, HOY, ("watchlist",))
    db.close()
    r = client.get(f"{URL}/historial/backtest")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["suficiente"] is False and b["minimo_muestra"] == 30 and b["limites"]
    assert all(not c["suficiente"] for e in b["estados"] for c in e["horizontes"].values())


def test_las_razones_y_reglas_guardadas_no_dicen_compra_ni_venta(db):
    """Esas razones viajan tal cual a los avisos de Telegram: tienen que cumplir la misma regla de lenguaje."""
    import re

    prohibidas = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)
    hd.registrar(db, HOY, ("catalogo",))
    for f in _filas(db):
        for dim in f.estados.values():
            assert not prohibidas.search(dim["razon"] or ""), dim["razon"]
            assert not prohibidas.search(dim["regla"] or ""), dim["regla"]
