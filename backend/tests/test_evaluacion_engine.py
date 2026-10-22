"""Motor de evaluación del Centro de Decisiones (`evaluacion_engine`): puntajes, faltantes, banderas, orden y conclusión."""
import re
from datetime import date, timedelta

import pytest

from app.services import evaluacion_engine as ev

HOY = date(2026, 10, 1)
PREFS = {"horizonte": "largo", "objetivo": "crecimiento", "enfoque": "combinado", "tolerancia": None,
         "moneda": "USD", "pesos": None}
PROHIBIDAS = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)


def _dim(clave, nivel="neutro", percentil=None, estado="Media"):
    return {"clave": clave, "nombre": clave, "estado": estado, "nivel": nivel, "resumen": f"{clave} {estado}",
            "regla": f"regla {clave}", "razones": [], "faltantes": [], "percentil": percentil, "votos": []}


def _diag(val=60, cal=70, cre=55, sol=65, confianza="alta", sol_nivel="bien"):
    return {"version_reglas": 2, "confianza": confianza, "dimensiones": [
        _dim("valuacion", "neutro", val, "En línea"), _dim("calidad", "bien", cal, "Alta"),
        _dim("crecimiento", "neutro", cre), _dim("solidez", sol_nivel, sol, "Sólida"),
        _dim("confianza", "bien", None, "Alta"),
    ]}


def _tecnico(tend="alcista", mom="neutral", fr="mejor"):
    return {"fecha": HOY, "ultimo_cierre": 100.0,
            "tendencia": {"estado": tend, "sma": 95.0, "periodo_sma": 50, "distancia_pct": 5.0, "pendiente_pct": 1.0, "ruedas_pendiente": 10},
            "momentum": {"estado": mom, "rsi": 55.0, "periodo_rsi": 14},
            "fuerza_relativa": {"estado": fr, "retorno_pct": 10.0, "retorno_benchmark_pct": 5.0, "diferencia_puntos": 5.0, "ruedas": 63}}


def _ins(**kw):
    base = dict(ticker="KO", diagnostico=_diag(), tecnico=_tecnico(),
                riesgo={"volatilidad": 0.20, "caida_maxima": -0.25, "beta": 0.8, "semanas": 260, "fecha": HOY, "moneda_serie": "USD"},
                encaje={"sin_cartera": False, "observaciones": [], "monto_ref_texto": "100 USD"},
                metricas={"div_yield": 0.03, "crec_ingresos": 0.05}, extra={"payout": 0.6},
                fecha_dato=HOY, fecha_precio=HOY, moneda_instrumento="ARS", sigue_dolar=True)
    base.update(kw)
    return ev.Insumos(**base)


