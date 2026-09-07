"""Tests del builder del laboratorio (app/lab/). Sin fixtures de DB: motor puro."""
import json
from datetime import date, timedelta

import pytest

from app.lab import Estrategia, ind, precio, entre, todas, alguna, negar
from app.lab import a_dataframe, comparar_con_mascara
from app.lab.builder import EstrategiaInvalida
from app.services import estrategia_engine as ee
from app.services.indicadores_engine import Barra


def _barras(cierres):
    base = date(2024, 1, 1)
    return [
        Barra(fecha=base + timedelta(days=i), cierre=float(c),
              apertura=float(c), maximo=float(c) + 1, minimo=float(c) - 1, volumen=1000.0 + i)
        for i, c in enumerate(cierres)
    ]


def _barras_close_only(cierres):
    base = date(2024, 1, 1)
    return [Barra(fecha=base + timedelta(days=i), cierre=float(c)) for i, c in enumerate(cierres)]


# ── el DSL del builder siempre valida ────────────────────────────────────────

def test_dsl_del_builder_pasa_validar_estrategia():
    canal = ind.EXTREMOS(ventana=0)
    est = (Estrategia("Mínimo histórico")
           .comprar(canal.dist_min_pct <= 1.0)
           .vender(canal.dist_max_pct >= -1.0)
           .riesgo(stop_loss_pct=20)
           .ejecucion(comision_pct=0.6, precio_ejecucion="apertura_siguiente", demora_barras=1))
    dsl = est.definicion()
    assert ee.validar_estrategia(dsl) == []
    assert dsl["indicadores"] == [{"id": "extremos_0", "tipo": "EXTREMOS", "params": {"ventana": 0}}]
    assert dsl["entrada"]["op"] == "menor_igual"
    assert dsl["ejecucion"]["precio_ejecucion"] == "apertura_siguiente"


def test_round_trip_a_dict_json_valida():
    sma = ind.SMA(periodo=50)
    est = Estrategia("MM").comprar(precio.cierre > sma).vender(precio.cierre < sma)
    dsl = json.loads(est.a_json())
    assert ee.validar_estrategia(dsl) == []
    assert dsl == est.a_dict()


def test_condiciones_avanzadas_entre_y_no_validan():
    rsi = ind.RSI(periodo=14)
    canal = ind.EXTREMOS(ventana=0)
    est = Estrategia("Avanzada").comprar(
        entre(rsi, 30, 70) & negar(canal.dist_min_pct > 5)
    )
    dsl = est.definicion()
    assert ee.validar_estrategia(dsl) == []
    assert dsl["entrada"]["op"] == "y"
    ops = {c["op"] for c in dsl["entrada"]["condiciones"]}
    assert ops == {"entre", "no"}


# ── ids determinísticos y deduplicados ──────────────────────────────────────

def test_ids_deterministicos_y_deduplicados():
    est1 = Estrategia("x").comprar((ind.SMA(50) > precio.cierre) & (precio.cierre > ind.SMA(50)))
    est2 = Estrategia("x").comprar((ind.SMA(50) > precio.cierre) & (precio.cierre > ind.SMA(50)))
    # dos SMA(50) sueltas colapsan en un único indicador declarado
    assert len(est1.a_dict()["indicadores"]) == 1
    assert est1.a_dict()["indicadores"][0]["id"] == "sma_50"
    # dos builds idénticos dan el mismo JSON byte a byte
    assert est1.a_json() == est2.a_json()


def test_slug_de_clave_para_varios_indicadores():
    assert ind.SMA(50).id == "sma_50"
    assert ind.EXTREMOS(ventana=0).id == "extremos_0"
    assert ind.MACD().id == "macd_12_26_9"
    assert ind.OBV().id == "obv"


def test_definicion_recolecta_solo_indicadores_referenciados():
    ind.RSI(14)  # creado pero nunca usado en una condición
    est = Estrategia("x").comprar(ind.SMA(20) > precio.cierre)
    ids = [i["id"] for i in est.a_dict()["indicadores"]]
    assert ids == ["sma_20"]


