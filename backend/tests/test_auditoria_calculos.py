"""Regresiones de la auditoría de cálculos del 2026-10-20.

Cada test reproduce el escenario concreto que producía un número equivocado en pantalla y fija
la convención correcta (no la implementación). Los ítems están numerados como en el plan
(`PLAN` de la auditoría): 1.x = números visiblemente mal, 2.x = inconsistencias entre
pantallas, 3.x = formato y avisos.
"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado, RebalanceoObjetivo
from app.services.inversiones_analytics import get_resumen, get_rendimiento_mensual, get_rendimiento_por_ticker
from app.services.validation import reglas_movimientos
from app.services.contribucion_analytics import get_contribucion
from app.services.opportunity_cost_analytics import get_opportunity_cost
from app.services.benchmarks_analytics import get_performance_relativa, get_performance_compare
from app.services.escenarios_analytics import simular_escenario_cartera
from app.services.inversiones_analytics import simular_rebalanceo
from app.schemas import EscenarioSimulacionRequest
from app.services.patrimonio_analytics import get_patrimonio_summary

HOY = date.today()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _instrumento(db: Session, ticker="AAPL", moneda="USD", tipo_instrumento="Accion"):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=f"{ticker} SA", tipo_instrumento=tipo_instrumento,
        mercado="TEST", moneda=moneda,
    ))
    db.commit()


def _mov(db: Session, fecha, tipo, cantidad, precio, ticker="AAPL", moneda="USD", cartera="test", comision=0.0):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento=tipo,
        cantidad=cantidad, precio=precio, moneda=moneda, comision=comision,
    ))
    db.commit()


def _precio(db: Session, fecha, precio, ticker="AAPL", moneda="USD"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda))
    db.commit()


# ── 1.1 Rendimiento simple con capital neto ≤ 0 o muy chico ─────────────────

def test_rendimiento_simple_normal_no_cambia(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _precio(db, HOY, 120.0)
    r = get_resumen("test", db)
    assert r["rendimiento_simple_usd"] == pytest.approx(0.20)
    assert r["rendimiento_no_calculable"] == {}


def test_vender_mas_de_lo_invertido_no_invierte_el_signo(db):
    """Compra 1000, el activo se triplica y se vende la mitad por 1500: neto = −500.

    Antes: (1500 + 500) / (−500) = −400% (ganancia mostrada como pérdida)."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=10), "venta", 5, 300.0)
    _precio(db, HOY, 300.0)
    r = get_resumen("test", db)
    assert r["total_invertido_usd"] == pytest.approx(-500.0)
    assert r["rendimiento_simple_usd"] is None
    assert r["rendimiento_no_calculable"]["usd"] == "capital_neto_negativo"
    assert r["valor_benchmark_usd_ars"] is None      # "si comprabas dólares" no puede ser negativo


def test_posicion_cerrada_con_ganancia_no_da_menos_100(db):
    """Cerrada con ganancia G: (0 + G) / (−G) = −100% en la fórmula vieja."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=10), "venta", 10, 150.0)
    r = get_resumen("test", db)
    assert r["rendimiento_simple_usd"] is None
    assert r["rendimiento_no_calculable"]["usd"] == "capital_neto_negativo"


def test_capital_neto_muy_chico_tampoco_se_informa(db):
    """Queda el 5% de lo comprado: cualquier ganancia se vuelve miles de %."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=10), "venta", 9.5, 100.0)
    _precio(db, HOY, 100.0)
    r = get_resumen("test", db)
    assert r["rendimiento_simple_usd"] is None
    assert r["rendimiento_no_calculable"]["usd"] == "capital_neto_chico"


def test_sin_compras_no_hay_aviso(db):
    r = get_resumen("test", db)
    assert r["rendimiento_simple_usd"] is None
    assert r["rendimiento_no_calculable"] == {}


# ── 1.3 Descomposición del período en Patrimonio ────────────────────────────

def _escenario_patrimonio(db, comision=0.0, precio_fin=100.0):
    _instrumento(db, "TEST")
    _mov(db, date(2024, 1, 10), "compra", 10, 100.0, ticker="TEST", comision=comision)
    _mov(db, date(2024, 2, 15), "dividendo", None, 50.0, ticker="TEST")
    for f, px in ((date(2024, 1, 31), 100.0), (date(2024, 2, 29), precio_fin), (date(2024, 3, 31), precio_fin)):
        _precio(db, f, px, ticker="TEST")


