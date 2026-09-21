"""Tests para el adaptador de "¿por qué ganó o perdió mi cartera?"
(backend/app/services/explicacion_resultado_analytics.py).

Un caso por requisito del producto: aportes, retiros, ganancias, pérdidas, dividendos,
comisiones, cambio de moneda, períodos sin movimientos — más "no disponible" en vez de
estimar, y reconciliación con Rendimiento/Contribución cuando el período es "Todo".
"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado
from app.services.explicacion_resultado_analytics import get_explicacion_resultado
from app.services.inversiones_analytics import get_resumen
from app.services.contribucion_analytics import get_contribucion

CARTERA = "test"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _inst(db, ticker, tipo="Accion", moneda="USD", mercado="TEST"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado=mercado, moneda=moneda))


def _mov(db, ticker, tipo, cantidad, precio, fecha, moneda="USD", comision=0.0):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=CARTERA, ticker=ticker, tipo_movimiento=tipo,
        cantidad=cantidad, precio=precio, moneda=moneda, comision=comision,
    ))


def _precio(db, ticker, precio, fecha, moneda="USD"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda))


def _mep(db, fecha, valor):
    db.add(IndiceMercado(fecha=fecha, mep=valor))


class TestSinDatos:
    def test_cartera_sin_movimientos(self, db: Session):
        resultado = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert resultado["estado"] == "sin_datos"
        assert resultado["resultado"]["pnl"] is None
        assert resultado["explicacion"]["frases"] == []


class TestAportes:
    def test_comprar_a_precio_de_mercado_no_es_ganancia(self, db: Session):
        """Un aporte de capital nunca debe interpretarse como rendimiento."""
        _inst(db, "AL30", tipo="Bono")
        db.commit()
        _mov(db, "AL30", "compra", 100, 10.0, date(2024, 1, 1))
        _precio(db, "AL30", 10.0, date(2024, 1, 1))  # el mismo precio hoy: sin variación
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["resultado"]["aportes"] == pytest.approx(1000.0)
        assert r["componentes"]["precio"] == pytest.approx(0.0)
        assert r["resultado"]["pnl"] == pytest.approx(0.0)


class TestRetiros:
    def test_vender_a_precio_de_mercado_no_es_perdida(self, db: Session):
        _inst(db, "GGAL")
        db.commit()
        _mov(db, "GGAL", "compra", 100, 10.0, date(2024, 1, 1))
        _mov(db, "GGAL", "venta", 100, 10.0, date(2024, 6, 1))
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["resultado"]["retiros"] == pytest.approx(1000.0)
        assert r["resultado"]["aportes"] == pytest.approx(1000.0)
        assert r["resultado"]["pnl"] == pytest.approx(0.0)


class TestGanancias:
    def test_suba_de_precio_genera_ganancia_y_contribuyente(self, db: Session):
        _inst(db, "AAPL")
        db.commit()
        _mov(db, "AAPL", "compra", 10, 100.0, date(2024, 1, 1))
        _precio(db, "AAPL", 100.0, date(2024, 1, 1))
        _precio(db, "AAPL", 142.0, date(2024, 6, 1))
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["resultado"]["pnl"] == pytest.approx(420.0)
        assert r["componentes"]["precio"] == pytest.approx(420.0)
        assert len(r["contribuyentes"]) == 1
        assert r["contribuyentes"][0]["ticker"] == "AAPL"
        assert r["detractores"] == []


class TestPerdidas:
    def test_baja_de_precio_genera_perdida_y_detractor(self, db: Session):
        _inst(db, "YPFD")
        db.commit()
        _mov(db, "YPFD", "compra", 10, 100.0, date(2024, 1, 1))
        _precio(db, "YPFD", 100.0, date(2024, 1, 1))
        _precio(db, "YPFD", 79.0, date(2024, 6, 1))
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["resultado"]["pnl"] == pytest.approx(-210.0)
        assert r["detractores"][0]["ticker"] == "YPFD"
        assert r["contribuyentes"] == []


class TestDividendos:
    def test_dividendo_no_afecta_precio_pero_suma_al_pnl(self, db: Session):
        _inst(db, "KO")
        db.commit()
        _mov(db, "KO", "compra", 10, 50.0, date(2024, 1, 1))
        _mov(db, "KO", "dividendo", None, 18.0, date(2024, 3, 1))  # $18 totales
        _precio(db, "KO", 50.0, date(2024, 1, 1))
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["componentes"]["dividendos"] == pytest.approx(18.0)
        assert r["componentes"]["precio"] == pytest.approx(0.0)
        assert r["resultado"]["pnl"] == pytest.approx(18.0)
        assert r["resultado"]["ingresos"] == pytest.approx(18.0)


class TestCupones:
    def test_cupon_de_bono_suma_al_pnl(self, db: Session):
        _inst(db, "AL30", tipo="Bono")
        db.commit()
        _mov(db, "AL30", "compra", 100, 10.0, date(2024, 1, 1))
        _mov(db, "AL30", "cupon", None, 35.0, date(2024, 6, 1))
        _precio(db, "AL30", 10.0, date(2024, 1, 1))
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["componentes"]["cupones"] == pytest.approx(35.0)
        assert r["resultado"]["pnl"] == pytest.approx(35.0)


class TestAmortizacion:
    def test_amortizacion_es_capital_devuelto(self, db: Session):
        _inst(db, "AL30", tipo="Bono")
        db.commit()
        _mov(db, "AL30", "compra", 100, 10.0, date(2024, 1, 1))
        _mov(db, "AL30", "amortizacion", 100, 10.0, date(2024, 6, 1))  # a la par
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["resultado"]["amortizaciones"] == pytest.approx(1000.0)
        assert r["resultado"]["pnl"] == pytest.approx(0.0)
        # No aparece mezclada como "retiro" (son campos separados)
        assert r["resultado"]["retiros"] == pytest.approx(0.0)


class TestComisiones:
    def test_comisiones_son_el_unico_resultado_negativo(self, db: Session):
        _inst(db, "AL30", tipo="Bono")
        db.commit()
        _mov(db, "AL30", "compra", 100, 10.0, date(2024, 1, 1), comision=10.0)
        _mov(db, "AL30", "venta", 100, 10.0, date(2024, 6, 1), comision=5.0)
        db.commit()

        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r["componentes"]["comisiones"] == pytest.approx(-15.0)
        assert r["resultado"]["pnl"] == pytest.approx(-15.0)
        assert r["componentes"]["precio"] == pytest.approx(0.0)


class TestCambioDeMoneda:
    def test_efecto_mep_solo_en_vista_ars_identidad_exacta(self, db: Session):
        _inst(db, "AAPL", moneda="USD")
        db.commit()
        _mep(db, date(2024, 1, 1), 900.0)
        _mep(db, date(2024, 6, 1), 1000.0)
        _mov(db, "AAPL", "compra", 100, 10.0, date(2024, 1, 1))
        _precio(db, "AAPL", 10.0, date(2024, 1, 1))
        _precio(db, "AAPL", 12.0, date(2024, 6, 1))
        db.commit()

        r_ars = get_explicacion_resultado(CARTERA, None, "ars", db)
        assert r_ars["fx"]["estado"] == "ok"
        # Identidad exacta: resultado_activos_ars + efecto_mep_ars == pnl en ARS.
        assert r_ars["fx"]["resultado_activos_ars"] + r_ars["fx"]["efecto_mep_ars"] == pytest.approx(
            r_ars["resultado"]["pnl"], abs=0.5
        )
        # 100 unidades pasan de 10 a 12 USD: pnl_usd = 200. resultado_activos_ars = 200 * mep_hoy (1000).
        assert r_ars["fx"]["resultado_activos_ars"] == pytest.approx(200000.0, abs=1.0)

    def test_no_aplica_en_vista_usd(self, db: Session):
        _inst(db, "AAPL", moneda="USD")
        db.commit()
        _mep(db, date(2024, 1, 1), 900.0)
        _mov(db, "AAPL", "compra", 100, 10.0, date(2024, 1, 1))
        _precio(db, "AAPL", 10.0, date(2024, 1, 1))
        db.commit()

        r_usd = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert r_usd["fx"]["estado"] == "no_aplica"
        assert r_usd["fx"]["resultado_activos_ars"] is None


class TestPeriodoSinMovimientos:
    def test_solo_variacion_de_precio_sin_flujos_en_la_ventana(self, db: Session):
        _inst(db, "AAPL")
        db.commit()
        _mov(db, "AAPL", "compra", 10, 100.0, date(2024, 1, 1))
        _precio(db, "AAPL", 100.0, date(2024, 1, 1))
        _precio(db, "AAPL", 110.0, date(2024, 6, 1))
        db.commit()

        # Ventana desde 1/mar (sin movimientos entre 1/mar y hoy): sólo revalorización.
        r = get_explicacion_resultado(CARTERA, date(2024, 3, 1), "usd", db)
        assert r["resultado"]["aportes"] == pytest.approx(0.0)
        assert r["resultado"]["retiros"] == pytest.approx(0.0)
        assert r["resultado"]["v0"] == pytest.approx(1000.0)  # 10 x 100, carry-forward desde el 1/1
        assert r["resultado"]["v1"] == pytest.approx(1100.0)
        assert r["resultado"]["pnl"] == pytest.approx(100.0)
        assert r["resultado"]["twr_pct"] == pytest.approx(10.0, abs=0.01)  # 1100/1000 - 1


class TestNoDisponible:
    def test_ticker_sin_tipo_de_cambio_queda_no_disponible_y_marca_parcial(self, db: Session):
        """Instrumento en ARS comprado antes de que exista ningún MEP cargado: en vista USD no
        se puede convertir, así que no se estima — se lista en `no_disponibles`."""
        _inst(db, "BONOARS", tipo="Bono", moneda="ARS")
        _inst(db, "AAPL", moneda="USD")
        db.commit()
        _mov(db, "BONOARS", "compra", 100, 10.0, date(2024, 1, 1), moneda="ARS")
        _mov(db, "AAPL", "compra", 10, 100.0, date(2024, 1, 1))
        _precio(db, "AAPL", 100.0, date(2024, 1, 1))
        # El primer MEP disponible es posterior al período pedido: no hay forma de convertir
        # BONOARS a USD en `desde`.
        _mep(db, date(2024, 6, 1), 1000.0)
        db.commit()

        r = get_explicacion_resultado(CARTERA, date(2024, 3, 1), "usd", db)
        assert r["estado"] == "parcial"
        tickers_no_disp = {it["ticker"] for it in r["no_disponibles"]}
        assert "BONOARS" in tickers_no_disp
        assert "AAPL" not in tickers_no_disp
        # AAPL sigue calculándose bien pese al problema de BONOARS.
        assert r["resultado"]["pnl"] is not None


class TestReconciliacionConTodo:
    def _portafolio(self, db):
        _inst(db, "AAPL")
        _inst(db, "GGAL")
        db.commit()
        _mov(db, "AAPL", "compra", 10, 100.0, date(2024, 1, 1))
        _mov(db, "GGAL", "compra", 20, 50.0, date(2024, 2, 1))
        _mov(db, "GGAL", "venta", 10, 60.0, date(2024, 5, 1))
        _precio(db, "AAPL", 100.0, date(2024, 1, 1))
        _precio(db, "AAPL", 120.0, date(2024, 6, 1))
        _precio(db, "GGAL", 50.0, date(2024, 2, 1))
        _precio(db, "GGAL", 60.0, date(2024, 5, 1))
        _precio(db, "GGAL", 55.0, date(2024, 6, 1))
        db.commit()

    def test_twr_todo_coincide_con_get_resumen(self, db: Session):
        self._portafolio(db)
        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        resumen = get_resumen(CARTERA, db)
        assert resumen["twr_usd"] is not None
        assert r["resultado"]["twr_pct"] / 100 == pytest.approx(resumen["twr_usd"], abs=1e-4)

    def test_contribucion_por_ticker_todo_coincide_con_get_contribucion(self, db: Session):
        self._portafolio(db)
        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        contrib = get_contribucion(CARTERA, db)
        eje_ticker = next(e for e in contrib["contribucion"] if e["eje"] == "Ticker")
        contrib_por_ticker = {it["etiqueta"]: it["contribucion_pct"] for it in eje_ticker["items"]}

        for it in r["por_ticker"]:
            assert it["contribucion_pct"] == pytest.approx(contrib_por_ticker[it["ticker"]], abs=0.5)

    def test_suma_por_tipo_y_por_mercado_igual_al_total(self, db: Session):
        self._portafolio(db)
        r = get_explicacion_resultado(CARTERA, None, "usd", db)
        assert sum(it["pnl"] for it in r["por_tipo"]) == pytest.approx(r["resultado"]["pnl"], abs=0.01)
        assert sum(it["pnl"] for it in r["por_mercado"]) == pytest.approx(r["resultado"]["pnl"], abs=0.01)
        assert sum(it["pnl"] for it in r["por_ticker"]) == pytest.approx(r["resultado"]["pnl"], abs=0.01)


class TestConsolidado:
    def test_moneda_invalida_lanza_value_error(self, db: Session):
        _inst(db, "AAPL")
        db.commit()
        _mov(db, "AAPL", "compra", 10, 100.0, date(2024, 1, 1))
        db.commit()
        with pytest.raises(ValueError):
            get_explicacion_resultado(CARTERA, None, "eur", db)
