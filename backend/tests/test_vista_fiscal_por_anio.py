"""Vista fiscal por año: realizado, ingresos (dividendos/cupones) y comisiones agrupados
por año calendario, en USD y ARS, con desglose por ticker."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado,
)
from app.services.inversiones_analytics import (
    get_vista_fiscal_por_anio, get_pnl_realizado_no_realizado,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _inst(db, ticker="ACME", moneda="USD", nombre="Acme Corp"):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=nombre, tipo_instrumento="Accion", mercado="TEST", moneda=moneda,
    ))
    db.commit()


def _mov(db, **kw):
    kw.setdefault("cartera", "test")
    kw.setdefault("ticker", "ACME")
    kw.setdefault("moneda", "USD")
    kw.setdefault("comision", 0.0)
    db.add(MovimientoInversion(**kw))
    db.commit()


def test_cartera_vacia_devuelve_estructura_en_cero(db: Session):
    out = get_vista_fiscal_por_anio("test", db)
    assert out["por_anio"] == []
    assert out["total"] == {
        "realizado_usd": 0.0, "realizado_ars": 0.0,
        "ingresos_usd": 0.0, "ingresos_ars": 0.0,
        "comisiones_usd": 0.0, "comisiones_ars": 0.0,
        "resultado_usd": 0.0, "resultado_ars": 0.0,
    }


def test_realizado_se_atribuye_al_anio_de_la_venta(db: Session):
    _inst(db)
    _mov(db, fecha=date(2023, 1, 10), tipo_movimiento="compra", cantidad=100, precio=10.0)
    # vende mitad en 2024 a 15 → realizado 2024 = 50*(15-10) = 250
    _mov(db, fecha=date(2024, 6, 1), tipo_movimiento="venta", cantidad=50, precio=15.0)
    # vende resto en 2025 a 20 → realizado 2025 = 50*(20-10) = 500
    _mov(db, fecha=date(2025, 3, 1), tipo_movimiento="venta", cantidad=50, precio=20.0)

    out = get_vista_fiscal_por_anio("test", db)
    anios = {a["anio"]: a for a in out["por_anio"]}

    assert set(anios) == {2024, 2025}  # 2023 sólo tuvo compras
    assert anios[2024]["realizado_usd"] == pytest.approx(250.0)
    assert anios[2025]["realizado_usd"] == pytest.approx(500.0)
    # orden: año más reciente primero
    assert [a["anio"] for a in out["por_anio"]] == [2025, 2024]
    assert out["total"]["realizado_usd"] == pytest.approx(750.0)
    assert out["total"]["resultado_usd"] == pytest.approx(750.0)


def test_dividendos_y_cupones_van_a_ingresos_del_anio(db: Session):
    _inst(db)
    _mov(db, fecha=date(2024, 1, 5), tipo_movimiento="compra", cantidad=10, precio=100.0)
    _mov(db, fecha=date(2024, 7, 1), tipo_movimiento="dividendo", cantidad=0, precio=40.0)
    _mov(db, fecha=date(2025, 7, 1), tipo_movimiento="dividendo", cantidad=0, precio=55.0)

    out = get_vista_fiscal_por_anio("test", db)
    anios = {a["anio"]: a for a in out["por_anio"]}

    assert anios[2024]["ingresos_usd"] == pytest.approx(40.0)
    assert anios[2025]["ingresos_usd"] == pytest.approx(55.0)
    assert anios[2024]["realizado_usd"] == 0.0
    assert out["total"]["ingresos_usd"] == pytest.approx(95.0)
    assert out["total"]["resultado_usd"] == pytest.approx(95.0)


def test_comisiones_por_anio_todas_las_operaciones(db: Session):
    _inst(db)
    _mov(db, fecha=date(2024, 1, 5), tipo_movimiento="compra", cantidad=10, precio=100.0, comision=3.0)
    _mov(db, fecha=date(2024, 9, 5), tipo_movimiento="venta", cantidad=5, precio=120.0, comision=2.0)
    _mov(db, fecha=date(2025, 2, 5), tipo_movimiento="venta", cantidad=5, precio=130.0, comision=1.5)

    out = get_vista_fiscal_por_anio("test", db)
    anios = {a["anio"]: a for a in out["por_anio"]}

    assert anios[2024]["comisiones_usd"] == pytest.approx(5.0)
    assert anios[2025]["comisiones_usd"] == pytest.approx(1.5)
    assert out["total"]["comisiones_usd"] == pytest.approx(6.5)
    # las comisiones NO se restan de resultado (= realizado + ingresos)
    for a in out["por_anio"]:
        assert a["resultado_usd"] == pytest.approx(a["realizado_usd"] + a["ingresos_usd"])


def test_m11b_comision_ars_se_conserva_sin_conversion_usd(db: Session):
    # Movimiento en ARS sin MEP para su fecha: monto_usd es None y la operación se saltea del
    # realizado, pero la comisión en ARS sí es calculable y no debe perderse.
    _inst(db, moneda="ARS")
    _mov(db, fecha=date(2024, 5, 1), tipo_movimiento="compra", cantidad=10, precio=1000.0,
         moneda="ARS", comision=500.0)

    out = get_vista_fiscal_por_anio("test", db)
    anios = {a["anio"]: a for a in out["por_anio"]}
    assert anios[2024]["comisiones_ars"] == pytest.approx(500.0)
    assert anios[2024]["comisiones_usd"] == 0.0
    assert out["total"]["comisiones_ars"] == pytest.approx(500.0)


def test_desglose_por_ticker_suma_al_total_del_anio(db: Session):
    _inst(db, ticker="AAA", nombre="Triple A")
    _inst(db, ticker="BBB", nombre="Triple B")
    _mov(db, ticker="AAA", fecha=date(2024, 1, 1), tipo_movimiento="compra", cantidad=10, precio=10.0)
    _mov(db, ticker="AAA", fecha=date(2024, 8, 1), tipo_movimiento="venta", cantidad=10, precio=15.0)
    _mov(db, ticker="BBB", fecha=date(2024, 2, 1), tipo_movimiento="compra", cantidad=5, precio=20.0)
    _mov(db, ticker="BBB", fecha=date(2024, 9, 1), tipo_movimiento="dividendo", cantidad=0, precio=12.0)

    out = get_vista_fiscal_por_anio("test", db)
    anio = out["por_anio"][0]
    assert anio["anio"] == 2024

    tickers = {t["ticker"]: t for t in anio["por_ticker"]}
    assert tickers["AAA"]["realizado_usd"] == pytest.approx(50.0)
    assert tickers["BBB"]["ingresos_usd"] == pytest.approx(12.0)

    suma_realizado = sum(t["realizado_usd"] for t in anio["por_ticker"])
    suma_ingresos = sum(t["ingresos_usd"] for t in anio["por_ticker"])
    assert suma_realizado == pytest.approx(anio["realizado_usd"])
    assert suma_ingresos == pytest.approx(anio["ingresos_usd"])


def test_ars_se_completa_con_mep(db: Session):
    _inst(db)
    db.add_all([
        IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0),
        IndiceMercado(fecha=date(2024, 6, 1), mep=1200.0),
    ])
    db.commit()
    _mov(db, fecha=date(2024, 1, 10), tipo_movimiento="compra", cantidad=10, precio=100.0)
    _mov(db, fecha=date(2024, 6, 10), tipo_movimiento="venta", cantidad=10, precio=150.0)

    out = get_vista_fiscal_por_anio("test", db)
    anio = out["por_anio"][0]
    # costo ARS = 1000 (USD) * 1000 = 1_000_000 ; venta ARS = 1500 * 1200 = 1_800_000
    assert anio["realizado_usd"] == pytest.approx(500.0)
    assert anio["realizado_ars"] == pytest.approx(800_000.0)


def test_identidad_con_get_pnl_realizado(db: Session):
    """La suma de realizado + ingresos de todos los años coincide con el consolidado del P&L."""
    _inst(db)
    _mov(db, fecha=date(2023, 1, 1), tipo_movimiento="compra", cantidad=100, precio=10.0, comision=1.0)
    _mov(db, fecha=date(2023, 6, 1), tipo_movimiento="dividendo", cantidad=0, precio=20.0)
    _mov(db, fecha=date(2024, 4, 1), tipo_movimiento="venta", cantidad=40, precio=14.0, comision=2.0)
    _mov(db, fecha=date(2025, 4, 1), tipo_movimiento="venta", cantidad=30, precio=9.0)
    db.add(PrecioInstrumento(fecha=date(2025, 4, 1), ticker="ACME", precio=11.0, moneda="USD"))
    db.commit()

    fiscal = get_vista_fiscal_por_anio("test", db)
    pnl = get_pnl_realizado_no_realizado("test", db)["consolidado"]

    suma_realizado = sum(a["realizado_usd"] for a in fiscal["por_anio"])
    suma_ingresos = sum(a["ingresos_usd"] for a in fiscal["por_anio"])
    assert suma_realizado == pytest.approx(pnl["realizado_usd"], abs=0.01)
    assert suma_ingresos == pytest.approx(pnl["ingresos_usd"], abs=0.01)
    assert fiscal["total"]["realizado_usd"] == pytest.approx(suma_realizado, abs=0.01)