def test_patrimonio_cobros_no_se_restan_del_rendimiento(db):
    """Precio constante y USD 50 de dividendo: el rendimiento de mercado es 0, no −50."""
    _escenario_patrimonio(db)
    d = get_patrimonio_summary("test", db, desde=date(2024, 1, 31))["descomposicion"]
    assert d["rendimiento_usd"] == pytest.approx(0.0, abs=0.01)
    assert d["dividendos_usd"] == pytest.approx(50.0)


def test_patrimonio_variacion_del_valor_se_explica_sin_los_cobros(db):
    """Δvalor = aportes + rendimiento + otros_ajustes; los cobros no están en el valor."""
    _escenario_patrimonio(db, comision=5.0, precio_fin=110.0)
    r = get_patrimonio_summary("test", db, desde=date(2024, 1, 31))
    d = r["descomposicion"]
    delta_valor = 10 * 110.0 - 10 * 100.0   # el valor de la cartera pasa de 1000 a 1100
    assert d["aportes_usd"] + d["rendimiento_usd"] + d["otros_ajustes_usd"] == pytest.approx(delta_valor, abs=0.02)
    assert d["rendimiento_usd"] == pytest.approx(100.0, abs=0.02)    # 10 u × USD 10, bruto de comisiones


# ── 1.4 El TWR incluye dividendos y cupones ─────────────────────────────────

def _cartera_con_cupon(db, comision_cupon=0.0):
    """Posición de USD 1000 con precio constante y un cupón de USD 50 a mitad de camino."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=50), "cupon", None, 50.0, comision=comision_cupon)
    _precio(db, HOY - timedelta(days=100), 100.0)
    _precio(db, HOY, 100.0)


def test_twr_incluye_el_cupon_cobrado(db):
    """Antes el TWR daba 0% (sólo variación de precio) mientras el rendimiento simple daba +5%."""
    _cartera_con_cupon(db)
    r = get_resumen("test", db)
    assert r["rendimiento_simple_usd"] == pytest.approx(0.05)
    assert r["twr_usd"] == pytest.approx(0.05, abs=1e-4)


def test_twr_y_xirr_coinciden_con_un_solo_cupon_sin_aportes_intermedios(db):
    _cartera_con_cupon(db)
    r = get_resumen("test", db)
    assert r["twr_usd"] == pytest.approx(r["xirr_usd_periodo"], abs=0.01)


def test_twr_bruto_y_neto_con_comision_en_el_cupon(db):
    """El cupón neto de comisión baja el TWR neto; el bruto cuenta el cupón completo."""
    _cartera_con_cupon(db, comision_cupon=5.0)
    r = get_resumen("test", db)
    assert r["twr_usd"] == pytest.approx(0.045, abs=1e-4)
    assert r["twr_usd_bruto"] == pytest.approx(0.05, abs=1e-4)


def test_twr_mensual_atribuye_el_cupon_a_su_mes(db):
    _cartera_con_cupon(db)
    meses = get_rendimiento_mensual("test", db)["meses"]
    fecha_cupon = HOY - timedelta(days=50)
    del_mes = [m for m in meses if (m["anio"], m["mes"]) == (fecha_cupon.year, fecha_cupon.month)]
    assert del_mes and del_mes[0]["twr_usd"] == pytest.approx(0.05, abs=1e-3)


def test_sin_cobros_el_twr_no_cambia(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _precio(db, HOY - timedelta(days=100), 100.0)
    _precio(db, HOY, 110.0)
    assert get_resumen("test", db)["twr_usd"] == pytest.approx(0.10, abs=1e-4)


# ── 1.5 Precio promedio de Posiciones: sólo la posición abierta ─────────────

def test_precio_promedio_se_reinicia_al_cerrar_y_recomprar(db):
    """Compra a 10, vende todo, recompra a 50: el promedio de la posición abierta es 50 (no 30)."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=200), "compra", 10, 10.0)
    _mov(db, HOY - timedelta(days=150), "venta", 10, 20.0)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 50.0)
    _precio(db, HOY, 60.0)
    fila = next(f for f in get_rendimiento_por_ticker("test", db) if f["ticker"] == "AAPL")
    assert fila["precio_promedio"] == pytest.approx(50.0)


