"""Valuación relativa: limpieza de métricas (unidades de Yahoo, P/E negativo, monedas), percentiles,
winsorización y lecturas (barata, cara, trampa de valor, cara justificada)."""
from datetime import date, timedelta

import pytest

from app.services import valuacion_engine as ve


# ── extracción ────────────────────────────────────────────────────────────

def test_unidades_de_yahoo():
    raw = {"trailingPE": 25.0, "dividendYield": 2.3, "debtToEquity": 150.0, "returnOnEquity": 0.42,
           "revenueGrowth": 0.067, "_usd": {"market_cap": 1e11, "freeCashflow": 5e9, "netIncomeToCommon": 4e9}}
    e = ve.extraer_metricas(raw, True, False, "Consumo básico")
    assert e.valores["pe"] == 25.0
    assert e.valores["div_yield"] == pytest.approx(0.023)
    assert e.valores["deuda_patrimonio"] == pytest.approx(1.5)
    assert e.valores["fcf_yield"] == pytest.approx(0.05)
    assert e.valores["roe"] == 0.42


def test_etf_gastos_en_porcentaje_y_yield_en_fraccion():
    e = ve.extraer_metricas({"netExpenseRatio": 0.0945, "yield": 0.0099, "trailingPE": 24.5}, True, True, None)
    assert e.valores["gastos"] == pytest.approx(0.000945)
    assert e.valores["div_yield"] == pytest.approx(0.0099)
    assert e.valores["pe"] == 24.5
    assert "roe" not in e.valores


def test_pe_negativo_es_sin_ganancias():
    e = ve.extraer_metricas({"trailingPE": -12.0, "_usd": {"market_cap": 1e9, "netIncomeToCommon": -5e7}}, True, False, None)
    assert e.valores["pe"] is None and e.sin_ganancias


def test_tope_de_cordura():
    e = ve.extraer_metricas({"trailingPE": 850.0, "enterpriseToEbitda": 400.0}, True, False, None)
    assert e.valores["pe"] is None and e.valores["ev_ebitda"] is None


def test_balance_en_otra_moneda_recalcula_en_usd():
    raw = {"trailingPE": 41.0, "forwardPE": 5.2, "priceToBook": 9.6, "enterpriseToEbitda": 3.0,
           "returnOnEquity": 0.01,
           "_usd": {"market_cap": 6e9, "netIncomeToCommon": 6e7, "totalRevenue": 3e9}}
    e = ve.extraer_metricas(raw, False, False, "Industria")
    assert e.valores["pe"] == pytest.approx(100.0)
    assert e.valores["ps"] == pytest.approx(2.0)
    assert e.valores["forward_pe"] is None and e.valores["pb"] is None and e.valores["ev_ebitda"] is None
    assert set(e.recalculadas) == {"pe", "ps"}
    assert "forward_pe" in e.descartadas_moneda
    assert e.valores["roe"] == 0.01      # las proporciones no dependen de la moneda


def test_financieros_sin_ebitda_ni_deuda():
    raw = {"trailingPE": 10.0, "enterpriseToEbitda": 5.0, "priceToSalesTrailing12Months": 2.0, "debtToEquity": 300.0}
    raw["grossMargins"] = 0.0
    e = ve.extraer_metricas(raw, True, False, "Financiero")
    assert e.valores["ev_ebitda"] is None and e.valores["ps"] is None and e.valores["deuda_patrimonio"] is None
    assert e.valores["margen_bruto"] is None


def test_frases_respetan_siglas():
    obj = _ficha("X", pe=23, ev_ebitda=13.5, ps=3.7, roe=0.40, margen_operativo=0.40)
    textos = " ".join(f.texto for f in ve.evaluar(obj, PARES).frases)
    assert "Mejor margen operativo y ROE que sus pares." in textos


# ── rendimientos ──────────────────────────────────────────────────────────

def _serie(precios, desde=date(2025, 10, 6)):
    return [{"fecha": (desde + timedelta(weeks=i)).isoformat(), "cierre": p} for i, p in enumerate(precios)]


