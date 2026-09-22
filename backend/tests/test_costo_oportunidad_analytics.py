"""get_costo_oportunidad: adaptador Session/DB de la comparación histórica cartera vs. referencia."""
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado,
    BenchmarkValor, ConfiguracionCartera,
)
from app.services.benchmarks_analytics import BENCHMARK_DOLAR, BENCHMARK_INFLACION
from app.services.cache import limpiar_cache
from app.services.costo_oportunidad_analytics import get_costo_oportunidad

HOY = date.today()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _inst(db, ticker, moneda="USD", tipo="Accion"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="NYSE", moneda=moneda))


def _compra(db, cartera, ticker, cantidad, precio, fecha, moneda="USD"):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0,
    ))


def _precio(db, ticker, precio, fecha, moneda="USD"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda))


def _mep(db, fecha, valor):
    db.add(IndiceMercado(fecha=fecha, mep=valor))


def _cer(db, fecha, valor):
    db.add(IndiceMercado(fecha=fecha, cer=valor))


def _mep_y_cer(db, fecha, mep, cer):
    db.add(IndiceMercado(fecha=fecha, mep=mep, cer=cer))


def _mes_atras(n: int) -> date:
    """Primer día del mes, `n` meses antes del mes de hoy (n=0 -> primer día del mes actual)."""
    return (HOY.replace(day=1)) - relativedelta(months=n)


def _serie_mensual(db, fn, n_meses_atras, valor_inicial, paso):
    """Agrega `n_meses_atras+1` puntos mensuales (del más viejo al más nuevo) con `fn`."""
    for i in range(n_meses_atras, -1, -1):
        fn(db, _mes_atras(i), valor_inicial + (n_meses_atras - i) * paso)


class TestEstados:
    def test_sin_movimientos_devuelve_dict_completo(self, db: Session):
        resultado = get_costo_oportunidad("cartera-vacia", "usd", BENCHMARK_DOLAR, None, db)

        assert resultado["estado"] == "sin_movimientos"
        assert resultado["referencia"] is None
        assert resultado["serie_indices"] == []
        assert resultado["serie_valores"] == []
        assert resultado["advertencias"] == []

    def test_sin_benchmark_ni_configuracion(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        _compra(db, "test", "AAA", 10, 100.0, _mes_atras(3))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", None, None, db)

        assert resultado["estado"] == "sin_benchmark"

    def test_benchmark_sin_datos_es_datos_insuficientes(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        _compra(db, "test", "AAA", 10, 100.0, _mes_atras(3))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", "Un Benchmark Que No Existe", None, db)

        assert resultado["estado"] == "datos_insuficientes"

    def test_moneda_invalida_lanza_value_error(self, db: Session):
        with pytest.raises(ValueError):
            get_costo_oportunidad(None, "eur", BENCHMARK_DOLAR, None, db)

    def test_ars_real_sin_cer_es_datos_insuficientes(self, db: Session):
        """T2: `_calcular_twr_mensual_ars_real` devuelve `{}` en silencio si falta CER."""
        _inst(db, "AAA")
        db.commit()
        _compra(db, "test", "AAA", 10, 100.0, _mes_atras(6))
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, _mes_atras(6))
        _precio(db, "AAA", 110.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "ars_real", BENCHMARK_INFLACION, None, db)

        assert resultado["estado"] == "datos_insuficientes"


class TestCasoEspecialMonedaPropia:
    def test_dolar_mep_en_usd_da_referencia_cero(self, db: Session):
        """El control de aceptación: seguir el propio MEP valuado en USD no rinde nada."""
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _serie_mensual(db, _mep, 6, 900.0, 30.0)  # MEP sube mes a mes: no debería importar
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)

        assert resultado["estado"] == "ok"
        assert resultado["resultado_referencia_pct"] == pytest.approx(0.0, abs=1e-6)
        # Con la referencia plana, el valor final == capital neto invertido (v0 + aportes).
        esperado = resultado["valor_inicial"] + resultado["aportes_netos_periodo"]
        assert resultado["valor_final_referencia"] == pytest.approx(esperado, abs=0.01)

    def test_inflacion_cer_en_ars_real_da_referencia_cero(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        for i in range(6, -1, -1):
            _mep_y_cer(db, _mes_atras(i), 900.0 + (6 - i) * 10, 100.0 + (6 - i) * 8)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "ars_real", BENCHMARK_INFLACION, None, db)

        assert resultado["estado"] == "ok"
        assert resultado["resultado_referencia_pct"] == pytest.approx(0.0, abs=1e-6)


