"""Niveles de stop-loss y objetivo fijados desde la app, que pisan los del Sheet.

Cubre lo que los motores puros no pueden: la precedencia app > Sheet, que el override **sobreviva
a un sync** (que es el motivo entero de que exista una tabla aparte), el re-armado de los avisos
de Telegram cuando se cambia un nivel, y que editar se vea sin sincronizar.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import (
    AlertaPrecio, Base, InstrumentoInversion, MovimientoInversion, NivelPrecioOverride,
    PrecioInstrumento, get_db,
)
from app.main import app
from app.services import (
    alertas_analytics, alertas_engine, diagnostico_analytics, inversiones_analytics,
    niveles_analytics,
)
from app.services import inversiones_sync
from app.services.notificaciones import telegram
from app.services.sheets_client import TabRaw
from app.services.ticker_analytics import get_ticker_position

HOY = date.today()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def cliente():
    """App con una SQLite en memoria compartida entre la sesión de test y la de los requests."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)

    def _get_db():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    sesion = Sesion()
    yield TestClient(app), sesion
    sesion.close()
    app.dependency_overrides.clear()


def _posicion(
    db: Session, *, ticker="AAPL", sheet_stop=None, sheet_objetivo=None, modo_sheet="Fijo",
    precio_compra=100.0, precio_actual=100.0, cartera="Principal",
):
    """Un instrumento con sus niveles del Sheet, una compra y un precio de hoy."""
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=f"{ticker} SA", tipo_instrumento="Accion", mercado="TEST",
        moneda="USD",
        stop_loss_modo=modo_sheet if sheet_stop is not None else None,
        stop_loss_valor=sheet_stop,
        objetivo_modo=modo_sheet if sheet_objetivo is not None else None,
        objetivo_valor=sheet_objetivo,
    ))
    db.add(MovimientoInversion(
        fecha=HOY - timedelta(days=30), cartera=cartera, ticker=ticker,
        tipo_movimiento="compra", cantidad=10.0, precio=precio_compra, moneda="USD", comision=0.0,
    ))
    db.add(PrecioInstrumento(
        fecha=HOY, ticker=ticker, precio=precio_actual, moneda="USD", fuente="sheet",
    ))
    db.commit()


def _override(db: Session, ticker: str, tipo: str, modo: str, valor: float):
    ahora = datetime.now()
    db.add(NivelPrecioOverride(
        ticker=ticker, tipo=tipo, modo=modo, valor=valor,
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    ))
    db.commit()


def _fila(db: Session, cartera="Principal", ticker="AAPL") -> dict:
    filas = inversiones_analytics.get_rendimiento_por_ticker(cartera, db)
    return next(f for f in filas if f["ticker"] == ticker)


# ── Resolución de la precedencia ──────────────────────────────────────────────

def test_sin_override_manda_el_sheet(db: Session):
    _posicion(db, sheet_stop=90.0, sheet_objetivo=120.0, precio_actual=100.0)

    fila = _fila(db)
    assert fila["stop_loss_origen"] == "sheet"
    assert fila["stop_loss_valor"] == 90.0
    assert fila["precio_stop_loss"] == 90.0
    assert fila["stop_loss_disparado"] is False
    assert fila["objetivo_origen"] == "sheet"
    assert fila["precio_objetivo"] == 120.0
    # La referencia del Sheet viaja igual, aunque sea la que se está usando.
    assert fila["stop_loss_valor_sheet"] == 90.0
    assert fila["stop_loss_modo_sheet"] == "Fijo"


def test_override_pisa_el_valor_del_sheet(db: Session):
    _posicion(db, sheet_stop=90.0, precio_actual=100.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 98.0)

    fila = _fila(db)
    assert fila["stop_loss_origen"] == "app"
    assert fila["stop_loss_valor"] == 98.0
    assert fila["precio_stop_loss"] == 98.0
    # El del Sheet sigue viajando como referencia, para poder volver a él.
    assert fila["stop_loss_valor_sheet"] == 90.0


def test_override_cambia_si_el_nivel_esta_cruzado(db: Session):
    """El del Sheet no estaba cruzado y el de la app sí: es lo que leen alertas y diagnóstico."""
    _posicion(db, sheet_stop=90.0, precio_actual=95.0)
    assert _fila(db)["stop_loss_disparado"] is False

    _override(db, "AAPL", "stop_loss", "Fijo", 96.0)
    assert _fila(db)["stop_loss_disparado"] is True


