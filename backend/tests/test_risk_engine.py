"""Tests numéricos del motor puro de riesgo (backend/app/services/risk_engine.py).

Los valores esperados se calculan a mano en los comentarios de cada test (no reimplementando
la fórmula bajo test), como referencia manual de verificación.
"""
import math
from datetime import date

import pytest

from app.services import risk_engine


# ── construir_indice ─────────────────────────────────────────────────────────

def test_construir_indice_compone_y_mantiene_plano_en_meses_sin_tenencia():
    retornos = {
        (2024, 1): 0.10,
        (2024, 2): None,   # sin tenencia: no compone
        (2024, 3): -0.05,
    }
    indice = risk_engine.construir_indice(retornos)

    assert [f for f, _ in indice] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)]
    assert indice[0][1] == pytest.approx(110.0)   # 100 * 1.10
    assert indice[1][1] == pytest.approx(110.0)   # plano, no compone
    assert indice[2][1] == pytest.approx(104.5)   # 110 * 0.95


# ── calcular_drawdown ─────────────────────────────────────────────────────────

def test_drawdown_maximo_y_actual_sin_recuperar():
    # NAV: 100 -> 120 -> 90 -> 110. Pico en 120 (feb), valle en 90 (mar).
    # drawdown máximo = 90/120 - 1 = -25%. drawdown actual = 110/120 - 1 = -8.33%.
    indice = [
        (date(2024, 1, 31), 100.0),
        (date(2024, 2, 29), 120.0),
        (date(2024, 3, 31), 90.0),
        (date(2024, 4, 30), 110.0),
    ]
    resultado = risk_engine.calcular_drawdown(indice)

    assert resultado["estado"] == "ok"
    assert resultado["maximo"] == pytest.approx(-0.25)
    assert resultado["actual"] == pytest.approx(-1 / 12, abs=1e-4)  # -8.33%
    assert resultado["fecha_pico"] == date(2024, 2, 29)
    assert resultado["fecha_valle"] == date(2024, 3, 31)
    assert resultado["en_recuperacion"] is True
    assert resultado["tiempo_recuperacion_meses"] is None


def test_drawdown_con_recuperacion():
    # Mismo camino que el test anterior, pero en mayo el NAV vuelve a superar el pico (120).
    indice = [
        (date(2024, 1, 31), 100.0),
        (date(2024, 2, 29), 120.0),
        (date(2024, 3, 31), 90.0),
        (date(2024, 4, 30), 110.0),
        (date(2024, 5, 31), 130.0),
    ]
    resultado = risk_engine.calcular_drawdown(indice)

    assert resultado["maximo"] == pytest.approx(-0.25)
    assert resultado["en_recuperacion"] is False
    assert resultado["tiempo_recuperacion_meses"] == 2  # de marzo a mayo
    assert resultado["actual"] == pytest.approx(0.0)  # nuevo máximo histórico


def test_serie_drawdown_punto_a_punto():
    # Mismo camino 100 -> 120 -> 90 -> 110: drawdown 0%, 0%, -25%, -8.33% respecto del pico corriente.
    indice = [
        (date(2024, 1, 31), 100.0),
        (date(2024, 2, 29), 120.0),
        (date(2024, 3, 31), 90.0),
        (date(2024, 4, 30), 110.0),
    ]
    serie = risk_engine.serie_drawdown(indice)
    valores = [p["drawdown"] for p in serie]
    assert valores[0] == pytest.approx(0.0)
    assert valores[1] == pytest.approx(0.0)
    assert valores[2] == pytest.approx(-0.25)
    assert valores[3] == pytest.approx(-1 / 12, abs=1e-4)


def test_drawdown_datos_insuficientes_con_un_solo_punto():
    resultado = risk_engine.calcular_drawdown([(date(2024, 1, 31), 100.0)])
    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["maximo"] is None


# ── calcular_volatilidad ───────────────────────────────────────────────────────

def test_volatilidad_calculo_manual():
    # 5 meses en 0% y uno en 6%: media = 1%, varianza muestral = 0.0006, stdev = sqrt(0.0006).
    retornos = [0.0, 0.0, 0.0, 0.0, 0.0, 0.06]
    resultado = risk_engine.calcular_volatilidad(retornos)

    stdev_esperado = math.sqrt(0.0006)
    assert resultado["estado"] == "ok"
    assert resultado["mensual"] == pytest.approx(round(stdev_esperado, 4), abs=1e-4)
    assert resultado["anualizada"] == pytest.approx(round(stdev_esperado * math.sqrt(12), 4), abs=1e-4)
    assert resultado["n_obs"] == 6


def test_volatilidad_datos_insuficientes_bajo_el_minimo():
    resultado = risk_engine.calcular_volatilidad([0.01, -0.02, 0.03, 0.0, 0.01])  # 5 < MIN_OBS_VOLATILIDAD (6)
    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["mensual"] is None
    assert resultado["n_obs"] == 5


