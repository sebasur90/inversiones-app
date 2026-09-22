"""Tests para el motor de 'Escenarios de vida' (capa sencilla del simulador).

Convención: fecha fija (no date.today()), helpers privados para armar casos.
Modelo cerrado contra el que se testea (posiciones=[], yield 0, comisión 0):

    V_n = V_(n-1) * (1+i) + A_n         con i = (1+r)^(1/12) - 1, V_0 = P

El aporte entra DESPUÉS del crecimiento del mes ⇒ anualidad ORDINARIA:

    V_N = P*(1+r)^(N/12) + A * ((1+i)^N - 1) / i
"""
import math
import pytest
from datetime import date

from app.services.vida_engine import (
    SupuestosVida,
    EscenarioVidaSpec,
    simular_vida,
    validar,
    _fecha_mes,
    _deflactar,
    TIPOS_VIDA,
)

HOY = date(2026, 9, 22)


def _resultado(supuestos: SupuestosVida, spec: EscenarioVidaSpec):
    """Simula un único escenario y devuelve su ResultadoVida (último de la lista:
    la base si spec ya es 'continuar_igual', o el escenario pedido si no)."""
    comparacion = simular_vida(supuestos, [spec], hoy=HOY)
    return comparacion.resultados[-1]


def _base(supuestos: SupuestosVida):
    comparacion = simular_vida(supuestos, [EscenarioVidaSpec(tipo="continuar_igual")], hoy=HOY)
    return comparacion.resultados[0]


# ─── Casos básicos: interés compuesto y anualidad ──────────────────────────

def test_continuar_igual_sin_crecimiento_es_suma_lineal():
    """r=0: sin crecimiento, el patrimonio final es sólo suma de aportes."""
    supuestos = SupuestosVida(
        patrimonio_inicial=10000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=0.0, horizonte_meses=12,
    )
    res = _base(supuestos)
    assert res.metricas.patrimonio_final == pytest.approx(11200.0, abs=1e-6)
    assert res.metricas.aportes_periodo == pytest.approx(1200.0, abs=1e-6)
    assert res.metricas.crecimiento_estimado == pytest.approx(0.0, abs=1e-6)


def test_compuesto_puro_sin_aportes():
    """Sin aportes, el patrimonio compone a la tasa anual exacta."""
    supuestos_12 = SupuestosVida(
        patrimonio_inicial=10000.0, aporte_mensual=0.0,
        crecimiento_anual_pct=10.0, horizonte_meses=12,
    )
    assert _base(supuestos_12).metricas.patrimonio_final == pytest.approx(11000.0, rel=1e-9)

    supuestos_24 = SupuestosVida(
        patrimonio_inicial=10000.0, aporte_mensual=0.0,
        crecimiento_anual_pct=10.0, horizonte_meses=24,
    )
    assert _base(supuestos_24).metricas.patrimonio_final == pytest.approx(12100.0, rel=1e-9)


def test_anualidad_ordinaria():
    """P=0: el patrimonio final es la fórmula cerrada de anualidad ordinaria."""
    supuestos = SupuestosVida(
        patrimonio_inicial=0.0, aporte_mensual=100.0,
        crecimiento_anual_pct=12.0, horizonte_meses=12,
    )
    i = math.pow(1.12, 1 / 12) - 1
    esperado = 100.0 * (math.pow(1 + i, 12) - 1) / i

    res = _base(supuestos)
    assert res.metricas.patrimonio_final == pytest.approx(esperado, rel=1e-9)


# ─── Aumentar / disminuir aporte ───────────────────────────────────────────

def test_aumentar_por_pct_y_por_monto_coinciden():
    supuestos = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=5.0, horizonte_meses=12,
    )
    por_monto = _resultado(supuestos, EscenarioVidaSpec(tipo="aumentar_aporte", monto=150.0))
    por_pct = _resultado(supuestos, EscenarioVidaSpec(tipo="aumentar_aporte", pct=50.0))

    assert por_monto.aporte_mensual_efectivo == pytest.approx(150.0, abs=1e-9)
    assert por_pct.aporte_mensual_efectivo == pytest.approx(150.0, abs=1e-9)
    assert por_monto.metricas.patrimonio_final == pytest.approx(por_pct.metricas.patrimonio_final, rel=1e-9)


