"""Efectividad histórica de cada estado del ciclo: qué rindió el grupo contra su referencia después de estar en cada estado.

Series sintéticas de resultado conocido (`ciclos_helpers`). Lo que se prueba: que el rendimiento posterior sea exactamente
`RS[t+h]/RS[t] − 1`, que el estado de cada semana no mire el futuro, que los episodios no se confundan con las semanas y que
con pocos episodios no se calcule ningún promedio.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.services import ciclos_efectividad_engine as ee
from app.services import ciclos_engine as eng

from .ciclos_helpers import SEMANAS, benchmark, cartera_de_prueba, con_rs, perfil

PROHIBIDO = re.compile(r"compr\w*|vend\w*|recomend\w*|conviene|deber[ií]a|oportunidad", re.IGNORECASE)

# Varias idas y vueltas de fortaleza relativa: pasa por los cuatro cuadrantes más de una vez.
ONDAS = perfil(("plano", 30), ("crece", 1.03, 35), ("crece", 0.97, 35), ("crece", 1.03, 35), ("crece", 0.97, 35))


def _series(rs=None):
    b = benchmark()
    return con_rs(b, rs or ONDAS), b


def _obs(rs=None, clave="g"):
    a, b = _series(rs)
    return ee.observaciones(a, b, clave)


# -- estadísticas ---------------------------------------------------------------------------------

def test_estadisticas_con_numeros_conocidos():
    e = ee.estadisticas([-0.02, 0.0, 0.01, 0.03, 0.05, 0.06], episodios=6)
    assert e["suficiente"] and e["n"] == 6 and e["episodios"] == 6
    assert e["mediana"] == pytest.approx(0.02) and e["media"] == pytest.approx(0.0216666, abs=1e-6)
    assert e["positivos_pct"] == pytest.approx(100 * 4 / 6)
    assert e["p25"] == pytest.approx(0.0025) and e["p75"] == pytest.approx(0.045)


def test_con_pocos_episodios_no_se_calcula_ningun_promedio():
    e = ee.estadisticas([0.1] * 40, episodios=ee.MIN_EPISODIOS - 1)       # muchas semanas, pocos episodios
    assert e["n"] == 40 and e["suficiente"] is False
    assert e["mediana"] is None and e["media"] is None and e["positivos_pct"] is None


# -- observaciones --------------------------------------------------------------------------------

def test_el_rendimiento_posterior_es_el_cociente_relativo_exacto():
    a, b = _series()
    t = ee.observaciones(a, b, "g")
    semanal = eng.semanal_comun(eng.normalizar(a), eng.normalizar(b))
    por_fecha = {f: i for i, (f, _, _) in enumerate(semanal)}
    rs = [x / y for _, x, y in semanal]
    assert t["obs"]
    for o in t["obs"][::17]:
        k = por_fecha[o["fecha"]]
        for h, valor in o["fwd"].items():
            assert valor == pytest.approx(rs[k + h] / rs[k] - 1)
            assert valor == pytest.approx((semanal[k + h][1] / semanal[k][1]) / (semanal[k + h][2] / semanal[k][2]) - 1)


def test_las_ultimas_semanas_no_tienen_horizonte_largo():
    t = _obs()
    ultima = t["obs"][-1]
    assert ultima["fwd"] == {}                                           # no hay "después" para la última semana
    assert 26 not in t["obs"][-10]["fwd"] and 4 in t["obs"][-10]["fwd"]


def test_el_estado_de_una_semana_no_mira_el_futuro():
    a, b = _series()
    completa = ee.observaciones(a, b, "g")["obs"]
    corte = completa[len(completa) // 2]["fecha"]
    parcial = ee.observaciones([x for x in a if x[0] <= corte], [x for x in b if x[0] <= corte], "g")["obs"]
    comparables = {o["fecha"]: (o["cuadrante"], o["confirma"]) for o in completa if o["fecha"] <= corte}
    # Lo que se calcula con datos hasta `corte` coincide con lo que dice la serie completa para esas mismas semanas.
    # (la última barra semanal puede quedar incompleta al cortar a mitad de semana: se compara sin ella)
    for o in parcial[:-1]:
        assert comparables[o["fecha"]] == (o["cuadrante"], o["confirma"])
    assert len(parcial) > 20


def test_cada_estado_confirmado_se_sostuvo_al_menos_tres_semanas():
    t = _obs()["obs"]
    corridas, previo, n = [], None, 0
    for o in t:
        if o["episodio"] != previo:
            if previo is not None:
                corridas.append(n)
            previo, n = o["episodio"], 0
        n += 1
    corridas.append(n)
    assert len(corridas) >= 3 and all(c >= eng.CONFIRMACION_SEMANAS for c in corridas)


def test_el_primer_estado_confirmado_no_cuenta_como_cambio():
    t = _obs()["obs"]
    assert t[0]["confirma"] is False and sum(o["confirma"] for o in t) == len({o["episodio"] for o in t}) - 1


def test_pocas_semanas_dice_el_motivo_y_no_inventa():
    b = benchmark(semanas=30)
    t = ee.observaciones(con_rs(b, perfil(("plano", 30), semanas=30)), b, "g")
    assert t["obs"] == [] and "pocas semanas" in t["motivo"]


# -- resumen --------------------------------------------------------------------------------------

def test_el_resumen_junta_episodios_de_varios_grupos_sin_confundirlos():
    uno, dos = _obs(clave="uno"), _obs(clave="dos")
    solo = ee.resumir([uno])
    junto = ee.resumir([uno, dos])
    for a, j in zip(solo["por_estado"], junto["por_estado"]):
        assert j["episodios"] == 2 * a["episodios"] and j["semanas"] == 2 * a["semanas"]


def test_el_resumen_compara_cada_estado_contra_la_base():
    r = ee.resumir([_obs(clave=f"g{i}") for i in range(5)])         # 5 grupos: alcanzan los episodios mínimos por estado
    assert r["horizontes_semanas"] == [4, 13, 26] and r["semanas_analizadas"] > 500
    assert [e["cuadrante"] for e in r["por_estado"]] == list(eng.CUADRANTES)
    suficientes = [e["horizontes"][13] for e in r["por_estado"] if e["horizontes"][13]["suficiente"]]
    assert suficientes
    for e in suficientes:
        assert e["mediana_vs_base"] == pytest.approx(e["mediana"] - r["base"][13]["mediana"])


def test_un_grupo_siempre_igual_no_tiene_ventaja_sobre_la_base():
    r = ee.resumir([_obs(rs=[1.0] * SEMANAS)])
    assert r["semanas_analizadas"] == 0 or all(not e["horizontes"][13]["suficiente"] for e in r["por_estado"])


# -- API ------------------------------------------------------------------------------------------

URL = "/api/inversiones"


@pytest.fixture
def client(tmp_path, monkeypatch):
    sesion = cartera_de_prueba(tmp_path, monkeypatch)

    def override():
        s = sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_de_un_grupo(client):
    r = client.get(f"{URL}/ciclos/grupos/tecnologia/efectividad")
    assert r.status_code == 200
    d = r.json()
    assert d["alcance"] == "grupo" and d["grupo"]["id"] == "tecnologia" and d["benchmark"]["id"] == "estados-unidos"
    assert d["estado"] in ("ok", "datos_insuficientes")
    assert d["meta"]["moneda"] == "USD" and d["min_episodios"] == ee.MIN_EPISODIOS


def test_api_por_tipo_junta_todos_los_sectores(client):
    d = client.get(f"{URL}/ciclos/grupos/tecnologia/efectividad", params={"alcance": "tipo"}).json()
    assert d["alcance"] == "tipo"
    assert {g["id"] for g in d["grupos"]} >= {"tecnologia", "salud", "energia", "consumo-basico"}
    assert any("independientes" in a for a in d["meta"]["advertencias"])


def test_api_errores(client):
    assert client.get(f"{URL}/ciclos/grupos/no-existe/efectividad").status_code == 404
    assert client.get(f"{URL}/ciclos/grupos/tecnologia/efectividad", params={"alcance": "otro"}).status_code == 422


def test_api_no_recomienda_nada(client):
    d = client.get(f"{URL}/ciclos/grupos/tecnologia/efectividad", params={"alcance": "tipo"}).json()
    textos = [d["lectura"], *d["meta"]["advertencias"], *d["meta"]["limitaciones"]]
    assert not [t for t in textos if PROHIBIDO.search(t)]
