"""Banda de pesos (peso_minimo / peso_maximo) aplicada en modo rebalanceo completo
(Ola 5, ítem 9). Antes generar_propuesta recibía peso_minimo_pp/peso_maximo_pp y sólo
usaba el máximo, y sólo en modo solo_aportes."""
import pytest

from app.services.rebalanceo_engine import PosicionActual, generar_propuesta


def _item(items, ticker):
    for it in items:
        if it.posicion == ticker:
            return it
    raise AssertionError(f"sin item {ticker}")


def _propuesta(objetivos_ticker, *, peso_maximo=None, peso_minimo=None, posiciones=None):
    posiciones = posiciones or [
        PosicionActual("AAA", "AAA", 500.0),
        PosicionActual("BBB", "BBB", 300.0),
        PosicionActual("CCC", "CCC", 200.0),
    ]
    return generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria=objetivos_ticker,
        objetivos_ticker=objetivos_ticker,
        eje="Ticker",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=peso_maximo,
        peso_minimo_pp=peso_minimo,
        modo="completo",
        aporte_usd=0.0,
        tasa_comision_pct=0.0,
    )


def test_techo_recorta_objetivo_que_lo_supera():
    # Objetivo AAA 70% de 1000 = 700, pero peso_maximo 50% -> recorta a 500.
    res = _propuesta({"AAA": 70.0}, peso_maximo=50.0)
    aaa = _item(res.items, "AAA")
    assert aaa.valor_objetivo_usd == pytest.approx(500.0)
    assert aaa.peso_objetivo_pct == pytest.approx(50.0)
    assert aaa.importe_sugerido_usd == pytest.approx(0.0)  # ya estaba en 500
    assert "peso máximo" in aaa.motivo


def test_techo_aplica_a_instrumento_sin_objetivo_propio():
    # AAA sin objetivo, hoy 50%. peso_maximo 30% -> sugerir vender hasta 300.
    res = _propuesta({"BBB": 30.0}, peso_maximo=30.0)
    aaa = _item(res.items, "AAA")
    assert aaa.valor_objetivo_usd == pytest.approx(300.0)
    assert aaa.accion == "vender"
    assert aaa.importe_sugerido_usd == pytest.approx(-200.0)
    assert "peso máximo" in aaa.motivo


def test_piso_sube_objetivo_por_debajo_del_minimo():
    # Objetivo CCC 5% de 1000 = 50, peso_minimo 15% -> sube a 150.
    res = _propuesta({"CCC": 5.0}, peso_minimo=15.0)
    ccc = _item(res.items, "CCC")
    assert ccc.valor_objetivo_usd == pytest.approx(150.0)
    assert ccc.accion == "vender"  # hoy 200 -> baja a 150
    assert "peso mínimo" in ccc.motivo


def test_piso_no_toca_instrumento_sin_objetivo_ni_delta():
    # CCC sin objetivo, hoy 20%. peso_minimo 30% NO debe forzar compra (delta_pp == 0).
    res = _propuesta({"AAA": 50.0}, peso_minimo=30.0)
    ccc = _item(res.items, "CCC")
    assert ccc.accion == "mantener"
    assert ccc.valor_objetivo_usd == pytest.approx(200.0)
    assert "peso mínimo" not in ccc.motivo


def test_sin_banda_configurada_no_cambia_nada():
    con = _propuesta({"AAA": 70.0}, peso_maximo=None, peso_minimo=None)
    aaa = _item(con.items, "AAA")
    assert aaa.valor_objetivo_usd == pytest.approx(700.0)
    assert "peso máximo" not in aaa.motivo and "peso mínimo" not in aaa.motivo


def test_solo_aportes_conserva_su_comportamiento_previo():
    # En solo_aportes el techo se aplica por _aplicar_solo_aportes, no por la banda nueva.
    posiciones = [PosicionActual("AAA", "AAA", 500.0), PosicionActual("BBB", "BBB", 500.0)]
    res = generar_propuesta(
        posiciones=posiciones,
        objetivos_categoria={"AAA": 90.0},
        objetivos_ticker={"AAA": 90.0},
        eje="Ticker",
        total_usd=1000.0,
        tolerancia_pp=2.0,
        peso_maximo_pp=60.0,
        peso_minimo_pp=10.0,
        modo="solo_aportes",
        aporte_usd=1000.0,
        tasa_comision_pct=0.0,
    )
    aaa = _item(res.items, "AAA")
    # total_efectivo = 2000; techo 60% = 1200; ya tiene 500 -> importe cap 700
    # (lo aplica _aplicar_solo_aportes, no _aplicar_banda_pesos).
    assert aaa.importe_sugerido_usd == pytest.approx(700.0)
    assert "Recortado al peso máximo" not in aaa.motivo  # no pasó por la banda nueva