def test_precio_promedio_con_venta_parcial_no_se_mueve(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=200), "compra", 10, 10.0)
    _mov(db, HOY - timedelta(days=150), "compra", 10, 30.0)
    _mov(db, HOY - timedelta(days=100), "venta", 5, 50.0)
    _precio(db, HOY, 60.0)
    fila = next(f for f in get_rendimiento_por_ticker("test", db) if f["ticker"] == "AAPL")
    assert fila["precio_promedio"] == pytest.approx(20.0)


def test_validacion_avisa_compras_en_dos_monedas_del_mismo_ticker():
    rows = [
        (2, {"Fecha": "2024-01-01", "Cartera": "P", "Ticker": "AAPL", "Tipo Movimiento": "Compra",
             "Cantidad": "1", "Precio": "10", "Moneda": "USD"}),
        (3, {"Fecha": "2024-02-01", "Cartera": "P", "Ticker": "AAPL", "Tipo Movimiento": "Compra",
             "Cantidad": "1", "Precio": "9000", "Moneda": "ARS"}),
    ]
    validos, _, issues = reglas_movimientos.validar_movimientos(rows, {"AAPL"})
    assert len(validos) == 2                                   # advierte, no descarta
    assert any(i.regla == "moneda_mixta_en_ticker" for i in issues)


# ── 1.7 Contribución: denominador = capital neto (el del Resumen) ───────────

def _suma_contribucion_ticker(db):
    out = get_contribucion("test", db)
    eje = next(e for e in out["contribucion"] if e["eje"] == "Ticker")
    return out, sum(i["contribucion_pct"] for i in eje["items"])


def test_contribucion_reconcilia_con_el_rendimiento_del_resumen(db):
    """Compra 1000, vende la mitad a 150 (cobra 750 por 500 de costo… neto 250): P&L 500 / 250."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=50), "venta", 5, 150.0)
    _precio(db, HOY, 150.0)
    out, suma = _suma_contribucion_ticker(db)
    rendimiento = get_resumen("test", db)["rendimiento_simple_usd"]
    assert out["base_contribucion"] == "capital_neto"
    assert out["aviso_contribucion"] is None
    assert suma == pytest.approx(rendimiento * 100, abs=0.05)


def test_contribucion_con_capital_reciclado_no_se_divide_a_la_mitad(db):
    """Compra 1000, vende todo a 1100, recompra 1000: el neto es 900 (2000 − 1100), no las compras (2000)."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=200), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=150), "venta", 10, 110.0)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _precio(db, HOY, 100.0)
    out, suma = _suma_contribucion_ticker(db)
    # P&L = 100 (lo ganado en el primer ciclo) sobre 900 de capital neto = 11,11% (antes 5%)
    assert suma == pytest.approx(100 / 900 * 100, abs=0.05)
    assert suma == pytest.approx(get_resumen("test", db)["rendimiento_simple_usd"] * 100, abs=0.05)


