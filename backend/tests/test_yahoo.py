"""Tests del cliente `market_data.yahoo` — sin red: inyecta un `yfinance` falso en sys.modules."""
import sys
from datetime import date

import pandas as pd
import pytest

from backend.app.services.market_data import yahoo

pytestmark = pytest.mark.usa_yahoo_real


def _df(filas):
    """`filas`: list de (yyyy-mm-dd, o, h, l, c, v). Devuelve un DataFrame con la misma forma
    que `yfinance.Ticker.history(auto_adjust=True, actions=False)`."""
    idx = pd.DatetimeIndex([pd.Timestamp(f, tz="America/New_York") for f, *_ in filas])
    return pd.DataFrame(
        {
            "Open": [o for _, o, *_ in filas],
            "High": [h for _, _, h, *_ in filas],
            "Low": [l for _, _, _, l, *_ in filas],
            "Close": [c for _, _, _, _, c, _ in filas],
            "Volume": [v for *_, v in filas],
        },
        index=idx,
    )


class _FakeTicker:
    def __init__(self, hist=None, hist_exc=None, fast_info=None, info=None, info_exc=None):
        self._hist, self._hist_exc = hist, hist_exc
        self._fast_info, self._info, self._info_exc = fast_info or {}, info, info_exc

    def history(self, **kwargs):
        if self._hist_exc is not None:
            raise self._hist_exc
        return self._hist

    @property
    def fast_info(self):
        return self._fast_info

    def get_info(self):
        if self._info_exc is not None:
            raise self._info_exc
        return self._info


def _instalar_yf(monkeypatch, ticker_obj):
    fake = type("FakeYF", (), {"Ticker": staticmethod(lambda _sym: ticker_obj)})
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_dataframe_a_lista_de_barras(monkeypatch):
    df = _df([
        ("2026-09-03", 501.0, 515.0, 500.0, 510.0, 24_000_000),
        ("2026-09-04", 510.0, 511.0, 498.0, 499.7, 18_000_000),
    ])
    _instalar_yf(monkeypatch, _FakeTicker(hist=df))
    out = yahoo.fetch_historico_ohlcv("MSFT", date(2026, 9, 1), date(2026, 9, 5))
    assert [b.fecha for b in out] == [date(2026, 9, 3), date(2026, 9, 4)]
    assert out[-1].cierre == 499.7
    assert out[-1].apertura == 510.0 and out[-1].maximo == 511.0 and out[-1].minimo == 498.0
    assert out[-1].volumen == 18_000_000


def test_ohlc_inconsistente_degrada_a_close_only(monkeypatch):
    # máximo (505) por debajo del cierre (510): o/h/l se anulan, el cierre se conserva.
    df = _df([("2026-09-04", 500.0, 505.0, 499.0, 510.0, 1_000)])
    _instalar_yf(monkeypatch, _FakeTicker(hist=df))
    out = yahoo.fetch_historico_ohlcv("MSFT", date(2026, 9, 1), date(2026, 9, 5))
    assert len(out) == 1
    assert out[0].cierre == 510.0
    assert out[0].apertura is None and out[0].maximo is None and out[0].minimo is None


def test_dataframe_vacio_con_ruedas_es_none(monkeypatch):
    """Vacío sobre un rango que sí tenía ruedas = yfinance se comió un error de red -> None."""
    _instalar_yf(monkeypatch, _FakeTicker(hist=pd.DataFrame()))
    assert yahoo.fetch_historico_ohlcv("MSFT", date(2026, 8, 1), date(2026, 9, 5)) is None


def test_dataframe_vacio_sin_ruedas_es_lista_vacia(monkeypatch):
    """Rango de un sábado a un domingo: no hay ruedas posibles -> [] (no None)."""
    _instalar_yf(monkeypatch, _FakeTicker(hist=pd.DataFrame()))
    assert yahoo.fetch_historico_ohlcv("MSFT", date(2026, 9, 5), date(2026, 9, 6)) == []


def test_excepcion_de_red_es_none(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(hist_exc=RuntimeError("connection reset")))
    assert yahoo.fetch_historico_ohlcv("MSFT", date(2026, 1, 1), date(2026, 2, 1)) is None


def test_cierre_nan_o_no_positivo_se_descarta(monkeypatch):
    df = _df([
        ("2026-09-02", 1.0, 1.0, 1.0, float("nan"), 0),
        ("2026-09-03", 1.0, 1.0, 1.0, 0.0, 0),
        ("2026-09-04", 500.0, 501.0, 499.0, 499.7, 10),
    ])
    _instalar_yf(monkeypatch, _FakeTicker(hist=df))
    out = yahoo.fetch_historico_ohlcv("MSFT", date(2026, 9, 1), date(2026, 9, 5))
    assert [b.fecha for b in out] == [date(2026, 9, 4)]


def test_fetch_info_moneda_usd(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(
        fast_info={"currency": "usd", "exchange": "NMS"},
        info={"longName": "Microsoft Corporation"},
    ))
    info = yahoo.fetch_info("MSFT")
    assert info == {"moneda": "USD", "mercado": "NMS", "nombre": "Microsoft Corporation"}


def test_fetch_info_moneda_no_usd(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(
        fast_info={"currency": "ARS", "exchange": "BUE"},
        info={"shortName": "Grupo Galicia"},
    ))
    info = yahoo.fetch_info("GGAL.BA")
    assert info["moneda"] == "ARS"
    assert info["nombre"] == "Grupo Galicia"


def test_fetch_info_sin_fast_info_es_none(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(fast_info={}))
    assert yahoo.fetch_info("NOEXISTE") is None


