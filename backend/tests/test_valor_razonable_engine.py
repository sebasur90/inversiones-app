"""Valor razonable por múltiplos de pares: escenarios, margen de seguridad vs. potencial, faltantes, supuestos."""
import random
import re
from dataclasses import asdict

import pytest

from app.services import valor_razonable_engine as vre
from app.services import valuacion_engine as ve

PRECIO = 100.0
# Cinco pares con mediana 25, Q1 22 y Q3 28: con un múltiplo propio de 20, el valor base es 125 (precio × 25 ÷ 20).
PARES_PE = [20.0, 22.0, 25.0, 28.0, 30.0]
PARES_PS = [2.0, 2.2, 2.5, 2.8, 3.0]


def ficha(sector="Consumo básico", base="X", **valores) -> ve.Ficha:
    return ve.Ficha(ticker_base=base, valores=dict(valores), sector=sector)


def grupo(clave: str, multiplos: list[float], **fijos) -> list[ve.Ficha]:
    """Pares que sólo difieren en un múltiplo (el resto de `fijos` es igual para todos)."""
    return [ficha(base=f"P{i}", **{clave: m}, **fijos) for i, m in enumerate(multiplos)]


def pares_pe_ps() -> list[ve.Ficha]:
    return [ficha(base=f"P{i}", pe=a, ps=b) for i, (a, b) in enumerate(zip(PARES_PE, PARES_PS))]


def mercado(**kw) -> vre.DatosMercado:
    base = dict(precio=PRECIO, moneda="USD", market_cap=1000.0, enterprise_value=1000.0, ratios_confiables=True)
    base.update(kw)
    return vre.DatosMercado(**base)


def calcular(propio=None, pares=None, mkt=None, supuestos=None, **kw):
    propio = propio or ficha(pe=20.0, ps=2.0)
    return vre.valor_razonable(propio, pares if pares is not None else pares_pe_ps(), mkt or mercado(), supuestos, **kw)


def metodo(res, clave):
    return next(m for m in res.metodos if m.clave == clave)


def esc(res, clave):
    return next(e for e in res.escenarios if e.clave == clave)


# ── Margen de seguridad vs. potencial ───────────────────────────────────────

def test_valor_125_con_precio_100_da_margen_20_y_potencial_25():
    r = calcular()
    assert r.estado == vre.ESTADO_OK
    base = esc(r, "base")
    assert base.valor == pytest.approx(125.0)
    assert base.margen_seguridad == pytest.approx(0.20)
    assert base.potencial == pytest.approx(0.25)
    assert base.margen_seguridad != base.potencial


def test_escenarios_salen_de_los_cuartiles_de_los_pares_y_estan_ordenados():
    r = calcular()
    assert esc(r, "pesimista").valor == pytest.approx(110.0)    # 100 × 22 ÷ 20
    assert esc(r, "optimista").valor == pytest.approx(140.0)    # 100 × 28 ÷ 20
    pes, base, opt = (esc(r, c).valor for c in vre.ESCENARIOS)
    assert pes <= base <= opt


def test_precio_por_encima_del_valor_da_margen_y_potencial_negativos():
    r = calcular(mkt=mercado(precio=150.0), propio=ficha(pe=30.0, ps=3.0))
    base = esc(r, "base")
    assert base.valor == pytest.approx(125.0)       # el valor sólo depende de la relación con los pares
    assert base.margen_seguridad == pytest.approx(-0.20)
    assert base.potencial == pytest.approx(-1 / 6)
    assert r.lectura == vre.LECTURA_POR_ENCIMA        # 150 > optimista (140)


def test_lectura_por_debajo_dentro_y_por_encima_del_rango():
    assert calcular(mkt=mercado(precio=100.0)).lectura == vre.LECTURA_POR_DEBAJO       # 100 < pesimista 110
    assert calcular(propio=ficha(pe=30.0, ps=3.0), mkt=mercado(precio=150.0)).lectura == vre.LECTURA_POR_ENCIMA
    # múltiplo propio 22,5: pesimista 97,8 ≤ precio 100 ≤ optimista 124,4, y por debajo del valor base (111,1)
    dentro = calcular(propio=ficha(pe=22.5, ps=2.25))
    assert dentro.lectura == vre.LECTURA_DENTRO
    assert "dentro del rango" in dentro.lectura_texto and "por debajo del valor base" in dentro.lectura_texto


# ── Faltante ≠ negativo, no aplica ≠ faltante ───────────────────────────────

