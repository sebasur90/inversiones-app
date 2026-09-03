"""Watchlist: parser de la pestaña, precios automáticos y cálculo de zona de compra."""
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import (
    Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento, PrecioWatchlist,
    WatchlistItem,
)
from backend.app.services.inversiones_sync import sync_from_sheet
from backend.app.services.market_data import precios as market_data_precios
from backend.app.services.sheets_client import TabRaw
from backend.app.services.validation.reglas_watchlist import validar_watchlist
from backend.app.services.watchlist_analytics import get_watchlist

HEADER_WL = ["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda", "País", "Sector", "Objetivo"]


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _fila(ticker="AAPL", **extra):
    fila = {
        "Ticker": ticker, "Nombre": "Aple", "Tipo Instrumento": "CEDEAR", "Mercado": "Global",
        "Moneda": "ARS", "País": "AR", "Sector": "Tecnologia", "Objetivo": "4900",
    }
    fila.update(extra)
    return fila


# ── Parser ────────────────────────────────────────────────────────────────────

def test_validar_watchlist_fila_completa():
    validos, issues = validar_watchlist([(2, _fila())])
    assert issues == []
    assert validos == [{
        "ticker": "AAPL", "nombre": "Aple", "tipo_instrumento": "CEDEAR", "mercado": "Global",
        "moneda": "ARS", "pais": "AR", "sector": "Tecnologia", "objetivo": 4900.0,
    }]


def test_validar_watchlist_objetivo_desde_excel_y_notacion_ars():
    """Las pestañas opcionales se leen sin dtype=str: un 4900 del Excel llega como '4900.0'."""
    validos, issues = validar_watchlist([
        (2, _fila("AAPL", Objetivo="4900.0")),
        (3, _fila("AMZN", Objetivo="2.900,50")),
    ])
    assert issues == []
    assert [v["objetivo"] for v in validos] == [4900.0, 2900.5]


def test_validar_watchlist_objetivo_invalido_es_salvage():
    validos, issues = validar_watchlist([
        (2, _fila("AAPL", Objetivo="")),
        (3, _fila("AMZN", Objetivo="-10")),
    ])
    assert [i.regla for i in issues] == ["objetivo_watchlist_invalido"] * 2
    assert all(i.severidad.value == "advertencia" for i in issues)
    # La fila sobrevive, sin objetivo: se lista pero no genera alerta.
    assert [(v["ticker"], v["objetivo"]) for v in validos] == [("AAPL", None), ("AMZN", None)]


def test_validar_watchlist_moneda_invalida_cae_a_ars():
    validos, issues = validar_watchlist([(2, _fila(Moneda="EUR"))])
    assert [i.regla for i in issues] == ["moneda_invalida"]
    assert validos[0]["moneda"] == "ARS"


def test_validar_watchlist_ticker_vacio_o_duplicado_se_descarta():
    validos, issues = validar_watchlist([
        (2, _fila("")),
        (3, _fila("AAPL")),
        (4, _fila("AAPL")),
    ])
    assert [i.regla for i in issues] == ["ticker_vacio", "ticker_duplicado"]
    assert all(i.severidad.value == "critico" for i in issues)
    assert [v["ticker"] for v in validos] == ["AAPL"]


# ── Sync ──────────────────────────────────────────────────────────────────────

def _raw(watchlist_tab):
    return {
        "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[
            (2, {"Ticker": "AL30", "Nombre": "Bonar 30", "Tipo Instrumento": "Bono", "Mercado": "BYMA", "Moneda": "USD"}),
        ]),
        "Movimientos": TabRaw(presente=True, header=["Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Cantidad", "Precio", "Moneda"], rows=[
            (2, {"Fecha": "2024-01-01", "Cartera": "P1", "Ticker": "AL30", "Tipo Movimiento": "Compra", "Cantidad": "10", "Precio": "50", "Moneda": "USD"}),
        ]),
        "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
            (2, {"Fecha": "2024-01-01", "Ticker": "AL30", "Precio": "50", "Moneda": "USD"}),
        ]),
        "Objetivos": TabRaw(presente=False, header=[], rows=[]),
        "Rebalanceo": TabRaw(presente=False, header=[], rows=[]),
        "Benchmarks": TabRaw(presente=False, header=[], rows=[]),
        "Configuracion": TabRaw(presente=False, header=[], rows=[]),
        "Tipos de Cambio": TabRaw(presente=False, header=[], rows=[]),
        "Watchlist": watchlist_tab,
    }


def _sync_con(monkeypatch, db, watchlist_tab):
    import backend.app.services.inversiones_sync as sync_module
    monkeypatch.setattr(sync_module, "fetch_sheet_data", lambda: _raw(watchlist_tab))
    return sync_from_sheet(db)