def test_override_de_un_tipo_no_toca_el_otro(db: Session):
    _posicion(db, sheet_stop=90.0, sheet_objetivo=120.0)
    _override(db, "AAPL", "objetivo", "Fijo", 150.0)

    fila = _fila(db)
    assert fila["objetivo_origen"] == "app"
    assert fila["precio_objetivo"] == 150.0
    assert fila["stop_loss_origen"] == "sheet"
    assert fila["precio_stop_loss"] == 90.0


def test_override_en_ticker_sin_nivel_en_el_sheet(db: Session):
    _posicion(db, precio_actual=100.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 95.0)

    fila = _fila(db)
    assert fila["stop_loss_origen"] == "app"
    assert fila["precio_stop_loss"] == 95.0
    assert fila["stop_loss_modo_sheet"] is None
    assert fila["stop_loss_valor_sheet"] is None
    # El objetivo no está en ninguna de las dos fuentes.
    assert fila["objetivo_origen"] == "ninguno"
    assert fila["precio_objetivo"] is None


def test_override_en_modo_porcentaje_usa_el_precio_promedio(db: Session):
    _posicion(db, precio_compra=200.0, precio_actual=190.0)
    _override(db, "AAPL", "stop_loss", "Porcentaje", -5.0)

    fila = _fila(db)
    assert fila["precio_stop_loss"] == pytest.approx(190.0)  # 200 * (1 - 0.05)
    assert fila["stop_loss_modo"] == "Porcentaje"
    assert fila["stop_loss_valor"] == -5.0


def test_fila_de_override_sin_valor_se_ignora(db: Session):
    """Hoy no se escribe ninguna así; si apareciera, manda el Sheet y nada se rompe."""
    _posicion(db, sheet_stop=90.0)
    ahora = datetime.now()
    db.add(NivelPrecioOverride(
        ticker="AAPL", tipo="stop_loss", modo=None, valor=None,
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    ))
    db.commit()

    fila = _fila(db)
    assert fila["stop_loss_origen"] == "sheet"
    assert fila["precio_stop_loss"] == 90.0


def test_detalle_del_ticker_tambien_resuelve_el_override(db: Session):
    _posicion(db, sheet_stop=90.0, precio_actual=100.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 98.0)

    position = get_ticker_position("AAPL", "Principal", db)
    assert position["stop_loss_origen"] == "app"
    assert position["precio_stop_loss"] == 98.0
    assert position["stop_loss_valor_sheet"] == 90.0


def test_detalle_sin_movimientos_igual_trae_los_niveles(db: Session):
    """Es la pantalla donde se editan: sin esto el formulario aparecería vacío."""
    _posicion(db, sheet_stop=90.0, cartera="Otra")
    _override(db, "AAPL", "objetivo", "Porcentaje", 25.0)

    position = get_ticker_position("AAPL", "Principal", db)
    assert position["cantidad_actual"] == 0.0
    assert position["objetivo_origen"] == "app"
    assert position["objetivo_valor"] == 25.0
    assert position["stop_loss_origen"] == "sheet"
    assert position["stop_loss_valor"] == 90.0
    # Sin precio promedio no hay nivel absoluto ni distancia que calcular.
    assert position["precio_objetivo"] is None
    assert position["pct_a_objetivo"] is None
    assert position["objetivo_alcanzado"] is None


# ── El override sobrevive al sync ─────────────────────────────────────────────

def _sheet_con_instrumento(stop_modo, stop_valor):
    """Un Sheet mínimo con AAPL, su compra y su precio."""
    def mock():
        return {
            "Instrumentos": TabRaw(presente=True, header=[
                "Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda",
                "Stop Loss Modo", "Stop Loss Valor",
            ], rows=[(2, {
                "Ticker": "AAPL", "Nombre": "Apple", "Tipo Instrumento": "Accion",
                "Mercado": "TEST", "Moneda": "USD",
                "Stop Loss Modo": stop_modo, "Stop Loss Valor": stop_valor,
            })]),
            "Movimientos": TabRaw(presente=True, header=[
                "Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Cantidad", "Precio", "Moneda",
            ], rows=[(2, {
                "Fecha": (HOY - timedelta(days=30)).isoformat(), "Cartera": "Principal",
                "Ticker": "AAPL", "Tipo Movimiento": "Compra", "Cantidad": "10",
                "Precio": "100", "Moneda": "USD",
            })]),
            "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
                (2, {"Fecha": HOY.isoformat(), "Ticker": "AAPL", "Precio": "100", "Moneda": "USD"})
            ]),
            "Objetivos": TabRaw(presente=False, header=[], rows=[]),
            "Rebalanceo": TabRaw(presente=False, header=[], rows=[]),
            "Benchmarks": TabRaw(presente=False, header=[], rows=[]),
            "Configuracion": TabRaw(presente=False, header=[], rows=[]),
        }
    return mock


