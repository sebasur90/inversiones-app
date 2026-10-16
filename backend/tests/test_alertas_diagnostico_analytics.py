"""Cambios de diagnóstico de punta a punta: historial → motor → estado guardado → canal."""
import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import (
    AlertaPrecio, Base, DiagnosticoAlertaEstado, DiagnosticoHistorial, InstrumentoInversion, MovimientoInversion,
    PrecioInstrumento, PrecioWatchlist, WatchlistItem,
)
from app.services import alertas_analytics, alertas_engine, avisos_config
from app.services.notificaciones import telegram

HOY = date.today()
D1, D2, D3, D4 = (HOY - timedelta(days=n) for n in (15, 10, 5, 1))


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(WatchlistItem(ticker="MSFT", nombre="Microsoft", tipo_instrumento="CEDEAR", mercado="BCBA", moneda="ARS"))
    session.add(PrecioWatchlist(ticker="MSFT", fecha=HOY, precio=24000.0, moneda="ARS", fuente="iol"))
    session.commit()
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


def _estados(valuacion="Barata", calidad="Sólida", solidez="Sólida"):
    def dim(estado, razon):
        return {"estado": estado, "nivel": "neutro", "percentil": 50, "razon": razon, "regla": f"regla de {estado}"}
    return {
        "valuacion": dim(valuacion, f"{valuacion}: múltiplos contra sus pares"),
        "calidad": dim(calidad, "márgenes y retornos"),
        "crecimiento": dim("Estable", "ingresos"),
        "solidez": dim(solidez, "deuda"),
        "confianza": dim("Alta", "datos completos"),
    }


def _foto(db, fecha_dato, ticker="MSFT", version=2, confianza="alta", **estados):
    db.add(DiagnosticoHistorial(
        ticker_base=ticker, fecha=HOY, fecha_dato=fecha_dato, version_diagnostico=version,
        estados=_estados(**estados), lectura="barata", confianza=confianza, pares=[], huella=f"{ticker}{fecha_dato}{version}{estados}",
        precio=410.5, moneda="USD",
    ))
    db.commit()


def _estado_guardado(db, dimension="valuacion", ticker="MSFT"):
    return db.query(DiagnosticoAlertaEstado).filter_by(ticker_base=ticker, dimension=dimension).one()


# ── Ciclo completo ──────────────────────────────────────────────────────────

def test_primera_corrida_siembra_y_no_manda_nada(db, canal):
    _foto(db, D1)
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_sembrados"] == 3 and r["diagnosticos_nuevos"] == 0 and canal["mensajes"] == []
    assert _estado_guardado(db).estado_base == "Barata"
    assert db.query(DiagnosticoAlertaEstado).count() == 3        # valuación, calidad y solidez


def test_un_cambio_se_avisa_recien_cuando_se_confirma_y_una_sola_vez(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)

    _foto(db, D2, valuacion="Cara")
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_pendientes"] == 1 and canal["mensajes"] == []
    assert _estado_guardado(db).pendiente == "Cara"

    _foto(db, D3, valuacion="Cara")
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_nuevos"] == 1 and r["entregado"] is True and len(canal["mensajes"]) == 1
    msg = canal["mensajes"][0]
    assert "CAMBIO DE DIAGNÓSTICO" in msg and "<b>MSFT</b>" in msg and "Barata → <b>Cara</b>" in msg
    assert "Cara: múltiplos contra sus pares" in msg and "watchlist" in msg
    assert not re.search(r"\b(compr\w*|vend\w*|recomend\w*)\b", msg, re.IGNORECASE), msg
    est = _estado_guardado(db)
    assert est.estado_base == "Cara" and est.pendiente is None

    # ni la misma foto ni una posterior sin cambios vuelven a avisar
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D4, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db)
    assert len(canal["mensajes"]) == 1


def test_la_misma_foto_evaluada_dos_veces_no_confirma(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, valuacion="Cara")
    for _ in range(3):
        alertas_analytics.evaluar_y_notificar(db)
    assert canal["mensajes"] == [] and _estado_guardado(db).pendiente == "Cara"


