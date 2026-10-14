"""Zonas de compra y de venta: cálculo puro, validación, escritura y endpoints.

El nivel de compra dejó de ser el escalar `watchlist.objetivo` y pasó a ser el **techo de la zona
de compra** (`services/zonas_precio.py`), que es lo que se dibuja y se arrastra en el gráfico.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import (
    AlertaPrecio, Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento,
    PrecioWatchlist, WatchlistItem, ZonaPrecio, get_db, migrar_objetivo_watchlist_a_zonas,
)
from app.main import app
from app.services import alertas_engine, watchlist_analytics, zonas_precio as zp


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)(), engine


def _zona(tipo=zp.TIPO_COMPRA, piso=None, techo=None, activa=True, variante="local"):
    return zp.Zona(tipo=tipo, piso=piso, techo=techo, activa=activa, variante=variante)


# ── Cálculo: qué borde dispara ───────────────────────────────────────────────

def test_la_zona_de_compra_dispara_en_el_techo():
    """Se cruza hacia abajo: el techo es el borde de entrada."""
    zona = _zona(piso=1150.0, techo=1250.0)
    nivel, pct, en_zona = zp.estado_de_zona(zona, 1300.0)
    assert nivel == 1250.0          # el piso no dispara
    assert en_zona is False
    assert pct == pytest.approx((1250.0 - 1300.0) / 1300.0)   # negativo: todavía caro

    _, pct, en_zona = zp.estado_de_zona(zona, 1200.0)
    assert en_zona is True
    assert pct > 0


def test_la_zona_de_venta_dispara_en_el_piso():
    """Se cruza hacia arriba: el piso es el borde de entrada."""
    zona = _zona(tipo=zp.TIPO_VENTA, piso=2000.0, techo=2200.0)
    nivel, _, en_zona = zp.estado_de_zona(zona, 1900.0)
    assert nivel == 2000.0
    assert en_zona is False

    _, _, en_zona = zp.estado_de_zona(zona, 2050.0)
    assert en_zona is True


def test_por_debajo_del_piso_sigue_en_zona_de_compra():
    """Un precio que se desplomó por debajo de la banda está *más* adentro de la oportunidad, no
    afuera. Es lo que hace que el badge de la watchlist signifique lo mismo que antes."""
    _, _, en_zona = zp.estado_de_zona(_zona(piso=1150.0, techo=1250.0), 900.0)
    assert en_zona is True


def test_zona_abierta_de_un_lado():
    """Sin piso es exactamente lo que significaba el `Objetivo` escalar: "compro por debajo de X"."""
    _, _, en_zona = zp.estado_de_zona(_zona(techo=1250.0), 1200.0)
    assert en_zona is True
    # Abierta justo del lado que dispara: no se puede decir nada.
    assert zp.estado_de_zona(_zona(piso=1150.0), 1200.0) == (None, None, None)


def test_sin_zona_sin_precio_o_apagada_no_se_puede_decir():
    assert zp.estado_de_zona(None, 1200.0) == (None, None, None)
    assert zp.estado_de_zona(_zona(techo=1250.0), None) == (None, None, None)
    assert zp.estado_de_zona(_zona(techo=1250.0, activa=False), 1200.0) == (None, None, None)


def test_el_borde_que_no_dispara_es_informativo():
    """Se dibuja y se escribe en el aviso, pero no decide nada — en particular no re-arma la
    alerta: si a 900 la zona de compra 1150-1250 sigue cruzada, salir por abajo no es un evento."""
    compra = _zona(piso=1150.0, techo=1250.0)
    assert compra.borde_disparo == 1250.0
    assert compra.borde_informativo == 1150.0

    venta = _zona(tipo=zp.TIPO_VENTA, piso=2000.0, techo=2200.0)
    assert venta.borde_disparo == 2000.0
    assert venta.borde_informativo == 2200.0


# ── Validación ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,codigo", [
    ({"piso": None, "techo": None}, "zona_vacia"),
    ({"piso": 1250.0, "techo": 1150.0}, "bordes_invertidos"),
    ({"piso": 1250.0, "techo": 1250.0}, "bordes_invertidos"),
    ({"techo": 0}, "borde_no_positivo"),     # un borde en 0 no es "sin borde"
    ({"techo": -5.0}, "borde_no_positivo"),
    ({"techo": 1250.0, "variante": "mep"}, "variante_invalida"),
])
def test_validacion_rechaza(entrada, codigo):
    db, _ = _db()
    _, error = zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: entrada})
    assert error == codigo
    assert zp.MENSAJE_ERROR[error]


def test_valida_todo_antes_de_escribir_nada():
    """Un PUT con las dos zonas donde una está mal no deja la otra guardada a medias."""
    db, _ = _db()
    _, error = zp.aplicar_cambios(db, "AAPL", {
        zp.TIPO_COMPRA: {"techo": 1250.0},
        zp.TIPO_VENTA: {"piso": 2200.0, "techo": 2000.0},   # invertida
    })
    assert error == "bordes_invertidos"
    assert db.query(ZonaPrecio).count() == 0


def test_sin_cambios():
    db, _ = _db()
    _, error = zp.aplicar_cambios(db, "AAPL", {})
    assert error == "sin_cambios"


# ── Escritura y lectura ──────────────────────────────────────────────────────

def test_guarda_lee_y_edita_parcial():
    db, _ = _db()
    zonas, error = zp.aplicar_cambios(db, "AAPL", {
        zp.TIPO_COMPRA: {"piso": 1150.0, "techo": 1250.0, "moneda": "ars"},
        zp.TIPO_VENTA: {"piso": 2000.0},
    })
    assert error is None
    assert zonas.compra.techo == 1250.0
    assert zonas.compra.moneda == "ARS"        # normalizada
    assert zonas.venta.piso == 2000.0

    # Un cambio parcial no toca la otra zona.
    zonas, _ = zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1300.0}})
    assert zonas.compra.techo == 1300.0
    assert zonas.compra.piso is None           # el upsert reemplaza la zona entera
    assert zonas.venta.piso == 2000.0          # intacta

    # `None` explícito borra.
    zonas, _ = zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: None})
    assert zonas.compra is None
    assert zonas.venta is not None


def test_una_sola_zona_por_ticker_y_tipo():
    db, _ = _db()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1250.0}})
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1300.0}})
    assert db.query(ZonaPrecio).filter(ZonaPrecio.tipo == "compra").count() == 1


def test_mapa_zonas_en_una_consulta():
    db, _ = _db()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1250.0}})
    zp.aplicar_cambios(db, "MSFT", {zp.TIPO_VENTA: {"piso": 500.0, "variante": "subyacente"}})
    mapa = zp.mapa_zonas(db)
    assert mapa["AAPL"].compra.techo == 1250.0
    assert mapa["AAPL"].venta is None
    assert mapa["MSFT"].venta.variante == "subyacente"
    assert "GGAL" not in mapa


# ── Re-armado de la alerta al mover la zona ──────────────────────────────────

def test_mover_la_zona_rearma_su_alerta():
    """Sin esto, mover el techo dejaría la alerta silenciada por un cruce del nivel anterior."""
    db, _ = _db()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1250.0}})
    db.add(AlertaPrecio(ticker="AAPL", tipo=alertas_engine.TIPO_COMPRA_ZONA, cartera="",
                        estado=alertas_engine.ESTADO_DISPARADA, nivel=1250.0, entregada=1))
    db.commit()

    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1100.0}})
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.ticker == "AAPL").one()
    assert fila.estado == alertas_engine.ESTADO_ARMADA


def test_reescribir_la_misma_zona_no_rearma():
    """Un PUT que no cambia nada no tiene por qué resucitar un aviso ya emitido."""
    db, _ = _db()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1250.0}})
    db.add(AlertaPrecio(ticker="AAPL", tipo=alertas_engine.TIPO_COMPRA_ZONA, cartera="",
                        estado=alertas_engine.ESTADO_DISPARADA, nivel=1250.0, entregada=1))
    db.commit()

    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 1250.0}})
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.ticker == "AAPL").one()
    assert fila.estado == alertas_engine.ESTADO_DISPARADA


def test_la_zona_de_venta_rearma_su_propio_tipo():
    db, _ = _db()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_VENTA: {"piso": 2000.0}})
    for tipo in (alertas_engine.TIPO_COMPRA_ZONA, alertas_engine.TIPO_VENTA_ZONA):
        db.add(AlertaPrecio(ticker="AAPL", tipo=tipo, cartera="",
                            estado=alertas_engine.ESTADO_DISPARADA, entregada=1))
    db.commit()

    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_VENTA: {"piso": 2100.0}})
    por_tipo = {f.tipo: f.estado for f in db.query(AlertaPrecio).all()}
    assert por_tipo[alertas_engine.TIPO_VENTA_ZONA] == alertas_engine.ESTADO_ARMADA
    assert por_tipo[alertas_engine.TIPO_COMPRA_ZONA] == alertas_engine.ESTADO_DISPARADA


# ── Migración del `objetivo` escalar ─────────────────────────────────────────

def test_migracion_convierte_el_objetivo_en_zona_de_compra():
    db, engine = _db()
    db.add(WatchlistItem(ticker="AAPL", nombre="Aple", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", objetivo=4900.0,
                         agregado_en=date.today()))
    db.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion",
                         mercado="BCBA", moneda="ARS", objetivo=None,
                         agregado_en=date.today()))
    db.commit()

    with engine.connect() as conn:
        migrar_objetivo_watchlist_a_zonas(conn)

    db.expire_all()
    zonas = zp.zonas_de_ticker(db, "AAPL")
    assert zonas.compra.techo == 4900.0
    assert zonas.compra.piso is None          # abierta hacia abajo: es lo que era el escalar
    assert zonas.compra.variante == "local"
    assert zonas.compra.moneda == "ARS"
    # El ticker sin objetivo no inventa zona, y la columna queda vacía.
    assert zp.zonas_de_ticker(db, "GGAL").compra is None
    assert db.get(WatchlistItem, "AAPL").objetivo is None


def test_migracion_es_idempotente_y_no_pisa_una_zona_existente():
    db, engine = _db()
    db.add(WatchlistItem(ticker="AAPL", nombre="Aple", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", objetivo=4900.0,
                         agregado_en=date.today()))
    db.commit()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"piso": 4000.0, "techo": 4500.0}})

    with engine.connect() as conn:
        migrar_objetivo_watchlist_a_zonas(conn)
        migrar_objetivo_watchlist_a_zonas(conn)

    db.expire_all()
    assert db.query(ZonaPrecio).count() == 1
    assert zp.zonas_de_ticker(db, "AAPL").compra.techo == 4500.0   # la del usuario, no el escalar


# ── La watchlist lee la zona ─────────────────────────────────────────────────

def _seguido(db, ticker="AAPL", precio=5300.0):
    db.add(WatchlistItem(ticker=ticker, nombre=ticker, tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", agregado_en=date.today()))
    db.add(PrecioWatchlist(ticker=ticker, fecha=date.today(), precio=precio,
                           moneda="ARS", fuente="api"))
    db.commit()


def test_get_watchlist_usa_el_techo_de_la_zona():
    db, _ = _db()
    _seguido(db, precio=5300.0)
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"piso": 4500.0, "techo": 4900.0}})

    fila = watchlist_analytics.get_watchlist(db)[0]
    assert fila["precio_objetivo"] == 4900.0
    assert fila["en_zona"] is False
    assert fila["zona_compra"]["piso"] == 4500.0
    assert fila["zona_compra"]["techo"] == 4900.0
    assert fila["zona_venta"] is None


def test_get_watchlist_no_compara_una_zona_en_usd_contra_el_precio_local():
    """`precio_actual` es el CEDEAR en ARS; una zona dibujada sobre el subyacente está en USD del
    mercado de origen. Compararlos daría una distancia sin sentido (y un aviso falso)."""
    db, _ = _db()
    _seguido(db, precio=26000.0)
    zp.aplicar_cambios(db, "AAPL", {
        zp.TIPO_COMPRA: {"techo": 180.0, "variante": "subyacente", "moneda": "USD"},
    })

    fila = watchlist_analytics.get_watchlist(db)[0]
    assert fila["precio_objetivo"] is None
    assert fila["pct_a_objetivo"] is None
    assert fila["en_zona"] is None
    # La zona viaja igual: el gráfico la dibuja sobre su propia serie.
    assert fila["zona_compra"]["techo"] == 180.0
    assert fila["zona_compra"]["variante"] == "subyacente"


def test_actualizar_watchlist_con_objetivo_escribe_la_zona():
    """El endpoint de watchlist sigue aceptando el escalar como atajo ("comprar por debajo de X");
    lo que escribe es el techo de la zona."""
    db, _ = _db()
    _seguido(db)
    watchlist_analytics.actualizar(db, "AAPL", {"objetivo": 4900.0})
    assert zp.zonas_de_ticker(db, "AAPL").compra.techo == 4900.0

    watchlist_analytics.actualizar(db, "AAPL", {"objetivo": None})
    assert zp.zonas_de_ticker(db, "AAPL").compra is None


def test_dar_de_baja_un_ticker_seguido_se_lleva_sus_zonas():
    db, _ = _db()
    _seguido(db)
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_COMPRA: {"techo": 4900.0}})

    watchlist_analytics.eliminar(db, "AAPL")
    db.commit()
    assert db.query(ZonaPrecio).count() == 0


def test_dar_de_baja_un_ticker_en_cartera_conserva_sus_zonas():
    """Si se posee, las zonas siguen siendo las de la posición: el gráfico las sigue dibujando."""
    db, _ = _db()
    _seguido(db)
    db.add(InstrumentoInversion(ticker="AAPL", nombre="Aple", tipo_instrumento="CEDEAR",
                                mercado="BCBA", moneda="ARS"))
    db.commit()
    zp.aplicar_cambios(db, "AAPL", {zp.TIPO_VENTA: {"piso": 6000.0}})

    watchlist_analytics.eliminar(db, "AAPL")
    db.commit()
    assert db.query(ZonaPrecio).count() == 1


# ── Endpoints ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    db.add(WatchlistItem(ticker="AAPL", nombre="Aple", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", agregado_en=date.today()))
    db.add(InstrumentoInversion(ticker="AL30", nombre="Bono", tipo_instrumento="Bono",
                                mercado="MERVAL", moneda="USD",
                                objetivo_modo="Fijo", objetivo_valor=120.0,
                                stop_loss_modo="Fijo", stop_loss_valor=80.0))
    db.add(MovimientoInversion(fecha=date.today() - timedelta(days=30), cartera="P1",
                               ticker="AL30", tipo_movimiento="compra", cantidad=10,
                               precio=100.0, moneda="USD", comision=0))
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=105.0,
                             moneda="USD", fuente="sheet"))
    db.commit()
    db.close()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_zonas_vacias_de_un_ticker_de_watchlist(client):
    r = client.get("/api/inversiones/tecnico/AAPL/zonas")
    assert r.status_code == 200
    assert r.json() == {"ticker": "AAPL", "compra": None, "venta": None,
                        "nivel_stop_loss": None, "nivel_objetivo": None}


def test_endpoint_guarda_y_devuelve_la_zona(client):
    r = client.put("/api/inversiones/tecnico/AAPL/zonas",
                   json={"compra": {"piso": 4500, "techo": 4900, "moneda": "ARS"}})
    assert r.status_code == 200
    assert r.json()["compra"]["techo"] == 4900
    assert r.json()["venta"] is None

    assert client.get("/api/inversiones/tecnico/AAPL/zonas").json()["compra"]["piso"] == 4500


def test_endpoint_informa_los_niveles_de_la_posicion(client):
    """Están para dibujarlos y para no poner la zona de venta encima del objetivo sin darse cuenta;
    se editan en el detalle del ticker, no acá."""
    r = client.get("/api/inversiones/tecnico/AL30/zonas")
    assert r.status_code == 200
    assert r.json()["nivel_objetivo"] == 120.0
    assert r.json()["nivel_stop_loss"] == 80.0


def test_endpoint_rechaza_una_zona_invalida(client):
    r = client.put("/api/inversiones/tecnico/AAPL/zonas",
                   json={"compra": {"piso": 4900, "techo": 4500}})
    assert r.status_code == 422
    assert "piso" in r.json()["detail"]


def test_endpoint_borra_una_zona(client):
    client.put("/api/inversiones/tecnico/AAPL/zonas", json={"compra": {"techo": 4900}})
    r = client.delete("/api/inversiones/tecnico/AAPL/zonas/compra")
    assert r.status_code == 200
    assert r.json()["compra"] is None


def test_endpoint_rechaza_un_tipo_desconocido(client):
    assert client.delete("/api/inversiones/tecnico/AAPL/zonas/lateral").status_code == 422


def test_endpoint_404_para_un_ticker_fuera_del_universo(client):
    assert client.get("/api/inversiones/tecnico/NOEXISTE/zonas").status_code == 404
    r = client.put("/api/inversiones/tecnico/NOEXISTE/zonas", json={"compra": {"techo": 1}})
    assert r.status_code == 404
