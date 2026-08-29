"""Tests de `market_data.iol` — cliente de cotizaciones de IOL. Sin red: mockea
`iol_auth.get_autenticado`."""
from datetime import date

from backend.app.services.market_data import iol

_DB = object()  # las funciones de iol.py sólo reenvían `db` a iol_auth, no lo usan directamente


def test_fetch_precios_paneles_une_varios_paneles(monkeypatch):
    respuestas = {}
    for instrumento, panel, pais in iol._PANELES:
        url = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{instrumento}/{panel}/{pais}"
        respuestas[url] = None

    p0 = iol._PANELES[0]
    p1 = iol._PANELES[1]
    url0 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p0[0]}/{p0[1]}/{p0[2]}"
    url1 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p1[0]}/{p1[1]}/{p1[2]}"
    respuestas[url0] = {"titulos": [{"simbolo": "al30", "ultimoPrecio": 85160.0, "moneda": "ars"}]}
    respuestas[url1] = {"titulos": [{"simbolo": "GGAL", "ultimoPrecio": 5230.0, "moneda": "ARS"}]}

    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: respuestas.get(url))

    out = iol.fetch_precios_paneles(_DB)
    assert out == {"AL30": (85160.0, "ARS"), "GGAL": (5230.0, "ARS")}


def test_fetch_precios_paneles_ningun_panel_responde_es_none(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: None)
    assert iol.fetch_precios_paneles(_DB) is None


def test_fetch_precios_paneles_descarta_precios_invalidos(monkeypatch):
    p0 = iol._PANELES[0]
    url0 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p0[0]}/{p0[1]}/{p0[2]}"

    def _fake(db, url):
        if url == url0:
            return {"titulos": [
                {"simbolo": "AL30", "ultimoPrecio": 85160.0, "moneda": "ARS"},
                {"simbolo": "ROTO", "ultimoPrecio": None, "moneda": "ARS"},
                {"simbolo": "", "ultimoPrecio": 100.0, "moneda": "ARS"},
                {"simbolo": "NEG", "ultimoPrecio": -5.0, "moneda": "ARS"},
            ]}
        return None

    monkeypatch.setattr(iol.iol_auth, "get_autenticado", _fake)
    out = iol.fetch_precios_paneles(_DB)
    assert out == {"AL30": (85160.0, "ARS")}


def test_fetch_precios_paneles_primer_panel_gana_en_duplicados(monkeypatch):
    p0, p1 = iol._PANELES[0], iol._PANELES[1]
    url0 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p0[0]}/{p0[1]}/{p0[2]}"
    url1 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p1[0]}/{p1[1]}/{p1[2]}"

    def _fake(db, url):
        if url == url0:
            return {"titulos": [{"simbolo": "GGAL", "ultimoPrecio": 5230.0, "moneda": "ARS"}]}
        if url == url1:
            return {"titulos": [{"simbolo": "GGAL", "ultimoPrecio": 9999.0, "moneda": "ARS"}]}
        return None

    monkeypatch.setattr(iol.iol_auth, "get_autenticado", _fake)
    out = iol.fetch_precios_paneles(_DB)
    assert out["GGAL"] == (5230.0, "ARS")


def test_fetch_precios_fci(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"simbolo": "fciabc", "ultimoPrecio": 1234.5, "moneda": "ARS"},
        {"simbolo": "ROTO"},
    ])
    out = iol.fetch_precios_fci(_DB)
    assert out == {"FCIABC": (1234.5, "ARS")}


def test_fetch_precios_fci_caida_devuelve_none(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: None)
    assert iol.fetch_precios_fci(_DB) is None


def test_fetch_precio_simbolo(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado",
                         lambda db, url: {"ultimoPrecio": 272.85, "moneda": "ARS"})
    assert iol.fetch_precio_simbolo(_DB, "TZXD7") == (272.85, "ARS")


def test_fetch_precio_simbolo_sin_precio_valido(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: {"ultimoPrecio": 0})
    assert iol.fetch_precio_simbolo(_DB, "TZXD7") is None


def test_fetch_historico_ordena_y_filtra(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"fechaHora": "2026-06-03T14:00:00Z", "ultimoPrecio": 272.0},
        {"fechaHora": "2026-06-02T14:00:00Z", "ultimoPrecio": 270.0},
        {"fechaHora": None, "ultimoPrecio": 999.0},
        {"fechaHora": "2026-06-04T14:00:00Z", "ultimoPrecio": 0},
    ])
    out = iol.fetch_historico(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5))
    assert out == [(date(2026, 6, 2), 270.0), (date(2026, 6, 3), 272.0)]


def test_fetch_historico_caida_devuelve_none(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: None)
    assert iol.fetch_historico(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5)) is None
