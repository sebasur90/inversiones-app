"""Tests de las fuentes de OHLCV (fetch_historico_ohlcv de analisistecnico e iol) y de que los
wrappers de compatibilidad (`fetch_historico_bono`, `fetch_historico`) no regresionan."""
from datetime import date, datetime, timezone

from backend.app.services.market_data import analisistecnico, iol

_DB = object()


def _ts(y, m, d, hora=13):
    return int(datetime(y, m, d, hora, tzinfo=timezone.utc).timestamp())


# ── analisistecnico.fetch_historico_ohlcv ────────────────────────────────────

def test_analisistecnico_parsea_ohlcv_completo(monkeypatch):
    resp = {
        "s": "ok", "t": [_ts(2026, 1, 8)],
        "o": [100.0], "h": [105.0], "l": [98.0], "c": [102.0], "v": [5000.0],
    }
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: resp)
    out = analisistecnico.fetch_historico_ohlcv("AL30", date(2026, 1, 1), date(2026, 1, 31))
    assert out == [analisistecnico.BarraCruda(
        fecha=date(2026, 1, 8), cierre=102.0, apertura=100.0, maximo=105.0, minimo=98.0, volumen=5000.0,
    )]


def test_analisistecnico_error_es_none(monkeypatch):
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: {"s": "error"})
    assert analisistecnico.fetch_historico_ohlcv("MGCJO", date(2025, 1, 1), date(2026, 1, 1)) is None


def test_analisistecnico_barra_incoherente_anula_ohl(monkeypatch):
    # mínimo (98) no cubre el menor de apertura/cierre (100), la barra es inconsistente.
    resp = {
        "s": "ok", "t": [999999], "o": [100.0], "h": [101.0], "l": [98.0], "c": [50.0], "v": [10.0],
    }
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: resp)
    out = analisistecnico.fetch_historico_ohlcv("AL30", date(2020, 1, 1), date(2020, 1, 2))
    assert len(out) == 1
    assert out[0].cierre == 50.0
    assert out[0].apertura is None and out[0].maximo is None and out[0].minimo is None


def test_analisistecnico_fetch_historico_bono_wrapper_no_regresiona(monkeypatch):
    resp = {"s": "ok", "t": [_ts(2026, 1, 8), _ts(2026, 1, 9)], "o": [1, 1], "h": [1, 1], "l": [1, 1],
            "c": [272.25, 272.5], "v": [0, 0]}
    monkeypatch.setattr(analisistecnico, "get_json", lambda url: resp)
    out = analisistecnico.fetch_historico_bono("TZXD7", date(2026, 1, 1), date(2026, 1, 31))
    assert out == [(date(2026, 1, 8), 272.25), (date(2026, 1, 9), 272.5)]


# ── iol.fetch_historico_ohlcv ─────────────────────────────────────────────────

def test_iol_parsea_con_alias_estandar(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"fechaHora": "2026-06-02T14:00:00Z", "ultimoPrecio": 270.0,
         "apertura": 268.0, "maximo": 271.0, "minimo": 267.0, "volumenNominal": 1000.0},
    ])
    out = iol.fetch_historico_ohlcv(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5))
    assert out == [iol.BarraCruda(
        fecha=date(2026, 6, 2), cierre=270.0, apertura=268.0, maximo=271.0, minimo=267.0, volumen=1000.0,
    )]


def test_iol_parsea_con_alias_alternativos(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"fechaHora": "2026-06-02T14:00:00Z", "ultimoPrecio": 270.0,
         "precioApertura": 268.0, "high": 271.0, "low": 267.0, "cantidadOperada": 500.0},
    ])
    out = iol.fetch_historico_ohlcv(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5))
    assert out == [iol.BarraCruda(
        fecha=date(2026, 6, 2), cierre=270.0, apertura=268.0, maximo=271.0, minimo=267.0, volumen=500.0,
    )]


def test_iol_solo_ultimo_precio_es_close_only(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"fechaHora": "2026-06-02T14:00:00Z", "ultimoPrecio": 270.0},
    ])
    out = iol.fetch_historico_ohlcv(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5))
    assert out == [iol.BarraCruda(fecha=date(2026, 6, 2), cierre=270.0)]


def test_iol_montooperado_sin_volumen_nominal_no_cuenta_como_volumen(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"fechaHora": "2026-06-02T14:00:00Z", "ultimoPrecio": 270.0, "montoOperado": 999999.0},
    ])
    out = iol.fetch_historico_ohlcv(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5))
    assert out[0].volumen is None


def test_iol_caida_devuelve_none(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: None)
    assert iol.fetch_historico_ohlcv(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5)) is None


def test_iol_fetch_historico_wrapper_no_regresiona(monkeypatch):
    monkeypatch.setattr(iol.iol_auth, "get_autenticado", lambda db, url: [
        {"fechaHora": "2026-06-03T14:00:00Z", "ultimoPrecio": 272.0},
        {"fechaHora": "2026-06-02T14:00:00Z", "ultimoPrecio": 270.0},
    ])
    out = iol.fetch_historico(_DB, "TZXD7", date(2026, 6, 1), date(2026, 6, 5))
    assert out == [(date(2026, 6, 2), 270.0), (date(2026, 6, 3), 272.0)]
