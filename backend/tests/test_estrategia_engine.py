"""Tests del motor puro de estrategias (services/estrategia_engine.py).

Los valores esperados de retorno/win-rate/comisión se calculan a mano en los comentarios (no
reimplementando la fórmula bajo test), como referencia manual de verificación — igual estilo que
`test_risk_engine.py`.
"""
import math
from datetime import date, timedelta

import pytest

from app.services import estrategia_engine as ee
from app.services.indicadores_engine import Barra


def _barras(cierres, aperturas=None, maximos=None, minimos=None):
    base = date(2024, 1, 1)
    out = []
    for i, c in enumerate(cierres):
        out.append(Barra(
            fecha=base + timedelta(days=i),
            cierre=c,
            apertura=aperturas[i] if aperturas else None,
            maximo=maximos[i] if maximos else None,
            minimo=minimos[i] if minimos else None,
        ))
    return out


def _dsl_base(entrada, salida=None, riesgo=None, ejecucion=None, indicadores=None):
    return {
        "version": 1,
        "indicadores": indicadores or [],
        "entrada": entrada,
        "salida": salida,
        "riesgo": riesgo or {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": ejecucion or {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0},
    }


# ── compilar: cruce en índice conocido, no dispara en la primera barra evaluable ─────────────

def test_cruce_sma_no_dispara_en_la_primera_barra_evaluable():
    cierres = [10, 10, 10, 20, 20, 20, 20]
    barras = _barras(cierres)
    dsl = _dsl_base(
        entrada={"op": "y", "condiciones": [
            {"op": "cruce_arriba", "izq": {"ref": "mm2"}, "der": {"ref": "mm3"}},
        ]},
        indicadores=[
            {"id": "mm2", "tipo": "SMA", "params": {"periodo": 2}},
            {"id": "mm3", "tipo": "SMA", "params": {"periodo": 3}},
        ],
    )
    compilado = ee.compilar(dsl, barras)
    # SMA(3) recién está definida desde el índice 2; el cruce en sí (que exige el par i-1,i)
    # sólo puede dispararse desde el índice 3 -> primera_barra_evaluable == 3, no 2.
    assert compilado.primera_barra_evaluable == 3
    assert compilado.entrada[:3] == [None, None, None]
    assert compilado.entrada[3] is True
    assert compilado.entrada[4] is False


# ── tablas de verdad trivaluadas de y/o/no ────────────────────────────────────────────────────

def test_tabla_de_verdad_trivaluada_y_o_no():
    # 3 barras; leaf1 usa RSI(14) -> None en las 3 (warmup no cumplido), leaf2 siempre True.
    cierres = [100.0, 101.0, 102.0]
    barras = _barras(cierres)
    dsl_y = _dsl_base(
        entrada={"op": "y", "condiciones": [
            {"op": "mayor", "izq": {"ref": "rsi"}, "der": {"const": 0}},
            {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}},
        ]},
        indicadores=[{"id": "rsi", "tipo": "RSI", "params": {"periodo": 14}}],
    )
    compilado_y = ee.compilar(dsl_y, barras)
    assert compilado_y.entrada == [None, None, None]  # y con un hijo None nunca es True

    dsl_o = _dsl_base(
        entrada={"op": "o", "condiciones": [
            {"op": "mayor", "izq": {"ref": "rsi"}, "der": {"const": 0}},
            {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}},
        ]},
        indicadores=[{"id": "rsi", "tipo": "RSI", "params": {"periodo": 14}}],
    )
    compilado_o = ee.compilar(dsl_o, barras)
    assert compilado_o.entrada == [None, None, None]  # o NO cortocircuita a True con un hijo None

    dsl_no = _dsl_base(entrada={"op": "no", "condicion": {"op": "mayor", "izq": {"ref": "rsi"}, "der": {"const": 0}}},
                        indicadores=[{"id": "rsi", "tipo": "RSI", "params": {"periodo": 14}}])
    assert ee.compilar(dsl_no, barras).entrada == [None, None, None]

    # Con ambos hijos definidos, y/o/no se comportan booleanamente normal.
    cierres2 = [90.0, 110.0, 95.0]
    barras2 = _barras(cierres2)
    dsl_y2 = _dsl_base(entrada={"op": "y", "condiciones": [
        {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 100}},
        {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 120}},
    ]})
    assert ee.compilar(dsl_y2, barras2).entrada == [False, True, False]

    dsl_o2 = _dsl_base(entrada={"op": "o", "condiciones": [
        {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 100}},
        {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 91}},
    ]})
    assert ee.compilar(dsl_o2, barras2).entrada == [True, True, False]

    dsl_no2 = _dsl_base(entrada={"op": "no", "condicion": {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 100}}})
    assert ee.compilar(dsl_no2, barras2).entrada == [True, False, True]


