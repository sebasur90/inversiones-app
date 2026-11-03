"""Motor de «Ciclos de mercado» con series sintéticas de resultado conocido: rotación relativa y sus
cuadrantes, transiciones confirmadas, huecos y datos insuficientes, rendimientos, riesgo, correlaciones,
desfases, sintético y descomposición de un país. Nada acá usa datos reales."""
import math
import random
import statistics
from datetime import date, timedelta

import pytest

from app.services import ciclos_engine as ce

VIERNES0 = date(2020, 1, 3)          # un viernes


def viernes(i: int, inicio: date = VIERNES0) -> date:
    return inicio + timedelta(days=7 * i)


def semanal_desde(valores, inicio: date = VIERNES0):
    return [(viernes(i, inicio), v) for i, v in enumerate(valores)]


def par_desde_rs(rs, benchmark=100.0):
    """(grupo, benchmark) semanales tales que grupo/benchmark = rs."""
    b = [benchmark] * len(rs) if isinstance(benchmark, (int, float)) else list(benchmark)
    return semanal_desde([r * x for r, x in zip(rs, b)]), semanal_desde(b)


def crece(g: float, n: int, desde: float = 1.0):
    return [desde * g ** i for i in range(1, n + 1)]


def ultimo(res: dict) -> dict:
    return res["puntos"][-1]


# -- rotación: cuadrantes ----------------------------------------------------------------------

def test_mismo_rendimiento_deja_ratio_y_momentum_en_100():
    a, b = par_desde_rs([1.0] * 60)
    res = ce.rotacion(a, b)
    assert res["estado"] == "ok"
    for p in res["puntos"]:
        assert p["rs_ratio"] == pytest.approx(100.0, abs=1e-9)
        assert p["rs_momentum"] == pytest.approx(100.0, abs=1e-9)


def test_mismo_rendimiento_con_benchmark_que_se_mueve():
    b = [100 * 1.004 ** i for i in range(60)]
    a, bb = par_desde_rs([1.0] * 60, b)
    assert all(p["rs_ratio"] == pytest.approx(100.0, abs=1e-9) for p in ce.rotacion(a, bb)["puntos"])


def test_el_que_empieza_a_superar_al_benchmark_queda_leading():
    rs = [1.0] * 40 + crece(1.015, 20)
    res = ce.rotacion(*par_desde_rs(rs))
    p = ultimo(res)
    assert res["actual"] == p
    assert p["rs_ratio"] > 100 and p["rs_momentum"] > 100 and p["cuadrante"] == ce.LEADING


def test_el_que_supero_y_se_estanca_pasa_a_weakening():
    rs = crece(1.015, 40) + [1.015 ** 40] * 6
    p = ultimo(ce.rotacion(*par_desde_rs(rs)))
    assert p["rs_ratio"] > 100 and p["rs_momentum"] < 100 and p["cuadrante"] == ce.WEAKENING


def test_el_que_empieza_a_quedar_atras_es_lagging():
    rs = [1.0] * 40 + crece(0.985, 20)
    p = ultimo(ce.rotacion(*par_desde_rs(rs)))
    assert p["rs_ratio"] < 100 and p["rs_momentum"] < 100 and p["cuadrante"] == ce.LAGGING


def test_el_que_cayo_y_se_estabiliza_es_improving():
    rs = crece(0.985, 40) + [0.985 ** 40] * 6
    p = ultimo(ce.rotacion(*par_desde_rs(rs)))
    assert p["rs_ratio"] < 100 and p["rs_momentum"] > 100 and p["cuadrante"] == ce.IMPROVING


def test_la_formula_coincide_con_un_calculo_a_mano():
    rs = [1.0] * 40 + crece(1.015, 20)
    a, b = par_desde_rs(rs)
    puntos = ce.rotacion(a, b)["puntos"]
    # RS_Ratio en la última semana: 100·RS / EMA13(RS), con la EMA sembrada con la SMA de las primeras 13 semanas.
    k = 2 / 14
    ema = sum(rs[:13]) / 13
    for v in rs[13:]:
        ema = v * k + ema * (1 - k)
    assert puntos[-1]["rs_ratio"] == pytest.approx(100 * rs[-1] / ema, abs=1e-5)