# ── calcular_sortino ────────────────────────────────────────────────────────

def test_sortino_calculo_manual():
    # retornos: 0.02, -0.01, 0.03, -0.02, 0.01, 0.00 (media = 0.005)
    # bajo MAR=0: -0.01, -0.02 -> desvio_bajo = sqrt((0.0001+0.0004)/5) = sqrt(0.0001) = 0.01
    # sortino = (0.005 / 0.01) * sqrt(12) = 0.5 * sqrt(12)
    retornos = [0.02, -0.01, 0.03, -0.02, 0.01, 0.00]
    resultado = risk_engine.calcular_sortino(retornos, mar=0.0)

    esperado = 0.5 * math.sqrt(12)
    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(round(esperado, 4), abs=1e-4)


def test_sortino_sin_retornos_negativos():
    resultado = risk_engine.calcular_sortino([0.01, 0.02, 0.03, 0.01, 0.02, 0.04], mar=0.0)
    assert resultado["estado"] == "ok"
    assert resultado["valor"] is None  # sin downside deviation, no se puede dividir


# ── calcular_retorno_anualizado / calcular_calmar ────────────────────────────

def test_retorno_anualizado_cagr():
    # 100 -> 144 en 24 meses: CAGR = (1.44)^(12/24) - 1 = sqrt(1.44) - 1 = 0.2
    indice = [(date(2022, 1, 31), 100.0), (date(2024, 1, 31), 144.0)]
    assert risk_engine.calcular_retorno_anualizado(indice) == pytest.approx(0.2)


def test_calmar_calculo_manual():
    resultado = risk_engine.calcular_calmar(retorno_anualizado=0.15, max_drawdown=-0.20)
    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(0.75)


def test_calmar_datos_insuficientes_sin_drawdown():
    resultado = risk_engine.calcular_calmar(retorno_anualizado=0.15, max_drawdown=None)
    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["valor"] is None


# ── calcular_sharpe_vs_benchmark ─────────────────────────────────────────────

def test_sharpe_vs_benchmark_calculo_manual():
    # exceso mes a mes = retorno_cartera - retorno_benchmark(constante 1%)
    claves = [(2024, m) for m in range(1, 7)]
    retornos = dict(zip(claves, [0.02, 0.01, 0.03, 0.00, 0.02, 0.01]))
    benchmark = dict(zip(claves, [0.01] * 6))
    # excesos: 0.01, 0.00, 0.02, -0.01, 0.01, 0.00 -> media=0.005, stdev muestral = sqrt(0.00011)
    resultado = risk_engine.calcular_sharpe_vs_benchmark(retornos, benchmark, "MERVAL")

    stdev_esperado = math.sqrt(0.00011)
    sharpe_esperado = (0.005 / stdev_esperado) * math.sqrt(12)
    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(round(sharpe_esperado, 4), abs=1e-3)
    assert resultado["benchmark"] == "MERVAL"
    assert resultado["n_obs"] == 6


def test_sharpe_sin_benchmark_seleccionado():
    resultado = risk_engine.calcular_sharpe_vs_benchmark({(2024, 1): 0.01}, {}, None)
    assert resultado["estado"] == "sin_benchmark"
    assert resultado["valor"] is None


def test_sharpe_solo_considera_meses_presentes_en_ambas_series():
    retornos = {(2024, 1): 0.02, (2024, 2): 0.01, (2024, 3): 0.03, (2024, 4): 0.0, (2024, 5): 0.02, (2024, 6): 0.01, (2024, 7): 0.05}
    benchmark = {(2024, 1): 0.01, (2024, 2): 0.01, (2024, 3): 0.01, (2024, 4): 0.01, (2024, 5): 0.01, (2024, 6): 0.01}
    resultado = risk_engine.calcular_sharpe_vs_benchmark(retornos, benchmark, "SP500")
    assert resultado["n_obs"] == 6  # julio se descarta: no está en el benchmark


# ── mejores_peores_periodos / frecuencia_positivos_negativos ────────────────

def test_mejores_peores_periodos():
    retornos = {
        (2024, 1): 0.05,
        (2024, 2): -0.03,
        (2024, 3): 0.02,
        (2024, 4): -0.08,
        (2024, 5): 0.01,
    }
    resultado = risk_engine.mejores_peores_periodos(retornos, n=2)
    assert [p["retorno"] for p in resultado["mejores"]] == [0.05, 0.02]
    assert [p["retorno"] for p in resultado["peores"]] == [-0.08, -0.03]


def test_frecuencia_positivos_negativos():
    resultado = risk_engine.frecuencia_positivos_negativos([0.01, -0.02, 0.03, 0.0, -0.01])
    assert resultado["estado"] == "ok"
    assert resultado["pct_positivos"] == pytest.approx(0.4)
    assert resultado["pct_negativos"] == pytest.approx(0.4)
    assert resultado["n_obs"] == 5