def test_rendimientos_en_usd():
    serie = _serie([100.0] * 39 + [110.0] * 13 + [120.0])
    r = ve.rendimientos(serie)
    assert r["rend_12m"] == pytest.approx(0.2)
    assert r["rend_3m"] == pytest.approx(120 / 110 - 1)


def test_rendimientos_pasados_a_usd_con_factor():
    serie = _serie([1000.0] * 52 + [2000.0])           # en pesos se duplicó…
    corte = date(2025, 10, 6) + timedelta(weeks=52)
    r = ve.rendimientos(serie, lambda f: 1 / 1000 if f < corte else 1 / 2000)  # …pero el MEP también
    assert r["rend_12m"] == pytest.approx(0.0)


def test_rendimientos_serie_corta():
    assert ve.rendimientos(_serie([100.0, 101.0]))["rend_12m"] is None
    assert ve.rendimientos([])["rend_3m"] is None


# ── percentiles ───────────────────────────────────────────────────────────

def test_percentil_rango_medio():
    assert ve.percentil(10, [10, 20, 30, 40]) == pytest.approx(12.5)
    assert ve.percentil(40, [10, 20, 30, 40]) == pytest.approx(87.5)


def test_winsorizar_recorta_outliers_con_cinco_o_mas():
    datos = [10, 11, 12, 13, 14, 500]
    w = ve.winsorizar(datos)
    assert max(w) < 500
    assert ve.winsorizar([1, 2, 500]) == [1, 2, 500]


def test_evaluar_metrica_invierte_si_menor_es_mejor():
    pe = ve.METRICA_POR_CLAVE["pe"]
    r = ve.evaluar_metrica(pe, 10.0, [20.0, 25.0, 30.0, 35.0])
    assert r.percentil == pytest.approx(90.0) and r.banda == "mejor"
    assert r.mediana_pares == pytest.approx(27.5)


def test_sin_pares_no_hay_comparacion():
    r = ve.evaluar_metrica(ve.METRICA_POR_CLAVE["pe"], 10.0, [None, None])
    assert r.percentil is None and r.banda is None and r.metodo is None


# ── lecturas ──────────────────────────────────────────────────────────────

def _ficha(t, **valores):
    return ve.Ficha(ticker_base=t, valores=valores)


PARES = [
    _ficha("A", pe=20, ev_ebitda=12, ps=3, margen_operativo=0.20, roe=0.15, crec_ingresos=0.05, rend_12m=0.10),
    _ficha("B", pe=22, ev_ebitda=13, ps=3.5, margen_operativo=0.22, roe=0.16, crec_ingresos=0.06, rend_12m=0.12),
    _ficha("C", pe=25, ev_ebitda=14, ps=4, margen_operativo=0.18, roe=0.14, crec_ingresos=0.04, rend_12m=0.08),
    _ficha("D", pe=28, ev_ebitda=15, ps=4.5, margen_operativo=0.21, roe=0.17, crec_ingresos=0.07, rend_12m=0.09),
]


def test_barata_limpia():
    obj = _ficha("X", pe=12, ev_ebitda=8, ps=2, margen_operativo=0.20, roe=0.15, crec_ingresos=0.05, rend_12m=0.10)
    r = ve.evaluar(obj, PARES)
    assert r.lectura == ve.LECTURA_BARATA
    assert any("Más barata que sus pares en P/E, EV/EBITDA y P/Ventas" in f.texto for f in r.frases)


def test_barata_con_trampa_de_valor():
    obj = _ficha("X", pe=12, ev_ebitda=8, ps=2, margen_operativo=0.05, roe=0.02, crec_ingresos=-0.10, rend_12m=-0.30)
    r = ve.evaluar(obj, PARES)
    assert r.lectura == ve.LECTURA_TRAMPA
    assert r.frases[0].tono == "alerta"
    assert "ingresos cayendo" in r.frases[0].texto


def test_cara_justificada():
    obj = _ficha("X", pe=40, ev_ebitda=25, ps=8, margen_operativo=0.40, roe=0.35, crec_ingresos=0.30, rend_12m=0.10)
    r = ve.evaluar(obj, PARES)
    assert r.lectura == ve.LECTURA_CARA_JUSTIFICADA