def _ema_a_mano(valores, n):
    """EMA sembrada con la media simple de las primeras n observaciones; None antes de la semilla."""
    k = 2 / (n + 1)
    out, prev = [None] * len(valores), None
    for i, v in enumerate(valores):
        if i == n - 1:
            prev = sum(valores[:n]) / n
        elif i >= n:
            prev = v * k + prev * (1 - k)
        if i >= n - 1:
            out[i] = prev
    return out


@pytest.mark.parametrize("n", [5, 13])
def test_ratio_y_momentum_de_todos_los_puntos_coinciden_con_un_calculo_independiente(n):
    rnd = random.Random(3)
    rs = [1.0]
    for _ in range(79):
        rs.append(rs[-1] * (1 + rnd.uniform(-0.02, 0.025)))
    a, b = par_desde_rs(rs)
    ratio = [100 * r / e for r, e in zip(rs[n - 1:], _ema_a_mano(rs, n)[n - 1:])]
    ema_ratio = _ema_a_mano(ratio, n)
    esperado = [(viernes(n - 1 + i), x, 100 * x / e) for i, (x, e) in enumerate(zip(ratio, ema_ratio)) if e is not None]
    puntos = ce.rotacion(a, b, ventana=n, cola=2)["puntos"]
    assert [p["fecha"] for p in puntos] == [f for f, _, _ in esperado]
    assert [p["rs_ratio"] for p in puntos] == pytest.approx([x for _, x, _ in esperado], abs=1e-5)
    assert [p["rs_momentum"] for p in puntos] == pytest.approx([m for _, _, m in esperado], abs=1e-5)
    assert puntos[0]["fecha"] == viernes(2 * n - 2)           # el primer momentum existe recién tras 2n−1 semanas


def test_la_ventana_se_puede_cambiar():
    rs = [1.0] * 40 + crece(1.015, 20)
    a, b = par_desde_rs(rs)
    r13, r8 = ce.rotacion(a, b, ventana=13), ce.rotacion(a, b, ventana=8)
    assert r8["ventana"] == 8 and len(r8["puntos"]) > len(r13["puntos"])
    assert r8["puntos"][-1]["rs_ratio"] != r13["puntos"][-1]["rs_ratio"]


def test_cuadrante_en_el_borde():
    assert ce.cuadrante(100.0, 100.0) == ce.LEADING
    assert ce.cuadrante(100.0 - 1e-12, 100.0 + 1e-12) == ce.LEADING        # ruido de punto flotante, no cambia de lado
    assert ce.cuadrante(101, 99) == ce.WEAKENING
    assert ce.cuadrante(99, 99) == ce.LAGGING
    assert ce.cuadrante(99, 101) == ce.IMPROVING


# -- rotación: datos ---------------------------------------------------------------------------

def test_historia_insuficiente():
    res = ce.rotacion(*par_desde_rs([1.0] * 30))
    assert res["estado"] == "datos_insuficientes" and res["actual"] is None and res["puntos"] == []
    assert "34 semanas" in res["motivo"] and "30" in res["motivo"]


def test_el_minimo_exacto_alcanza():
    assert ce.rotacion(*par_desde_rs([1.0] * 34))["estado"] == "ok"
    assert ce.rotacion(*par_desde_rs([1.0] * 33))["estado"] == "datos_insuficientes"


def test_sin_datos_y_sin_benchmark():
    a, _ = par_desde_rs([1.0] * 60)
    assert ce.rotacion([], a)["estado"] == "sin_datos"
    assert ce.rotacion(a, [])["estado"] == "sin_benchmark"


def test_series_sin_fechas_en_comun():
    a = semanal_desde([100.0] * 60)
    b = semanal_desde([100.0] * 60, VIERNES0 + timedelta(days=1))
    assert ce.rotacion(a, b)["estado"] == "datos_insuficientes"


def test_una_semana_faltante_corta_el_tramo_y_la_ema_no_la_cruza():
    rs = [1.0] * 40 + crece(1.015, 20)
    a, b = par_desde_rs(rs)
    a_hueco = [x for i, x in enumerate(a) if i != 20]
    b_hueco = [x for i, x in enumerate(b) if i != 20]
    res = ce.rotacion(a_hueco, b_hueco)
    assert res["estado"] == "ok" and res["semanas_usadas"] == 39
    assert res["puntos"][0]["fecha"] >= viernes(21)


