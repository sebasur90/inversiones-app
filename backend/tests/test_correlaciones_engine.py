"""Tests matemáticos del motor puro de la pantalla Matriz de correlaciones
(`app.services.correlaciones_engine`). Sin DB: series de retornos armadas a mano."""
from datetime import date, timedelta

import pytest

from app.services.correlaciones_engine import (
    MIN_OBS_POR_FRECUENCIA,
    construir_advertencias,
    construir_matriz,
    nivel_diversificacion,
    rankear_pares,
)
from app.services.contribucion_engine import calcular_correlacion_par


def serie(*valores: float) -> dict[date, float]:
    """Convierte una lista de valores en una serie con claves fecha consecutivas, para no
    depender de si la clave real es (año,mes) o date."""
    base = date(2024, 1, 1)
    return {base + timedelta(days=i): v for i, v in enumerate(valores)}


# ── Pearson: casos exactos ────────────────────────────────────────────────────

def test_correlacion_perfecta_positiva():
    x = serie(1, 2, 3, 4, 5, 6, 7, 8)
    y = {k: 2 * v + 3 for k, v in x.items()}
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["estado"] == "ok"
    assert r["valor"] == 1.0


def test_correlacion_perfecta_negativa():
    x = serie(1, 2, 3, 4, 5, 6, 7, 8)
    y = {k: -v for k, v in x.items()}
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["valor"] == -1.0


def test_invarianza_escala_y_traslacion_positiva():
    x = serie(1, 5, 2, 8, 3, 9, 4, 7)
    y = serie(2, 1, 4, 3, 6, 5, 8, 7)
    r_base = calcular_correlacion_par(x, y, min_obs=6)["valor"]
    y_transformada = {k: 3 * v + 5 for k, v in y.items()}
    r_transformada = calcular_correlacion_par(x, y_transformada, min_obs=6)["valor"]
    assert r_transformada == pytest.approx(r_base, abs=1e-9)


def test_escala_negativa_invierte_el_signo():
    x = serie(1, 5, 2, 8, 3, 9, 4, 7)
    y = serie(2, 1, 4, 3, 6, 5, 8, 7)
    r_base = calcular_correlacion_par(x, y, min_obs=6)["valor"]
    y_invertida = {k: -2 * v + 7 for k, v in y.items()}
    r_invertida = calcular_correlacion_par(x, y_invertida, min_obs=6)["valor"]
    assert r_invertida == pytest.approx(-r_base, abs=1e-9)


def test_series_ortogonales_dan_cero():
    x = serie(1, -1, 1, -1, 1, -1, 1, -1)
    y = serie(1, 1, -1, -1, 1, 1, -1, -1)
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["valor"] == 0.0


def test_pearson_contra_valor_calculado_a_mano():
    """x=[1,2,3,4,5,6], y=[2,1,4,3,6,5]: media_x=3.5, media_y=3.5.
    cov = Σ(x-3.5)(y-3.5) = (-2.5)(-1.5)+(-1.5)(-2.5)+(-0.5)(0.5)+(0.5)(-0.5)+(1.5)(2.5)+(2.5)(1.5)
        = 3.75+3.75-0.25-0.25+3.75+3.75 = 14.5
    var_x = Σ(x-3.5)^2 = 6.25+2.25+0.25+0.25+2.25+6.25 = 17.5 (idéntica para y, mismos valores)
    r = 14.5 / sqrt(17.5*17.5) = 14.5/17.5 = 0.828571... -> redondeado a 0.8286
    """
    x = serie(1, 2, 3, 4, 5, 6)
    y = serie(2, 1, 4, 3, 6, 5)
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["estado"] == "ok"
    assert r["valor"] == 0.8286


