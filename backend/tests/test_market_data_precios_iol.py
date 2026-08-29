"""Tests de la integración de IOL en `market_data.precios`: IOL primero, data912/analisistecnico
como red de contención. Sin red: mockea `iol` y `data912`/`analisistecnico`."""
from datetime import date, timedelta

import pytest

from backend.app.services.market_data import precios as mdp
from backend.app.services.market_data import analisistecnico, data912

_DB = object()  # las funciones de iol.py no usan `db` en estos tests, sólo lo reenvían


def _inst(ticker, tipo="Bono", moneda="ARS"):
    return {"ticker": ticker, "tipo_instrumento": tipo, "moneda": moneda}


def _px(ticker, precio, fecha=date(2026, 7, 27)):
    return {"ticker": ticker, "fecha": fecha, "precio": precio, "moneda": "ARS"}


HOY = date(2026, 8, 28)


@pytest.mark.parametrize("tipo, esperado", [
    ("FCI", True), ("fci", True), ("Fondo Común de Inversión", True),
    ("Bono", False), ("Accion", False), ("", False), (None, False),
])
def test_es_fci(tipo, esperado):
    assert mdp._es_fci(tipo) is esperado


# --- fetch_precios_api: IOL primero, data912 como red de contención ----------------------------

def test_iol_cubre_todo_no_llama_a_data912(monkeypatch):
    def _boom():
        raise AssertionError("no debería llamar a data912 si IOL cubrió todo")

    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {"AL30": (85160.0, "ARS")})
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", _boom)
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, issues = mdp.fetch_precios_api([_inst("AL30")], [_px("AL30", 84000.0)], set(), _DB, hoy=HOY)
    assert len(filas) == 1
    assert filas[0]["fuente"] == "iol"
    assert filas[0]["precio"] == 85160.0


def test_iol_parcial_completa_con_data912(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {"AL30": (85160.0, "ARS")})
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    instrumentos = [_inst("AL30"), _inst("TZXD7")]
    precios_sheet = [_px("AL30", 84000.0), _px("TZXD7", 2.7135)]
    filas, issues = mdp.fetch_precios_api(instrumentos, precios_sheet, set(), _DB, hoy=HOY)

    por_ticker = {f["ticker"]: f for f in filas}
    assert por_ticker["AL30"]["fuente"] == "iol"
    assert por_ticker["TZXD7"]["fuente"] == "api"
    assert round(por_ticker["TZXD7"]["precio"], 4) == 2.7285


def test_iol_caida_cae_completo_a_data912_y_reporta(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: None)
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"AL30": 85160.0})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, issues = mdp.fetch_precios_api([_inst("AL30")], [_px("AL30", 84000.0)], set(), _DB, hoy=HOY)
    assert len(filas) == 1
    assert filas[0]["fuente"] == "api"
    assert any(i.regla == "iol_no_disponible" for i in issues)


def test_iol_y_data912_caidos_no_carga_nada(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: None)
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: None)
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, issues = mdp.fetch_precios_api([_inst("AL30")], [_px("AL30", 84000.0)], set(), _DB, hoy=HOY)
    assert filas == []
    assert any(i.regla == "iol_no_disponible" for i in issues)
    assert any(i.regla == "data912_no_disponible" for i in issues)


def test_fci_solo_via_iol_sin_respaldo(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_fci", lambda db: {"FCIABC": (1234.5, "ARS")})

    filas, issues = mdp.fetch_precios_api(
        [_inst("FCIABC", tipo="FCI")], [_px("FCIABC", 1200.0)], set(), _DB, hoy=HOY,
    )
    assert len(filas) == 1 and filas[0]["fuente"] == "iol"


def test_fci_sin_iol_no_carga_y_reporta(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_fci", lambda db: None)

    filas, issues = mdp.fetch_precios_api(
        [_inst("FCIABC", tipo="FCI")], [_px("FCIABC", 1200.0)], set(), _DB, hoy=HOY,
    )
    assert filas == []
    assert any(i.regla == "iol_no_disponible" for i in issues)


def test_escala_se_calibra_igual_via_iol(monkeypatch):
    """IOL también cotiza renta fija por lámina de 100 VN: la calibración de escala aplica igual."""
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {"TZXD7": (272.85, "ARS")})
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, issues = mdp.fetch_precios_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)], set(), _DB, hoy=HOY,
    )
    assert issues == []
    assert round(filas[0]["precio"], 4) == 2.7285


def test_sin_precio_manual_previo_no_carga_ni_via_iol(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {"TZXD7": (272.85, "ARS")})
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, issues = mdp.fetch_precios_api([_inst("TZXD7")], [], set(), _DB, hoy=HOY)
    assert filas == []
    assert any(i.regla == "sin_precio_para_calibrar" for i in issues)


# --- fetch_backfill_iol: ONs y renta variable, lo que analisistecnico no cubre ------------------

def test_backfill_iol_cubre_on_marcada_sin_serie(monkeypatch):
    estado = {"MGCJO": {"factor_escala": None, "factor_fecha": None,
                        "backfill_estado": "sin_serie", "backfill_intento": HOY - timedelta(days=91)}}
    serie = [(date(2025, 6, 2), 105000.0), (date(2025, 6, 3), 106000.0)]
    monkeypatch.setattr(mdp.iol_client, "fetch_historico", lambda db, t, d, h: serie)

    filas, issues = mdp.fetch_backfill_iol(
        [_inst("MGCJO", tipo="ON")], [_px("MGCJO", 105000.0, fecha=date(2026, 7, 27))],
        set(), {"MGCJO": date(2025, 6, 1)}, {}, _DB, hoy=HOY, estado_por_ticker=estado,
    )
    assert issues == []
    assert all(f["fuente"] == "iol" for f in filas)
    assert {f["fecha"] for f in filas} == {date(2025, 6, 2), date(2025, 6, 3)}


