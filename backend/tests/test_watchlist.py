"""Watchlist: precios automáticos sin calibración, sync desacoplado del Sheet y zona de compra.

El CRUD (alta desde el catálogo, edición, baja) está en `test_watchlist_crud.py`.
"""
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
from backend.app.services.watchlist_analytics import get_watchlist


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _item(db, ticker="AAPL", objetivo=4900.0, tipo="CEDEAR"):
    db.add(WatchlistItem(ticker=ticker, nombre="Aple", tipo_instrumento=tipo,
                         mercado="BCBA", moneda="ARS", pais="argentina",
                         objetivo=objetivo, agregado_en=date.today()))
    db.commit()


# ── Sync: la watchlist ya no sale del Sheet ───────────────────────────────────

def _raw():
    """El Sheet sin pestaña `Watchlist`: ya no se lee, ni siquiera se pide."""
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
    }


def _sync(monkeypatch, db):
    import backend.app.services.inversiones_sync as sync_module
    monkeypatch.setattr(sync_module, "fetch_sheet_data", lambda: _raw())
    return sync_from_sheet(db)


def test_sync_no_borra_lo_que_cargo_el_usuario(monkeypatch):
    """El DELETE+INSERT de la pestaña desapareció: el sync no puede tocar la lista."""
    db = _db()
    _item(db, "AAPL")
    _sync(monkeypatch, db)
    assert [w.ticker for w in db.query(WatchlistItem).all()] == ["AAPL"]


def test_sync_no_reporta_issues_de_la_pestana_watchlist(monkeypatch):
    """La pestaña dejó de existir para el sync: no puede faltar ni bloquearse."""
    db = _db()
    result = _sync(monkeypatch, db)
    assert not [i for i in result["issues"] if i["tab"] == "Watchlist"]


def test_sync_purga_precios_de_tickers_que_ya_no_se_siguen(monkeypatch):
    db = _db()
    _item(db, "AAPL")
    db.add(PrecioWatchlist(ticker="VIEJO", fecha=date(2024, 1, 1), precio=120,
                           moneda="ARS", fuente="api"))
    db.commit()
    _sync(monkeypatch, db)
    assert [p.ticker for p in db.query(PrecioWatchlist).all()] != ["VIEJO"]


# ── Precios automáticos: sin calibración de escala ────────────────────────────

def _watchlist_dicts(objetivo=4900.0, ticker="AAPL", tipo="CEDEAR"):
    return [{"ticker": ticker, "nombre": "Aple", "tipo_instrumento": tipo, "mercado": "BCBA",
             "moneda": "ARS", "pais": "argentina", "sector": None, "objetivo": objetivo}]


def _sin_iol(monkeypatch):
    """IOL fuera de juego: se ejercita la rama data912, sin tocar la red ni el cupo."""
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", lambda db: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)


def test_precios_watchlist_toma_el_precio_de_los_paneles_de_iol(monkeypatch):
    """El camino barato: el símbolo está en la tanda de paneles que el sync ya pidió."""
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles",
                        lambda db: {"AAPL": (5300.0, "ARS")})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)
    hoy = date(2026, 9, 3)
    filas, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(), db=None, hoy=hoy)

    assert filas == [{"fecha": hoy, "ticker": "AAPL", "precio": 5300.0, "moneda": "ARS", "fuente": "iol"}]
    assert issues == []


def test_precios_watchlist_no_calibra_contra_el_objetivo(monkeypatch):
    """La regresión que motivó el cambio: un objetivo lejísimos del mercado ya no anula el precio.

    Antes, un objetivo a 1/10 del mercado dejaba el ratio fuera de las ventanas de `_factor_escala`
    y el instrumento quedaba sin precio (`escala_desconocida`). El símbolo ahora sale del catálogo
    de IOL, así que la cotización se toma tal cual y el objetivo no interviene.
    """
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles",
                        lambda db: {"AAPL": (49000.0, "ARS")})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)
    filas, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(objetivo=4900.0), db=None, hoy=date(2026, 9, 3))

    assert filas[0]["precio"] == 49000.0
    assert not [i for i in issues if i.regla == "escala_desconocida"]


def test_precios_watchlist_sin_objetivo_igual_se_cotiza(monkeypatch):
    """Agregar un instrumento y decidir el objetivo después es el flujo normal de la pantalla."""
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles",
                        lambda db: {"AAPL": (5300.0, "ARS")})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)
    filas, _ = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(objetivo=None), db=None, hoy=date(2026, 9, 3))

    assert filas[0]["precio"] == 5300.0