def test_metodo_sin_dato_propio_es_faltante_y_no_baja_el_valor():
    con = calcular()
    sin_pe = calcular(propio=ficha(ps=2.0, ev_ebitda=10.0, pb=2.0, pe=None), pares=[
        ficha(base=f"P{i}", pe=a, ps=b, ev_ebitda=10.0 * a / 20.0, pb=b)
        for i, (a, b) in enumerate(zip(PARES_PE, PARES_PS))])
    assert metodo(sin_pe, "pe").estado == vre.FALTA
    assert any(f.startswith("P/E:") for f in sin_pe.faltantes)
    assert sin_pe.estado == vre.ESTADO_OK
    assert esc(sin_pe, "base").valor == pytest.approx(esc(con, "base").valor)    # no hay penalización por el dato ausente


def test_empresa_sin_ganancias_quita_los_pe_como_no_aplica_y_sigue_concluyendo():
    propio = ficha(pe=None, ps=2.0, ev_ebitda=10.0, pb=2.0)
    propio.sin_ganancias = True
    pares = [ficha(base=f"P{i}", pe=a, ps=b, ev_ebitda=10 * a / 20, pb=b)
             for i, (a, b) in enumerate(zip(PARES_PE, PARES_PS))]
    r = calcular(propio=propio, pares=pares)
    assert metodo(r, "pe").estado == vre.NO_APLICA and "no tiene ganancias" in metodo(r, "pe").motivo
    assert metodo(r, "forward_pe").estado == vre.NO_APLICA
    assert not any(f.startswith("P/E") for f in r.faltantes)      # no aplica no es faltante
    assert r.estado == vre.ESTADO_OK and {f.familia for f in r.familias} == {"ventas_ebitda", "patrimonio"}


def test_con_menos_de_cuatro_pares_no_concluye_y_dice_que_falta():
    r = calcular(pares=pares_pe_ps()[:3])
    assert r.estado == vre.ESTADO_SIN_CONCLUSION and r.escenarios == []
    assert metodo(r, "pe").estado == vre.FALTA and "sólo 3 pares" in metodo(r, "pe").motivo
    assert any("sólo 3 pares" in f for f in r.faltantes)
    assert "no alcanza" in r.mensaje.lower()


def test_una_sola_familia_no_concluye():
    r = calcular(propio=ficha(pe=20.0), pares=grupo("pe", PARES_PE))
    assert r.estado == vre.ESTADO_SIN_CONCLUSION
    assert [f.familia for f in r.familias] == ["ganancias"]


def test_pe_y_pe_estimado_son_una_sola_familia_no_dos_votos():
    propio = ficha(pe=20.0, forward_pe=20.0)
    pares = [ficha(base=f"P{i}", pe=m, forward_pe=m) for i, m in enumerate(PARES_PE)]
    r = calcular(propio=propio, pares=pares)
    assert r.estado == vre.ESTADO_SIN_CONCLUSION
    assert len(r.familias) == 1 and sorted(r.familias[0].metodos) == ["forward_pe", "pe"]


def test_sin_precio_no_concluye_y_lo_lista_como_faltante():
    r = calcular(mkt=mercado(precio=None))
    assert r.estado == vre.ESTADO_SIN_CONCLUSION and r.faltantes[0] == "precio actual"


def test_sin_ficha_es_sin_datos():
    r = vre.valor_razonable(None, [], mercado())
    assert r.estado == vre.ESTADO_SIN_DATOS and r.escenarios == []


def test_un_etf_no_tiene_valor_razonable_por_multiplos():
    f = ve.Ficha(ticker_base="SPY", valores={"pb": 4.0}, es_etf=True)
    r = vre.valor_razonable(f, pares_pe_ps(), mercado())
    assert r.estado == vre.ESTADO_NO_APLICA and "ETF" in r.mensaje and r.metodos == []


# ── Modelo de negocio ───────────────────────────────────────────────────────

def test_un_banco_usa_pe_y_valor_libro_y_no_ev_ebitda_ni_ventas():
    propio = ficha(sector="Financiero", pe=20.0, pb=2.0, ev_ebitda=10.0, ps=2.0)
    pares = [ficha(sector="Financiero", base=f"P{i}", pe=a, pb=b, ev_ebitda=12.0, ps=2.5)
             for i, (a, b) in enumerate(zip(PARES_PE, PARES_PS))]
    r = calcular(propio=propio, pares=pares)
    assert r.estado == vre.ESTADO_OK
    assert {m.clave for m in r.metodos if m.estado == vre.USADO} == {"pe", "pb"}
    assert metodo(r, "ev_ebitda").estado == vre.NO_APLICA and metodo(r, "ps").estado == vre.NO_APLICA
    assert not any("EV/EBITDA" in f or "P/Ventas" in f for f in r.faltantes)


