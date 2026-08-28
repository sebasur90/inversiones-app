"""Tests de flujo_caja_analytics: proyección de cupones y amortizaciones de renta fija.

Fijan la convención de inferencia (periodicidad = gap mediano entre cupones cobrados; monto
por unidad = mediana de precio/tenencia), no la implementación.
"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado,
)
from app.services.flujo_caja_analytics import (
    get_flujo_caja_proyectado,
    _clasificar_periodicidad,
    _sumar_meses,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _bono(db, ticker="TX26", moneda="ARS", vto_dias=400):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=f"Bono {ticker}", tipo_instrumento="Bono",
        mercado="MERVAL", moneda=moneda,
        fecha_vencimiento=date.today() + timedelta(days=vto_dias),
    ))
    db.commit()


def _mov(db, ticker, tipo, dias, precio, cantidad=None, moneda="ARS"):
    db.add(MovimientoInversion(
        fecha=date.today() + timedelta(days=dias),
        cartera="RF", ticker=ticker, tipo_movimiento=tipo,
        cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0,
    ))
    db.commit()


def _mep(db, valor=1000.0):
    db.add(IndiceMercado(fecha=date.today() - timedelta(days=800), cer=100.0, mep=valor))
    db.commit()


# ── helpers puros ────────────────────────────────────────────────────────────

def test_clasificar_periodicidad():
    assert _clasificar_periodicidad(30) == (1, "Mensual")
    assert _clasificar_periodicidad(91) == (3, "Trimestral")
    assert _clasificar_periodicidad(182) == (6, "Semestral")
    assert _clasificar_periodicidad(365) == (12, "Anual")


def test_sumar_meses_negativo_cruza_anio():
    assert _sumar_meses(date(2026, 3, 15), -6) == date(2025, 9, 15)
    assert _sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)


# ── proyección ───────────────────────────────────────────────────────────────

def test_sin_bonos_devuelve_estructura_vacia(db: Session):
    out = get_flujo_caja_proyectado("RF", db)
    assert out["total_usd"] == 0
    assert out["instrumentos"] == []
    assert out["sin_proyeccion"] == []
    # la grilla mensual siempre cubre el horizonte completo
    assert len(out["meses"]) == out["horizonte_meses"] + 1


def test_cupon_semestral_inferido_y_bullet(db: Session):
    _mep(db)
    _bono(db, "TX26", moneda="ARS", vto_dias=400)
    _mov(db, "TX26", "compra", dias=-540, precio=1.0, cantidad=1000)
    # tres cupones, ~180 días de gap, tenencia constante 1000 -> 0.05 por unidad
    for d in (-540, -360, -180):
        _mov(db, "TX26", "cupon", dias=d, precio=50.0)
    # precio de mercado para estimar el capital bullet
    db.add(PrecioInstrumento(fecha=date.today(), ticker="TX26", precio=1.2, moneda="ARS"))
    db.commit()

    out = get_flujo_caja_proyectado("RF", db)
    assert len(out["instrumentos"]) == 1
    inst = out["instrumentos"][0]
    assert inst["periodicidad_meses"] == 6
    assert inst["periodicidad_label"] == "Semestral"
    assert inst["confianza"] == "alta"
    assert inst["cupon_por_unidad"] == pytest.approx(0.05, rel=1e-6)
    assert inst["metodo_capital"] == "bullet"

    # 0.05 ARS/unidad * tenencia actual 1000 = 50 ARS por cupón (igual al histórico)
    cupones = [
        d for mes in out["meses"] for d in mes["detalle"]
        if d["tipo"] == "cupon"
    ]
    assert cupones, "debería proyectar al menos un cupón"
    assert all(c["monto_nativo"] == pytest.approx(50.0) for c in cupones)
    # conversión a USD con MEP 1000
    assert all(c["monto_usd"] == pytest.approx(0.05) for c in cupones)

    # un único evento de amortización (bullet), el día del vencimiento
    amorts = [
        (mes["periodo"], d) for mes in out["meses"] for d in mes["detalle"]
        if d["tipo"] == "amortizacion"
    ]
    assert len(amorts) == 1
    venc = date.today() + timedelta(days=400)
    assert amorts[0][0] == venc.strftime("%Y-%m")
    assert amorts[0][1]["monto_nativo"] == pytest.approx(1.2 * 1000)


def test_cupon_alineado_al_vencimiento(db: Session):
    """La grilla de cupones se ancla al vencimiento, no al último cupón cobrado."""
    _mep(db)
    _bono(db, "AL30", moneda="USD", vto_dias=370)
    _mov(db, "AL30", "compra", dias=-400, precio=50.0, cantidad=100, moneda="USD")
    for d in (-360, -180):
        _mov(db, "AL30", "cupon", dias=d, precio=100.0, moneda="USD")  # 1 USD por unidad
    db.add(PrecioInstrumento(fecha=date.today(), ticker="AL30", precio=60.0, moneda="USD"))
    db.commit()

    out = get_flujo_caja_proyectado("RF", db)
    venc = date.today() + timedelta(days=370)
    periodos_cupon = {
        mes["periodo"] for mes in out["meses"]
        for d in mes["detalle"] if d["tipo"] == "cupon"
    }
    # hay un cupón que cae exactamente en el mes del vencimiento
    assert venc.strftime("%Y-%m") in periodos_cupon


def test_amortizacion_inferida(db: Session):
    _mep(db)
    _bono(db, "TZXD7", moneda="ARS", vto_dias=400)
    _mov(db, "TZXD7", "compra", dias=-400, precio=1.0, cantidad=1000)
    # dos amortizaciones trimestrales del 10% del par (0.1 por unidad, escala par = 1)
    _mov(db, "TZXD7", "amortizacion", dias=-180, precio=0.1, cantidad=100)
    _mov(db, "TZXD7", "amortizacion", dias=-90, precio=0.1, cantidad=100)
    db.add(PrecioInstrumento(fecha=date.today(), ticker="TZXD7", precio=1.0, moneda="ARS"))
    db.commit()

    out = get_flujo_caja_proyectado("RF", db)
    inst = out["instrumentos"][0]
    assert inst["metodo_capital"] == "amortizacion_inferida"
    amorts = [
        d for mes in out["meses"] for d in mes["detalle"] if d["tipo"] == "amortizacion"
    ]
    assert amorts
    # 0.1/unidad * tenencia actual (1000 - 200 amortizadas = 800)
    assert all(a["monto_nativo"] == pytest.approx(80.0) for a in amorts)


def test_a6_amort_futuras_topeadas_al_capital_restante(db: Session):
    # Bono con período de gracia: 2 cuotas históricas del 10% del par -> total 10 cuotas ->
    # como máximo 8 futuras, aunque la grilla trimestral hasta el vto tenga más lugares.
    _mep(db)
    _bono(db, "GRACIA", moneda="ARS", vto_dias=365 * 4)
    _mov(db, "GRACIA", "compra", dias=-800, precio=1.0, cantidad=1000)
    _mov(db, "GRACIA", "amortizacion", dias=-180, precio=0.1, cantidad=0)
    _mov(db, "GRACIA", "amortizacion", dias=-90, precio=0.1, cantidad=0)
    _mov(db, "GRACIA", "cupon", dias=-180, precio=30.0)
    _mov(db, "GRACIA", "cupon", dias=-90, precio=30.0)
    db.add(PrecioInstrumento(fecha=date.today(), ticker="GRACIA", precio=0.9, moneda="ARS"))
    db.commit()

    out = get_flujo_caja_proyectado("RF", db)
    inst = next(i for i in out["instrumentos"] if i["ticker"] == "GRACIA")
    assert inst["metodo_capital"] == "amortizacion_inferida"
    assert inst["amort_futuras"] <= 8


def test_a6_amort_sin_escala_degrada_a_bullet(db: Session):
    # amortización 10 ARS/unidad con precio ~1: no se puede estimar qué fracción del par es
    # (escala desconocida) -> se degrada a bullet en vez de proyectar una serie sin tope.
    _mep(db)
    _bono(db, "ESCX", moneda="ARS", vto_dias=400)
    _mov(db, "ESCX", "compra", dias=-400, precio=1.0, cantidad=1000)
    _mov(db, "ESCX", "amortizacion", dias=-180, precio=10.0, cantidad=100)
    _mov(db, "ESCX", "amortizacion", dias=-90, precio=10.0, cantidad=100)
    _mov(db, "ESCX", "cupon", dias=-180, precio=30.0)
    _mov(db, "ESCX", "cupon", dias=-90, precio=30.0)
    db.add(PrecioInstrumento(fecha=date.today(), ticker="ESCX", precio=1.0, moneda="ARS"))
    db.commit()

    out = get_flujo_caja_proyectado("RF", db)
    inst = next(i for i in out["instrumentos"] if i["ticker"] == "ESCX")
    assert inst["metodo_capital"] == "bullet"
    assert inst["amort_futuras"] == 0


def test_bono_sin_cupones_ni_precio_va_a_sin_proyeccion(db: Session):
    _mep(db)
    _bono(db, "XXXX", moneda="ARS", vto_dias=300)
    _mov(db, "XXXX", "compra", dias=-100, precio=1.0, cantidad=500)
    # sin cupones, sin PrecioInstrumento

    out = get_flujo_caja_proyectado("RF", db)
    assert out["instrumentos"] == []
    assert len(out["sin_proyeccion"]) == 1
    assert out["sin_proyeccion"][0]["ticker"] == "XXXX"


def test_bono_vencido_se_ignora(db: Session):
    _mep(db)
    _bono(db, "OLD", moneda="ARS", vto_dias=-10)
    _mov(db, "OLD", "compra", dias=-400, precio=1.0, cantidad=100)
    _mov(db, "OLD", "cupon", dias=-200, precio=5.0)

    out = get_flujo_caja_proyectado("RF", db)
    assert out["instrumentos"] == []
    assert out["sin_proyeccion"] == []


def test_totales_cuadran_con_la_grilla(db: Session):
    _mep(db)
    _bono(db, "TX26", moneda="ARS", vto_dias=400)
    _mov(db, "TX26", "compra", dias=-540, precio=1.0, cantidad=1000)
    for d in (-540, -360, -180):
        _mov(db, "TX26", "cupon", dias=d, precio=50.0)
    db.add(PrecioInstrumento(fecha=date.today(), ticker="TX26", precio=1.2, moneda="ARS"))
    db.commit()

    out = get_flujo_caja_proyectado("RF", db)
    suma_meses = sum(mes["total_usd"] for mes in out["meses"])
    assert suma_meses == pytest.approx(out["total_usd"], rel=1e-6)
    assert out["total_usd"] == pytest.approx(
        out["total_cupones_usd"] + out["total_amortizaciones_usd"], rel=1e-6
    )
