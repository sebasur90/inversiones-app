"""Motor puro del mapa de mercado: variaciones por calendario, conversión a USD y tamaño."""
from datetime import date, timedelta

import pytest

from app.services import mapa_mercado_engine as eng


def _serie(desde: date, cierres: list[float], salto: int = 1):
    return [(desde + timedelta(days=i * salto), c) for i, c in enumerate(cierres)]


def test_variacion_diaria_contra_la_rueda_anterior():
    v = eng.variaciones([(date(2026, 10, 9), 100.0), (date(2026, 10, 12), 103.0)])  # viernes → lunes
    assert v.var_1d == pytest.approx(0.03)
    assert v.fecha_cierre == date(2026, 10, 12)
    assert v.cierre == 103.0


def test_ventanas_semana_mes_y_anio():
    serie = _serie(date(2025, 10, 1), [100.0] * 380)  # un año largo de días corridos, plano
    serie[-1] = (serie[-1][0], 110.0)
    v = eng.variaciones(serie)
    assert v.var_1s == pytest.approx(0.10)
    assert v.var_1m == pytest.approx(0.10)
    assert v.var_1a == pytest.approx(0.10)


def test_historia_insuficiente_deja_la_ventana_en_none():
    serie = _serie(date(2026, 10, 1), [100.0, 101.0, 102.0, 103.0, 104.0])
    v = eng.variaciones(serie)
    assert v.var_1d == pytest.approx(104 / 103 - 1)
    assert v.var_1s is None and v.var_1m is None and v.var_1a is None


def test_un_solo_cierre_no_tiene_variacion_diaria():
    v = eng.variaciones([(date(2026, 10, 9), 50.0)])
    assert v is not None and v.var_1d is None


def test_serie_vacia_o_cierre_muy_viejo_es_none():
    assert eng.variaciones([]) is None
    vieja = [(date(2026, 9, 1), 10.0), (date(2026, 9, 2), 11.0)]
    assert eng.variaciones(vieja, hoy=date(2026, 10, 19)) is None
    assert eng.variaciones(vieja, hoy=date(2026, 9, 5)) is not None


def test_el_cierre_de_referencia_no_puede_estar_muy_lejos():
    # Hueco de dos meses: el "hace 7 días" cae en el hueco y no se inventa con un dato de hace semanas.
    serie = [(date(2026, 8, 1), 100.0), (date(2026, 10, 9), 120.0), (date(2026, 10, 12), 121.0)]
    v = eng.variaciones(serie)
    assert v.var_1d == pytest.approx(121 / 120 - 1)
    assert v.var_1s is None and v.var_1m is None


def test_a_usd_divide_por_el_mep_de_cada_fecha():
    serie = [(date(2026, 10, 8), 1000.0), (date(2026, 10, 9), 1200.0)]
    mep = {date(2026, 10, 8): 1000.0, date(2026, 10, 9): 1200.0}
    out = eng.a_usd(serie, mep)
    assert out == [(date(2026, 10, 8), 1.0), (date(2026, 10, 9), 1.0)]
    # El dólar subió lo mismo que la acción: en USD no se movió.
    assert eng.variaciones(out).var_1d == pytest.approx(0.0)


def test_a_usd_usa_el_ultimo_mep_publicado_en_feriados():
    serie = [(date(2026, 10, 12), 1100.0)]  # lunes feriado sin MEP
    out = eng.a_usd(serie, {date(2026, 10, 9): 1100.0})
    assert out == [(date(2026, 10, 12), 1.0)]


def test_a_usd_sin_mep_suficiente_devuelve_none_en_vez_de_mezclar_monedas():
    assert eng.a_usd([(date(2026, 10, 9), 1000.0)], {}) is None
    assert eng.a_usd([(date(2026, 10, 9), 1000.0)], {date(2026, 1, 1): 900.0}) is None


@pytest.mark.parametrize("cap,esperado", [
    (3e12, eng.TAMANO_MEGA),
    (200e9, eng.TAMANO_MEGA),
    (50e9, eng.TAMANO_GRANDE),
    (5e9, eng.TAMANO_MEDIANA),
    (1e9, eng.TAMANO_CHICA),
    (None, eng.TAMANO_SIN_DATO),
    (0, eng.TAMANO_SIN_DATO),
])
def test_tamano_empresa(cap, esperado):
    assert eng.tamano_empresa(cap) == esperado
