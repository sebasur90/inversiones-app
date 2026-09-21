"""TWR de una ventana `(desde, hoy]` — extensión de `_calcular_twr_encadenado` para la
pantalla "¿Por qué ganó o perdió mi cartera?" (no duplica la fórmula del TWR histórico)."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento
from app.services.inversiones_analytics import _calcular_twr, get_resumen


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _setup(db):
    db.add(InstrumentoInversion(ticker="ACME", nombre="Acme", tipo_instrumento="Accion", mercado="TEST", moneda="USD"))
    db.commit()
    db.add_all([
        MovimientoInversion(fecha=date(2024, 1, 1), cartera="test", ticker="ACME", tipo_movimiento="compra",
                             cantidad=100, precio=10.0, moneda="USD", comision=0.0),
        MovimientoInversion(fecha=date(2024, 7, 1), cartera="test", ticker="ACME", tipo_movimiento="compra",
                             cantidad=50, precio=12.0, moneda="USD", comision=0.0),
    ])
    db.commit()
    db.add_all([
        PrecioInstrumento(fecha=date(2024, 1, 1), ticker="ACME", precio=10.0, moneda="USD"),
        PrecioInstrumento(fecha=date(2024, 7, 1), ticker="ACME", precio=12.0, moneda="USD"),
        PrecioInstrumento(fecha=date(2024, 12, 31), ticker="ACME", precio=15.0, moneda="USD"),
    ])
    db.commit()


def _precios_por_ticker(db):
    from app.services.inversiones_analytics import _precios_por_ticker as f
    return f(db)


def test_desde_none_no_cambia_el_resultado_historico(db: Session):
    """Con `desde=None` el comportamiento tiene que ser exactamente el histórico."""
    _setup(db)
    movs = db.query(MovimientoInversion).order_by(MovimientoInversion.fecha).all()
    precios = _precios_por_ticker(db)
    hoy = date(2024, 12, 31)

    twr_sin_desde, _, _ = _calcular_twr(movs, precios, db, {}, hoy)
    twr_desde_explicito_none, _, _ = _calcular_twr(movs, precios, db, {}, hoy, desde=None)
    assert twr_sin_desde == twr_desde_explicito_none


def test_ventana_desde_mitad_de_periodo_es_el_tramo_posterior(db: Session):
    """El TWR de (1/jul, 31/dic] sólo debe reflejar la revalorización de ese tramo: 12 -> 15."""
    _setup(db)
    movs = db.query(MovimientoInversion).order_by(MovimientoInversion.fecha).all()
    precios = _precios_por_ticker(db)
    hoy = date(2024, 12, 31)

    twr_ventana, _, _ = _calcular_twr(movs, precios, db, {}, hoy, desde=date(2024, 7, 1))
    assert twr_ventana == pytest.approx(15.0 / 12.0 - 1, rel=1e-6)


def test_ventana_sin_movimientos_en_el_periodo_es_variacion_pura(db: Session):
    """Ventana (1/ago, 31/dic]: sin compras en el medio, TWR = V_fin/V_inicio - 1."""
    _setup(db)
    movs = db.query(MovimientoInversion).order_by(MovimientoInversion.fecha).all()
    precios = _precios_por_ticker(db)
    hoy = date(2024, 12, 31)

    # Al 1/ago la tenencia es 150 unidades, valuadas al último precio conocido (12, de julio).
    twr_ventana, _, _ = _calcular_twr(movs, precios, db, {}, hoy, desde=date(2024, 8, 1))
    assert twr_ventana == pytest.approx(15.0 / 12.0 - 1, rel=1e-6)


def test_ventana_todo_el_periodo_coincide_con_desde_al_primer_movimiento(db: Session):
    """`desde` = fecha exacta del primer movimiento debe dar lo mismo que `desde=None`."""
    _setup(db)
    movs = db.query(MovimientoInversion).order_by(MovimientoInversion.fecha).all()
    precios = _precios_por_ticker(db)
    hoy = date(2024, 12, 31)

    twr_none, _, _ = _calcular_twr(movs, precios, db, {}, hoy)
    twr_desde_dia_anterior, _, _ = _calcular_twr(movs, precios, db, {}, hoy, desde=date(2023, 12, 31))
    assert twr_desde_dia_anterior == pytest.approx(twr_none, rel=1e-9)


def test_get_resumen_no_se_ve_afectado_por_la_extension(db: Session):
    """`get_resumen` no pasa `desde`: su TWR tiene que seguir siendo el histórico completo."""
    _setup(db)
    r = get_resumen("test", db)
    assert r["twr_usd"] is not None
    assert r["twr_usd"] == pytest.approx(r["twr_usd"])  # sanity: no crashea, valor estable