def test_sync_persiste_watchlist(monkeypatch):
    db = _db()
    _sync_con(monkeypatch, db, TabRaw(presente=True, header=HEADER_WL, rows=[
        (2, _fila("AAPL")),
        (3, _fila("AMZN", Nombre="Amazon", Objetivo="2900")),
    ]))
    guardados = {w.ticker: float(w.objetivo) for w in db.query(WatchlistItem).all()}
    assert guardados == {"AAPL": 4900.0, "AMZN": 2900.0}


def test_sync_watchlist_ausente_no_rompe(monkeypatch):
    db = _db()
    result = _sync_con(monkeypatch, db, TabRaw(presente=False, header=[], rows=[]))
    assert db.query(WatchlistItem).count() == 0
    assert not [i for i in result["issues"] if i["tab"] == "Watchlist"]


def test_sync_watchlist_bloqueada_preserva_datos(monkeypatch):
    """Con error de lectura, la tabla conserva lo anterior (aislamiento por pestaña)."""
    db = _db()
    db.add(WatchlistItem(ticker="PREV", nombre="Previo", tipo_instrumento="CEDEAR",
                         mercado="Global", moneda="ARS", objetivo=100))
    db.add(PrecioWatchlist(ticker="PREV", fecha=date(2024, 1, 1), precio=120,
                           moneda="ARS", fuente="api"))
    db.commit()

    result = _sync_con(monkeypatch, db, TabRaw(presente=True, header=HEADER_WL, rows=[],
                                               error_lectura="boom"))
    assert [w.ticker for w in db.query(WatchlistItem).all()] == ["PREV"]
    assert db.query(PrecioWatchlist).count() == 1, "la purga no debe correr con la pestaña bloqueada"
    assert any(i["regla"] == "lectura_fallo" and i["tab"] == "Watchlist" for i in result["issues"])


def test_sync_purga_precios_de_tickers_que_salieron(monkeypatch):
    db = _db()
    db.add(PrecioWatchlist(ticker="VIEJO", fecha=date(2024, 1, 1), precio=120,
                           moneda="ARS", fuente="api"))
    db.commit()
    _sync_con(monkeypatch, db, TabRaw(presente=True, header=HEADER_WL, rows=[(2, _fila("AAPL"))]))
    assert db.query(PrecioWatchlist).count() == 0


# ── Precios automáticos ───────────────────────────────────────────────────────

def _watchlist_dicts(objetivo=4900.0, ticker="AAPL"):
    return [{"ticker": ticker, "nombre": "Aple", "tipo_instrumento": "CEDEAR", "mercado": "Global",
             "moneda": "ARS", "pais": "AR", "sector": "Tecnologia", "objetivo": objetivo}]


def _sin_iol(monkeypatch):
    """IOL fuera de juego: se ejercita la rama data912, sin tocar la red ni el cupo."""
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", lambda db: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)


def test_precios_watchlist_calibra_contra_el_objetivo(monkeypatch):
    """Sin precio manual en la pestaña Precios, la referencia de escala es el propio Objetivo."""
    _sin_iol(monkeypatch)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable",
                        lambda: {"AAPL": 5300.0})
    hoy = date(2026, 9, 3)
    filas, issues = market_data_precios.fetch_precios_watchlist(
        _watchlist_dicts(), [], db=None, hoy=hoy)

    assert filas == [{"fecha": hoy, "ticker": "AAPL", "precio": 5300.0, "moneda": "ARS", "fuente": "api"}]
    assert not [i for i in issues if i.severidad.value != "info"]


def test_precios_watchlist_prefiere_el_precio_manual_del_sheet(monkeypatch):
    """Un precio real observado gana sobre el Objetivo, que es una intención."""
    _sin_iol(monkeypatch)
    # data912 cotiza por lámina de 100: el precio manual del Sheet fija el factor 1/100.
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable",
                        lambda: {"AAPL": 530000.0})
    hoy = date(2026, 9, 3)
    precios_sheet = [{"ticker": "AAPL", "fecha": date(2026, 9, 1), "precio": 5100.0, "moneda": "ARS"}]
    filas, _ = market_data_precios.fetch_precios_watchlist(
        _watchlist_dicts(), precios_sheet, db=None, hoy=hoy)

    assert filas[0]["precio"] == 5300.0


def test_precios_watchlist_objetivo_muy_lejos_no_carga(monkeypatch):
    """Objetivo a 1/10 del mercado: el ratio no cae cerca de 1 ni de 100, no se adivina."""
    _sin_iol(monkeypatch)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable",
                        lambda: {"AAPL": 49000.0})
    filas, issues = market_data_precios.fetch_precios_watchlist(
        _watchlist_dicts(objetivo=4900.0), [], db=None, hoy=date(2026, 9, 3))

    assert filas == []
    escala = [i for i in issues if i.regla == "escala_desconocida"]
    assert len(escala) == 1
    assert escala[0].tab == "Watchlist (API)"
    assert "pestaña Precios" in escala[0].impacto