def test_orden_de_escenarios():
    """Con crecimiento positivo: dejar < disminuir < continuar < aumentar."""
    supuestos = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=5.0, horizonte_meses=24,
    )
    dejar = _resultado(supuestos, EscenarioVidaSpec(tipo="dejar_de_aportar"))
    disminuir = _resultado(supuestos, EscenarioVidaSpec(tipo="disminuir_aporte", monto=50.0))
    continuar = _base(supuestos)
    aumentar = _resultado(supuestos, EscenarioVidaSpec(tipo="aumentar_aporte", monto=150.0))

    finales = [dejar.metricas.patrimonio_final, disminuir.metricas.patrimonio_final,
               continuar.metricas.patrimonio_final, aumentar.metricas.patrimonio_final]
    assert finales == sorted(finales)
    assert finales[0] < finales[1] < finales[2] < finales[3]


def test_dejar_de_aportar_es_compuesto_puro():
    supuestos = SupuestosVida(
        patrimonio_inicial=5000.0, aporte_mensual=200.0,
        crecimiento_anual_pct=7.0, horizonte_meses=36,
    )
    res = _resultado(supuestos, EscenarioVidaSpec(tipo="dejar_de_aportar"))

    esperado = 5000.0 * math.pow(1.07, 36 / 12)
    assert res.metricas.patrimonio_final == pytest.approx(esperado, rel=1e-9)
    assert res.metricas.aportes_periodo == pytest.approx(0.0, abs=1e-6)
    assert res.aporte_mensual_efectivo == 0.0


# ─── Extraordinarios ────────────────────────────────────────────────────────

def test_aporte_extraordinario_mes_final_vs_mes_1():
    supuestos = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=50.0,
        crecimiento_anual_pct=6.0, horizonte_meses=12,
    )
    base_final = _base(supuestos).metricas.patrimonio_final
    X = 500.0

    en_ultimo_mes = _resultado(
        supuestos, EscenarioVidaSpec(tipo="aporte_extraordinario", monto=X, mes=12)
    )
    en_primer_mes = _resultado(
        supuestos, EscenarioVidaSpec(tipo="aporte_extraordinario", monto=X, mes=1)
    )

    # Agregado en el último mes: no le queda tiempo para crecer.
    assert en_ultimo_mes.metricas.patrimonio_final == pytest.approx(base_final + X, rel=1e-9)

    # Agregado en el mes 1: compone (N-1) meses adicionales junto al resto de la cartera.
    i = math.pow(1.06, 1 / 12) - 1
    esperado_primer_mes = base_final + X * math.pow(1 + i, 11)
    assert en_primer_mes.metricas.patrimonio_final == pytest.approx(esperado_primer_mes, rel=1e-9)


def test_retiro_extraordinario_resta_capitalizado():
    supuestos = SupuestosVida(
        patrimonio_inicial=5000.0, aporte_mensual=50.0,
        crecimiento_anual_pct=6.0, horizonte_meses=12,
    )
    base = _base(supuestos)
    X = 300.0

    en_ultimo_mes = _resultado(
        supuestos, EscenarioVidaSpec(tipo="retiro_extraordinario", monto=X, mes=12)
    )
    assert en_ultimo_mes.metricas.patrimonio_final == pytest.approx(
        base.metricas.patrimonio_final - X, rel=1e-9
    )
    assert en_ultimo_mes.metricas.aportes_periodo == pytest.approx(
        base.metricas.aportes_periodo - X, abs=1e-6
    )
    assert en_ultimo_mes.metricas.diferencia_vs_base == pytest.approx(-X, rel=1e-9)