def test_el_override_sobrevive_a_un_sync(db: Session, monkeypatch):
    """El motivo entero de que exista la tabla: el sync vacía `instrumentos_inversion`."""
    _posicion(db, sheet_stop=90.0, precio_actual=100.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 98.0)

    # El Sheet llega con OTRO nivel: ni el viejo ni el de la app.
    monkeypatch.setattr(inversiones_sync, "fetch_sheet_data", _sheet_con_instrumento("Fijo", "80"))
    inversiones_sync.sync_from_sheet(db)

    assert db.query(NivelPrecioOverride).count() == 1
    fila = _fila(db)
    assert fila["stop_loss_origen"] == "app"
    assert fila["precio_stop_loss"] == 98.0
    # La referencia sí se actualizó con lo que trajo el sync.
    assert fila["stop_loss_valor_sheet"] == 80.0


def test_override_huerfano_no_rompe_nada(db: Session, monkeypatch):
    """Un ticker con override que desaparece del Sheet: la fila queda, nada explota."""
    _posicion(db, ticker="VIEJO", sheet_stop=90.0)
    _override(db, "VIEJO", "stop_loss", "Fijo", 95.0)

    monkeypatch.setattr(inversiones_sync, "fetch_sheet_data", _sheet_con_instrumento("Fijo", "80"))
    inversiones_sync.sync_from_sheet(db)

    assert db.query(NivelPrecioOverride).count() == 1
    filas = inversiones_analytics.get_rendimiento_por_ticker("Principal", db)
    assert [f["ticker"] for f in filas] == ["AAPL"]
    niveles = niveles_analytics.niveles_de_ticker(db, "VIEJO")
    assert niveles.stop_loss.origen == "app"
    assert niveles.stop_loss.valor_sheet is None


# ── Endpoints ─────────────────────────────────────────────────────────────────

def test_get_niveles_sin_override(cliente):
    client, db = cliente
    _posicion(db, sheet_stop=90.0)

    r = client.get("/api/inversiones/ticker/AAPL/niveles")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ticker"] == "AAPL"
    assert cuerpo["stop_loss"]["origen"] == "sheet"
    assert cuerpo["stop_loss"]["valor"] == 90.0
    assert cuerpo["objetivo"]["origen"] == "ninguno"
    assert cuerpo["objetivo"]["valor"] is None


def test_get_niveles_ticker_inexistente_404(cliente):
    client, _ = cliente
    assert client.get("/api/inversiones/ticker/NOPE/niveles").status_code == 404


def test_put_guarda_el_override(cliente):
    client, db = cliente
    _posicion(db, sheet_stop=90.0)

    r = client.put("/api/inversiones/ticker/AAPL/niveles",
                   json={"stop_loss": {"modo": "Fijo", "valor": 98.0}})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["stop_loss"]["origen"] == "app"
    assert cuerpo["stop_loss"]["valor"] == 98.0
    assert cuerpo["stop_loss"]["valor_sheet"] == 90.0
    assert cuerpo["stop_loss"]["actualizado_en"] is not None
    assert db.query(NivelPrecioOverride).count() == 1


def test_put_parcial_no_pisa_el_otro_nivel(cliente):
    client, db = cliente
    _posicion(db)
    client.put("/api/inversiones/ticker/AAPL/niveles",
               json={"objetivo": {"modo": "Fijo", "valor": 150.0}})

    r = client.put("/api/inversiones/ticker/AAPL/niveles",
                   json={"stop_loss": {"modo": "Fijo", "valor": 95.0}})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["objetivo"]["valor"] == 150.0
    assert cuerpo["stop_loss"]["valor"] == 95.0


