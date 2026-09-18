"""Tests del motor puro de ritmo de aportes (`services/aportes_engine.py`), sin DB.

Fijan las convenciones: meses sin movimientos valen 0 y cuentan, el mes en curso no entra en
promedios ni récords pero sí suma a la racha, y todas las comparaciones son contra el propio
historial.
"""
import pytest
from datetime import date

from app.services import aportes_engine as eng
from app.services.aportes_engine import calcular_ritmo

# 18 de septiembre: día 18 de 30, quedan 12.
HOY = date(2025, 9, 18)


def _m(neto: float, compras: float | None = None, salidas: float = 0.0) -> dict:
    return {"neto": neto, "compras": neto + salidas if compras is None else compras, "salidas": salidas}


def _serie_meses(netos: list[float], hasta: str = "2025-09") -> dict[str, dict]:
    """Arma la serie terminando en `hasta` (el mes en curso), un neto por mes hacia atrás."""
    serie = {}
    mes = hasta
    for neto in reversed(netos):
        serie[mes] = _m(neto)
        mes = eng._sumar_meses(mes, -1)
    return serie


def _mensaje(res: dict, clave: str) -> dict | None:
    return next((m for m in res["mensajes"] if m["clave"] == clave), None)


# ── Casos borde ───────────────────────────────────────────────────────────────

def test_sin_datos():
    res = calcular_ritmo({}, HOY)
    assert res["estado"] == "sin_datos"
    assert res["serie_mensual"] == [] and res["mensajes"] == []
    assert res["este_mes"] is None and res["rachas"] is None


def test_un_solo_mes_en_curso():
    res = calcular_ritmo({"2025-09": _m(300)}, HOY)
    assert res["estado"] == "ok"
    assert res["estado_ritmo"]["estado"] == "arrancando"
    assert res["estadisticas"]["meses_historia"] == 0
    assert res["este_mes"]["vs_mes_anterior"] is None
    assert res["este_mes"]["vs_promedio_3"] is None
    assert res["rachas"]["aportando_actual"] == {"meses": 1, "desde": "2025-09", "hasta": "2025-09", "incluye_mes_en_curso": True}
    assert any(h["clave"] == "primer_aporte" and h["fecha"] == "2025-09" for h in res["hitos_alcanzados"])
    assert _mensaje(res, "arrancando") is not None


def test_serie_completa_rellena_ceros():
    res = calcular_ritmo({"2025-01": _m(100), "2025-04": _m(200)}, HOY)
    meses = [s["mes"] for s in res["serie_mensual"]]
    assert meses == [f"2025-0{i}" for i in range(1, 10)]
    feb = res["serie_mensual"][1]
    assert feb["neto_usd"] == 0 and feb["con_aporte"] is False
    assert res["serie_mensual"][-1]["en_curso"] is True
    assert res["estadisticas"]["meses_historia"] == 8


def test_movimiento_futuro_no_rompe():
    serie = _serie_meses([100, 100, 100, 100, 100])
    serie["2025-11"] = _m(999)
    res = calcular_ritmo(serie, HOY)
    ultimo = res["serie_mensual"][-1]
    assert ultimo["mes"] == "2025-11" and ultimo["futuro"] is True
    assert res["estadisticas"]["meses_historia"] == 4
    assert res["estadisticas"]["mejor_mes"]["neto_usd"] == 100
    assert res["rachas"]["aportando_actual"]["meses"] == 5


# ── Mes en curso ──────────────────────────────────────────────────────────────

def test_mes_en_curso_no_entra_en_promedios_ni_records():
    res = calcular_ritmo(_serie_meses([100] * 8 + [5000]), HOY)
    est = res["estadisticas"]
    assert est["promedio_3_usd"] == 100 and est["promedio_usd"] == 100
    assert est["mejor_mes"]["mes"] != "2025-09"
    assert res["este_mes"]["es_record_parcial"] is True
    assert _mensaje(res, "record_en_curso") is not None