# ── backtest determinista: 2 operaciones, retorno/win-rate a mano ────────────────────────────

def _serie_dos_operaciones():
    # Trade 1 (WIN): entra en 3 (cruce arriba de 100, cierre=101), sale en 5 (cruce abajo de 105,
    #   cierre=104). bruto = 104/101 - 1 = 2.9703%.
    # Trade 2 (LOSS): entra en 8 (cierre=110), sale en 10 (cierre=90).
    #   bruto = 90/110 - 1 = -18.1818%.
    cierres = [95, 98, 99, 101, 200, 104, 95, 99, 110, 115, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90]
    return _barras([float(c) for c in cierres])


def _dsl_dos_umbrales(comision_pct=1.0):
    return _dsl_base(
        entrada={"op": "y", "condiciones": [{"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": 100}}]},
        salida={"op": "y", "condiciones": [{"op": "cruce_abajo", "izq": {"campo": "cierre"}, "der": {"const": 105}}]},
        ejecucion={"lado": "long", "comision_pct": comision_pct, "precio_ejecucion": "cierre", "demora_barras": 0},
    )


def test_backtest_dos_operaciones_retorno_y_winrate_a_mano():
    barras = _serie_dos_operaciones()
    resultado = ee.backtest(_dsl_dos_umbrales(comision_pct=1.0), barras)

    assert len(resultado.operaciones) == 2
    op1, op2 = resultado.operaciones
    assert op1.indice_entrada == 3 and op1.indice_salida == 5
    assert op1.precio_entrada == pytest.approx(101.0)
    assert op1.precio_salida == pytest.approx(104.0)
    assert op1.retorno_bruto_pct == pytest.approx((104 / 101 - 1) * 100)

    assert op2.indice_entrada == 8 and op2.indice_salida == 10
    assert op2.precio_entrada == pytest.approx(110.0)
    assert op2.precio_salida == pytest.approx(90.0)
    assert op2.retorno_bruto_pct == pytest.approx((90 / 110 - 1) * 100)

    assert resultado.metricas["operaciones"] == 2
    assert resultado.metricas["ganadoras"] == 1
    assert resultado.metricas["perdedoras"] == 1
    assert resultado.metricas["win_rate_pct"] == pytest.approx(50.0)

    # buy & hold: cierre inicial (95) -> cierre final (90)
    assert resultado.metricas["retorno_buy_hold_pct"] == pytest.approx(round((90 / 95 - 1) * 100, 4))
    assert resultado.curva_buy_hold[0][1] == pytest.approx(100.0)
    assert resultado.curva_buy_hold[-1][1] == pytest.approx((90 / 95) * 100)


def test_comision_baja_el_neto_exactamente_2x_por_operacion():
    barras = _serie_dos_operaciones()
    comision = 1.25
    resultado = ee.backtest(_dsl_dos_umbrales(comision_pct=comision), barras)
    for op in resultado.operaciones:
        assert op.retorno_neto_pct == pytest.approx(op.retorno_bruto_pct - 2 * comision)


def test_equity_plana_antes_de_la_primera_entrada():
    barras = _serie_dos_operaciones()
    resultado = ee.backtest(_dsl_dos_umbrales(comision_pct=0.0), barras)
    # Antes del índice 3 (primera entrada) la curva se mantiene plana en 100.
    for fecha, valor in resultado.curva_equity[:3]:
        assert valor == pytest.approx(100.0)


def test_posicion_abierta_al_final_excluida_del_winrate():
    # Sólo entrada, ninguna condición de salida -> queda abierta al final.
    cierres = [95, 98, 99, 101, 105, 110, 115, 120]
    barras = _barras([float(c) for c in cierres])
    dsl = _dsl_base(
        entrada={"op": "y", "condiciones": [{"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": 100}}]},
        salida=None,
    )
    resultado = ee.backtest(dsl, barras)
    assert len(resultado.operaciones) == 1
    assert resultado.operaciones[0].abierta is True
    assert "posicion_abierta_al_final" in resultado.advertencias
    # Con 0 operaciones cerradas, las métricas de ratio son None + datos_insuficientes.
    assert resultado.metricas["estado"] == "datos_insuficientes"
    assert resultado.metricas["win_rate_pct"] is None
    assert resultado.metricas["ganadoras"] == 0
    assert resultado.metricas["perdedoras"] == 0
    assert resultado.metricas["operaciones_cerradas"] == 0
    # El P&L no realizado de la posición abierta sí se expone (entra en 101, cierra la serie en 120).
    assert resultado.metricas["retorno_abierta_pct"] == pytest.approx((120 / 101 - 1) * 100, rel=1e-3)