def test_put_con_null_vuelve_al_valor_del_sheet(cliente):
    client, db = cliente
    _posicion(db, sheet_stop=90.0)
    client.put("/api/inversiones/ticker/AAPL/niveles",
               json={"stop_loss": {"modo": "Fijo", "valor": 98.0}})

    r = client.put("/api/inversiones/ticker/AAPL/niveles", json={"stop_loss": None})
    assert r.status_code == 200
    assert r.json()["stop_loss"] == {
        "modo": "Fijo", "valor": 90.0, "origen": "sheet",
        "modo_sheet": "Fijo", "valor_sheet": 90.0, "actualizado_en": None,
    }
    assert db.query(NivelPrecioOverride).count() == 0


def test_put_vacio_422(cliente):
    client, db = cliente
    _posicion(db)
    assert client.put("/api/inversiones/ticker/AAPL/niveles", json={}).status_code == 422


def test_delete_de_un_nivel(cliente):
    client, db = cliente
    _posicion(db, sheet_stop=90.0)
    client.put("/api/inversiones/ticker/AAPL/niveles", json={
        "stop_loss": {"modo": "Fijo", "valor": 98.0},
        "objetivo": {"modo": "Fijo", "valor": 150.0},
    })

    assert client.delete("/api/inversiones/ticker/AAPL/niveles/stop_loss").status_code == 204
    cuerpo = client.get("/api/inversiones/ticker/AAPL/niveles").json()
    assert cuerpo["stop_loss"]["origen"] == "sheet"
    assert cuerpo["objetivo"]["origen"] == "app"


def test_delete_es_idempotente(cliente):
    client, db = cliente
    _posicion(db)
    assert client.delete("/api/inversiones/ticker/AAPL/niveles/stop_loss").status_code == 204
    assert client.delete("/api/inversiones/ticker/AAPL/niveles/stop_loss").status_code == 204


def test_delete_de_los_dos(cliente):
    client, db = cliente
    _posicion(db)
    client.put("/api/inversiones/ticker/AAPL/niveles", json={
        "stop_loss": {"modo": "Fijo", "valor": 98.0},
        "objetivo": {"modo": "Fijo", "valor": 150.0},
    })

    assert client.delete("/api/inversiones/ticker/AAPL/niveles").status_code == 204
    assert db.query(NivelPrecioOverride).count() == 0


def test_delete_de_tipo_invalido_404(cliente):
    client, db = cliente
    _posicion(db)
    assert client.delete("/api/inversiones/ticker/AAPL/niveles/compra_zona").status_code == 404


@pytest.mark.parametrize("body", [
    {"stop_loss": {"modo": "Ninguno", "valor": 10.0}},     # modo que no existe
    {"stop_loss": {"modo": "Fijo", "valor": 0.0}},         # un precio no puede ser 0
    {"stop_loss": {"modo": "Fijo", "valor": -5.0}},
    {"stop_loss": {"modo": "Porcentaje", "valor": 0.0}},   # el nivel quedaría en el costo
    {"stop_loss": {"modo": "Porcentaje", "valor": 5.0}},   # el stop-loss va negativo
    {"stop_loss": {"modo": "Porcentaje", "valor": -100.0}},
    {"objetivo": {"modo": "Porcentaje", "valor": -5.0}},   # el objetivo va positivo
    {"objetivo": {"modo": "Porcentaje", "valor": 5000.0}},
])
def test_put_invalido_422(cliente, body):
    client, db = cliente
    _posicion(db)
    r = client.put("/api/inversiones/ticker/AAPL/niveles", json=body)
    assert r.status_code == 422
    assert db.query(NivelPrecioOverride).count() == 0


def test_un_nivel_invalido_no_guarda_el_otro(cliente):
    client, db = cliente
    _posicion(db)
    r = client.put("/api/inversiones/ticker/AAPL/niveles", json={
        "stop_loss": {"modo": "Fijo", "valor": 98.0},
        "objetivo": {"modo": "Porcentaje", "valor": -5.0},
    })
    assert r.status_code == 422
    assert db.query(NivelPrecioOverride).count() == 0


