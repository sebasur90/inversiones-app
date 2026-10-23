"""CRUD de la watchlist: alta desde el catálogo, edición, baja y refresco de precio."""
import json

import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base, BarraOHLCV, EstadoMarketDataTicker, InstrumentoInversion, PrecioWatchlist,
    WatchlistItem, get_db,
)
from app.main import app
from app.services import catalogo_instrumentos as cat
from app.services.market_data import precios as market_data_precios

CATALOGO = [
    {"simbolo": "ALUA", "descripcion": "Aluar", "moneda": "AR$", "mercado": "BCBA",
     "pais": "argentina", "paneles": ["Acciones/Merval"]},
    {"simbolo": "AAPL", "descripcion": "Cedear Apple Inc", "moneda": "AR$", "mercado": "BCBA",
     "pais": "argentina", "paneles": ["Acciones/CEDEARs"]},
    {"simbolo": "MR36O", "descripcion": "On Gmctr Cl.36", "moneda": "AR$", "mercado": "BCBA",
     "pais": "argentina", "paneles": ["ObligacionesNegociables/Todas"]},
]

# Lo que IOL cotiza, tanto por panel como por símbolo suelto. MR36O sólo sale por símbolo suelto
# (las ONs no siempre están en los paneles), que es el camino que ejercita `test_alta_de_on_*`.
PRECIOS_IOL = {"ALUA": (1234.5, "ARS"), "AAPL": (28000.0, "ARS")}
PRECIOS_SUELTOS = {**PRECIOS_IOL, "MR36O": (98.5, "USD")}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Catálogo de prueba, IOL cotizando de mentira y APIs externas habilitadas."""
    ruta = tmp_path / "iol_catalogo.json"
    ruta.write_text(json.dumps({"instrumentos": CATALOGO}), encoding="utf-8")
    monkeypatch.setenv("IOL_CATALOGO_FILE", str(ruta))
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    cat._cache.clear()

    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles",
                        lambda db: dict(PRECIOS_IOL))
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_fci", lambda db: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo",
                        lambda db, simbolo: PRECIOS_SUELTOS.get(simbolo))
    yield
    cat._cache.clear()


@pytest.fixture
def sesion():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def client(entorno, sesion):
    def override():
        s = sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── Catálogo ──────────────────────────────────────────────────────────────────

def test_endpoint_catalogo_busca_y_cuenta(client):
    r = client.get("/api/inversiones/catalogo", params={"q": "a"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["conteos_por_tipo"]["CEDEAR"] == 1
    assert {i["simbolo"] for i in cuerpo["items"]} == {"ALUA", "AAPL"}


def test_endpoint_catalogo_filtra_por_tipo(client):
    r = client.get("/api/inversiones/catalogo", params={"tipo": "ON"})
    assert [i["simbolo"] for i in r.json()["items"]] == ["MR36O"]


# ── Alta ──────────────────────────────────────────────────────────────────────

def test_alta_cotiza_en_el_acto(client):
    r = client.post("/api/inversiones/watchlist", json={"ticker": "ALUA", "objetivo": 1000})
    assert r.status_code == 201
    item = r.json()
    assert item["precio_actual"] == 1234.5
    assert item["fuente_precio"] == "iol"
    assert item["precio_objetivo"] == 1000.0
    assert item["en_zona"] is False


def test_alta_copia_nombre_y_tipo_del_catalogo(client):
    item = client.post("/api/inversiones/watchlist", json={"ticker": "AAPL"}).json()
    assert item["nombre"] == "Cedear Apple Inc"
    assert item["tipo_instrumento"] == "CEDEAR"
    assert item["mercado"] == "BCBA"
    assert item["agregado_en"] == date.today().isoformat()


def test_alta_no_calibra_contra_el_objetivo(client):
    """La regresión que motivó el rediseño: con un objetivo absurdo el precio se carga igual.

    Con la calibración vieja, un objetivo a ~1/1000 del mercado dejaba el ratio fuera de las
    ventanas de `_factor_escala` y el instrumento quedaba sin precio.
    """
    item = client.post("/api/inversiones/watchlist", json={"ticker": "ALUA", "objetivo": 1}).json()
    assert item["precio_actual"] == 1234.5


def test_alta_sin_objetivo(client):
    """Elegir primero y decidir el objetivo después es el flujo normal de la pantalla."""
    item = client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"}).json()
    assert item["precio_actual"] == 1234.5
    assert item["precio_objetivo"] is None
    assert item["en_zona"] is None


def test_alta_de_simbolo_fuera_del_catalogo_es_404(client):
    r = client.post("/api/inversiones/watchlist", json={"ticker": "NOEXISTE"})
    assert r.status_code == 404
    assert "catálogo" in r.json()["detail"]


def test_alta_duplicada_es_409(client):
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    r = client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    assert r.status_code == 409


def test_alta_sobrevive_a_que_la_cotizacion_falle(client, monkeypatch):
    """El alta no puede depender de que una API de terceros esté arriba."""
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", lambda db: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo", lambda db, s: None)
    monkeypatch.setattr(market_data_precios.data912, "fetch_precios_renta_variable", lambda: None)
    r = client.post("/api/inversiones/watchlist", json={"ticker": "ALUA", "objetivo": 1000})
    assert r.status_code == 201
    assert r.json()["precio_actual"] is None


def test_alta_de_on_usa_el_simbolo_suelto(client):
    """Las ONs no siempre están en los paneles: se cotizan con `Titulos/{simbolo}/Cotizacion`."""
    item = client.post("/api/inversiones/watchlist", json={"ticker": "MR36O"}).json()
    assert item["precio_actual"] == 98.5
    assert item["moneda_precio"] == "USD", "la moneda la manda la fuente, no el catálogo"


def test_objetivo_negativo_es_422(client):
    r = client.post("/api/inversiones/watchlist", json={"ticker": "ALUA", "objetivo": -5})
    assert r.status_code == 422


# ── Edición ───────────────────────────────────────────────────────────────────

def test_editar_objetivo_y_notas(client):
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA", "objetivo": 1000})
    r = client.put("/api/inversiones/watchlist/ALUA",
                   json={"objetivo": 1300, "notas": "esperar resultados"})
    assert r.status_code == 200
    item = r.json()
    assert item["precio_objetivo"] == 1300.0
    assert item["notas"] == "esperar resultados"
    # 1234.5 < 1300: cruzó hacia abajo, está en zona de compra.
    assert item["en_zona"] is True


def test_editar_solo_el_objetivo_no_borra_las_notas(client):
    """PUT parcial: lo que el body no manda, no se toca."""
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA", "notas": "seguir el balance"})
    item = client.put("/api/inversiones/watchlist/ALUA", json={"objetivo": 1300}).json()
    assert item["notas"] == "seguir el balance"
    assert item["precio_objetivo"] == 1300.0

    # Mandar null explícito sí limpia.
    item = client.put("/api/inversiones/watchlist/ALUA", json={"notas": None}).json()
    assert item["notas"] is None
    assert item["precio_objetivo"] == 1300.0, "el objetivo tampoco se toca si no vino en el body"


def test_editar_lo_que_no_se_sigue_es_404(client):
    assert client.put("/api/inversiones/watchlist/ALUA", json={"objetivo": 1}).status_code == 404


# ── Baja ──────────────────────────────────────────────────────────────────────

def test_baja_limpia_precio_y_velas(client, sesion):
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    db = sesion()
    db.add(BarraOHLCV(ticker="ALUA", fecha=date(2026, 1, 2), cierre=1000,
                      moneda="ARS", fuente="api"))
    db.add(BarraOHLCV(ticker="ALUA@SUB", fecha=date(2026, 1, 2), cierre=10,
                      moneda="USD", fuente="api"))
    db.add(EstadoMarketDataTicker(ticker="ALUA", factor_escala=1.0))
    db.commit()
    db.close()

    assert client.delete("/api/inversiones/watchlist/ALUA").status_code == 204

    db = sesion()
    assert db.query(WatchlistItem).count() == 0
    assert db.query(PrecioWatchlist).count() == 0
    assert db.query(BarraOHLCV).count() == 0, "la serie del subyacente (@SUB) también se va"
    assert db.query(EstadoMarketDataTicker).count() == 0
    db.close()


def test_baja_no_toca_las_velas_de_un_ticker_en_cartera(client, sesion):
    """Si además se posee, esa serie la usa el análisis técnico de la posición."""
    db = sesion()
    db.add(InstrumentoInversion(ticker="ALUA", nombre="Aluar", tipo_instrumento="Acción",
                                mercado="BCBA", moneda="ARS"))
    db.commit()
    db.close()

    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    db = sesion()
    db.add(BarraOHLCV(ticker="ALUA", fecha=date(2026, 1, 2), cierre=1000,
                      moneda="ARS", fuente="api"))
    db.commit()
    db.close()

    client.delete("/api/inversiones/watchlist/ALUA")
    db = sesion()
    assert db.query(BarraOHLCV).count() == 1
    db.close()


def test_baja_de_lo_que_no_se_sigue_es_404(client):
    assert client.delete("/api/inversiones/watchlist/ALUA").status_code == 404


# ── Refresco de precio ────────────────────────────────────────────────────────

def test_refrescar_un_ticker(client, monkeypatch):
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precio_simbolo",
                        lambda db, s: (1500.0, "ARS"))

    item = client.post("/api/inversiones/watchlist/ALUA/precio").json()
    assert item["precio_actual"] == 1500.0


def test_alta_y_refresco_de_uno_no_bajan_los_paneles(client, monkeypatch):
    """Cotizar un solo símbolo por los ~9 paneles gastaría 9 llamadas del cupo en vez de 1."""
    def _boom(db):
        raise AssertionError("un alta no debería bajar la tanda de paneles")

    monkeypatch.setattr(market_data_precios.iol_client, "fetch_precios_paneles", _boom)
    assert client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"}).status_code == 201
    assert client.post("/api/inversiones/watchlist/ALUA/precio").status_code == 200


def test_refrescar_toda_la_watchlist(client):
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    client.post("/api/inversiones/watchlist", json={"ticker": "AAPL"})
    r = client.post("/api/inversiones/watchlist/precios")
    assert r.status_code == 200
    assert r.json()["actualizados"] == 2


def test_refrescar_lo_que_no_se_sigue_es_404(client):
    assert client.post("/api/inversiones/watchlist/ALUA/precio").status_code == 404


def test_no_recotiza_lo_que_esta_en_cartera(client, sesion):
    """Para un ticker en cartera el precio sale de `precios_instrumento`, que tiene serie real."""
    db = sesion()
    db.add(InstrumentoInversion(ticker="ALUA", nombre="Aluar", tipo_instrumento="Acción",
                                mercado="BCBA", moneda="ARS"))
    db.commit()
    db.close()

    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    assert client.post("/api/inversiones/watchlist/precios").json()["actualizados"] == 0

    db = sesion()
    assert db.query(PrecioWatchlist).count() == 0
    db.close()


# ── Serie en USD de un CEDEAR al darlo de alta ───────────────────────────────

def _yahoo_xlp(monkeypatch, llamadas=None):
    """Yahoo de mentira: AAPL cotiza en USD con ~5 meses de velas hasta ayer."""
    from datetime import timedelta

    hoy = date.today()

    def _info(ticker):
        if llamadas is not None:
            llamadas.append(("info", ticker))
        return {"moneda": "USD", "mercado": "NMS", "nombre": "Apple Inc."} if ticker == "AAPL" else None

    def _historico(simbolo, desde, hasta):
        if llamadas is not None:
            llamadas.append(("historico", simbolo))
        if simbolo != "AAPL":
            return None
        return [
            market_data_precios.BarraCruda(
                fecha=hoy - timedelta(days=150 - i), cierre=200.0 + i, apertura=199.0 + i,
                maximo=201.0 + i, minimo=198.0 + i, volumen=1e6,
            )
            for i in range(150)
        ]

    monkeypatch.setattr(market_data_precios.yahoo, "fetch_info", _info)
    monkeypatch.setattr(market_data_precios.yahoo, "fetch_historico_ohlcv", _historico)


def test_alta_de_un_cedear_trae_la_serie_en_usd_en_el_acto(client, sesion, monkeypatch):
    """Sin esperar al sync: un CEDEAR recién agregado ya se mira en dólares."""
    _yahoo_xlp(monkeypatch)
    item = client.post("/api/inversiones/watchlist", json={"ticker": "AAPL"}).json()

    assert item["variante_referencia"] == "subyacente"
    assert item["moneda_referencia"] == "USD"
    assert item["precio_referencia"] is not None
    s = sesion()
    estado = s.get(EstadoMarketDataTicker, "AAPL")
    assert estado.resolucion_estado == "ok" and estado.moneda_subyacente == "USD"
    barras = s.query(BarraOHLCV).filter(BarraOHLCV.ticker == "AAPL@SUB").all()
    assert len(barras) > 60 and {b.moneda for b in barras} == {"USD"}


def test_alta_de_un_cedear_con_objetivo_escribe_la_zona_en_usd(client, sesion, monkeypatch):
    """La zona se guarda después de bajar la serie en USD, así nace en la serie de referencia."""
    from app.database import ZonaPrecio

    _yahoo_xlp(monkeypatch)
    client.post("/api/inversiones/watchlist", json={"ticker": "AAPL", "objetivo": 250})
    zona = sesion().query(ZonaPrecio).filter(ZonaPrecio.ticker == "AAPL").one()
    assert (zona.variante, zona.moneda, float(zona.techo)) == ("subyacente", "USD", 250.0)


def test_alta_de_una_accion_local_no_llama_a_yahoo(client, monkeypatch):
    llamadas: list = []
    _yahoo_xlp(monkeypatch, llamadas)
    client.post("/api/inversiones/watchlist", json={"ticker": "ALUA"})
    assert llamadas == []


def test_alta_de_un_cedear_sobrevive_a_que_yahoo_falle(client, sesion):
    """Yahoo caído (el stub por default de conftest): el alta sale igual, en pesos."""
    r = client.post("/api/inversiones/watchlist", json={"ticker": "AAPL"})
    assert r.status_code == 201
    assert r.json()["variante_referencia"] == "local"
    assert sesion().get(EstadoMarketDataTicker, "AAPL").resolucion_estado == "sin_subyacente"


def test_el_boton_precio_completa_la_serie_en_usd_de_un_cedear(client, sesion, monkeypatch):
    """El alta fue con Yahoo caído; días después, "Precio" la reintenta sin esperar al sync."""
    from datetime import timedelta

    client.post("/api/inversiones/watchlist", json={"ticker": "AAPL"})
    s = sesion()
    s.get(EstadoMarketDataTicker, "AAPL").resolucion_intento = (
        date.today() - timedelta(days=market_data_precios._REINTENTO_RESOLUCION_CEDEAR_DIAS)
    )
    s.commit()

    _yahoo_xlp(monkeypatch)
    item = client.post("/api/inversiones/watchlist/AAPL/precio").json()
    assert item["variante_referencia"] == "subyacente"


def test_un_item_viejo_con_tipo_que_no_dice_cedear_se_resuelve_por_el_catalogo(entorno, sesion):
    """Una watchlist de la época del Sheet puede traer otro tipo: el catálogo manda."""
    from app.services import watchlist_analytics

    s = sesion()
    s.add(WatchlistItem(ticker="AAPL", nombre="Apple", tipo_instrumento="Acción",
                        mercado="BCBA", moneda="ARS", agregado_en=date.today()))
    s.add(WatchlistItem(ticker="ALUA", nombre="Aluar", tipo_instrumento="Acción",
                        mercado="BCBA", moneda="ARS", agregado_en=date.today()))
    s.commit()
    tipos = {i["ticker"]: i["tipo_instrumento"] for i in watchlist_analytics.items_para_market_data(s)}
    assert tipos == {"AAPL": "CEDEAR", "ALUA": "Acción"}


# ── Preparar el técnico desde el Centro de Decisiones ────────────────────────

PREPARAR = "/api/inversiones/decisiones/tecnico/{}/preparar"


def _velas_locales(monkeypatch, precio_base=27000.0, dias=300):
    """analisistecnico de mentira: velas del CEDEAR en pesos, en la misma unidad que el precio de IOL."""
    from datetime import timedelta

    hoy = date.today()
    pedidos = []

    def _historico(simbolo, desde, hasta):
        pedidos.append(simbolo)
        return [
            market_data_precios.BarraCruda(
                fecha=hoy - timedelta(days=dias - i), cierre=precio_base + i * 3, apertura=precio_base + i * 3 - 5,
                maximo=precio_base + i * 3 + 20, minimo=precio_base + i * 3 - 20, volumen=1e5,
            )
            for i in range(dias - 1)
        ]

    monkeypatch.setattr(market_data_precios.analisistecnico, "fetch_historico_ohlcv", _historico)
    return pedidos


def test_preparar_da_de_alta_el_ticker_y_baja_las_velas_locales_y_del_subyacente(client, sesion, monkeypatch):
    _yahoo_xlp(monkeypatch)
    pedidos = _velas_locales(monkeypatch)

    r = client.post(PREPARAR.format("AAPL"))

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ok" and cuerpo["con_series"] and cuerpo["agregado_a_watchlist"]
    assert pedidos == ["AAPL:CEDEAR"]       # la serie local del CEDEAR en pesos, no la acción del Nasdaq
    s = sesion()
    assert s.get(WatchlistItem, "AAPL") is not None
    assert s.query(BarraOHLCV).filter(BarraOHLCV.ticker == "AAPL").count() > 200
    assert s.query(BarraOHLCV).filter(BarraOHLCV.ticker == "AAPL@SUB").count() > 60


def test_preparar_un_ticker_que_ya_esta_en_la_watchlist_no_lo_duplica_y_le_baja_las_velas(client, sesion, monkeypatch):
    _yahoo_xlp(monkeypatch)
    sin_velas = lambda s, d, h: None     # el alta sin sync: sólo precio y subyacente
    monkeypatch.setattr(market_data_precios.analisistecnico, "fetch_historico_ohlcv", sin_velas)
    assert client.post("/api/inversiones/watchlist", json={"ticker": "AAPL"}).status_code == 201
    assert sesion().query(BarraOHLCV).filter(BarraOHLCV.ticker == "AAPL").count() == 0
    _velas_locales(monkeypatch)

    cuerpo = client.post(PREPARAR.format("AAPL")).json()

    assert cuerpo["estado"] == "ok" and not cuerpo["agregado_a_watchlist"]
    s = sesion()
    assert s.query(WatchlistItem).filter(WatchlistItem.ticker == "AAPL").count() == 1
    assert s.query(BarraOHLCV).filter(BarraOHLCV.ticker == "AAPL").count() > 200


def test_preparar_un_ticker_fuera_del_catalogo_no_agrega_nada(client, sesion):
    cuerpo = client.post(PREPARAR.format("ZZZZ")).json()

    assert cuerpo["estado"] == "fuera_de_catalogo" and not cuerpo["con_series"]
    assert sesion().query(WatchlistItem).count() == 0


def test_preparar_con_las_fuentes_caidas_deja_el_ticker_seguido_pero_sin_series(client, sesion, monkeypatch):
    monkeypatch.setattr(market_data_precios.analisistecnico, "fetch_historico_ohlcv", lambda s, d, h: None)
    monkeypatch.setattr(market_data_precios.iol_client, "fetch_historico_ohlcv", lambda db, t, d, h: None)
    monkeypatch.setattr(market_data_precios.yahoo, "fetch_info", lambda t: None)
    monkeypatch.setattr(market_data_precios.yahoo, "fetch_historico_ohlcv", lambda s, d, h: None)

    cuerpo = client.post(PREPARAR.format("ALUA")).json()

    assert cuerpo["estado"] == "sin_series" and not cuerpo["con_series"] and cuerpo["agregado_a_watchlist"]
    assert sesion().get(WatchlistItem, "ALUA") is not None


def test_preparar_un_ticker_con_formato_invalido_es_422(client):
    assert client.post(PREPARAR.format("no valido!")).status_code == 422
