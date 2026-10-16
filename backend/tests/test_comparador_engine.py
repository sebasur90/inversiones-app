"""Comparador "¿qué compraría en su lugar?": comparabilidad, tabla por sector, ranking dentro del grupo
y conclusión determinista. Motor puro: sin DB ni red."""
import re
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from app.services import comparador_engine as ce
from app.services import pares_engine as pe
from app.services import valuacion_engine as ve

HOY = date(2026, 10, 16)
RECIENTE = HOY - timedelta(days=3)
BALANCE = HOY - timedelta(days=40)

_BASE = {
    "pe": 20, "forward_pe": 18, "ev_ebitda": 12, "ps": 3, "pb": 3, "fcf_yield": 0.04, "margen_bruto": 0.40,
    "margen_operativo": 0.20, "margen_neto": 0.12, "roe": 0.15, "roa": 0.06, "deuda_patrimonio": 0.6,
    "crec_ingresos": 0.06, "crec_ganancias": 0.08, "crec_esperado": 0.09, "div_yield": 0.02,
    "rend_3m": 0.02, "rend_6m": 0.04, "rend_12m": 0.08,
}
_MULTIPLOS = ("pe", "forward_pe", "ev_ebitda", "ps", "pb")
_FUNDAMENTOS = ("margen_bruto", "margen_operativo", "margen_neto", "roe", "roa", "crec_ingresos", "crec_ganancias", "crec_esperado")


def valores(val=1.0, fund=1.0, **cambios):
    """`val` > 1 = más cara; `fund` > 1 = mejores márgenes, retornos, crecimiento y menos deuda."""
    v = dict(_BASE)
    for k in _MULTIPLOS:
        v[k] = _BASE[k] * val
    v["fcf_yield"] = _BASE["fcf_yield"] / val
    for k in _FUNDAMENTOS:
        v[k] = _BASE[k] * fund
    v["deuda_patrimonio"] = _BASE["deuda_patrimonio"] / fund
    v.update(cambios)
    return v


def ficha(base, val=1.0, fund=1.0, sector="Industria", **kw):
    vals = kw.pop("vals", None) or valores(val, fund)
    return ve.Ficha(base, vals, sector=sector, fecha_dato=kw.pop("fecha_dato", RECIENTE),
                    periodo_contable=kw.pop("periodo_contable", BALANCE), **kw)


def perfil(base, *, etf=False, sector="Industria", industria="Máquinas", categoria=None, region="EEUU", tamano=1e11,
           simbolo=None, **flags):
    return ce.Perfil(pe.Candidato(base, simbolo or base, base, etf, sector, industria, categoria, region, tamano), **flags)


def fichero(fichas):
    return lambda base: fichas.get(base)


def correr(obj_ficha, alternativas, con=None, **perfil_kw):
    """`alternativas`: {base: (ficha, kwargs de perfil)}; el objetivo es 'X'."""
    obj = perfil("X", **perfil_kw)
    pool = [perfil(b, **kw) for b, (_, kw) in alternativas.items()]
    fichas = {"X": obj_ficha, **{b: f for b, (f, _) in alternativas.items()}}
    return ce.comparar(obj, pool, fichero(fichas), con, hoy=HOY)


def tres(val, fund, obj_val=1.0, obj_fund=1.0):
    """El objetivo contra tres alternativas comparables (todas en el grupo)."""
    alts = {
        "A": (ficha("A", 0.8, 1.2), {"en_grupo": True}),
        "B": (ficha("B", 1.0, 1.0), {"en_grupo": True}),
        "C": (ficha("C", 1.2, 0.8), {"en_grupo": True}),
    }
    return correr(ficha("X", val, fund), alts)


def textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from textos(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from textos(v)


# ── 1. sin competidores suficientes ───────────────────────────────────────

def test_sin_alternativas_no_hay_conclusion_y_el_mensaje_dice_que_falta():
    r = correr(ficha("X"), {})
    assert r.estado == "insuficiente"
    assert r.faltan == ce.MIN_ALTERNATIVAS == 2
    assert r.conclusion is None and r.ranking == [] and r.tabla is None
    assert "faltan 2" in r.mensaje and "buscador" in r.mensaje


def test_una_sola_alternativa_muestra_la_tabla_pero_no_concluye():
    r = correr(ficha("X"), {"A": (ficha("A", 0.8), {"en_grupo": True})})
    assert r.estado == "insuficiente" and r.faltan == 1
    assert r.tabla is not None and [c.ticker_base for c in r.tabla.columnas] == ["X", "A"]
    assert r.conclusion is None and r.ranking == []


def test_las_sugeridas_se_ofrecen_cuando_faltan_alternativas():
    alts = {"A": (ficha("A"), {"en_grupo": True}), "S": (ficha("S"), {})}
    r = correr(ficha("X"), alts)
    assert r.estado == "insuficiente"
    assert [a.ticker_base for a in r.sugeridas] == ["S"] and r.sugeridas[0].origen == "sugerida"
    assert "sugeridas" in r.mensaje


def test_el_instrumento_sin_datos_no_inventa_nada():
    obj = perfil("X")
    r = ce.comparar(obj, [perfil("A")], fichero({"A": ficha("A")}), None, hoy=HOY)
    assert r.estado == "sin_datos" and r.tabla is None and r.conclusion is None


def test_el_instrumento_con_muy_pocos_datos_no_se_compara():
    pobre = ficha("X", vals={"pe": 20.0, "pb": 3.0})
    r = correr(pobre, {"A": (ficha("A"), {"en_grupo": True})})
    assert r.estado == "sin_datos" and "muy poco" in r.mensaje


# ── 2. CEDEAR vs. subyacente ──────────────────────────────────────────────

def test_cedear_y_subyacente_son_el_mismo_emisor_y_no_cuentan():
    alts = {
        "AAPLD": (ficha("AAPLD"), {"simbolo": "AAPL"}),       # misma exposición, otro ticker
        "A": (ficha("A"), {"en_grupo": True}),
    }
    r = correr(ficha("X"), alts, con=["AAPLD", "A"], simbolo="AAPL")
    assert [a.ticker_base for a in r.alternativas] == ["A"]
    rech = next(x for x in r.rechazadas if x.ticker_base == "AAPLD")
    assert rech.nivel == ce.NO_COMPARABLE and "mismo emisor" in rech.motivo
    assert r.estado == "insuficiente"       # no suma al mínimo


def test_dos_tickers_del_mismo_emisor_elegidos_juntos_cuentan_una_vez():
    alts = {"PBR": (ficha("PBR"), {"simbolo": "PBR"}), "PETR3": (ficha("PETR3"), {"simbolo": "PBR"}),
            "A": (ficha("A"), {})}
    r = correr(ficha("X"), alts, con=["PBR", "PETR3", "A"])
    assert [a.ticker_base for a in r.alternativas] == ["PBR", "A"]
    assert any(x.ticker_base == "PETR3" and "mismo emisor" in x.motivo for x in r.rechazadas)


# ── 3. ETF vs. empresa ────────────────────────────────────────────────────

def _ficha_etf(base, gastos=0.001, pb=3.0, div=0.015, r12=0.1):
    return ve.Ficha(base, {"pb": pb, "div_yield": div, "gastos": gastos, "rend_3m": 0.02, "rend_6m": 0.05, "rend_12m": r12},
                    es_etf=True, fecha_dato=RECIENTE)


def test_un_etf_no_se_compara_con_una_empresa_individual():
    r = correr(_ficha_etf("X"), {"A": (ficha("A"), {})}, con=["A"], etf=True, categoria="Large Blend", industria=None)
    assert any(x.ticker_base == "A" and "ETF" in x.motivo for x in r.rechazadas)
    assert r.alternativas == []


def test_una_empresa_tampoco_se_compara_con_un_etf():
    alts = {"E": (_ficha_etf("E"), {"etf": True, "categoria": "Large Blend", "industria": None})}
    r = correr(ficha("X"), alts, con=["E"])
    assert r.alternativas == [] and r.rechazadas[0].nivel == ce.NO_COMPARABLE


def test_etf_contra_etf_se_compara_por_costo_y_valuacion():
    kw = {"etf": True, "categoria": "Large Blend", "industria": None, "en_grupo": True}
    alts = {"E1": (_ficha_etf("E1", gastos=0.0003), kw), "E2": (_ficha_etf("E2", gastos=0.0009), kw),
            "E3": (_ficha_etf("E3", gastos=0.002), kw)}
    r = correr(_ficha_etf("X", gastos=0.0006), alts, etf=True, categoria="Large Blend", industria=None)
    assert r.estado == "ok" and r.modelo == ce.MODELO_ETF
    assert r.conclusion.regla_aplicada == "ETF"
    assert [d.clave for d in r.ranking] == ["valuacion"]        # no hay calidad ni crecimiento de un fondo
    assert any("composición de tenencias" in f.texto for f in r.conclusion.frases)
    assert {f.clave for f in r.tabla.filas} <= set(ce.METRICAS_POR_MODELO[ce.MODELO_ETF])
    assert any("ETF" in n.motivo for n in r.tabla.no_aplican)


# ── 4. monedas distintas ──────────────────────────────────────────────────

def test_ratios_recalculados_por_moneda_bajan_la_comparabilidad_y_se_marcan():
    vals = valores()
    vals.update({"forward_pe": None, "pb": None})
    otra_moneda = ficha("M", vals=vals, recalculadas=["pe", "ps"], descartadas_moneda=["forward_pe", "pb"])
    alts = {"M": (otra_moneda, {"en_grupo": True}), "A": (ficha("A"), {"en_grupo": True}), "B": (ficha("B"), {"en_grupo": True})}
    r = correr(ficha("X"), alts)
    m = next(a for a in r.alternativas if a.ticker_base == "M")
    assert m.nivel == ce.MEDIA and any("queda en media" in n for n in m.notas)    # sería alta
    assert next(a for a in r.alternativas if a.ticker_base == "A").nivel == ce.ALTA
    fila = next(f for f in r.tabla.filas if f.clave == "forward_pe")
    assert fila.celdas["M"].estado == "moneda" and fila.celdas["M"].valor is None
    assert next(f for f in r.tabla.filas if f.clave == "pe").celdas["M"].origen == "calculado"
    assert next(c for c in r.tabla.columnas if c.ticker_base == "M").aviso_moneda


def test_el_rendimiento_en_moneda_local_no_se_compara_con_el_de_usd():
    local = ficha("L", momentum_aproximado=True)
    alts = {"L": (local, {"en_grupo": True}), "A": (ficha("A"), {"en_grupo": True}), "B": (ficha("B"), {"en_grupo": True})}
    r = correr(ficha("X"), alts)
    fila = next(f for f in r.tabla.filas if f.clave == "rend_12m")
    assert fila.celdas["L"].estado == "moneda"


# ── 5. modificar el conjunto de competidores ──────────────────────────────

def _grupo_de_cinco():
    return {b: (ficha(b, 0.7 + 0.1 * i), {"en_grupo": True}) for i, b in enumerate("ABCDE")}


def test_sin_elegir_se_usa_el_grupo_hasta_el_tope():
    r = correr(ficha("X"), _grupo_de_cinco())
    assert len(r.alternativas) == ce.N_DEFAULT and all(a.origen == "grupo" for a in r.alternativas)
    assert len(r.sugeridas) == 1       # la quinta del grupo queda para sumar con un toque


def test_elegir_otro_conjunto_cambia_el_resultado():
    alts = _grupo_de_cinco()
    por_defecto = correr(ficha("X"), alts)
    elegido = correr(ficha("X"), alts, con=["D", "E"])
    assert [a.ticker_base for a in elegido.alternativas] == ["D", "E"]
    assert {a.ticker_base for a in elegido.alternativas} != {a.ticker_base for a in por_defecto.alternativas}
    assert all(a.origen == "elegida" for a in elegido.alternativas)
    assert [c.ticker_base for c in elegido.tabla.columnas] == ["X", "D", "E"]
    assert asdict(elegido) != asdict(por_defecto)


def test_un_par_quitado_a_mano_no_se_sugiere_pero_se_puede_elegir():
    alts = _grupo_de_cinco()
    alts["E"] = (alts["E"][0], {"en_grupo": False, "quitado": True})
    r = correr(ficha("X"), alts)
    assert "E" not in [a.ticker_base for a in r.sugeridas + r.alternativas]
    r2 = correr(ficha("X"), alts, con=["A", "B", "E"])
    e = next(a for a in r2.alternativas if a.ticker_base == "E")
    assert any("quitaste" in n for n in e.notas)


def test_el_tope_de_alternativas_elegidas():
    alts = {f"T{i}": (ficha(f"T{i}", 0.5 + 0.1 * i), {}) for i in range(10)}
    r = correr(ficha("X"), alts, con=list(alts))
    assert len(r.alternativas) == ce.MAX_ALTERNATIVAS


# ── 6. misma industria de Yahoo no alcanza ────────────────────────────────

def test_misma_industria_con_tamano_y_region_muy_distintos_es_comparabilidad_baja():
    lejana = {"L": (ficha("L"), {"tamano": 1e8, "region": "Argentina"})}      # 1000 veces más chica, otra región
    r = correr(ficha("X"), lejana, con=["L"])
    a = r.alternativas[0]
    assert a.nivel == ce.BAJA and not a.en_ranking
    assert "Misma industria" in a.resumen and "tamaño muy distinto" in a.resumen
    assert r.estado == "insuficiente" and "comparabilidad baja" in r.mensaje


def test_una_alternativa_de_comparabilidad_baja_no_entra_al_ranking_ni_a_la_conclusion():
    alts = {"A": (ficha("A", 0.8), {"en_grupo": True}), "B": (ficha("B", 1.2), {"en_grupo": True}),
            "L": (ficha("L", 0.5), {"tamano": 1e8, "region": "Argentina"})}
    r = correr(ficha("X"), alts, con=["A", "B", "L"])
    assert r.estado == "ok"
    assert {p.ticker_base for p in r.ranking[0].puestos} == {"X", "A", "B"}
    par_l = next(p for p in r.pares if p.ticker_base == "L")
    assert par_l.orientativa and par_l.domina is None
    assert next(c for c in r.tabla.columnas if c.ticker_base == "L").en_ranking is False


def test_el_par_agregado_a_mano_sube_a_media_con_una_nota():
    lejana = {"L": (ficha("L"), {"tamano": 1e8, "region": "Argentina", "a_mano": True, "en_grupo": True})}
    r = correr(ficha("X"), lejana, con=["L"])
    assert r.alternativas[0].nivel == ce.MEDIA and "agregaste" in r.alternativas[0].notas[0]


def test_alta_requiere_industria_tamano_y_region():
    r = correr(ficha("X"), {"A": (ficha("A"), {})}, con=["A"])
    a = r.alternativas[0]
    assert a.nivel == ce.ALTA and "comparabilidad alta" in a.resumen
    assert {c.clave for c in a.criterios} >= {"emisor", "tipo", "modelo", "industria", "tamano", "region", "datos", "periodo", "moneda"}


# ── 7. modelo de negocio y métricas por sector ────────────────────────────

def test_un_banco_no_se_compara_con_una_industrial():
    r = correr(ficha("X", sector="Financiero"), {"A": (ficha("A"), {})}, con=["A"], sector="Financiero")
    assert r.alternativas == [] and "Modelo de negocio distinto" in r.rechazadas[0].motivo


def _banco(base, val=1.0, fund=1.0):
    v = valores(val, fund)
    for k in ("ev_ebitda", "ps", "fcf_yield", "margen_bruto", "deuda_patrimonio"):
        v[k] = None
    return ficha(base, vals=v, sector="Financiero")


def test_la_tabla_de_un_banco_no_trae_lo_que_no_aplica_y_dice_por_que():
    alts = {b: (_banco(b, 0.8 + 0.1 * i), {"sector": "Financiero", "en_grupo": True}) for i, b in enumerate("ABC")}
    r = correr(_banco("X"), alts, sector="Financiero")
    claves = {f.clave for f in r.tabla.filas}
    assert r.modelo == ce.MODELO_FINANCIERO
    assert claves <= set(ce.METRICAS_POR_MODELO[ce.MODELO_FINANCIERO])
    assert "ev_ebitda" not in claves and "deuda_patrimonio" not in claves and "roe" in claves
    nombres = {n.nombre: n.motivo for n in r.tabla.no_aplican}
    assert "EV/EBITDA" in nombres and "deuda" in nombres["EV/EBITDA"]
    assert "Margen bruto" in nombres and "Deuda/Patrimonio" in nombres


def test_sin_ganancias_el_pe_no_aplica_y_no_cuenta_como_faltante():
    sin = ficha("X", vals=valores(pe=None, forward_pe=None, crec_ganancias=None, crec_esperado=None), sin_ganancias=True)
    alts = {b: (ficha(b, 0.8 + 0.1 * i), {"en_grupo": True}) for i, b in enumerate("ABC")}
    r = correr(sin, alts)
    pe_ = next(f for f in r.tabla.filas if f.clave == "pe")
    assert pe_.celdas["X"].estado == "sin_ganancias" and pe_.celdas["A"].estado == "dato"
    assert any("ganancias" in n.motivo for n in r.tabla.no_aplican)


def test_las_filas_vacias_no_se_muestran_pero_se_nombran():
    vals = valores(roe=None)
    alts = {b: (ficha(b, vals={**valores(0.8 + 0.1 * i), "roe": None}), {"en_grupo": True}) for i, b in enumerate("ABC")}
    r = correr(ficha("X", vals=vals), alts)
    assert "ROE" in r.tabla.sin_dato_en_ninguna and "roe" not in {f.clave for f in r.tabla.filas}


def test_cada_fila_declara_unidad_periodo_y_origen():
    r = tres(1.0, 1.0)
    for f in r.tabla.filas:
        assert f.unidad in ("veces (x)", "%") and f.periodo
        assert all(c.origen in ("observado", "estimado", "calculado") for c in f.celdas.values())
    assert next(f for f in r.tabla.filas if f.clave == "forward_pe").celdas["X"].origen == "estimado"
    assert next(f for f in r.tabla.filas if f.clave == "fcf_yield").celdas["X"].origen == "calculado"
    x = r.tabla.columnas[0]
    assert x.es_objetivo and x.fecha_dato == RECIENTE and x.periodo_contable == BALANCE


def test_el_mejor_y_el_peor_de_cada_fila_respetan_el_sentido_de_la_metrica():
    r = tres(1.0, 1.0)
    pe_ = next(f for f in r.tabla.filas if f.clave == "pe")
    assert pe_.mejor == "A" and pe_.peor == "C"                         # el múltiplo más bajo es el más barato
    roe = next(f for f in r.tabla.filas if f.clave == "roe")
    assert roe.mejor == "A" and roe.peor == "C"                         # fund 1.2 es el mejor retorno


# ── 8. cobertura insuficiente ─────────────────────────────────────────────

def test_una_alternativa_con_pocos_datos_se_descarta_sin_tratarla_como_mala():
    pobre = ficha("P", vals={"pe": 10.0, "pb": 1.0})
    alts = {"P": (pobre, {"en_grupo": True}), "A": (ficha("A"), {"en_grupo": True})}
    r = correr(ficha("X"), alts)
    rech = next(x for x in r.rechazadas if x.ticker_base == "P")
    assert rech.nivel == ce.NO_COMPARABLE and "Datos insuficientes" in rech.motivo
    assert [a.ticker_base for a in r.alternativas] == ["A"]


def test_un_ticker_pedido_que_no_esta_en_el_universo_se_informa():
    r = correr(ficha("X"), {"A": (ficha("A"), {})}, con=["ZZZ", "A"])
    assert any(x.ticker_base == "ZZZ" and "próxima corrida" in x.motivo for x in r.rechazadas)


def test_una_alternativa_sin_fundamentales_todavia_se_rechaza():
    r = correr(ficha("X"), {"N": (None, {"en_grupo": True})}, con=["N"])
    assert r.rechazadas[0].nivel == ce.NO_COMPARABLE and "fundamentales" in r.rechazadas[0].motivo


# ── 9. ranking y reglas de la conclusión ──────────────────────────────────

def _puestos(r, dim):
    return {p.ticker_base: p.posicion for p in next(d for d in r.ranking if d.clave == dim).puestos}


def test_el_ranking_ordena_el_grupo_por_dimension():
    r = tres(1.5, 1.5)           # la más cara del grupo y la de mejores fundamentos
    assert r.estado == "ok"
    assert _puestos(r, "valuacion") == {"A": 1, "B": 2, "C": 3, "X": 4}
    assert _puestos(r, "calidad")["X"] == 1 and _puestos(r, "calidad")["C"] == 4
    val = next(d for d in r.ranking if d.clave == "valuacion")
    assert val.posicion_objetivo == 4 and val.de == 4 and val.tercio == ce.ABAJO
    assert "3 miembros" in val.regla


def test_r1_prima_con_respaldo():
    c = tres(1.5, 1.5).conclusion
    assert c.regla_aplicada == "R1" and "prima" in c.titulo.lower()
    assert {f.dimension for f in c.mayor} >= {"calidad"} and not c.menor
    assert any("múltiplo mayor" in f.texto for f in c.frases)


def test_r2_prima_sin_respaldo():
    c = tres(1.5, 0.5).conclusion
    assert c.regla_aplicada == "R2" and "no respaldan" in c.titulo
    assert c.menor and not c.mayor
    assert any("más difícil de justificar" in f.texto for f in c.frases)


def test_r3_descuento_con_razones_que_lo_explican():
    c = tres(0.5, 0.5).conclusion
    assert c.regla_aplicada == "R3" and "podrían explicarlo" in c.titulo
    assert any(f.texto.startswith("Posible explicación") for f in c.frases)


def test_r4_descuento_sin_debilidades():
    c = tres(0.5, 1.5).conclusion
    assert c.regla_aplicada == "R4"
    assert any("no aparece una debilidad" in f.texto for f in c.frases)


def test_r5_en_linea_con_el_grupo():
    r = correr(ficha("X", 1.0, 1.0), {
        "A": (ficha("A", 0.8, 1.2), {"en_grupo": True}),
        "B": (ficha("B", 1.2, 0.8), {"en_grupo": True}),
    })
    c = r.conclusion
    assert c.regla_aplicada == "R5" and "en línea" in c.titulo
    assert next(d for d in r.ranking if d.clave == "valuacion").tercio == ce.MEDIO


def test_con_tres_miembros_el_ranking_ya_existe_pero_se_avisa_que_es_grueso():
    r = correr(ficha("X", 1.0, 1.0), {"A": (ficha("A", 0.8, 1.2), {"en_grupo": True}),
                                      "B": (ficha("B", 1.2, 0.8), {"en_grupo": True})})
    assert r.conclusion.firmeza in ("media", "baja")
    assert any("sólo 3 instrumentos" in x for x in r.conclusion.firmeza_razones)


def test_la_firmeza_sube_con_mas_miembros_y_datos_frescos():
    alts = {b: (ficha(b, 0.7 + 0.1 * i, 1.3 - 0.1 * i), {"en_grupo": True}) for i, b in enumerate("ABCD")}
    r = correr(ficha("X"), alts)
    assert len(r.alternativas) == 4 and r.conclusion.firmeza == "alta"


def test_una_alerta_propia_cuenta_como_debilidad_aunque_el_grupo_este_peor():
    pierde = valores(0.5, 1.0, margen_neto=-0.05)
    alts = {b: (ficha(b, 0.8 + 0.2 * i, 0.4, ), {"en_grupo": True}) for i, b in enumerate("ABC")}
    r = correr(ficha("X", vals=pierde), alts)
    assert r.conclusion.regla_aplicada == "R3"          # barata, pero pierde plata


def test_dominancia_una_alternativa_mas_barata_y_sin_desventajas():
    par = ce.comparar_par(ficha("X", 1.5, 1.0), ficha("A", 0.6, 1.0), "A", orientativa=False)
    assert par.domina == "alternativa" and "más barata" in par.texto_dominancia
    assert par.veredictos["valuacion"] == "peor"


def test_dominancia_del_objetivo():
    par = ce.comparar_par(ficha("X", 0.6, 1.0), ficha("A", 1.5, 1.0), "A", orientativa=False)
    assert par.domina == "objetivo"


def test_sin_dominancia_si_el_objetivo_compensa_lo_caro_con_mejores_fundamentos():
    par = ce.comparar_par(ficha("X", 1.5, 2.0), ficha("A", 0.6, 1.0), "A", orientativa=False)
    assert par.veredictos["valuacion"] == "peor" and par.veredictos["calidad"] == "mejor"
    assert par.domina is None


def test_la_alternativa_mas_barata_y_mejor_tambien_domina():
    par = ce.comparar_par(ficha("X", 1.5, 1.0), ficha("A", 0.6, 2.0), "A", orientativa=False)
    assert par.veredictos["calidad"] == "peor" and par.domina == "alternativa"


def test_ventajas_y_desventajas_citan_valores_y_regla():
    par = ce.comparar_par(ficha("X", 1.0, 1.5), ficha("A", 1.0, 1.0), "A", orientativa=False)
    cal = next(l for l in par.lineas if l.dimension == "calidad")
    assert cal.veredicto == "mejor" and "margen operativo (30,0% vs. 20,0%)" in cal.texto
    assert "15%" in cal.regla and cal.metricas


# ── 10. determinismo, trazabilidad y lenguaje ─────────────────────────────

def test_misma_entrada_misma_salida():
    assert asdict(tres(1.5, 0.5)) == asdict(tres(1.5, 0.5))


@pytest.mark.parametrize("val,fund", [(1.5, 1.5), (1.5, 0.5), (0.5, 0.5), (0.5, 1.5)])
def test_cada_frase_tiene_regla_y_metricas_validas(val, fund):
    c = tres(val, fund).conclusion
    for f in c.frases + c.mayor + c.menor + c.destacadas:
        assert f.regla and f.origen in ("observado", "estimado", "calculado") and f.tono
        assert set(f.metricas) <= set(ve.METRICA_POR_CLAVE)
    assert c.salvedad and c.limites and c.regla


@pytest.mark.parametrize("val,fund", [(1.5, 1.5), (1.5, 0.5), (0.5, 0.5), (0.5, 1.5), (1.0, 1.0)])
def test_nunca_dice_compra_ni_venta(val, fund):
    r = tres(val, fund)
    prohibidas = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)
    for t in textos(asdict(r.conclusion)):
        assert not prohibidas.search(t), t
    for t in textos([asdict(p) for p in r.pares]):
        assert not prohibidas.search(t), t


def test_la_conclusion_aclara_lo_que_no_cubre():
    c = tres(1.0, 1.0).conclusion
    assert any("valor razonable" in x for x in c.limites)
    assert any("historia contable" in x for x in c.limites)
    assert "no garantiza" in c.salvedad
