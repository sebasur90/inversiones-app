"""Aprendizaje: patrones con muestra mínima, una revisión por decisión y la tesis como algo del usuario."""
from datetime import date

from app.services import aprendizaje_engine as ae

HOY = date(2026, 6, 1)


def _decision(i, nota=True, ejecutada=True):
    return {"id": i, "accion_elegida": "entrar_ahora", "conclusion_tipo": "ninguna_superior", "ejecutada": ejecutada,
            "revisar_el": None, "condiciones": {"invalidacion": [{"tipo": "dimension"}]}, "banderas_altas": False,
            "concentracion_revisar": False, "favorable_pct": 0.4, "con_tesis": nota}


def _revision(i, variacion, cumplida=False):
    return {"decision_id": i, "comparacion": {"precio": {"variacion": variacion},
                                              "condiciones": [{"cumplida": cumplida}],
                                              "riesgo": {"volatilidad_al_decidir": 0.2, "volatilidad_observada": 0.3}}}


def _patron(res, clave):
    return next(p for p in res["patrones"] if p["clave"] == clave)


def test_la_tesis_cuenta_lo_que_escribio_el_usuario():
    decisiones = [_decision(1), _decision(2, nota=False), _decision(3), _decision(4, nota=False)]
    p = _patron(ae.patrones(decisiones, [], None, HOY), "tesis")
    assert (p["casos"], p["muestra"]) == (2, 4)
    assert not [x for x in ae.patrones(decisiones, [], None, HOY)["patrones"] if x["clave"] == "invalidacion"]


def test_una_decision_revisada_varias_veces_cuenta_una_sola_vez():
    decisiones = [_decision(i) for i in (1, 2, 3)]
    # la decisión 1 se revisó cuatro veces: antes pesaba cuatro casos
    revisiones = [_revision(1, 0.0, True)] * 3 + [_revision(1, 0.5)] + [_revision(2, 0.0), _revision(3, 0.0, True)]
    res = ae.patrones(decisiones, revisiones, None, HOY)
    expectativa, riesgo, invalidadas = (_patron(res, k) for k in ("expectativa", "riesgo", "invalidacion_cumplida"))
    assert expectativa["muestra"] == 3 and expectativa["casos"] == 2      # cuenta la última de la 1 (0,5 ≥ 25 % de 0,4)
    assert riesgo["muestra"] == 3
    assert (invalidadas["casos"], invalidadas["muestra"]) == (1, 3)
    assert res["revisiones"] == 6
