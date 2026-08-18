"""Tests para el motor de simulación de escenarios."""
import pytest
from datetime import date
from app.services.escenario_engine import (
    PosicionSnapshot,
    PortfolioSnapshot,
    EscenarioParams,
    simular_escenario,
    resolver_preset,
    PRESETS,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def snapshot_simple():
    """Snapshot con una sola posición USD de $1000."""
    return PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[PosicionSnapshot(ticker="AAPL", valor_usd=1000.0, moneda="USD")],
        mep_actual=1000.0,
        valor_total_usd=1000.0,
        total_invertido_usd=1000.0,
    )


@pytest.fixture
def snapshot_con_ars():
    """Snapshot con una posición ARS de 100000 ARS = $100 USD (MEP=1000)."""
    return PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[PosicionSnapshot(ticker="GGAL", valor_usd=100.0, moneda="ARS")],
        mep_actual=1000.0,
        valor_total_usd=100.0,
        total_invertido_usd=100.0,
    )


@pytest.fixture
def snapshot_vacio():
    """Snapshot sin posiciones."""
    return PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[],
        mep_actual=1000.0,
        valor_total_usd=0.0,
        total_invertido_usd=0.0,
    )


# ─── Tests: Casos básicos ──────────────────────────────────────────────────

def test_simulacion_cero_porciento_sin_aportes(snapshot_simple):
    """Tasa 0%, sin aportes/dividendos → patrimonio_final == patrimonio_inicial."""
    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=0.0,
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    resultado = simular_escenario(snapshot_simple, params)

    assert resultado.patrimonio_inicial_usd == 1000.0
    assert abs(resultado.patrimonio_final_usd - 1000.0) < 0.01
    assert abs(resultado.ganancia_perdida_usd) < 0.01
    assert abs(resultado.rendimiento_pct) < 0.01


def test_simulacion_compounding_anual(snapshot_simple):
    """Tasa 12% anual, sin aportes/dividendos → verifica compounding.

    Valores esperados (calculados a mano):
    - Mes 0: $1000
    - Tasa mensual: (1 + 0.12/100)^(1/12) - 1 ≈ 0.009488793
    - Mes 1: $1000 * 1.009488793 ≈ $1009.49
    - Mes 12: $1000 * (1.009488793)^12 ≈ $1120.0 (sin comisión, compounding limpio)
    """
    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=12.0,
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    resultado = simular_escenario(snapshot_simple, params)

    # Compounding a 12% anual sobre $1000 por 1 año ≈ $1120
    assert abs(resultado.patrimonio_final_usd - 1120.0) < 2.0
    # Sin dólar ni dividendos, efecto_mercado ≈ ganancia_perdida
    assert abs(resultado.efecto_mercado_usd - resultado.ganancia_perdida_usd) < 0.01


def test_simulacion_aportes_mensales_no_son_rendimiento(snapshot_simple):
    """Aporte mensual $100, tasa 0%, 12 meses.

    Capital aportado debe ser $1000 + ($100*12) = $2200.
    Rendimiento debe ser 0% (no hay ganancia de mercado).
    """
    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=0.0,
        aporte_mensual_usd=100.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    resultado = simular_escenario(snapshot_simple, params)

    assert abs(resultado.capital_aportado_usd - 2200.0) < 0.01  # 1000 + 100*12
    assert abs(resultado.patrimonio_final_usd - 2200.0) < 0.01  # Sin ganancia
    assert abs(resultado.ganancia_perdida_usd) < 0.01
    assert abs(resultado.rendimiento_pct) < 0.01


def test_efecto_dolar_en_posicion_ars(snapshot_con_ars):
    """Posición ARS con 0% mercado, +20% dólar.

    Efecto dólar debe explicar toda la ganancia.
    """
    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=20.0,  # MEP sube 20%
        variacion_por_instrumento={},
        variacion_por_defecto_pct=0.0,  # Sin cambio de precio
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    resultado = simular_escenario(snapshot_con_ars, params)

    # MEP sube 20%: $100 USD * 1.20 ≈ $120 USD de ganancia
    ganancia_esperada = snapshot_con_ars.valor_total_usd * 0.20
    assert abs(resultado.ganancia_perdida_usd - ganancia_esperada) < 1.0
    # Efecto dólar debe ser casi toda la ganancia (0% de mercado)
    assert abs(resultado.efecto_dolar_usd - ganancia_esperada) < 1.0
    # Efecto mercado ≈ 0
    assert abs(resultado.efecto_mercado_usd) < 1.0


def test_dividendos_reinvertir_total_vs_retirar():
    """Con mismo yield, reinvertir_total > retirar (compounding)."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[PosicionSnapshot(ticker="TEST", valor_usd=1000.0, moneda="USD")],
        mep_actual=1000.0,
        valor_total_usd=1000.0,
        total_invertido_usd=1000.0,
    )

    params_base = {
        "horizonte_meses": 12,
        "variacion_dolar_pct": 0.0,
        "variacion_por_instrumento": {},
        "variacion_por_defecto_pct": 0.0,
        "aporte_mensual_usd": 0.0,
        "crecimiento_aporte_anual_pct": 0.0,
        "retiro_mensual_usd": 0.0,
        "dividend_yield_anual_pct": 2.0,
        "pct_dividendo_reinvertido": None,
        "comision_pct": 0.0,
        "inflacion_anual_pct": None,
    }

    resultado_reinvertir = simular_escenario(
        snapshot,
        EscenarioParams(**{**params_base, "modo_dividendos": "reinvertir_total"})
    )
    resultado_retirar = simular_escenario(
        snapshot,
        EscenarioParams(**{**params_base, "modo_dividendos": "retirar"})
    )

    # Reinvertir debe dar más patrimonio final (compounding)
    assert resultado_reinvertir.patrimonio_final_usd > resultado_retirar.patrimonio_final_usd


def test_guarda_contra_1_plus_i_negativo():
    """Tasa -99% no rompe (guarda contra 1+i <= 0)."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[PosicionSnapshot(ticker="TEST", valor_usd=1000.0, moneda="USD")],
        mep_actual=1000.0,
        valor_total_usd=1000.0,
        total_invertido_usd=1000.0,
    )

    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=-99.0,  # Tasa defensiva
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    # No debe lanzar excepción
    resultado = simular_escenario(snapshot, params)
    assert resultado.patrimonio_final_usd > 0