def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _textos(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textos(v)


def _d(res, clave):
    return next(d for d in res["dimensiones"] if d["clave"] == clave)


def test_datos_completos_dan_cinco_dimensiones_y_un_orden():
    res = ev.evaluar(_ins(), PREFS, HOY)
    assert res["version_reglas"] == ev.VERSION_REGLAS
    assert [d["clave"] for d in res["dimensiones"]] == list(ev.DIMENSIONES)
    assert _d(res, "fundamentales")["puntaje"] == pytest.approx((70 + 55 + 65) / 3, abs=0.1)
    assert _d(res, "valoracion")["puntaje"] == 60
    assert _d(res, "riesgo")["puntaje"] == pytest.approx((75 + 75 + 70) / 3, abs=0.1)
    assert _d(res, "tecnico")["puntaje"] == pytest.approx((70 + 55 + 65) / 3, abs=0.1)
    assert _d(res, "encaje")["puntaje"] == 60
    assert res["orden"]["puntaje"] is not None and not res["orden"]["incompleto"]
    assert res["orden"]["cobertura"] == 1.0
    assert res["banderas"] == []
    assert res["orden"]["contribuciones"] and res["orden"]["regla"]


def test_faltantes_no_son_cero_y_el_orden_queda_incompleto():
    res = ev.evaluar(_ins(diagnostico=None, tecnico=None, riesgo=None, valor_razonable=None), PREFS, HOY)
    for clave in ("fundamentales", "valoracion", "riesgo", "tecnico"):
        assert _d(res, clave)["puntaje"] is None and _d(res, clave)["estado"] == "sin_datos"
    assert res["orden"]["puntaje"] is None and res["orden"]["incompleto"]
    assert "faltan datos" in res["orden"]["motivo"]


def test_un_faltante_baja_la_cobertura_pero_no_el_puntaje():
    completo = ev.evaluar(_ins(), PREFS, HOY)
    sin_tec = ev.evaluar(_ins(tecnico=None), PREFS, HOY)
    assert sin_tec["orden"]["cobertura"] == pytest.approx(0.9)
    # sin el técnico el orden es el promedio de las otras dimensiones (el peso no se reparte como 0)
    otros = {d["clave"]: d["puntaje"] for d in completo["dimensiones"] if d["clave"] != "tecnico"}
    pesos = ev.PESOS["combinado"]["largo"]
    esperado = sum(otros[k] * pesos[k] for k in otros) / sum(pesos[k] for k in otros)
    assert sin_tec["orden"]["puntaje"] == pytest.approx(esperado, abs=0.1)


def test_etf_fundamentales_no_aplica_y_no_cuenta_como_faltante():
    diag = {"version_reglas": 2, "confianza": "alta", "dimensiones": [
        _dim("valuacion", "neutro", 50), _dim("calidad", "no_aplica"), _dim("crecimiento", "no_aplica"),
        _dim("solidez", "no_aplica"), _dim("confianza", "bien")]}
    res = ev.evaluar(_ins(es_etf=True, diagnostico=diag), PREFS, HOY)
    assert _d(res, "fundamentales")["estado"] == "no_aplica"
    assert res["orden"]["cobertura"] == 1.0 and res["orden"]["puntaje"] is not None


def test_cotizacion_y_dato_viejos_levantan_banderas():
    res = ev.evaluar(_ins(fecha_precio=HOY - timedelta(days=20), fecha_dato=HOY - timedelta(days=40)), PREFS, HOY)
    claves = {b["clave"] for b in res["banderas"]}
    assert {"precio_viejo", "dato_viejo"} <= claves


def test_banderas_criticas_aparecen_aunque_el_orden_sea_alto():
    res = ev.evaluar(_ins(diagnostico=_diag(sol_nivel="riesgo"), sin_ganancias=True), PREFS, HOY)
    assert res["orden"]["puntaje"] is not None
    assert {b["clave"] for b in res["banderas"] if b["severidad"] == "alta"} >= {"solidez", "sin_ganancias"}


def test_valor_razonable_ajusta_sin_votar_dos_veces():
    vr = {"estado": "ok", "lectura": "por_debajo", "lectura_texto": "Debajo del rango", "regla_lectura": "r"}
    con = ev.evaluar(_ins(valor_razonable=vr), PREFS, HOY)
    sin = ev.evaluar(_ins(), PREFS, HOY)
    assert _d(con, "valoracion")["puntaje"] == _d(sin, "valoracion")["puntaje"] + ev.AJUSTE_VALOR_RAZONABLE


def test_objetivo_ingresos_usa_el_dividendo_en_fraccion():
    p = {**PREFS, "objetivo": "ingresos"}
    alto = ev.evaluar(_ins(metricas={"div_yield": 0.03}), p, HOY)
    bajo = ev.evaluar(_ins(metricas={"div_yield": 0.005}), p, HOY)
    assert _d(alto, "encaje")["puntaje"] == 75 and _d(bajo, "encaje")["puntaje"] == 45


def test_pesos_dependen_del_enfoque_y_la_tolerancia():
    assert ev.pesos_para({**PREFS, "enfoque": "tecnico", "horizonte": "corto"})["tecnico"] == 50
    assert ev.pesos_para({**PREFS, "tolerancia": "baja"})["riesgo"] == pytest.approx(30.0)
    with pytest.raises(ValueError):
        ev.normalizar_pesos({d: 0 for d in ev.DIMENSIONES})
    with pytest.raises(ValueError):
        ev.normalizar_pesos({"fundamentales": 120})
    assert sum(ev.normalizar_pesos({"fundamentales": 50, "riesgo": 50}).values()) == 100


def test_tolerancia_baja_con_riesgo_alto_es_bandera_critica():
    r = {"volatilidad": 0.6, "caida_maxima": -0.7, "beta": 2.0, "semanas": 260, "fecha": HOY}
    res = ev.evaluar(_ins(riesgo=r), {**PREFS, "tolerancia": "baja"}, HOY)
    assert any(b["clave"] == "tolerancia" and b["severidad"] == "alta" for b in res["banderas"])


def _eval(ticker, puntaje, banderas=()):
    return {"ticker": ticker, "dimensiones": [
        {"clave": d, "nombre": d, "puntaje": puntaje, "estado": "evaluada", "factores": [
            {"texto": f"{d} ok", "efecto": 1.0, "regla": "", "origen": "calculado"}], "faltantes": []}
        for d in ev.DIMENSIONES],
        "banderas": list(banderas), "orden": {"puntaje": puntaje, "incompleto": False, "motivo": None, "cobertura": 1.0}}


def test_conclusion_alternativa_mas_atractiva_exige_diferencia_robusta():
    obj, alt = _eval("GOOGL", 55), _eval("MSFT", 70)
    c = ev.concluir(obj, [alt], {"fundamental": "MSFT", "tecnico": "MSFT", "combinado": "MSFT"}, "media", [])
    assert c["tipo"] == ev.MAS_ATRACTIVA and c["ganador"] == "MSFT" and c["robusta"]
    # si con otro enfoque gana otro, depende de supuestos: no hay ganador
    c2 = ev.concluir(obj, [alt], {"fundamental": "MSFT", "tecnico": "GOOGL", "combinado": "MSFT"}, "media", [])
    assert c2["tipo"] != ev.MAS_ATRACTIVA and c2["ganador"] is None
    assert any("depende de supuestos" in r for r in c2["respuestas"]["incertidumbre_razones"])


def test_conclusion_ninguna_superior_con_diferencia_chica():
    c = ev.concluir(_eval("GOOGL", 55), [_eval("MSFT", 60)], {e: "MSFT" for e in ev.ENFOQUES}, "alta", [])
    assert c["tipo"] == ev.NINGUNA_SUPERIOR and c["ganador"] is None


def test_conclusion_datos_insuficientes_y_riesgo_elevado():
    inc = _eval("X", 50)
    inc["orden"] = {"puntaje": None, "incompleto": True, "motivo": "faltan datos", "cobertura": 0.3}
    assert ev.concluir(inc, [], {}, None, [])["tipo"] == ev.DATOS_INSUFICIENTES
    alta = {"clave": "solidez", "texto": "deuda", "regla": "", "severidad": "alta"}
    c = ev.concluir(_eval("X", 80, [alta]), [], {}, None, [])
    assert c["tipo"] == ev.RIESGO_ELEVADO_T and c["respuestas"]["siguiente_paso"] == "descartar_por_ahora"
    assert any("Bandera" in t for t in c["evidencia_en_contra"])


def test_conclusion_siempre_trae_evidencia_en_contra_y_preguntas():
    c = ev.concluir(_eval("X", 65), [], {}, None, [])
    assert c["evidencia_en_contra"] and c["preguntas"] and c["respuestas"]["invalidaria"]


def test_ningun_texto_indica_operar():
    res = ev.evaluar(_ins(diagnostico=_diag(sol_nivel="riesgo"), sin_ganancias=True,
                          fecha_precio=HOY - timedelta(days=30)), {**PREFS, "objetivo": "ingresos"}, HOY)
    c = ev.concluir(res, [_eval("MSFT", 90)], {e: "MSFT" for e in ev.ENFOQUES}, "alta", ["fechas distintas"])
    textos = list(_textos(res)) + list(_textos(c)) + [ev.REGLA_CONCLUSION, ev.REGLA_ORDEN]
    malas = [t for t in textos if PROHIBIDAS.search(t)]
    assert malas == []