def test_el_valor_libro_solo_apoya_en_tecnologia_y_no_entra_al_valor():
    propio = ficha(sector="Tecnología", pe=20.0, ps=2.0, pb=5.0)
    pares = [ficha(sector="Tecnología", base=f"P{i}", pe=a, ps=b, pb=10.0)
             for i, (a, b) in enumerate(zip(PARES_PE, PARES_PS))]
    r = calcular(propio=propio, pares=pares)
    pb = metodo(r, "pb")
    assert pb.estado == vre.USADO and pb.decide is False
    assert pb.valores["base"] == pytest.approx(200.0)
    assert esc(r, "base").valor == pytest.approx(125.0)      # P/VL daría 200 y no pesa
    assert next(f for f in r.familias if f.familia == "patrimonio").decide is False


# ── EV/EBITDA con deuda neta ────────────────────────────────────────────────

def test_ev_ebitda_descuenta_la_deuda_neta():
    mkt = mercado(market_cap=1000.0, enterprise_value=1500.0)     # deuda neta 500
    propio = ficha(ev_ebitda=10.0, ps=2.0)
    pares = [ficha(base=f"P{i}", ev_ebitda=m, ps=b) for i, (m, b) in enumerate(zip([10, 11, 12, 13, 14], PARES_PS))]
    r = calcular(propio=propio, pares=pares, mkt=mkt)
    ev = metodo(r, "ev_ebitda")
    # EV de referencia = 12 × 1500 ÷ 10 = 1800; patrimonio = 1800 − 500 = 1300; valor = 100 × 1300 ÷ 1000
    assert ev.valores["base"] == pytest.approx(130.0)
    assert ev.estado == vre.USADO


def test_ev_ebitda_con_patrimonio_negativo_queda_inestable_y_se_muestra():
    mkt = mercado(market_cap=1000.0, enterprise_value=1500.0)
    propio = ficha(ev_ebitda=10.0, ps=2.0)
    pares = [ficha(base=f"P{i}", ev_ebitda=m, ps=b) for i, (m, b) in enumerate(zip([2, 3, 3, 3, 4], PARES_PS))]
    ev = metodo(calcular(propio=propio, pares=pares, mkt=mkt), "ev_ebitda")
    assert ev.estado == vre.INESTABLE and "no resulta positivo" in ev.motivo


# ── Moneda ──────────────────────────────────────────────────────────────────

def test_con_balance_en_otra_moneda_solo_quedan_pe_y_ps_recalculados():
    propio = ficha(pe=20.0, ps=2.0, forward_pe=None, ev_ebitda=None, pb=None)
    propio.descartadas_moneda = ["forward_pe", "pb", "ev_ebitda"]
    propio.recalculadas = ["pe", "ps"]
    r = calcular(propio=propio, mkt=mercado(ratios_confiables=False))
    for c in ("forward_pe", "pb", "ev_ebitda"):
        assert metodo(r, c).estado == vre.NO_APLICA and "otra moneda" in metodo(r, c).motivo
    assert {m.clave for m in r.metodos if m.estado == vre.USADO} == {"pe", "ps"}
    assert metodo(r, "pe").origen == "calculado"


# ── Estabilidad, dispersión y confianza ─────────────────────────────────────

def test_un_metodo_que_da_un_valor_absurdo_se_muestra_pero_no_entra():
    propio = ficha(pe=2.0, ps=2.0, pb=2.0)      # P/E 2 contra pares en 25 → 12,5× el precio
    pares = [ficha(base=f"P{i}", pe=a, ps=b, pb=b) for i, (a, b) in enumerate(zip(PARES_PE, PARES_PS))]
    r = calcular(propio=propio, pares=pares)
    pe = metodo(r, "pe")
    assert pe.estado == vre.INESTABLE and "no entra al valor" in pe.motivo
    assert pe.valores["base"] == pytest.approx(1250.0)       # no se oculta
    assert esc(r, "base").valor == pytest.approx(125.0)       # y no distorsiona el valor


def test_si_los_metodos_no_convergen_la_confianza_es_baja():
    propio = ficha(pe=20.0, ps=2.0)
    pares = [ficha(base=f"P{i}", pe=a, ps=m * 2.4) for i, (a, m) in enumerate(zip(PARES_PE, PARES_PS))]
    r = calcular(propio=propio, pares=pares)
    assert r.dispersion > vre.DISPERSION_MAXIMA and r.convergen is False
    assert r.confianza == "baja" and "no convergen" in r.regla_confianza


def test_confianza_alta_con_tres_familias_pocas_diferencias_y_muchos_pares():
    multiplos = [20, 21, 22, 23, 24, 25, 26]
    propio = ficha(pe=20.0, ps=2.0, fcf_yield=0.05)
    pares = [ficha(base=f"P{i}", pe=m, ps=m / 10, fcf_yield=1 / m) for i, m in enumerate(multiplos)]
    r = calcular(propio=propio, pares=pares)
    assert r.estado == vre.ESTADO_OK and len(r.familias) == 3
    assert r.confianza == "alta"