def test_si_tras_el_hueco_no_alcanza_la_historia_se_dice_cuántas_se_descartaron():
    a, b = par_desde_rs([1.0] * 60)
    hueco = lambda s: [x for i, x in enumerate(s) if i != 40]
    res = ce.rotacion(hueco(a), hueco(b))
    assert res["estado"] == "datos_insuficientes" and "descartaron 40" in res["motivo"]


def test_un_dato_viejo_no_se_presenta_como_actual():
    a, b = par_desde_rs([1.0] * 60)
    res = ce.rotacion(a, b, hoy=viernes(59) + timedelta(days=30))
    assert res["estado"] == "desactualizado" and res["actual"] is None
    assert res["puntos"] and res["ultima_fecha"] == viernes(59)       # la historia sigue disponible como historia


def test_un_grupo_atrasado_respecto_del_benchmark_esta_desactualizado():
    a, b = par_desde_rs([1.0] * 60)
    assert ce.rotacion(a[:50], b)["estado"] == "desactualizado"       # 9 semanas atrás


def test_los_dias_se_alinean_por_interseccion_y_la_barra_semanal_es_el_ultimo_dia_comun():
    # Grupo diario (7 días, como Bitcoin) contra benchmark en días hábiles; cada viernes vale lo que dice el perfil.
    rs = [1.0] * 40 + crece(1.015, 20)
    sem_a, sem_b = par_desde_rs(rs)
    diario_a, diario_b = [], []
    lunes0 = viernes(0) - timedelta(days=4)
    for i in range(60):
        for dia in range(7):
            f = lunes0 + timedelta(days=7 * i + dia)
            ruido = 1.0 if dia == 4 else 1.07                          # el viernes vale el perfil; el resto, distinto
            diario_a.append((f, sem_a[i][1] * ruido))
            if dia < 5:
                diario_b.append((f, 100.0))
    res_diario = ce.rotacion(diario_a, diario_b)
    res_semanal = ce.rotacion(sem_a, sem_b)
    assert [p["rs_ratio"] for p in res_diario["puntos"]] == pytest.approx([p["rs_ratio"] for p in res_semanal["puntos"]])
    assert all(p["fecha"].weekday() == 4 for p in res_diario["puntos"])      # ningún sábado ni domingo


def test_fechas_duplicadas_y_valores_invalidos_se_descartan():
    s = ce.normalizar([(date(2024, 1, 2), 10.0), (date(2024, 1, 2), 11.0), (date(2024, 1, 1), 9.0),
                       (date(2024, 1, 3), 0.0), (date(2024, 1, 4), float("nan")), (date(2024, 1, 5), -3.0),
                       (date(2024, 1, 6), None)])
    assert s == [(date(2024, 1, 1), 9.0), (date(2024, 1, 2), 11.0)]


def test_semana_cerrada():
    lunes = date(2024, 1, 1)
    assert ce.semana_cerrada(date(2023, 12, 29), lunes)               # viernes de la semana anterior
    assert not ce.semana_cerrada(date(2024, 1, 2), date(2024, 1, 3))  # misma semana, miércoles
    assert ce.semana_cerrada(date(2024, 1, 5), date(2024, 1, 6))      # misma semana, ya sábado


# -- transiciones ------------------------------------------------------------------------------

def _puntos(secuencia: str):
    cuad = {"L": ce.LEADING, "W": ce.WEAKENING, "G": ce.LAGGING, "I": ce.IMPROVING}
    return [{"fecha": viernes(i), "rs_ratio": 100.0, "rs_momentum": 100.0, "cuadrante": cuad[c]} for i, c in enumerate(secuencia)]


def test_un_cambio_sostenido_es_confirmado():
    t = ce.transiciones(_puntos("GGGGGIIIIILLLL"))
    assert [(c["cuadrante"], c["anterior"]) for c in t["cambios_confirmados"]] == [("lagging", None), ("improving", "lagging"), ("leading", "improving")]
    assert t["cuadrante_confirmado"] == "leading" and t["pendiente"] is None and t["transitorios"] == []
    assert t["cambios_confirmados"][1]["desde"] == viernes(5) and t["cambios_confirmados"][1]["semanas"] == 5


