"""Tests del cliente `market_data.data912` — sin red: mockea `get_json`."""
from backend.app.services.market_data import data912


def test_fetch_precios_renta_fija_une_los_tres_endpoints(monkeypatch):
    respuestas = {
        "https://data912.com/live/arg_bonds": [
            {"symbol": "AL30", "c": 85160.0, "px_bid": 85100.0, "px_ask": 85200.0},
        ],
        "https://data912.com/live/arg_corp": [
            {"symbol": "AEC3O", "c": 0.0, "px_bid": 153000.0, "px_ask": 154600.0},  # sin `c`: usa punto medio
        ],
        "https://data912.com/live/arg_notes": [
            {"symbol": "S30S6", "c": 115.244},
            {"symbol": "ROTO", "c": None, "px_bid": None, "px_ask": None},  # se descarta
        ],
    }
    monkeypatch.setattr(data912, "get_json", lambda url: respuestas.get(url))

    out = data912.fetch_precios_renta_fija()
    assert out == {"AL30": 85160.0, "AEC3O": 153800.0, "S30S6": 115.244}
    assert "ROTO" not in out


def test_fetch_precios_renta_fija_todos_caidos_devuelve_none(monkeypatch):
    monkeypatch.setattr(data912, "get_json", lambda url: None)
    assert data912.fetch_precios_renta_fija() is None


def test_fetch_precios_renta_fija_endpoint_vacio_no_es_none(monkeypatch):
    """Si los endpoints responden pero sin filas, es {} (no None): la API está viva."""
    monkeypatch.setattr(data912, "get_json", lambda url: [])
    assert data912.fetch_precios_renta_fija() == {}


def test_fetch_precios_renta_variable_une_los_dos_endpoints(monkeypatch):
    respuestas = {
        "https://data912.com/live/arg_stocks": [
            {"symbol": "GGAL", "c": 5230.0, "px_bid": 5225.0, "px_ask": 5235.0},
        ],
        "https://data912.com/live/arg_cedears": [
            {"symbol": "KO", "c": 0.0, "px_bid": 8200.0, "px_ask": 8300.0},  # sin `c`: punto medio
            {"symbol": "ROTO", "c": None, "px_bid": None, "px_ask": None},  # se descarta
        ],
    }
    monkeypatch.setattr(data912, "get_json", lambda url: respuestas.get(url))

    out = data912.fetch_precios_renta_variable()
    assert out == {"GGAL": 5230.0, "KO": 8250.0}
    assert "ROTO" not in out


def test_fetch_precios_renta_variable_todos_caidos_devuelve_none(monkeypatch):
    monkeypatch.setattr(data912, "get_json", lambda url: None)
    assert data912.fetch_precios_renta_variable() is None


def test_fetch_precios_renta_variable_endpoint_vacio_no_es_none(monkeypatch):
    monkeypatch.setattr(data912, "get_json", lambda url: [])
    assert data912.fetch_precios_renta_variable() == {}
