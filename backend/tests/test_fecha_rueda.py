"""El precio "del día" se fecha por la rueda a la que pertenece, no por el día del sync.

Antes se usaba `date.today()` del contenedor (UTC): un sync antes de la apertura, un fin de semana o
después de las 21 hs de Buenos Aires guardaba el cierre de la rueda anterior con otra fecha, y la
caída de un viernes aparecía corrida (o duplicada) en el histórico."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text

from app import database
from app.database import Base
from app.services.market_data import data912, iol
from app.services.market_data import precios as mdp

ART = ZoneInfo("America/Argentina/Buenos_Aires")
VIERNES = date(2026, 10, 30)
LUNES = date(2026, 11, 2)
_DB = object()


@pytest.mark.parametrize("ahora, esperado", [
    (datetime(2026, 11, 2, 9, 33, tzinfo=ART), VIERNES),     # lunes antes de la apertura
    (datetime(2026, 11, 2, 11, 0, tzinfo=ART), LUNES),       # lunes con el mercado abierto
    (datetime(2026, 10, 30, 18, 30, tzinfo=ART), VIERNES),   # viernes después del cierre
    (datetime(2026, 10, 31, 12, 0, tzinfo=ART), VIERNES),    # sábado
    (datetime(2026, 11, 1, 20, 0, tzinfo=ART), VIERNES),     # domingo
    (datetime(2026, 11, 4, 10, 59, tzinfo=ART), date(2026, 11, 3)),  # miércoles pre-apertura
    # Viernes 22 hs en Buenos Aires = sábado 01 hs UTC: `date.today()` del contenedor ya decía sábado.
    (datetime(2026, 10, 31, 1, 0, tzinfo=timezone.utc), VIERNES),
])
def test_fecha_rueda(ahora, esperado):
    assert mdp.fecha_rueda(ahora) == esperado


def test_fecha_cotizacion_usa_la_de_la_fuente_si_es_creible():
    assert mdp._fecha_cotizacion(VIERNES, LUNES) == VIERNES          # feriado el lunes: manda IOL
    assert mdp._fecha_cotizacion(None, LUNES) == LUNES
    assert mdp._fecha_cotizacion(date(2026, 11, 3), LUNES) == LUNES   # posterior a la rueda: no
    assert mdp._fecha_cotizacion(date(2026, 9, 1), LUNES) == LUNES    # de hace semanas: no


def _panel(monkeypatch, titulos):
    p0 = iol._PANELES[0]
    url0 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p0[0]}/{p0[1]}/{p0[2]}"
    monkeypatch.setattr(iol.iol_auth, "get_autenticado",
                        lambda db, url: {"titulos": titulos} if url == url0 else None)


def test_panel_captura_la_fecha_de_la_ultima_operacion(monkeypatch):
    _panel(monkeypatch, [
        {"simbolo": "GOOGL", "ultimoPrecio": 27000.0, "moneda": "AR$", "fecha": "2026-10-30T16:59:56.333"},
        {"simbolo": "KO", "ultimoPrecio": 18000.0, "moneda": "AR$", "fecha": "basura"},
        {"simbolo": "SPY", "ultimoPrecio": 20980.0, "moneda": "AR$"},
    ])
    out = iol.fetch_precios_paneles(_DB)
    assert out["GOOGL"].fecha == VIERNES
    assert out["KO"].fecha is None and out["SPY"].fecha is None
    assert out["GOOGL"] == (27000.0, "ARS")


def _inst(ticker, tipo="CEDEAR"):
    return {"ticker": ticker, "tipo_instrumento": tipo, "moneda": "ARS"}


def _px(ticker, precio):
    return {"ticker": ticker, "fecha": date(2026, 10, 1), "precio": precio, "moneda": "ARS"}


def test_precio_de_iol_se_fecha_con_su_ultima_operacion(monkeypatch):
    """Lunes feriado (o antes de la apertura): IOL informa el cierre del viernes y así se guarda."""
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: {
        "GOOGL": iol.CotizacionIOL(27000.0, "ARS", 28500.0, -5.26, VIERNES),
    })
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {})

    filas, issues = mdp.fetch_precios_api([_inst("GOOGL")], [_px("GOOGL", 26000.0)], set(), _DB, hoy=LUNES)

    assert issues == []
    assert [(f["ticker"], f["fecha"], f["fuente"]) for f in filas] == [("GOOGL", VIERNES, "iol")]


def test_data912_sin_fecha_usa_la_rueda(monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_precios_paneles", lambda db: None)
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"GOOGL": 27000.0})
    monkeypatch.setattr(mdp, "fecha_rueda", lambda: VIERNES)

    filas, _ = mdp.fetch_precios_api([_inst("GOOGL")], [_px("GOOGL", 26000.0)], set(), _DB)

    assert [(f["fecha"], f["fuente"]) for f in filas] == [(VIERNES, "api")]


def test_watchlist_se_fecha_con_la_ultima_operacion():
    cot = iol.CotizacionIOL(9000.0, "ARS", None, None, VIERNES)
    filas, _ = mdp.fetch_precios_watchlist_catalogo(
        [{"ticker": "MSFT", "tipo_instrumento": "CEDEAR", "moneda": "ARS"}], None, hoy=LUNES,
        paneles_fn=lambda: {"MSFT": cot}, fci_fn=lambda: None,
    )
    assert filas[0]["fecha"] == VIERNES


# --- Limpieza única de las filas automáticas fechadas en fin de semana ---------------------------

@pytest.fixture
def conn():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.connect() as c:
        yield c


def _sql(conn, sentencia, **params):
    conn.execute(text(sentencia), params)
    conn.commit()


def test_borra_precios_automaticos_de_fin_de_semana_una_sola_vez(conn):
    _sql(conn, "INSERT INTO instrumentos_inversion (ticker, nombre, tipo_instrumento, mercado, moneda) "
               "VALUES ('GOOGL', 'Alphabet', 'CEDEAR', 'BCBA', 'ARS')")
    for fecha, fuente in (("2026-10-30", "iol"), ("2026-10-31", "iol"), ("2026-11-01", "api"),
                          ("2026-10-25", "sheet")):
        _sql(conn, "INSERT INTO precios_instrumento (fecha, ticker, precio, moneda, fuente) "
                   "VALUES (:f, 'GOOGL', 27000, 'ARS', :fu)", f=fecha, fu=fuente)
    for fecha in ("2026-10-30", "2026-10-31"):
        _sql(conn, "INSERT INTO cotizacion_diaria (ticker, fecha, variacion_pct, fuente) "
                   "VALUES ('GOOGL', :f, -5, 'iol')", f=fecha)
    for ticker, fecha, fuente in (("GOOGL", "2026-10-30", "iol"), ("GOOGL", "2026-10-31", "iol"),
                                  ("GOOGL@SUB", "2026-10-31", "iol")):
        _sql(conn, "INSERT INTO serie_ohlcv (ticker, fecha, cierre, moneda, fuente) "
                   "VALUES (:t, :f, 100, 'ARS', :fu)", t=ticker, f=fecha, fu=fuente)

    database.borrar_precios_automaticos_de_fin_de_semana(conn)

    assert {r[0] for r in conn.execute(text("SELECT fecha FROM precios_instrumento"))} == {"2026-10-30", "2026-10-25"}
    assert {r[0] for r in conn.execute(text("SELECT fecha FROM cotizacion_diaria"))} == {"2026-10-30"}
    assert set(conn.execute(text("SELECT ticker, fecha FROM serie_ohlcv")).fetchall()) == {
        ("GOOGL", "2026-10-30"), ("GOOGL@SUB", "2026-10-31"),
    }

    _sql(conn, "INSERT INTO precios_instrumento (fecha, ticker, precio, moneda, fuente) "
               "VALUES ('2026-11-07', 'GOOGL', 1, 'ARS', 'iol')")
    database.borrar_precios_automaticos_de_fin_de_semana(conn)
    assert conn.execute(text("SELECT COUNT(*) FROM precios_instrumento WHERE fecha = '2026-11-07'")).scalar() == 1
