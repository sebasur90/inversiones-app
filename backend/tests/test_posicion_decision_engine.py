"""Evaluación de una posición existente: el resultado (ganancia o pérdida) nunca es evidencia."""
import re

from app.services import evaluacion_engine as ev
from app.services import posicion_decision_engine as pde

PROHIBIDAS = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)


def _eval(fund=65, val=55, riesgo=60, banderas=()):
    dims = []
    for clave, p in ((ev.FUNDAMENTALES, fund), (ev.VALORACION, val), (ev.RIESGO, riesgo), (ev.TECNICO, 50), (ev.ENCAJE, 60)):
        dims.append({"clave": clave, "nombre": ev.NOMBRE[clave], "puntaje": p, "estado": "evaluada", "factores": [], "faltantes": []})
    return {"dimensiones": dims, "banderas": list(banderas), "orden": {"puntaje": 60}}


def _sim(peso_antes, peso_despues, niveles=()):
    return {"ejes": [{"eje": "Emisor", "items": [{"etiqueta": "KO", "antes_pct": peso_antes, "despues_pct": peso_despues}]}],
            "observaciones": [{"nivel": n, "texto": "t", "regla": "r"} for n in niveles], "liquidez_usd": 0.0,
            "comision_estimada_usd": 1.5, "ventas": []}


SIMS = {pde.AUMENTAR: _sim(10, 12), pde.REDUCIR: _sim(10, 5), pde.SALIR: _sim(10, 0)}
SIN_TESIS = pde.comparar_tesis(None, _eval())


def _op(ops, clave):
    return next(o for o in ops if o["clave"] == clave)


def test_cuatro_opciones_con_evidencia_cambios_y_condiciones():
    ops = pde.evaluar_opciones(_eval(), "KO", 10.0, (20.0, 30.0), SIMS, SIN_TESIS, None, [])
    assert [o["clave"] for o in ops] == list(pde.OPCIONES)
    for o in ops:
        assert o["condiciones"] and o["invalidaria"] and o["balance"] in ("mas_a_favor", "mas_en_contra", "mixta")
    assert _op(ops, pde.REDUCIR)["cambio_en_cartera"]["peso_despues_pct"] == 5
    assert _op(ops, pde.SALIR)["cambio_en_cartera"]["peso_despues_pct"] == 0


def test_el_motor_no_recibe_ni_usa_el_resultado_de_la_posicion():
    # La firma no tiene ganancia/pérdida: con los mismos fundamentos, las opciones son idénticas
    # sea cual sea el precio de compra. El adaptador no le pasa el P&L.
    import inspect
    params = set(inspect.signature(pde.evaluar_opciones).parameters)
    assert not params & {"pnl", "resultado", "ganancia", "perdida", "precio_promedio", "rendimiento"}
    textos = [t for o in pde.evaluar_opciones(_eval(), "KO", 10.0, (20.0, 30.0), SIMS, SIN_TESIS, None, [])
              for t in o["a_favor"] + o["en_contra"]]
    assert not any(re.search(r"p[ée]rdida|ganancia|precio de compra", t, re.I) for t in textos)


def test_salir_se_apoya_en_banderas_y_alternativa_no_en_el_precio():
    alta = {"clave": "solidez", "texto": "deuda alta", "regla": "", "severidad": "alta"}
    ops = pde.evaluar_opciones(_eval(fund=30, banderas=[alta]), "KO", 10.0, (20.0, 30.0), SIMS, SIN_TESIS, "MSFT", [])
    salir = _op(ops, pde.SALIR)
    assert any("deuda alta" in t for t in salir["a_favor"]) and any("MSFT" in t for t in salir["a_favor"])
    assert salir["balance"] == "mas_a_favor"


def test_concentracion_sostiene_reducir():
    ops = pde.evaluar_opciones(_eval(), "KO", 32.0, (20.0, 30.0), SIMS, SIN_TESIS, None, [])
    assert any("Concentración" in t for t in _op(ops, pde.REDUCIR)["a_favor"])
    assert any("revisar" in t for t in _op(ops, pde.MANTENER)["en_contra"])


def test_tesis_deteriorada_se_detecta_contra_la_foto_guardada():
    tesis = _eval(fund=70)
    cmp_ = pde.comparar_tesis(tesis, _eval(fund=50))
    assert cmp_["existe"] and cmp_["deteriorada"]
    assert any(c["dimension"] == ev.FUNDAMENTALES and c["delta"] == -20 for c in cmp_["cambios"])
    assert not pde.comparar_tesis(tesis, _eval(fund=65))["deteriorada"]


def test_textos_no_indican_operar():
    alta = {"clave": "solidez", "texto": "deuda alta", "regla": "", "severidad": "alta"}
    ops = pde.evaluar_opciones(_eval(val=20, banderas=[alta]), "KO", 35.0, (20.0, 30.0),
                               {k: _sim(35, 40, ("revisar",)) for k in SIMS}, pde.comparar_tesis(_eval(fund=90), _eval()),
                               "MSFT", ["cierre bajo 80"])
    textos = [pde.NOTA_RESULTADO, pde.REGLA_OPCIONES] + [
        t for o in ops for t in o["a_favor"] + o["en_contra"] + o["condiciones"] + o["invalidaria"]]
    assert [t for t in textos if PROHIBIDAS.search(t)] == []