def test_retiro_mayor_al_patrimonio_clampea_y_advierte():
    supuestos = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=0.0,
        crecimiento_anual_pct=0.0, horizonte_meses=2,
    )
    res = _resultado(
        supuestos, EscenarioVidaSpec(tipo="retiro_extraordinario", monto=100000.0, mes=1)
    )

    punto_mes_1 = next(p for p in res.puntos if p.mes == 1)
    assert punto_mes_1.valor == 0.0
    assert punto_mes_1.valor >= 0.0
    assert len(res.advertencias) >= 1
    assert "no alcanzaban los fondos" in res.advertencias[0]
    assert res.se_agota_en_mes == 1


def test_aumentar_aportes_anualmente_escalones_de_12_meses():
    supuestos = SupuestosVida(
        patrimonio_inicial=0.0, aporte_mensual=100.0,
        crecimiento_anual_pct=0.0, horizonte_meses=24,
    )
    res = _resultado(supuestos, EscenarioVidaSpec(tipo="aumentar_aportes_anualmente", pct=100.0))

    assert res.metricas.aportes_periodo == pytest.approx(12 * 100.0 + 12 * 200.0, abs=1e-6)

    puntos_por_mes = {p.mes: p for p in res.puntos}
    incremento_mes_2 = puntos_por_mes[2].aportado_acum - puntos_por_mes[1].aportado_acum
    incremento_mes_13 = puntos_por_mes[13].aportado_acum - puntos_por_mes[12].aportado_acum
    assert incremento_mes_2 == pytest.approx(100.0, abs=1e-6)  # sin aumento todavía
    assert incremento_mes_13 == pytest.approx(200.0, abs=1e-6)  # primer aumento, recién acá


# ─── Identidad final = inicial + aportes + crecimiento ─────────────────────

@pytest.mark.parametrize("spec", [
    EscenarioVidaSpec(tipo="continuar_igual"),
    EscenarioVidaSpec(tipo="aumentar_aporte", monto=150.0),
    EscenarioVidaSpec(tipo="disminuir_aporte", monto=50.0),
    EscenarioVidaSpec(tipo="dejar_de_aportar"),
    EscenarioVidaSpec(tipo="aporte_extraordinario", monto=500.0, mes=6),
    EscenarioVidaSpec(tipo="retiro_extraordinario", monto=200.0, mes=6),
    EscenarioVidaSpec(tipo="aumentar_aportes_anualmente", pct=10.0),
])
def test_identidad_final_igual_inicial_mas_aportes_mas_crecimiento(spec):
    supuestos = SupuestosVida(
        patrimonio_inicial=5000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=8.0, horizonte_meses=24,
    )
    res = _resultado(supuestos, spec)
    m = res.metricas
    assert m.patrimonio_final == pytest.approx(
        supuestos.patrimonio_inicial + m.aportes_periodo + m.crecimiento_estimado, rel=1e-9
    )


def test_diferencia_vs_base_es_cero_en_la_base():
    supuestos = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=5.0, horizonte_meses=12,
    )
    comparacion = simular_vida(
        supuestos,
        [EscenarioVidaSpec(tipo="continuar_igual"), EscenarioVidaSpec(tipo="aumentar_aporte", monto=150.0)],
        hoy=HOY,
    )
    base, aumentado = comparacion.resultados
    assert base.es_base is True
    assert base.metricas.diferencia_vs_base == 0.0
    assert aumentado.metricas.diferencia_vs_base == pytest.approx(
        aumentado.metricas.patrimonio_final - base.metricas.patrimonio_final, rel=1e-9
    )


# ─── Inflación ──────────────────────────────────────────────────────────────

def test_deflactar_serie():
    supuestos = SupuestosVida(
        patrimonio_inicial=10000.0, aporte_mensual=0.0,
        crecimiento_anual_pct=0.0, horizonte_meses=12, inflacion_anual_pct=10.0,
    )
    res = _base(supuestos)
    puntos_por_mes = {p.mes: p for p in res.puntos}

    assert puntos_por_mes[0].valor_real == pytest.approx(10000.0, rel=1e-9)
    assert puntos_por_mes[12].valor_real == pytest.approx(puntos_por_mes[12].valor / 1.1, rel=1e-9)
    assert res.metricas.patrimonio_final_real == pytest.approx(puntos_por_mes[12].valor_real, rel=1e-9)


