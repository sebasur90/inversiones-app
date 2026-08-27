"""Verifica que la amortización se trate como devolución de capital de forma consistente
entre get_resumen y get_pnl_realizado_no_realizado (bug §1.5 de PLAN_BUGS_PENDIENTES.md)."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento
from app.services.inversiones_analytics import get_resumen, get_pnl_realizado_no_realizado


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def test_amortizacion_no_rompe_identidad_resumen_pnl(db: Session):
    """Δvalor (resumen) debe coincidir con realizado + no_realizado + ingresos (pnl)."""
    inst = InstrumentoInversion(ticker="BOND", nombre="Bono Test", tipo_instrumento="Bono", mercado="TEST", moneda="USD")
    db.add(inst)
    db.commit()

    mov_compra = MovimientoInversion(
        fecha=date(2024, 1, 1), cartera="test", ticker="BOND", tipo_movimiento="compra",
        cantidad=100.0, precio=10.0, moneda="USD", comision=0.0,
    )
    mov_amortizacion = MovimientoInversion(
        fecha=date(2024, 6, 1), cartera="test", ticker="BOND", tipo_movimiento="amortizacion",
        cantidad=50.0, precio=10.0, moneda="USD", comision=0.0,
    )
    db.add_all([mov_compra, mov_amortizacion])
    db.commit()

    precio = PrecioInstrumento(fecha=date(2024, 6, 1), ticker="BOND", precio=11.0, moneda="USD")
    db.add(precio)
    db.commit()

    resumen = get_resumen("test", db)
    pnl = get_pnl_realizado_no_realizado("test", db)

    delta_resumen = resumen["valor_actual_usd"] + resumen["ingresos_recibidos_usd"] - resumen["total_invertido_usd"]
    delta_pnl = pnl["consolidado"]["realizado_usd"] + pnl["consolidado"]["no_realizado_usd"] + pnl["consolidado"]["ingresos_usd"]

    assert delta_resumen == pytest.approx(delta_pnl, abs=0.01)
