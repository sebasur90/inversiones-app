"""Tests de ohlcv_analytics: resolución de la serie de barras (serie_ohlcv + precios_instrumento)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, BarraOHLCV, InstrumentoInversion, PrecioInstrumento, WatchlistItem
from app.services import ohlcv_analytics as oa


def _instrumento(db, ticker="AL30", moneda="USD"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=f"Bono {ticker}", tipo_instrumento="Bono",
                                 mercado="MERVAL", moneda=moneda))
    db.commit()


def _watchlist(db, ticker="GGAL", moneda="ARS"):
    db.add(WatchlistItem(ticker=ticker, nombre=f"Accion {ticker}", tipo_instrumento="Accion",
                          mercado="BCBA", moneda=moneda))
    db.commit()


def _vela(db, ticker, fecha, cierre, o=None, h=None, l=None, v=None, moneda="ARS", fuente="iol"):
    db.add(BarraOHLCV(ticker=ticker, fecha=fecha, apertura=o, maximo=h, minimo=l, cierre=cierre,
                       volumen=v, moneda=moneda, fuente=fuente))
    db.commit()


def _precio(db, ticker, fecha, precio, moneda="ARS", fuente="sheet"):
    db.add(PrecioInstrumento(ticker=ticker, fecha=fecha, precio=precio, moneda=moneda, fuente=fuente))
    db.commit()


BASE = date(2024, 1, 1)


def test_serie_solo_ohlcv_es_velas():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    for i in range(5):
        _vela(db, "AL30", BASE + timedelta(days=i), 100 + i, o=99 + i, h=101 + i, l=98 + i, v=1000)

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=10), db)
    assert r["fuente_serie"] == "velas"
    assert r["tiene_velas"] is True
    assert r["tiene_volumen"] is True
    assert len(r["barras"]) == 5
    assert r["origen"] == "cartera"
    assert r["advertencias"] == []


def test_serie_solo_cierres_es_mixta_y_sin_velas():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    for i in range(5):
        _precio(db, "AL30", BASE + timedelta(days=i), 100 + i)

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=10), db)
    assert r["fuente_serie"] == "mixta"
    assert r["tiene_velas"] is False
    assert r["tiene_volumen"] is False
    assert len(r["barras"]) == 5
    for b in r["barras"]:
        assert b.apertura is None and b.maximo is None and b.minimo is None


def test_serie_mixta_ohlcv_pisa_a_precio_en_la_misma_fecha():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    for i in range(20):
        _precio(db, "AL30", BASE + timedelta(days=i), 100 + i)
    # Sólo 2 de los 20 días tienen vela real -> por debajo del 90%, tiene_velas=False.
    _vela(db, "AL30", BASE + timedelta(days=0), 111, o=110, h=112, l=109, v=500)
    _vela(db, "AL30", BASE + timedelta(days=1), 112, o=111, h=113, l=110, v=500)

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=30), db)
    assert r["fuente_serie"] == "mixta"
    assert r["tiene_velas"] is False
    # La barra del día 0 viene de serie_ohlcv (cierre 111), no de precios_instrumento (100).
    assert r["barras"][0].cierre == pytest.approx(111.0)
    assert r["barras"][0].apertura == pytest.approx(110.0)


def test_watchlist_con_un_solo_punto_no_se_sirve():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _watchlist(db)
    _precio(db, "GGAL", BASE, 500)  # un solo día -> no es serie

    r = oa.get_serie_barras("GGAL", BASE, BASE + timedelta(days=5), db)
    assert r["barras"] == []
    assert r["advertencias"] == ["un_solo_punto"]
    assert r["fuente_serie"] == "sin_datos"


def test_ticker_sin_ningun_dato():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=5), db)
    assert r["barras"] == []
    assert r["advertencias"] == ["sin_serie"]


def test_warmup_barras_previas_agrega_filas_antes_de_desde():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    for i in range(20):
        _precio(db, "AL30", BASE + timedelta(days=i), 100 + i)

    desde = BASE + timedelta(days=10)
    r = oa.get_serie_barras("AL30", desde, BASE + timedelta(days=19), db, barras_previas=5)
    assert len(r["barras"]) == 15  # 5 de warmup + 10 (índices 10..19)
    assert r["indice_desde"] == 5
    assert r["barras"][r["indice_desde"]].fecha == desde


def test_serie_con_huecos_genera_advertencia():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    _precio(db, "AL30", BASE, 100)
    _precio(db, "AL30", BASE + timedelta(days=1), 101)
    _precio(db, "AL30", BASE + timedelta(days=60), 150)  # hueco enorme

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=90), db)
    assert "serie_con_huecos" in r["advertencias"]


def test_moneda_mixta_genera_advertencia():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    _precio(db, "AL30", BASE, 100, moneda="USD")
    _precio(db, "AL30", BASE + timedelta(days=1), 101, moneda="ARS")

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=5), db)
    assert "moneda_mixta" in r["advertencias"]


def test_origen_ambos_cuando_esta_en_cartera_y_watchlist():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db, ticker="AL30")
    _watchlist(db, ticker="AL30")
    _precio(db, "AL30", BASE, 100)
    _precio(db, "AL30", BASE + timedelta(days=1), 101)

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=5), db)
    assert r["origen"] == "ambos"


def test_max_barras_recorta_desde_el_principio_y_ajusta_indice_desde():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db)
    for i in range(30):
        _precio(db, "AL30", BASE + timedelta(days=i), 100 + i)

    r = oa.get_serie_barras("AL30", BASE, BASE + timedelta(days=29), db, barras_previas=0, max_barras=10)
    assert len(r["barras"]) == 10
    assert r["barras"][0].fecha == BASE + timedelta(days=20)


def test_listar_tickers_tecnicos_union_cartera_y_watchlist():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    _instrumento(db, ticker="AL30")
    _watchlist(db, ticker="GGAL")
    _instrumento(db, ticker="COMUN")
    _watchlist(db, ticker="COMUN")

    tickers = {t["ticker"]: t for t in oa.listar_tickers_tecnicos(db)}
    assert set(tickers) == {"AL30", "GGAL", "COMUN"}
    assert tickers["AL30"]["origen"] == "cartera"
    assert tickers["GGAL"]["origen"] == "watchlist"
    assert tickers["COMUN"]["origen"] == "ambos"