def test_editar_se_ve_sin_sincronizar(cliente):
    """El caché de analytics se invalida por escritura, no sólo por sync."""
    client, db = cliente
    _posicion(db, sheet_stop=90.0, precio_actual=95.0)

    antes = client.get("/api/inversiones/carteras/Principal/rendimiento-por-ticker").json()
    assert antes[0]["stop_loss_disparado"] is False

    client.put("/api/inversiones/ticker/AAPL/niveles",
               json={"stop_loss": {"modo": "Fijo", "valor": 96.0}})

    despues = client.get("/api/inversiones/carteras/Principal/rendimiento-por-ticker").json()
    assert despues[0]["precio_stop_loss"] == 96.0
    assert despues[0]["stop_loss_disparado"] is True
    assert despues[0]["stop_loss_origen"] == "app"


# ── Re-armado de los avisos ───────────────────────────────────────────────────

def _alerta(db: Session, tipo: str, cartera: str, *, entregada=1, ticker="AAPL"):
    db.add(AlertaPrecio(
        ticker=ticker, tipo=tipo, cartera=cartera, estado=alertas_engine.ESTADO_DISPARADA,
        nivel=90.0, precio_disparo=89.0, moneda="USD",
        emitida_en=datetime.utcnow(), entregada=entregada,
    ))
    db.commit()


def _estado(db: Session, tipo: str, cartera="Principal", ticker="AAPL") -> AlertaPrecio:
    return (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.ticker == ticker, AlertaPrecio.tipo == tipo,
                AlertaPrecio.cartera == cartera)
        .one()
    )


def test_cambiar_el_nivel_rearma_el_aviso(db: Session):
    _posicion(db, sheet_stop=90.0)
    _alerta(db, "stop_loss", "Principal")

    niveles_analytics.aplicar_cambios(
        db, "AAPL", {"stop_loss": {"modo": "Fijo", "valor": 95.0}},
    )
    fila = _estado(db, "stop_loss")
    assert fila.estado == alertas_engine.ESTADO_ARMADA
    # La bitácora del último aviso emitido no se toca.
    assert fila.emitida_en is not None
    assert float(fila.nivel) == 90.0


def test_rearma_todas_las_carteras(db: Session):
    _posicion(db, sheet_stop=90.0)
    for cartera in ("Principal", "Segunda", "Tercera"):
        _alerta(db, "stop_loss", cartera)

    niveles_analytics.aplicar_cambios(
        db, "AAPL", {"stop_loss": {"modo": "Fijo", "valor": 95.0}},
    )
    for cartera in ("Principal", "Segunda", "Tercera"):
        assert _estado(db, "stop_loss", cartera).estado == alertas_engine.ESTADO_ARMADA


def test_no_toca_los_otros_tipos_del_mismo_ticker(db: Session):
    _posicion(db, sheet_stop=90.0)
    _alerta(db, "stop_loss", "Principal")
    _alerta(db, "objetivo", "Principal")
    _alerta(db, "compra_zona", "")
    _alerta(db, alertas_engine.tipo_senal(7), "")

    niveles_analytics.aplicar_cambios(
        db, "AAPL", {"stop_loss": {"modo": "Fijo", "valor": 95.0}},
    )
    assert _estado(db, "stop_loss").estado == alertas_engine.ESTADO_ARMADA
    assert _estado(db, "objetivo").estado == alertas_engine.ESTADO_DISPARADA
    assert _estado(db, "compra_zona", "").estado == alertas_engine.ESTADO_DISPARADA
    assert _estado(db, alertas_engine.tipo_senal(7), "").estado == alertas_engine.ESTADO_DISPARADA


def test_guardar_el_mismo_nivel_no_rearma(db: Session):
    """Un PUT que no cambia nada no tiene por qué resucitar un aviso ya emitido."""
    _posicion(db)
    _override(db, "AAPL", "stop_loss", "Fijo", 95.0)
    _alerta(db, "stop_loss", "Principal")

    niveles_analytics.aplicar_cambios(
        db, "AAPL", {"stop_loss": {"modo": "Fijo", "valor": 95.0}},
    )
    assert _estado(db, "stop_loss").estado == alertas_engine.ESTADO_DISPARADA


def test_borrar_un_override_que_coincidia_con_el_sheet_no_rearma(db: Session):
    _posicion(db, sheet_stop=95.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 95.0)
    _alerta(db, "stop_loss", "Principal")

    niveles_analytics.aplicar_cambios(db, "AAPL", {"stop_loss": None})
    assert _estado(db, "stop_loss").estado == alertas_engine.ESTADO_DISPARADA


