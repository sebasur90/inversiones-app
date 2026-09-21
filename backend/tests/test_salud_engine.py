"""Tests para el motor puro de Salud de cartera (backend/app/services/salud_engine.py)."""
from datetime import date, timedelta

from app.services import salud_engine
from app.services.diagnostico_engine import evaluar_comisiones


class TestEvaluarRiesgo:
    def test_sin_datos(self):
        dim = salud_engine.evaluar_riesgo({"estado": "datos_insuficientes"}, {"estado": "datos_insuficientes"})
        assert dim["estado"] == "sin_datos"

    def test_normal(self):
        dim = salud_engine.evaluar_riesgo({"estado": "ok", "maximo": -0.05}, {"estado": "ok", "anualizada": 0.10})
        assert dim["estado"] == "normal"

    def test_atencion_por_drawdown(self):
        dim = salud_engine.evaluar_riesgo({"estado": "ok", "maximo": -0.20}, {"estado": "ok", "anualizada": 0.10})
        assert dim["estado"] == "atencion"

    def test_revisar_por_volatilidad(self):
        dim = salud_engine.evaluar_riesgo({"estado": "ok", "maximo": -0.05}, {"estado": "ok", "anualizada": 0.50})
        assert dim["estado"] == "revisar"

    def test_usa_el_peor_de_los_dos(self):
        dim = salud_engine.evaluar_riesgo({"estado": "ok", "maximo": -0.40}, {"estado": "ok", "anualizada": 0.10})
        assert dim["estado"] == "revisar"

    def test_parcial_con_un_solo_dato(self):
        dim = salud_engine.evaluar_riesgo({"estado": "ok", "maximo": -0.20}, {"estado": "datos_insuficientes"})
        assert dim["estado"] == "atencion"
        assert "Caída máx." in dim["valor"]
        assert "volatilidad" not in dim["valor"]


class TestEvaluarConcentracion:
    def test_sin_datos(self):
        dim = salud_engine.evaluar_concentracion([], [], None)
        assert dim["estado"] == "sin_datos"

    def test_normal(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.05, "effective_n": 20}]
        exp = [{"etiqueta": "AL30", "porcentaje": 10.0, "valor_usd": 1000, "valor_ars": 1000}]
        dim = salud_engine.evaluar_concentracion(conc, exp, None)
        assert dim["estado"] == "normal"

    def test_revisar_por_peso_default(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.05, "effective_n": 20}]
        exp = [{"etiqueta": "AL30", "porcentaje": 35.0, "valor_usd": 1000, "valor_ars": 1000}]
        dim = salud_engine.evaluar_concentracion(conc, exp, None)
        assert dim["estado"] == "revisar"

    def test_usa_peso_maximo_configurado(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.05, "effective_n": 20}]
        exp = [{"etiqueta": "AL30", "porcentaje": 12.0, "valor_usd": 1000, "valor_ars": 1000}]
        # peso_maximo=10 -> atención en 10%, revisar en 15%
        dim = salud_engine.evaluar_concentracion(conc, exp, 10.0)
        assert dim["estado"] == "atencion"
        assert "peso máximo configurado" in dim["regla"]

    def test_revisar_por_hhi(self):
        conc = [{"eje": "Ticker", "estado": "ok", "hhi_normalizado": 0.30, "effective_n": 3}]
        exp = [{"etiqueta": "AL30", "porcentaje": 10.0, "valor_usd": 1000, "valor_ars": 1000}]
        dim = salud_engine.evaluar_concentracion(conc, exp, None)
        assert dim["estado"] == "revisar"


class TestEvaluarDiversificacion:
    def test_sin_datos(self):
        dim = salud_engine.evaluar_diversificacion([])
        assert dim["estado"] == "sin_datos"

    def test_normal(self):
        conc = [{"eje": "Ticker", "estado": "ok", "effective_n": 10}, {"eje": "Tipo de instrumento", "estado": "ok", "n_componentes": 3}]
        dim = salud_engine.evaluar_diversificacion(conc)
        assert dim["estado"] == "normal"

    def test_revisar_por_n_efectivo_bajo(self):
        conc = [{"eje": "Ticker", "estado": "ok", "effective_n": 2}]
        dim = salud_engine.evaluar_diversificacion(conc)
        assert dim["estado"] == "revisar"

    def test_atencion_por_un_solo_tipo(self):
        conc = [{"eje": "Ticker", "estado": "ok", "effective_n": 10}, {"eje": "Tipo de instrumento", "estado": "ok", "n_componentes": 1}]
        dim = salud_engine.evaluar_diversificacion(conc)
        assert dim["estado"] == "atencion"


