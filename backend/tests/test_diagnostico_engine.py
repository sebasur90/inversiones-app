"""Tests para el motor puro de diagnóstico."""
import pytest
from datetime import date
from app.services import diagnostico_engine


class TestEvaluarDrawdown:
    def test_drawdown_ok_sin_hallazgo(self):
        drawdown = {"estado": "ok", "maximo": -0.10}
        result = diagnostico_engine.evaluar_drawdown(drawdown)
        assert result is None

    def test_drawdown_advertencia(self):
        drawdown = {"estado": "ok", "maximo": -0.20}
        result = diagnostico_engine.evaluar_drawdown(drawdown)
        assert result is not None
        assert result["severidad"] == "advertencia"
        assert result["tipo"] == "drawdown_elevado"

    def test_drawdown_critico(self):
        drawdown = {"estado": "ok", "maximo": -0.40}
        result = diagnostico_engine.evaluar_drawdown(drawdown)
        assert result is not None
        assert result["severidad"] == "critico"

    def test_drawdown_datos_insuficientes(self):
        drawdown = {"estado": "datos_insuficientes", "maximo": None}
        result = diagnostico_engine.evaluar_drawdown(drawdown)
        assert result is None

    def test_drawdown_sin_maximo(self):
        drawdown = {"estado": "ok", "maximo": None}
        result = diagnostico_engine.evaluar_drawdown(drawdown)
        assert result is None


class TestEvaluarVolatilidad:
    def test_volatilidad_ok_sin_hallazgo(self):
        vol = {"estado": "ok", "anualizada": 0.20}
        result = diagnostico_engine.evaluar_volatilidad(vol)
        assert result is None

    def test_volatilidad_advertencia(self):
        vol = {"estado": "ok", "anualizada": 0.35}
        result = diagnostico_engine.evaluar_volatilidad(vol)
        assert result is not None
        assert result["severidad"] == "advertencia"

    def test_volatilidad_critico(self):
        vol = {"estado": "ok", "anualizada": 0.50}
        result = diagnostico_engine.evaluar_volatilidad(vol)
        assert result is not None
        assert result["severidad"] == "critico"


class TestEvaluarConcentracion:
    def test_concentracion_ok_sin_hallazgo(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.10}]
        result = diagnostico_engine.evaluar_concentracion(conc)
        assert result is None

    def test_concentracion_advertencia(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.20, "effective_n": 5.0}]
        result = diagnostico_engine.evaluar_concentracion(conc)
        assert result is not None
        assert result["severidad"] == "advertencia"

    def test_concentracion_critico(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.30, "effective_n": 3.3}]
        result = diagnostico_engine.evaluar_concentracion(conc)
        assert result is not None
        assert result["severidad"] == "critico"

    def test_concentracion_sin_eje_ticker(self):
        conc = [{"eje": "Sector", "estado": "ok", "hhi_normalizado": 0.50}]
        result = diagnostico_engine.evaluar_concentracion(conc)
        assert result is None


class TestEvaluarRebalanceo:
    def test_rebalanceo_sin_necesarios(self):
        rebal = [
            {
                "eje": "Ticker",
                "items": [
                    {"etiqueta": "AAPL", "delta_pp": 0.5},
                    {"etiqueta": "TSLA", "delta_pp": -0.3},
                ],
            }
        ]
        result = diagnostico_engine.evaluar_rebalanceo(rebal, tolerancia_pp=2.0)
        assert result is None

    def test_rebalanceo_advertencia(self):
        rebal = [
            {
                "eje": "Ticker",
                "items": [
                    {"etiqueta": "AAPL", "delta_pp": 2.5},
                    {"etiqueta": "TSLA", "delta_pp": -2.1},
                ],
            }
        ]
        result = diagnostico_engine.evaluar_rebalanceo(rebal, tolerancia_pp=2.0)
        assert result is not None
        assert result["severidad"] == "advertencia"
        assert result["tipo"] == "rebalanceo_necesario"
        assert "posiciones_fuera_tolerancia" in result["dato_disparador"]

    def test_rebalanceo_critico(self):
        rebal = [
            {
                "eje": "Ticker",
                "items": [
                    {"etiqueta": "AAPL", "delta_pp": 7.0},
                ],
            }
        ]
        result = diagnostico_engine.evaluar_rebalanceo(rebal, tolerancia_pp=2.0)
        assert result is not None
        assert result["severidad"] == "critico"

    def test_rebalanceo_sin_eje_ticker(self):
        rebal = [{"eje": "Sector", "items": []}]
        result = diagnostico_engine.evaluar_rebalanceo(rebal, tolerancia_pp=2.0)
        assert result is None


