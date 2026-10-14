"""Tests del refresco liviano de precios.

Lo que importa verificar acá: que respete la precedencia `iol > sheet > api` igual que el sync, que
**no** escriba un `SyncRun` (el historial de calidad de datos es del sync, que sí mira el Sheet), y
que no haga backfill ni toque nada más.

La red está stubeada: `fetch_precios_api` se reemplaza por una función que devuelve filas fijas.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, BarraOHLCV, EstadoMarketDataTicker, InstrumentoInversion, PrecioInstrumento,
    RefrescoPrecios, SyncRun, WatchlistItem,
)
from app.services import refresco_precios
from app.services.market_data import precios as market_data_precios


HOY = date.today()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _con_apis(monkeypatch):
    """El refresco se corta solo si `USE_EXTERNAL_APIS` está apagado (lo apaga el conftest)."""
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    # Los memos piden paneles a IOL en cuanto se los invoca: se neutralizan.
    monkeypatch.setattr(market_data_precios, "memo_paneles", lambda db: (lambda: None))
    monkeypatch.setattr(market_data_precios, "memo_fci", lambda db: (lambda: None))


def _instrumento(db, ticker="AL30", tipo="Bono", moneda="USD"):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=f"Bono {ticker}", tipo_instrumento=tipo,
        mercado="MERVAL", moneda=moneda,
    ))
    db.commit()


def _stub_fetch(monkeypatch, filas, issues=None):
    """Reemplaza la traída de precios por filas fijas, y captura con qué la llamaron."""
    capturado = {}

    def falso(instrumentos, precios_sheet, claves_excluir, db, **kwargs):
        capturado["instrumentos"] = instrumentos
        capturado["precios_sheet"] = precios_sheet
        capturado["claves_excluir"] = claves_excluir
        return list(filas), list(issues or [])

    monkeypatch.setattr(market_data_precios, "fetch_precios_api", falso)
    return capturado


def _fila(ticker="AL30", precio=100.0, fuente="iol", fecha=None, moneda="USD"):
    return {"ticker": ticker, "fecha": fecha or HOY, "precio": precio, "moneda": moneda,
            "fuente": fuente}


# --- Lo básico ---------------------------------------------------------------------------------

def test_guarda_el_precio_del_dia(db, monkeypatch):
    _instrumento(db)
    _stub_fetch(monkeypatch, [_fila(precio=101.5)])

    resumen = refresco_precios.refrescar(db)

    assert resumen["resultado"] == "ok"
    assert resumen["precios_actualizados"] == 1
    fila = db.query(PrecioInstrumento).one()
    assert (fila.ticker, float(fila.precio), fila.fuente) == ("AL30", 101.5, "iol")


def test_no_escribe_sync_run(db, monkeypatch):
    """El historial de Calidad de datos es del sync completo: este job no lo ensucia."""
    _instrumento(db)
    _stub_fetch(monkeypatch, [_fila()])

    refresco_precios.refrescar(db)

    assert db.query(SyncRun).count() == 0


def test_registra_la_corrida_en_su_propia_tabla(db, monkeypatch):
    _instrumento(db)
    _stub_fetch(monkeypatch, [_fila()])

    refresco_precios.refrescar(db)

    fila = db.query(RefrescoPrecios).one()
    assert fila.id == 1
    assert fila.resultado == "ok"
    assert fila.precios_actualizados == 1
    assert fila.timestamp is not None

    # Segunda corrida: actualiza la misma fila, no agrega otra.
    refresco_precios.refrescar(db)
    assert db.query(RefrescoPrecios).count() == 1


def test_lee_los_instrumentos_de_la_db_no_del_sheet(db, monkeypatch):
    _instrumento(db, ticker="GGAL", tipo="Accion", moneda="ARS")
    capturado = _stub_fetch(monkeypatch, [])

    refresco_precios.refrescar(db)

    assert [i["ticker"] for i in capturado["instrumentos"]] == ["GGAL"]
    assert capturado["instrumentos"][0]["tipo_instrumento"] == "Accion"


def test_apis_apagadas_no_pide_nada(db, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    _instrumento(db)

    resumen = refresco_precios.refrescar(db)

    assert resumen["resultado"] == "sin_fuentes"
    assert db.query(PrecioInstrumento).count() == 0
    assert db.query(RefrescoPrecios).one().resultado == "sin_fuentes"


# --- Precedencia iol > sheet > api -------------------------------------------------------------

def test_iol_desplaza_el_precio_manual_del_mismo_dia(db, monkeypatch):
    """Misma regla que el sync: IOL es la fuente primaria y puede pisar al Sheet."""
    _instrumento(db)
    db.add(PrecioInstrumento(ticker="AL30", fecha=HOY, precio=90.0, moneda="USD", fuente="sheet"))
    db.commit()
    _stub_fetch(monkeypatch, [_fila(precio=105.0, fuente="iol")])

    refresco_precios.refrescar(db)

    filas = db.query(PrecioInstrumento).all()
    assert len(filas) == 1  # el UNIQUE es (fecha, ticker): no pueden convivir
    assert (float(filas[0].precio), filas[0].fuente) == (105.0, "iol")


def test_data912_no_pisa_un_precio_manual(db, monkeypatch):
    _instrumento(db)
    db.add(PrecioInstrumento(ticker="AL30", fecha=HOY, precio=90.0, moneda="USD", fuente="sheet"))
    db.commit()
    _stub_fetch(monkeypatch, [_fila(precio=105.0, fuente="api")])

    resumen = refresco_precios.refrescar(db)

    assert resumen["precios_actualizados"] == 0
    fila = db.query(PrecioInstrumento).one()
    assert (float(fila.precio), fila.fuente) == (90.0, "sheet")


def test_data912_si_entra_donde_no_hay_precio_manual(db, monkeypatch):
    _instrumento(db)
    _stub_fetch(monkeypatch, [_fila(precio=105.0, fuente="api")])

    refresco_precios.refrescar(db)

    fila = db.query(PrecioInstrumento).one()
    assert fila.fuente == "api"


def test_actualiza_en_vez_de_duplicar_una_fila_automatica(db, monkeypatch):
    _instrumento(db)
    db.add(PrecioInstrumento(ticker="AL30", fecha=HOY, precio=100.0, moneda="USD", fuente="iol"))
    db.commit()
    _stub_fetch(monkeypatch, [_fila(precio=103.0, fuente="iol")])

    refresco_precios.refrescar(db)

    fila = db.query(PrecioInstrumento).one()
    assert float(fila.precio) == 103.0


def test_el_precio_manual_se_pasa_para_calibrar_la_escala(db, monkeypatch):
    """`fetch_precios_api` necesita los precios del Sheet para resolver el factor de escala."""
    _instrumento(db)
    db.add(PrecioInstrumento(ticker="AL30", fecha=HOY - timedelta(days=1), precio=90.0,
                             moneda="USD", fuente="sheet"))
    db.commit()
    capturado = _stub_fetch(monkeypatch, [])

    refresco_precios.refrescar(db)

    assert [p["ticker"] for p in capturado["precios_sheet"]] == ["AL30"]
    # Igual que el sync: no se excluye ninguna clave, la precedencia se resuelve al escribir.
    assert capturado["claves_excluir"] == set()


# --- Espejo en serie_ohlcv ---------------------------------------------------------------------

def test_deja_espejo_close_only_en_la_serie(db, monkeypatch):
    """Para que el backfill del día siguiente promueva la fecha a vela real."""
    _instrumento(db)
    _stub_fetch(monkeypatch, [_fila(precio=101.0)])

    refresco_precios.refrescar(db)

    barra = db.query(BarraOHLCV).one()
    assert (barra.ticker, float(barra.cierre)) == ("AL30", 101.0)
    assert barra.apertura is None  # close-only


def test_no_degrada_una_vela_real_existente(db, monkeypatch):
    _instrumento(db)
    db.add(BarraOHLCV(ticker="AL30", fecha=HOY, apertura=99.0, maximo=102.0, minimo=98.0,
                      cierre=100.0, volumen=1000.0, moneda="USD", fuente="iol"))
    db.commit()
    _stub_fetch(monkeypatch, [_fila(precio=101.0, fuente="iol")])

    refresco_precios.refrescar(db)

    barra = db.query(BarraOHLCV).one()
    assert barra.apertura is not None  # la vela completa sobrevive
    assert float(barra.cierre) == 100.0


# --- Estado de market data --------------------------------------------------------------------

def test_persiste_el_estado_que_mutan_las_rutas_de_precios(db, monkeypatch):
    """El factor de escala calibrado tiene que sobrevivir a la corrida, como en el sync."""
    _instrumento(db)

    def falso(instrumentos, precios_sheet, claves_excluir, db_, **kwargs):
        kwargs["estado_por_ticker"]["AL30"] = {"factor_escala": 100.0, "factor_fecha": HOY}
        return [], []

    monkeypatch.setattr(market_data_precios, "fetch_precios_api", falso)

    refresco_precios.refrescar(db)

    fila = db.query(EstadoMarketDataTicker).one()
    assert float(fila.factor_escala) == 100.0


# --- Watchlist ---------------------------------------------------------------------------------

def test_recotiza_la_watchlist(db, monkeypatch):
    _instrumento(db)
    db.add(WatchlistItem(ticker="MSFT", nombre="Microsoft", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS"))
    db.commit()
    _stub_fetch(monkeypatch, [])

    llamado = {}

    def falso_wl(db_, tickers=None, **kwargs):
        llamado["tickers"] = tickers
        return 1, []

    monkeypatch.setattr(
        refresco_precios.watchlist_analytics, "refrescar_precios", falso_wl,
    )

    resumen = refresco_precios.refrescar(db)

    assert llamado["tickers"] == ["MSFT"]
    assert resumen["precios_watchlist"] == 1


def test_no_recotiza_un_ticker_que_ya_esta_en_cartera(db, monkeypatch):
    """Para los de cartera, `get_watchlist` lee la serie de `precios_instrumento`."""
    _instrumento(db, ticker="GGAL", tipo="Accion", moneda="ARS")
    db.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion",
                         mercado="BCBA", moneda="ARS"))
    db.commit()
    _stub_fetch(monkeypatch, [])

    llamado = {"veces": 0}

    def falso_wl(db_, tickers=None, **kwargs):
        llamado["veces"] += 1
        return 0, []

    monkeypatch.setattr(refresco_precios.watchlist_analytics, "refrescar_precios", falso_wl)

    refresco_precios.refrescar(db)

    assert llamado["veces"] == 0  # no quedó ninguno por cotizar


# --- Lectura para la UI ------------------------------------------------------------------------

def test_ultimo_sin_corridas(db):
    assert refresco_precios.ultimo(db) is None


def test_ultimo_despues_de_una_corrida(db, monkeypatch):
    _instrumento(db)
    _stub_fetch(monkeypatch, [_fila()])

    refresco_precios.refrescar(db)
    ultimo = refresco_precios.ultimo(db)

    assert ultimo is not None
    assert ultimo["precios_actualizados"] == 1
    assert ultimo["resultado"] == "ok"


# ── Precio intradía del subyacente en USD ────────────────────────────────────
#
# Para qué: la serie `TICKER@SUB` sólo se refresca en el sync de la tarde, así que una zona de
# precio medida en dólares y cruzada a media rueda avisaría a la noche. Este job la pone al día.

def _con_zona_subyacente(db, ticker="MSFT", simbolo="MSFT"):
    from datetime import datetime

    from app.database import ZonaPrecio

    db.add(WatchlistItem(ticker=ticker, nombre="Microsoft", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", agregado_en=HOY))
    db.add(EstadoMarketDataTicker(
        ticker=ticker, simbolo_subyacente=simbolo, mercado_subyacente="NMS",
        moneda_subyacente="USD", resolucion_estado="ok",
    ))
    ahora = datetime.now()
    db.add(ZonaPrecio(ticker=ticker, tipo="compra", variante="subyacente", moneda="USD",
                      piso=None, techo=180.0, activa=1,
                      fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()


def _stub_ultimo_precio(monkeypatch, por_simbolo):
    pedidos: list[str] = []

    def falso(simbolo):
        pedidos.append(simbolo)
        return por_simbolo.get(simbolo)

    monkeypatch.setattr(refresco_precios.yahoo, "fetch_ultimo_precio", falso)
    return pedidos


def test_refresca_el_subyacente_de_los_tickers_con_zona_en_usd(db, monkeypatch):
    from app.database import PrecioSubyacente

    _con_zona_subyacente(db)
    _stub_fetch(monkeypatch, [])
    pedidos = _stub_ultimo_precio(monkeypatch, {"MSFT": {"precio": 173.4, "moneda": "USD"}})

    resumen = refresco_precios.refrescar(db)

    assert pedidos == ["MSFT"]              # el símbolo de Yahoo, no el ticker local
    assert resumen["precios_subyacente"] == 1
    fila = db.query(PrecioSubyacente).one()
    assert fila.ticker == "MSFT" and float(fila.precio) == 173.4 and fila.moneda == "USD"
    assert db.get(RefrescoPrecios, 1).precios_subyacente == 1


def test_no_pide_nada_sin_zonas_medidas_sobre_el_subyacente(db, monkeypatch):
    """Bajar el precio de todos los subyacentes resueltos sería gastar llamadas en series que
    nadie está vigilando."""
    db.add(WatchlistItem(ticker="MSFT", nombre="Microsoft", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", agregado_en=HOY))
    db.add(EstadoMarketDataTicker(
        ticker="MSFT", simbolo_subyacente="MSFT", mercado_subyacente="NMS",
        moneda_subyacente="USD", resolucion_estado="ok",
    ))
    db.commit()
    _stub_fetch(monkeypatch, [])
    pedidos = _stub_ultimo_precio(monkeypatch, {"MSFT": {"precio": 173.4, "moneda": "USD"}})

    assert refresco_precios.refrescar(db)["precios_subyacente"] == 0
    assert pedidos == []


def test_una_zona_local_no_pide_el_subyacente(db, monkeypatch):
    from datetime import datetime

    from app.database import ZonaPrecio

    _con_zona_subyacente(db)
    db.query(ZonaPrecio).update({"variante": "local"})
    db.commit()
    _stub_fetch(monkeypatch, [])
    pedidos = _stub_ultimo_precio(monkeypatch, {"MSFT": {"precio": 173.4, "moneda": "USD"}})

    assert refresco_precios.refrescar(db)["precios_subyacente"] == 0
    assert pedidos == []


def test_un_precio_que_no_viene_en_usd_no_se_guarda(db, monkeypatch):
    """Comparar una zona en dólares contra un precio en otra moneda es un aviso falso: es más
    seguro no tener precio que tener uno equivocado."""
    from app.database import PrecioSubyacente

    _con_zona_subyacente(db)
    _stub_fetch(monkeypatch, [])
    _stub_ultimo_precio(monkeypatch, {"MSFT": {"precio": 173.4, "moneda": "EUR"}})

    assert refresco_precios.refrescar(db)["precios_subyacente"] == 0
    assert db.query(PrecioSubyacente).count() == 0


def test_un_fallo_de_yahoo_no_rompe_la_corrida(db, monkeypatch):
    _con_zona_subyacente(db)
    _stub_fetch(monkeypatch, [])
    _stub_ultimo_precio(monkeypatch, {})    # devuelve None

    resumen = refresco_precios.refrescar(db)
    assert resumen["resultado"] == "ok"
    assert resumen["precios_subyacente"] == 0


def test_un_subyacente_sin_resolver_no_se_pide(db, monkeypatch):
    """Sin `resolucion_estado == "ok"` no hay un subyacente en USD confirmado."""
    _con_zona_subyacente(db)
    db.query(EstadoMarketDataTicker).update({"resolucion_estado": "sin_subyacente"})
    db.commit()
    _stub_fetch(monkeypatch, [])
    pedidos = _stub_ultimo_precio(monkeypatch, {"MSFT": {"precio": 173.4, "moneda": "USD"}})

    assert refresco_precios.refrescar(db)["precios_subyacente"] == 0
    assert pedidos == []


def test_el_precio_del_subyacente_no_entra_en_la_serie_ohlcv(db, monkeypatch):
    """`serie_ohlcv` alimenta indicadores y backtests: un close-only intradía no puede degradar la
    vela que yfinance ya trajo del día en curso (es la guarda G4 del diseño del subyacente)."""
    _con_zona_subyacente(db)
    _stub_fetch(monkeypatch, [])
    _stub_ultimo_precio(monkeypatch, {"MSFT": {"precio": 173.4, "moneda": "USD"}})

    refresco_precios.refrescar(db)
    assert db.query(BarraOHLCV).filter(BarraOHLCV.ticker.like("%@SUB")).count() == 0