def test_oscilar_no_avisa(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    for fecha, estado in ((D2, "Cara"), (D3, "Barata"), (D4, "Cara")):
        _foto(db, fecha, valuacion=estado)
        alertas_analytics.evaluar_y_notificar(db)
    assert canal["mensajes"] == []


def test_se_ven_en_el_historial_de_avisos_con_su_contexto(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, calidad="Débil")
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D3, calidad="Débil")
    alertas_analytics.evaluar_y_notificar(db)
    item = alertas_analytics.listar(db)[0]
    assert item["tipo"] == "diagnostico:calidad" and item["etiqueta"] == "Cambio de diagnóstico · Calidad"
    assert item["accion"] == "REVISAR" and item["encabezado"] == "🔎 CAMBIO DE DIAGNÓSTICO"
    assert (item["diag_de"], item["diag_a"]) == ("Sólida", "Débil") and item["diag_dimension"] == "Calidad"
    assert item["diag_razon"] and item["diag_fecha_dato"] == D3.isoformat() and item["nivel"] is None


# ── Silencios ───────────────────────────────────────────────────────────────

def test_apagado_el_estado_avanza_pero_no_se_manda_ni_se_acumula(db, canal):
    avisos_config.actualizar(db, avisar_diagnostico=False)
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D3, valuacion="Cara")
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_nuevos"] == 1 and r["silenciadas"] == 1 and canal["mensajes"] == []
    assert _estado_guardado(db).estado_base == "Cara"
    fila = db.query(AlertaPrecio).filter_by(tipo="diagnostico:valuacion").one()
    assert fila.entregada == 1 and fila.emitida_en is None
    assert alertas_analytics.listar(db) == []
    # prenderlo después no manda lo que pasó mientras estaba apagado
    avisos_config.actualizar(db, avisar_diagnostico=True)
    alertas_analytics.evaluar_y_notificar(db)
    assert canal["mensajes"] == []


def test_el_dato_viejo_no_avisa_ni_siembra(db, canal):
    _foto(db, HOY - timedelta(days=60))
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_silenciados_por_dato"] == 3 and r["diagnosticos_sembrados"] == 0
    assert db.query(DiagnosticoAlertaEstado).count() == 0 and canal["mensajes"] == []


def test_confianza_baja_no_avisa(db, canal):
    _foto(db, D1, confianza="baja")
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_silenciados_por_dato"] == 3 and canal["mensajes"] == []


def test_un_cambio_de_reglas_no_es_un_cambio_de_la_empresa(db, canal):
    _foto(db, D1, version=2)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, version=3, valuacion="Cara")
    _foto(db, D3, version=3, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db)
    assert canal["mensajes"] == [] and _estado_guardado(db).version == 3 and _estado_guardado(db).estado_base == "Cara"


def test_lo_que_no_esta_en_cartera_ni_en_watchlist_se_ignora(db, canal):
    _foto(db, D1, ticker="KO")
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_sembrados"] == 0 and db.query(DiagnosticoAlertaEstado).count() == 0


def test_una_posicion_en_cartera_tambien_se_vigila(db, canal):
    db.add(InstrumentoInversion(ticker="KO", nombre="Coca-Cola", tipo_instrumento="CEDEAR", mercado="BCBA", moneda="USD"))
    db.add(MovimientoInversion(fecha=HOY - timedelta(days=30), cartera="Principal", ticker="KO", tipo_movimiento="compra",
                               cantidad=10.0, precio=60.0, moneda="USD", comision=0.0))
    db.add(PrecioInstrumento(fecha=HOY, ticker="KO", precio=65.0, moneda="USD", fuente="sheet"))
    db.commit()
    _foto(db, D1, ticker="KO")
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, ticker="KO", solidez="Frágil")
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D3, ticker="KO", solidez="Frágil")
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_nuevos"] == 1 and len(canal["mensajes"]) == 1
    assert "Solidez financiera" in canal["mensajes"][0] and "cartera Principal" in canal["mensajes"][0]