def test_precios_watchlist_sin_objetivo_no_se_cotiza(monkeypatch):
    """Sin objetivo no hay referencia de escala; se reporta, no se inventa un factor."""
    _sin_iol(monkeypatch)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable",
                        lambda: {"AAPL": 5300.0})
    filas, issues = market_data_precios.fetch_precios_watchlist(
        _watchlist_dicts(objetivo=None), [], db=None, hoy=date(2026, 9, 3))

    assert filas == []
    # `iol_no_disponible` también sale porque `_sin_iol` apaga IOL (legítimo, no es lo que se
    # está probando acá); lo que importa es que sin Objetivo no hay referencia de escala.
    assert "sin_precio_para_calibrar" in [i.regla for i in issues]


# ── Analytics ─────────────────────────────────────────────────────────────────

def _seed_watchlist(db, objetivo=4900.0, precio=None):
    db.add(WatchlistItem(ticker="AAPL", nombre="Aple", tipo_instrumento="CEDEAR",
                         mercado="Global", moneda="ARS", pais="AR", sector="Tecnologia",
                         objetivo=objetivo))
    if precio is not None:
        db.add(PrecioWatchlist(ticker="AAPL", fecha=date.today(), precio=precio,
                               moneda="ARS", fuente="api"))
    db.commit()


def test_get_watchlist_precio_por_encima_del_objetivo():
    db = _db()
    _seed_watchlist(db, objetivo=4900.0, precio=5300.0)
    fila = get_watchlist(db)[0]

    assert fila["precio_actual"] == 5300.0
    assert fila["precio_objetivo"] == 4900.0
    assert fila["en_zona"] is False
    # (4900 - 5300) / 5300: negativo mientras siga caro.
    assert fila["pct_a_objetivo"] == (4900.0 - 5300.0) / 5300.0
    assert fila["en_cartera"] is False
    assert fila["fuente_precio"] == "api"


def test_get_watchlist_en_zona_de_compra():
    db = _db()
    _seed_watchlist(db, objetivo=4900.0, precio=4850.0)
    fila = get_watchlist(db)[0]
    assert fila["en_zona"] is True
    assert fila["pct_a_objetivo"] > 0


def test_get_watchlist_sin_precio_ni_objetivo():
    db = _db()
    _seed_watchlist(db, objetivo=None, precio=None)
    fila = get_watchlist(db)[0]
    assert fila["precio_actual"] is None
    assert fila["precio_objetivo"] is None
    assert fila["pct_a_objetivo"] is None
    assert fila["en_zona"] is None


def test_get_watchlist_usa_la_serie_de_cartera_si_el_ticker_esta_en_instrumentos():
    """Un ticker que además se posee toma el precio de `precios_instrumento` (serie real)."""
    db = _db()
    _seed_watchlist(db, objetivo=4900.0, precio=1.0)  # precio de watchlist obsoleto
    db.add(InstrumentoInversion(ticker="AAPL", nombre="Aple", tipo_instrumento="CEDEAR",
                                mercado="Global", moneda="ARS"))
    db.add(PrecioInstrumento(fecha=date.today() - timedelta(days=1), ticker="AAPL",
                             precio=5300, moneda="ARS", fuente="iol"))
    db.add(MovimientoInversion(fecha=date.today() - timedelta(days=10), cartera="P1",
                               ticker="AAPL", tipo_movimiento="compra", cantidad=5,
                               precio=5000, moneda="ARS", comision=0))
    db.commit()

    fila = get_watchlist(db)[0]
    assert fila["precio_actual"] == 5300.0
    assert fila["fuente_precio"] == "cartera"
    assert fila["en_cartera"] is True


def test_get_watchlist_ordena_zona_primero_y_luego_cercania():
    db = _db()
    for ticker, objetivo, precio in (
        ("LEJOS", 100.0, 200.0),   # a 50 %
        ("CERCA", 100.0, 104.0),   # a ~3.8 %
        ("ZONA", 100.0, 95.0),     # ya en zona
        ("SINDATO", None, None),
    ):
        db.add(WatchlistItem(ticker=ticker, nombre=ticker, tipo_instrumento="CEDEAR",
                             mercado="Global", moneda="ARS", objetivo=objetivo))
        if precio is not None:
            db.add(PrecioWatchlist(ticker=ticker, fecha=date.today(), precio=precio,
                                   moneda="ARS", fuente="api"))
    db.commit()

    assert [f["ticker"] for f in get_watchlist(db)] == ["ZONA", "CERCA", "LEJOS", "SINDATO"]
