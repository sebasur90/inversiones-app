"""Tests del motor puro del comparador (services/comparador_estrategias_engine.py).

Los valores esperados se calculan a mano en los comentarios, igual estilo que
`test_estrategia_engine.py` / `test_risk_engine.py`.
"""
from datetime import date

import pytest

from app.services import comparador_estrategias_engine as cee


# ── dinero ───────────────────────────────────────────────────────────────────────────────────

def test_dinero_capital_final_y_ganancia():
    assert cee.dinero(10.0, 1000.0) == {"capital_final": 1100.0, "ganancia": 100.0}


def test_dinero_retorno_negativo():
    assert cee.dinero(-20.0, 500.0) == {"capital_final": 400.0, "ganancia": -100.0}


# ── diferencia: pp, monetaria y relativa no son la misma cuenta ────────────────────────────────

def test_diferencia_pp_monetaria_relativa():
    # estrategia +20%, referencia +10%, capital 1.000.000
    d = cee.diferencia(20.0, 10.0, 1_000_000.0)
    assert d["pp"] == pytest.approx(10.0)
    assert d["monetaria"] == pytest.approx(100_000.0)
    # relativa = (1.20 / 1.10 - 1) * 100
    assert d["relativa_pct"] == pytest.approx(9.0909, abs=1e-3)


def test_diferencia_con_referencia_negativa():
    d = cee.diferencia(5.0, -5.0, 1000.0)
    assert d["pp"] == pytest.approx(10.0)
    assert d["monetaria"] == pytest.approx(100.0)
    # relativa = (1.05 / 0.95 - 1) * 100
    assert d["relativa_pct"] == pytest.approx(10.526, abs=1e-3)


# ── volatilidad_curva: puente hacia risk_engine, mismo mínimo de 6 meses ────────────────────────

def test_volatilidad_curva_menos_de_6_meses_es_insuficiente():
    curva = [
        (date(2024, 1, 31), 100.0), (date(2024, 2, 29), 105.0),
        (date(2024, 3, 31), 102.0), (date(2024, 4, 30), 108.0),
    ]
    # 4 puntos -> 3 retornos mensuales, por debajo del mínimo de 6 (`risk_engine.MIN_OBS_VOLATILIDAD`).
    assert cee.volatilidad_curva(curva) == {"estado": "datos_insuficientes", "anualizada_pct": None, "n_obs": 3}


def test_volatilidad_curva_retorno_mensual_constante_da_desvio_cero():
    # 7 fines de mes exactos, +10% cada mes -> 6 retornos idénticos -> stdev muestral = 0.
    fechas = [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30),
              date(2024, 5, 31), date(2024, 6, 30), date(2024, 7, 31)]
    valores = [100.0]
    for _ in range(6):
        valores.append(valores[-1] * 1.10)
    r = cee.volatilidad_curva(list(zip(fechas, valores)))
    assert r["estado"] == "ok"
    assert r["anualizada_pct"] == pytest.approx(0.0, abs=1e-6)


def test_volatilidad_curva_retornos_alternados():
    # +2%/-2% alternado, 6 meses -> stdev muestral = 0.0219089023 (statistics.stdev); anualizada
    # (ratio) = round(stdev * sqrt(12), 4) = 0.0759 (redondeo de `risk_engine.calcular_volatilidad`)
    # -> anualizada_pct = 7.59 (calculado a mano con Python).
    fechas = [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30),
              date(2024, 5, 31), date(2024, 6, 30), date(2024, 7, 31)]
    valores = [100.0]
    for i in range(6):
        valores.append(valores[-1] * (1.02 if i % 2 == 0 else 0.98))
    r = cee.volatilidad_curva(list(zip(fechas, valores)))
    assert r["estado"] == "ok"
    assert r["anualizada_pct"] == pytest.approx(7.59, abs=1e-6)


# ── duracion_drawdown ────────────────────────────────────────────────────────────────────────

def test_duracion_drawdown_con_recuperacion():
    d0 = date(2024, 1, 1)
    curva = [
        (d0, 100.0), (d0.replace(day=6), 90.0), (d0.replace(day=11), 80.0),
        (d0.replace(day=16), 85.0), (d0.replace(day=21), 95.0), (d0.replace(day=26), 101.0),
    ]
    r = cee.duracion_drawdown(curva, fecha_pico=d0, fecha_valle=d0.replace(day=11))
    assert r["dias_caida"] == 10
    assert r["dias_recuperacion"] == 15
    assert r["recuperado"] is True


def test_duracion_drawdown_sin_recuperar():
    d0 = date(2024, 1, 1)
    curva = [(d0, 100.0), (d0.replace(day=11), 80.0), (d0.replace(day=21), 90.0)]
    r = cee.duracion_drawdown(curva, fecha_pico=d0, fecha_valle=d0.replace(day=11))
    assert r["dias_caida"] == 10
    assert r["dias_recuperacion"] is None
    assert r["recuperado"] is False


def test_duracion_drawdown_sin_fechas_es_none():
    assert cee.duracion_drawdown([], None, None) == {"dias_caida": None, "dias_recuperacion": None, "recuperado": None}


# ── submuestrear: conserva primer y último punto ────────────────────────────────────────────────

