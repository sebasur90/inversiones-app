"""Tests numéricos del motor puro de la propuesta de rebalanceo (rebalanceo_engine.py).

Los valores esperados se calculan a mano en los comentarios de cada test, como referencia
manual de verificación (no se reimplementa la fórmula bajo test).
"""
import pytest

from app.services import rebalanceo_engine
from app.services.rebalanceo_engine import PosicionActual, generar_propuesta


def _item(items, ticker=None, categoria=None):
    for it in items:
        if (ticker is None or it.posicion == ticker) and (categoria is None or it.categoria == categoria):
            if ticker is not None or categoria is not None:
                return it
    raise AssertionError(f"No se encontró item ticker={ticker} categoria={categoria}")


# ── Prorrateo intra-categoría ─────────────────────────────────────────────────

def test_prorrateo_compra_proporcional_al_valor_actual():
    # Acciones: actual 200 (AAA 100, BBB 100), objetivo 50% de 1000 = 500 -> falta 300,
    # repartido 50/50 (mismo valor actual) = +150 cada uno.
    posiciones = [
        PosicionActual("AAA", "Acciones", 100.0),
        PosicionActual("BBB", "Acciones", 100.0),
        PosicionActual("CCC", "Bonos", 800.0),
    ]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"Acciones": 50.0, "Bonos": 50.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )

    aaa = _item(resultado.items, ticker="AAA")
    bbb = _item(resultado.items, ticker="BBB")
    assert aaa.importe_sugerido_usd == pytest.approx(150.0)
    assert bbb.importe_sugerido_usd == pytest.approx(150.0)
    assert aaa.accion == "comprar"
    assert aaa.necesidad == "necesario"  # delta_pp categoría = 50-20 = 30 > 2


def test_prorrateo_venta_categoria_con_un_solo_ticker():
    # Bonos: actual 800 (solo CCC), objetivo 50% de 1000 = 500 -> sobran 300, vender todo en CCC.
    posiciones = [PosicionActual("CCC", "Bonos", 800.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"Bonos": 50.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )
    ccc = _item(resultado.items, ticker="CCC")
    assert ccc.importe_sugerido_usd == pytest.approx(-300.0)
    assert ccc.accion == "vender"


# ── Override por ticker dentro de una categoría ───────────────────────────────

def test_objetivo_propio_de_ticker_prioriza_sobre_categoria():
    # Categoria Acciones: AAA=100, BBB=300 (actual 400), objetivo categoría 40% de 1000 = 400
    # (delta categoría = 0). AAA tiene objetivo propio 15% (=150, +50). El remanente de la
    # categoría (0 - 50 = -50) se prorratea sobre BBB (único sin override): BBB -50.
    posiciones = [
        PosicionActual("AAA", "Acciones", 100.0),
        PosicionActual("BBB", "Acciones", 300.0),
    ]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"Acciones": 40.0},
        objetivos_ticker={"AAA": 15.0},
        eje="Tipo",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )
    aaa = _item(resultado.items, ticker="AAA")
    bbb = _item(resultado.items, ticker="BBB")
    assert aaa.importe_sugerido_usd == pytest.approx(50.0)
    assert aaa.accion == "comprar"
    assert bbb.importe_sugerido_usd == pytest.approx(-50.0)
    assert bbb.accion == "vender"
    assert bbb.necesidad == "opcional"  # delta_pp categoría = 40-40 = 0


# ── Categoría objetivo sin instrumentos en cartera ────────────────────────────