def test_un_movimiento_corto_es_transitorio_y_no_corta_el_ciclo_confirmado():
    t = ce.transiciones(_puntos("LLLLLWLLLLL"))
    assert len(t["cambios_confirmados"]) == 1 and t["cambios_confirmados"][0]["semanas"] == 10
    assert [(x["cuadrante"], x["semanas"], x["confirmado"]) for x in t["transitorios"]] == [("weakening", 1, False)]
    assert t["cuadrante_confirmado"] == "leading" and t["pendiente"] is None


def test_un_cambio_reciente_sin_confirmar_queda_pendiente():
    t = ce.transiciones(_puntos("LLLLLLWW"))
    assert t["cuadrante_confirmado"] == "leading"
    assert t["pendiente"]["cuadrante"] == "weakening" and t["pendiente"]["semanas"] == 2 and not t["pendiente"]["confirmado"]


def test_la_confirmacion_se_puede_ajustar():
    assert ce.transiciones(_puntos("LLLLWW"), confirmacion=2)["cuadrante_confirmado"] == "weakening"
    assert ce.transiciones(_puntos("LLLLWW"), confirmacion=3)["cuadrante_confirmado"] == "leading"


def test_sin_ningun_tramo_firme():
    t = ce.transiciones(_puntos("LWLW"))
    assert t["cambios_confirmados"] == [] and t["cuadrante_confirmado"] is None


def test_la_rotacion_real_detecta_el_orden_de_los_cuadrantes():
    # Parte de neutral, supera, se estanca y cae: leading → weakening → lagging, cada uno con tramo firme.
    tope = 1.015 ** 20
    rs = [1.0] * 40 + crece(1.015, 20) + [tope] * 12 + crece(0.985, 25, tope)
    cambios = ce.rotacion(*par_desde_rs(rs))["transiciones"]["cambios_confirmados"]
    assert [c["cuadrante"] for c in cambios][:1] == ["leading"]
    orden = [c["cuadrante"] for c in cambios]
    assert "weakening" in orden and orden[-1] == "lagging" and orden.index("weakening") < orden.index("lagging")
    assert all(c["confirmado"] and c["semanas"] >= 3 for c in cambios)


# -- trayectoria -------------------------------------------------------------------------------

def test_trayectoria_toma_las_ultimas_semanas_y_limita_los_puntos():
    pts = _puntos("L" * 100)
    assert [p["fecha"] for p in ce.trayectoria(pts, 5)] == [viernes(i) for i in range(95, 100)]
    larga = ce.trayectoria(pts, 100, max_puntos=13)
    assert len(larga) == 13 and larga[-1]["fecha"] == viernes(99) and larga[0]["fecha"] == viernes(0)
    assert ce.trayectoria(pts, 0) == []


# -- rendimientos ------------------------------------------------------------------------------

def diaria(g: float, dias: int, hasta: date = date(2024, 6, 14), base: float = 100.0):
    """Un dato por día calendario que crece g por día, terminando en `hasta`."""
    return [(hasta - timedelta(days=dias - 1 - i), base * g ** i) for i in range(dias)]


HASTA = date(2024, 6, 14)


def test_rendimiento_acumulado_exacto():
    a = diaria(1.001, 1500)
    r = ce.rendimientos(a, None, HASTA)
    dias_1a = (HASTA - ce.restar_meses(HASTA, 12)).days
    assert r["1A"]["absoluto"] == pytest.approx(1.001 ** dias_1a - 1)
    dias_3m = (HASTA - ce.restar_meses(HASTA, 3)).days
    assert r["3M"]["absoluto"] == pytest.approx(1.001 ** dias_3m - 1)
    assert r["1A"]["desde"] == date(2023, 6, 14) and r["1A"]["hasta"] == HASTA


def test_el_relativo_es_cociente_de_los_dos_rendimientos():
    a, b = diaria(1.001, 1500), diaria(1.0004, 1500)
    r = ce.rendimientos(a, b, HASTA)["1A"]
    ra, rb = r["absoluto"], ce.rendimientos(b, None, HASTA)["1A"]["absoluto"]
    assert r["relativo"] == pytest.approx((1 + ra) / (1 + rb) - 1)


def test_sin_historia_suficiente_no_se_completa_ni_se_acorta():
    r = ce.rendimientos(diaria(1.001, 200), None, HASTA)
    assert r["3M"]["absoluto"] is not None and r["6M"]["absoluto"] is not None
    assert r["1A"]["absoluto"] is None and r["1A"]["motivo"] == "sin datos suficientes"
    assert r["3A"]["absoluto"] is None and r["10A"]["absoluto"] is None