def test_submuestrear_no_toca_series_cortas():
    fechas = [date(2024, 1, i) for i in range(1, 4)]
    curvas = {"a": [1.0, 2.0, 3.0]}
    f_out, c_out = cee.submuestrear(fechas, curvas, max_puntos=5)
    assert f_out == fechas
    assert c_out == curvas


def test_submuestrear_recorta_conservando_extremos():
    fechas = [date(2024, 1, 1 + i) for i in range(10)]
    curvas = {"a": [float(i) for i in range(10)], "b": [float(-i) for i in range(10)]}
    f_out, c_out = cee.submuestrear(fechas, curvas, max_puntos=4)
    assert len(f_out) <= 4
    assert f_out[0] == fechas[0]
    assert f_out[-1] == fechas[-1]
    assert c_out["a"][0] == 0.0 and c_out["a"][-1] == 9.0
    assert len(c_out["a"]) == len(f_out) and len(c_out["b"]) == len(f_out)


# ── divergencias ─────────────────────────────────────────────────────────────────────────────

def test_divergencias_detecta_el_tramo_que_supera_el_umbral():
    fechas = [
        date(2024, 1, 1), date(2024, 1, 15), date(2024, 1, 31),
        date(2024, 2, 1), date(2024, 2, 15), date(2024, 2, 28),
    ]
    # Enero: ambas iguales (sin separación). Febrero: `a` sube 6% mientras `b` queda plana.
    curva_a = [100.0, 100.0, 100.0, 100.0, 100.0, 106.0]
    curva_b = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    # `a` invertida todo febrero (índices 3-5); `b` nunca invertida.
    tramos = cee.divergencias(fechas, curva_a, curva_b, operaciones_a=[(3, 5)], operaciones_b=[])
    assert len(tramos) == 1
    t = tramos[0]
    assert t["desde"] == date(2024, 2, 1) and t["hasta"] == date(2024, 2, 28)
    assert t["delta_pp"] == pytest.approx(6.0)
    assert t["invertida_pct"] == pytest.approx(100.0)
    assert t["invertida_referencia_pct"] == pytest.approx(0.0)


def test_divergencias_por_debajo_del_umbral_no_se_reporta():
    fechas = [date(2024, 1, 1), date(2024, 1, 31)]
    curva_a = [100.0, 101.0]  # 1% de separación, umbral default 2.0 pp
    curva_b = [100.0, 100.0]
    assert cee.divergencias(fechas, curva_a, curva_b, [], []) == []


def test_divergencias_devuelve_como_maximo_max_tramos_ordenado_por_magnitud():
    # 4 meses, cada uno con una separación distinta; con max_tramos=2 sólo quedan los 2 mayores.
    fechas = [
        date(2024, 1, 1), date(2024, 1, 31),
        date(2024, 2, 1), date(2024, 2, 29),
        date(2024, 3, 1), date(2024, 3, 31),
        date(2024, 4, 1), date(2024, 4, 30),
    ]
    curva_a = [100.0, 103.0, 103.0, 100.0, 100.0, 108.0, 108.0, 99.0]
    curva_b = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    tramos = cee.divergencias(fechas, curva_a, curva_b, [], [], max_tramos=2)
    assert len(tramos) == 2
    # Ordenados por |delta_pp| descendente: marzo (+8%) y abril (-8.33%) ganan a enero (+3%).
    assert {round(abs(t["delta_pp"])) for t in tramos} == {8}


# ── advertencias_dsl_serie ───────────────────────────────────────────────────────────────────

def _dsl_con_condicion(cond, indicadores=None):
    return {"version": 1, "indicadores": indicadores or [], "entrada": cond, "salida": None,
            "riesgo": {}, "ejecucion": {}}


def test_advertencias_requiere_velas_si_usa_maximo_sin_velas():
    dsl = _dsl_con_condicion({"op": "mayor_igual", "izq": {"campo": "maximo"}, "der": {"const": 10}})
    assert cee.advertencias_dsl_serie(dsl, tiene_velas=False, tiene_volumen=True) == ["requiere_velas"]
    assert cee.advertencias_dsl_serie(dsl, tiene_velas=True, tiene_volumen=True) == []


def test_advertencias_requiere_volumen_por_indicador_obv():
    dsl = _dsl_con_condicion(
        {"op": "mayor", "izq": {"ref": "obv1"}, "der": {"const": 0}},
        indicadores=[{"id": "obv1", "tipo": "OBV", "params": {}}],
    )
    assert cee.advertencias_dsl_serie(dsl, tiene_velas=True, tiene_volumen=False) == ["requiere_volumen"]


def test_advertencias_vacias_con_solo_cierre():
    dsl = _dsl_con_condicion({"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}})
    assert cee.advertencias_dsl_serie(dsl, tiene_velas=False, tiene_volumen=False) == []


# ── dsl_sin_costos ───────────────────────────────────────────────────────────────────────────

def test_dsl_sin_costos_no_muta_el_original():
    original = {"version": 1, "indicadores": [], "entrada": {}, "ejecucion": {"comision_pct": 0.6}}
    copia = cee.dsl_sin_costos(original)
    assert copia["ejecucion"]["comision_pct"] == 0.0
    assert original["ejecucion"]["comision_pct"] == 0.6