class TestEvaluarStopLoss:
    def test_stop_loss_sin_disparados(self):
        rend = [
            {"ticker": "AAPL", "nombre": "Apple", "stop_loss_disparado": False},
            {"ticker": "TSLA", "nombre": "Tesla", "stop_loss_disparado": False},
        ]
        result = diagnostico_engine.evaluar_stop_loss(rend)
        assert result is None

    def test_stop_loss_con_disparados(self):
        rend = [
            {"ticker": "AAPL", "nombre": "Apple", "stop_loss_disparado": True},
            {"ticker": "TSLA", "nombre": "Tesla", "stop_loss_disparado": True},
        ]
        result = diagnostico_engine.evaluar_stop_loss(rend)
        assert result is not None
        assert result["severidad"] == "critico"
        assert result["dato_disparador"]["cantidad"] == 2


class TestEvaluarObjetivoPrecio:
    def test_objetivo_precio_sin_alcanzados(self):
        rend = [{"ticker": "AAPL", "objetivo_alcanzado": False}]
        result = diagnostico_engine.evaluar_objetivo_precio(rend)
        assert result is None

    def test_objetivo_precio_con_alcanzados(self):
        rend = [
            {"ticker": "AAPL", "nombre": "Apple", "objetivo_alcanzado": True},
            {"ticker": "TSLA", "nombre": "Tesla", "objetivo_alcanzado": False},
        ]
        result = diagnostico_engine.evaluar_objetivo_precio(rend)
        assert result is not None
        assert result["severidad"] == "info"


class TestEvaluarObjetivoInversion:
    def test_objetivo_none(self):
        result = diagnostico_engine.evaluar_objetivo_inversion(None)
        assert result is None

    def test_objetivo_alcanzable(self):
        objetivo = {"alcanzable": True, "monto_usd": 10000}
        result = diagnostico_engine.evaluar_objetivo_inversion(objetivo)
        assert result is None

    def test_objetivo_advertencia(self):
        objetivo = {
            "alcanzable": False,
            "monto_usd": 10000,
            "deficit_usd": 1000,
            "meses_restantes": 12,
        }
        result = diagnostico_engine.evaluar_objetivo_inversion(objetivo)
        assert result is not None
        assert result["severidad"] == "advertencia"

    def test_objetivo_critico(self):
        objetivo = {
            "alcanzable": False,
            "monto_usd": 10000,
            "deficit_usd": 2500,
            "meses_restantes": 12,
        }
        result = diagnostico_engine.evaluar_objetivo_inversion(objetivo)
        assert result is not None
        assert result["severidad"] == "critico"


class TestEvaluarVencimientos:
    def test_vencimientos_sin_vencidos(self):
        venc = [{"dias_restantes": 100, "vencido": False, "ticker": "BOND"}]
        result = diagnostico_engine.evaluar_vencimientos(venc)
        assert result is None

    def test_vencimientos_proximo(self):
        venc = [
            {"dias_restantes": 60, "vencido": False, "ticker": "BOND", "nombre": "Bond"},
        ]
        result = diagnostico_engine.evaluar_vencimientos(venc)
        assert result is not None
        assert result["severidad"] == "advertencia"

    def test_vencimientos_vencido(self):
        venc = [
            {"dias_restantes": -5, "vencido": True, "ticker": "BOND", "nombre": "Bond"},
        ]
        result = diagnostico_engine.evaluar_vencimientos(venc)
        assert result is not None
        assert result["severidad"] == "critico"


class TestEvaluarComisiones:
    def test_comisiones_sin_datos(self):
        comis = {"por_mes": []}
        result = diagnostico_engine.evaluar_comisiones(comis, 100000)
        assert result is None

    def test_comisiones_advertencia(self):
        comis = {
            "por_mes": [
                {"periodo": "2026-06", "total_usd": 80},
                {"periodo": "2026-07", "total_usd": 90},
                {"periodo": "2026-08", "total_usd": 100},
            ]
        }
        # 270/3 * 4 = 360/año, 360/100000 = 0.36%
        result = diagnostico_engine.evaluar_comisiones(comis, 100000)
        assert result is not None
        assert result["severidad"] == "advertencia"

    def test_comisiones_critico(self):
        comis = {
            "por_mes": [
                {"periodo": "2026-06", "total_usd": 200},
                {"periodo": "2026-07", "total_usd": 200},
                {"periodo": "2026-08", "total_usd": 200},
            ]
        }
        # 600/3 * 4 = 800/año, 800/100000 = 0.8%
        result = diagnostico_engine.evaluar_comisiones(comis, 100000)
        assert result is not None
        assert result["severidad"] == "critico"


