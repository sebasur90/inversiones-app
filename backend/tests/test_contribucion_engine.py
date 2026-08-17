"""Tests numéricos del motor puro de contribución/concentración/correlación
(backend/app/services/contribucion_engine.py).

Los valores esperados se calculan a mano en los comentarios de cada test (no reimplementando
la fórmula bajo test), como referencia manual de verificación.
"""
import pytest

from app.services import contribucion_engine


# ── calcular_hhi ──────────────────────────────────────────────────────────────

def test_hhi_pesos_iguales():
    # 4 posiciones de 25% cada una: HHI = 4 * 25^2 = 2500. effective_n = 10000/2500 = 4.
    resultado = contribucion_engine.calcular_hhi([25.0, 25.0, 25.0, 25.0])

    assert resultado["estado"] == "ok"
    assert resultado["hhi"] == pytest.approx(2500.0)
    assert resultado["hhi_normalizado"] == pytest.approx(0.25)
    assert resultado["effective_n"] == pytest.approx(4.0)
    assert resultado["n_componentes"] == 4


def test_hhi_muy_concentrado():
    # 90/10: HHI = 90^2 + 10^2 = 8100 + 100 = 8200. effective_n = 10000/8200 ≈ 1.2195.
    resultado = contribucion_engine.calcular_hhi([90.0, 10.0])

    assert resultado["estado"] == "ok"
    assert resultado["hhi"] == pytest.approx(8200.0)
    assert resultado["effective_n"] == pytest.approx(1.2195, abs=1e-3)


def test_hhi_sin_datos():
    resultado = contribucion_engine.calcular_hhi([])

    assert resultado["estado"] == "sin_datos"
    assert resultado["hhi"] is None
    assert resultado["effective_n"] is None
    assert resultado["n_componentes"] == 0


# ── calcular_correlacion_par ──────────────────────────────────────────────────

def test_correlacion_perfecta_positiva():
    # y = 2x exactamente: correlación = 1.0
    retornos_x = {(2024, m): float(m) for m in range(1, 8)}
    retornos_y = {(2024, m): float(m) * 2 for m in range(1, 8)}

    resultado = contribucion_engine.calcular_correlacion_par(retornos_x, retornos_y)

    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(1.0)
    assert resultado["n_obs"] == 7


def test_correlacion_perfecta_negativa():
    retornos_x = {(2024, m): float(m) for m in range(1, 8)}
    retornos_y = {(2024, m): -float(m) for m in range(1, 8)}

    resultado = contribucion_engine.calcular_correlacion_par(retornos_x, retornos_y)

    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(-1.0)


def test_correlacion_serie_constante_es_datos_insuficientes():
    # Varianza cero en y: no se puede definir un coeficiente de correlación.
    retornos_x = {(2024, m): float(m) for m in range(1, 8)}
    retornos_y = {(2024, m): 0.05 for m in range(1, 8)}

    resultado = contribucion_engine.calcular_correlacion_par(retornos_x, retornos_y)

    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["valor"] is None


def test_correlacion_menos_de_min_obs_es_datos_insuficientes():
    retornos_x = {(2024, m): float(m) for m in range(1, 5)}  # solo 4 meses
    retornos_y = {(2024, m): float(m) * 2 for m in range(1, 5)}

    resultado = contribucion_engine.calcular_correlacion_par(retornos_x, retornos_y)

    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["valor"] is None
    assert resultado["n_obs"] == 4


# ── construir_matriz_correlacion ──────────────────────────────────────────────

def test_matriz_correlacion_diagonal_es_uno():
    series = {
        "AAA": {(2024, m): float(m) for m in range(1, 8)},
        "BBB": {(2024, m): float(m) * 2 for m in range(1, 8)},
    }
    resultado = contribucion_engine.construir_matriz_correlacion(["AAA", "BBB"], series)

    assert resultado["matriz"][0][0] == 1.0
    assert resultado["matriz"][1][1] == 1.0
    assert resultado["matriz"][0][1] == pytest.approx(1.0)
    assert resultado["matriz"][0][1] == resultado["matriz"][1][0]  # simétrica


def test_matriz_correlacion_advertencia_historial_corto():
    # AAA/BBB con historia suficiente; CCC con muy poca historia frente a ambos.
    # De los 3 pares posibles, 2 son insuficientes (>50%) -> advertencia encendida.
    series = {
        "AAA": {(2024, m): float(m) for m in range(1, 8)},
        "BBB": {(2024, m): float(m) * 2 for m in range(1, 8)},
        "CCC": {(2024, 1): 0.01, (2024, 2): 0.02},
    }
    resultado = contribucion_engine.construir_matriz_correlacion(["AAA", "BBB", "CCC"], series)

    estados = {(p["ticker_a"], p["ticker_b"]): p["estado"] for p in resultado["pares"]}
    assert estados[("AAA", "BBB")] == "ok"
    assert estados[("AAA", "CCC")] == "datos_insuficientes"
    assert estados[("BBB", "CCC")] == "datos_insuficientes"
    assert resultado["advertencia_historial_corto"] is True


def test_matriz_correlacion_sin_advertencia_cuando_mayoria_ok():
    series = {
        "AAA": {(2024, m): float(m) for m in range(1, 8)},
        "BBB": {(2024, m): float(m) * 2 for m in range(1, 8)},
        "CCC": {(2024, m): float(m) * 3 for m in range(1, 8)},
    }
    resultado = contribucion_engine.construir_matriz_correlacion(["AAA", "BBB", "CCC"], series)

    assert resultado["advertencia_historial_corto"] is False
