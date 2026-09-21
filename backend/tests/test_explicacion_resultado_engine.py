"""Tests para el motor puro de "¿por qué ganó o perdió mi cartera?"
(backend/app/services/explicacion_resultado_engine.py)."""
import pytest

from app.services import explicacion_resultado_engine as engine


class TestDescomponerTicker:
    def test_identidad_precio_mas_ingresos_menos_comisiones_igual_pnl(self):
        """pnl = precio + dividendos + cupones - comisiones, siempre que exacto."""
        item = engine.descomponer_ticker(
            "AAPL", v0=1000.0, v1=1250.0,
            compras_bruto=0.0, compras_neto=0.0,
            ventas_bruto=0.0, ventas_neto=0.0,
            amortizaciones_bruto=0.0, amortizaciones_neto=0.0,
            dividendos=20.0, cupones=0.0, comisiones=5.0,
        )
        assert item["precio"] == pytest.approx(250.0)
        assert item["comisiones"] == pytest.approx(-5.0)
        assert item["pnl"] == pytest.approx(item["precio"] + item["dividendos"] + item["cupones"] + item["comisiones"])
        assert item["pnl"] == pytest.approx(265.0)
        assert item["disponible"] is True

    def test_compra_pura_sin_variacion_de_precio_da_pnl_cero(self):
        """Comprar y no moverse: el aporte no es ganancia. V1 == V0 + compra_bruto."""
        item = engine.descomponer_ticker(
            "AL30", v0=0.0, v1=1000.0,
            compras_bruto=1000.0, compras_neto=1010.0,  # con $10 de comisión
            ventas_bruto=0.0, ventas_neto=0.0,
            amortizaciones_bruto=0.0, amortizaciones_neto=0.0,
            dividendos=0.0, cupones=0.0, comisiones=10.0,
        )
        assert item["precio"] == pytest.approx(0.0)
        assert item["pnl"] == pytest.approx(-10.0)  # sólo la comisión, ninguna ganancia inventada
        assert item["aportes"] == pytest.approx(1010.0)

    def test_venta_a_precio_de_mercado_no_genera_pnl(self):
        """Vender toda la posición a su valor de mercado: el retiro no es pérdida."""
        item = engine.descomponer_ticker(
            "GGAL", v0=500.0, v1=0.0,
            compras_bruto=0.0, compras_neto=0.0,
            ventas_bruto=500.0, ventas_neto=495.0,  # con $5 de comisión
            amortizaciones_bruto=0.0, amortizaciones_neto=0.0,
            dividendos=0.0, cupones=0.0, comisiones=5.0,
        )
        assert item["precio"] == pytest.approx(0.0)
        assert item["pnl"] == pytest.approx(-5.0)
        assert item["retiros"] == pytest.approx(495.0)

    def test_amortizacion_es_capital_devuelto_no_ganancia(self):
        """Una amortización íntegra a la par no genera 'ganancia': va a `amortizaciones`."""
        item = engine.descomponer_ticker(
            "AL30", v0=1000.0, v1=0.0,
            compras_bruto=0.0, compras_neto=0.0,
            ventas_bruto=0.0, ventas_neto=0.0,
            amortizaciones_bruto=1000.0, amortizaciones_neto=1000.0,
            dividendos=0.0, cupones=0.0, comisiones=0.0,
        )
        assert item["precio"] == pytest.approx(0.0)
        assert item["pnl"] == pytest.approx(0.0)
        assert item["amortizaciones"] == pytest.approx(1000.0)

    def test_dividendo_no_afecta_precio(self):
        item = engine.descomponer_ticker(
            "KO", v0=100.0, v1=100.0,
            compras_bruto=0.0, compras_neto=0.0,
            ventas_bruto=0.0, ventas_neto=0.0,
            amortizaciones_bruto=0.0, amortizaciones_neto=0.0,
            dividendos=8.0, cupones=0.0, comisiones=0.0,
        )
        assert item["precio"] == pytest.approx(0.0)
        assert item["pnl"] == pytest.approx(8.0)

    def test_perdida_de_precio(self):
        item = engine.descomponer_ticker(
            "YPFD", v0=1000.0, v1=800.0,
            compras_bruto=0.0, compras_neto=0.0,
            ventas_bruto=0.0, ventas_neto=0.0,
            amortizaciones_bruto=0.0, amortizaciones_neto=0.0,
            dividendos=0.0, cupones=0.0, comisiones=0.0,
        )
        assert item["precio"] == pytest.approx(-200.0)
        assert item["pnl"] == pytest.approx(-200.0)
        assert item["disponible"] is True

    def test_v0_faltante_marca_no_disponible_pero_conserva_aportes(self):
        """Sin precio inicial no se puede calcular `precio`/`pnl`, pero si el flujo de caja sí
        se pudo convertir, los aportes no se pierden (no todo o nada)."""
        item = engine.descomponer_ticker(
            "SINPRECIO", v0=None, v1=500.0,
            compras_bruto=400.0, compras_neto=410.0,
            ventas_bruto=0.0, ventas_neto=0.0,
            amortizaciones_bruto=0.0, amortizaciones_neto=0.0,
            dividendos=0.0, cupones=0.0, comisiones=10.0,
        )
        assert item["precio"] is None
        assert item["pnl"] is None
        assert item["disponible"] is False
        assert item["aportes"] == pytest.approx(410.0)

    def test_flujos_faltantes_no_inventan_cero(self):
        """Sin poder convertir los movimientos del período (falta MEP), todo queda None."""
        item = engine.descomponer_ticker(
            "AL30", v0=1000.0, v1=1100.0,
            compras_bruto=None, compras_neto=None,
            ventas_bruto=None, ventas_neto=None,
            amortizaciones_bruto=None, amortizaciones_neto=None,
            dividendos=None, cupones=None, comisiones=None,
        )
        assert item["precio"] is None
        assert item["pnl"] is None
        assert item["aportes"] is None
        assert item["disponible"] is False


