"""Escenarios de entrada (`escenarios_entrada_engine`): reglas explícitas, faltantes declarados, sin predicciones."""
import re
from datetime import date

import pytest

from app.services import escenarios_entrada_engine as ee

HOY = date(2026, 10, 1)
PROHIBIDAS = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)


def _ins(**kw):
    base = dict(precio=100.0, fecha_precio=HOY, moneda="USD", atr=4.0, soporte=90.0, resistencia=110.0, rsi=55.0,
                valor_pesimista=95.0, valor_base=120.0, valor_optimista=140.0, moneda_valor="USD",
                tasa_comision_pct=0.5, horizonte="mediano")
    base.update(kw)
    return ee.Insumos(**base)


def _esc(res, clave):
    return next(e for e in res["escenarios"] if e["clave"] == clave)


def test_entrar_ahora_con_formulas_visibles():
    res = ee.construir(_ins())
    a = _esc(res, ee.AHORA)
    assert a["precio_entrada"] == 100.0
    assert a["invalidacion"] == pytest.approx(90.0 - 4.0)          # soporte − 1 ATR
    assert a["riesgo_pct"] == pytest.approx(-0.14)
    assert a["base_pct"] == pytest.approx(0.20)                     # (120 − 100) / 100
    assert a["favorable_pct"] == pytest.approx(0.40)
    assert a["desfavorable_pct"] == pytest.approx(-0.05)
    assert a["comision_pct"] == pytest.approx(0.01)                 # 2 × 0,5 %
    assert res["horizonte_meses"] == 12 and res["salvedad"] and res["regla_potencial"]


def test_esperar_tecnica_usa_el_soporte_y_escalonada_tres_tramos():
    res = ee.construir(_ins())
    t = _esc(res, ee.ESPERAR_TECNICA)
    assert t["disponible"] and t["precio_entrada"] == 90.0
    e = _esc(res, ee.ESCALONADA)
    assert [x["precio"] for x in e["tramos"]] == [100.0, 90.0, 86.0]
    assert e["precio_entrada"] == pytest.approx((100 + 90 + 86) / 3)


def test_esperar_valoracion_apunta_al_valor_base_o_al_pesimista():
    assert _esc(ee.construir(_ins(precio=130.0, soporte=None)), ee.ESPERAR_VALORACION)["precio_entrada"] == 120.0
    assert _esc(ee.construir(_ins(precio=100.0)), ee.ESPERAR_VALORACION)["precio_entrada"] == 95.0


def test_sin_atr_ni_serie_no_se_inventa_la_invalidacion():
    res = ee.construir(_ins(atr=None, soporte=None, rsi=None))
    a = _esc(res, ee.AHORA)
    assert a["invalidacion"] is None and a["riesgo_pct"] is None
    assert any("ATR" in f for f in a["faltantes"])
    assert not _esc(res, ee.ESPERAR_TECNICA)["disponible"]
    assert not _esc(res, ee.ESCALONADA)["disponible"]


def test_monedas_distintas_no_se_comparan():
    res = ee.construir(_ins(moneda="ARS", moneda_valor="USD"))
    a = _esc(res, ee.AHORA)
    assert a["base_pct"] is None and any("otra moneda" in f for f in a["faltantes"])


def test_descartar_se_activa_con_banderas_o_datos_insuficientes():
    assert not _esc(ee.construir(_ins()), ee.DESCARTAR)["disponible"]
    d = _esc(ee.construir(_ins(banderas_criticas=["deuda alta"])), ee.DESCARTAR)
    assert d["disponible"] and "deuda alta" in d["condicion"]
    assert _esc(ee.construir(_ins(datos_insuficientes=True)), ee.DESCARTAR)["disponible"]


def test_sin_precio_no_hay_escenarios_ni_comision_inventada():
    res = ee.construir(_ins(precio=None))
    assert res["estado"] == "sin_datos" and res["escenarios"] == []
    a = _esc(ee.construir(_ins(tasa_comision_pct=None)), ee.AHORA)
    assert a["comision_pct"] is None and any("comisión" in f for f in a["faltantes"])


def test_textos_no_indican_operar():
    res = ee.construir(_ins(banderas_criticas=["x"]))
    textos = [res["salvedad"], res["regla_potencial"]] + [
        v for e in res["escenarios"] for v in (e["condicion"], e["fundamento"], *e["faltantes"], *e["incertidumbres"])]
    assert [t for t in textos if PROHIBIDAS.search(t)] == []
