"""get_concentracion ahora incluye el eje País (Ola 5, ítem 11): InstrumentoInversion.pais
estaba casi sin explotar."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado,
)
from app.services.contribucion_analytics import get_concentracion


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    # MEP para poder valuar en ARS (get_concentracion descarta posiciones sin valor en ARS).
    session.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    session.commit()
    yield session
    session.close()


def _inst(db, ticker, pais):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=ticker, tipo_instrumento="Accion", mercado="NYSE",
        moneda="USD", pais=pais,
    ))


def _pos(db, ticker, cantidad, precio):
    db.add(MovimientoInversion(
        fecha=date(2024, 1, 1), cartera="test", ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda="USD", comision=0.0,
    ))
    db.add(PrecioInstrumento(fecha=date(2024, 6, 1), ticker=ticker, precio=precio, moneda="USD"))


def test_concentracion_expone_eje_pais(db: Session):
    _inst(db, "AAA", "Estados Unidos")
    _inst(db, "BBB", "Estados Unidos")
    _inst(db, "CCC", "Brasil")
    db.commit()
    _pos(db, "AAA", 10, 50.0)   # 500
    _pos(db, "BBB", 10, 30.0)   # 300
    _pos(db, "CCC", 10, 20.0)   # 200
    db.commit()

    ejes = {c["eje"]: c for c in get_concentracion("test", db)}
    assert "País" in ejes
    pais = ejes["País"]
    assert pais["estado"] == "ok"
    assert pais["n_componentes"] == 2  # EE.UU. + Brasil
    # HHI sobre pesos 80% (EEUU: 500+300) y 20% (Brasil) = 80^2 + 20^2 = 6800
    assert pais["hhi"] == pytest.approx(6800.0, abs=1.0)


def test_concentracion_pais_bucket_sin_pais(db: Session):
    _inst(db, "AAA", "Estados Unidos")
    _inst(db, "BBB", None)
    db.commit()
    _pos(db, "AAA", 10, 50.0)
    _pos(db, "BBB", 10, 50.0)
    db.commit()

    ejes = {c["eje"]: c for c in get_concentracion("test", db)}
    pais = ejes["País"]
    # "Estados Unidos" 50% + "Sin país" 50% -> 2 componentes, HHI 5000
    assert pais["n_componentes"] == 2
    assert pais["hhi"] == pytest.approx(5000.0, abs=1.0)
    # M8: pero sólo 1 país real -> el guardrail de diversificación no debe contarlo como país.
    assert pais["n_componentes_reales"] == 1
    sector = ejes["Sector"]
    assert sector["n_componentes_reales"] == 0  # "Accion" no tiene sector -> todo "Sin sector"


def test_concentracion_n_componentes_reales_cuenta_solo_los_etiquetados(db: Session):
    _inst(db, "AAA", "Estados Unidos")
    _inst(db, "BBB", "Brasil")
    _inst(db, "CCC", None)
    db.commit()
    _pos(db, "AAA", 10, 40.0)
    _pos(db, "BBB", 10, 30.0)
    _pos(db, "CCC", 10, 30.0)
    db.commit()

    ejes = {c["eje"]: c for c in get_concentracion("test", db)}
    pais = ejes["País"]
    assert pais["n_componentes"] == 3               # EE.UU. + Brasil + "Sin país"
    assert pais["n_componentes_reales"] == 2        # sólo EE.UU. + Brasil