def test_la_confianza_de_los_datos_del_diagnostico_la_limita():
    multiplos = [20, 21, 22, 23, 24, 25, 26]
    propio = ficha(pe=20.0, ps=2.0, fcf_yield=0.05)
    pares = [ficha(base=f"P{i}", pe=m, ps=m / 10, fcf_yield=1 / m) for i, m in enumerate(multiplos)]
    assert calcular(propio=propio, pares=pares, confianza_datos="media").confianza == "media"
    assert calcular(propio=propio, pares=pares, confianza_datos="baja").confianza == "baja"


# ── Supuestos del usuario ───────────────────────────────────────────────────

def test_ajuste_global_mueve_el_valor_exactamente():
    r = calcular(supuestos=vre.Supuestos(ajuste_pct=-10.0))
    assert esc(r, "base").valor == pytest.approx(112.5)
    assert esc(r, "pesimista").valor == pytest.approx(99.0)
    assert r.supuestos["ajuste_pct"] == -10.0 and r.supuestos["por_defecto"] is False


def test_excluir_un_metodo_lo_saca_del_valor_y_lo_marca():
    r = calcular(supuestos=vre.Supuestos(excluir=("ps",)))
    assert metodo(r, "ps").estado == vre.EXCLUIDO
    assert r.estado == vre.ESTADO_SIN_CONCLUSION      # queda una sola familia


def test_multiplo_manual_reemplaza_la_mediana_y_escala_los_cuartiles():
    r = calcular(supuestos=vre.Supuestos(multiplos={"pe": 30.0}))
    pe = metodo(r, "pe")
    assert pe.manual is True and pe.referencias["base"] == 30.0
    assert pe.valores["base"] == pytest.approx(150.0)             # 100 × 30 ÷ 20
    assert pe.referencias["pesimista"] == pytest.approx(30.0 * 22 / 25)
    assert esc(r, "base").valor == pytest.approx(137.5)           # mediana entre 150 (ganancias) y 125 (ventas)


def test_el_ajuste_global_no_toca_un_multiplo_fijado_a_mano():
    r = calcular(supuestos=vre.Supuestos(ajuste_pct=-10.0, multiplos={"pe": 30.0}))
    assert metodo(r, "pe").valores["base"] == pytest.approx(150.0)
    assert metodo(r, "ps").valores["base"] == pytest.approx(112.5)


@pytest.mark.parametrize("crudo", [
    {"ajuste_pct": 80}, {"ajuste_pct": "mucho"}, {"excluir": ["magia"]}, {"multiplos": {"pe": -3}},
    {"multiplos": {"pe": 0}}, {"multiplos": {"pe": 1000}}, {"multiplos": {"zzz": 10}},
])
def test_supuestos_invalidos_se_rechazan_con_mensaje(crudo):
    with pytest.raises(ValueError):
        vre.normalizar_supuestos(crudo)


def test_supuestos_validos_se_normalizan():
    s = vre.normalizar_supuestos({"ajuste_pct": 5, "excluir": ["ps", "ps"], "multiplos": {"pe": 18}})
    assert s.ajuste_pct == 5.0 and s.excluir == ("ps",) and s.multiplos == {"pe": 18.0}
    assert vre.normalizar_supuestos(None).por_defecto and vre.normalizar_supuestos({}).por_defecto


# ── Determinismo y referencia externa ───────────────────────────────────────

def test_mismo_resultado_sin_importar_el_orden_de_los_pares():
    pares = pares_pe_ps()
    esperado = asdict(calcular(pares=list(pares)))
    for semilla in range(5):
        mezclados = list(pares)
        random.Random(semilla).shuffle(mezclados)
        assert asdict(calcular(pares=mezclados)) == esperado
    assert asdict(calcular()) == asdict(calcular())


def test_la_referencia_de_analistas_se_informa_pero_no_cambia_el_valor():
    sin = calcular()
    con = calcular(mkt=mercado(analistas={"media": 200.0, "minimo": 150.0, "maximo": 250.0, "n": 12}))
    assert con.analistas["media"] == 200.0 and sin.analistas is None
    assert [asdict(e) for e in con.escenarios] == [asdict(e) for e in sin.escenarios]
    assert con.lectura == sin.lectura and con.confianza == sin.confianza


# ── Lenguaje ────────────────────────────────────────────────────────────────

def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _textos(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _textos(v)


@pytest.mark.parametrize("kw", [
    {}, {"supuestos": vre.Supuestos(ajuste_pct=10)}, {"pares": pares_pe_ps()[:2]},
    {"mkt": mercado(precio=300.0)}, {"mkt": mercado(precio=50.0)},
])
def test_nunca_dice_compra_ni_venta(kw):
    prohibidas = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)
    r = calcular(**kw)
    for t in _textos(asdict(r)):
        assert not prohibidas.search(t), t
    for t in vre.LIMITES + (vre.SALVEDAD,):
        assert not prohibidas.search(t), t
