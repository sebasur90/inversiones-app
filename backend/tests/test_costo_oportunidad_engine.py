"""Tests para costo_oportunidad_engine.py (motor puro sin BD)."""
from datetime import date

import pytest

from app.services.opportunity_cost_engine import valor_shadow
from app.services.costo_oportunidad_engine import (
    ContextoComparacion,
    advertencias_homogeneidad,
    normalizar_serie,
    serie_valor_shadow,
)

D = date


class TestNormalizarSerie:
    def test_mep_a_usd_queda_plana(self):
        """El caso especial: seguir el propio Dólar (MEP) valuado en USD no rinde nada."""
        serie_mep = [(D(2026, 1, 1), 900.0), (D(2026, 2, 1), 1000.0), (D(2026, 3, 1), 1100.0)]
        # La serie nativa del benchmark "Dólar (MEP)" ES la serie de MEP, en ARS.
        serie_nativa = [(f, v, "ARS") for f, v in serie_mep]

        serie_norm, descartados = normalizar_serie(serie_nativa, "usd", serie_mep, [], None)

        assert descartados == 0
        niveles = [v for _, v in serie_norm]
        assert niveles == pytest.approx([1.0, 1.0, 1.0])

    def test_cer_a_ars_real_queda_plana(self):
        serie_cer = [(D(2026, 1, 1), 100.0), (D(2026, 2, 1), 110.0), (D(2026, 3, 1), 125.0)]
        serie_nativa = [(f, v, "ARS") for f, v in serie_cer]
        cer_hoy = 125.0

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_real", [], serie_cer, cer_hoy)

        assert descartados == 0
        niveles = [v for _, v in serie_norm]
        assert niveles == pytest.approx([cer_hoy, cer_hoy, cer_hoy])

    def test_ars_a_usd_divide_por_mep(self):
        serie_mep = [(D(2026, 1, 1), 1000.0)]
        serie_nativa = [(D(2026, 1, 1), 50000.0, "ARS")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "usd", serie_mep, [], None)

        assert descartados == 0
        assert serie_norm == [(D(2026, 1, 1), 50.0)]

    def test_usd_a_ars_nominal_multiplica_por_mep(self):
        serie_mep = [(D(2026, 1, 1), 1000.0)]
        serie_nativa = [(D(2026, 1, 1), 50.0, "USD")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_nominal", serie_mep, [], None)

        assert descartados == 0
        assert serie_norm == [(D(2026, 1, 1), 50000.0)]

    def test_ars_a_ars_real_usa_cer_hoy_sobre_cer_fecha(self):
        """Convención del proyecto: inflar a pesos de hoy (`* cer_hoy / cer_fecha`), no dividir."""
        serie_cer = [(D(2026, 1, 1), 100.0)]
        serie_nativa = [(D(2026, 1, 1), 1000.0, "ARS")]
        cer_hoy = 150.0

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_real", [], serie_cer, cer_hoy)

        assert descartados == 0
        # 1000 * (150/100) = 1500, NUNCA 1000/100 = 10.
        assert serie_norm == [(D(2026, 1, 1), 1500.0)]

    def test_destino_igual_a_nativa_es_identidad(self):
        serie_nativa = [(D(2026, 1, 1), 100.0, "USD"), (D(2026, 2, 1), 110.0, "USD")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "usd", [], [], None)

        assert descartados == 0
        assert serie_norm == [(D(2026, 1, 1), 100.0), (D(2026, 2, 1), 110.0)]

    def test_usa_carry_forward_de_mep(self):
        serie_mep = [(D(2026, 1, 1), 1000.0)]  # sin dato en marzo: se arrastra el de enero
        serie_nativa = [(D(2026, 3, 15), 50.0, "USD")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_nominal", serie_mep, [], None)

        assert descartados == 0
        assert serie_norm == [(D(2026, 3, 15), 50000.0)]

    def test_descarta_punto_sin_mep_anterior_y_cuenta(self):
        serie_mep = [(D(2026, 6, 1), 1000.0)]  # nada antes de junio
        serie_nativa = [(D(2026, 1, 1), 50.0, "USD"), (D(2026, 6, 1), 50.0, "USD")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_nominal", serie_mep, [], None)

        assert descartados == 1
        assert serie_norm == [(D(2026, 6, 1), 50000.0)]

    def test_descarta_nivel_o_factor_cero(self):
        serie_mep = [(D(2026, 1, 1), 0.0)]
        serie_nativa = [(D(2026, 1, 1), 50.0, "USD")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_nominal", serie_mep, [], None)

        assert descartados == 1
        assert serie_norm == []

    def test_serie_con_monedas_mezcladas_convierte_cada_punto_con_la_suya(self):
        serie_mep = [(D(2026, 1, 1), 1000.0), (D(2026, 2, 1), 1100.0)]
        serie_nativa = [
            (D(2026, 1, 1), 100.0, "ARS"),
            (D(2026, 2, 1), 50.0, "USD"),
        ]

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_nominal", serie_mep, [], None)

        assert descartados == 0
        assert serie_norm == [(D(2026, 1, 1), 100.0), (D(2026, 2, 1), 55000.0)]

    def test_ars_real_sin_cer_hoy_descarta_todo(self):
        serie_nativa = [(D(2026, 1, 1), 100.0, "ARS"), (D(2026, 2, 1), 110.0, "ARS")]

        serie_norm, descartados = normalizar_serie(serie_nativa, "ars_real", [], [(D(2026, 1, 1), 100.0)], None)

        assert serie_norm == []
        assert descartados == 2

    def test_moneda_destino_invalida_lanza(self):
        with pytest.raises(ValueError):
            normalizar_serie([], "eur", [], [], None)


class TestSerieValorShadow:
    @pytest.mark.parametrize("hasta", [
        D(2026, 1, 20), D(2026, 2, 15), D(2026, 3, 1), D(2026, 4, 10), D(2026, 5, 31),
    ])
    def test_coincide_con_valor_shadow(self, hasta):
        """Consistencia algebraica con el motor ya existente, punto a punto."""
        serie = [
            (D(2026, 1, 1), 100.0),
            (D(2026, 2, 1), 110.0),
            (D(2026, 3, 1), 105.0),
            (D(2026, 4, 1), 130.0),
            (D(2026, 5, 1), 140.0),
        ]
        flujos = [
            (D(2026, 1, 10), -1000.0),
            (D(2026, 2, 20), -500.0),
            (D(2026, 3, 5), 300.0),
            (D(2026, 4, 15), -200.0),
        ]

        fechas = [D(2026, 1, 20), D(2026, 2, 15), D(2026, 3, 1), D(2026, 4, 10), D(2026, 5, 31)]
        resultado = serie_valor_shadow(flujos, serie, fechas)

        flujos_hasta = [(f, m) for f, m in flujos if f <= hasta]
        esperado = valor_shadow(flujos_hasta, serie, hasta) if flujos_hasta else 0.0

        idx = fechas.index(hasta)
        assert resultado[idx] == pytest.approx(esperado, rel=1e-9)

    def test_flujo_anterior_a_la_serie_da_none_desde_ese_punto(self):
        serie = [(D(2026, 2, 1), 100.0), (D(2026, 3, 1), 110.0)]
        flujos = [(D(2026, 1, 1), -1000.0)]  # anterior al primer dato de la serie
        fechas = [D(2026, 1, 15), D(2026, 2, 15), D(2026, 3, 15)]

        resultado = serie_valor_shadow(flujos, serie, fechas)

        # Antes de que ocurra el flujo (2026-01-01 <= 2026-01-15 ya ocurrió) -> dañado desde ya
        assert resultado == [None, None, None]

    def test_sin_flujos_da_ceros(self):
        serie = [(D(2026, 1, 1), 100.0)]
        fechas = [D(2026, 1, 15), D(2026, 2, 15)]

        resultado = serie_valor_shadow([], serie, fechas)

        assert resultado == [0.0, 0.0]

    def test_sin_serie_da_ceros(self):
        flujos = [(D(2026, 1, 1), -1000.0)]
        fechas = [D(2026, 1, 15)]

        resultado = serie_valor_shadow(flujos, [], fechas)

        assert resultado == [0.0]

    def test_antes_del_primer_flujo_es_cero(self):
        serie = [(D(2026, 1, 1), 100.0), (D(2026, 3, 1), 120.0)]
        flujos = [(D(2026, 2, 1), -1000.0)]
        fechas = [D(2026, 1, 15), D(2026, 2, 15)]

        resultado = serie_valor_shadow(flujos, serie, fechas)

        assert resultado[0] == 0.0  # el flujo todavía no ocurrió
        assert resultado[1] is not None

    def test_un_solo_flujo_reproduce_el_ratio_de_niveles(self):
        serie = [(D(2026, 1, 1), 100.0), (D(2026, 6, 1), 150.0)]
        flujos = [(D(2026, 1, 1), -1000.0)]
        fechas = [D(2026, 6, 1)]

        resultado = serie_valor_shadow(flujos, serie, fechas)

        assert resultado[0] == pytest.approx(1000.0 * (150.0 / 100.0))

    def test_venta_resta_unidades_acumuladas(self):
        serie = [(D(2026, 1, 1), 100.0), (D(2026, 2, 1), 100.0), (D(2026, 3, 1), 100.0)]
        flujos = [
            (D(2026, 1, 1), -1000.0),   # +10 unidades
            (D(2026, 2, 1), 500.0),     # -5 unidades (venta)
        ]
        fechas = [D(2026, 3, 1)]

        resultado = serie_valor_shadow(flujos, serie, fechas)

        # Quedan 5 unidades a nivel 100 = 500
        assert resultado[0] == pytest.approx(500.0)

    def test_fecha_anterior_al_primer_dato_de_la_serie_es_none(self):
        serie = [(D(2026, 3, 1), 100.0)]
        flujos = [(D(2026, 3, 1), -1000.0)]
        fechas = [D(2026, 1, 1)]  # antes de cualquier dato Y antes de que exista el flujo

        resultado = serie_valor_shadow(flujos, serie, fechas)

        assert resultado == [0.0]  # el flujo (2026-03-01) todavía no ocurrió en 2026-01-01


class TestAdvertenciasHomogeneidad:
    def _ctx(self, **overrides):
        base = dict(
            moneda_destino="usd",
            moneda_nativa_referencia="USD",
            referencia="S&P 500",
            periodo_pedido_desde=None,
            periodo_efectivo_desde=None,
            periodo_hasta=D(2026, 6, 30),
            n_meses=12,
            n_puntos_referencia=250,
            dias_entre_puntos_referencia=1.0,
            puntos_fx_descartados=0,
            meses_sin_tenencia=0,
            valuacion_aproximada=False,
            precio_faltante=False,
        )
        base.update(overrides)
        return ContextoComparacion(**base)

    def test_sin_advertencias_cuando_todo_es_homogeneo(self):
        assert advertencias_homogeneidad(self._ctx()) == []

    def test_periodo_recortado(self):
        ctx = self._ctx(periodo_pedido_desde=D(2020, 1, 1), periodo_efectivo_desde=D(2023, 5, 31))
        adv = advertencias_homogeneidad(ctx)
        assert any("2020-01-01" in a and "2023-05-31" in a for a in adv)

    def test_pocos_meses(self):
        ctx = self._ctx(n_meses=2)
        adv = advertencias_homogeneidad(ctx)
        assert any("menos de 3 meses" in a for a in adv)

    def test_moneda_convertida_usd_a_ars(self):
        ctx = self._ctx(moneda_destino="ars_nominal", moneda_nativa_referencia="USD")
        adv = advertencias_homogeneidad(ctx)
        assert any("dólar MEP" in a for a in adv)

    def test_moneda_convertida_ars_a_usd(self):
        ctx = self._ctx(moneda_destino="usd", moneda_nativa_referencia="ARS")
        adv = advertencias_homogeneidad(ctx)
        assert any("dólar MEP" in a for a in adv)

    def test_moneda_mixta(self):
        ctx = self._ctx(moneda_nativa_referencia="mixta")
        adv = advertencias_homogeneidad(ctx)
        assert any("pesos y puntos cargados en dólares" in a for a in adv)

    def test_ars_real_siempre_advierte(self):
        ctx = self._ctx(moneda_destino="ars_real", moneda_nativa_referencia="ARS")
        adv = advertencias_homogeneidad(ctx)
        assert any("CER" in a for a in adv)

    def test_frecuencia_baja_densidad(self):
        ctx = self._ctx(dias_entre_puntos_referencia=30.0, n_puntos_referencia=12)
        adv = advertencias_homogeneidad(ctx)
        assert any("uno cada" in a for a in adv)

    def test_fx_descartado(self):
        ctx = self._ctx(puntos_fx_descartados=3)
        adv = advertencias_homogeneidad(ctx)
        assert any("3 puntos" in a for a in adv)

    def test_meses_sin_tenencia(self):
        ctx = self._ctx(meses_sin_tenencia=2, n_meses=12)
        adv = advertencias_homogeneidad(ctx)
        assert any("2 de los 12" in a for a in adv)

    def test_valuacion_aproximada(self):
        ctx = self._ctx(valuacion_aproximada=True)
        adv = advertencias_homogeneidad(ctx)
        assert any("último precio conocido" in a for a in adv)

    def test_precio_faltante(self):
        ctx = self._ctx(precio_faltante=True)
        adv = advertencias_homogeneidad(ctx)
        assert any("sin precio ni costo conocido" in a for a in adv)