def test_sin_inflacion_valor_real_es_none():
    supuestos = SupuestosVida(
        patrimonio_inicial=10000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=5.0, horizonte_meses=12,
    )
    res = _base(supuestos)
    assert all(p.valor_real is None for p in res.puntos)
    assert res.metricas.patrimonio_final_real is None


# ─── Fechas y moneda ────────────────────────────────────────────────────────

def test_fechas_por_calendario_no_meses_de_30_dias():
    assert _fecha_mes(date(2024, 1, 15), 0) == date(2024, 1, 15)
    assert _fecha_mes(date(2024, 1, 15), 120) == date(2034, 1, 15)


def test_moneda_es_solo_etiqueta():
    supuestos_usd = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=6.0, horizonte_meses=12, moneda="USD",
    )
    supuestos_ars = SupuestosVida(
        patrimonio_inicial=1000.0, aporte_mensual=100.0,
        crecimiento_anual_pct=6.0, horizonte_meses=12, moneda="ARS",
    )
    final_usd = _base(supuestos_usd).metricas.patrimonio_final
    final_ars = _base(supuestos_ars).metricas.patrimonio_final
    assert final_usd == pytest.approx(final_ars, rel=1e-12)


# ─── Casos borde ────────────────────────────────────────────────────────────

def test_patrimonio_inicial_cero():
    supuestos = SupuestosVida(
        patrimonio_inicial=0.0, aporte_mensual=0.0,
        crecimiento_anual_pct=5.0, horizonte_meses=12,
    )
    res = _base(supuestos)
    assert res.metricas.patrimonio_final == pytest.approx(0.0, abs=1e-9)
    assert res.metricas.diferencia_vs_base_pct is None


def test_deflactar_helper_devuelve_none_sin_inflacion():
    assert _deflactar(1000.0, 12, None) is None
    assert _deflactar(1000.0, 12, 0.0) is None


def test_validar_tipo_desconocido():
    supuestos = SupuestosVida(patrimonio_inicial=1000.0, aporte_mensual=0.0,
                               crecimiento_anual_pct=0.0, horizonte_meses=12)
    with pytest.raises(ValueError):
        validar(supuestos, [EscenarioVidaSpec(tipo="no_existe")])


def test_validar_mes_mayor_al_horizonte():
    supuestos = SupuestosVida(patrimonio_inicial=1000.0, aporte_mensual=0.0,
                               crecimiento_anual_pct=0.0, horizonte_meses=12)
    with pytest.raises(ValueError):
        validar(supuestos, [EscenarioVidaSpec(tipo="aporte_extraordinario", monto=100.0, mes=13)])


def test_validar_extraordinario_sin_monto_o_mes():
    supuestos = SupuestosVida(patrimonio_inicial=1000.0, aporte_mensual=0.0,
                               crecimiento_anual_pct=0.0, horizonte_meses=12)
    with pytest.raises(ValueError):
        validar(supuestos, [EscenarioVidaSpec(tipo="aporte_extraordinario", mes=5)])
    with pytest.raises(ValueError):
        validar(supuestos, [EscenarioVidaSpec(tipo="retiro_extraordinario", monto=100.0)])


def test_validar_aumentar_aportes_anualmente_sin_pct():
    supuestos = SupuestosVida(patrimonio_inicial=1000.0, aporte_mensual=0.0,
                               crecimiento_anual_pct=0.0, horizonte_meses=12)
    with pytest.raises(ValueError):
        validar(supuestos, [EscenarioVidaSpec(tipo="aumentar_aportes_anualmente")])


def test_todos_los_tipos_estan_en_tipos_vida():
    esperados = {
        "continuar_igual", "aumentar_aporte", "disminuir_aporte", "dejar_de_aportar",
        "aporte_extraordinario", "retiro_extraordinario", "aumentar_aportes_anualmente",
    }
    assert set(TIPOS_VIDA) == esperados