def test_cara():
    obj = _ficha("X", pe=40, ev_ebitda=25, ps=8, margen_operativo=0.20, roe=0.15, crec_ingresos=0.05, rend_12m=0.10)
    assert ve.evaluar(obj, PARES).lectura == ve.LECTURA_CARA


def test_mixta_y_en_linea():
    mixta = _ficha("X", pe=12, ev_ebitda=25, ps=3.7)
    assert ve.evaluar(mixta, PARES).lectura == ve.LECTURA_MIXTA
    en_linea = _ficha("X", pe=23, ev_ebitda=13.5, ps=3.7)
    assert ve.evaluar(en_linea, PARES).lectura == ve.LECTURA_EN_LINEA


def test_datos_insuficientes():
    # Una sola métrica de valuación comparable no alcanza para una lectura.
    r = ve.evaluar(_ficha("X", pe=12), [_ficha("A", pe=20)])
    assert r.lectura == ve.LECTURA_SIN_DATOS
    r = ve.evaluar(_ficha("X", pe=12), [])
    assert r.lectura == ve.LECTURA_SIN_DATOS
    assert any("pocos pares" in a for a in r.advertencias)


def test_advertencias_moneda_y_dato_viejo():
    obj = ve.Ficha(ticker_base="X", valores={"pe": 12, "ev_ebitda": 8}, recalculadas=["pe"],
                   descartadas_moneda=["forward_pe"], fecha_dato=date(2026, 1, 1))
    r = ve.evaluar(obj, PARES, hoy=date(2026, 3, 1))
    assert any("otra moneda" in a and "P/E se recalcularon" in a for a in r.advertencias)
    assert any("desactualizados" in a for a in r.advertencias)


def test_etf_usa_gastos_como_valuacion():
    pares = [ve.Ficha("A", {"gastos": 0.0009, "pe": 24}, es_etf=True),
             ve.Ficha("B", {"gastos": 0.0003, "pe": 25}, es_etf=True),
             ve.Ficha("C", {"gastos": 0.0020, "pe": 26}, es_etf=True)]
    obj = ve.Ficha("X", {"gastos": 0.0040, "pe": 30}, es_etf=True)
    r = ve.evaluar(obj, pares)
    assert r.lectura == ve.LECTURA_CARA
    assert "roe" not in {m.clave for m in r.metricas}


# ── un solo par: comparación directa ──────────────────────────────────────

def test_un_solo_par_compara_directo():
    pe = ve.METRICA_POR_CLAVE["pe"]
    r = ve.evaluar_metrica(pe, 20.0, [25.0])
    assert r.metodo == "directo" and r.banda == "mejor" and r.percentil is None
    assert r.diferencia == pytest.approx(-0.2)
    assert ve.evaluar_metrica(pe, 24.0, [25.0]).banda == "media"
    assert ve.evaluar_metrica(pe, 30.0, [25.0]).banda == "peor"


def test_un_solo_par_en_metricas_pct_usa_piso():
    crec = ve.METRICA_POR_CLAVE["crec_ingresos"]
    # 1% vs 0,5%: relativo sería +100%, pero contra el piso de 2 puntos es +25% -> mejor
    assert ve.evaluar_metrica(crec, 0.01, [0.005]).banda == "mejor"
    assert ve.evaluar_metrica(crec, 0.006, [0.005]).banda == "media"


def test_ko_contra_pep_da_lectura():
    ko = _ficha("KO", pe=27.9, forward_pe=26.4, ps=8.0, margen_operativo=0.35, roe=0.42, rend_12m=0.39)
    pep = _ficha("PEP", pe=20.0, forward_pe=17.0, ps=2.4, margen_operativo=0.13, roe=0.50, rend_12m=0.05)
    r = ve.evaluar(ko, [pep])
    assert r.lectura == ve.LECTURA_CARA
    assert "15% mejores que el par" in r.regla_lectura
    assert any("un solo par (PEP)" in a for a in r.advertencias)
    assert any("vs. el par" in f.texto for f in r.frases)