class TestNoSeMultiplicaPorMepCuandoNoCorresponde:
    def test_ticker_en_usd_no_se_multiplica_por_mep(self, db: Session):
        """Regresión del bug de `opportunity_cost_analytics`: un ticker en USD, valuado en
        USD, no debe moverse si cambia el MEP."""
        _inst(db, "AAA")
        _inst(db, "SPY")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 110.0, _mes_atras(0))
        _precio(db, "SPY", 100.0, compra_fecha)
        _precio(db, "SPY", 150.0, _mes_atras(0))
        _serie_mensual(db, _mep, 6, 900.0, 10.0)
        db.commit()

        resultado_1 = get_costo_oportunidad("test", "usd", "SPY", None, db)

        # Cambiar drásticamente el MEP no debería mover un resultado 100% en dólares.
        for fila in db.query(IndiceMercado).all():
            fila.mep = float(fila.mep) * 5
        db.commit()
        limpiar_cache()

        resultado_2 = get_costo_oportunidad("test", "usd", "SPY", None, db)

        assert resultado_1["resultado_referencia_pct"] == pytest.approx(resultado_2["resultado_referencia_pct"])
        assert resultado_1["valor_final_referencia"] == pytest.approx(resultado_2["valor_final_referencia"], abs=0.01)


class TestBenchmarkValorConMonedaPropia:
    def test_benchmark_valor_con_moneda_nativa_usd(self, db: Session):
        """T7: `BENCHMARK_MONEDA_NATIVA` (hoy código muerto) pasa a usarse por primera vez."""
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 110.0, _mes_atras(0))
        for i in range(6, -1, -1):
            db.add(BenchmarkValor(fecha=_mes_atras(i), benchmark="S&P 500", valor=100.0 + (6 - i) * 5))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", "S&P 500", None, db)

        assert resultado["estado"] == "ok"
        assert resultado["moneda_nativa_referencia"] == "USD"


class TestCoherenciaPctYMonetario:
    def _setup_aporte_unico(self, db: Session):
        """AAA (cartera) y SPY (referencia), con un único aporte y sin datos de SPY entre el
        ancla y la fecha del aporte (mismo nivel, vía carry-forward) para que el % y el $
        describan exactamente el mismo hecho."""
        _inst(db, "AAA")
        _inst(db, "SPY")
        db.commit()
        ancla = _mes_atras(6)  # el primer día del mes 6 atrás coincide con lo que usa _mes_atras
        compra_fecha = _mes_atras(5)  # un mes después: no hay dato nuevo de SPY en el medio
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 300.0, _mes_atras(0))
        _precio(db, "SPY", 100.0, ancla)
        _precio(db, "SPY", 150.0, _mes_atras(0))
        db.commit()
        return compra_fecha

    def test_pct_y_monetario_coherentes_con_un_solo_aporte(self, db: Session):
        self._setup_aporte_unico(db)

        resultado = get_costo_oportunidad("test", "usd", "SPY", None, db)

        assert resultado["estado"] == "ok"
        assert resultado["resultado_referencia_pct"] == pytest.approx(0.5, abs=1e-6)
        capital = resultado["valor_inicial"] + resultado["aportes_netos_periodo"]
        assert resultado["valor_final_referencia"] == pytest.approx(capital * 1.5, abs=0.01)

    def test_diferencia_pp_y_monetaria_tienen_el_mismo_signo(self, db: Session):
        """AAA triplica (200%) mientras SPY sube 50%: la cartera gana en ambas unidades."""
        self._setup_aporte_unico(db)

        resultado = get_costo_oportunidad("test", "usd", "SPY", None, db)

        assert resultado["diferencia_pp"] > 0
        assert resultado["diferencia_monetaria"] > 0


