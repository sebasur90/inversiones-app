"""Tests de la caché de analytics invalidada por sync (services/cache.py)."""
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, SyncRun
from app.services import cache as cache_mod
from app.services.cache import cache_por_sync, estadisticas, limpiar_cache


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _sembrar(db: Session):
    db.add(InstrumentoInversion(
        ticker="AAPL", nombre="Apple", tipo_instrumento="Accion", mercado="NASDAQ", moneda="USD",
    ))
    db.add(MovimientoInversion(
        fecha=date(2024, 1, 1), cartera="test", ticker="AAPL", tipo_movimiento="compra",
        cantidad=10.0, precio=100.0, moneda="USD", comision=0.0,
    ))
    db.add(PrecioInstrumento(fecha=date(2024, 1, 1), ticker="AAPL", precio=110.0, moneda="USD"))
    db.commit()


def _registrar_sync(db: Session):
    db.add(SyncRun(
        timestamp=datetime.now(), duration_ms=1, filas_procesadas=1, filas_validas=1,
        filas_advertencia=0, filas_error=0, health_score=100, resultado="ok",
    ))
    db.commit()


def test_segundo_llamado_no_recalcula(db: Session):
    llamadas = []

    @cache_por_sync
    def calcular(cartera, db):
        llamadas.append(cartera)
        return {"cartera": cartera, "valor": 42}

    assert calcular("test", db) == {"cartera": "test", "valor": 42}
    assert calcular("test", db) == {"cartera": "test", "valor": 42}
    assert len(llamadas) == 1
    assert estadisticas()["hits"] == 1


def test_sync_nuevo_invalida(db: Session):
    llamadas = []

    @cache_por_sync
    def calcular(cartera, db):
        llamadas.append(cartera)
        return len(llamadas)

    assert calcular("test", db) == 1
    assert calcular("test", db) == 1

    _registrar_sync(db)

    # Generación nueva: la entrada anterior ya no aplica.
    assert calcular("test", db) == 2
    assert len(llamadas) == 2


def test_params_distintos_no_comparten_entrada(db: Session):
    @cache_por_sync
    def calcular(cartera, db, moneda="USD"):
        return f"{cartera}-{moneda}"

    assert calcular("a", db) == "a-USD"
    assert calcular("b", db) == "b-USD"
    assert calcular("a", db, moneda="ARS") == "a-ARS"
    assert estadisticas()["entradas"] == 3


def test_mutar_el_resultado_no_corrompe_la_entrada(db: Session):
    @cache_por_sync
    def calcular(cartera, db):
        return {"items": [1, 2, 3]}

    primero = calcular("test", db)
    primero["items"].append(999)

    assert calcular("test", db) == {"items": [1, 2, 3]}


def test_bases_distintas_no_comparten_entrada():
    """Dos SQLite en memoria, ambas sin sync (generación 0), no deben cruzarse."""
    limpiar_cache()

    @cache_por_sync
    def calcular(cartera, db):
        return id(db.get_bind())

    engines = [create_engine("sqlite://") for _ in range(2)]
    sesiones = []
    for e in engines:
        Base.metadata.create_all(e)
        sesiones.append(Session(e))

    try:
        a = calcular("test", sesiones[0])
        b = calcular("test", sesiones[1])
        assert a != b
    finally:
        for s in sesiones:
            s.close()


def test_sin_sesion_no_cachea():
    """Si la función no recibe Session no hay generación que consultar: siempre recalcula."""
    llamadas = []

    @cache_por_sync
    def calcular(x):
        llamadas.append(x)
        return x * 2

    assert calcular(3) == 6
    assert calcular(3) == 6
    assert len(llamadas) == 2


def test_analytics_real_usa_la_cache(db: Session):
    """get_resumen decorado: el segundo llamado sale de la caché con el mismo resultado."""
    from app.services.inversiones_analytics import get_resumen

    _sembrar(db)
    limpiar_cache()

    primero = get_resumen("test", db)
    hits_antes = estadisticas()["hits"]
    segundo = get_resumen("test", db)

    assert primero == segundo
    assert estadisticas()["hits"] == hits_antes + 1


def test_lru_acota_el_tamanio(db: Session, monkeypatch):
    monkeypatch.setattr(cache_mod, "MAX_ENTRADAS", 3)
    limpiar_cache()

    @cache_por_sync
    def calcular(cartera, db):
        return cartera

    for i in range(6):
        calcular(f"c{i}", db)

    assert estadisticas()["entradas"] == 3


def test_una_escritura_invalida_aunque_no_haya_sync(db: Session):
    """Garantía de `test_bugs_calculo.test_valuacion_ve_precios_agregados_despues_de_una_lectura`:
    escribir en la sesión tiene que invalidar lo cacheado, sin esperar un SyncRun nuevo."""
    from app.services.inversiones_analytics import get_resumen

    _sembrar(db)
    limpiar_cache()

    assert get_resumen("test", db)["valor_actual_usd"] == pytest.approx(1100.0)

    db.add(PrecioInstrumento(fecha=date(2024, 2, 1), ticker="AAPL", precio=150.0, moneda="USD"))
    db.commit()

    assert get_resumen("test", db)["valor_actual_usd"] == pytest.approx(1500.0)