def test_backfill_iol_cubre_renta_variable_sin_pedirlo_a_analisistecnico(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("analisistecnico no cubre renta variable")

    monkeypatch.setattr(analisistecnico, "fetch_historico_bono", _boom)
    serie = [(date(2025, 6, 2), 5000.0)]
    monkeypatch.setattr(mdp.iol_client, "fetch_historico", lambda db, t, d, h: serie)

    filas, issues = mdp.fetch_backfill_iol(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0, fecha=date(2026, 7, 27))],
        set(), {"GGAL": date(2025, 6, 1)}, {}, _DB, hoy=HOY,
    )
    assert filas and filas[0]["fuente"] == "iol"


def test_backfill_iol_tampoco_tiene_serie_marca_sin_serie_iol(monkeypatch):
    estado: dict = {}
    monkeypatch.setattr(mdp.iol_client, "fetch_historico", lambda db, t, d, h: None)

    filas, issues = mdp.fetch_backfill_iol(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0, fecha=date(2026, 7, 27))],
        set(), {"GGAL": date(2025, 6, 1)}, {}, _DB, hoy=HOY, estado_por_ticker=estado,
    )
    assert filas == []
    assert issues[0].regla == "sin_historico_backfill_iol"
    assert estado["GGAL"]["backfill_estado"] == "sin_serie_iol"


def test_backfill_iol_no_pisa_fechas_del_sheet(monkeypatch):
    serie = [(date(2025, 6, 2), 5000.0), (date(2026, 7, 27), 5100.0)]
    monkeypatch.setattr(mdp.iol_client, "fetch_historico", lambda db, t, d, h: serie)

    filas, issues = mdp.fetch_backfill_iol(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0, fecha=date(2026, 7, 27))],
        {("GGAL", date(2026, 7, 27))}, {"GGAL": date(2025, 6, 1)}, {}, _DB, hoy=HOY,
    )
    assert {f["fecha"] for f in filas} == {date(2025, 6, 2)}


def test_backfill_iol_converge_no_vuelve_a_pedir(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("ya está backfilleado hasta el piso")

    monkeypatch.setattr(mdp.iol_client, "fetch_historico", _boom)
    filas, issues = mdp.fetch_backfill_iol(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0, fecha=date(2026, 7, 27))],
        set(), {"GGAL": date(2025, 6, 1)}, {"GGAL": date(2025, 6, 10)}, _DB, hoy=HOY,
    )
    assert filas == [] and issues == []


def test_paneles_se_piden_una_sola_vez_para_todas_las_familias(monkeypatch):
    """Los paneles traen renta fija y renta variable en la misma tanda: pedirlos una vez por
    familia duplicaría el consumo del cupo mensual de IOL."""
    llamadas = []

    def _paneles(db):
        llamadas.append(db)
        return {"AL30": (85160.0, "ARS"), "GGAL": (5100.0, "ARS")}

    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", _paneles)
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, _ = mdp.fetch_precios_api(
        [_inst("AL30"), _inst("GGAL", tipo="Accion")],
        [_px("AL30", 84000.0), _px("GGAL", 5050.0)],
        set(), _DB, hoy=HOY,
    )
    assert len(llamadas) == 1
    assert {f["ticker"] for f in filas} == {"AL30", "GGAL"}


def test_sin_serie_iol_gatea_tambien_el_reintento_de_analisistecnico(monkeypatch):
    """A3: 'sin_serie_iol' lo escribe `fetch_backfill_iol` sobre el mismo estado que gatea a
    `fetch_backfill_renta_fija_api`. Si esta última no lo reconociera, las dos se reintentarían
    mutuamente en cada sync (cada una reescribe el estado que gatea a la otra) y la cota de A3
    nunca frenaría."""
    def _boom(*a, **kw):
        raise AssertionError("no debería reintentar analisistecnico antes de los 90 días")

    monkeypatch.setattr(analisistecnico, "fetch_historico_bono", _boom)
    estado = {"MGCJO": {"factor_escala": None, "factor_fecha": None,
                        "backfill_estado": "sin_serie_iol",
                        "backfill_intento": HOY - timedelta(days=5)}}

    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("MGCJO", tipo="ON")], [_px("MGCJO", 105000.0)],
        set(), {"MGCJO": date(2025, 6, 1)}, {}, hoy=HOY, estado_por_ticker=estado,
    )
    assert filas == [] and issues == []
    assert estado["MGCJO"]["backfill_estado"] == "sin_serie_iol"


def test_sin_serie_iol_se_limpia_cuando_analisistecnico_empieza_a_cubrirlo(monkeypatch):
    serie = [(date(2025, 6, 2), 105000.0)]
    monkeypatch.setattr(analisistecnico, "fetch_historico_bono", lambda t, d, h: serie)
    estado = {"MGCJO": {"factor_escala": None, "factor_fecha": None,
                        "backfill_estado": "sin_serie_iol",
                        "backfill_intento": HOY - timedelta(days=91)}}

    filas, _ = mdp.fetch_backfill_renta_fija_api(
        [_inst("MGCJO", tipo="ON")], [_px("MGCJO", 105000.0)],
        set(), {"MGCJO": date(2025, 6, 1)}, {}, hoy=HOY, estado_por_ticker=estado,
    )
    assert filas and estado["MGCJO"]["backfill_estado"] is None