class TestEvaluarLiquidez:
    def test_sin_datos_sin_inventario(self):
        dim = salud_engine.evaluar_liquidez([])
        assert dim["estado"] == "sin_datos"

    def test_normal_por_fci(self):
        inv = [
            {"ticker": "FCI1", "tipo_instrumento": "FCI Money Market", "sector": None, "fecha_vencimiento": None, "valor_usd": 200},
            {"ticker": "AL30", "tipo_instrumento": "Bono", "sector": None, "fecha_vencimiento": date(2030, 1, 1), "valor_usd": 800},
        ]
        dim = salud_engine.evaluar_liquidez(inv, hoy=date(2026, 1, 1))
        assert dim["estado"] == "normal"
        assert "20.0%" in dim["valor"]

    def test_normal_por_sector_liquidez(self):
        inv = [
            {"ticker": "FCI1", "tipo_instrumento": "Fondo", "sector": "Liquidez", "fecha_vencimiento": None, "valor_usd": 300},
            {"ticker": "GGAL", "tipo_instrumento": "Accion", "sector": "Bancos", "fecha_vencimiento": None, "valor_usd": 700},
        ]
        dim = salud_engine.evaluar_liquidez(inv, hoy=date(2026, 1, 1))
        assert dim["estado"] == "normal"

    def test_normal_por_vencimiento_corto(self):
        inv = [
            {"ticker": "LECAP", "tipo_instrumento": "Letra", "sector": None,
             "fecha_vencimiento": date(2026, 3, 1), "valor_usd": 300},
            {"ticker": "AL30", "tipo_instrumento": "Bono", "sector": None,
             "fecha_vencimiento": date(2035, 1, 1), "valor_usd": 700},
        ]
        dim = salud_engine.evaluar_liquidez(inv, hoy=date(2026, 1, 1))
        assert dim["estado"] == "normal"

    def test_revisar_sin_nada_liquido(self):
        inv = [{"ticker": "AL30", "tipo_instrumento": "Bono", "sector": "Soberano",
                "fecha_vencimiento": date(2035, 1, 1), "valor_usd": 1000}]
        dim = salud_engine.evaluar_liquidez(inv, hoy=date(2026, 1, 1))
        assert dim["estado"] == "revisar"


class TestEvaluarCostos:
    def test_sin_datos(self):
        dim = salud_engine.evaluar_costos(None)
        assert dim["estado"] == "sin_datos"

    def test_normal(self):
        dim = salud_engine.evaluar_costos({"anualizado_usd": 10, "ratio": 0.001, "meses_cubiertos": 12})
        assert dim["estado"] == "normal"

    def test_atencion(self):
        dim = salud_engine.evaluar_costos({"anualizado_usd": 150, "ratio": 0.015, "meses_cubiertos": 12})
        assert dim["estado"] == "atencion"

    def test_revisar(self):
        dim = salud_engine.evaluar_costos({"anualizado_usd": 300, "ratio": 0.03, "meses_cubiertos": 12})
        assert dim["estado"] == "revisar"


class TestEvaluarVencimientos:
    def test_no_aplica_sin_bonos(self):
        dim = salud_engine.evaluar_vencimientos([])
        assert dim["estado"] == "sin_datos"

    def test_normal_lejano(self):
        dim = salud_engine.evaluar_vencimientos([{"ticker": "AL30", "nombre": "AL30", "vencido": False, "dias_restantes": 400}])
        assert dim["estado"] == "normal"

    def test_atencion_proximo(self):
        dim = salud_engine.evaluar_vencimientos([{"ticker": "AL30", "nombre": "AL30", "vencido": False, "dias_restantes": 30}])
        assert dim["estado"] == "atencion"

    def test_revisar_vencido(self):
        dim = salud_engine.evaluar_vencimientos([{"ticker": "AL30", "nombre": "AL30", "vencido": True, "dias_restantes": -5}])
        assert dim["estado"] == "revisar"


class TestEvaluarBalanceObjetivo:
    def test_sin_objetivos(self):
        dim = salud_engine.evaluar_balance_objetivo([], 2.0)
        assert dim["estado"] == "sin_datos"

    def test_normal_dentro_de_tolerancia(self):
        ejes = [{"eje": "Tipo", "items": [{"etiqueta": "Bonos", "delta_pp": 1.0, "porcentaje_actual": 51, "porcentaje_objetivo": 50}]}]
        dim = salud_engine.evaluar_balance_objetivo(ejes, 2.0)
        assert dim["estado"] == "normal"

    def test_atencion_fuera_de_tolerancia(self):
        ejes = [{"eje": "Tipo", "items": [{"etiqueta": "Bonos", "delta_pp": 4.0, "porcentaje_actual": 54, "porcentaje_objetivo": 50}]}]
        dim = salud_engine.evaluar_balance_objetivo(ejes, 2.0)
        assert dim["estado"] == "atencion"

    def test_revisar_muy_fuera_de_tolerancia(self):
        ejes = [{"eje": "Tipo", "items": [{"etiqueta": "Bonos", "delta_pp": 10.0, "porcentaje_actual": 60, "porcentaje_objetivo": 50}]}]
        dim = salud_engine.evaluar_balance_objetivo(ejes, 2.0)
        assert dim["estado"] == "revisar"