def test_precios_watchlist_cae_a_simbolo_suelto_si_los_paneles_no_lo_traen(monkeypatch):
    """Las ONs y las letras no siempre están en los paneles: 1 llamada por símbolo, con tope."""
    pedidos = []
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles",
                        lambda db: {"OTRO": (1.0, "ARS")})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)

    def _suelto(db, simbolo):
        pedidos.append(simbolo)
        return (98.5, "USD")

    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo", _suelto)
    filas, _ = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(ticker="MR36O", tipo="ON"), db=None, hoy=date(2026, 9, 3))

    assert pedidos == ["MR36O"]
    assert filas[0]["precio"] == 98.5
    assert filas[0]["moneda"] == "USD", "la moneda la manda la fuente, no el catálogo"


def test_precios_watchlist_respeta_el_tope_de_simbolos_sueltos(monkeypatch):
    """Lo que pasa el tope no se pide: se reintenta en la corrida siguiente."""
    pedidos = []
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", lambda db: {})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable", lambda: None)

    def _suelto(db, simbolo):
        pedidos.append(simbolo)
        return (10.0, "ARS")

    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo", _suelto)
    items = _watchlist_dicts(ticker="A") + _watchlist_dicts(ticker="B") + _watchlist_dicts(ticker="C")
    filas, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        items, db=None, hoy=date(2026, 9, 3), max_simbolos_sueltos=2)

    assert pedidos == ["A", "B"]
    assert len(filas) == 2
    assert [i.campo for i in issues if i.regla == "ticker_no_cotizado"] == ["C"]


def test_el_tope_de_simbolos_sueltos_rota_entre_corridas(monkeypatch):
    """El tope corta una lista ordenada por antigüedad del precio guardado, no el mismo prefijo
    alfabético siempre: si no, la cola de la watchlist nunca llegaría a pedirse a IOL."""
    db = _db()
    for ticker, dias in (("A", 0), ("B", 10), ("C", None)):
        db.add(WatchlistItem(ticker=ticker, nombre=ticker, tipo_instrumento="ON",
                             mercado="BCBA", moneda="ARS", agregado_en=date.today()))
        if dias is not None:
            db.add(PrecioWatchlist(ticker=ticker, fecha=date.today() - timedelta(days=dias),
                                   precio=100, moneda="ARS", fuente="iol"))
    db.commit()

    pedidos = []
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", lambda db_: {})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db_: None)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_fija", lambda: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo",
                        lambda db_, s: pedidos.append(s) or (10.0, "ARS"))

    items = [{"ticker": t, "tipo_instrumento": "ON", "moneda": "ARS"} for t in ("A", "B", "C")]
    market_data_precios.fetch_precios_watchlist_catalogo(
        items, db, hoy=date.today(), max_simbolos_sueltos=2)

    # C nunca se cotizó, B tiene el precio más viejo: van antes que A, que se cotizó hoy.
    assert pedidos == ["C", "B"]


def test_el_que_queda_fuera_del_tope_no_se_reporta_como_no_cotizado(monkeypatch):
    """Decir "IOL no lo cotiza" de un ticker al que no se le preguntó sería engañoso."""
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", lambda db: {})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable", lambda: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo",
                        lambda db, s: (10.0, "ARS"))

    items = _watchlist_dicts(ticker="A") + _watchlist_dicts(ticker="B")
    _, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        items, db=None, hoy=date(2026, 9, 3), max_simbolos_sueltos=1)

    fuera = [i for i in issues if i.campo == "B"]
    assert len(fuera) == 1
    assert "fuera del cupo" in fuera[0].mensaje
    assert "no lo cotiza" not in fuera[0].mensaje


def test_solo_simbolo_suelto_no_baja_los_paneles(monkeypatch):
    """El alta y el botón "Precio" cotizan uno solo: bajar los ~9 paneles costaría 9 llamadas."""
    def _boom(db):
        raise AssertionError("no debería pedir los paneles para un solo símbolo")

    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", _boom)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", _boom)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo",
                        lambda db, s: (5300.0, "ARS"))

    filas, _ = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(), db=None, hoy=date(2026, 9, 3), solo_simbolo_suelto=True)
    assert filas[0]["precio"] == 5300.0


def test_precios_watchlist_cae_a_data912_si_iol_no_responde(monkeypatch):
    """Respaldo público: no gasta cupo y tampoco calibra."""
    _sin_iol(monkeypatch)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable",
                        lambda: {"AAPL": 5300.0})
    filas, _ = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(), db=None, hoy=date(2026, 9, 3))

    assert filas[0]["precio"] == 5300.0
    assert filas[0]["fuente"] == "api"


def test_precios_watchlist_reporta_el_que_nadie_cotiza(monkeypatch):
    _sin_iol(monkeypatch)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable", lambda: {})
    filas, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        _watchlist_dicts(), db=None, hoy=date(2026, 9, 3))

    assert filas == []
    assert [i.regla for i in issues] == ["ticker_no_cotizado"]
    assert issues[0].tab == "Watchlist (API)"


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
