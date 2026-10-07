"""Tests del adaptador de alertas: DB → motor → canal, y la persistencia del estado.

El canal está stubeado; lo que se verifica acá es que el estado guardado haga que un cruce avise
una sola vez, y que un envío fallido se reintente sin volver a tratar el cruce como nuevo.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    AlertaPrecio, Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento,
    PrecioWatchlist, WatchlistItem,
)
from app.services import alertas_analytics, alertas_engine, avisos_config
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
    estado = {"mensajes": [], "modos": [], "entrega": True}

    def enviar(texto, parse_mode=None):
        estado["mensajes"].append(texto)
        estado["modos"].append(parse_mode)
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


def test_sin_notificar_siembra_el_estado_y_la_corrida_siguiente_no_manda_la_andanada(db, canal):
    """Sembrar el estado inicial sin una andanada de avisos la primera vez.

    Antes esto no funcionaba: la fila quedaba `entregada=0` y la corrida siguiente la levantaba
    como pendiente de entrega y mandaba el aviso igual, así que la receta documentada para la
    puesta en marcha no servía para nada.
    """
    _posicion(db, stop_loss=96.0, precio_actual=95.0)

    resumen = alertas_analytics.evaluar_y_notificar(db, notificar=False)

    assert resumen["nuevas"] == 1
    assert canal["mensajes"] == []
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.estado == alertas_engine.ESTADO_DISPARADA
    assert fila.entregada == 1
    assert fila.emitida_en is None  # no se emitió: no va al historial

    segunda = alertas_analytics.evaluar_y_notificar(db)
    assert segunda["pendientes_de_entrega"] == 0
    assert canal["mensajes"] == []
    assert alertas_analytics.listar(db) == []


# --- Watchlist y objetivo ----------------------------------------------------------------------

def test_watchlist_en_zona_de_compra_avisa(db, canal):
    _watchlist(db, objetivo=25000.0, precio_actual=24000.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 1
    assert "OPORTUNIDAD DE COMPRA" in canal["mensajes"][0]
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_COMPRA_ZONA).one()
    assert fila.cartera == ""  # la watchlist no pertenece a ninguna cartera


def test_objetivo_de_venta_alcanzado_avisa(db, canal):
    _posicion(db, objetivo=120.0, precio_actual=125.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 1
    assert "OBJETIVO ALCANZADO" in canal["mensajes"][0]


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


# --- Contexto del aviso y reintento ------------------------------------------------------------

def test_el_aviso_dice_cartera_tenencia_y_resultado(db, canal):
    _posicion(db, stop_loss=96.0, precio_actual=95.0)

    alertas_analytics.evaluar_y_notificar(db)

    mensaje = canal["mensajes"][0]
    assert "cartera Principal" in mensaje
    assert "10 un." in mensaje and "PPC" in mensaje
    # Y el contexto quedó persistido, que es lo que hace idéntico al reintento.
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.detalle["cantidad"] == 10.0
    assert fila.detalle["origen"] == alertas_engine.ORIGEN_CARTERA


def test_el_mensaje_se_manda_con_formato_html(db, canal):
    _posicion(db, stop_loss=96.0, precio_actual=95.0)
    alertas_analytics.evaluar_y_notificar(db)
    assert canal["modos"] == ["HTML"]


def test_el_reintento_manda_exactamente_el_mismo_texto(db, canal):
    """Si el reintento se armara con menos contexto, el mismo cruce avisaría dos cosas distintas."""
    _posicion(db, stop_loss=96.0, precio_actual=95.0)
    canal["entrega"] = False
    alertas_analytics.evaluar_y_notificar(db)
    primero = canal["mensajes"][0]

    canal["entrega"] = True
    alertas_analytics.evaluar_y_notificar(db)

    assert canal["mensajes"][1] == primero


def test_una_fila_vieja_con_detalle_minimo_se_reintenta_sin_explotar(db, canal):
    """El estado de la DB el día del deploy: `detalle` con sólo el nombre."""
    db.add(AlertaPrecio(
        ticker="AL30", tipo=alertas_engine.TIPO_STOP_LOSS, cartera="Principal",
        estado=alertas_engine.ESTADO_DISPARADA, nivel=96.0, precio_disparo=95.0, moneda="USD",
        entregada=0, detalle={"nombre": "Bono AL30"},
    ))
    db.commit()

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["pendientes_de_entrega"] == 1
    assert resumen["entregado"] is True
    assert "AL30" in canal["mensajes"][0]


# --- Interruptores de los tipos de nivel -------------------------------------------------------

def test_un_tipo_apagado_no_manda_pero_sigue_el_estado(db, canal):
    """Y lo importante: prenderlo después **no** dispara el cruce que ya pasó."""
    _posicion(db, stop_loss=96.0, precio_actual=95.0)
    avisos_config.actualizar(db, avisar_stop_loss=False)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 1
    assert resumen["silenciadas"] == 1
    assert canal["mensajes"] == []
    fila = db.query(AlertaPrecio).filter(AlertaPrecio.tipo == alertas_engine.TIPO_STOP_LOSS).one()
    assert fila.estado == alertas_engine.ESTADO_DISPARADA
    assert fila.entregada == 1
    assert fila.emitida_en is None  # no se emitió: no va al historial
    assert alertas_analytics.listar(db) == []

    avisos_config.actualizar(db, avisar_stop_loss=True)
    segunda = alertas_analytics.evaluar_y_notificar(db)
    assert segunda["nuevas"] == 0
    assert canal["mensajes"] == []


def test_apagar_un_tipo_no_afecta_a_los_otros(db, canal):
    _posicion(db, stop_loss=96.0, precio_actual=95.0, ticker="AL30")
    _watchlist(db, objetivo=25000.0, precio_actual=24000.0)
    avisos_config.actualizar(db, avisar_stop_loss=False)

    alertas_analytics.evaluar_y_notificar(db)

    assert len(canal["mensajes"]) == 1
    assert "MSFT" in canal["mensajes"][0]
    assert "AL30" not in canal["mensajes"][0]


def test_los_tres_interruptores_arrancan_prendidos(db):
    """El default tiene que ser el comportamiento previo a que la tabla existiera."""
    assert avisos_config.tipos_habilitados(db) == set(alertas_engine.TIPOS)


# --- Señales de estrategia ---------------------------------------------------------------------

def _estrategia(db, *, nombre="Cruce de medias", compra=False, venta=False):
    from app.database import EstrategiaTecnica
    ahora = datetime.utcnow()
    e = EstrategiaTecnica(
        nombre=nombre, definicion={"entrada": {}}, variante="local",
        notificar_compra=1 if compra else 0, notificar_venta=1 if venta else 0,
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _senal(estrategia, *, ticker="AL30", tipo="compra", fecha=None, precio=95.0):
    return {
        "ticker": ticker, "estrategia_id": estrategia.id,
        "estrategia_nombre": estrategia.nombre, "tipo": tipo,
        "fecha": fecha or date.today(), "precio": precio, "motivo": "entrada",
        "barras_desde": 0, "variante": "local", "moneda": "USD",
    }


def _stub_senales(monkeypatch, filas):
    """Reemplaza `senales_recientes` y registra con qué se la llamó."""
    llamadas = []

    def fake(db, max_antiguedad_barras=5, tickers=(), estrategia_ids=()):
        llamadas.append({"antiguedad": max_antiguedad_barras, "ids": estrategia_ids})
        return list(filas)

    monkeypatch.setattr(alertas_analytics.estrategias_analytics, "senales_recientes", fake)
    return llamadas


def test_una_senal_habilitada_avisa_una_sola_vez(db, canal, monkeypatch):
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia)])

    primera = alertas_analytics.evaluar_y_notificar(db)
    assert primera["senales_nuevas"] == 1
    assert "SEÑAL DE COMPRA" in canal["mensajes"][0]
    assert "Cruce de medias" in canal["mensajes"][0]

    segunda = alertas_analytics.evaluar_y_notificar(db)
    assert segunda["senales_nuevas"] == 0
    assert len(canal["mensajes"]) == 1


def test_una_barra_nueva_de_la_misma_estrategia_vuelve_a_avisar(db, canal, monkeypatch):
    estrategia = _estrategia(db, compra=True)
    vieja = date.today() - timedelta(days=3)
    _stub_senales(monkeypatch, [_senal(estrategia, fecha=vieja)])
    alertas_analytics.evaluar_y_notificar(db)
    assert len(canal["mensajes"]) == 1

    _stub_senales(monkeypatch, [_senal(estrategia, fecha=date.today())])
    alertas_analytics.evaluar_y_notificar(db)
    assert len(canal["mensajes"]) == 2


def test_sin_estrategias_habilitadas_no_se_calculan_senales(db, canal, monkeypatch):
    """Correr los backtests de todo el universo para descartarlos es el gasto más caro del job."""
    _estrategia(db, compra=False, venta=False)

    def explota(*args, **kwargs):
        raise AssertionError("no se tiene que llamar a senales_recientes")

    monkeypatch.setattr(alertas_analytics.estrategias_analytics, "senales_recientes", explota)

    resumen = alertas_analytics.evaluar_y_notificar(db)
    assert resumen["senales_vigiladas"] == 0
    assert resumen["senales_nuevas"] == 0


def test_solo_las_compras_habilitadas_dejan_pasar_una_venta(db, canal, monkeypatch):
    estrategia = _estrategia(db, compra=True, venta=False)
    _stub_senales(monkeypatch, [_senal(estrategia, tipo="venta")])

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["senales_nuevas"] == 0
    assert canal["mensajes"] == []


def test_la_estrategia_habilitada_acota_el_calculo_y_la_antiguedad(db, canal, monkeypatch):
    habilitada = _estrategia(db, nombre="Con aviso", compra=True)
    _estrategia(db, nombre="Sin aviso")
    llamadas = _stub_senales(monkeypatch, [])

    alertas_analytics.evaluar_y_notificar(db)

    assert llamadas[0]["ids"] == (habilitada.id,)
    assert llamadas[0]["antiguedad"] == alertas_analytics.MAX_BARRAS_SENAL_AVISO


def test_la_senal_de_un_ticker_en_cartera_dice_la_cartera_y_la_tenencia(db, canal, monkeypatch):
    _posicion(db, precio_actual=95.0, ticker="AL30")  # sin niveles: sólo la señal avisa
    estrategia = _estrategia(db, venta=True)
    _stub_senales(monkeypatch, [_senal(estrategia, ticker="AL30", tipo="venta")])

    alertas_analytics.evaluar_y_notificar(db)

    mensaje = canal["mensajes"][0]
    assert "SEÑAL DE VENTA" in mensaje
    assert "cartera Principal" in mensaje
    assert "10 un." in mensaje


def test_la_senal_de_un_ticker_de_la_watchlist_lo_dice(db, canal, monkeypatch):
    _watchlist(db, objetivo=1.0, precio_actual=24000.0)  # objetivo lejísimo: no cruza
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia, ticker="MSFT", precio=24000.0)])

    alertas_analytics.evaluar_y_notificar(db)

    assert "watchlist" in canal["mensajes"][0]


def test_la_senal_no_lleva_cartera_en_la_clave(db, canal, monkeypatch):
    """Una señal es sobre la serie del ticker: si la cartera entrara en la clave, un ticker con
    tenencia en dos carteras avisaría dos veces."""
    _posicion(db, precio_actual=95.0, ticker="AL30")
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia, ticker="AL30")])

    alertas_analytics.evaluar_y_notificar(db)

    fila = db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.tipo_senal(estrategia.id)).one()
    assert fila.cartera == ""
    assert fila.nivel is None
    assert fila.detalle["senal_fecha"] == date.today().isoformat()


def test_el_reintento_de_una_senal_no_se_descarta_por_no_tener_nivel(db, canal, monkeypatch):
    """El guard viejo (`nivel is None` → descartar) se habría tragado todas las señales."""
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia)])
    canal["entrega"] = False
    alertas_analytics.evaluar_y_notificar(db)
    primero = canal["mensajes"][0]

    canal["entrega"] = True
    segunda = alertas_analytics.evaluar_y_notificar(db)

    assert segunda["pendientes_de_entrega"] == 1
    assert canal["mensajes"][1] == primero


def test_las_senales_de_estrategias_que_ya_no_avisan_se_purgan(db, canal, monkeypatch):
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia)])
    alertas_analytics.evaluar_y_notificar(db)
    assert db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.tipo_senal(estrategia.id)).count() == 1

    # Se apaga el aviso: la fila ya entregada no tiene por qué seguir ocupando lugar.
    estrategia.notificar_compra = 0
    db.commit()
    alertas_analytics.evaluar_y_notificar(db)

    assert db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.tipo_senal(estrategia.id)).count() == 0


def test_una_senal_sin_entregar_no_se_purga(db, canal, monkeypatch):
    """Un aviso pendiente no se tira, ni aunque se apague la estrategia."""
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia)])
    canal["entrega"] = False
    alertas_analytics.evaluar_y_notificar(db)

    estrategia.notificar_compra = 0
    db.commit()
    alertas_analytics.evaluar_y_notificar(db)

    assert db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.tipo_senal(estrategia.id)).count() == 1


def test_listar_una_senal_trae_el_contexto_legible(db, canal, monkeypatch):
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia)])
    alertas_analytics.evaluar_y_notificar(db)

    fila = alertas_analytics.listar(db)[0]

    assert fila["accion"] == alertas_engine.ACCION_COMPRA
    assert fila["estrategia_nombre"] == "Cruce de medias"
    assert fila["senal_fecha"] == date.today().isoformat()
    assert fila["senal_tipo"] == "compra"
    assert "estrategia:" not in fila["etiqueta"]
    assert "SEÑAL DE COMPRA" in fila["encabezado"]
    assert fila["nivel"] is None


def test_estado_configuracion_separa_niveles_de_senales(db, canal, monkeypatch):
    _posicion(db, stop_loss=50.0, precio_actual=100.0)  # un nivel armado
    estrategia = _estrategia(db, compra=True)
    _stub_senales(monkeypatch, [_senal(estrategia)])
    alertas_analytics.evaluar_y_notificar(db)

    estado = alertas_analytics.estado_configuracion(db)

    assert estado["niveles_vigilados"] == 1
    assert estado["senales_vigiladas"] == 1
    assert estado["estrategias_con_aviso"] == 1


# --- Endpoints de configuración ----------------------------------------------------------------

def test_endpoint_config_de_avisos(client):
    r = client.get("/api/inversiones/alertas/config")
    assert r.status_code == 200
    assert r.json()["avisar_stop_loss"] is True

    r = client.put("/api/inversiones/alertas/config", json={"avisar_stop_loss": False})
    assert r.status_code == 200
    assert r.json()["avisar_stop_loss"] is False
    assert r.json()["avisar_objetivo"] is True  # lo que no se manda no se toca


def test_endpoint_avisos_de_una_estrategia_inexistente(client):
    r = client.put("/api/inversiones/alertas/config/estrategias/999",
                   json={"notificar_compra": True})
    assert r.status_code == 404


def test_silenciar_un_cruce_no_borra_del_historial_el_aviso_anterior(db, canal):
    """La fila lleva el estado del nivel **y** el registro del último aviso emitido. Un cruce que
    no se mandó no puede pisar ese registro."""
    _posicion(db, stop_loss=96.0, precio_actual=95.0)
    alertas_analytics.evaluar_y_notificar(db)
    historial = alertas_analytics.listar(db)
    assert len(historial) == 1

    # Se re-arma, se apaga el tipo y vuelve a cruzar con otro precio.
    avisos_config.actualizar(db, avisar_stop_loss=False)
    for precio in (110.0, 90.0):
        db.query(PrecioInstrumento).delete()
        db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=precio,
                                 moneda="USD", fuente="sheet"))
        db.commit()
        alertas_analytics.evaluar_y_notificar(db)

    assert len(canal["mensajes"]) == 1
    assert alertas_analytics.listar(db) == historial
    assert alertas_analytics.estado_configuracion(db)["ultimo_aviso"] is not None