def test_categoria_sin_instrumento_no_inventa_ticker():
    resultado = generar_propuesta(
        posiciones=[],
        objetivos_categoria={"Cripto": 10.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )
    assert len(resultado.items) == 1
    item = resultado.items[0]
    assert item.tipo == "categoria_sin_instrumento"
    assert item.posicion is None
    assert item.importe_sugerido_usd == pytest.approx(100.0)
    assert item.accion == "comprar"


# ── Corte necesario / opcional en el límite de tolerancia ────────────────────

def test_necesidad_en_el_limite_exacto_de_tolerancia_es_opcional():
    # peso_actual 48%, objetivo 50%, delta_pp = 2.0 == tolerancia -> opcional (no estrictamente mayor)
    posiciones = [PosicionActual("AAA", "AAA", 4800.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"AAA": 50.0},
        objetivos_ticker={"AAA": 50.0},
        eje="Ticker",
        total_usd=10000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )
    item = _item(resultado.items, ticker="AAA")
    assert item.delta_pp == pytest.approx(2.0)
    assert item.necesidad == "opcional"


def test_necesidad_por_encima_de_tolerancia_es_necesario():
    posiciones = [PosicionActual("AAA", "AAA", 4790.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"AAA": 50.0},
        objetivos_ticker={"AAA": 50.0},
        eje="Ticker",
        total_usd=10000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )
    item = _item(resultado.items, ticker="AAA")
    assert item.delta_pp == pytest.approx(2.1)
    assert item.necesidad == "necesario"


# ── Modo "solo aportes" ────────────────────────────────────────────────────────

def test_solo_aportes_alcanza_a_cerrar_todas_las_brechas():
    # total_usd=1000 + aporte=5000 -> total_efectivo=6000.
    # X: objetivo 40% de 6000=2400, actual 100 -> necesita 2300.
    # Y: objetivo 30% de 6000=1800, actual 100 -> necesita 1700.
    # suma necesaria=4000 <= 5000 -> se cierra completo, sobra 5000-4000=1000.
    posiciones = [PosicionActual("AAA", "X", 100.0), PosicionActual("BBB", "Y", 100.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"X": 40.0, "Y": 30.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="solo_aportes",
        aporte_usd=5000.0,
        tasa_comision_pct=0.0,
    )
    aaa = _item(resultado.items, ticker="AAA")
    bbb = _item(resultado.items, ticker="BBB")
    assert aaa.importe_sugerido_usd == pytest.approx(2300.0)
    assert bbb.importe_sugerido_usd == pytest.approx(1700.0)
    assert resultado.sobrante_usd == pytest.approx(1000.0)


def test_solo_aportes_prorratea_cuando_el_aporte_no_alcanza():
    # total_usd=1000 + aporte=1000 -> total_efectivo=2000.
    # X: objetivo 40% de 2000=800, actual 100 -> necesita 700.
    # Y: objetivo 30% de 2000=600, actual 100 -> necesita 500.
    # suma necesaria=1200 > aporte=1000 -> factor=1000/1200.
    posiciones = [PosicionActual("AAA", "X", 100.0), PosicionActual("BBB", "Y", 100.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"X": 40.0, "Y": 30.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="solo_aportes",
        aporte_usd=1000.0,
        tasa_comision_pct=0.0,
    )
    aaa = _item(resultado.items, ticker="AAA")
    bbb = _item(resultado.items, ticker="BBB")
    assert aaa.importe_sugerido_usd == pytest.approx(700.0 * 1000 / 1200, abs=0.01)
    assert bbb.importe_sugerido_usd == pytest.approx(500.0 * 1000 / 1200, abs=0.01)
    assert resultado.sobrante_usd == pytest.approx(0.0, abs=0.02)


def test_solo_aportes_descarta_ventas():
    # Categoría muy sobreponderada: en modo completo pediría vender, en solo_aportes no aparece.
    posiciones = [PosicionActual("CCC", "Z", 300.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"Z": 10.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=300.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="solo_aportes",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )
    assert resultado.items == []


def test_solo_aportes_respeta_peso_maximo():
    # total_efectivo = 100 + 1000 = 1100. Objetivo X 80% = 880, actual 100 -> necesita 780
    # (sin tope alcanzaría con el aporte de 1000). Con peso_maximo=50%: techo=550, importe
    # máximo = 550-100=450. Sobrante = 1000-450=550.
    posiciones = [PosicionActual("AAA", "X", 100.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"X": 80.0},
        objetivos_ticker={},
        eje="Tipo",
        total_usd=100.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=50.0,
        peso_minimo_pp=None,
        modo="solo_aportes",
        aporte_usd=1000.0,
        tasa_comision_pct=0.0,
    )
    aaa = _item(resultado.items, ticker="AAA")
    assert aaa.importe_sugerido_usd == pytest.approx(450.0)
    assert resultado.sobrante_usd == pytest.approx(550.0)


# ── Comisión estimada ──────────────────────────────────────────────────────────

def test_comision_estimada_proporcional_al_importe():
    posiciones = [PosicionActual("AAA", "AAA", 0.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"AAA": 10.0},
        objetivos_ticker={"AAA": 10.0},
        eje="Ticker",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=1.0,
    )
    aaa = _item(resultado.items, ticker="AAA")
    assert aaa.importe_sugerido_usd == pytest.approx(100.0)
    assert aaa.comision_estimada_usd == pytest.approx(1.0)


def test_comision_cero_para_items_mantener():
    posiciones = [PosicionActual("AAA", "AAA", 100.0)]
    resultado = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={},
        objetivos_ticker={},
        eje="Ticker",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=None,
        peso_minimo_pp=None,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=1.0,
    )
    aaa = _item(resultado.items, ticker="AAA")
    assert aaa.accion == "mantener"
    assert aaa.comision_estimada_usd == pytest.approx(0.0)
