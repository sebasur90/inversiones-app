"""Objetivo de aporte mensual: CRUD, endpoints y su efecto sobre el ritmo de aportes.

Cubre lo que el motor puro no puede: que el objetivo sobreviva a la capa de datos, que cartera y
consolidado no se pisen, y —lo más importante— que editarlo se vea **sin sincronizar**, porque el
caché de analytics se invalida por sync y la meta la edita el usuario.
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, MovimientoInversion, InstrumentoInversion, get_db
from app.main import app
from app.services import objetivo_aporte_analytics as obj_svc
from app.services.aportes_analytics import get_ritmo_aportes


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


def _instrumento(db: Session, ticker="AAPL"):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=f"{ticker} SA", tipo_instrumento="Accion", mercado="TEST", moneda="USD"
    ))
    db.commit()


def _mov(db: Session, fecha, cantidad, precio, cartera="test", ticker="AAPL"):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda="USD", comision=0.0,
    ))
    db.commit()


# ── CRUD ─────────────────────────────────────────────────────────────────────

def test_sin_objetivo_devuelve_none(db: Session):
    assert obj_svc.get_objetivo("test", db) is None
    assert obj_svc.get_objetivo(None, db) is None


def test_guardar_y_leer(db: Session):
    guardado = obj_svc.guardar_objetivo("test", 250.0, db)
    assert guardado["monto_usd"] == 250.0
    assert guardado["retroactivo"] is False
    hoy = date.today()
    assert guardado["vigente_desde"] == f"{hoy.year:04d}-{hoy.month:02d}"
    assert obj_svc.get_objetivo("test", db)["monto_usd"] == 250.0


def test_segundo_guardado_actualiza_y_no_duplica(db: Session):
    from app.database import ObjetivoAporteMensual

    obj_svc.guardar_objetivo("test", 250.0, db)
    obj_svc.guardar_objetivo("test", 400.0, db)
    assert obj_svc.get_objetivo("test", db)["monto_usd"] == 400.0
    assert db.query(ObjetivoAporteMensual).count() == 1


def test_editar_el_monto_no_reinicia_la_vigencia(db: Session):
    """Cambiar la meta en septiembre no debe borrar el historial de cumplimiento previo."""
    obj_svc.guardar_objetivo("test", 250.0, db, hoy=date(2025, 3, 15))
    obj_svc.guardar_objetivo("test", 400.0, db, hoy=date(2025, 9, 18))
    assert obj_svc.get_objetivo("test", db)["vigente_desde"] == "2025-03"


def test_retroactivo_va_y_viene_sin_perder_la_fecha(db: Session):
    obj_svc.guardar_objetivo("test", 250.0, db, hoy=date(2025, 3, 15))
    obj_svc.guardar_objetivo("test", 250.0, db, retroactivo=True)
    assert obj_svc.get_objetivo("test", db)["retroactivo"] is True
    obj_svc.guardar_objetivo("test", 250.0, db, retroactivo=False)
    datos = obj_svc.get_objetivo("test", db)
    assert datos["retroactivo"] is False
    assert datos["vigente_desde"] == "2025-03"


def test_cartera_y_consolidado_son_independientes(db: Session):
    from app.database import ObjetivoAporteMensual

    obj_svc.guardar_objetivo("test", 250.0, db)
    obj_svc.guardar_objetivo(None, 900.0, db)
    assert obj_svc.get_objetivo("test", db)["monto_usd"] == 250.0
    assert obj_svc.get_objetivo(None, db)["monto_usd"] == 900.0
    assert db.query(ObjetivoAporteMensual).count() == 2


def test_consolidado_no_duplica_pese_al_null(db: Session):
    """SQLite considera distintos entre sí a los NULL: la unicidad la garantiza el upsert."""
    from app.database import ObjetivoAporteMensual

    obj_svc.guardar_objetivo(None, 100.0, db)
    obj_svc.guardar_objetivo(None, 200.0, db)
    assert db.query(ObjetivoAporteMensual).count() == 1
    assert obj_svc.get_objetivo(None, db)["monto_usd"] == 200.0


def test_eliminar_es_idempotente(db: Session):
    obj_svc.guardar_objetivo("test", 250.0, db)
    assert obj_svc.eliminar_objetivo("test", db) is True
    assert obj_svc.get_objetivo("test", db) is None
    assert obj_svc.eliminar_objetivo("test", db) is False


# ── Efecto sobre el ritmo de aportes ─────────────────────────────────────────

def test_el_objetivo_llega_al_payload_sin_sincronizar(db: Session):
    """El test que justifica sacar `get_ritmo_aportes` del caché: entre las dos llamadas no hay
    ningún sync, sólo una escritura del usuario."""
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)

    antes = get_ritmo_aportes("test", db)
    assert antes["progreso"]["objetivo"]["configurado"] is False

    obj_svc.guardar_objetivo("test", 150.0, db)

    despues = get_ritmo_aportes("test", db)
    assert despues["progreso"]["objetivo"]["configurado"] is True
    assert despues["progreso"]["objetivo"]["monto_usd"] == 150.0
    assert despues["progreso"]["objetivo"]["mes_actual"]["cumplido"] is True   # 200 >= 150


def test_borrar_el_objetivo_tambien_se_ve_al_instante(db: Session):
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)
    obj_svc.guardar_objetivo("test", 150.0, db)
    assert get_ritmo_aportes("test", db)["progreso"]["objetivo"]["configurado"] is True

    obj_svc.eliminar_objetivo("test", db)
    assert get_ritmo_aportes("test", db)["progreso"]["objetivo"]["configurado"] is False


def test_el_objetivo_del_consolidado_no_se_aplica_a_la_cartera(db: Session):
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0, cartera="A")
    obj_svc.guardar_objetivo(None, 900.0, db)

    assert get_ritmo_aportes("A", db)["progreso"]["objetivo"]["configurado"] is False
    assert get_ritmo_aportes(None, db)["progreso"]["objetivo"]["monto_usd"] == 900.0


# ── Endpoints ────────────────────────────────────────────────────────────────

def test_endpoints_crud_cartera(cliente):
    client, db = cliente
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)

    assert client.get("/api/inversiones/carteras/test/aportes/objetivo").status_code == 204

    r = client.put("/api/inversiones/carteras/test/aportes/objetivo", json={"monto_usd": 300})
    assert r.status_code == 200
    assert r.json()["monto_usd"] == 300.0 and r.json()["cartera"] == "test"

    assert client.get("/api/inversiones/carteras/test/aportes/objetivo").json()["monto_usd"] == 300.0
    assert client.delete("/api/inversiones/carteras/test/aportes/objetivo").status_code == 204
    assert client.get("/api/inversiones/carteras/test/aportes/objetivo").status_code == 204


def test_endpoints_crud_consolidado(cliente):
    client, db = cliente
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)

    assert client.get("/api/inversiones/consolidado/aportes/objetivo").status_code == 204
    r = client.put("/api/inversiones/consolidado/aportes/objetivo", json={"monto_usd": 500})
    assert r.status_code == 200 and r.json()["cartera"] is None
    assert client.get("/api/inversiones/consolidado/aportes/objetivo").json()["monto_usd"] == 500.0


def test_endpoint_rechaza_monto_no_positivo(cliente):
    client, db = cliente
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)
    for monto in (0, -50):
        r = client.put("/api/inversiones/carteras/test/aportes/objetivo", json={"monto_usd": monto})
        assert r.status_code == 422


def test_endpoint_cartera_inexistente(cliente):
    client, db = cliente
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)
    assert client.get("/api/inversiones/carteras/nope/aportes/objetivo").status_code == 404
    r = client.put("/api/inversiones/carteras/nope/aportes/objetivo", json={"monto_usd": 100})
    assert r.status_code == 404


def test_endpoint_ritmo_expone_el_progreso(cliente):
    client, db = cliente
    _instrumento(db)
    _mov(db, date.today().replace(day=1), 10.0, 20.0)

    datos = client.get("/api/inversiones/carteras/test/aportes/ritmo").json()
    prog = datos["progreso"]
    assert prog is not None
    assert prog["nivel"]["clave"] == "primer_paso"
    assert prog["objetivo"]["configurado"] is False
    assert prog["mision"] is not None
    assert any(l["clave"] == "primer_aporte" and l["desbloqueado"] for l in prog["logros"])


def test_endpoint_sin_datos_no_rompe_el_schema(cliente):
    """`progreso: None` tiene que validar contra `RitmoAportesOut`."""
    client, _ = cliente
    datos = client.get("/api/inversiones/consolidado/aportes/ritmo").json()
    assert datos["estado"] == "sin_datos"
    assert datos["progreso"] is None