def test_proyeccion_del_mes():
    res = calcular_ritmo(_serie_meses([100, 100, 300]), HOY)
    em = res["este_mes"]
    assert em["dia"] == 18 and em["dias_mes"] == 30 and em["dias_restantes"] == 12
    assert em["proyeccion_usd"] == 500
    assert em["proyeccion_fiable"] is True
    assert em["vs_mes_anterior"] == {
        "referencia_usd": 100, "delta_usd": 200, "delta_pct": 200.0,
        "delta_proyectado_usd": 400, "delta_proyectado_pct": 400.0,
    }

    temprano = calcular_ritmo(_serie_meses([100, 100, 30]), date(2025, 9, 3))
    assert temprano["este_mes"]["proyeccion_usd"] == 300
    assert temprano["este_mes"]["proyeccion_fiable"] is False


def test_vs_mismo_mes_anio_anterior():
    serie = _serie_meses([100] * 13)  # 2024-09 .. 2025-09
    serie["2024-09"] = _m(50)
    res = calcular_ritmo(serie, HOY)
    assert res["este_mes"]["vs_mismo_mes_anio_anterior"]["referencia_usd"] == 50
    corto = calcular_ritmo(_serie_meses([100] * 5), HOY)
    assert corto["este_mes"]["vs_mismo_mes_anio_anterior"] is None


# ── Retiros y rachas ──────────────────────────────────────────────────────────

def test_retiro_es_mes_negativo_y_corta_racha():
    serie = _serie_meses([100, 100, 100, 100, 100, 100, 100])
    serie["2025-06"] = {"neto": -150, "compras": 50, "salidas": 200}
    res = calcular_ritmo(serie, HOY)
    jun = next(s for s in res["serie_mensual"] if s["mes"] == "2025-06")
    assert jun["neto_usd"] == -150 and jun["con_aporte"] is False
    assert res["estadisticas"]["meses_con_retiro"] == 1
    assert res["estadisticas"]["peor_mes"] == {"mes": "2025-06", "neto_usd": -150}
    # jul, ago cerrados + sep en curso
    assert res["rachas"]["aportando_actual"]["meses"] == 3
    assert res["rachas"]["aportando_actual"]["desde"] == "2025-07"


def test_racha_actual_no_la_corta_el_mes_en_curso_en_cero():
    # 4 con aporte, 1 en cero, 6 con aporte, mes actual en cero
    netos = [100] * 4 + [0] + [100] * 6 + [0]
    res = calcular_ritmo(_serie_meses(netos), HOY)
    r = res["rachas"]
    assert r["aportando_actual"]["meses"] == 6
    assert r["aportando_actual"]["incluye_mes_en_curso"] is False
    assert r["aportando_actual"]["hasta"] == "2025-08"
    assert r["aportando_record"]["meses"] == 6
    assert r["aportando_record"]["desde"] == "2025-03" and r["aportando_record"]["hasta"] == "2025-08"
    assert r["sin_aportar_actual"] == 0

    con_actual = calcular_ritmo(_serie_meses(netos[:-1] + [50]), HOY)
    assert con_actual["rachas"]["aportando_actual"]["meses"] == 7
    assert con_actual["rachas"]["aportando_actual"]["incluye_mes_en_curso"] is True
    assert con_actual["rachas"]["aportando_record"]["meses"] == 7


def test_record_de_racha_anterior_gana_a_la_actual():
    netos = [100] * 8 + [0] + [100] * 2 + [100]
    res = calcular_ritmo(_serie_meses(netos), HOY)
    assert res["rachas"]["aportando_actual"]["meses"] == 3
    assert res["rachas"]["aportando_record"]["meses"] == 8


def test_parado():
    netos = [160] * 5 + [0, 0, 0] + [0]
    res = calcular_ritmo(_serie_meses(netos), HOY)
    assert res["estado_ritmo"]["estado"] == "parado"
    assert res["estado_ritmo"]["nivel"] == "riesgo"
    assert res["rachas"]["sin_aportar_actual"] == 3
    assert res["rachas"]["aportando_actual"]["meses"] == 0
    assert res["mensajes"][0]["clave"] == "parado"
    assert res["mensajes"][0]["tono"] == "negativo"
    assert "USD 100/mes" in res["mensajes"][0]["detalle"]  # promedio 800/8


def test_sin_aporte_a_mitad_de_mes():
    res = calcular_ritmo(_serie_meses([100, 100, 100, 100, 100, 0]), HOY)
    m = _mensaje(res, "sin_aporte_mes")
    assert m is not None and m["tono"] == "negativo"
    assert "12 días" in m["detalle"]
    temprano = calcular_ritmo(_serie_meses([100, 100, 100, 100, 100, 0]), date(2025, 9, 10))
    assert _mensaje(temprano, "sin_aporte_mes") is None


