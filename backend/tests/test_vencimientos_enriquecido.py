"""Tests de la pantalla Vencimientos enriquecida (Ola 3 ítem 3).

Fijan la convención: paridad = precio / valor técnico, TIR al vencimiento y duration se
calculan sobre el flujo de caja **inferido** (mismo motor que flujo_caja_analytics) y por eso
van siempre marcadas como estimadas. No fijan los valores exactos, sí su signo / orden de
magnitud y la forma de la respuesta.
"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado,
)
from app.services.flujo_caja_analytics import get_vencimientos_completo


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _bono(db, ticker, moneda="ARS", vto_dias=400):
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


def _precio(db, ticker, precio, moneda="ARS", dias=0):
    db.add(PrecioInstrumento(
        fecha=date.today() + timedelta(days=dias), ticker=ticker, precio=precio, moneda=moneda,
    ))
    db.commit()


def _mep(db, valor=1000.0):
    db.add(IndiceMercado(fecha=date.today() - timedelta(days=800), cer=100.0, mep=valor))
    db.commit()


def test_estructura_de_respuesta(db: Session):
    out = get_vencimientos_completo("RF", db)
    assert set(out) >= {"generado", "items", "por_anio", "cartera_valor_usd", "cartera_valor_ars"}
    assert out["items"] == []
    assert out["por_anio"] == []


def test_bono_bullet_sobre_la_par(db: Session):
    _mep(db)
    _bono(db, "TX26", moneda="ARS", vto_dias=400)
    _mov(db, "TX26", "compra", dias=-540, precio=1.0, cantidad=1000)
    for d in (-540, -360, -180):
        _mov(db, "TX26", "cupon", dias=d, precio=50.0)   # 0.05 por unidad
    _precio(db, "TX26", 1.2, moneda="ARS")               # cotiza sobre la par (par = 1)
    db.commit()

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "TX26")

    assert item["metricas_estimadas"] is True
    assert item["moneda_metricas"] == "ARS"
    # paridad: precio 1.2 contra valor técnico ~1 + interés corrido -> claramente > 1
    assert item["paridad"] is not None and item["paridad"] > 1.0
    assert item["valor_residual"] == pytest.approx(1.0)
    assert item["interes_corrido"] is not None and item["interes_corrido"] >= 0
    # TIR al vencimiento definida y razonable (positiva, < 100%)
    assert item["tir_vencimiento"] is not None and 0 < item["tir_vencimiento"] < 1
    # duration modificada positiva y menor al plazo restante (~1.1 años)
    assert item["duration_modificada"] is not None and 0 < item["duration_modificada"] < 1.5
    assert item["duration_macaulay"] >= item["duration_modificada"]
    assert "precio de mercado" in (item["metricas_nota"] or "")


def test_bono_bullet_bajo_la_par(db: Session):
    _mep(db)
    _bono(db, "TX28", moneda="ARS", vto_dias=400)
    _mov(db, "TX28", "compra", dias=-540, precio=1.0, cantidad=1000)
    for d in (-540, -360, -180):
        _mov(db, "TX28", "cupon", dias=d, precio=50.0)
    _precio(db, "TX28", 0.8, moneda="ARS")               # cotiza bajo la par
    db.commit()

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "TX28")
    assert item["paridad"] is not None and item["paridad"] < 1.0


def test_m9_precio_en_escala_100_no_da_paridad_de_70(db: Session):
    # El Sheet carga el precio por lámina de 100 VN: paridad tiene que salir ~0.7, no ~70.
    _mep(db)
    _bono(db, "S100", moneda="ARS", vto_dias=400)
    _mov(db, "S100", "compra", dias=-540, precio=70.0, cantidad=1000)
    for d in (-540, -360, -180):
        _mov(db, "S100", "cupon", dias=d, precio=3000.0)          # 3.0 por unidad (par = 100)
    _mov(db, "S100", "amortizacion", dias=-360, precio=10.0, cantidad=0)  # 10% de par = 100
    _mov(db, "S100", "amortizacion", dias=-180, precio=10.0, cantidad=0)
    _precio(db, "S100", 70.0, moneda="ARS")
    db.commit()

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "S100")
    assert item["paridad"] is None or 0.3 < item["paridad"] < 3.0


def test_m9_escala_del_precio_indeterminada_no_muestra_paridad(db: Session):
    _mep(db)
    _bono(db, "AMBX", moneda="ARS", vto_dias=400)
    _mov(db, "AMBX", "compra", dias=-540, precio=2000.0, cantidad=100)
    for d in (-540, -360, -180):
        _mov(db, "AMBX", "cupon", dias=d, precio=5000.0)
    _precio(db, "AMBX", 2000.0, moneda="ARS")   # ni ~1 ni ~100: no se puede inferir el par
    db.commit()

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "AMBX")
    assert item["paridad"] is None
    assert "escala del precio" in (item["metricas_nota"] or "").lower()


def test_sin_precio_no_calcula_metricas(db: Session):
    _mep(db)
    _bono(db, "NOPX", moneda="ARS", vto_dias=200)
    _mov(db, "NOPX", "compra", dias=-400, precio=1.0, cantidad=500)
    _mov(db, "NOPX", "cupon", dias=-180, precio=25.0)
    # sin PrecioInstrumento

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "NOPX")
    assert item["tir_vencimiento"] is None
    assert item["duration_modificada"] is None
    assert item["paridad"] is None
    assert item["metricas_nota"]


def test_bono_vencido_marca_nota(db: Session):
    _mep(db)
    _bono(db, "OLD", moneda="ARS", vto_dias=-10)
    _mov(db, "OLD", "compra", dias=-400, precio=1.0, cantidad=100)
    _precio(db, "OLD", 1.0, moneda="ARS")
    db.commit()

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "OLD")
    assert item["vencido"] is True
    assert item["tir_vencimiento"] is None
    assert item["metricas_nota"] == "Instrumento vencido."


def test_b16_vencidos_fuera_del_resumen_por_anio(db: Session):
    _mep(db)
    _bono(db, "OLD", moneda="ARS", vto_dias=-10)     # ya venció
    _bono(db, "FUT", moneda="ARS", vto_dias=200)     # vence a futuro
    for t in ("OLD", "FUT"):
        _mov(db, t, "compra", dias=-400, precio=1.0, cantidad=100)
        _precio(db, t, 1.0, moneda="ARS")
    db.commit()

    out = get_vencimientos_completo("RF", db)
    assert {"OLD", "FUT"} <= {i["ticker"] for i in out["items"]}   # ambos siguen en items

    anios_tickers = {t for b in out["por_anio"] for t in b["tickers"]}
    assert "OLD" not in anios_tickers                              # el vencido no está en el resumen
    assert "FUT" in anios_tickers
    assert all(b["anio"] >= date.today().year for b in out["por_anio"])


def test_resumen_por_anio(db: Session):
    _mep(db)
    _bono(db, "A1", moneda="ARS", vto_dias=100)
    _bono(db, "A2", moneda="ARS", vto_dias=900)   # otro año calendario
    for t in ("A1", "A2"):
        _mov(db, t, "compra", dias=-300, precio=1.0, cantidad=1000)
        _precio(db, t, 1.0, moneda="ARS")
    db.commit()

    out = get_vencimientos_completo("RF", db)
    anios = {b["anio"]: b for b in out["por_anio"]}
    assert len(anios) == 2
    for b in out["por_anio"]:
        assert b["cantidad_instrumentos"] == 1
        # el peso en la cartera está entre 0 y 1 cuando hay valuación
        if b["pct_cartera_ars"] is not None:
            assert 0 <= b["pct_cartera_ars"] <= 1
    # ordenado por año ascendente
    assert [b["anio"] for b in out["por_anio"]] == sorted(anios)


def test_amortizacion_inferida_estima_residual(db: Session):
    _mep(db)
    _bono(db, "AMO", moneda="ARS", vto_dias=370)
    _mov(db, "AMO", "compra", dias=-400, precio=1.0, cantidad=1000)
    for d in (-360, -180):
        _mov(db, "AMO", "cupon", dias=d, precio=40.0)
    # dos amortizaciones semestrales ya cobradas -> quedan ~2 por delante hasta el vto
    _mov(db, "AMO", "amortizacion", dias=-360, precio=0.25, cantidad=250)
    _mov(db, "AMO", "amortizacion", dias=-180, precio=0.25, cantidad=250)
    _precio(db, "AMO", 0.6, moneda="ARS")
    db.commit()

    out = get_vencimientos_completo("RF", db)
    item = next(i for i in out["items"] if i["ticker"] == "AMO")
    assert item["valor_residual"] is not None and 0 < item["valor_residual"] <= 1.0
    assert item["paridad"] is not None
    assert "residual" in (item["metricas_nota"] or "").lower()