class TestAncla:
    def test_valor_inicial_entra_como_flujo_y_aportes_solo_cuentan_lo_posterior(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_previa = _mes_atras(12)   # bastante antes del período comparado
        compra_posterior = _mes_atras(3)  # dentro del período comparado
        _compra(db, "test", "AAA", 10, 50.0, compra_previa)
        _compra(db, "test", "AAA", 5, 80.0, compra_posterior)
        _serie_mensual(db, _mep, 12, 900.0, 10.0)
        _precio(db, "AAA", 50.0, compra_previa)
        _precio(db, "AAA", 90.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)

        assert resultado["estado"] == "ok"
        # El aporte de -3 meses atrás (5 * 80 = 400) sí cuenta; el de -12 meses (bien anterior
        # al período comparado) queda absorbido dentro de `valor_inicial`, no en los aportes.
        assert resultado["aportes_netos_periodo"] == pytest.approx(400.0, abs=0.01)
        assert resultado["valor_inicial"] > 0  # la tenencia previa ya valía algo en el ancla

    def test_desde_recorta_de_verdad(self, db: Session):
        """`desde` no sólo filtra flujos (lo que hacía `opportunity_cost_analytics`): tiene que
        recalcular el ancla, de forma que la compra vieja quede absorbida en `valor_inicial`
        y no se cuente de nuevo como aporte del período."""
        _inst(db, "AAA")
        db.commit()
        vieja = _mes_atras(12)
        reciente = _mes_atras(3)
        _serie_mensual(db, _mep, 14, 900.0, 10.0)
        _precio(db, "AAA", 50.0, vieja)
        _precio(db, "AAA", 90.0, _mes_atras(0))
        db.commit()

        _compra(db, "test", "AAA", 10, 50.0, vieja)
        _compra(db, "test", "AAA", 5, 80.0, reciente)
        db.commit()

        sin_desde = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)
        desde = _mes_atras(4)
        con_desde = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, desde, db)

        assert sin_desde["estado"] == "ok" and con_desde["estado"] == "ok"
        # Sin filtro: el ancla precede a la primera compra -> no había nada, todo es aporte.
        assert sin_desde["valor_inicial"] == pytest.approx(0.0, abs=0.01)
        assert sin_desde["aportes_netos_periodo"] == pytest.approx(10 * 50.0 + 5 * 80.0, abs=0.01)
        # Con `desde` después de la compra vieja: esa compra ya no es "aporte del período",
        # queda absorbida en `valor_inicial` (recorte real, no sólo un filtro de flujos).
        assert con_desde["valor_inicial"] > 0
        assert con_desde["aportes_netos_periodo"] == pytest.approx(5 * 80.0, abs=0.01)
        assert con_desde["periodo_desde"] > sin_desde["periodo_desde"]

    def test_periodo_desde_es_el_cierre_del_mes_anterior(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        # El MEP arranca antes que la compra: si arrancara el mismo día, el mes de la compra
        # quedaría fuera de la intersección de meses comunes por un desfasaje de un mes en los
        # límites (la cartera tiene un borde extra justo en la fecha de compra; la referencia
        # sólo tiene fines de mes) — caso ya presente en `get_performance_relativa`.
        _serie_mensual(db, _mep, 8, 900.0, 20.0)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)

        assert resultado["periodo_desde"] < compra_fecha
        anio, mes = compra_fecha.year, compra_fecha.month
        anio_prev, mes_prev = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
        assert resultado["periodo_desde"].year == anio_prev
        assert resultado["periodo_desde"].month == mes_prev


class TestSeriesYFechas:
    def test_serie_indices_no_tiene_fechas_futuras(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)

        assert resultado["serie_indices"], "debería haber al menos un punto"
        for punto in resultado["serie_indices"]:
            assert punto["fecha"] <= HOY


class TestAdvertencias:
    def test_advertencia_moneda_al_convertir(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        # ARS nominal: la cartera nativa es USD, pero la referencia (MEP) ya es ARS -> sin
        # conversión. Probamos el caso que sí convierte: referencia en USD, destino ARS.
        _inst(db, "SPY")
        _precio(db, "SPY", 100.0, compra_fecha)
        _precio(db, "SPY", 120.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "ars_nominal", "SPY", None, db)

        assert resultado["estado"] == "ok"
        assert any("dólar MEP" in a for a in resultado["advertencias"])

    def test_advertencia_periodo_pedido_recortado(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        pedido = _mes_atras(24)
        resultado = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, pedido, db)

        assert resultado["estado"] == "ok"
        assert resultado["periodo_pedido_desde"] == pedido
        assert any("Se pidió comparar desde" in a for a in resultado["advertencias"])

    def test_advertencia_meses_sin_tenencia_al_vender_todo(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        venta_fecha = _mes_atras(4)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        db.add(MovimientoInversion(
            fecha=venta_fecha, cartera="test", ticker="AAA", tipo_movimiento="venta",
            cantidad=10, precio=100.0, moneda="USD", comision=0.0,
        ))
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 100.0, venta_fecha)
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)

        assert resultado["estado"] == "ok"
        assert any("no tuvo posiciones" in a for a in resultado["advertencias"])


class TestCachePorSync:
    def test_no_recalcula_hasta_la_proxima_escritura(self, db: Session):
        _inst(db, "AAA")
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        r1 = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)
        r2 = get_costo_oportunidad("test", "usd", BENCHMARK_DOLAR, None, db)

        assert r1 == r2
        assert r1 is not r2  # deepcopy: no comparten identidad


class TestConfiguracionPorDefecto:
    def test_usa_benchmark_de_configuracion_cartera_si_no_se_pasa_explicito(self, db: Session):
        _inst(db, "AAA")
        db.add(ConfiguracionCartera(cartera="test", benchmark=BENCHMARK_DOLAR))
        db.commit()
        compra_fecha = _mes_atras(6)
        _compra(db, "test", "AAA", 10, 100.0, compra_fecha)
        _serie_mensual(db, _mep, 6, 900.0, 20.0)
        _precio(db, "AAA", 100.0, compra_fecha)
        _precio(db, "AAA", 115.0, _mes_atras(0))
        db.commit()

        resultado = get_costo_oportunidad("test", "usd", None, None, db)

        assert resultado["estado"] == "ok"
        assert resultado["referencia"] == BENCHMARK_DOLAR
