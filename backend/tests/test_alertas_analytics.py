"""Tests del adaptador de alertas: DB → motor → canal, y la persistencia del estado.

El canal está stubeado; lo que se verifica acá es que el estado guardado haga que un cruce avise
una sola vez, y que un envío fallido se reintente sin volver a tratar el cruce como nuevo.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    AlertaPrecio, Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento,
    PrecioWatchlist, WatchlistItem,
)
from app.services import alertas_analytics, alertas_engine
from app.services.notificaciones import telegram


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def canal(monkeypatch):
    """Canal falso: registra los mensajes y permite forzar un fallo de entrega."""
    estado = {"mensajes": [], "entrega": True}

    def enviar(texto):
        estado["mensajes"].append(texto)
        return (True, None) if estado["entrega"] else (False, "canal caído")

    monkeypatch.setattr(telegram, "enviar", enviar)
    return estado


def _posicion(db, *, stop_loss=None, objetivo=None, precio_actual=100.0, ticker="AL30"):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=f"Bono {ticker}", tipo_instrumento="Bono", mercado="TEST",
        moneda="USD",
        stop_loss_modo="Fijo" if stop_loss is not None else None, stop_loss_valor=stop_loss,
        objetivo_modo="Fijo" if objetivo is not None else None, objetivo_valor=objetivo,
    ))
    db.add(MovimientoInversion(
        fecha=date.today() - timedelta(days=30), cartera="Principal", ticker=ticker,
        tipo_movimiento="compra", cantidad=10.0, precio=100.0, moneda="USD", comision=0.0,
    ))
    db.add(PrecioInstrumento(
        fecha=date.today(), ticker=ticker, precio=precio_actual, moneda="USD", fuente="sheet",
    ))
    db.commit()


def _watchlist(db, *, objetivo, precio_actual, ticker="MSFT"):
    db.add(WatchlistItem(
        ticker=ticker, nombre="Microsoft", tipo_instrumento="CEDEAR", mercado="BCBA",
        moneda="ARS", objetivo=objetivo,
    ))
    db.add(PrecioWatchlist(
        ticker=ticker, fecha=date.today(), precio=precio_actual, moneda="ARS", fuente="iol",
    ))
    db.commit()


# --- Ciclo de vida de una alerta ---------------------------------------------------------------

def test_stop_loss_cruzado_avisa_una_sola_vez(db, canal):
    _posicion(db, stop_loss=96.0, precio_actual=95.0)

    primera = alertas_analytics.evaluar_y_notificar(db)
    assert primera["nuevas"] == 1
    assert primera["entregado"] is True
    assert len(canal["mensajes"]) == 1
    assert "AL30" in canal["mensajes"][0]

    segunda = alertas_analytics.evaluar_y_notificar(db)
    assert segunda["nuevas"] == 0
    assert segunda["pendientes_de_entrega"] == 0
    assert len(canal["mensajes"]) == 1  # no se repitió


def test_nivel_no_cruzado_no_avisa_pero_queda_armado(db, canal):
    _posicion(db, stop_loss=50.0, precio_actual=100.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 0
    assert canal["mensajes"] == []
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.estado == alertas_engine.ESTADO_ARMADA


def test_rearmado_permite_avisar_de_nuevo(db, canal):
    _posicion(db, stop_loss=96.0, precio_actual=95.0)
    alertas_analytics.evaluar_y_notificar(db)
    assert len(canal["mensajes"]) == 1

    # El precio se recupera bien por encima del nivel: la alerta vuelve a quedar armada.
    db.query(PrecioInstrumento).delete()
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=110.0, moneda="USD", fuente="sheet"))
    db.commit()
    alertas_analytics.evaluar_y_notificar(db)
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.estado == alertas_engine.ESTADO_ARMADA
    assert len(canal["mensajes"]) == 1  # volver al lado normal no es noticia

    # Y vuelve a cruzar: avisa otra vez.
    db.query(PrecioInstrumento).delete()
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=94.0, moneda="USD", fuente="sheet"))
    db.commit()
    alertas_analytics.evaluar_y_notificar(db)
    assert len(canal["mensajes"]) == 2


def test_oscilar_dentro_de_la_banda_no_genera_un_segundo_aviso(db, canal):
    """El caso que haría inutilizable la función: el precio rondando el nivel."""
    _posicion(db, stop_loss=100.0, precio_actual=99.5)
    alertas_analytics.evaluar_y_notificar(db)

    for precio in (100.5, 99.8, 100.4, 99.9):
        db.query(PrecioInstrumento).delete()
        db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=precio,
                                 moneda="USD", fuente="sheet"))
        db.commit()
        alertas_analytics.evaluar_y_notificar(db)

    assert len(canal["mensajes"]) == 1


# --- Entrega fallida y reintento ---------------------------------------------------------------

def test_entrega_fallida_queda_pendiente_y_se_reintenta(db, canal):
    _posicion(db, stop_loss=96.0, precio_actual=95.0)
    canal["entrega"] = False

    primera = alertas_analytics.evaluar_y_notificar(db)
    assert primera["nuevas"] == 1
    assert primera["entregado"] is False
    assert primera["motivo"] == "canal caído"
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.estado == alertas_engine.ESTADO_DISPARADA
    assert fila.entregada == 0

    # Con el canal de vuelta, la corrida siguiente reintenta sin re-disparar el cruce.
    canal["entrega"] = True
    segunda = alertas_analytics.evaluar_y_notificar(db)
    assert segunda["nuevas"] == 0
    assert segunda["pendientes_de_entrega"] == 1
    assert segunda["entregado"] is True
    db.expire_all()
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.entregada == 1


def test_sin_notificar_persiste_el_estado_y_no_manda_nada(db, canal):
    """Sirve para sembrar el estado inicial sin una andanada de avisos la primera vez."""
    _posicion(db, stop_loss=96.0, precio_actual=95.0)

    resumen = alertas_analytics.evaluar_y_notificar(db, notificar=False)

    assert resumen["nuevas"] == 1
    assert canal["mensajes"] == []
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.estado == alertas_engine.ESTADO_DISPARADA
    assert fila.entregada == 0


# --- Watchlist y objetivo ----------------------------------------------------------------------

def test_watchlist_en_zona_de_compra_avisa(db, canal):
    _watchlist(db, objetivo=25000.0, precio_actual=24000.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 1
    assert "Zona de compra" in canal["mensajes"][0]
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_COMPRA_ZONA).one()
    assert fila.cartera == ""  # la watchlist no pertenece a ninguna cartera


def test_objetivo_de_venta_alcanzado_avisa(db, canal):
    _posicion(db, objetivo=120.0, precio_actual=125.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 1
    assert "Objetivo alcanzado" in canal["mensajes"][0]


def test_un_solo_mensaje_con_todos_los_cruces(db, canal):
    """Diez cruces el mismo día son diez notificaciones que el usuario descarta sin leer."""
    _posicion(db, stop_loss=96.0, precio_actual=95.0, ticker="AL30")
    _watchlist(db, objetivo=25000.0, precio_actual=24000.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 2
    assert len(canal["mensajes"]) == 1
    assert "AL30" in canal["mensajes"][0] and "MSFT" in canal["mensajes"][0]


# --- Lecturas para la UI -----------------------------------------------------------------------

def test_listar_devuelve_solo_los_emitidos(db, canal):
    _posicion(db, stop_loss=96.0, objetivo=200.0, precio_actual=95.0)

    alertas_analytics.evaluar_y_notificar(db)
    historial = alertas_analytics.listar(db)

    # El stop-loss cruzó; el objetivo quedó armado y nunca se emitió.
    assert [a["tipo"] for a in historial] == [alertas_engine.TIPO_STOP_LOSS]
    assert historial[0]["etiqueta"] == "Stop-loss disparado"
    assert historial[0]["nombre"] == "Bono AL30"
    assert historial[0]["entregada"] is True


def test_estado_configuracion_reporta_lo_que_falta(db, canal, monkeypatch):
    monkeypatch.setenv("ALERTAS_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    _posicion(db, stop_loss=50.0, precio_actual=100.0)
    alertas_analytics.evaluar_y_notificar(db)

    estado = alertas_analytics.estado_configuracion(db)

    assert estado["habilitadas"] is False
    assert estado["configurado"] is False
    assert estado["canal"] == "telegram"
    assert estado["niveles_vigilados"] == 1
    assert estado["ultimo_aviso"] is None


# --- Endpoints ---------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    """TestClient con DB en memoria y una posición cuyo stop-loss ya está cruzado."""
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool

    from app.database import get_db
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = Session(engine)
    _posicion(sesion, stop_loss=96.0, precio_actual=95.0)
    sesion.close()

    def override():
        s = Session(engine)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_estado_alertas(client):
    r = client.get("/api/inversiones/alertas/estado")
    assert r.status_code == 200
    assert r.json()["canal"] == "telegram"


def test_endpoint_evaluar_sin_notificar_no_manda_nada(client, canal):
    r = client.post("/api/inversiones/alertas/evaluar", params={"notificar": "false"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["nuevas"] == 1
    assert cuerpo["entregado"] is False
    assert canal["mensajes"] == []


def test_endpoint_evaluar_notifica_y_queda_en_el_historial(client, canal):
    r = client.post("/api/inversiones/alertas/evaluar")
    assert r.status_code == 200
    assert r.json()["entregado"] is True

    historial = client.get("/api/inversiones/alertas")
    assert historial.status_code == 200
    filas = historial.json()
    assert [f["ticker"] for f in filas] == ["AL30"]
    assert filas[0]["etiqueta"] == "Stop-loss disparado"
    assert filas[0]["entregada"] is True


def test_endpoint_probar_usa_el_canal(client, canal):
    r = client.post("/api/inversiones/alertas/probar")
    assert r.status_code == 200
    assert r.json()["entregado"] is True
    assert len(canal["mensajes"]) == 1
    assert "Prueba" in canal["mensajes"][0]
