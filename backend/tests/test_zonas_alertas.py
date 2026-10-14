"""Alertas de zona evaluadas sobre **su propia serie**: la local en pesos o la del subyacente en
dólares nativos.

Es lo que hace que un aviso de CEDEAR pueda medirse contra el precio real del instrumento en
EE.UU. en vez de contra el precio local, que mezcla el movimiento de la acción con el del dólar.
No hay conversión de moneda en ningún punto del camino: cada zona se compara con el precio de la
serie sobre la que fue dibujada.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    AlertaPrecio, BarraOHLCV, Base, EstadoMarketDataTicker, InstrumentoInversion,
    MovimientoInversion, PrecioInstrumento, PrecioSubyacente, WatchlistItem, ZonaPrecio,
)
from app.services import alertas_analytics, alertas_engine, avisos_config, zonas_precio as zp
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
    estado = {"mensajes": [], "entrega": True}

    def enviar(texto, parse_mode=None):
        estado["mensajes"].append(texto)
        return (True, None) if estado["entrega"] else (False, "canal caído")

    monkeypatch.setattr(telegram, "enviar", enviar)
    return estado


def _seguido(db, ticker="MSFT", precio_local=26000.0):
    db.add(WatchlistItem(ticker=ticker, nombre="Microsoft", tipo_instrumento="CEDEAR",
                         mercado="BCBA", moneda="ARS", agregado_en=date.today()))
    if precio_local is not None:
        from app.database import PrecioWatchlist
        db.add(PrecioWatchlist(ticker=ticker, fecha=date.today(), precio=precio_local,
                               moneda="ARS", fuente="iol"))
    db.commit()


def _en_cartera(db, ticker="MSFT", precio_local=26000.0, cantidad=10.0):
    db.add(InstrumentoInversion(ticker=ticker, nombre="Microsoft", tipo_instrumento="CEDEAR",
                                mercado="BCBA", moneda="ARS"))
    db.add(MovimientoInversion(
        fecha=date.today() - timedelta(days=30), cartera="Principal", ticker=ticker,
        tipo_movimiento="compra", cantidad=cantidad, precio=20000.0, moneda="ARS", comision=0.0,
    ))
    db.add(PrecioInstrumento(fecha=date.today(), ticker=ticker, precio=precio_local,
                             moneda="ARS", fuente="sheet"))
    db.commit()


def _subyacente_resuelto(db, ticker="MSFT", simbolo="MSFT", mercado="NMS"):
    db.add(EstadoMarketDataTicker(
        ticker=ticker, simbolo_subyacente=simbolo, mercado_subyacente=mercado,
        moneda_subyacente="USD", resolucion_estado="ok",
    ))
    db.commit()


def _zona(db, ticker="MSFT", tipo="compra", piso=None, techo=None,
          variante="local", moneda="ARS"):
    ahora = datetime.now()
    db.add(ZonaPrecio(ticker=ticker, tipo=tipo, variante=variante, moneda=moneda,
                      piso=piso, techo=techo, activa=1,
                      fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()


def _precio_sub(db, ticker="MSFT", precio=170.0, moneda="USD"):
    db.add(PrecioSubyacente(ticker=ticker, fecha=date.today(), precio=precio,
                            moneda=moneda, fuente="yahoo"))
    db.commit()


# ── Zona en dólares sobre la serie del subyacente ────────────────────────────

def test_zona_en_usd_se_evalua_contra_el_subyacente_y_no_contra_el_cedear(db, canal):
    """El caso que motivó todo: el CEDEAR cotiza 26.000 pesos y la zona está en 180 dólares.

    Si se compararan los dos números (26.000 ≤ 180 es falso, 26.000 ≥ 180 es verdadero), el aviso
    sería basura. La zona se mide contra el precio del subyacente: 170 ≤ 180 → entró.
    """
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", piso=160.0, techo=180.0, variante="subyacente", moneda="USD")
    _precio_sub(db, precio=170.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)

    assert resumen["nuevas"] == 1
    fila = db.query(AlertaPrecio).one()
    assert fila.tipo == alertas_engine.TIPO_COMPRA_ZONA
    assert float(fila.nivel) == 180.0
    assert float(fila.precio_disparo) == 170.0
    assert fila.moneda == "USD"
    # El mensaje tiene que decir que es otra serie: "≤ zona 180" sobre un CEDEAR de 26.000 pesos
    # se leería como un error de la app.
    assert "subyacente" in canal["mensajes"][0]
    assert "NMS" in canal["mensajes"][0]


def test_zona_en_usd_sin_precio_del_subyacente_no_avisa(db, canal):
    """Sin precio de su propia serie no se evalúa: avisar contra el precio local en pesos sería
    comparar dólares con pesos."""
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", techo=180.0, variante="subyacente", moneda="USD")

    resumen = alertas_analytics.evaluar_y_notificar(db)
    assert resumen["nuevas"] == 0
    assert db.query(AlertaPrecio).count() == 0


def test_cae_al_ultimo_cierre_de_la_serie_del_subyacente(db, canal):
    """Si el job liviano todavía no refrescó ese ticker, sirve el cierre de la serie `@SUB`: puede
    ser de ayer, pero es mejor que no evaluar la zona nunca."""
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", techo=180.0, variante="subyacente", moneda="USD")
    for dias, cierre in ((2, 190.0), (1, 175.0)):
        db.add(BarraOHLCV(
            ticker="MSFT@SUB", fecha=date.today() - timedelta(days=dias),
            apertura=None, maximo=None, minimo=None, cierre=cierre, volumen=None,
            moneda="USD", fuente="yahoo",
        ))
    db.commit()

    resumen = alertas_analytics.evaluar_y_notificar(db)
    assert resumen["nuevas"] == 1
    assert float(db.query(AlertaPrecio).one().precio_disparo) == 175.0   # el último, no el primero


def test_el_precio_refrescado_le_gana_al_cierre_de_la_serie(db, canal):
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", techo=180.0, variante="subyacente", moneda="USD")
    db.add(BarraOHLCV(ticker="MSFT@SUB", fecha=date.today() - timedelta(days=1),
                      apertura=None, maximo=None, minimo=None, cierre=200.0, volumen=None,
                      moneda="USD", fuente="yahoo"))
    db.commit()
    _precio_sub(db, precio=179.0)   # intradía: ya entró en zona

    resumen = alertas_analytics.evaluar_y_notificar(db)
    assert resumen["nuevas"] == 1
    assert float(db.query(AlertaPrecio).one().precio_disparo) == 179.0


def test_un_precio_del_subyacente_en_otra_moneda_se_ignora(db, canal):
    """Una fila vieja o mal guardada no puede disparar una zona en dólares."""
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", techo=180.0, variante="subyacente", moneda="USD")
    _precio_sub(db, precio=170.0, moneda="EUR")

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 0


# ── Zona local ───────────────────────────────────────────────────────────────

def test_zona_local_de_un_ticker_seguido(db, canal):
    _seguido(db, precio_local=24000.0)
    _zona(db, tipo="compra", piso=23000.0, techo=25000.0)

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 1
    assert "watchlist" in canal["mensajes"][0]
    # El rango completo, no sólo el borde: es lo que distingue una zona de un nivel suelto.
    assert "25.000" in canal["mensajes"][0] and "23.000" in canal["mensajes"][0]


def test_zona_de_venta_de_una_posicion_informa_la_tenencia(db, canal):
    """Las zonas valen también para lo que ya se tiene: planear la salida es tan válido como
    planear la entrada."""
    _en_cartera(db, precio_local=31000.0, cantidad=10.0)
    _zona(db, tipo="venta", piso=30000.0, techo=32000.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)
    assert resumen["nuevas"] == 1
    fila = db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.TIPO_VENTA_ZONA
    ).one()
    assert float(fila.nivel) == 30000.0          # dispara el piso: el precio sube y entra
    mensaje = canal["mensajes"][0]
    assert "cartera Principal" in mensaje
    assert "ZONA DE VENTA" in mensaje
    assert "10" in mensaje                        # la tenencia


def test_una_posicion_valuada_al_costo_no_dispara_su_zona(db, canal):
    """Sin cotización, la posición se valúa al costo promedio. Disparar una zona contra el propio
    precio de compra sería un aviso inventado."""
    db.add(InstrumentoInversion(ticker="ILIQ", nombre="Ilíquido", tipo_instrumento="Accion",
                                mercado="BCBA", moneda="ARS"))
    db.add(MovimientoInversion(
        fecha=date.today() - timedelta(days=30), cartera="Principal", ticker="ILIQ",
        tipo_movimiento="compra", cantidad=10.0, precio=1000.0, moneda="ARS", comision=0.0,
    ))
    db.commit()
    _zona(db, ticker="ILIQ", tipo="compra", techo=1200.0)

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 0


def test_el_mismo_ticker_en_dos_carteras_avisa_una_sola_vez_por_zona(db, canal):
    """La zona es una decisión sobre el instrumento, no sobre una tenencia: si la cartera entrara
    en la clave, el mismo ticker avisaría dos veces de la misma zona."""
    _en_cartera(db, precio_local=24000.0)
    db.add(MovimientoInversion(
        fecha=date.today() - timedelta(days=20), cartera="Secundaria", ticker="MSFT",
        tipo_movimiento="compra", cantidad=5.0, precio=21000.0, moneda="ARS", comision=0.0,
    ))
    db.commit()
    _zona(db, tipo="compra", techo=25000.0)

    resumen = alertas_analytics.evaluar_y_notificar(db)
    assert resumen["nuevas"] == 1
    assert db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.TIPO_COMPRA_ZONA
    ).count() == 1


def test_zona_pausada_no_se_evalua(db, canal):
    _seguido(db, precio_local=24000.0)
    _zona(db, tipo="compra", techo=25000.0)
    db.query(ZonaPrecio).update({"activa": 0})
    db.commit()

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 0


# ── Antirrebote con el borde opuesto ─────────────────────────────────────────

def test_avisa_una_vez_y_se_rearma_al_volver_por_arriba_del_techo(db, canal):
    from app.database import PrecioWatchlist

    _seguido(db, precio_local=24000.0)
    _zona(db, tipo="compra", piso=23000.0, techo=25000.0)

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 1
    # Sigue adentro: no repite.
    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 0

    # Por debajo del piso **sigue** en zona (está más barato, no afuera): tampoco se re-arma.
    db.query(PrecioWatchlist).update({"precio": 22000.0})
    db.commit()
    alertas_analytics.evaluar_y_notificar(db)
    assert db.query(AlertaPrecio).one().estado == alertas_engine.ESTADO_DISPARADA

    # Vuelve por arriba del techo y se despega de la banda: ahí sí.
    db.query(PrecioWatchlist).update({"precio": 27000.0})
    db.commit()
    alertas_analytics.evaluar_y_notificar(db)
    assert db.query(AlertaPrecio).one().estado == alertas_engine.ESTADO_ARMADA


# ── Interruptor ──────────────────────────────────────────────────────────────

def test_el_interruptor_de_zona_de_venta_silencia_pero_sigue(db, canal):
    """Un tipo apagado se sigue igual: el cruce se guarda silenciado, así que prenderlo después no
    manda de golpe todo lo que pasó."""
    _en_cartera(db, precio_local=31000.0)
    _zona(db, tipo="venta", piso=30000.0)
    avisos_config.actualizar(db, avisar_venta_zona=False)

    alertas_analytics.evaluar_y_notificar(db)

    fila = db.query(AlertaPrecio).filter(
        AlertaPrecio.tipo == alertas_engine.TIPO_VENTA_ZONA
    ).one()
    assert fila.estado == alertas_engine.ESTADO_DISPARADA
    assert fila.entregada == 1 and fila.emitida_en is None
    assert canal["mensajes"] == []


def test_la_zona_de_venta_arranca_prendida(db):
    assert alertas_engine.TIPO_VENTA_ZONA in avisos_config.tipos_habilitados(db)


def test_la_moneda_del_aviso_es_la_del_precio_comparado(db, canal):
    """Una etiqueta guardada que contradiga la serie no puede llegar al mensaje: "ARS 173,40" sobre
    un precio en dólares haría desconfiar de todo el aviso."""
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", techo=180.0, variante="subyacente", moneda="ARS")   # etiqueta errónea
    _precio_sub(db, precio=170.0)

    alertas_analytics.evaluar_y_notificar(db)

    assert db.query(AlertaPrecio).one().moneda == "USD"
    assert "ARS 170" not in canal["mensajes"][0]
    assert "USD 170,00" in canal["mensajes"][0]


def test_gana_el_precio_del_subyacente_mas_fresco(db, canal):
    """Si el job liviano dejó de correr, su precio puede ser más viejo que el último cierre de la
    serie. Fijar una fuente ganadora haría comparar la zona contra un precio de la semana pasada
    teniendo uno de hoy."""
    _seguido(db, precio_local=26000.0)
    _subyacente_resuelto(db)
    _zona(db, tipo="compra", techo=180.0, variante="subyacente", moneda="USD")
    # Refresco viejo y fuera de zona; cierre de hoy ya dentro.
    db.add(PrecioSubyacente(ticker="MSFT", fecha=date.today() - timedelta(days=7),
                            precio=210.0, moneda="USD", fuente="yahoo"))
    db.add(BarraOHLCV(ticker="MSFT@SUB", fecha=date.today(),
                      apertura=None, maximo=None, minimo=None, cierre=175.0, volumen=None,
                      moneda="USD", fuente="yahoo"))
    db.commit()

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 1
    assert float(db.query(AlertaPrecio).one().precio_disparo) == 175.0