def test_direccion_subiendo_y_bajando():
    sube = calcular_ritmo(_serie_meses([100, 200, 300, 0]), HOY)
    assert sube["rachas"]["direccion"] == "subiendo" and sube["rachas"]["direccion_meses"] == 2
    baja = calcular_ritmo(_serie_meses([300, 200, 100, 0]), HOY)
    assert baja["rachas"]["direccion"] == "bajando" and baja["rachas"]["direccion_meses"] == 2
    plano = calcular_ritmo(_serie_meses([100, 100, 100, 0]), HOY)
    assert plano["rachas"]["direccion"] == "ninguna"


# ── Estado del ritmo ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("ultimos, esperado, t3", [
    (480, "acelerando", 20.0),
    (330, "frenando", -17.5),
    (420, "sostenido", 5.0),
])
def test_estado_por_tendencia(ultimos, esperado, t3):
    res = calcular_ritmo(_serie_meses([400] * 3 + [ultimos] * 3 + [0]), HOY)
    assert res["estado_ritmo"]["estado"] == esperado
    assert res["estado_ritmo"]["tendencia_3v3_pct"] == t3
    assert res["estado_ritmo"]["promedio_3_usd"] == ultimos
    assert res["estado_ritmo"]["promedio_3_anterior_usd"] == 400


def test_volvio_a_aportar_es_acelerando_sin_porcentaje():
    res = calcular_ritmo(_serie_meses([0, 0, 0, 100, 100, 100, 0]), HOY)
    assert res["estado_ritmo"]["estado"] == "acelerando"
    assert res["estado_ritmo"]["tendencia_3v3_pct"] is None
    assert _mensaje(res, "acelerando")["titulo"] == "Volviste a aportar"


def test_arrancando_con_pocos_meses():
    res = calcular_ritmo(_serie_meses([100, 100, 100, 100]), HOY)  # 3 cerrados
    assert res["estado_ritmo"]["estado"] == "arrancando"
    con_cuatro = calcular_ritmo(_serie_meses([100, 100, 100, 100, 100]), HOY)
    assert con_cuatro["estado_ritmo"]["estado"] == "sostenido"
    # con 4-5 cerrados el "trimestre anterior" es lo que haya antes de los últimos 3
    assert con_cuatro["estado_ritmo"]["promedio_3_anterior_usd"] == 100


def test_promedios_insuficientes_son_none():
    res = calcular_ritmo(_serie_meses([100] * 5 + [50]), HOY)
    est = res["estadisticas"]
    assert est["promedio_3_usd"] == 100
    assert est["promedio_6_usd"] is None and est["promedio_12_usd"] is None
    assert est["constancia"] is None
    assert res["este_mes"]["vs_promedio_6"] is None and res["este_mes"]["vs_promedio_12"] is None
    assert res["rachas"]["sobre_promedio_12_actual"] is None
    assert res["estado_ritmo"]["tendencia_6v6_pct"] is None


def test_constancia_por_coeficiente_de_variacion():
    constante = calcular_ritmo(_serie_meses([100, 110, 90, 100, 105, 95, 0]), HOY)
    assert constante["estadisticas"]["constancia"]["nivel"] == "bien"
    irregular = calcular_ritmo(_serie_meses([100, 300, 50, 200, 20, 150, 0]), HOY)
    assert irregular["estadisticas"]["constancia"]["nivel"] == "atencion"
    muy = calcular_ritmo(_serie_meses([0, 0, 0, 0, 0, 600, 0]), HOY)
    assert muy["estadisticas"]["constancia"]["nivel"] == "riesgo"


def test_sobre_promedio_12():
    netos = [100] * 9 + [200, 200, 200] + [0]
    res = calcular_ritmo(_serie_meses(netos), HOY)
    assert res["estadisticas"]["promedio_12_usd"] == 125
    assert res["rachas"]["sobre_promedio_12_actual"] == 3
    assert res["rachas"]["meses_sin_aportar_ultimos_12"] == 0
    assert res["rachas"]["meses_considerados_ultimos_12"] == 12


# ── Año en curso y proyecciones ───────────────────────────────────────────────

