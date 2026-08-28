"""Tests de `market_data.precios` (renta fija vía data912) — sin red: mockea `data912`."""
from datetime import date, timedelta

import pytest

from backend.app.services.market_data import precios as mdp
from backend.app.services.market_data import data912


@pytest.mark.parametrize("tipo, esperado", [
    ("Bono", True),
    ("bono", True),
    ("BONO SOBERANO", True),
    ("Boncer", True),
    ("Obligación Negociable", True),
    ("ON", True),
    ("on", True),
    ("Letra", True),
    ("LECAP", True),
    ("CEDEAR", False),
    ("Acción", False),  # "accion" no debe matchear por el token "on"
    ("Accion", False),
    ("FCI", False),
    ("", False),
    (None, False),
])
def test_es_renta_fija(tipo, esperado):
    assert mdp._es_renta_fija(tipo) is esperado


def _inst(ticker, tipo="Bono", moneda="ARS"):
    return {"ticker": ticker, "tipo_instrumento": tipo, "moneda": moneda}


def _px(ticker, precio, fecha=date(2026, 7, 27)):
    return {"ticker": ticker, "fecha": fecha, "precio": precio, "moneda": "ARS"}


HOY = date(2026, 8, 28)


def test_escala_100_se_normaliza(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)], claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert len(filas) == 1
    assert filas[0]["ticker"] == "TZXD7"
    assert filas[0]["fecha"] == HOY
    assert filas[0]["fuente"] == "api"
    assert round(filas[0]["precio"], 4) == 2.7285  # 272.85 / 100


def test_escala_1_se_deja_igual(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"AL30": 85160.0})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("AL30")], [_px("AL30", 84000.0)], claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert filas[0]["precio"] == 85160.0


def test_sin_precio_previo_no_carga_y_reporta(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert len(issues) == 1
    assert issues[0].regla == "sin_precio_para_calibrar"
    assert issues[0].severidad.value == "info"


def test_ticker_no_encontrado_en_data912(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"OTRO": 100.0})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "ticker_no_mapeado"
    assert issues[0].severidad.value == "info"


def test_ratio_raro_no_carga_y_advierte(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 27.0})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert issues[0].severidad.value == "advertencia"


def test_api_caida_devuelve_none(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: None)
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY
    )
    assert filas is None
    assert len(issues) == 1
    assert issues[0].regla == "data912_no_disponible"


def test_fecha_ya_cubierta_por_el_sheet_se_saltea(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)],
        claves_excluir={("TZXD7", HOY)}, hoy=HOY,
    )
    assert filas == []
    assert issues == []


def test_sin_instrumentos_de_renta_fija_no_llama_api(monkeypatch):
    def _boom():
        raise AssertionError("no debería pegarle a data912 si no hay renta fija")

    monkeypatch.setattr(data912, "fetch_precios_renta_fija", _boom)
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("KO", tipo="CEDEAR")], [], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues == []


def test_usa_el_ultimo_precio_del_sheet_para_calibrar(monkeypatch):
    """Con varias filas del Sheet, calibra contra la más reciente."""
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    precios_sheet = [
        _px("TZXD7", 200.0, fecha=date(2026, 1, 1)),   # vieja y en otra escala: no debe ganar
        _px("TZXD7", 2.7135, fecha=date(2026, 7, 27)),
    ]
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], precios_sheet, claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert round(filas[0]["precio"], 4) == 2.7285
