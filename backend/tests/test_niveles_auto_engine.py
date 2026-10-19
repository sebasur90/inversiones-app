"""Soportes y resistencias automáticos (services/niveles_auto_engine.py)."""
from datetime import date, timedelta

import pytest

from app.services import niveles_auto_engine as ne
from app.services.indicadores_engine import Barra


def _barras(cierres, maximos=None, minimos=None):
    base = date(2025, 1, 1)
    return [
        Barra(fecha=base + timedelta(days=i), cierre=c, apertura=c,
              maximo=maximos[i] if maximos else None, minimo=minimos[i] if minimos else None)
        for i, c in enumerate(cierres)
    ]


def _onda(n, picos=110.0, valles=90.0):
    """Onda triangular de período 20: techo en la fase 5 y piso en la fase 15."""
    def v(i):
        fase = i % 20
        if fase <= 5:
            return 100 + (picos - 100) / 5 * fase
        if fase <= 15:
            return picos - (picos - valles) / 10 * (fase - 5)
        return valles + (100 - valles) / 5 * (fase - 15)
    return [v(i) for i in range(n)]


def test_pivotes_de_una_onda_y_no_hay_en_las_ultimas_n_barras():
    barras = _barras(_onda(80))
    pv = ne.pivotes(barras, 5)
    assert [(i, p) for i, p, t in pv if t == "maximo"] == [(5, 110.0), (25, 110.0), (45, 110.0), (65, 110.0)]
    assert [(i, p) for i, p, t in pv if t == "minimo"] == [(15, 90.0), (35, 90.0), (55, 90.0)]
    assert max(i for i, _, _ in pv) <= 80 - 1 - 5            # el pivote se confirma N barras después


def test_meseta_cuenta_una_sola_vez():
    cierres = [100, 101, 102, 103, 104, 110, 110, 104, 103, 102, 101, 100, 99]
    pv = [p for p in ne.pivotes(_barras(cierres), 5) if p[2] == "maximo"]
    assert len(pv) == 1 and pv[0][0] == 5                     # el primero de la meseta


def test_niveles_toques_tipo_y_orden():
    niveles = ne.niveles_automaticos(_barras(_onda(80)))
    assert [(n["tipo"], round(n["precio"]), n["toques"]) for n in niveles] == [
        ("resistencia", 110, 4), ("soporte", 90, 3),
    ]
    assert niveles[0]["ultima_fecha"] == date(2025, 1, 1) + timedelta(days=65)
    assert niveles[0]["puntaje"] > 0


def test_agrupa_por_cercania_con_tolerancia_atr():
    onda = _onda(80)
    # El segundo techo sube medio punto: dentro de 0,5 × ATR (ATR = 2 → tolerancia 1) → mismo nivel.
    onda[25] = 110.5
    niveles = ne.niveles_automaticos(_barras(onda))
    resistencias = [n for n in niveles if n["tipo"] == "resistencia"]
    assert len(resistencias) == 1 and resistencias[0]["toques"] == 4
    assert resistencias[0]["precio"] == pytest.approx((110 * 3 + 110.5) / 4)
    # Cuatro puntos arriba ya no es lo mismo: queda como un nivel aparte con un solo toque (descartado).
    onda2 = _onda(80)
    onda2[25] = 114.0
    res2 = [n for n in ne.niveles_automaticos(_barras(onda2)) if n["tipo"] == "resistencia"]
    assert len(res2) == 1 and res2[0]["toques"] == 3


def test_un_solo_toque_no_es_un_nivel():
    assert ne.niveles_automaticos(_barras(_onda(22))) == []   # sólo un techo y un piso confirmados
    assert ne.niveles_automaticos(_barras([100.0] * 5)) == []


def test_el_toque_reciente_pesa_mas_que_el_viejo():
    # Dos techos de 2 toques: uno cerca de 110 (viejo, barras 5 y 25) y otro cerca de 120 (reciente).
    cierres = _onda(100)
    for i in (65, 85):
        cierres[i] = 120.0
        for k in range(1, 6):
            cierres[i - k] = min(cierres[i - k], 120 - 2 * k)
            cierres[i + k] = min(cierres[i + k], 120 - 2 * k)
    niveles = ne.niveles_automaticos(_barras(cierres), max_por_lado=3)
    reciente = next(n for n in niveles if round(n["precio"]) == 120)
    viejo = next(n for n in niveles if n["tipo"] == "resistencia" and round(n["precio"]) == 110)
    assert reciente["puntaje"] > viejo["puntaje"]


def test_devuelve_a_lo_sumo_n_por_lado():
    niveles = ne.niveles_automaticos(_barras(_onda(200)), max_por_lado=1)
    assert sum(1 for n in niveles if n["tipo"] == "resistencia") <= 1
    assert sum(1 for n in niveles if n["tipo"] == "soporte") <= 1


def test_serie_vacia_o_corta_no_lanza():
    assert ne.niveles_automaticos([]) == []
    assert ne.niveles_automaticos(_barras([100.0, 101.0])) == []