def test_borrar_el_override_rearma_si_el_nivel_cambia(db: Session):
    _posicion(db, sheet_stop=90.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 95.0)
    _alerta(db, "stop_loss", "Principal")

    niveles_analytics.aplicar_cambios(db, "AAPL", {"stop_loss": None})
    assert _estado(db, "stop_loss").estado == alertas_engine.ESTADO_ARMADA


def test_un_aviso_pendiente_de_entrega_se_cancela(db: Session):
    """Mandaría un número que el usuario acaba de cambiar."""
    _posicion(db, sheet_stop=90.0)
    _alerta(db, "stop_loss", "Principal", entregada=0)

    niveles_analytics.aplicar_cambios(
        db, "AAPL", {"stop_loss": {"modo": "Fijo", "valor": 95.0}},
    )
    fila = _estado(db, "stop_loss")
    assert fila.estado == alertas_engine.ESTADO_ARMADA
    assert fila.entregada == 1
    assert fila.emitida_en is None


def test_sin_fila_de_alerta_no_falla(db: Session):
    """Un nivel nuevo donde nunca hubo alerta: no hay nada que re-armar."""
    _posicion(db)
    niveles, error = niveles_analytics.aplicar_cambios(
        db, "AAPL", {"objetivo": {"modo": "Fijo", "valor": 150.0}},
    )
    assert error is None
    assert niveles.objetivo.valor == 150.0


# ── Costo de la resolución ────────────────────────────────────────────────────

def test_los_overrides_no_agregan_una_consulta_por_ticker(db: Session):
    """`get_rendimiento_por_ticker` corre varias veces por request y una por cartera en cada
    corrida de alertas: una consulta por ticker se notaría."""
    for i in range(30):
        ticker = f"T{i:02d}"
        _posicion(db, ticker=ticker, sheet_stop=90.0, precio_actual=100.0)
        _override(db, ticker, "stop_loss", "Fijo", 95.0)

    consultas = []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def _contar(conn, cursor, statement, parameters, context, executemany):
        if "niveles_precio_override" in statement:
            consultas.append(statement)

    try:
        filas = inversiones_analytics.get_rendimiento_por_ticker("Principal", db)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _contar)

    assert len(filas) == 30
    assert all(f["stop_loss_origen"] == "app" for f in filas)
    assert len(consultas) == 1, f"una consulta por ticker: {len(consultas)}"


# ── Los consumidores se enteran gratis ────────────────────────────────────────
#
# Alertas y diagnóstico leen `get_rendimiento_por_ticker`, así que no hubo que tocarlos. Estos dos
# tests son los que lo demuestran: si alguno volviera a leer `instrumentos_inversion` por su
# cuenta, fallan.

def test_el_aviso_de_telegram_usa_el_nivel_de_la_app(db: Session, monkeypatch):
    mensajes = []
    monkeypatch.setattr(
        telegram, "enviar", lambda texto, parse_mode=None: (mensajes.append(texto), (True, None))[1],
    )
    # El nivel del Sheet no está cruzado; el de la app sí.
    _posicion(db, sheet_stop=90.0, precio_actual=95.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 96.0)

    resultado = alertas_analytics.evaluar_y_notificar(db)
    assert resultado["nuevas"] == 1
    assert len(mensajes) == 1
    assert "AAPL" in mensajes[0]
    assert float(_estado(db, "stop_loss").nivel) == 96.0


def test_el_sheet_solo_no_dispara_si_el_override_esta_mas_lejos(db: Session, monkeypatch):
    monkeypatch.setattr(telegram, "enviar", lambda texto, parse_mode=None: (True, None))
    # Al revés: el del Sheet estaba cruzado y el usuario bajó el stop desde la app.
    _posicion(db, sheet_stop=96.0, precio_actual=95.0)
    _override(db, "AAPL", "stop_loss", "Fijo", 90.0)

    assert alertas_analytics.evaluar_y_notificar(db)["nuevas"] == 0


def test_el_diagnostico_ve_el_nivel_de_la_app(db: Session):
    _posicion(db, sheet_stop=90.0, precio_actual=95.0)
    tipos = [h["tipo"] for h in diagnostico_analytics.get_diagnostico("Principal", db)["hallazgos"]]
    assert "stop_loss_disparado" not in tipos

    _override(db, "AAPL", "stop_loss", "Fijo", 96.0)
    tipos = [h["tipo"] for h in diagnostico_analytics.get_diagnostico("Principal", db)["hallazgos"]]
    assert "stop_loss_disparado" in tipos