def test_cartera_vacia_con_aportes():
    """Cartera vacía con aportes mensuales crece sin dividir por cero."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[],
        mep_actual=1000.0,
        valor_total_usd=0.0,
        total_invertido_usd=0.0,
    )

    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=0.0,
        aporte_mensual_usd=100.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    # No debe lanzar excepción (sin dividir por cero)
    resultado = simular_escenario(snapshot, params)
    # Capital aportado = 100 * 12
    assert abs(resultado.capital_aportado_usd - 1200.0) < 0.01


# ─── Tests: Presets ───────────────────────────────────────────────────────

def test_resolver_preset_alcista():
    """Preset 'alcista' devuelve valores exactos."""
    resolved = resolver_preset("alcista")
    assert resolved["variacion_por_defecto_pct"] == 20.0
    assert resolved["variacion_dolar_pct"] == 5.0
    assert resolved["dividend_yield_anual_pct"] == 2.0


def test_resolver_preset_bajista():
    """Preset 'bajista' devuelve valores exactos."""
    resolved = resolver_preset("bajista")
    assert resolved["variacion_por_defecto_pct"] == -10.0
    assert resolved["variacion_dolar_pct"] == 10.0
    assert resolved["dividend_yield_anual_pct"] == 1.5


def test_resolver_preset_crisis():
    """Preset 'crisis' devuelve valores exactos."""
    resolved = resolver_preset("crisis")
    assert resolved["variacion_por_defecto_pct"] == -35.0
    assert resolved["variacion_dolar_pct"] == 60.0
    assert resolved["dividend_yield_anual_pct"] == 0.5


def test_resolver_preset_personalizado():
    """Preset 'personalizado' no filtra defaults."""
    custom = {"variacion_por_defecto_pct": 5.0}
    resolved = resolver_preset("personalizado", custom)
    assert resolved == custom


def test_resolver_preset_personalizado_vacio():
    """Preset 'personalizado' sin overrides devuelve dict vacío."""
    resolved = resolver_preset("personalizado")
    assert resolved == {}


# ─── Tests: Edge cases ────────────────────────────────────────────────────

def test_horizonte_cero_rechazado():
    """Horizonte 0 debe rechazarse."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[],
        mep_actual=None,
        valor_total_usd=0.0,
        total_invertido_usd=0.0,
    )

    params = EscenarioParams(
        horizonte_meses=0,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=0.0,
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    with pytest.raises(ValueError, match="horizonte_meses debe ser > 0"):
        simular_escenario(snapshot, params)


def test_horizonte_muy_largo_rechazado():
    """Horizonte > 1200 meses debe rechazarse."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[],
        mep_actual=None,
        valor_total_usd=0.0,
        total_invertido_usd=0.0,
    )

    params = EscenarioParams(
        horizonte_meses=1201,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=0.0,
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    with pytest.raises(ValueError, match="no puede superar"):
        simular_escenario(snapshot, params)


def test_inflacion_deflaciona_patriomonio_final():
    """Con inflación, patrimonio_final_real < patrimonio_final_usd."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[PosicionSnapshot(ticker="TEST", valor_usd=1000.0, moneda="USD")],
        mep_actual=1000.0,
        valor_total_usd=1000.0,
        total_invertido_usd=1000.0,
    )

    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=10.0,  # Ganancia nominal 10%
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=5.0,  # 5% anual
    )

    resultado = simular_escenario(snapshot, params)

    # patrimonio_final_real debe ser < patrimonio_final (deflacionado)
    assert resultado.patrimonio_final_real_usd is not None
    assert resultado.patrimonio_final_real_usd < resultado.patrimonio_final_usd


def test_override_por_ticker():
    """Override de variación por ticker se aplica."""
    snapshot = PortfolioSnapshot(
        fecha=date(2024, 1, 1),
        posiciones=[
            PosicionSnapshot(ticker="AAPL", valor_usd=500.0, moneda="USD"),
            PosicionSnapshot(ticker="MSFT", valor_usd=500.0, moneda="USD"),
        ],
        mep_actual=1000.0,
        valor_total_usd=1000.0,
        total_invertido_usd=1000.0,
    )

    params = EscenarioParams(
        horizonte_meses=12,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={"AAPL": 20.0},  # AAPL +20%
        variacion_por_defecto_pct=0.0,  # MSFT +0%
        aporte_mensual_usd=0.0,
        crecimiento_aporte_anual_pct=0.0,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,
    )

    resultado = simular_escenario(snapshot, params)

    # AAPL crece ~20%, MSFT sin cambio: patrimonio_final ≈ $500*1.2 + $500 = $1100
    assert abs(resultado.patrimonio_final_usd - 1100.0) < 2.0
