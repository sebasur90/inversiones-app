"""Serie de referencia: un CEDEAR se analiza por su precio real en USD, no por el del CEDEAR.

Cubre la regla (`ohlcv_analytics.variante_referencia`), cómo la resuelven el endpoint, el screener,
las señales y la Watchlist, el refresco del precio del subyacente y las dos migraciones de datos
(estrategias y zonas). Los tests de cada pieza por separado viven en sus archivos; acá está lo que
sólo tiene sentido en conjunto.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.database import (
    AlertaPrecio, Base, BarraOHLCV, EstadoMarketDataTicker, EstrategiaTecnica, InstrumentoInversion,
    PrecioInstrumento, PrecioSubyacente, PrecioWatchlist, WatchlistItem, ZonaPrecio, get_db,
)
from app.main import app
from app.services import ohlcv_analytics as oa
from app.services import refresco_precios, screener_analytics, watchlist_analytics
from app.services.estrategias_analytics import senales_recientes

HOY = date.today()
N = oa.MIN_BARRAS_REFERENCIA + 20   # barras suficientes para ser la referencia


# ── helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _watchlist(db, ticker, tipo="CEDEAR", moneda="ARS"):
    db.add(WatchlistItem(ticker=ticker, nombre=f"{ticker} S.A.", tipo_instrumento=tipo,
                         mercado="BCBA", moneda=moneda, agregado_en=HOY))
    db.commit()


def _resuelto(db, ticker, moneda="USD", estado="ok"):
    db.add(EstadoMarketDataTicker(
        ticker=ticker, simbolo_subyacente=ticker, mercado_subyacente="NMS",
        moneda_subyacente=moneda, resolucion_estado=estado,
    ))
    db.commit()


def _serie_sub(db, ticker, n=N, base=500.0, moneda="USD", paso=1.0):
    """`n` velas del subyacente (clave `@SUB`), la última de ayer."""
    for i in range(n):
        f = HOY - timedelta(days=n - i)
        c = base + i * paso
        db.add(BarraOHLCV(ticker=f"{ticker}@SUB", fecha=f, apertura=c - 1, maximo=c + 1,
                          minimo=c - 2, cierre=c, volumen=1e6, moneda=moneda, fuente="yahoo"))
    db.commit()


def _serie_local(db, ticker, n=N, base=26000.0, moneda="ARS", paso=10.0):
    for i in range(n):
        f = HOY - timedelta(days=n - i)
        c = base + i * paso
        db.add(BarraOHLCV(ticker=ticker, fecha=f, apertura=c - 5, maximo=c + 5, minimo=c - 10,
                          cierre=c, volumen=1e3, moneda=moneda, fuente="iol"))
    db.commit()


def _cedear_con_sub(db, ticker="MSFT", base_sub=500.0, paso_sub=1.0):
    _watchlist(db, ticker)
    _resuelto(db, ticker)
    _serie_sub(db, ticker, base=base_sub, paso=paso_sub)
    _serie_local(db, ticker)


def _zona(db, ticker, techo, variante, moneda, tipo="compra", activa=1, piso=None):
    ahora = datetime.now()
    db.add(ZonaPrecio(ticker=ticker, tipo=tipo, variante=variante, moneda=moneda,
                      piso=piso, techo=techo, activa=activa,
                      fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()


# ── la regla ──────────────────────────────────────────────────────────────────

def _series(barras_sub=N, moneda_sub="USD"):
    return [
        {"variante": "local", "moneda": "ARS", "mercado": "BCBA", "barras": 0},
        {"variante": "subyacente", "moneda": moneda_sub, "mercado": "NMS", "barras": barras_sub},
    ]


def test_cedear_con_serie_del_subyacente_en_usd_se_mide_en_usd():
    assert oa.variante_referencia("CEDEAR", _series()) == "subyacente"


def test_cedear_sin_serie_del_subyacente_sigue_en_local():
    """Un CEDEAR recién agregado, o uno que yfinance no resolvió, no apunta a una serie vacía."""
    assert oa.variante_referencia("CEDEAR", [_series()[0]]) == "local"


def test_cedear_con_muy_pocas_barras_del_subyacente_sigue_en_local():
    """Con 3 barras la pantalla por defecto mostraría un gráfico de 3 puntos tapando años de serie."""
    assert oa.variante_referencia("CEDEAR", _series(barras_sub=3)) == "local"
    assert oa.variante_referencia("CEDEAR", _series(barras_sub=oa.MIN_BARRAS_REFERENCIA)) == "subyacente"


def test_accion_argentina_con_adr_resuelto_sigue_en_local():
    """GGAL/YPF tienen el ADR como subyacente, pero su mercado de referencia es BYMA en pesos."""
    assert oa.variante_referencia("Acción", _series()) == "local"
    assert oa.variante_referencia("Accion", _series()) == "local"


def test_bono_o_on_sigue_en_local():
    assert oa.variante_referencia("Bono", _series()) == "local"
    assert oa.variante_referencia("ON", _series()) == "local"


def test_si_la_serie_del_subyacente_no_esta_en_usd_no_es_la_referencia():
    assert oa.variante_referencia("CEDEAR", _series(moneda_sub="EUR")) == "local"


def test_resolver_variante():
    assert oa.resolver_variante(None, "subyacente") == "subyacente"
    assert oa.resolver_variante("referencia", "subyacente") == "subyacente"
    assert oa.resolver_variante("referencia", "local") == "local"
    # Un pedido explícito manda sobre la referencia.
    assert oa.resolver_variante("local", "subyacente") == "local"
    assert oa.resolver_variante("subyacente", "local") == "subyacente"
    with pytest.raises(ValueError):
        oa.resolver_variante("otra", "local")


def test_clave_serie_rechaza_una_variante_sin_resolver():
    """Un 'referencia' que se filtrara hasta acá degradaría en silencio a la serie local."""
    with pytest.raises(ValueError):
        oa.clave_serie("MSFT", "referencia")


def test_el_listado_de_tickers_trae_la_referencia(db):
    _cedear_con_sub(db, "MSFT")
    _watchlist(db, "GGAL", tipo="Acción")
    _resuelto(db, "GGAL")          # ADR resuelto...
    _serie_sub(db, "GGAL")         # ...y con serie en USD, pero es una acción argentina
    _watchlist(db, "AAPL")         # CEDEAR sin serie del subyacente todavía

    por_ticker = {t["ticker"]: t["variante_referencia"] for t in oa.listar_tickers_tecnicos(db)}
    assert por_ticker == {"MSFT": "subyacente", "GGAL": "local", "AAPL": "local"}
    assert oa.mapa_referencias(db) == por_ticker


# ── endpoint ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(db):
    _cedear_con_sub(db, "MSFT")
    _watchlist(db, "GGAL", tipo="Acción")
    _serie_local(db, "GGAL", base=7000.0)

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_serie_sin_variante_sirve_la_de_referencia(client):
    msft = client.get("/api/inversiones/tecnico/MSFT/serie").json()
    assert msft["variante"] == "subyacente" and msft["moneda"] == "USD"
    assert all(b["cierre"] < 1000 for b in msft["barras"])      # dólares, no los ~26.000 del CEDEAR

    ggal = client.get("/api/inversiones/tecnico/GGAL/serie").json()
    assert ggal["variante"] == "local" and ggal["moneda"] == "ARS"


def test_serie_con_variante_explicita_manda_sobre_la_referencia(client):
    r = client.get("/api/inversiones/tecnico/MSFT/serie", params={"variante": "local"}).json()
    assert r["variante"] == "local"
    assert all(b["cierre"] > 20000 for b in r["barras"])


def test_serie_no_acepta_el_literal_referencia(client):
    assert client.get("/api/inversiones/tecnico/MSFT/serie", params={"variante": "referencia"}).status_code == 422


def test_serie_explicita_del_subyacente_sin_serie_sigue_siendo_404(client):
    assert client.get("/api/inversiones/tecnico/GGAL/serie", params={"variante": "subyacente"}).status_code == 404


def test_listado_expone_la_referencia(client):
    por_ticker = {t["ticker"]: t["variante_referencia"] for t in client.get("/api/inversiones/tecnico/tickers").json()}
    assert por_ticker["MSFT"] == "subyacente" and por_ticker["GGAL"] == "local"


_DSL = {
    "version": 1, "indicadores": [],
    "entrada": {"op": "menor_igual", "izq": {"campo": "cierre"}, "der": {"const": 400.0}},
    "salida": None,
    "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
    "ejecucion": {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0},
}


def test_backtest_sin_variante_corre_sobre_la_referencia(client):
    r = client.post("/api/inversiones/tecnico/MSFT/backtest", json={"definicion": _DSL}).json()
    assert r["variante"] == "subyacente" and r["moneda"] == "USD"
    r = client.post("/api/inversiones/tecnico/MSFT/backtest",
                    json={"definicion": _DSL, "variante": "local"}).json()
    assert r["variante"] == "local"


def test_estrategia_guardada_acepta_referencia_pero_no_un_valor_desconocido(client):
    r = client.post("/api/inversiones/estrategias", json={"nombre": "E1", "definicion": _DSL})
    assert r.status_code == 201 and r.json()["variante"] == "referencia"
    r = client.post("/api/inversiones/estrategias", json={"nombre": "E2", "definicion": _DSL, "variante": "otra"})
    assert r.status_code == 422


# ── estrategias: screener y señales ───────────────────────────────────────────

def _dsl_cierre_menor_igual(nivel):
    return {**_DSL, "entrada": {"op": "menor_igual", "izq": {"campo": "cierre"}, "der": {"const": nivel}}}


def _estrategia(db, variante="referencia", nombre="Barata", ticker=None, nivel=550.0):
    """El screener sólo busca disparos a menos de ~15 %: el nivel tiene que quedar cerca del precio
    de la serie que se quiere evaluar (~579 USD el subyacente, ~26.800 ARS el CEDEAR)."""
    ahora = datetime.utcnow()
    db.add(EstrategiaTecnica(nombre=nombre, ticker=ticker, definicion=_dsl_cierre_menor_igual(nivel),
                             variante=variante, fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()


def _fila(resultado, ticker):
    return next(f for f in resultado["filas"] if f["ticker"] == ticker)


def test_screener_evalua_cada_ticker_en_su_serie_de_referencia(db):
    """La misma estrategia mide a MSFT en dólares y a GGAL en pesos, en el mismo escaneo."""
    # Series casi planas que empiezan por encima del nivel: si arrancaran por debajo, la estrategia
    # abriría una posición en las primeras barras y el screener buscaría su salida, no su entrada.
    _cedear_con_sub(db, "MSFT", base_sub=600.0, paso_sub=0.1)     # USD ~600-608; el CEDEAR, ~26.000
    _watchlist(db, "GGAL", tipo="Acción")
    _serie_local(db, "GGAL", base=600.0, moneda="ARS", paso=0.1)  # ARS ~600-608
    _estrategia(db, nivel=590.0)

    r = screener_analytics.escanear(db, umbral_pct=99.0)

    msft, ggal = _fila(r, "MSFT"), _fila(r, "GGAL")
    assert msft["variante"] == "subyacente" and msft["moneda"] == "USD"
    assert 600 < msft["precio_actual"] < 610                 # el precio del Nasdaq, no el del CEDEAR
    assert ggal["variante"] == "local" and ggal["moneda"] == "ARS"
    assert all(f["variante"] in ("local", "subyacente") for f in r["filas"])   # nunca 'referencia'


def test_screener_con_variante_forzada_pisa_la_de_la_estrategia(db):
    _cedear_con_sub(db, "MSFT")
    _estrategia(db, variante="referencia", nivel=25500.0)

    r = screener_analytics.escanear(db, umbral_pct=99.0, variante="local")
    assert _fila(r, "MSFT")["variante"] == "local"
    assert _fila(r, "MSFT")["precio_actual"] > 20000


def test_screener_rechaza_una_variante_forzada_desconocida(db):
    with pytest.raises(ValueError):
        screener_analytics.escanear(db, variante="referencia")


def test_una_estrategia_fijada_en_local_no_sigue_la_referencia(db):
    _cedear_con_sub(db, "MSFT")
    _estrategia(db, variante="local", nivel=25500.0)
    assert _fila(screener_analytics.escanear(db, umbral_pct=99.0), "MSFT")["variante"] == "local"


def test_senales_recientes_informan_la_serie_ya_resuelta(db):
    """El mensaje de Telegram trata cualquier variante que no sea 'local' como 'subyacente en USD':
    una señal con 'referencia' sin resolver mentiría sobre la serie."""
    _cedear_con_sub(db, "MSFT")
    _watchlist(db, "GGAL", tipo="Acción")
    _serie_local(db, "GGAL", base=350.0, moneda="ARS")
    _estrategia(db)

    # Un DSL que cumple en la última barra de cualquiera de las dos series.
    ahora = datetime.utcnow()
    db.query(EstrategiaTecnica).delete()
    dsl = {**_DSL, "entrada": {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0.0}}}
    db.add(EstrategiaTecnica(nombre="Siempre", definicion=dsl, variante="referencia",
                             fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()

    por_ticker = {s["ticker"]: s for s in senales_recientes(db, max_antiguedad_barras=10_000)}
    assert por_ticker["MSFT"]["variante"] == "subyacente" and por_ticker["MSFT"]["moneda"] == "USD"
    assert por_ticker["GGAL"]["variante"] == "local"


# ── watchlist ─────────────────────────────────────────────────────────────────

def _fila_wl(db, ticker):
    return next(f for f in watchlist_analytics.get_watchlist(db) if f["ticker"] == ticker)


def test_watchlist_muestra_el_precio_en_usd_como_referencia_y_conserva_el_local(db):
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioWatchlist(ticker="MSFT", fecha=HOY, precio=26400.0, moneda="ARS", fuente="iol"))
    db.commit()

    fila = _fila_wl(db, "MSFT")
    assert fila["variante_referencia"] == "subyacente"
    assert fila["moneda_referencia"] == "USD"
    assert fila["precio_referencia"] == pytest.approx(500.0 + N - 1)        # último cierre del @SUB
    assert fila["fuente_precio_referencia"] == "cierre"
    # El contrato de `precio_actual` no cambia: es el CEDEAR en pesos.
    assert fila["precio_actual"] == 26400.0 and fila["moneda_precio"] == "ARS"


def test_watchlist_prefiere_el_precio_intradia_si_es_mas_fresco(db):
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioSubyacente(ticker="MSFT", fecha=HOY, precio=612.5, moneda="USD", fuente="yahoo"))
    db.commit()

    fila = _fila_wl(db, "MSFT")
    assert fila["precio_referencia"] == 612.5
    assert fila["fuente_precio_referencia"] == "intradia"
    assert fila["fecha_precio_referencia"] == HOY


def test_la_variacion_del_dia_de_la_referencia_sale_de_las_velas_del_subyacente(db):
    """No de `cotizacion_diaria` de IOL, que es la variación del CEDEAR en pesos."""
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioSubyacente(ticker="MSFT", fecha=HOY, precio=600.0, moneda="USD", fuente="yahoo"))
    db.add(PrecioWatchlist(ticker="MSFT", fecha=HOY, precio=26400.0, moneda="ARS", fuente="iol"))
    db.commit()
    cierre_ayer = 500.0 + N - 1

    fila = _fila_wl(db, "MSFT")
    assert fila["variacion_dia_referencia"] == pytest.approx(600.0 - cierre_ayer)
    assert fila["variacion_dia_referencia_pct"] == pytest.approx(600.0 / cierre_ayer - 1, abs=1e-4)


def test_un_cedear_sin_serie_del_subyacente_se_comporta_como_antes(db):
    _watchlist(db, "AAPL")
    db.add(PrecioWatchlist(ticker="AAPL", fecha=HOY, precio=5300.0, moneda="ARS", fuente="api"))
    db.commit()
    _zona(db, "AAPL", 4900.0, "local", "ARS")

    fila = _fila_wl(db, "AAPL")
    assert fila["variante_referencia"] == "local"
    assert fila["precio_referencia"] == 5300.0 and fila["moneda_referencia"] == "ARS"
    assert fila["base_comparacion"] == "local" and fila["moneda_objetivo"] == "ARS"
    assert fila["pct_a_objetivo"] == pytest.approx((4900.0 - 5300.0) / 5300.0)


def test_una_zona_en_usd_ahora_mide_la_distancia_contra_el_subyacente(db):
    """Antes la fila decía 'Sin zona' porque la zona del subyacente no se comparaba con nada."""
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioWatchlist(ticker="MSFT", fecha=HOY, precio=26400.0, moneda="ARS", fuente="iol"))
    db.add(PrecioSubyacente(ticker="MSFT", fecha=HOY, precio=500.0, moneda="USD", fuente="yahoo"))
    db.commit()
    _zona(db, "MSFT", 470.0, "subyacente", "USD")

    fila = _fila_wl(db, "MSFT")
    assert fila["base_comparacion"] == "subyacente" and fila["moneda_objetivo"] == "USD"
    assert fila["precio_objetivo"] == 470.0
    assert fila["en_zona"] is False
    assert fila["pct_a_objetivo"] == pytest.approx((470.0 - 500.0) / 500.0)   # sobre dólares, no pesos


def test_una_zona_en_usd_en_zona_cuando_el_subyacente_la_cruza(db):
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioSubyacente(ticker="MSFT", fecha=HOY, precio=455.0, moneda="USD", fuente="yahoo"))
    db.commit()
    _zona(db, "MSFT", 470.0, "subyacente", "USD")
    assert _fila_wl(db, "MSFT")["en_zona"] is True


def test_una_zona_local_sobre_un_cedear_sigue_midiendo_contra_el_cedear(db):
    """Las zonas viejas en pesos no se reinterpretan: se miden contra su propia serie."""
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioWatchlist(ticker="MSFT", fecha=HOY, precio=26400.0, moneda="ARS", fuente="iol"))
    db.commit()
    _zona(db, "MSFT", 24000.0, "local", "ARS")

    fila = _fila_wl(db, "MSFT")
    assert fila["base_comparacion"] == "local" and fila["moneda_objetivo"] == "ARS"
    assert fila["pct_a_objetivo"] == pytest.approx((24000.0 - 26400.0) / 26400.0)


def test_zona_en_usd_sin_precio_del_subyacente_no_inventa_distancia(db):
    _watchlist(db, "AAPL")       # sin serie ni precio del subyacente
    _zona(db, "AAPL", 150.0, "subyacente", "USD")
    fila = _fila_wl(db, "AAPL")
    assert fila["pct_a_objetivo"] is None and fila["en_zona"] is None and fila["base_comparacion"] is None


def test_el_atajo_de_compra_escribe_en_la_serie_de_referencia(db):
    """'Comprar por debajo de 470' sobre MSFT son 470 dólares del Nasdaq, no 470 pesos."""
    _cedear_con_sub(db, "MSFT")
    watchlist_analytics.actualizar(db, "MSFT", {"objetivo": 470.0})
    z = db.query(ZonaPrecio).filter_by(ticker="MSFT", tipo="compra").one()
    assert z.variante == "subyacente" and z.moneda == "USD" and float(z.techo) == 470.0

    _watchlist(db, "GGAL", tipo="Acción")
    watchlist_analytics.actualizar(db, "GGAL", {"objetivo": 7000.0})
    z = db.query(ZonaPrecio).filter_by(ticker="GGAL", tipo="compra").one()
    assert z.variante == "local" and z.moneda == "ARS"


def test_el_orden_por_urgencia_sigue_siendo_porcentual_entre_monedas(db):
    _cedear_con_sub(db, "MSFT")
    db.add(PrecioSubyacente(ticker="MSFT", fecha=HOY, precio=455.0, moneda="USD", fuente="yahoo"))
    _watchlist(db, "GGAL", tipo="Acción")
    db.add(PrecioWatchlist(ticker="GGAL", fecha=HOY, precio=8000.0, moneda="ARS", fuente="api"))
    db.commit()
    _zona(db, "MSFT", 470.0, "subyacente", "USD")     # ya en zona (USD)
    _zona(db, "GGAL", 7000.0, "local", "ARS")         # 12,5 % por encima (ARS)

    assert [f["ticker"] for f in watchlist_analytics.get_watchlist(db)] == ["MSFT", "GGAL"]


# ── refresco del precio del subyacente ────────────────────────────────────────

@pytest.fixture
def pedidos(monkeypatch):
    llamados: list[str] = []

    def falso(simbolo):
        llamados.append(simbolo)
        return {"precio": 123.0, "moneda": "USD"}

    monkeypatch.setattr(refresco_precios.yahoo, "fetch_ultimo_precio", falso)
    return llamados


def test_refresca_los_cedears_que_se_miran_en_usd_aunque_no_tengan_zona(db, pedidos):
    _cedear_con_sub(db, "MSFT")
    assert refresco_precios._refrescar_subyacentes(db) == 1
    assert pedidos == ["MSFT"]
    assert db.get(PrecioSubyacente, "MSFT").moneda == "USD"


def test_no_refresca_a_quien_no_se_mira_en_usd(db, pedidos):
    _watchlist(db, "GGAL", tipo="Acción")
    _resuelto(db, "GGAL")
    _serie_sub(db, "GGAL")                       # acción argentina con ADR: referencia local
    _watchlist(db, "AAPL")
    _resuelto(db, "AAPL")                        # CEDEAR resuelto pero sin serie todavía
    assert refresco_precios._refrescar_subyacentes(db) == 0
    assert pedidos == []


def test_las_zonas_tienen_prioridad_y_el_tope_rota(db, pedidos, monkeypatch):
    """Con más tickers que cupo, los que tienen una zona vigilada no pueden quedar afuera por un
    ticker sin zona que empieza con 'A', y los de referencia rotan entre corridas."""
    monkeypatch.setattr(refresco_precios, "_MAX_SUBYACENTES_CON_ZONA", 1)
    monkeypatch.setattr(refresco_precios, "_MAX_SUBYACENTES_REFERENCIA", 1)
    for t in ("AAA", "BBB", "ZZZ"):
        _cedear_con_sub(db, t)
    _zona(db, "ZZZ", 100.0, "subyacente", "USD")

    refresco_precios._refrescar_subyacentes(db)
    assert pedidos[0] == "ZZZ"                    # el de la zona primero, pese al orden alfabético
    assert pedidos[1:] == ["AAA"]                 # y uno solo de los de referencia

    pedidos.clear()
    db.get(PrecioSubyacente, "AAA").fecha = HOY   # AAA ya está fresco; ahora le toca a BBB
    db.commit()
    refresco_precios._refrescar_subyacentes(db)
    assert pedidos[1:] == ["BBB"]


# ── migraciones ───────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.connect() as c:
        yield c


def _sql(conn, sentencia, **params):
    conn.execute(text(sentencia), params)
    conn.commit()


def test_la_migracion_replica_el_minimo_de_barras_de_la_regla():
    import inspect
    asumido = inspect.signature(database.migrar_zonas_locales_de_cedears).parameters["min_barras"].default
    assert asumido == oa.MIN_BARRAS_REFERENCIA


def test_las_estrategias_en_local_pasan_a_referencia_y_las_de_subyacente_no(conn):
    ahora = "2026-01-01 00:00:00"
    for nombre, variante in (("a", "local"), ("b", "subyacente")):
        _sql(conn, "INSERT INTO estrategias_tecnicas (nombre, definicion, variante, notificar_compra, "
                   "notificar_venta, fecha_creacion, fecha_actualizacion) VALUES (:n, '{}', :v, 0, 0, :f, :f)",
             n=nombre, v=variante, f=ahora)

    database.migrar_estrategias_a_referencia(conn)

    variantes = dict(conn.execute(text("SELECT nombre, variante FROM estrategias_tecnicas")).fetchall())
    assert variantes == {"a": "referencia", "b": "subyacente"}


def test_fijar_una_estrategia_en_local_a_proposito_sobrevive_al_proximo_arranque(conn):
    """La marca evita que la migración le deshaga la elección al usuario."""
    database.migrar_estrategias_a_referencia(conn)
    _sql(conn, "INSERT INTO estrategias_tecnicas (nombre, definicion, variante, notificar_compra, "
               "notificar_venta, fecha_creacion, fecha_actualizacion) "
               "VALUES ('c', '{}', 'local', 0, 0, '2026-01-01', '2026-01-01')")

    database.migrar_estrategias_a_referencia(conn)

    assert conn.execute(text("SELECT variante FROM estrategias_tecnicas WHERE nombre='c'")).scalar() == "local"


def _poblar_para_zonas(conn):
    """MSFT: CEDEAR con 80 velas USD del subyacente. AAPL: CEDEAR sin serie. GGAL: acción con ADR.
    AL30: bono."""
    for ticker, tipo in (("MSFT", "CEDEAR"), ("AAPL", "CEDEAR"), ("GGAL", "Acción")):
        _sql(conn, "INSERT INTO watchlist (ticker, nombre, tipo_instrumento, mercado, moneda) "
                   "VALUES (:t, :t, :tipo, 'BCBA', 'ARS')", t=ticker, tipo=tipo)
    _sql(conn, "INSERT INTO instrumentos_inversion (ticker, nombre, tipo_instrumento, mercado, moneda) "
               "VALUES ('AL30', 'Bono', 'Bono', 'MERVAL', 'USD')")
    for ticker in ("MSFT", "GGAL"):
        for i in range(N):
            _sql(conn, "INSERT INTO serie_ohlcv (ticker, fecha, cierre, moneda, fuente) "
                       "VALUES (:t, :f, 100, 'USD', 'yahoo')",
                 t=f"{ticker}@SUB", f=(date(2025, 1, 1) + timedelta(days=i)).isoformat())
    for ticker in ("MSFT", "AAPL", "GGAL", "AL30"):
        _sql(conn, "INSERT INTO zonas_precio (ticker, tipo, variante, moneda, techo, activa, "
                   "fecha_creacion, fecha_actualizacion) VALUES (:t, 'compra', 'local', 'ARS', 100, 1, "
                   "'2026-01-01', '2026-01-01')", t=ticker)
        _sql(conn, "INSERT INTO alertas_precio (ticker, tipo, cartera, estado, entregada) "
                   "VALUES (:t, 'compra_zona', '', 'disparada', 1)", t=ticker)


def _estado_zonas(conn):
    return {t: (a, v) for t, a, v in conn.execute(text("SELECT ticker, activa, vencida FROM zonas_precio"))}


def test_las_zonas_locales_de_cedears_con_subyacente_quedan_vencidas(conn):
    _poblar_para_zonas(conn)

    database.migrar_zonas_locales_de_cedears(conn)

    assert _estado_zonas(conn) == {
        "MSFT": (0, 1),    # CEDEAR con serie del subyacente: vencida
        "AAPL": (1, 0),    # CEDEAR sin serie todavía: no se toca
        "GGAL": (1, 0),    # acción argentina con ADR: sigue en pesos
        "AL30": (1, 0),    # bono
    }
    # Los números se conservan, para poder recuperarla.
    assert conn.execute(text("SELECT techo FROM zonas_precio WHERE ticker='MSFT'")).scalar() == 100
    # El estado de la alerta de la zona vencida se borra: al re-dibujarla en USD el primer cruce avisa.
    assert {t for (t,) in conn.execute(text("SELECT ticker FROM alertas_precio"))} == {"AAPL", "GGAL", "AL30"}


def test_una_zona_local_dibujada_despues_no_se_vuelve_a_vencer(conn):
    _poblar_para_zonas(conn)
    database.migrar_zonas_locales_de_cedears(conn)
    _sql(conn, "UPDATE zonas_precio SET activa = 1, vencida = 0 WHERE ticker = 'MSFT'")

    database.migrar_zonas_locales_de_cedears(conn)

    assert _estado_zonas(conn)["MSFT"] == (1, 0)


def test_guardar_una_zona_limpia_la_marca_de_vencida(db):
    from app.services import zonas_precio

    _cedear_con_sub(db, "MSFT")
    _zona(db, "MSFT", 24000.0, "local", "ARS", activa=0)
    db.query(ZonaPrecio).update({"vencida": 1})
    db.commit()
    assert zonas_precio.zonas_de_ticker(db, "MSFT").compra.vencida is True

    zonas_precio.aplicar_cambios(db, "MSFT", {"compra": {
        "variante": "subyacente", "moneda": "USD", "techo": 470.0, "activa": True,
    }})

    z = zonas_precio.zonas_de_ticker(db, "MSFT").compra
    assert z.vencida is False and z.activa is True and z.variante == "subyacente"
