"""Motor puro de intervalos: agregación de barras diarias en semanales y mensuales."""
from datetime import date, timedelta

import pytest

from app.services import intervalos_engine as ie
from app.services.indicadores_engine import Barra


def _b(fecha, cierre, ap=None, mx=None, mn=None, vol=None):
    return Barra(fecha=fecha, cierre=cierre, apertura=ap, maximo=mx, minimo=mn, volumen=vol)


def _ruedas(desde, hasta):
    """Barras diarias de lunes a viernes, cierre = número de orden."""
    dia, n, out = desde, 0, []
    while dia <= hasta:
        if dia.weekday() < 5:
            n += 1
            out.append(_b(dia, float(n), ap=n - 0.5, mx=n + 1.0, mn=n - 1.0, vol=100.0))
        dia += timedelta(days=1)
    return out


def test_clave_periodo_semana_iso_y_mes():
    # 2026-01-01 (jueves) cae en la semana 1; el 29/12/2025 (lunes) es la misma semana ISO.
    assert ie.clave_periodo(date(2025, 12, 29), ie.SEMANAL) == ie.clave_periodo(date(2026, 1, 2), ie.SEMANAL)
    assert ie.clave_periodo(date(2026, 1, 2), ie.SEMANAL) != ie.clave_periodo(date(2026, 1, 5), ie.SEMANAL)
    assert ie.clave_periodo(date(2026, 1, 31), ie.MENSUAL) == (2026, 1)
    assert ie.clave_periodo(date(2026, 2, 1), ie.MENSUAL) == (2026, 2)


def test_agregar_semanal_ohlcv():
    barras = [
        _b(date(2026, 3, 2), 10, ap=9, mx=12, mn=8, vol=100),    # lunes
        _b(date(2026, 3, 3), 11, ap=10, mx=15, mn=10, vol=200),
        _b(date(2026, 3, 4), 9, ap=11, mx=11, mn=7, vol=300),
        _b(date(2026, 3, 9), 20, ap=18, mx=21, mn=17, vol=50),   # semana siguiente
    ]
    s = ie.agregar(barras, ie.SEMANAL)
    assert len(s) == 2
    assert s[0] == _b(date(2026, 3, 4), 9, ap=9, mx=15, mn=7, vol=600)   # fecha = última rueda
    assert s[1].fecha == date(2026, 3, 9) and s[1].volumen == 50


def test_semana_con_feriado_usa_la_ultima_rueda_disponible():
    # Semana con jueves feriado y viernes hábil, y otra que termina el miércoles (feriados de jueves y viernes).
    barras = [_b(date(2026, 4, d), float(d)) for d in (6, 7, 8, 9, 10)]
    barras = [b for b in barras if b.fecha != date(2026, 4, 9)]
    assert ie.agregar(barras, ie.SEMANAL)[0].fecha == date(2026, 4, 10)
    corta = [b for b in barras if b.fecha <= date(2026, 4, 8)]
    assert ie.agregar(corta, ie.SEMANAL)[0].fecha == date(2026, 4, 8)


def test_mes_parcial_al_inicio_y_al_final():
    barras = _ruedas(date(2026, 1, 28), date(2026, 3, 3))   # enero y marzo parciales, febrero completo
    m = ie.agregar(barras, ie.MENSUAL)
    assert [b.fecha.month for b in m] == [1, 2, 3]
    assert m[0].fecha == date(2026, 1, 30)                  # sólo 28, 29 y 30 de enero (viernes)
    assert m[2].fecha == date(2026, 3, 3)
    assert m[1].volumen == 100.0 * 20                       # febrero 2026: 20 ruedas
    assert m[1].cierre == barras[[b.fecha for b in barras].index(date(2026, 2, 27))].cierre


def test_serie_de_solo_cierres_no_inventa_ohlc():
    barras = [_b(date(2026, 3, 2), 10), _b(date(2026, 3, 3), 12)]
    s = ie.agregar(barras, ie.SEMANAL)[0]
    assert (s.apertura, s.maximo, s.minimo, s.volumen) == (None, None, None, None) and s.cierre == 12


def test_serie_mixta_usa_el_cierre_de_la_barra_sin_ohlc():
    barras = [_b(date(2026, 3, 2), 10), _b(date(2026, 3, 3), 12, ap=11, mx=13, mn=11)]
    s = ie.agregar(barras, ie.SEMANAL)[0]
    assert (s.apertura, s.maximo, s.minimo) == (10, 13, 10)


def test_diario_devuelve_las_mismas_barras():
    barras = _ruedas(date(2026, 3, 2), date(2026, 3, 13))
    assert ie.agregar(barras, ie.DIARIO) == barras
    assert ie.agregar_serie(barras, ie.DIARIO, 3) == (barras, 3)


def test_agregar_serie_traduce_indice_desde_al_periodo_que_lo_contiene():
    barras = _ruedas(date(2026, 3, 2), date(2026, 3, 27))    # 4 semanas completas
    agregadas, desde = ie.agregar_serie(barras, ie.SEMANAL, 7)   # 7 = miércoles de la semana 2
    assert len(agregadas) == 4 and desde == 1
    assert ie.agregar_serie(barras, ie.SEMANAL, 0)[1] == 0
    assert ie.agregar_serie(barras, ie.MENSUAL, 7) == (ie.agregar(barras, ie.MENSUAL), 0)