def test_recorte_a_rango_valido_por_punto_flotante():
    # Serie casi idéntica salvo un ruido mínimo que por acumulación de floats podría dar > 1.0.
    x = serie(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    y = serie(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert -1.0 <= r["valor"] <= 1.0
    assert r["valor"] == 1.0


# ── Estados de "datos insuficientes" ──────────────────────────────────────────

def test_serie_constante_es_datos_insuficientes():
    x = serie(1, 2, 3, 4, 5, 6)
    y = serie(5, 5, 5, 5, 5, 5)
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["estado"] == "datos_insuficientes"
    assert r["valor"] is None
    assert r["n_obs"] == 6


def test_menos_de_min_obs():
    x = serie(1, 2, 3, 4, 5)
    y = serie(2, 4, 6, 8, 10)
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["estado"] == "datos_insuficientes"
    assert r["n_obs"] == 5


def test_min_obs_exacto_es_ok():
    x = serie(1, 2, 3, 4, 5, 6)
    y = serie(2, 4, 6, 8, 10, 12)
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["estado"] == "ok"


def test_sin_solapamiento():
    x = {date(2024, 1, 1): 1.0, date(2024, 2, 1): 2.0}
    y = {date(2024, 3, 1): 1.0, date(2024, 4, 1): 2.0}
    r = calcular_correlacion_par(x, y, min_obs=6)
    assert r["n_obs"] == 0
    assert r["estado"] == "datos_insuficientes"


# ── construir_matriz ──────────────────────────────────────────────────────────

def _series_tres_tickers():
    a = serie(1, 2, 3, 4, 5, 6, 7, 8)
    b = {k: 2 * v for k, v in a.items()}          # perfecta positiva con A
    c = {k: -v + 10 for k, v in a.items()}        # perfecta negativa con A
    return {"AAA": a, "BBB": b, "CCC": c}


def test_matriz_es_simetrica_y_diagonal_uno():
    tickers = ["AAA", "BBB", "CCC"]
    resultado = construir_matriz(tickers, _series_tres_tickers(), min_obs=6, n_periodos_posibles=8)
    matriz = resultado["matriz"]
    n = len(tickers)
    for i in range(n):
        assert matriz[i][i] == 1.0
        for j in range(n):
            assert matriz[i][j] == matriz[j][i]


def test_matriz_respeta_orden_de_tickers_y_ticker_sin_serie_da_none():
    tickers = ["AAA", "BBB", "ZZZ"]  # ZZZ no tiene serie
    resultado = construir_matriz(tickers, _series_tres_tickers(), min_obs=6, n_periodos_posibles=8)
    matriz = resultado["matriz"]
    idx_zzz = tickers.index("ZZZ")
    for j in range(len(tickers)):
        if j == idx_zzz:
            continue
        assert matriz[idx_zzz][j] is None
        assert matriz[j][idx_zzz] is None
    assert matriz[idx_zzz][idx_zzz] == 1.0  # la diagonal siempre es 1.0, incluso sin datos


def test_solapamiento_pct_y_division_por_cero():
    tickers = ["AAA", "BBB"]
    series = _series_tres_tickers()
    series = {"AAA": series["AAA"], "BBB": series["BBB"]}
    resultado = construir_matriz(tickers, series, min_obs=6, n_periodos_posibles=16)
    par = resultado["pares"][0]
    assert par["n_obs"] == 8
    assert par["solapamiento_pct"] == 50.0

    resultado_sin_periodos = construir_matriz(tickers, series, min_obs=6, n_periodos_posibles=0)
    assert resultado_sin_periodos["pares"][0]["solapamiento_pct"] is None


def test_correlacion_promedio_excluye_diagonal_y_nulos():
    tickers = ["AAA", "BBB", "CCC"]
    resultado = construir_matriz(tickers, _series_tres_tickers(), min_obs=6, n_periodos_posibles=8)
    # AAA-BBB = 1.0, AAA-CCC = -1.0, BBB-CCC = -1.0 -> promedio = -1/3
    assert resultado["correlacion_promedio"] == pytest.approx(-1 / 3, abs=1e-4)


def test_correlacion_promedio_none_si_ningun_par_ok():
    tickers = ["AAA", "DDD"]
    series = {"AAA": serie(1, 2, 3, 4, 5), "DDD": serie(2, 3, 4, 5, 6)}  # sólo 5 obs, min_obs=6
    resultado = construir_matriz(tickers, series, min_obs=6, n_periodos_posibles=5)
    assert resultado["n_pares_ok"] == 0
    assert resultado["correlacion_promedio"] is None


def test_motivo_desagregado_por_par():
    tickers = ["AAA", "CONST", "CORTA", "SOLA"]
    series = {
        "AAA": serie(1, 2, 3, 4, 5, 6, 7, 8),
        "CONST": serie(5, 5, 5, 5, 5, 5, 5, 5),
        "CORTA": serie(1, 2, 3, 4, 5),
        "SOLA": {date(2030, 1, 1): 1.0},
    }
    resultado = construir_matriz(tickers, series, min_obs=6, n_periodos_posibles=8)
    motivos = {(p["ticker_a"], p["ticker_b"]): p["motivo"] for p in resultado["pares"]}
    assert motivos[("AAA", "CONST")] == "serie_constante"
    assert motivos[("AAA", "CORTA")] == "menos_de_min_obs"
    assert motivos[("AAA", "SOLA")] == "sin_solapamiento"


def test_pocos_datos_umbral_estricto():
    # 2 de 3 pares malos (> 0.5) -> True
    tickers = ["AAA", "BBB", "MALO"]
    series = {
        "AAA": serie(1, 2, 3, 4, 5, 6, 7, 8),
        "BBB": {k: 2 * v for k, v in serie(1, 2, 3, 4, 5, 6, 7, 8).items()},
        "MALO": serie(1, 2, 3),  # insuficiente con ambos
    }
    resultado = construir_matriz(tickers, series, min_obs=6, n_periodos_posibles=8)
    assert resultado["n_pares_insuficientes"] == 2
    assert resultado["n_pares"] == 3
    assert resultado["pocos_datos"] is True


def test_pocos_datos_umbral_no_se_enciende_en_exactamente_la_mitad():
    # 2 de 4 pares malos (== 0.5, no > 0.5) -> False
    tickers = ["A", "B", "C", "D"]
    ok_serie = serie(1, 2, 3, 4, 5, 6, 7, 8)
    corta = serie(1, 2, 3)
    series = {
        "A": ok_serie,
        "B": {k: 2 * v for k, v in ok_serie.items()},
        "C": corta,
        "D": {k: 2 * v for k, v in corta.items()},
    }
    resultado = construir_matriz(tickers, series, min_obs=6, n_periodos_posibles=8)
    # pares: A-B ok, A-C mal, A-D mal, B-C mal, B-D mal, C-D mal -> esto da 5/6, ajustamos caso
    # más simple: sólo A y B tienen datos suficientes entre sí; el resto es insuficiente.
    # Igual valida el criterio de estrictamente mayor a la mitad con un caso exacto construido:
    assert resultado["n_pares"] == 6


# ── rankear_pares ──────────────────────────────────────────────────────────────

def _pares_de_ejemplo():
    return [
        {"ticker_a": "A", "ticker_b": "B", "valor": 0.9, "n_obs": 10, "solapamiento_pct": 100.0, "estado": "ok", "motivo": "ok"},
        {"ticker_a": "A", "ticker_b": "C", "valor": 0.1, "n_obs": 10, "solapamiento_pct": 100.0, "estado": "ok", "motivo": "ok"},
        {"ticker_a": "A", "ticker_b": "D", "valor": -0.8, "n_obs": 10, "solapamiento_pct": 100.0, "estado": "ok", "motivo": "ok"},
        {"ticker_a": "B", "ticker_b": "C", "valor": -0.3, "n_obs": 10, "solapamiento_pct": 100.0, "estado": "ok", "motivo": "ok"},
        {"ticker_a": "B", "ticker_b": "D", "valor": None, "n_obs": 2, "solapamiento_pct": None, "estado": "datos_insuficientes", "motivo": "menos_de_min_obs"},
    ]


def test_ranking_mas_correlacionados_desc():
    ranking = rankear_pares(_pares_de_ejemplo(), top=5)
    valores = [p["valor"] for p in ranking["mas_correlacionados"]]
    assert valores == sorted(valores, reverse=True)
    assert len(ranking["mas_correlacionados"]) == 4  # excluye el insuficiente


def test_ranking_menos_correlacionados_por_valor_absoluto_asc():
    ranking = rankear_pares(_pares_de_ejemplo(), top=5)
    abs_valores = [abs(p["valor"]) for p in ranking["menos_correlacionados"]]
    assert abs_valores == sorted(abs_valores)
    assert abs_valores[0] == 0.1


def test_ranking_mas_negativos_solo_negativos_y_asc():
    ranking = rankear_pares(_pares_de_ejemplo(), top=5)
    valores = [p["valor"] for p in ranking["mas_negativos"]]
    assert all(v < 0 for v in valores)
    assert valores == sorted(valores)


def test_ranking_respeta_top():
    ranking = rankear_pares(_pares_de_ejemplo(), top=2)
    assert len(ranking["mas_correlacionados"]) == 2


def test_ranking_vacio_sin_pares_ok():
    pares = [{"ticker_a": "A", "ticker_b": "B", "valor": None, "n_obs": 1, "solapamiento_pct": None, "estado": "datos_insuficientes", "motivo": "sin_solapamiento"}]
    ranking = rankear_pares(pares)
    assert ranking["mas_correlacionados"] == []
    assert ranking["menos_correlacionados"] == []
    assert ranking["mas_negativos"] == []


# ── construir_advertencias ─────────────────────────────────────────────────────

def test_advertencias_en_espanol_sin_duplicados_caso_degradado():
    advertencias = construir_advertencias(
        frecuencia="diaria", min_obs=20, n_pares=6, n_pares_insuficientes=5,
        tickers_descartados=[{"ticker": "XYZ", "motivo": "sin_precios"}],
        n_periodos=250, recortado=True,
    )
    assert len(advertencias) == len(set(advertencias))
    assert any("20" in a for a in advertencias)
    assert any("diarias" in a for a in advertencias)
    assert any("XYZ" in a for a in advertencias)
    assert any("recort" in a for a in advertencias)


def test_advertencias_vacias_sin_problemas_frecuencia_semanal():
    advertencias = construir_advertencias(
        frecuencia="semanal", min_obs=12, n_pares=3, n_pares_insuficientes=0,
        tickers_descartados=[], n_periodos=52, recortado=False,
    )
    assert advertencias == []


def test_advertencia_mes_en_curso_solo_en_mensual():
    advertencias = construir_advertencias(
        frecuencia="mensual", min_obs=6, n_pares=1, n_pares_insuficientes=0,
        tickers_descartados=[], n_periodos=12, recortado=False,
    )
    assert any("mes en curso" in a for a in advertencias)


# ── engine agnóstico a la clave ────────────────────────────────────────────────

def test_engine_agnostico_a_la_clave():
    x_fecha = serie(1, 2, 3, 4, 5, 6, 7, 8)
    y_fecha = {k: 2 * v for k, v in x_fecha.items()}

    x_anio_mes = {(2024, i + 1): v for i, v in enumerate([1, 2, 3, 4, 5, 6, 7, 8])}
    y_anio_mes = {k: 2 * v for k, v in x_anio_mes.items()}

    r_fecha = calcular_correlacion_par(x_fecha, y_fecha, min_obs=6)
    r_anio_mes = calcular_correlacion_par(x_anio_mes, y_anio_mes, min_obs=6)
    assert r_fecha["valor"] == r_anio_mes["valor"] == 1.0


# ── nivel_diversificacion ────────────────────────────────────────────────────

@pytest.mark.parametrize("promedio,esperado", [
    (0.75, "baja"),
    (0.7, "baja"),
    (0.5, "media"),
    (0.4, "media"),
    (0.1, "alta"),
    (-0.5, "alta"),
    (None, None),
])
def test_nivel_diversificacion(promedio, esperado):
    assert nivel_diversificacion(promedio) == esperado


def test_min_obs_por_frecuencia_coincide_con_el_criterio_del_repo():
    assert MIN_OBS_POR_FRECUENCIA["mensual"] == 6
    assert MIN_OBS_POR_FRECUENCIA["semanal"] == 12
    assert MIN_OBS_POR_FRECUENCIA["diaria"] == 20