# ── calcular_tracking_error ──────────────────────────────────────────────────

def test_tracking_error_calculo_manual():
    # excesos: 0.01, 0.00, 0.02, -0.01, 0.01, 0.00 (media=0.005, var_muestral=0.00011)
    # stdev_mensual = sqrt(0.00011), tracking_error_anualizado = sqrt(0.00011) * sqrt(12)
    claves = [(2024, m) for m in range(1, 7)]
    retornos_cartera = dict(zip(claves, [0.02, 0.01, 0.03, 0.00, 0.02, 0.01]))
    retornos_benchmark = dict(zip(claves, [0.01] * 6))
    resultado = risk_engine.calcular_tracking_error(retornos_cartera, retornos_benchmark)

    stdev_esperado = math.sqrt(0.00011)
    te_esperado = round(stdev_esperado * math.sqrt(12), 4)
    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(te_esperado, abs=1e-3)
    assert resultado["n_obs"] == 6


def test_tracking_error_datos_insuficientes():
    resultado = risk_engine.calcular_tracking_error({(2024, 1): 0.01}, {(2024, 1): 0.00})
    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["valor"] is None


# ── calcular_beta ───────────────────────────────────────────────────────────

def test_beta_calculo_manual():
    # cartera: 0.02, 0.01, 0.03, 0.00, 0.02, 0.01 (media=0.015)
    # benchmark: 0.01, 0.01, 0.01, 0.01, 0.01, 0.01 (media=0.01, var=0)
    # Pero si benchmark tiene variación: benchmark: 0.00, 0.01, 0.02, 0.01, 0.00, 0.01 (var=0.00067)
    # cov(cartera, benchmark) = E[(cartera-mean_c)*(benchmark-mean_b)]
    claves = [(2024, m) for m in range(1, 7)]
    retornos_cartera = dict(zip(claves, [0.02, 0.01, 0.03, 0.00, 0.02, 0.01]))
    retornos_benchmark = dict(zip(claves, [0.00, 0.01, 0.02, 0.01, 0.00, 0.01]))
    resultado = risk_engine.calcular_beta(retornos_cartera, retornos_benchmark)

    cartera_vals = [0.02, 0.01, 0.03, 0.00, 0.02, 0.01]
    benchmark_vals = [0.00, 0.01, 0.02, 0.01, 0.00, 0.01]
    var_benchmark = statistics.variance(benchmark_vals)
    cov = statistics.covariance(cartera_vals, benchmark_vals)
    beta_esperado = cov / var_benchmark
    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(round(beta_esperado, 4), abs=1e-3)
    assert resultado["n_obs"] == 6


def test_beta_benchmark_sin_varianza():
    # Benchmark constante -> var=0 -> datos insuficientes
    claves = [(2024, m) for m in range(1, 7)]
    retornos_cartera = dict(zip(claves, [0.02, 0.01, 0.03, 0.00, 0.02, 0.01]))
    retornos_benchmark = dict(zip(claves, [0.01] * 6))
    resultado = risk_engine.calcular_beta(retornos_cartera, retornos_benchmark)

    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["valor"] is None


# ── calcular_alpha ──────────────────────────────────────────────────────────

def test_alpha_calculo_manual():
    # cartera_anualizado = 0.20, benchmark_anualizado = 0.10, beta = 1.5
    # alpha = 0.20 - 1.5*0.10 = 0.05 (5%)
    resultado = risk_engine.calcular_alpha(retorno_anualizado_cartera=0.20, retorno_anualizado_benchmark=0.10, beta=1.5)
    assert resultado["estado"] == "ok"
    assert resultado["valor"] == pytest.approx(0.05)


def test_alpha_datos_insuficientes_con_none():
    resultado = risk_engine.calcular_alpha(retorno_anualizado_cartera=None, retorno_anualizado_benchmark=0.10, beta=1.5)
    assert resultado["estado"] == "datos_insuficientes"
    assert resultado["valor"] is None


# ── calcular_information_ratio ──────────────────────────────────────────────

def test_information_ratio_es_igual_a_sharpe_vs_benchmark():
    # IR debería retornar exactamente lo mismo que Sharpe (ambos usan el exceso de retorno)
    claves = [(2024, m) for m in range(1, 7)]
    retornos = dict(zip(claves, [0.02, 0.01, 0.03, 0.00, 0.02, 0.01]))
    benchmark = dict(zip(claves, [0.01] * 6))
    sharpe = risk_engine.calcular_sharpe_vs_benchmark(retornos, benchmark, "MERVAL")
    ir = risk_engine.calcular_information_ratio(retornos, benchmark, "MERVAL")

    assert sharpe["estado"] == ir["estado"]
    assert sharpe["valor"] == ir["valor"]
    assert sharpe["n_obs"] == ir["n_obs"]