def test_contribucion_avisa_cuando_el_capital_neto_no_sirve(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _mov(db, HOY - timedelta(days=10), "venta", 10, 150.0)
    out, _ = _suma_contribucion_ticker(db)
    assert out["base_contribucion"] == "total_comprado"
    assert out["aviso_contribucion"]


# ── 1.8 Costo de oportunidad (pantalla vieja) con la referencia en la moneda correcta ──

def _cartera_usd_con_mep(db, mep_inicial=1000.0, mep_hoy=1400.0, precio_hoy=100.0):
    _instrumento(db)
    d0 = HOY - timedelta(days=200)
    db.add(IndiceMercado(fecha=d0, mep=mep_inicial, cer=100.0))
    db.add(IndiceMercado(fecha=HOY, mep=mep_hoy, cer=140.0))
    db.commit()
    _mov(db, d0, "compra", 10, 100.0)
    _precio(db, d0, 100.0)
    _precio(db, HOY, precio_hoy)


def test_el_dolar_medido_en_dolares_no_tiene_costo_de_oportunidad(db):
    """USD 1000 con el MEP de 1000 a 1400: antes el 'valor sombra' daba 1400 'dólares' y el
    costo de oportunidad ≈ −USD 1000 aunque la cartera no se movió."""
    _cartera_usd_con_mep(db)
    r = get_opportunity_cost("test", "Dólar (MEP)", None, db)
    assert r["estado"] == "ok"
    assert r["valor_shadow_usd"] == pytest.approx(1000.0, abs=0.01)
    assert r["costo_oportunidad_usd"] == pytest.approx(0.0, abs=0.01)
    # En pesos el dólar sí subió 40%: la referencia vale 1.400.000 y la cartera (USD 1000) también.
    assert r["valor_shadow_ars"] == pytest.approx(1_400_000.0, abs=1.0)
    assert r["costo_oportunidad_ars"] == pytest.approx(0.0, abs=1.0)


def test_costo_de_oportunidad_por_posicion_usa_la_misma_cuenta(db):
    _cartera_usd_con_mep(db, precio_hoy=120.0)
    r = get_opportunity_cost("test", "Dólar (MEP)", None, db)
    pos = r["por_posicion"][0]
    assert pos["ticker"] == "AAPL"
    assert pos["valor_actual_usd"] == pytest.approx(1200.0)
    assert pos["valor_shadow_usd"] == pytest.approx(1000.0, abs=0.01)
    assert pos["costo_oportunidad_usd"] == pytest.approx(-200.0, abs=0.01)


def test_desde_no_deja_la_tenencia_previa_de_un_solo_lado(db):
    """Con `desde` posterior a la compra, la tenencia que ya tenías entra a la referencia como
    aporte inicial: si no, el valor actual la incluía y la referencia no."""
    _cartera_usd_con_mep(db)
    desde = HOY - timedelta(days=100)
    r = get_opportunity_cost("test", "Dólar (MEP)", desde, db)
    assert r["estado"] == "ok"
    assert r["valor_shadow_usd"] == pytest.approx(1000.0, abs=0.01)
    assert r["costo_oportunidad_usd"] == pytest.approx(0.0, abs=0.01)


# ── 1.9 / 2.6 Benchmarks en la moneda de la cartera y período común ─────────

def _cartera_plana_con_mep_creciente(db):
    """Cartera USD sin variación de precio durante ~8 meses; el MEP sube de 1000 a 1400."""
    _instrumento(db)
    inicio = HOY - timedelta(days=240)
    _mov(db, inicio, "compra", 10, 100.0)
    _precio(db, inicio, 100.0)
    _precio(db, HOY, 100.0)
    for i in range(0, 241, 10):
        db.add(IndiceMercado(fecha=inicio + timedelta(days=i), mep=1000.0 + i * (400.0 / 240), cer=100.0 + i))
    db.commit()


def test_el_dolar_medido_en_dolares_rinde_cero_en_performance_relativa(db):
    """Antes el dólar 'rendía' ~40% en una comparación en USD (y el costo de oportunidad salía −40pp)."""
    _cartera_plana_con_mep_creciente(db)
    r = get_performance_relativa("test", "usd", "Dólar (MEP)", None, db)
    assert r["estado"] == "ok"
    assert r["retorno_benchmark_pct"] == pytest.approx(0.0, abs=1e-6)
    assert r["retorno_cartera_pct"] == pytest.approx(0.0, abs=1e-6)


def test_el_dolar_en_pesos_si_sube(db):
    _cartera_plana_con_mep_creciente(db)
    r = get_performance_relativa("test", "ars_nominal", "Dólar (MEP)", None, db)
    assert r["estado"] == "ok"
    assert r["retorno_benchmark_pct"] > 0.2


def test_comparador_mide_cartera_y_fuentes_en_el_mismo_periodo(db):
    """El ticker sólo tiene precios los últimos ~4 meses: la cartera se mide desde ahí, no desde
    que empezó, y el comparador lo avisa."""
    _cartera_plana_con_mep_creciente(db)
    _instrumento(db, "SPY")
    for i in range(0, 121, 10):
        _precio(db, HOY - timedelta(days=120 - i), 100.0 + i, ticker="SPY")
    r = get_performance_compare("test", "usd", None, ["Dólar (MEP)"], ["SPY"], db)
    assert r["estado"] == "ok"
    assert r["advertencias"] and "se compara desde" in r["advertencias"][0]
    filas = {f["fuente"]: f for f in r["filas"]}
    assert filas["Dólar (MEP)"]["n_meses_historia"] == filas["SPY"]["n_meses_historia"]
    assert filas["Dólar (MEP)"]["retorno_pct"] == pytest.approx(0.0, abs=1e-6)


# ── 1.11 Los presets no se anulan con los valores por defecto del cliente ──

def _simular(db, escenarios):
    req = EscenarioSimulacionRequest(escenarios=escenarios)
    return {r["nombre"]: r for r in simular_escenario_cartera("test", req, db)["resultados"]}


def test_presets_alcista_y_bajista_se_diferencian_del_base(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _precio(db, HOY, 100.0)
    res = _simular(db, [
        {"tipo_preset": "personalizado", "nombre": "Base", "parametros": {"horizonte_meses": 12}},
        {"tipo_preset": "alcista", "nombre": "Alcista", "parametros": {"horizonte_meses": 12}},
        {"tipo_preset": "bajista", "nombre": "Bajista", "parametros": {"horizonte_meses": 12}},
    ])
    base, alcista, bajista = (res[n]["patrimonio_final_usd"] for n in ("Base", "Alcista", "Bajista"))
    assert alcista > base > bajista


def test_un_preset_sin_parametros_usa_los_suyos(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _precio(db, HOY, 100.0)
    res = _simular(db, [{"tipo_preset": "crisis", "nombre": "Crisis"}])
    assert res["Crisis"]["patrimonio_final_usd"] < 1000.0     # −35% anual durante 10 años


def test_editar_un_campo_de_un_preset_no_borra_el_resto(db):
    """Cambiar sólo el aporte mensual de 'alcista' sigue aplicando el +20% anual del preset."""
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 10, 100.0)
    _precio(db, HOY, 100.0)
    res = _simular(db, [
        {"tipo_preset": "alcista", "nombre": "A", "parametros": {"horizonte_meses": 12}},
        {"tipo_preset": "alcista", "nombre": "B", "parametros": {"horizonte_meses": 12, "aporte_mensual_usd": 100}},
    ])
    assert res["B"]["patrimonio_final_usd"] > res["A"]["patrimonio_final_usd"] + 1000


# ── 1.12 Rebalanceo consolidado: un ticker en dos carteras ──────────────────

def _ticker_en_dos_carteras(db):
    _instrumento(db)
    _mov(db, HOY - timedelta(days=100), "compra", 5, 100.0, cartera="A")
    _mov(db, HOY - timedelta(days=100), "compra", 5, 100.0, cartera="B")
    _precio(db, HOY, 100.0)


def test_rebalanceo_eje_ticker_suma_las_carteras(db):
    """AAPL es el 100% del consolidado (500 + 500) y el objetivo es 100%: no hay nada que comprar.
    Antes se quedaba con una sola cartera (500) y sugería comprar otros 500."""
    _ticker_en_dos_carteras(db)
    db.add(RebalanceoObjetivo(cartera=None, eje="Ticker", categoria="AAPL", porcentaje_objetivo=100))
    db.commit()
    r = simular_rebalanceo(None, db, "Ticker", "rebalanceo", 0.0, 0.0)
    item = next(i for i in r["items"] if i["posicion"] == "AAPL")
    assert item["valor_actual_usd"] == pytest.approx(1000.0)
    assert item["accion"] == "mantener"
    assert r["total_a_comprar_usd"] == pytest.approx(0.0)


def test_rebalanceo_eje_tipo_con_objetivo_propio_no_se_duplica(db):
    """Con objetivo propio de 100% para AAPL, repartido en dos carteras, no se compra por duplicado."""
    _ticker_en_dos_carteras(db)
    db.add(RebalanceoObjetivo(cartera=None, eje="Ticker", categoria="AAPL", porcentaje_objetivo=100))
    db.add(RebalanceoObjetivo(cartera=None, eje="Tipo", categoria="Accion", porcentaje_objetivo=100))
    db.commit()
    r = simular_rebalanceo(None, db, "Tipo", "rebalanceo", 0.0, 0.0)
    assert r["total_a_comprar_usd"] == pytest.approx(0.0)
    assert r["total_a_vender_usd"] == pytest.approx(0.0)
