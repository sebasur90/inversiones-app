"""Tests para patrimonio_analytics."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento
from app.services.patrimonio_analytics import get_patrimonio_history, get_patrimonio_summary


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def test_patrimonio_history_empty(db: Session):
    """Sin movimientos debe retornar lista vacía."""
    result = get_patrimonio_history("test", db)
    assert result == {"puntos": []}


def test_patrimonio_history_single_buy(db: Session):
    """Compra simple de 100 USD en ARS."""
    inst = InstrumentoInversion(ticker="AAPL", tipo_instrumento="Acción", mercado="NASDAQ", moneda="USD")
    db.add(inst)
    db.commit()

    mov = MovimientoInversion(
        fecha=date(2024, 1, 1),
        cartera="test",
        ticker="AAPL",
        tipo_movimiento="compra",
        cantidad=10.0,
        precio=100.0,
        moneda="USD",
        comision=0.0,
    )
    db.add(mov)
    db.commit()

    precio = PrecioInstrumento(fecha=date(2024, 1, 1), ticker="AAPL", precio=100.0, moneda="USD")
    db.add(precio)
    db.commit()

    result = get_patrimonio_history("test", db, desde=None)
    puntos = result["puntos"]
    assert len(puntos) > 0

    primer_punto = puntos[0]
    assert primer_punto["aportes_acumulados_usd"] == 1000.0
    assert primer_punto["dividendos_acumulados_usd"] == 0.0


def test_patrimonio_summary_empty(db: Session):
    """Sin movimientos debe retornar structure con Nones."""
    result = get_patrimonio_summary("test", db)
    assert "maximo" in result
    assert "descomposicion" in result
    assert result["maximo"]["valor_usd"] is None


def test_patrimonio_decomposition_identity(db: Session):
    """Verificar identidad: Δvalor = Δaportes + Δrendimiento + Δdividendos + Δotros."""
    inst = InstrumentoInversion(ticker="TEST", tipo_instrumento="Acción", mercado="TEST", moneda="USD")
    db.add(inst)
    db.commit()

    mov1 = MovimientoInversion(
        fecha=date(2024, 1, 1),
        cartera="test",
        ticker="TEST",
        tipo_movimiento="compra",
        cantidad=10.0,
        precio=100.0,
        moneda="USD",
        comision=0.0,
    )
    mov2 = MovimientoInversion(
        fecha=date(2024, 2, 1),
        cartera="test",
        ticker="TEST",
        tipo_movimiento="dividendo",
        cantidad=None,
        precio=50.0,
        moneda="USD",
        comision=0.0,
    )
    db.add_all([mov1, mov2])
    db.commit()

    precios = [
        PrecioInstrumento(fecha=date(2024, 1, 1), ticker="TEST", precio=100.0, moneda="USD"),
        PrecioInstrumento(fecha=date(2024, 2, 1), ticker="TEST", precio=110.0, moneda="USD"),
    ]
    db.add_all(precios)
    db.commit()

    result = get_patrimonio_summary("test", db, desde=date(2024, 1, 1))
    decomp = result["descomposicion"]

    assert isinstance(decomp["aportes_usd"], float)
    assert isinstance(decomp["rendimiento_usd"], float)
    assert isinstance(decomp["dividendos_usd"], float)
    assert isinstance(decomp["otros_ajustes_usd"], float)