class TestAgruparPorEtiqueta:
    def test_suma_por_etiqueta_ignorando_no_disponibles(self):
        disponible = engine.descomponer_ticker(
            "AAPL", 100.0, 150.0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0,
        )
        no_disponible = engine.descomponer_ticker(
            "MSFT", None, None, None, None, None, None, None, None, None, None, None,
        )
        grupos = engine.agrupar_por_etiqueta([("Acciones", disponible), ("Acciones", no_disponible)])
        assert len(grupos) == 1
        assert grupos[0]["etiqueta"] == "Acciones"
        assert grupos[0]["pnl"] == pytest.approx(50.0)
        assert grupos[0]["n_no_disponibles"] == 1

    def test_grupos_separados_por_etiqueta_distinta(self):
        a = engine.descomponer_ticker("AAPL", 100.0, 120.0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)
        b = engine.descomponer_ticker("AL30", 200.0, 190.0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)
        grupos = {g["etiqueta"]: g for g in engine.agrupar_por_etiqueta([("Acciones", a), ("Bonos", b)])}
        assert grupos["Acciones"]["pnl"] == pytest.approx(20.0)
        assert grupos["Bonos"]["pnl"] == pytest.approx(-10.0)


class TestConContribucion:
    def test_contribucion_pct_mismo_denominador(self):
        items = [
            engine.descomponer_ticker("A", 0, 60, 100, 100, 0, 0, 0, 0, 0.0, 0.0, 0.0),
            engine.descomponer_ticker("B", 0, -40, 100, 100, 0, 0, 0, 0, 0.0, 0.0, 0.0),
        ]
        con_contrib = engine.con_contribucion(items, base=200.0)
        # A: pnl = 60-100 = -40 -> -20%; B: pnl = -40-100 = -140 -> -70%
        by_ticker = {it["ticker"]: it for it in con_contrib}
        assert by_ticker["A"]["contribucion_pct"] == pytest.approx(-20.0)
        assert by_ticker["B"]["contribucion_pct"] == pytest.approx(-70.0)

    def test_base_cero_da_none(self):
        items = [engine.descomponer_ticker("A", 0, 10, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)]
        con_contrib = engine.con_contribucion(items, base=0.0)
        assert con_contrib[0]["contribucion_pct"] is None

    def test_pnl_none_da_contribucion_none(self):
        items = [engine.descomponer_ticker("A", None, None, None, None, None, None, None, None, None, None, None)]
        con_contrib = engine.con_contribucion(items, base=100.0)
        assert con_contrib[0]["contribucion_pct"] is None


class TestRanking:
    def _item(self, ticker, pnl):
        v0 = 100.0
        v1 = v0 + pnl
        return engine.descomponer_ticker(ticker, v0, v1, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)

    def test_contribuyentes_ordenados_descendente(self):
        items = [self._item("A", 50), self._item("B", 200), self._item("C", -30), self._item("D", 10)]
        top = engine.ranking(items, n=5, positivos=True)
        assert [it["ticker"] for it in top] == ["B", "A", "D"]

    def test_detractores_ordenados_por_perdida_mayor_primero(self):
        items = [self._item("A", 50), self._item("B", -200), self._item("C", -30)]
        peores = engine.ranking(items, n=5, positivos=False)
        assert [it["ticker"] for it in peores] == ["B", "C"]

    def test_no_disponibles_nunca_entran_al_ranking(self):
        disponible = self._item("A", 50)
        no_disponible = engine.descomponer_ticker("B", None, None, None, None, None, None, None, None, None, None, None)
        top = engine.ranking([disponible, no_disponible], n=5, positivos=True)
        assert [it["ticker"] for it in top] == ["A"]

    def test_respeta_el_limite_n(self):
        items = [self._item(f"T{i}", 10 + i) for i in range(10)]
        top = engine.ranking(items, n=3, positivos=True)
        assert len(top) == 3


class TestDescomponerFxPeriodo:
    def test_identidad_exacta(self):
        resultado = engine.descomponer_fx_periodo(pnl_ars=15000.0, pnl_usd=10.0, mep_hoy=1000.0)
        assert resultado["estado"] == "ok"
        assert resultado["resultado_activos_ars"] == pytest.approx(10000.0)
        assert resultado["efecto_mep_ars"] == pytest.approx(5000.0)

    def test_sin_mep_no_disponible(self):
        resultado = engine.descomponer_fx_periodo(pnl_ars=100.0, pnl_usd=1.0, mep_hoy=None)
        assert resultado["estado"] == "no_disponible"
        assert resultado["efecto_mep_ars"] is None


class TestExplicar:
    def test_frases_con_todos_los_componentes(self):
        resultado = engine.explicar(
            pnl_total=820.0, precio_total=610.0, dividendos_total=150.0,
            cupones_total=30.0, comisiones_total=-30.0, moneda="usd",
        )
        assert "USD 820" in resultado["titulo"]
        assert any("610" in f for f in resultado["frases"])
        assert any("180" in f for f in resultado["frases"])  # dividendos + cupones
        assert any("30" in f for f in resultado["frases"])  # comisiones

    def test_sin_datos_no_inventa_numeros(self):
        resultado = engine.explicar(None, None, None, None, None, "usd")
        assert resultado["frases"] == []
        assert "no se pudo" in resultado["titulo"].lower()

    def test_perdida_usa_verbo_bajo(self):
        resultado = engine.explicar(-500.0, -500.0, 0.0, 0.0, 0.0, "ars")
        assert "bajó" in resultado["titulo"]
