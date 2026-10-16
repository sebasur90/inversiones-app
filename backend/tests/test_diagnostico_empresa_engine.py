"""Diagnóstico integral: valuación, calidad, crecimiento, solidez y confianza, cada una por separado,
con el faltante distinguido del negativo y lo que no aplica distinguido del faltante."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import diagnostico_empresa_engine as de
from app.services import valuacion_engine as ve

HOY = date(2026, 10, 16)
RECIENTE = HOY - timedelta(days=3)
BALANCE = HOY - timedelta(days=40)

#           A     B     C     D
_PARES = {
    "pe": (20, 22, 25, 28), "forward_pe": (18, 20, 22, 25), "ev_ebitda": (12, 13, 14, 15), "ps": (3, 3.5, 4, 4.5),
    "pb": (3, 3.5, 4, 4.5), "fcf_yield": (0.03, 0.035, 0.04, 0.045),
    "margen_bruto": (0.40, 0.42, 0.44, 0.46), "margen_operativo": (0.20, 0.22, 0.18, 0.21),
    "margen_neto": (0.12, 0.14, 0.10, 0.13), "roe": (0.15, 0.16, 0.14, 0.17), "roa": (0.06, 0.07, 0.05, 0.065),
    "deuda_patrimonio": (0.5, 0.6, 0.7, 0.8), "crec_ingresos": (0.05, 0.06, 0.04, 0.07),
    "crec_ganancias": (0.08, 0.10, 0.06, 0.12), "crec_esperado": (0.07, 0.09, 0.05, 0.10),
}
# Una empresa sana, con todo mejor que el grupo.
_BUENA = {
    "pe": 12, "forward_pe": 10, "ev_ebitda": 8, "ps": 2, "pb": 2, "fcf_yield": 0.07, "margen_bruto": 0.50,
    "margen_operativo": 0.30, "margen_neto": 0.20, "roe": 0.25, "roa": 0.10, "deuda_patrimonio": 0.3,
    "crec_ingresos": 0.12, "crec_ganancias": 0.20, "crec_esperado": 0.15,
}


def pares(sector="Industria", **cambios):
    return [
        ve.Ficha(t, {k: v[i] for k, v in _PARES.items()}, sector=sector, fecha_dato=RECIENTE, periodo_contable=BALANCE, **cambios)
        for i, t in enumerate("ABCD")
    ]


def empresa(sector="Industria", **valores):
    base = {**_BUENA, **valores}
    return ve.Ficha("X", {k: v for k, v in base.items() if v is not None}, sector=sector, fecha_dato=RECIENTE,
                    periodo_contable=BALANCE, extra={})


def diag(obj, ps=None):
    ps = pares(obj.sector) if ps is None else ps
    res = ve.evaluar(obj, ps, hoy=HOY)
    d = de.diagnosticar(obj, res, ps, hoy=HOY)
    return d, {x.clave: x for x in d.dimensiones}


# ── 1. empresa rentable con valuación inferior a sus pares ────────────────

def test_empresa_sana_y_barata():
    d, por = diag(empresa())
    assert d.version_reglas == de.VERSION_REGLAS
    assert por["valuacion"].estado == "Más barata que sus pares"
    assert por["calidad"].estado == "Alta" and por["calidad"].nivel == de.BIEN
    assert por["crecimiento"].estado == "Alto"
    assert por["solidez"].estado == "Sólida"
    assert por["confianza"].estado == "Alta" and d.confianza == "alta"
    # Las cinco dimensiones, en orden, y ninguna lleva un número único
    assert [x.clave for x in d.dimensiones] == ["valuacion", "calidad", "crecimiento", "solidez", "confianza"]
    # Cada dimensión explica cómo se decide
    assert all(x.regla for x in d.dimensiones)
    assert por["valuacion"].percentil is not None and por["valuacion"].percentil >= 75


# ── 2. barata pero con beneficios negativos ───────────────────────────────

def test_barata_sin_ganancias_no_es_una_oportunidad_limpia():
    obj = empresa(pe=None, forward_pe=None, margen_neto=-0.10, margen_operativo=-0.05, fcf_yield=None,
                  crec_ganancias=None, crec_esperado=None)
    obj.sin_ganancias = True
    _, por = diag(obj)
    assert "alerta" in por["valuacion"].estado.lower()                     # barata, con señales de alerta
    assert por["calidad"].estado == "Débil"
    assert por["solidez"].estado == "Con señales de atención"
    # El P/E que no aplica no se lista como dato faltante, y el crecimiento de ganancias tampoco
    assert not any("P/E" in f for f in por["valuacion"].faltantes)
    assert not any("Crecimiento de ganancias" in f for f in por["crecimiento"].faltantes)
    assert any("no aplica" in r.texto for r in por["crecimiento"].razones)


def test_sin_ganancias_y_consumiendo_caja_es_fragil():
    obj = empresa(pe=None, forward_pe=None, margen_neto=-0.10, fcf_yield=-0.02, crec_ganancias=None, crec_esperado=None)
    obj.sin_ganancias = True
    _, por = diag(obj)
    assert por["solidez"].estado == "Frágil" and por["solidez"].nivel == de.RIESGO
    # Un flujo de caja negativo también es "más caro" en la familia de flujo: la valuación queda mixta, no barata
    assert por["valuacion"].estado == "Señales mixtas"


# ── 3. barata con caída de ingresos y márgenes ────────────────────────────

def test_barata_con_ingresos_y_margenes_en_caida():
    obj = empresa(crec_ingresos=-0.10, margen_operativo=0.05, margen_neto=0.02, roe=0.02, roa=0.01, crec_ganancias=-0.30)
    _, por = diag(obj)
    assert por["calidad"].estado == "Débil"
    assert por["crecimiento"].estado == "En caída" and por["crecimiento"].nivel == de.RIESGO
    assert "alerta" in por["valuacion"].estado.lower()


# ── 4. calidad alta con valuación elevada ─────────────────────────────────

def test_calidad_alta_con_valuacion_exigente():
    obj = empresa(pe=40, forward_pe=35, ev_ebitda=25, ps=8, pb=9, fcf_yield=0.01)
    _, por = diag(obj)
    assert por["valuacion"].estado == "Cara, con fundamentos que la acompañan"
    assert por["calidad"].estado == "Alta"
    # La valuación nunca se juzga "mala": es neutra, y la calidad y la valuación no se mezclan
    assert por["valuacion"].nivel == de.NEUTRO


# ── 5. crecimiento alto con historia insuficiente ─────────────────────────

def test_crecimiento_alto_aclara_que_no_hay_historia():
    _, por = diag(empresa(crec_ingresos=0.60, crec_ganancias=0.80, crec_esperado=0.50))
    c = por["crecimiento"]
    assert c.estado == "Alto"
    assert de.HISTORIA_NO_DISPONIBLE in c.faltantes
    assert any(r.origen == "estimado" for r in c.razones)         # lo esperado se rotula como estimación
    assert any(r.origen == "observado" for r in c.razones)


def test_crecimiento_esperado_distinto_del_observado_se_explica():
    _, por = diag(empresa(crec_ganancias=0.05, crec_esperado=0.30))
    assert any("Se espera más crecimiento" in r.texto and r.origen == "estimado" for r in por["crecimiento"].razones)


# ── 6. sin competidores suficientes ───────────────────────────────────────

def test_sin_pares_no_hay_conclusion_de_valuacion():
    obj = empresa()
    d, por = diag(obj, ps=[])
    assert por["valuacion"].estado == "Datos insuficientes" and por["valuacion"].nivel == de.SIN_DATOS
    assert por["calidad"].estado == "Sin conclusión"
    assert por["confianza"].estado == "Baja" and d.confianza == "baja"


# ── 7. métricas incompletas: faltante no es negativo ──────────────────────

def test_metricas_incompletas_no_bajan_el_estado():
    obj = ve.Ficha("X", {"pe": 12, "ev_ebitda": 8, "margen_operativo": 0.30, "roe": 0.25},
                   sector="Industria", fecha_dato=RECIENTE, periodo_contable=BALANCE)
    _, por = diag(obj)
    assert por["calidad"].estado == "Alta"                         # lo que hay es bueno; no se penaliza lo que falta
    assert "Margen neto" in por["calidad"].faltantes
    assert por["solidez"].estado == "Sin conclusión"              # un solo indicador no alcanza para decir "sólida"
    assert por["confianza"].estado in ("Baja", "Media")           # pero la confianza sí lo refleja


# ── 8. balances de períodos distintos ─────────────────────────────────────

def test_periodos_contables_distintos_bajan_la_confianza():
    ps = pares()
    for p in ps:
        p.periodo_contable = BALANCE - timedelta(days=200)
    d, por = diag(empresa(), ps)
    assert por["confianza"].estado == "Media"
    assert any("balances de otro período" in r.texto for r in por["confianza"].razones)


# ── 9. datos desactualizados ──────────────────────────────────────────────

def test_datos_viejos_dan_confianza_baja():
    obj = empresa()
    obj.fecha_dato = HOY - timedelta(days=100)
    d, por = diag(obj)
    assert por["confianza"].estado == "Baja"
    obj.fecha_dato, obj.periodo_contable = RECIENTE, HOY - timedelta(days=300)    # balance viejo
    assert diag(obj)[1]["confianza"].estado == "Baja"


def test_sin_fecha_de_balance_no_penaliza_pero_avisa():
    obj = empresa()
    obj.periodo_contable = None
    _, por = diag(obj)
    assert por["confianza"].estado == "Alta"                       # recién agregada la clave: no baja la confianza
    assert any("último balance" in f for f in por["confianza"].faltantes)


# ── 12. ETF frente a empresa individual ───────────────────────────────────

def test_etf_solo_se_evalua_por_valuacion_y_confianza():
    ps = [ve.Ficha(t, {"gastos": g, "pe": pe}, es_etf=True, fecha_dato=RECIENTE) for t, g, pe in
          (("A", 0.0009, 24), ("B", 0.0003, 25), ("C", 0.0020, 26))]
    obj = ve.Ficha("X", {"gastos": 0.0004, "pe": 22}, es_etf=True, fecha_dato=RECIENTE)
    d, por = diag(obj, ps)
    for clave in ("calidad", "crecimiento", "solidez"):
        assert por[clave].nivel == de.NO_APLICA and "ETF" in por[clave].resumen
    assert por["valuacion"].nivel != de.NO_APLICA
    assert por["confianza"].clave == "confianza"


# ── 13. el sector cambia qué se espera ────────────────────────────────────

def test_un_banco_no_se_penaliza_por_lo_que_no_aplica():
    sin = {"ev_ebitda": None, "ps": None, "margen_bruto": None, "deuda_patrimonio": None, "fcf_yield": None}
    obj = empresa(sector="Financiero", **sin)
    ps = [ve.Ficha(f.ticker_base, {k: v for k, v in f.valores.items() if k not in sin}, sector="Financiero",
                   fecha_dato=RECIENTE, periodo_contable=BALANCE) for f in pares("Financiero")]
    _, por = diag(obj, ps)
    nombres_faltantes = " ".join(por["confianza"].faltantes)
    assert "EV/EBITDA" not in nombres_faltantes and "Margen bruto" not in nombres_faltantes
    assert por["confianza"].estado == "Alta"
    assert any("capital regulatorio" in f for f in por["calidad"].faltantes)    # lo propio del sector, dicho


# ── solidez ───────────────────────────────────────────────────────────────

def test_dividendo_no_cubierto_y_deuda_alta_es_fragil():
    obj = empresa(deuda_patrimonio=3.0)
    obj.extra = {"payout": 1.4, "beta": 1.0, "liquidez_corriente": 1.5}
    _, por = diag(obj)
    assert por["solidez"].estado == "Frágil"
    assert any("más dividendos que lo que gana" in r.texto for r in por["solidez"].razones)


def test_beta_alto_solo_pide_atencion():
    obj = empresa()
    obj.extra = {"beta": 2.1}
    _, por = diag(obj)
    assert por["solidez"].estado == "Con señales de atención" and por["solidez"].nivel == de.ATENCION


# ── origen de cada dato ───────────────────────────────────────────────────

def test_origen_de_las_metricas():
    f = ve.Ficha("X", {}, recalculadas=["ps"])
    assert de.origen_metrica("pe", f) == "observado"
    assert de.origen_metrica("forward_pe", f) == "estimado" and de.origen_metrica("crec_esperado", f) == "estimado"
    assert de.origen_metrica("fcf_yield", f) == "calculado" and de.origen_metrica("rend_12m", f) == "calculado"
    assert de.origen_metrica("ps", f) == "calculado"            # recalculado en USD por la app


def test_diagnostico_sin_datos_no_inventa_nada():
    d = de.diagnostico_sin_datos()
    assert d.confianza == "sin_datos"
    assert all(x.nivel == de.SIN_DATOS and x.percentil is None and not x.razones for x in d.dimensiones)


# ── extracción de los datos nuevos ────────────────────────────────────────

def test_extrae_valores_absolutos_y_periodo_contable():
    epoch = int(datetime(2026, 6, 30, tzinfo=timezone.utc).timestamp())
    raw = {"trailingPE": 20.0, "forwardPE": 16.0, "beta": 1.2, "payoutRatio": 0.45, "currentRatio": 1.8,
           "mostRecentQuarter": epoch, "_usd": {"market_cap": 1e10, "freeCashflow": 4e8}}
    e = ve.extraer_metricas(raw, True, False, "Industria")
    assert e.extra == {"beta": 1.2, "payout": 0.45, "liquidez_corriente": 1.8}
    assert e.periodo_contable == date(2026, 6, 30)
    assert e.valores["crec_esperado"] == pytest.approx(0.25)       # 20 / 16 − 1


def test_crecimiento_esperado_no_se_inventa():
    base = {"_usd": {"market_cap": 1e10}}
    assert ve.extraer_metricas({**base, "trailingPE": 20.0}, True, False, None).valores["crec_esperado"] is None
    assert ve.extraer_metricas({**base, "trailingPE": -5.0, "forwardPE": 10.0}, True, False, None).valores["crec_esperado"] is None
    # balance en otra moneda: los dos P/E no son comparables
    assert ve.extraer_metricas({**base, "trailingPE": 20.0, "forwardPE": 16.0}, False, False, None).valores["crec_esperado"] is None
    # absurdo (P/E estimado casi cero) se descarta en vez de mostrar +4000%
    assert ve.extraer_metricas({**base, "trailingPE": 50.0, "forwardPE": 1.0}, True, False, None).valores["crec_esperado"] is None


def test_flujo_de_caja_de_un_banco_no_se_usa():
    raw = {"_usd": {"market_cap": 1e10, "freeCashflow": 4e8}}
    assert ve.extraer_metricas(raw, True, False, "Financiero").valores["fcf_yield"] is None
    assert ve.extraer_metricas(raw, True, False, "Industria").valores["fcf_yield"] == pytest.approx(0.04)


def test_la_estimacion_no_mueve_la_lectura_clasica():
    # Un crec_esperado altísimo no alcanza para "justificar" una prima en la lectura de siempre
    obj = ve.Ficha("X", {"pe": 40, "ev_ebitda": 25, "ps": 8, "crec_esperado": 0.9, "crec_ingresos": 0.05})
    ps = [ve.Ficha(t, {"pe": pe, "ev_ebitda": ev, "ps": ps_, "crec_esperado": 0.05, "crec_ingresos": 0.05})
          for t, pe, ev, ps_ in (("A", 20, 12, 3), ("B", 22, 13, 3.5), ("C", 25, 14, 4), ("D", 28, 15, 4.5))]
    assert ve.evaluar(obj, ps).lectura == ve.LECTURA_CARA