class TestEvaluarCalidadDatos:
    def test_sin_sync(self):
        dim = salud_engine.evaluar_calidad_datos(None, [], False)
        assert dim["estado"] == "sin_datos"

    def test_normal(self):
        calidad = {"ultimo_sync": {"resultado": "ok", "health_score": 100}}
        dim = salud_engine.evaluar_calidad_datos(calidad, [], False)
        assert dim["estado"] == "normal"

    def test_revisar_por_sync_con_errores(self):
        calidad = {"ultimo_sync": {"resultado": "con_errores", "health_score": 40}}
        dim = salud_engine.evaluar_calidad_datos(calidad, [], False)
        assert dim["estado"] == "revisar"

    def test_revisar_por_posicion_sin_precio(self):
        calidad = {"ultimo_sync": {"resultado": "ok", "health_score": 100}}
        inv = [{"ticker": "XYZ", "sin_precio": True, "sector": "Bancos", "pais": "AR", "dias_precio": None}]
        dim = salud_engine.evaluar_calidad_datos(calidad, inv, False)
        assert dim["estado"] == "revisar"

    def test_atencion_por_sin_sector(self):
        calidad = {"ultimo_sync": {"resultado": "ok", "health_score": 100}}
        inv = [{"ticker": "XYZ", "sin_precio": False, "sector": None, "pais": "AR", "dias_precio": 1}]
        dim = salud_engine.evaluar_calidad_datos(calidad, inv, False)
        assert dim["estado"] == "atencion"


class TestGenerarObservaciones:
    def _base_kwargs(self, **overrides):
        base = dict(
            exposicion_ticker=[],
            peso_maximo=None,
            rebalanceo_ejes=[],
            tolerancia_pp=2.0,
            inventario=[],
            vencimientos=[],
            ratio_comisiones=None,
            calidad=None,
            dim_liquidez=salud_engine.evaluar_liquidez([]),
            dim_diversificacion=salud_engine.evaluar_diversificacion([]),
            dim_riesgo=salud_engine.evaluar_riesgo({"estado": "datos_insuficientes"}, {"estado": "datos_insuficientes"}),
            concentracion=[],
            exposicion_pais=[],
        )
        base.update(overrides)
        return base

    def test_sin_datos_no_genera_nada(self):
        obs = salud_engine.generar_observaciones(**self._base_kwargs())
        assert obs == []

    def test_ticker_sobre_umbral_genera_observacion_con_drilldown(self):
        obs = salud_engine.generar_observaciones(**self._base_kwargs(
            exposicion_ticker=[{"etiqueta": "AL30", "porcentaje": 35.0, "valor_usd": 1, "valor_ars": 1}],
        ))
        assert len(obs) == 1
        assert obs[0]["severidad"] == "revisar"
        assert obs[0]["pantalla"] == "/ticker/AL30"
        assert obs[0]["valor"] == "35.0%"
        assert obs[0]["fuente"]

    def test_instrumentos_sin_sector_se_agrupan(self):
        inv = [
            {"ticker": "A", "sector": None, "pais": "AR", "sin_precio": False, "dias_precio": 1},
            {"ticker": "B", "sector": None, "pais": "AR", "sin_precio": False, "dias_precio": 1},
        ]
        obs = salud_engine.generar_observaciones(**self._base_kwargs(inventario=inv))
        titulos = [o["titulo"] for o in obs]
        assert any("2 instrumento(s) no tienen sector" in t for t in titulos)

    def test_orden_por_severidad(self):
        inv = [{"ticker": "A", "sector": None, "pais": "AR", "sin_precio": False, "dias_precio": 1}]  # atencion
        obs = salud_engine.generar_observaciones(**self._base_kwargs(
            exposicion_ticker=[{"etiqueta": "AL30", "porcentaje": 40.0, "valor_usd": 1, "valor_ars": 1}],  # revisar
            inventario=inv,
        ))
        severidades = [o["severidad"] for o in obs]
        assert severidades == sorted(severidades, key=lambda s: salud_engine.RANK_SEVERIDAD[s])
        assert severidades[0] == "revisar"

    def test_vencimiento_proximo_apunta_a_flujo_caja(self):
        venc = [{"ticker": "AL30", "nombre": "AL30", "vencido": False, "dias_restantes": 30, "valor_actual_usd": 4500}]
        obs = salud_engine.generar_observaciones(**self._base_kwargs(vencimientos=venc))
        item = next(o for o in obs if o["id"] == "vencimiento_proximo")
        assert item["pantalla"] == "/flujo-caja"
        assert "4,500" in item["titulo"] or "4500" in item["titulo"]


class TestCalcularRatioComisionesCompartido:
    def test_mismo_resultado_que_diagnostico(self):
        """`calcular_ratio_comisiones` (usado por salud_engine) debe coincidir con el ratio que
        ya usaba `evaluar_comisiones` de Diagnóstico, para no mostrar números distintos."""
        comisiones = {"por_mes": [{"periodo": _mes_actual(), "total_usd": 200.0}]}
        hallazgo = evaluar_comisiones(comisiones, 10000.0)
        from app.services.diagnostico_engine import calcular_ratio_comisiones
        calculo = calcular_ratio_comisiones(comisiones, 10000.0)
        assert hallazgo is not None
        assert round(calculo["ratio"] * 100, 2) == hallazgo["dato_disparador"]["comision_pct_cartera"]


def _mes_actual() -> str:
    hoy = date.today()
    return f"{hoy.year:04d}-{hoy.month:02d}"
