"""Tests de integración de la capa DB-aware de 'Escenarios de vida' (defaults)."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, IndiceMercado
from app.services.vida_analytics import get_defaults_vida


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _instrumento(db: Session, ticker="AAPL", moneda="USD"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=f"{ticker} SA", tipo_instrumento="Accion", mercado="TEST", moneda=moneda))
    db.commit()


def _mov(db: Session, fecha, tipo, cantidad, precio, ticker="AAPL", moneda="USD", comision=0.0, cartera="test"):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento=tipo,
        cantidad=cantidad, precio=precio, moneda=moneda, comision=comision,
    ))
    db.commit()


def _mes_atras(n: int) -> date:
    """Fecha en el día 5 de un mes cerrado (n meses antes del actual), para que
    `calcular_ritmo` no lo excluya por ser el mes en curso."""
    hoy = date.today()
    total = hoy.year * 12 + (hoy.month - 1) - n
    anio, mes = divmod(total, 12)
    return date(anio, mes + 1, 5)


def test_defaults_sin_historia_devuelve_none_y_origen_sin_datos(db: Session):
    defaults = get_defaults_vida(None, db)

    assert defaults["patrimonio_inicial_usd"] == 0.0
    assert defaults["aporte_mensual_usd"] is None
    assert defaults["origen_aporte"] == "sin_datos"
    assert defaults["meses_historia"] == 0
    assert defaults["advertencias"] == []


def test_defaults_toma_promedio_de_aportes_de_la_cartera(db: Session):
    _instrumento(db)
    db.add(IndiceMercado(fecha=_mes_atras(3), cer=100.0, mep=1000.0))
    db.commit()

    for n in (3, 2, 1):
        _mov(db, _mes_atras(n), "compra", 10.0, 10.0, cartera="test")

    defaults = get_defaults_vida("test", db)

    assert defaults["origen_aporte"] in ("promedio_12m", "promedio_historico")
    assert defaults["aporte_mensual_usd"] == pytest.approx(100.0, abs=1e-6)
    assert defaults["meses_historia"] >= 2


def test_defaults_aporte_negativo_se_clampea_a_cero_con_advertencia(db: Session):
    _instrumento(db)
    db.add(IndiceMercado(fecha=_mes_atras(4), cer=100.0, mep=1000.0))
    db.commit()

    # Compra chica seguida de ventas grandes: neto negativo en los meses recientes.
    _mov(db, _mes_atras(4), "compra", 10.0, 10.0, cartera="test")  # +100
    for n in (3, 2, 1):
        _mov(db, _mes_atras(n), "venta", 20.0, 10.0, cartera="test")  # -200 cada mes

    defaults = get_defaults_vida("test", db)

    assert defaults["aporte_mensual_usd"] == pytest.approx(0.0, abs=1e-6)
    assert any("negativo" in a for a in defaults["advertencias"])