def test_proyecciones_fin_de_anio():
    # ene–ago 100 c/u, sep 60 al día 18/30 → proyección del mes 100
    serie = {f"2025-{m:02d}": _m(100) for m in range(1, 9)}
    serie["2025-09"] = _m(60)
    res = calcular_ritmo(serie, HOY)
    a = res["anio_en_curso"]
    assert a["ytd_usd"] == 860 and a["meses_cerrados"] == 8 and a["meses_restantes"] == 3
    assert a["promedio_mensual_ytd_usd"] == 100
    por_clave = {p["clave"]: p for p in a["proyecciones"]}
    assert por_clave["este_mes"]["total_fin_anio_usd"] == 1200      # 800 + 100 × 4
    assert por_clave["promedio_3"]["total_fin_anio_usd"] == 1200    # 800 + max(60,100) + 100 × 3
    assert por_clave["promedio_ytd"]["total_fin_anio_usd"] == 1200
    assert a["anio_anterior_total_usd"] is None
    assert a["vs_mismo_periodo_anio_anterior"] is None


def test_proyeccion_no_descuenta_lo_ya_aportado():
    serie = {f"2025-{m:02d}": _m(100) for m in range(1, 9)}
    serie["2025-09"] = _m(500)  # ya superó el ritmo
    res = calcular_ritmo(serie, HOY)
    por_clave = {p["clave"]: p for p in res["anio_en_curso"]["proyecciones"]}
    assert por_clave["promedio_3"]["total_fin_anio_usd"] == 800 + 500 + 300


def test_proyeccion_ytd_none_en_enero():
    res = calcular_ritmo({"2024-12": _m(100), "2025-01": _m(50)}, date(2025, 1, 10))
    a = res["anio_en_curso"]
    assert a["promedio_mensual_ytd_usd"] is None
    por_clave = {p["clave"]: p for p in a["proyecciones"]}
    assert por_clave["promedio_ytd"]["total_fin_anio_usd"] is None
    assert por_clave["este_mes"]["total_fin_anio_usd"] == pytest.approx(50 * 31 / 10 * 12, abs=0.01)


def test_vs_mismo_periodo_prorratea_el_mes_equivalente():
    serie = {f"2024-{m:02d}": _m(100) for m in range(1, 13)}
    serie.update({f"2025-{m:02d}": _m(120) for m in range(1, 10)})
    res = calcular_ritmo(serie, HOY)
    cmp = res["anio_en_curso"]["vs_mismo_periodo_anio_anterior"]
    assert cmp["referencia_usd"] == 860  # 800 + 100 × 18/30
    assert cmp["delta_usd"] == pytest.approx(1080 - 860)
    assert res["anio_en_curso"]["anio_anterior_total_usd"] == 1200
    assert _mensaje(res, "vs_anio_pasado")["tono"] == "positivo"


def test_por_anio_y_mejor_anio():
    serie = {f"2023-{m:02d}": _m(100) for m in range(1, 13)}          # 1200
    serie.update({f"2024-{m:02d}": _m(125) for m in range(1, 13)})    # 1500
    serie.update({f"2025-{m:02d}": _m(100) for m in range(1, 10)})    # 900 en curso
    res = calcular_ritmo(serie, HOY)
    assert [a["anio"] for a in res["por_anio"]] == [2025, 2024, 2023]
    a2024 = res["por_anio"][1]
    assert a2024["total_usd"] == 1500 and a2024["var_vs_anio_anterior_pct"] == 25.0
    assert a2024["meses_con_aporte"] == 12 and a2024["en_curso"] is False
    assert res["por_anio"][2]["var_vs_anio_anterior_pct"] is None
    a2025 = res["por_anio"][0]
    assert a2025["en_curso"] is True and a2025["meses_en_rango"] == 9
    assert a2025["promedio_mensual_usd"] == 100  # sólo cerrados
    assert res["mejor_anio"] == {"anio": 2024, "total_usd": 1500}
    assert not any(h["clave"] == "mejor_anio_en_curso" for h in res["hitos_alcanzados"])

    serie["2025-09"] = _m(700)  # ytd 1500 → todavía no supera; 1501 sí
    assert not any(h["clave"] == "mejor_anio_en_curso" for h in calcular_ritmo(serie, HOY)["hitos_alcanzados"])
    serie["2025-09"] = _m(701)
    hito = next(h for h in calcular_ritmo(serie, HOY)["hitos_alcanzados"] if h["clave"] == "mejor_anio_en_curso")
    assert hito["fecha"] == "2025-09" and hito["reciente"] is True


