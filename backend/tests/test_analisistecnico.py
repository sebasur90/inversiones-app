"""Tests del cliente `market_data.analisistecnico` — sin red: mockea `get_json`."""
from datetime import date, datetime, timezone

from backend.app.services.market_data import analisistecnico


def _ts(y, m, d, hora=13):
    """Epoch de una barra diaria con timestamp intradiario (hora de sesión, en UTC)."""
    return int(datetime(y, m, d, hora, tzinfo=timezone.utc).timestamp())


def _resp(t, c, s="ok"):
    return {"s": s, "t": t, "o": c, "h": c, "l": c, "c": c, "v": [0] * len(t)}


def test_fetch_historico_bono_mapea_timestamps_a_fechas(monkeypatch):
    monkeypatch.setattr(analisistecnico, "get_json",
                        lambda url: _resp([_ts(2026, 1, 8), _ts(2026, 1, 9)], [272.25, 272.5]))
    out = analisistecnico.fetch_historico_bono("TZXD7", date(2026, 1, 1), date(2026, 1, 31))
    assert out == [(date(2026, 1, 8), 272.25), (date(2026, 1, 9), 272.5)]


def test_fetch_historico_bono_ordena_por_fecha_y_descarta_no_positivos(monkeypatch):
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: _resp(
        [_ts(2026, 1, 9), _ts(2026, 1, 8), _ts(2026, 1, 10)], [272.5, 272.25, 0.0]))
    out = analisistecnico.fetch_historico_bono("TZXD7", date(2026, 1, 1), date(2026, 1, 31))
    assert out == [(date(2026, 1, 8), 272.25), (date(2026, 1, 9), 272.5)]


def test_fetch_historico_bono_pasa_el_rango_en_epoch(monkeypatch):
    capturado = {}

    def _fake(url):
        capturado["url"] = url
        return _resp([_ts(2025, 6, 1)], [1.0])

    monkeypatch.setattr(analisistecnico, "get_json", _fake)
    analisistecnico.fetch_historico_bono("AL30", date(2025, 1, 1), date(2026, 1, 1))
    assert "symbol=AL30" in capturado["url"] and "resolution=D" in capturado["url"]
    desde = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
    hasta = int(datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    assert f"from={desde}" in capturado["url"]
    assert f"to={hasta}" in capturado["url"]


def test_ticker_desconocido_es_none(monkeypatch):
    """analisistecnico responde {"s": "error"} para símbolos que no tiene (p.ej. ONs)."""
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: {"s": "error"})
    assert analisistecnico.fetch_historico_bono("MGCJO", date(2025, 1, 1), date(2026, 1, 1)) is None


def test_no_data_es_lista_vacia(monkeypatch):
    """Símbolo válido sin ruedas en el rango: [] (no None) — la fuente respondió."""
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: {"s": "no_data"})
    assert analisistecnico.fetch_historico_bono("AL30", date(2001, 1, 1), date(2001, 2, 1)) == []


def test_red_caida_es_none(monkeypatch):
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: None)
    assert analisistecnico.fetch_historico_bono("AL30", date(2025, 1, 1), date(2026, 1, 1)) is None


def test_ok_sin_cierres_usables_es_lista_vacia(monkeypatch):
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: _resp([], []))
    assert analisistecnico.fetch_historico_bono("AL30", date(2025, 1, 1), date(2026, 1, 1)) == []
