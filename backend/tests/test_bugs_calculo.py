"""Regresiones de los bugs de cálculo detectados en la revisión del 2026-08-27 (bloque §A).

Cada test fija la convención que el bug rompía, no la implementación: si mañana se refactorea
el recorrido de movimientos, estos siguen valiendo.
"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado,
)
from app.services.inversiones_analytics import (
    get_rendimiento_por_ticker,
    get_pnl_realizado_no_realizado,
    get_aportes_historicos,
    get_vencimientos,
    get_exposicion,
    get_resumen,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _instrumento(db: Session, ticker="AAPL", moneda="USD", tipo_instrumento="Accion", **kwargs):
    inst = InstrumentoInversion(
        ticker=ticker, nombre=f"{ticker} SA", tipo_instrumento=tipo_instrumento,
        mercado="TEST", moneda=moneda, **kwargs,
    )
    db.add(inst)
    db.commit()
    return inst


def _mov(db: Session, fecha, tipo, cantidad, precio, ticker="AAPL", moneda="USD", comision=0.0):
    db.add(MovimientoInversion(
        fecha=fecha, cartera="test", ticker=ticker, tipo_movimiento=tipo,
        cantidad=cantidad, precio=precio, moneda=moneda, comision=comision,
    ))
    db.commit()


def _precio(db: Session, fecha, precio, ticker="AAPL", moneda="USD"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda))
    db.commit()


# ── A1: costo remanente tras ventas y amortizaciones parciales ───────────────

def test_venta_parcial_usa_costo_remanente(db: Session):
    """Vendida la mitad a 12, el remanente se compara contra su propio costo (500), no contra 1000."""
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0)
    _mov(db, date(2024, 6, 1), "venta", 50.0, 12.0)
    _precio(db, date(2024, 6, 1), 12.0)

    item = get_rendimiento_por_ticker("test", db)[0]

    assert item["cantidad_actual"] == pytest.approx(50.0)
    assert item["valor_invertido_usd"] == pytest.approx(500.0)  # antes: 1000.0
    assert item["valor_actual_usd"] == pytest.approx(600.0)
    assert item["rendimiento_simple_usd"] == pytest.approx(0.20)  # antes: -0.40


def test_amortizacion_parcial_usa_costo_remanente(db: Session):
    """Una amortización devuelve capital: baja la tenencia y su costo en la misma proporción."""
    _instrumento(db, ticker="BOND", tipo_instrumento="Bono")
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0, ticker="BOND")
    _mov(db, date(2024, 6, 1), "amortizacion", 40.0, 10.0, ticker="BOND")
    _precio(db, date(2024, 6, 1), 10.0, ticker="BOND")

    item = get_rendimiento_por_ticker("test", db)[0]

    assert item["cantidad_actual"] == pytest.approx(60.0)
    assert item["valor_invertido_usd"] == pytest.approx(600.0)
    assert item["rendimiento_simple_usd"] == pytest.approx(0.0)  # antes: -0.40


def test_rendimiento_por_ticker_coincide_con_pnl(db: Session):
    """El costo remanente es el mismo que usa get_pnl_realizado_no_realizado."""
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0)
    _mov(db, date(2024, 3, 1), "compra", 50.0, 12.0)
    _mov(db, date(2024, 6, 1), "venta", 60.0, 15.0)
    _precio(db, date(2024, 6, 1), 15.0)

    item = get_rendimiento_por_ticker("test", db)[0]
    pnl = next(p for p in get_pnl_realizado_no_realizado("test", db)["por_ticker"] if p["ticker"] == "AAPL")

    # no_realizado = valor de mercado del remanente - su costo remanente
    assert pnl["no_realizado_usd"] == pytest.approx(
        item["valor_actual_usd"] - item["valor_invertido_usd"], abs=0.01
    )


def test_ingresos_cuentan_en_el_rendimiento_del_ticker(db: Session):
    """Un dividendo cobrado es parte del retorno de la posición."""
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0)
    _mov(db, date(2024, 3, 1), "dividendo", 0.0, 50.0)
    _precio(db, date(2024, 6, 1), 10.0)

    item = get_rendimiento_por_ticker("test", db)[0]

    # valor 1000 + dividendo 50 - costo 1000 = 50 sobre 1000
    assert item["rendimiento_simple_usd"] == pytest.approx(0.05)


# ── A2: los dividendos no son aportes de capital ─────────────────────────────

def test_dividendo_reinvertido_no_cuenta_dos_veces(db: Session):
    """Cobrar 100 y reinvertirlos aporta 0 neto, no 200."""
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 10.0, 10.0)          # aporte real: 100
    _mov(db, date(2024, 2, 1), "dividendo", 0.0, 100.0)        # ingreso, no aporte
    _mov(db, date(2024, 2, 2), "compra", 10.0, 10.0)           # reinversión: 100

    curva = get_aportes_historicos("test", db)["curva"]

    assert curva[-1]["aportes_netos_acumulados"] == pytest.approx(200.0)  # antes: 300.0


def test_venta_reduce_los_aportes_acumulados(db: Session):
    """Vender devuelve capital: baja el aporte neto."""
    _instrumento(db)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0)
    _mov(db, date(2024, 6, 1), "venta", 50.0, 10.0)

    curva = get_aportes_historicos("test", db)["curva"]

    assert curva[-1]["aportes_netos_acumulados"] == pytest.approx(500.0)


# ── A3: el ajuste por CER usa la fecha de cada compra ────────────────────────

def test_precio_promedio_cer_pondera_cada_compra(db: Session):
    """Dos compras con CER distinto: el promedio deflactado usa el CER de cada una."""
    _instrumento(db, ticker="BONO", moneda="ARS")
    db.add_all([
        IndiceMercado(fecha=date(2024, 1, 1), cer=100.0, mep=1000.0),
        IndiceMercado(fecha=date(2024, 6, 1), cer=200.0, mep=1000.0),
    ])
    db.commit()

    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0, ticker="BONO", moneda="ARS")
    _mov(db, date(2024, 6, 1), "compra", 100.0, 20.0, ticker="BONO", moneda="ARS")
    _precio(db, date(2024, 6, 1), 20.0, ticker="BONO", moneda="ARS")

    item = get_rendimiento_por_ticker("test", db)[0]

    # CER hoy = 200 (carry-forward). Compra 1: 10 * 200/100 = 20. Compra 2: 20 * 200/200 = 20.
    # Promedio ponderado por cantidad (100 y 100) = 20.
    # Con el bug, ambas usaban el CER de la primera compra: (10+20)/2 * 2 = 30.
    assert item["precio_promedio_ars_ajustado_cer"] == pytest.approx(20.0)
    assert item["rendimiento_simple_ars_real"] == pytest.approx(0.0)


# ── A4: los vencimientos no dependen de que haya precio ──────────────────────

def test_vencimiento_aparece_sin_precio_cargado(db: Session):
    """Un bono con tenencia y vencimiento se informa aunque no tenga cotización."""
    vence = date.today() + timedelta(days=90)
    _instrumento(db, ticker="BONOX", tipo_instrumento="Bono", fecha_vencimiento=vence)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0, ticker="BONOX")
    # sin PrecioInstrumento a propósito

    items = get_vencimientos("test", db)

    assert len(items) == 1
    assert items[0]["ticker"] == "BONOX"
    assert items[0]["cantidad_actual"] == pytest.approx(100.0)
    assert items[0]["valor_actual_usd"] is None
    assert items[0]["dias_restantes"] == 90


def test_vencimiento_con_precio_reporta_valor(db: Session):
    """Con cotización disponible, el valor se completa."""
    vence = date.today() + timedelta(days=30)
    _instrumento(db, ticker="BONOY", tipo_instrumento="Bono", fecha_vencimiento=vence)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0, ticker="BONOY")
    _precio(db, date(2024, 1, 1), 11.0, ticker="BONOY")

    items = get_vencimientos("test", db)

    assert items[0]["valor_actual_usd"] == pytest.approx(1100.0)


def test_vencimiento_ignora_posicion_cerrada(db: Session):
    """Si ya no queda tenencia, el vencimiento no se informa."""
    vence = date.today() + timedelta(days=30)
    _instrumento(db, ticker="BONOZ", tipo_instrumento="Bono", fecha_vencimiento=vence)
    _mov(db, date(2024, 1, 1), "compra", 100.0, 10.0, ticker="BONOZ")
    _mov(db, date(2024, 2, 1), "venta", 100.0, 10.0, ticker="BONOZ")

    assert get_vencimientos("test", db) == []


# ── A5: TWR con un único movimiento hecho hoy ────────────────────────────────

def test_twr_no_inventa_perdida_con_una_compra_de_hoy(db: Session):
    """Una sola compra hecha hoy no tiene período medible: TWR None, no -100%."""
    hoy = date.today()
    _instrumento(db)
    _mov(db, hoy, "compra", 100.0, 10.0)
    _precio(db, hoy, 10.0)

    resumen = get_resumen("test", db)

    assert resumen["twr_usd"] is None  # antes: ≈ -1.0
    assert resumen["valor_actual_usd"] == pytest.approx(1000.0)


# ── A6: sin cotización en ARS la posición no suma 0 ──────────────────────────

def test_posicion_sin_mep_no_se_reporta_con_ars_cero(db: Session):
    """Sin MEP la posición en USD no se puede pasar a pesos: se descarta, no se informa en 0."""
    _instrumento(db, ticker="USDSTOCK", moneda="USD")
    _mov(db, date(2024, 1, 1), "compra", 10.0, 100.0, ticker="USDSTOCK", moneda="USD")
    _precio(db, date(2024, 1, 1), 100.0, ticker="USDSTOCK", moneda="USD")
    # sin IndiceMercado a propósito: no hay tipo de cambio para convertir a ARS

    ejes = get_exposicion("test", db)["ejes"]

    # Antes se informaba USDSTOCK con valor_usd=1000 y valor_ars=0, hundiendo el total en pesos
    todos = [it for eje in ejes for it in eje["items"]]
    assert not any(it["valor_usd"] > 0 and it["valor_ars"] == 0 for it in todos)


def test_posicion_con_mep_se_valua_en_ambas_monedas(db: Session):
    """Con MEP cargado, la misma posición sí se reporta, en USD y en ARS."""
    _instrumento(db, ticker="USDSTOCK", moneda="USD")
    db.add(IndiceMercado(fecha=date(2024, 1, 1), cer=100.0, mep=1000.0))
    db.commit()
    _mov(db, date(2024, 1, 1), "compra", 10.0, 100.0, ticker="USDSTOCK", moneda="USD")
    _precio(db, date(2024, 1, 1), 100.0, ticker="USDSTOCK", moneda="USD")

    ejes = {e["eje"]: e["items"] for e in get_exposicion("test", db)["ejes"]}
    ticker = next(it for it in ejes["Ticker"] if it["etiqueta"] == "USDSTOCK")

    assert ticker["valor_usd"] == pytest.approx(1000.0)
    assert ticker["valor_ars"] == pytest.approx(1_000_000.0)