# ── Hitos ─────────────────────────────────────────────────────────────────────

def test_hitos_total_y_racha_con_fecha():
    # 1000/mes desde 2024-01: cruza 5k en 2024-05, 10k en 2024-10; racha 3 en 2024-03, 6 en 2024-06, 12 en 2024-12
    serie = {f"2024-{m:02d}": _m(1000) for m in range(1, 13)}
    serie.update({f"2025-{m:02d}": _m(1000) for m in range(1, 10)})  # total 21k, racha 21
    res = calcular_ritmo(serie, HOY)
    por_clave = {h["clave"]: h for h in res["hitos_alcanzados"]}
    assert por_clave["total_5000"]["fecha"] == "2024-05"
    assert por_clave["total_10000"]["fecha"] == "2024-10"
    assert "total_25000" not in por_clave
    assert por_clave["racha_3"]["fecha"] == "2024-03"
    assert por_clave["racha_12"]["fecha"] == "2024-12"
    assert por_clave["primer_aporte"]["fecha"] == "2024-01"
    assert por_clave["record_mensual"]["fecha"] == "2024-01"  # empate → el más antiguo
    assert res["hitos_alcanzados"][0]["fecha"] >= res["hitos_alcanzados"][-1]["fecha"]

    proximos = {p["clave"]: p for p in res["proximos_hitos"]}
    assert proximos["total_25000"]["falta"] == 4000 and proximos["total_25000"]["progreso_pct"] == 84.0
    assert proximos["racha_24"]["falta"] == 3


def test_hito_se_conserva_tras_retiro_y_el_proximo_es_el_siguiente():
    serie = {f"2025-{m:02d}": _m(1000) for m in range(1, 6)}       # 5k en mayo
    serie["2025-06"] = {"neto": -1000, "compras": 0, "salidas": 1000}  # vuelve a 4k
    res = calcular_ritmo(serie, HOY)
    assert any(h["clave"] == "total_5000" and h["fecha"] == "2025-05" for h in res["hitos_alcanzados"])
    assert res["proximos_hitos"][0]["clave"] == "total_10000"
    assert res["proximos_hitos"][0]["valor_actual"] == 4000
    assert res["proximos_hitos"][0]["falta"] == 6000


# ── Mensajes ──────────────────────────────────────────────────────────────────

def test_mensajes_max_4_prioridad_y_claves_unicas():
    # 13 meses: 400 × 9, luego 700 × 3 (acelerando), mes en curso 900 al día 18 → récord parcial,
    # racha larga, proyección arriba del promedio 12 → sobran candidatos.
    netos = [400] * 9 + [700] * 3 + [900]
    res = calcular_ritmo(_serie_meses(netos), HOY)
    claves = [m["clave"] for m in res["mensajes"]]
    assert len(claves) == eng.MAX_MENSAJES
    assert len(set(claves)) == len(claves)
    assert claves == ["record_en_curso", "acelerando", "racha", "arriba_promedio"]


def test_mensaje_abajo_promedio():
    netos = [400] * 12 + [100]  # proyección 167 < 70% de 400
    res = calcular_ritmo(_serie_meses(netos), HOY)
    m = _mensaje(res, "abajo_promedio")
    assert m is not None and m["tono"] == "negativo"
    assert "12 días" in m["detalle"]


def test_mensaje_proyeccion_y_proximo_hito_con_pocos_datos():
    res = calcular_ritmo(_serie_meses([100, 100, 100, 100, 50]), HOY)
    assert _mensaje(res, "proyeccion_anio") is not None
    assert _mensaje(res, "proximo_hito")["titulo"].startswith("Te faltan USD 4.550")


def test_promedio_movil_usa_la_proyeccion_en_el_mes_en_curso():
    res = calcular_ritmo(_serie_meses([100, 100, 300]), HOY)  # proyección 500
    serie = res["serie_mensual"]
    assert serie[0]["promedio_movil_3_usd"] is None and serie[1]["promedio_movil_3_usd"] is None
    assert serie[2]["promedio_movil_3_usd"] == pytest.approx((100 + 100 + 500) / 3, abs=0.01)