def test_el_anualizado_solo_desde_un_año():
    r = ce.rendimientos(diaria(1.001, 1500), None, HASTA)
    assert r["6M"]["anualizado"] is None and r["3M"]["anualizado"] is None
    assert r["3A"]["anualizado"] == pytest.approx(1.001 ** 365 - 1, rel=1e-3)


def test_las_columnas_largas_solo_con_cobertura():
    assert ce.horizontes_con_cobertura([ce.rendimientos(diaria(1.001, 400), None, HASTA)]) == ["1M", "3M", "6M", "1A"]
    largo = ce.rendimientos(diaria(1.0003, 4000), None, HASTA)
    assert ce.horizontes_con_cobertura([ce.rendimientos(diaria(1.001, 400), None, HASTA), largo])[-2:] == ["5A", "10A"]


def test_un_hueco_en_la_fecha_pedida_no_se_rellena():
    a = [x for x in diaria(1.001, 800) if not (date(2023, 6, 1) <= x[0] <= date(2023, 6, 30))]
    assert ce.rendimientos(a, None, HASTA)["1A"]["absoluto"] is None


def test_una_serie_que_termina_antes_no_tiene_rendimiento_a_la_fecha():
    a = diaria(1.001, 800, hasta=HASTA - timedelta(days=30))
    r = ce.rendimientos(a, None, HASTA)
    assert r["1M"]["absoluto"] is None and r["1M"]["motivo"] == "sin dato cerca de la fecha"


def test_los_meses_se_restan_en_calendario():
    assert ce.restar_meses(date(2024, 3, 31), 1) == date(2024, 2, 29)
    assert ce.restar_meses(date(2024, 1, 15), 13) == date(2022, 12, 15)


# -- riesgo ------------------------------------------------------------------------------------

def test_drawdown_maximo_y_recuperacion_en_semanas():
    sem = semanal_desde([100, 110, 99, 105, 110, 115])
    d = ce.drawdown(sem)
    assert d["maximo"] == pytest.approx(-0.1) and d["fecha_pico"] == viernes(1) and d["fecha_valle"] == viernes(2)
    assert d["recuperacion_semanas"] == 2 and d["en_recuperacion"] is False and d["actual"] == 0.0


def test_drawdown_sin_recuperar():
    d = ce.drawdown(semanal_desde([100, 120, 90, 95]))
    assert d["maximo"] == pytest.approx(-0.25) and d["recuperacion_semanas"] is None and d["en_recuperacion"] is True


def test_drawdown_con_pocos_datos():
    assert ce.drawdown(semanal_desde([100]))["estado"] == "datos_insuficientes"


def test_volatilidad_anualizada():
    rets = [0.01 * (-1) ** i for i in range(20)]
    v = ce.volatilidad_anualizada(rets)
    assert v["anualizada"] == pytest.approx(statistics.stdev(rets) * math.sqrt(52)) and v["n_obs"] == 20
    assert ce.volatilidad_anualizada([0.01] * 5)["estado"] == "datos_insuficientes"
    assert ce.volatilidad_anualizada([0.01] * 20)["anualizada"] == 0.0


def test_los_retornos_semanales_no_cruzan_un_hueco():
    sem = [x for i, x in enumerate(semanal_desde([100, 101, 102, 103, 104])) if i != 2]
    assert ce.retornos_semanales(sem) == pytest.approx([0.01, 104 / 103 - 1])


def test_tendencia_distancia_y_pendiente():
    sem = semanal_desde([100 + i for i in range(60)])
    t = ce.tendencia(sem)
    media = sum(100 + i for i in range(20, 60)) / 40
    assert t["distancia"] == pytest.approx(159 / media - 1) and t["pendiente"] > 0
    assert ce.tendencia(semanal_desde([100 + i for i in range(30)]))["estado"] == "datos_insuficientes"


def test_analizar_junta_todo_y_cada_pieza_tiene_su_estado():
    rs = [1.0] * 40 + crece(1.015, 20)
    a, b = par_desde_rs(rs)
    res = ce.analizar(a, b, hasta=a[-1][0])
    assert set(res) == {"ultima_fecha", "rotacion", "rendimientos", "riesgo", "tendencia"}
    assert res["rotacion"]["estado"] == "ok" and res["ultima_fecha"] == a[-1][0]
    sin_bench = ce.analizar(a, None, hasta=a[-1][0])
    assert sin_bench["rotacion"]["estado"] == "sin_benchmark" and sin_bench["rendimientos"]["3M"]["relativo"] is None


