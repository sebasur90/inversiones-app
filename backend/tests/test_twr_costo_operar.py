"""TWR bruto (sin comisiones) vs. TWR neto: la brecha es el costo de operar en puntos de
retorno (Ola 5, ítem 6)."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento
from app.services.inversiones_analytics import get_resumen


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _setup(db, comision_compra=0.0, comision_venta=0.0):
    db.add(InstrumentoInversion(
        ticker="ACME", nombre="Acme", tipo_instrumento="Accion", mercado="TEST", moneda="USD",
    ))
    db.commit()
    db.add_all([
        MovimientoInversion(
            fecha=date(2024, 1, 1), cartera="test", ticker="ACME", tipo_movimiento="compra",
            cantidad=100, precio=10.0, moneda="USD", comision=comision_compra,
        ),
        MovimientoInversion(
            fecha=date(2024, 7, 1), cartera="test", ticker="ACME", tipo_movimiento="venta",
            cantidad=40, precio=13.0, moneda="USD", comision=comision_venta,
        ),
    ])
    db.commit()
    db.add_all([
        PrecioInstrumento(fecha=date(2024, 1, 1), ticker="ACME", precio=10.0, moneda="USD"),
        PrecioInstrumento(fecha=date(2024, 7, 1), ticker="ACME", precio=13.0, moneda="USD"),
        PrecioInstrumento(fecha=date(2024, 12, 1), ticker="ACME", precio=15.0, moneda="USD"),
    ])
    db.commit()


def test_sin_comisiones_bruto_igual_neto(db: Session):
    _setup(db, 0.0, 0.0)
    r = get_resumen("test", db)
    assert r["twr_usd"] is not None
    assert r["twr_usd_bruto"] == pytest.approx(r["twr_usd"])
    assert r["twr_ars_bruto"] is None or r["twr_ars"] is None or r["twr_ars_bruto"] == pytest.approx(r["twr_ars"])


def test_con_comisiones_bruto_mejor_que_neto(db: Session):
    _setup(db, comision_compra=50.0, comision_venta=20.0)
    r = get_resumen("test", db)
    assert r["twr_usd"] is not None and r["twr_usd_bruto"] is not None
    # el bruto ignora las comisiones -> rinde igual o mejor
    assert r["twr_usd_bruto"] >= r["twr_usd"] - 1e-9
    # y estrictamente mejor cuando hubo comisiones que pesan
    assert r["twr_usd_bruto"] > r["twr_usd"]
    # costo de operar = neto - bruto < 0
    assert r["twr_usd"] - r["twr_usd_bruto"] < 0


def test_campos_presentes_en_el_resumen(db: Session):
    _setup(db, 10.0, 5.0)
    r = get_resumen("test", db)
    for k in ("twr_usd_bruto", "twr_ars_bruto"):
        assert k in r