def test_fetch_info_nombre_degrada_a_none_si_info_falla(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(
        fast_info={"currency": "USD", "exchange": "NYQ"},
        info_exc=RuntimeError("429 Too Many Requests"),
    ))
    info = yahoo.fetch_info("AAPL")
    assert info["moneda"] == "USD" and info["mercado"] == "NYQ" and info["nombre"] is None


# ── fetch_ultimo_precio: el precio intradía del subyacente ───────────────────

def test_ultimo_precio_desde_fast_info(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(fast_info={"last_price": 173.45, "currency": "usd"}))
    assert yahoo.fetch_ultimo_precio("MSFT") == {"precio": 173.45, "moneda": "USD"}


def test_ultimo_precio_acepta_el_atributo_en_vez_de_la_clave(monkeypatch):
    """`fast_info` no es un dict común y yfinance cambió la grafía entre versiones: se prueban las
    dos antes de dar el precio por perdido."""
    class _FastInfo(dict):
        last_price = 99.5

    fi = _FastInfo(currency="USD")
    _instalar_yf(monkeypatch, _FakeTicker(fast_info=fi))
    assert yahoo.fetch_ultimo_precio("MSFT") == {"precio": 99.5, "moneda": "USD"}


def test_ultimo_precio_sin_dato_es_none(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(fast_info={"currency": "USD"}))
    assert yahoo.fetch_ultimo_precio("MSFT") is None


def test_ultimo_precio_no_positivo_es_none(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(fast_info={"last_price": 0, "currency": "USD"}))
    assert yahoo.fetch_ultimo_precio("MSFT") is None


def test_ultimo_precio_informa_la_moneda_que_vino(monkeypatch):
    """La moneda viaja y no se asume: quien la consume exige USD, porque comparar una zona en
    dólares contra un precio en otra moneda es un aviso falso."""
    _instalar_yf(monkeypatch, _FakeTicker(fast_info={"last_price": 10.0, "currency": "EUR"}))
    assert yahoo.fetch_ultimo_precio("ASML.AS") == {"precio": 10.0, "moneda": "EUR"}


def test_ultimo_precio_no_lanza_si_falla_la_red(monkeypatch):
    class _Explota:
        @property
        def fast_info(self):
            raise RuntimeError("sin red")

    _instalar_yf(monkeypatch, _Explota())
    assert yahoo.fetch_ultimo_precio("MSFT") is None


# ── fundamentales ─────────────────────────────────────────────────────────

class _RateLimitError(Exception):
    pass


_RateLimitError.__name__ = "YFRateLimitError"


def test_fundamentales_filtra_lista_blanca_y_descarta_nan(monkeypatch):
    info = {
        "quoteType": "EQUITY", "longName": "The Coca-Cola Company", "sector": "Consumer Defensive",
        "trailingPE": 25.3, "forwardPE": float("nan"), "marketCap": 3.0e11,
        "longBusinessSummary": "texto largo que no se guarda", "address1": "Atlanta",
        "industry": "  ",
    }
    _instalar_yf(monkeypatch, _FakeTicker(info=info))
    r = yahoo.fetch_fundamentales("KO")
    assert r.estado == yahoo.ESTADO_OK
    assert r.datos["trailingPE"] == 25.3
    assert r.datos["marketCap"] == 3.0e11
    assert "forwardPE" not in r.datos
    assert "industry" not in r.datos
    assert "longBusinessSummary" not in r.datos and "address1" not in r.datos


def test_fundamentales_dict_casi_vacio_es_no_encontrado(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(info={"trailingPegRatio": None}))
    assert yahoo.fetch_fundamentales("XXXX").estado == yahoo.ESTADO_NO_ENCONTRADO


def test_fundamentales_rate_limit_se_distingue(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(info_exc=_RateLimitError("Too Many Requests. Rate limited.")))
    r = yahoo.fetch_fundamentales("KO")
    assert r.estado == yahoo.ESTADO_RATE_LIMITED


def test_fundamentales_404_es_no_encontrado(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(info_exc=RuntimeError("HTTP Error 404: Not Found")))
    assert yahoo.fetch_fundamentales("ZZZZ").estado == yahoo.ESTADO_NO_ENCONTRADO


def test_fundamentales_error_de_red_no_lanza(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(info_exc=ConnectionError("proxy caído")))
    r = yahoo.fetch_fundamentales("KO")
    assert r.estado == yahoo.ESTADO_ERROR
    assert "proxy" in r.error


def test_cierres_semanales(monkeypatch):
    df = _df([
        ("2026-09-07", 60.0, 61.0, 59.0, 60.5, 1_000),
        ("2026-09-14", 60.5, 62.0, 60.0, float("nan"), 1_000),
        ("2026-09-21", 61.0, 63.0, 60.0, 62.0, 1_000),
    ])
    _instalar_yf(monkeypatch, _FakeTicker(hist=df))
    r = yahoo.fetch_cierres_semanales("KO")
    assert r.estado == yahoo.ESTADO_OK
    assert r.datos == [{"fecha": "2026-09-07", "cierre": 60.5}, {"fecha": "2026-09-21", "cierre": 62.0}]


def test_cierres_semanales_vacio_es_error(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(hist=pd.DataFrame()))
    assert yahoo.fetch_cierres_semanales("KO").estado == yahoo.ESTADO_ERROR


def test_cierres_semanales_rate_limit(monkeypatch):
    _instalar_yf(monkeypatch, _FakeTicker(hist_exc=_RateLimitError("429")))
    assert yahoo.fetch_cierres_semanales("KO").estado == yahoo.ESTADO_RATE_LIMITED