# -- base 100 y comparación --------------------------------------------------------------------

def test_base_100_en_la_primera_fecha_comun():
    a = [(date(2024, 1, d), 10.0 * d) for d in (1, 2, 3, 4)]
    b = [(date(2024, 1, d), 5.0 * d) for d in (2, 3, 4, 5)]
    r = ce.base_100({"a": a, "b": b})
    assert r["fecha_base"] == date(2024, 1, 2)
    assert [f["fecha"].day for f in r["filas"]] == [2, 3, 4]
    assert r["filas"][0]["a"] == 100.0 and r["filas"][-1]["a"] == pytest.approx(200.0) and r["filas"][-1]["b"] == pytest.approx(200.0)


def test_base_100_semanal_toma_el_ultimo_dia_comun_de_la_semana():
    a = diaria(1.001, 30, hasta=date(2024, 1, 31))
    r = ce.base_100({"a": a}, paso="S")
    assert len(r["filas"]) < 30 and r["filas"][-1]["fecha"] == date(2024, 1, 31)
    assert all(f["fecha"].weekday() == 6 for f in r["filas"][:-1])       # el último día (domingo) de cada semana completa


def test_base_100_sin_series_o_con_una_vacia():
    assert ce.base_100({})["filas"] == [] and ce.base_100({"a": [(date(2024, 1, 1), 1.0)], "b": []})["filas"] == []


def test_comparar_usa_el_mismo_periodo_para_todos_y_lo_avisa():
    largo = semanal_desde([100 * 1.01 ** i for i in range(80)])
    corto = semanal_desde([100 * 1.02 ** i for i in range(30)], viernes(50))
    r = ce.comparar({"largo": largo, "corto": corto}, desde=viernes(0), hasta=viernes(79))
    assert r["periodo_ajustado"] is True and r["desde"] == viernes(50)
    assert r["grupos"]["largo"]["retorno"] == pytest.approx(1.01 ** 29 - 1)
    assert r["grupos"]["corto"]["retorno"] == pytest.approx(1.02 ** 29 - 1)


def test_comparar_mantiene_visibles_las_series_sin_datos():
    r = ce.comparar({"a": semanal_desde([100.0] * 20), "vacia": []}, desde=viernes(0), hasta=viernes(19))
    assert r["grupos"]["vacia"]["retorno"] is None and r["grupos"]["vacia"]["motivo"] == "sin datos"


# -- correlaciones -----------------------------------------------------------------------------

def precios_desde_retornos(rets, base=100.0, inicio=VIERNES0):
    precios, p = [base], base
    for r in rets:
        p *= 1 + r
        precios.append(p)
    return semanal_desde(precios, inicio)


RETS = [0.02 * math.sin(i) for i in range(1, 41)]
DESDE, HASTA_C = VIERNES0, viernes(40)


def _par(a_rets, b_rets, **kw):
    res = ce.matriz_correlacion({"a": precios_desde_retornos(a_rets), "b": precios_desde_retornos(b_rets)}, DESDE, HASTA_C, **kw)
    return res["pares"][0], res


def test_correlacion_positiva_perfecta():
    par, _ = _par(RETS, RETS)
    assert par["valor"] == pytest.approx(1.0) and par["n_obs"] == 40


def test_correlacion_negativa_perfecta():
    par, _ = _par(RETS, [-r for r in RETS])
    assert par["valor"] == pytest.approx(-1.0)