class TestPriorizarHallazgos:
    def test_prioriza_por_severidad(self):
        hallazgos = [
            {"tipo": "volatilidad_elevada", "severidad": "info"},
            {"tipo": "drawdown_elevado", "severidad": "critico"},
            {"tipo": "concentracion_alta", "severidad": "advertencia"},
        ]
        result = diagnostico_engine.priorizar_hallazgos(hallazgos)
        assert result[0]["severidad"] == "critico"
        assert result[1]["severidad"] == "advertencia"
        assert result[2]["severidad"] == "info"

    def test_prioriza_por_tipo_dentro_severidad(self):
        hallazgos = [
            {"tipo": "objetivo_precio_alcanzado", "severidad": "info"},
            {"tipo": "stop_loss_disparado", "severidad": "info"},
        ]
        result = diagnostico_engine.priorizar_hallazgos(hallazgos)
        # stop_loss_disparado tiene índice 0, objetivo_precio_alcanzado tiene 9
        assert result[0]["tipo"] == "stop_loss_disparado"
        assert result[1]["tipo"] == "objetivo_precio_alcanzado"


class TestScoreFunctions:
    def test_score_riesgo_ok(self):
        drawdown = {"estado": "ok", "maximo": -0.20}
        volatilidad = {"estado": "ok", "anualizada": 0.25}
        result = diagnostico_engine.score_riesgo(drawdown, volatilidad)
        assert result is not None
        assert 0 <= result["score"] <= 100

    def test_score_riesgo_missing_data(self):
        drawdown = {"estado": "datos_insuficientes", "maximo": None}
        volatilidad = {"estado": "ok", "anualizada": 0.25}
        result = diagnostico_engine.score_riesgo(drawdown, volatilidad)
        assert result is not None  # Partial data still gives score

    def test_score_concentracion_ok(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.20}]
        result = diagnostico_engine.score_concentracion(conc)
        assert result is not None
        assert 0 <= result["score"] <= 100

    def test_score_diversificacion_ok(self):
        conc = [
            {"eje": "Tipo de instrumento", "estado": "ok", "hhi_normalizado": 0.15},
            {"eje": "Sector", "estado": "ok", "hhi_normalizado": 0.20},
            {"eje": "Mercado", "estado": "ok", "hhi_normalizado": 0.10},
        ]
        result = diagnostico_engine.score_diversificacion(conc)
        assert result is not None
        assert 0 <= result["score"] <= 100

    def test_score_performance_vs_benchmark(self):
        calmar = {"estado": "ok", "retorno_anualizado": 0.12}
        result = diagnostico_engine.score_performance(calmar, 0.10)
        assert result is not None
        assert result["score"] == 55.0  # (0.12 - 0.10) / 0.20 * 50 + 50 = 55

    def test_score_performance_sin_benchmark(self):
        calmar = {"estado": "ok", "retorno_anualizado": 0.12}
        result = diagnostico_engine.score_performance(calmar, None)
        assert result is not None
        assert 0 <= result["score"] <= 100

    def test_score_objetivo_alcanzable(self):
        objetivo = {"alcanzable": True, "monto_usd": 10000}
        result = diagnostico_engine.score_objetivo(objetivo)
        assert result is not None
        assert result["score"] == 100.0

    def test_score_objetivo_con_deficit(self):
        objetivo = {"alcanzable": False, "monto_usd": 10000, "deficit_usd": 2000}
        result = diagnostico_engine.score_objetivo(objetivo)
        assert result is not None
        assert 0 <= result["score"] <= 100


class TestCalcularSaludCartera:
    def test_todas_dimensiones_presentes(self):
        dimensiones_raw = {
            "riesgo": {"score": 60, "detalle": "..."},
            "concentracion": {"score": 70, "detalle": "..."},
            "diversificacion": {"score": 80, "detalle": "..."},
            "performance": {"score": 75, "detalle": "..."},
            "objetivo": {"score": 90, "detalle": "..."},
        }
        result = diagnostico_engine.calcular_salud_cartera(dimensiones_raw)
        assert result["score_total"] is not None
        assert 0 <= result["score_total"] <= 100
        assert len(result["dimensiones"]) == 5
        assert all(d["estado"] == "ok" for d in result["dimensiones"])

    def test_una_dimension_excluida(self):
        dimensiones_raw = {
            "riesgo": {"score": 60, "detalle": "..."},
            "concentracion": {"score": 70, "detalle": "..."},
            "diversificacion": {"score": 80, "detalle": "..."},
            "performance": {"score": 75, "detalle": "..."},
            "objetivo": None,  # Excluida
        }
        result = diagnostico_engine.calcular_salud_cartera(dimensiones_raw)
        assert result["score_total"] is not None
        objetivo_dim = next(d for d in result["dimensiones"] if d["nombre"] == "objetivo")
        assert objetivo_dim["estado"] == "excluida"
        assert objetivo_dim["score"] is None

    def test_todas_dimensiones_excluidas(self):
        dimensiones_raw = {
            "riesgo": None,
            "concentracion": None,
            "diversificacion": None,
            "performance": None,
            "objetivo": None,
        }
        result = diagnostico_engine.calcular_salud_cartera(dimensiones_raw)
        assert result["score_total"] is None
        assert all(d["estado"] == "excluida" for d in result["dimensiones"])