def test_una_sola_operacion_cerrada_calcula_metricas_por_operacion():
    # Un único trade cerrado (entra al cruzar 100, sale al cruzar por debajo de 105) -> antes daba
    # "datos_insuficientes"; ahora las métricas por operación se calculan sobre esa muestra.
    cierres = [95, 98, 101, 108, 104, 103, 102, 101, 100, 99]
    barras = _barras([float(c) for c in cierres])
    dsl = _dsl_base(
        entrada={"op": "y", "condiciones": [{"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": 100}}]},
        salida={"op": "y", "condiciones": [{"op": "cruce_abajo", "izq": {"campo": "cierre"}, "der": {"const": 105}}]},
    )
    resultado = ee.backtest(dsl, barras)
    cerradas = [o for o in resultado.operaciones if not o.abierta]
    assert len(cerradas) == 1
    assert resultado.metricas["estado"] == "ok"
    assert resultado.metricas["operaciones_cerradas"] == 1
    assert resultado.metricas["win_rate_pct"] in (0.0, 100.0)
    assert resultado.metricas["retorno_medio_operacion_pct"] == pytest.approx(cerradas[0].retorno_neto_pct)
    assert resultado.metricas["duracion_media_barras"] == pytest.approx(float(cerradas[0].barras))


# ── stops intrabar, gap de apertura y trailing ───────────────────────────────────────────────

def _dsl_entrada_unica(riesgo):
    # cruce_arriba de un umbral bajo (99): dispara una única vez, en el cruce real, y nunca
    # vuelve a dispararse mientras el precio se mantenga arriba (a diferencia de una condición
    # "siempre verdadera", que reabriría posición en cada barra tras cada salida).
    return _dsl_base(
        entrada={"op": "y", "condiciones": [{"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": 99}}]},
        riesgo=riesgo,
    )


def test_stop_loss_intrabar_contra_el_minimo():
    # Cruce arriba de 99 en la barra 1 (cierre=100) -> entra a 100. stop_loss 10% -> nivel = 90.
    # Barra 4 tiene mínimo 85 (toca el stop sin gap de apertura) -> sale exactamente a 90.
    cierres = [90.0, 100.0, 100.0, 100.0, 95.0, 95.0]
    aperturas = [90.0, 100.0, 100.0, 100.0, 94.0, 95.0]
    minimos = [90.0, 100.0, 100.0, 100.0, 85.0, 90.0]
    maximos = [90.0, 100.0, 100.0, 100.0, 96.0, 96.0]
    barras = _barras(cierres, aperturas, maximos, minimos)
    dsl = _dsl_entrada_unica({"stop_loss_pct": 10.0, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None})
    resultado = ee.backtest(dsl, barras)
    assert len(resultado.operaciones) == 1
    op = resultado.operaciones[0]
    assert op.indice_entrada == 1 and op.precio_entrada == pytest.approx(100.0)
    assert op.motivo_salida == "stop_loss"
    assert op.precio_salida == pytest.approx(90.0)


def test_stop_loss_con_gap_de_apertura_sale_a_la_apertura():
    cierres = [90.0, 100.0, 100.0, 100.0, 80.0]
    aperturas = [90.0, 100.0, 100.0, 100.0, 82.0]   # gapea por debajo del nivel de stop (90)
    minimos = [90.0, 100.0, 100.0, 100.0, 78.0]
    maximos = [90.0, 100.0, 100.0, 100.0, 83.0]
    barras = _barras(cierres, aperturas, maximos, minimos)
    dsl = _dsl_entrada_unica({"stop_loss_pct": 10.0, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None})
    resultado = ee.backtest(dsl, barras)
    op = resultado.operaciones[0]
    assert op.motivo_salida == "stop_loss"
    assert op.precio_salida == pytest.approx(82.0)  # se sale a la apertura, no al nivel teórico (90)


def test_trailing_stop_sigue_el_maximo():
    # Entra a 100 (barra 1). Sube a 150 (nuevo máximo), trailing 10% -> nivel = 135. Luego cae y
    # toca 130.
    cierres = [90.0, 100.0, 150.0, 140.0, 130.0]
    maximos = [90.0, 100.0, 150.0, 140.0, 132.0]
    minimos = [90.0, 100.0, 150.0, 138.0, 128.0]
    barras = _barras(cierres, maximos=maximos, minimos=minimos)
    dsl = _dsl_entrada_unica({"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": 10.0, "max_barras": None})
    resultado = ee.backtest(dsl, barras)
    op = resultado.operaciones[0]
    assert op.motivo_salida == "trailing_stop"
    assert op.precio_salida == pytest.approx(135.0)  # 150 * (1 - 0.10)