def test_correlacion_cercana_a_cero():
    x = [0.01 * (-1) ** i for i in range(40)]
    y = [0.01 * (1 if (i // 2) % 2 == 0 else -1) for i in range(40)]
    par, _ = _par(x, y)
    assert par["valor"] == pytest.approx(0.0, abs=1e-9)


def test_pocas_observaciones_no_dan_correlacion():
    par, res = _par(RETS[:8], RETS[:8])
    assert par["valor"] is None and par["estado"] == "datos_insuficientes" and par["n_obs"] == 8
    assert res["matriz"][0][1] is None and res["matriz"][0][0] == 1.0


def test_periodos_distintos_solo_cuentan_las_semanas_en_comun():
    a = precios_desde_retornos(RETS[:40])                           # semanas 0..40
    b = precios_desde_retornos(RETS[:40], inicio=viernes(20))        # semanas 20..60
    res = ce.matriz_correlacion({"a": a, "b": b}, DESDE, viernes(60))
    par = res["pares"][0]
    assert par["n_obs"] == 20                                       # retornos de las semanas 21..40
    assert res["periodo"]["desde"] == viernes(1) and res["periodo"]["hasta"] == viernes(60)


def test_la_matriz_es_simetrica_y_informa_muestra_y_periodo():
    series = {k: precios_desde_retornos([r * m for r in RETS]) for k, m in (("a", 1), ("b", 2), ("c", -1))}
    res = ce.matriz_correlacion(series, DESDE, HASTA_C)
    m = res["matriz"]
    assert m[0][1] == m[1][0] and m[0][2] == pytest.approx(-1.0) and res["ids"] == ["a", "b", "c"]
    assert res["frecuencia"] == "semanal" and res["n_periodos"] == 40


def test_un_hueco_de_datos_no_se_encadena_en_los_retornos():
    sem = [x for i, x in enumerate(precios_desde_retornos(RETS)) if i != 10]
    rets = ce.retornos_en_grilla(sem, ce.grilla_semanal(DESDE, HASTA_C), 3)
    assert viernes(10) not in rets and viernes(11) not in rets and len(rets) == 38


def test_un_feriado_el_viernes_usa_el_dia_anterior_dentro_de_la_tolerancia():
    sem = [(f - timedelta(days=1) if i == 5 else f, v) for i, (f, v) in enumerate(precios_desde_retornos(RETS))]
    rets = ce.retornos_en_grilla(sem, ce.grilla_semanal(DESDE, HASTA_C), 3)
    assert viernes(5) in rets and len(rets) == 40
    assert ce.retornos_en_grilla(sem, ce.grilla_semanal(DESDE, HASTA_C), 0).get(viernes(5)) is None


def test_correlacion_diaria_sobre_la_grilla_de_ruedas():
    ruedas = [date(2024, 3, 1) + timedelta(days=i) for i in range(60) if (date(2024, 3, 1) + timedelta(days=i)).weekday() < 5]
    rets = [0.01 * math.sin(i) for i in range(len(ruedas) - 1)]
    precios, p = [100.0], 100.0
    for r in rets:
        p *= 1 + r
        precios.append(p)
    a = list(zip(ruedas, precios))
    res = ce.matriz_correlacion({"a": a, "b": a}, ruedas[0], ruedas[-1], "diaria", grilla_diaria=ruedas)
    assert res["pares"][0]["valor"] == pytest.approx(1.0) and res["frecuencia"] == "diaria"
    assert res["n_periodos"] == len(ruedas) - 1


# -- desfases ----------------------------------------------------------------------------------

def test_un_desfase_conocido_se_recupera_en_el_k_correcto():
    rnd = random.Random(7)
    r = [rnd.uniform(-0.03, 0.03) for _ in range(90)]
    b_rets = [rnd.uniform(-0.03, 0.03) for _ in range(3)] + r[:-3]          # b repite a con 3 semanas de atraso
    a, b = precios_desde_retornos(r), precios_desde_retornos(b_rets)
    res = ce.desfases(a, b, DESDE, viernes(90))
    assert res["mejor"]["desfase_semanas"] == 3 and res["mejor"]["valor"] > 0.95
    assert len(res["desfases"]) == 17 and res["desfases"][0]["desfase_semanas"] == -8
    fila0 = next(f for f in res["desfases"] if f["desfase_semanas"] == 0)
    assert not fila0["supera_azar"] and fila0["n_obs"] == 90
    assert res["banda_azar"] == pytest.approx(1.96 / math.sqrt(90))


def test_el_signo_del_desfase_indica_quien_va_primero():
    rnd = random.Random(11)
    r = [rnd.uniform(-0.03, 0.03) for _ in range(90)]
    b_rets = r[3:] + [rnd.uniform(-0.03, 0.03) for _ in range(3)]            # ahora es `b` quien va primero
    res = ce.desfases(precios_desde_retornos(r), precios_desde_retornos(b_rets), DESDE, viernes(90))
    assert res["mejor"]["desfase_semanas"] == -3


def test_desfases_con_pocos_datos():
    res = ce.desfases(precios_desde_retornos(RETS[:10]), precios_desde_retornos(RETS[:10]), DESDE, viernes(10))
    assert res["mejor"] is None and all(f["valor"] is None for f in res["desfases"])


# -- sintético ---------------------------------------------------------------------------------

def test_sintetico_equiponderado_encadena_el_promedio_de_retornos():
    a = semanal_desde([100, 110, 121])
    b = semanal_desde([100, 100, 110])
    s = ce.sintetico_equiponderado([a, b])
    assert [round(v, 6) for _, v in s] == [100.0, 105.0, 115.5]     # (10% + 0%)/2 = 5%; luego (10% + 10%)/2 = 10%


def test_sintetico_no_rellena_una_semana_sin_dato_de_algun_miembro():
    a = semanal_desde([100, 110, 121])
    b = [x for i, x in enumerate(semanal_desde([100, 105, 100])) if i != 1]
    s = ce.sintetico_equiponderado([a, b])
    assert [f for f, _ in s] == [viernes(0), viernes(2)]            # no hay punto en la semana 1
    assert s[1][1] == pytest.approx(100 * (1 + (0.21 + 0.0) / 2))


def test_sintetico_sin_miembros_con_datos():
    assert ce.sintetico_equiponderado([semanal_desde([100, 101]), []]) == []


# -- país --------------------------------------------------------------------------------------

D0, D1 = date(2024, 1, 2), date(2024, 6, 28)


def _dos_puntos(v0, v1):
    return [(D0, v0), (D1, v1)]


def test_descomposicion_local_por_usd():
    r = ce.descomponer_pais(_dos_puntos(100, 110), _dos_puntos(1000, 1200), _dos_puntos(5.0, 5.5), "local_por_usd", D0, D1)
    assert r["proxy_usd"] == pytest.approx(0.10) and r["indice_local"] == pytest.approx(0.20)
    assert r["efecto_fx"] == pytest.approx(1 / 1.1 - 1)
    assert r["indice_local_usd"] == pytest.approx(1.2 / 1.1 - 1)
    assert r["diferencia_vehiculo"] == pytest.approx(0.10 - (1.2 / 1.1 - 1)) and r["completa"] is True


def test_descomposicion_usd_por_local():
    r = ce.descomponer_pais(_dos_puntos(100, 110), _dos_puntos(1000, 1200), _dos_puntos(1.0, 1.1), "usd_por_local", D0, D1)
    assert r["efecto_fx"] == pytest.approx(0.10) and r["indice_local_usd"] == pytest.approx(1.2 * 1.1 - 1)


def test_una_moneda_que_no_cambio_no_agrega_efecto():
    r = ce.descomponer_pais(_dos_puntos(100, 110), _dos_puntos(1000, 1100), _dos_puntos(5.0, 5.0), "local_por_usd", D0, D1)
    assert r["efecto_fx"] == pytest.approx(0.0) and r["diferencia_vehiculo"] == pytest.approx(0.0)


def test_sin_tipo_de_cambio_no_se_estima_el_efecto():
    r = ce.descomponer_pais(_dos_puntos(100, 110), _dos_puntos(1000, 1200), None, None, D0, D1)
    assert r["efecto_fx"] is None and r["indice_local_usd"] is None and r["diferencia_vehiculo"] is None
    assert r["completa"] is False and "tipo de cambio" in r["motivos"]["efecto_fx"]
    assert r["proxy_usd"] == pytest.approx(0.10) and r["indice_local"] == pytest.approx(0.20)


def test_un_indice_local_desactualizado_queda_sin_dato_y_lo_dice():
    viejo = [(D0, 1000.0), (date(2024, 5, 1), 1100.0)]
    r = ce.descomponer_pais(_dos_puntos(100, 110), viejo, _dos_puntos(5.0, 5.5), "local_por_usd", D0, D1)
    assert r["indice_local"] is None and r["completa"] is False
    assert "2024-05-01" in r["motivos"]["indice_local"]


def test_sin_indice_local():
    r = ce.descomponer_pais(_dos_puntos(100, 110), None, None, None, D0, D1)
    assert r["proxy_usd"] == pytest.approx(0.10) and r["indice_local"] is None and not r["completa"]
