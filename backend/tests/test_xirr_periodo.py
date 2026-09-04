"""El XIRR sale anualizado y el TWR es acumulado del período: restarlos crudos inventaba una
brecha (el "efecto de tus aportes") que era pura diferencia de unidades. `xirr_*_periodo` lleva
el XIRR a la base del TWR."""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento
from app.services.inversiones_analytics import (
    get_resumen,
    _dias_periodo_medido,
    _xirr_a_periodo,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _setup(db, dias_atras: int):
    """Una única compra hace `dias_atras` días, con el precio subiendo 10%."""
    inicio = date.today() - timedelta(days=dias_atras)
    db.add(InstrumentoInversion(
        ticker="ACME", nombre="Acme", tipo_instrumento="Accion", mercado="TEST", moneda="USD",
    ))
    db.add(MovimientoInversion(
        fecha=inicio, cartera="test", ticker="ACME", tipo_movimiento="compra",
        cantidad=100, precio=10.0, moneda="USD", comision=0.0,
    ))
    db.add_all([
        PrecioInstrumento(fecha=inicio, ticker="ACME", precio=10.0, moneda="USD"),
        PrecioInstrumento(fecha=date.today(), ticker="ACME", precio=11.0, moneda="USD"),
    ])
    db.commit()
    return inicio


def test_xirr_periodo_es_el_xirr_desanualizado(db: Session):
    _setup(db, dias_atras=90)
    r = get_resumen("test", db)

    assert r["dias_periodo"] == 90
    esperado = (1 + r["xirr_usd"]) ** (90 / 365) - 1
    assert r["xirr_usd_periodo"] == pytest.approx(esperado, abs=1e-4)


def test_historial_corto_no_infla_el_efecto_de_aportes(db: Session):
    """Con un solo aporte no hay timing que medir: XIRR del período ≈ TWR del período.

    Contra el XIRR anualizado la brecha es grande y espuria — es lo que se estaba mostrando.
    """
    _setup(db, dias_atras=60)
    r = get_resumen("test", db)

    efecto_correcto = r["xirr_usd_periodo"] - r["twr_usd"]
    assert efecto_correcto == pytest.approx(0.0, abs=0.01)

    efecto_viejo = r["xirr_usd"] - r["twr_usd"]
    assert efecto_viejo > 0.2  # la anualización sola generaba >20 pp de "efecto"


def test_periodo_de_un_anio_deja_ambas_bases_iguales(db: Session):
    """A 365 días anualizar es la identidad: el XIRR del período coincide con el anualizado."""
    _setup(db, dias_atras=365)
    r = get_resumen("test", db)

    assert r["xirr_usd_periodo"] == pytest.approx(r["xirr_usd"], abs=1e-4)


def test_dias_periodo_arranca_en_el_primer_movimiento_de_tenencia(db: Session):
    inicio = _setup(db, dias_atras=120)
    movs = db.query(MovimientoInversion).all()

    assert _dias_periodo_medido(movs, date.today()) == (date.today() - inicio).days


def test_xirr_a_periodo_casos_borde():
    assert _xirr_a_periodo(None, 100) is None
    assert _xirr_a_periodo(0.10, 0) is None       # sin período no hay base a la que llevarlo
    assert _xirr_a_periodo(-1.5, 100) is None     # (1 + r) negativo no es exponenciable
    assert _xirr_a_periodo(0.0, 100) == pytest.approx(0.0)