# ── apertura_siguiente desplaza una barra (sin sesgo de lookahead) ───────────────────────────

def test_apertura_siguiente_desplaza_la_ejecucion_una_barra():
    cierres = [95.0, 98.0, 99.0, 101.0, 102.0]
    aperturas = [95.0, 98.0, 99.0, 100.0, 103.0]
    barras = _barras(cierres, aperturas)
    dsl = _dsl_base(
        entrada={"op": "y", "condiciones": [{"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": 100}}]},
        ejecucion={"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "apertura_siguiente", "demora_barras": 1},
    )
    resultado = ee.backtest(dsl, barras)
    # la señal se cumple en la barra 3 (cierre cruza 100); ejecuta en la apertura de la barra 4
    assert resultado.senales[0].indice == 4
    assert resultado.operaciones[0].indice_entrada == 4
    assert resultado.operaciones[0].precio_entrada == pytest.approx(103.0)


# ── validar_estrategia ────────────────────────────────────────────────────────────────────────

def _dsl_valido_minimo():
    return _dsl_base(entrada={"op": "y", "condiciones": [{"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}}]})


def test_validar_estrategia_dsl_minimo_valido():
    assert ee.validar_estrategia(_dsl_valido_minimo()) == []


@pytest.mark.parametrize("mutacion", [
    lambda d: d.update(version=2) or d,
    lambda d: d.__setitem__("indicadores", [{"id": "x", "tipo": "NOEXISTE", "params": {}}]) or d,
    lambda d: d.__setitem__("indicadores", [
        {"id": "dup", "tipo": "SMA", "params": {"periodo": 10}},
        {"id": "dup", "tipo": "SMA", "params": {"periodo": 20}},
    ]) or d,
    lambda d: d.__setitem__("entrada", {"op": "y", "condiciones": [
        {"op": "mayor", "izq": {"ref": "no_declarado"}, "der": {"const": 0}}]}) or d,
    lambda d: d.__setitem__("entrada", {"op": "y", "condiciones": [
        {"op": "mayor", "izq": {"ref": "macd1", "salida": "no_existe"}, "der": {"const": 0}}]}) or (
        d.__setitem__("indicadores", [{"id": "macd1", "tipo": "MACD", "params": {"rapida": 12, "lenta": 26, "senal": 9}}]) or d
    ),
    lambda d: d.__setitem__("entrada", {"op": "operador_raro", "condiciones": []}) or d,
    lambda d: d.__setitem__("indicadores", [{"id": "x", "tipo": "SMA", "params": {"periodo": 5000}}]) or d,
    lambda d: d.pop("entrada") or d,
    lambda d: d.__setitem__("ejecucion", {"lado": "long", "comision_pct": 99, "precio_ejecucion": "cierre"}) or d,
])
def test_validar_estrategia_casos_invalidos(mutacion):
    dsl = _dsl_valido_minimo()
    dsl = mutacion(dsl)
    errores = ee.validar_estrategia(dsl)
    assert errores, f"se esperaba al menos un error para {dsl}"


def test_validar_estrategia_profundidad_y_nodos_maximos():
    condicion = {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}}
    for _ in range(6):
        condicion = {"op": "no", "condicion": condicion}
    dsl = _dsl_base(entrada=condicion)
    assert ee.validar_estrategia(dsl)

    muchas = {"op": "y", "condiciones": [
        {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": i}} for i in range(25)
    ]}
    dsl2 = _dsl_base(entrada=muchas)
    assert ee.validar_estrategia(dsl2)


# ── presets ───────────────────────────────────────────────────────────────────────────────────

def _serie_sintetica(n=300):
    base = date(2023, 1, 1)
    out = []
    precio = 100.0
    for i in range(n):
        precio += math.sin(i / 12.0) * 2.0 + (0.05 if i % 7 == 0 else -0.01)
        out.append(Barra(
            fecha=base + timedelta(days=i), cierre=precio,
            apertura=precio * 0.999, maximo=precio * 1.01, minimo=precio * 0.99, volumen=1000.0 + i,
        ))
    return out


@pytest.mark.parametrize("nombre", list(ee.PRESETS.keys()))
def test_presets_validan_y_corren_sobre_serie_sintetica(nombre):
    dsl = ee.resolver_preset(nombre)
    assert ee.validar_estrategia(dsl) == []
    barras = _serie_sintetica()
    resultado = ee.backtest(dsl, barras)
    assert isinstance(resultado.metricas, dict)
    assert resultado.metricas["estado"] in ("ok", "datos_insuficientes")
    assert len(resultado.curva_equity) == len(barras)
    assert len(resultado.curva_buy_hold) == len(barras)
