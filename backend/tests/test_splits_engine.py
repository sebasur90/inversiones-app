"""Tests de la detección de splits no ajustados."""
from dataclasses import dataclass
from datetime import date, timedelta

from app.services import splits_engine


@dataclass
class B:
    fecha: date
    cierre: float


def serie(precios, inicio=date(2026, 1, 5)):
    return [B(inicio + timedelta(days=i), p) for i, p in enumerate(precios)]


def test_serie_estable_no_tiene_saltos():
    assert splits_engine.detectar_saltos(serie([100, 101, 99, 102, 100])) == []


def test_split_1_a_2_se_detecta():
    saltos = splits_engine.detectar_saltos(serie([200, 202, 100, 101]))
    assert len(saltos) == 1
    assert saltos[0].etiqueta == "1:2"
    assert saltos[0].precio_previo == 202 and saltos[0].precio == 100


def test_split_1_a_10_se_detecta():
    saltos = splits_engine.detectar_saltos(serie([1000, 1010, 101, 100]))
    assert [s.etiqueta for s in saltos] == ["1:10"]


def test_split_inverso_se_detecta():
    saltos = splits_engine.detectar_saltos(serie([100, 99, 990, 1000]))
    assert [s.etiqueta for s in saltos] == ["10:1"]


def test_caida_fuerte_que_no_es_fraccion_simple_no_se_marca():
    """Un derrumbe del 40% es movimiento real, no split: no se parece a ninguna fracción."""
    assert splits_engine.detectar_saltos(serie([100, 100, 60, 58])) == []


def test_movimiento_chico_no_se_mira():
    """Aunque el ratio quede cerca de algo, por debajo del cambio mínimo no se evalúa."""
    assert splits_engine.detectar_saltos(serie([100, 90, 88])) == []


def test_tolerancia_acepta_ruido_alrededor_del_ratio():
    # 203 → 100 es 0.4926, dentro del 8% de 0.5.
    assert [s.etiqueta for s in splits_engine.detectar_saltos(serie([203, 100]))] == ["1:2"]


def test_fuera_de_tolerancia_no_se_marca():
    # 100 → 58 es 0.58, demasiado lejos de 0.5.
    assert splits_engine.detectar_saltos(serie([100, 58])) == []


def test_varios_splits_en_la_misma_serie():
    saltos = splits_engine.detectar_saltos(serie([400, 200, 199, 100, 99]))
    assert [s.etiqueta for s in saltos] == ["1:2", "1:2"]


def test_cierre_no_positivo_corta_la_comparacion_sin_ensuciar():
    saltos = splits_engine.detectar_saltos(serie([100, 0, 50, 51]))
    assert saltos == []


def test_serie_de_una_barra_o_vacia():
    assert splits_engine.detectar_saltos([]) == []
    assert splits_engine.detectar_saltos(serie([100])) == []


def test_descripcion_es_legible():
    salto = splits_engine.detectar_saltos(serie([200, 100]))[0]
    assert "2026-01-05" in salto.descripcion and "1:2" in salto.descripcion