# ── Entrega ─────────────────────────────────────────────────────────────────

def test_si_falla_la_entrega_se_reintenta_sin_re_disparar(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D3, valuacion="Cara")
    canal["entrega"] = False
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["entregado"] is False and r["diagnosticos_nuevos"] == 1
    primero = canal["mensajes"][-1]

    canal["entrega"] = True
    r = alertas_analytics.evaluar_y_notificar(db)
    assert r["diagnosticos_nuevos"] == 0 and r["pendientes_de_entrega"] == 1 and r["entregado"] is True
    assert canal["mensajes"][-1] == primero                    # el reintento es idéntico al original
    alertas_analytics.evaluar_y_notificar(db)
    assert len(canal["mensajes"]) == 2


def test_notificar_false_siembra_sin_mandar_ni_dejar_nada_encolado(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db, notificar=False)
    _foto(db, D3, valuacion="Cara")
    r = alertas_analytics.evaluar_y_notificar(db, notificar=False)      # acá se confirma el cambio
    assert r["diagnosticos_nuevos"] == 1 and canal["mensajes"] == []
    assert _estado_guardado(db).estado_base == "Cara"
    alertas_analytics.evaluar_y_notificar(db)                           # y la corrida siguiente no lo manda
    assert canal["mensajes"] == [] and alertas_analytics.listar(db) == []


def test_no_toca_los_niveles_ni_se_cuenta_como_uno(db, canal):
    _foto(db, D1)
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D2, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db)
    _foto(db, D3, valuacion="Cara")
    alertas_analytics.evaluar_y_notificar(db)
    estado = alertas_analytics.estado_configuracion(db)
    assert estado["niveles_vigilados"] == 0 and estado["senales_vigiladas"] == 0 and estado["diagnosticos_vigilados"] == 3
    estados, avisadas = alertas_analytics._estado_guardado(db)
    assert estados == {} and avisadas == {}


# ── Configuración ───────────────────────────────────────────────────────────

def test_el_interruptor_arranca_prendido_y_va_en_el_estado(db):
    assert avisos_config.diagnostico_habilitado(db) is True
    assert avisos_config.estado(db)["avisar_diagnostico"] is True
    avisos_config.actualizar(db, avisar_diagnostico=False)
    assert avisos_config.diagnostico_habilitado(db) is False and avisos_config.estado(db)["avisar_diagnostico"] is False
    avisos_config.actualizar(db, avisar_stop_loss=False)             # tocar otro no cambia éste
    assert avisos_config.diagnostico_habilitado(db) is False
    assert alertas_engine.TIPOS == tuple(avisos_config.CAMPO_POR_TIPO)     # el diagnóstico no es un tipo de nivel


def test_el_alter_de_una_db_vieja_es_idempotente(monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import database

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:       # `ajustes_avisos` como estaba antes de esta etapa
        conn.execute(text(
            "CREATE TABLE ajustes_avisos (id INTEGER PRIMARY KEY, avisar_stop_loss INTEGER NOT NULL DEFAULT 1, "
            "avisar_objetivo INTEGER NOT NULL DEFAULT 1, avisar_compra_zona INTEGER NOT NULL DEFAULT 1, "
            "avisar_venta_zona INTEGER NOT NULL DEFAULT 1, fecha_actualizacion DATETIME NOT NULL)"))
        conn.execute(text("INSERT INTO ajustes_avisos (id, avisar_stop_loss, fecha_actualizacion) VALUES (1, 0, '2026-01-01')"))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))

    database.init_db()
    database.init_db()                  # la segunda no debe fallar ni duplicar
    with engine.connect() as conn:
        columnas = [r[1] for r in conn.execute(text("PRAGMA table_info(ajustes_avisos)"))]
        fila = conn.execute(text("SELECT avisar_stop_loss, avisar_diagnostico FROM ajustes_avisos WHERE id = 1")).one()
    assert columnas.count("avisar_diagnostico") == 1
    assert fila == (0, 1)               # lo que el usuario ya había apagado se conserva; lo nuevo arranca prendido