# ── aplanado ────────────────────────────────────────────────────────────────

def test_a_and_b_and_c_se_aplana_a_un_nodo():
    a = precio.cierre > 1
    b = precio.cierre > 2
    c = precio.cierre > 3
    cond = a & b & c
    assert cond.dsl["op"] == "y"
    assert len(cond.dsl["condiciones"]) == 3
    assert all("condiciones" not in h for h in cond.dsl["condiciones"])


def test_doble_negacion_se_cancela():
    a = precio.cierre > 1
    assert (~~a).dsl == a.dsl


def test_todas_y_alguna_aplanan():
    conds = [precio.cierre > i for i in range(4)]
    assert len(todas(*conds).dsl["condiciones"]) == 4
    assert alguna(*conds).dsl["op"] == "o"
    assert len(alguna(*conds).dsl["condiciones"]) == 4


# ── el bool prohibido ───────────────────────────────────────────────────────

def test_and_python_explota_con_mensaje_claro():
    a = precio.cierre > 1
    b = precio.cierre < 100
    with pytest.raises(TypeError, match="'&'"):
        a and b


def test_if_cond_explota():
    a = precio.cierre > 1
    with pytest.raises(TypeError):
        bool(a)

    def _usa_if():
        if a:
            return 1
        return 0
    with pytest.raises(TypeError):
        _usa_if()


def test_comparacion_encadenada_explota():
    x = ind.RSI(14)
    with pytest.raises(TypeError):
        30 < x < 70  # Python lo convierte en (30 < x) and (x < 70)


# ── errores tempranos ──────────────────────────────────────────────────────

def test_parametro_desconocido_falla_en_la_construccion():
    with pytest.raises(TypeError, match="desconocido"):
        ind.SMA(periodoo=50)


def test_salida_desconocida_falla_al_referenciarla():
    macd = ind.MACD()
    with pytest.raises(AttributeError, match="salida"):
        macd.no_existe


def test_indicador_multisalida_sin_elegir_salida_falla():
    with pytest.raises((AttributeError, EstrategiaInvalida)):
        Estrategia("x").comprar(ind.MACD() > precio.cierre).definicion()


def test_parametro_fuera_de_rango_falla_en_la_construccion():
    with pytest.raises(ValueError):
        ind.EXTREMOS(ventana=5000)


def test_falta_comprar_levanta_estrategia_invalida():
    with pytest.raises(EstrategiaInvalida):
        Estrategia("x").definicion()


# ── a_dataframe alineado ───────────────────────────────────────────────────

def test_a_dataframe_alineado_con_las_barras():
    barras = _barras([10, 12, 11, 9, 13, 8, 14, 7, 15, 6, 16])
    est = Estrategia("x").comprar(ind.EXTREMOS(ventana=0).dist_min_pct <= 1)
    df = a_dataframe(barras, est.definicion())
    assert len(df) == len(barras)
    for salida in ("maximo", "minimo", "medio", "dist_max_pct", "dist_min_pct"):
        assert f"extremos_0.{salida}" in df.columns
    assert "entrada" in df.columns and "salida" in df.columns
    assert list(df.index) == [b.fecha for b in barras]


def test_comparar_con_mascara_detecta_diferencias():
    # close-only: _hl degrada a (cierre, cierre), así el canal usa el cierre y la máscara de
    # pandas equivalente es exacta.
    barras = _barras_close_only([10, 9, 8, 7, 6, 7, 8, 9, 10, 11])
    est = Estrategia("x").comprar(ind.EXTREMOS(ventana=0).dist_min_pct <= 1e-9)
    minimo_acum, m = [], None
    for b in barras:
        m = b.cierre if m is None else min(m, b.cierre)
        minimo_acum.append(b.cierre <= m + 1e-9)
    assert comparar_con_mascara(est, barras, minimo_acum).empty
    # una máscara arbitrariamente mala sí produce filas
    assert not comparar_con_mascara(est, barras, [not x for x in minimo_acum]).empty
