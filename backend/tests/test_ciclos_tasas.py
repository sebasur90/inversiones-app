"""Tasas de interés en «Ciclos de mercado»: catálogo, ingesta (el cero es un dato válido, no hay reajuste), cambios en
puntos porcentuales, pendiente de la curva, desfases con una tasa y API. Series sintéticas de resultado conocido."""
import copy
import json
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, BarraOHLCV, get_db
from app.main import app
from app.services import ciclos_catalogo as cc
from app.services import ciclos_engine as eng
from app.services import ciclos_ingesta as ci
from app.services import ciclos_tasas_engine as te
from app.services.cache import limpiar_cache
from app.services.market_data import yahoo

from .ciclos_helpers import DOC, benchmark, cargar_series, escribir_catalogo, fin, series_basicas

PROHIBIDO = re.compile(r"compr\w*|vend\w*|recomend\w*|conviene|deber[ií]a|pronostic\w*|recesi[oó]n", re.IGNORECASE)

TASAS = [
    {"id": "tasa-3m", "nombre": "Tesoro 3 meses", "simbolo": "^IRX", "plazo_meses": 3},
    {"id": "tasa-10a", "nombre": "Tesoro 10 años", "simbolo": "^TNX", "plazo_meses": 120},
    {"id": "tasa-30a", "nombre": "Tesoro 30 años", "simbolo": "^TYX", "plazo_meses": 360},
]
PENDIENTES = [{"id": "10a-3m", "nombre": "10 años − 3 meses", "larga": "tasa-10a", "corta": "tasa-3m"}]


def _doc(**extra):
    d = copy.deepcopy(DOC)
    d["tasas"] = copy.deepcopy(TASAS)
    d["pendientes_curva"] = copy.deepcopy(PENDIENTES)
    d["pares_desfase"] = [{"id": "tasa-fin", "nombre": "Tasa 10 años → tecnología", "grupos": ["tasa-10a", "tecnologia"], "nota": "n"}]
    d.update(extra)
    return d


# -- catálogo ------------------------------------------------------------------------------------

def test_el_catalogo_real_trae_las_cuatro_tasas_y_sus_pares():
    cat = cc.cargar()
    assert {"tasa-3m", "tasa-5a", "tasa-10a", "tasa-30a"} <= set(cat.tasas)
    assert {t.simbolo for t in cat.tasas_activas()} >= {"^IRX", "^FVX", "^TNX", "^TYX"}
    assert [t.plazo_meses for t in cat.tasas_activas()] == sorted(t.plazo_meses for t in cat.tasas_activas())
    assert any(p["grupos"][0] == "tasa-10a" for p in cat.pares_desfase)
    assert {p["id"] for p in cat.pendientes_curva} == {"10a-3m", "30a-5a"}
    assert not [e for e in cat.errores if "tasa" in e or "pendiente" in e or "comparación" in e]


def test_las_tasas_son_simbolos_a_descargar_con_su_propio_rol():
    cat = cc.construir(_doc())
    s = cat.simbolos()
    assert s["^TNX"].rol == cc.ROL_TASA and s["^TNX"].moneda == cc.MONEDA_TASA
    assert s["XLK"].rol == cc.ROL_PROXY


def test_una_tasa_invalida_se_descarta_sola():
    malas = [
        {"id": "mala-1", "nombre": "Sin plazo", "simbolo": "^X1", "plazo_meses": 0},
        {"id": "mala-2", "nombre": "Símbolo repetido", "simbolo": "^TNX", "plazo_meses": 24},
        {"id": "tecnologia", "nombre": "Choca con un grupo", "simbolo": "^X3", "plazo_meses": 12},
        {"id": "Mala 4", "nombre": "Id inválido", "simbolo": "^X4", "plazo_meses": 12},
    ]
    cat = cc.construir(_doc(tasas=TASAS + malas))
    assert set(cat.tasas) == {"tasa-3m", "tasa-10a", "tasa-30a"} and len(cat.errores) == 4


def test_una_pendiente_exige_la_larga_con_mayor_plazo():
    al_reves = [{"id": "x", "nombre": "X", "larga": "tasa-3m", "corta": "tasa-10a"},
                {"id": "y", "nombre": "Y", "larga": "no-existe", "corta": "tasa-3m"}]
    cat = cc.construir(_doc(pendientes_curva=PENDIENTES + al_reves))
    assert [p["id"] for p in cat.pendientes_curva] == ["10a-3m"] and len(cat.errores) == 2


def test_un_par_de_desfase_acepta_una_tasa_pero_no_una_inexistente():
    cat = cc.construir(_doc(pares_desfase=[
        {"id": "ok", "nombre": "ok", "grupos": ["tasa-10a", "tecnologia"]},
        {"id": "mal", "nombre": "mal", "grupos": ["tasa-99a", "tecnologia"]},
    ]))
    assert [p["id"] for p in cat.pares_desfase] == ["ok"]


# -- motor ---------------------------------------------------------------------------------------

def test_un_nivel_conserva_el_cero_y_lo_negativo_un_precio_no():
    serie = [(date(2024, 1, 1), 0.0), (date(2024, 1, 2), -0.1), (date(2024, 1, 3), 1.5), (date(2024, 1, 4), float("nan"))]
    assert [v for _, v in eng.normalizar_nivel(serie)] == [0.0, -0.1, 1.5]
    assert [v for _, v in eng.normalizar(serie)] == [1.5]


def test_el_cambio_en_grilla_es_una_diferencia_no_un_rendimiento():
    viernes = [date(2024, 1, 5), date(2024, 1, 12), date(2024, 1, 19)]
    serie = [(viernes[0], 0.10), (viernes[1], 0.20), (viernes[2], 0.0)]
    cambios = eng.cambios_en_grilla(serie, viernes, 3)
    assert cambios[viernes[1]] == pytest.approx(0.10) and cambios[viernes[2]] == pytest.approx(-0.20)


def test_cambio_pp_en_puntos_y_sin_acortar_el_periodo():
    serie = [(date(2024, 1, 2) + timedelta(days=i), 4.0 + i * 0.01) for i in range(400)]
    hasta = serie[-1][0]
    r = te.cambios(serie, hasta)
    assert r["1M"]["pp"] == pytest.approx(0.30, abs=0.04) and r["1M"]["motivo"] is None
    corta = serie[-60:]
    assert te.cambios(corta, hasta)["1A"]["pp"] is None and te.cambios(corta, hasta)["1A"]["motivo"] == "sin datos suficientes"


def test_la_pendiente_es_larga_menos_corta_en_la_misma_fecha_y_no_completa():
    largo = [(date(2024, 1, 5) + timedelta(days=7 * i), 4.0) for i in range(10)]
    corto = [(f, 5.0) for f, _ in largo if f != date(2024, 1, 19)]                   # falta un viernes (y no hay dato cerca)
    corto = [x for x in corto if abs((x[0] - date(2024, 1, 19)).days) > 3]
    sp = te.pendiente(largo, corto, date(2024, 1, 5), date(2024, 3, 8))
    assert all(v == pytest.approx(-1.0) for _, v in sp) and date(2024, 1, 19) not in {f for f, _ in sp}
    r = te.resumen_pendiente(sp, date(2024, 3, 9))
    assert r["invertida"] is True and r["semanas_invertida_52"] == len(sp) == r["semanas_52"]


def test_desfases_con_una_tasa_usa_su_cambio_y_encuentra_el_rezago_conocido():
    # El grupo se mueve con el cambio de la tasa de 3 semanas antes: el máximo debe estar en k = +3 (la tasa va primero).
    b = benchmark(semanas=170)
    viernes = eng.grilla_semanal(b[0][0], b[-1][0])
    import random
    azar = random.Random(7)
    cambio = {f: azar.uniform(-0.2, 0.2) for f in viernes}
    nivel, valor = [], 3.0
    for f in viernes:
        valor += cambio[f]
        nivel.append((f, valor))
    precio, p = [], 100.0
    for i, f in enumerate(viernes):
        p *= 1 + (cambio[viernes[i - 3]] * 0.05 if i >= 3 else 0.0)
        precio.append((f, p))
    r = eng.desfases(nivel, precio, viernes[0], viernes[-1], nivel_a=True)
    assert r["mejor"]["desfase_semanas"] == 3 and r["mejor"]["valor"] > 0.95


# -- ingesta -------------------------------------------------------------------------------------

def test_filas_barras_de_una_tasa_conserva_el_cero():
    hoy = date(2024, 6, 10)
    serie = [(date(2024, 6, 3), 0.0), (date(2024, 6, 4), 0.05), (date(2024, 6, 5), -0.01)]
    assert [f["cierre"] for f in ci.filas_barras("^IRX", "PCT", serie, hoy, nivel=True)] == [0.0, 0.05, -0.01]
    assert [f["cierre"] for f in ci.filas_barras("SPY", "USD", serie, hoy)] == [0.05]


@pytest.fixture
def db_ingesta():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    yield s
    s.close()


def test_la_ingesta_baja_las_tasas_con_ceros_y_no_las_reajusta(db_ingesta, monkeypatch, tmp_path):
    hoy = date.today()
    doc = {"version": 1, "grupos": [{"id": "spy", "nombre": "S&P 500", "tipo": "region", "proxy": "SPY", "es_benchmark": True, "benchmark": None}],
           "tasas": [{"id": "tasa-3m", "nombre": "3 meses", "simbolo": "^IRX", "plazo_meses": 3}]}
    ruta = tmp_path / "g.json"
    ruta.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(ruta))
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(ci, "INICIO_HISTORIA", hoy - timedelta(days=40))
    pedidos = []

    def lote(simbolos, desde, hasta=None, niveles=frozenset()):
        pedidos.append((list(simbolos), set(niveles)))
        out = {}
        for s in simbolos:
            if s == "^IRX":
                # Cero algunos días y, en la segunda corrida, otra escala: una tasa no se «reajusta».
                out[s] = [(desde + timedelta(days=i), 0.0 if i % 5 == 0 else 0.05 * (1 + len(pedidos))) for i in range((hoy - desde).days)]
            else:
                out[s] = [(desde + timedelta(days=i), 100.0 + (desde + timedelta(days=i) - date(2000, 1, 1)).days * 0.01) for i in range((hoy - desde).days)]
        return out, False

    monkeypatch.setattr(yahoo, "fetch_cierres_lote", lote)
    assert ci.correr(db_ingesta, pausa_seg=0)["resultado"] == "ok"
    assert pedidos[0][1] == {"^IRX"}                                           # sólo la tasa se pide «en nivel»
    ceros = db_ingesta.query(BarraOHLCV).filter(BarraOHLCV.ticker == "^IRX@BENCH", BarraOHLCV.cierre == 0).count()
    assert ceros >= 6                                                          # los ceros se guardaron

    # Segunda corrida, un día después de la última barra, con otra escala para la tasa: no dispara reajuste.
    barras_antes = db_ingesta.query(BarraOHLCV).filter(BarraOHLCV.ticker == "^IRX@BENCH").count()
    est = db_ingesta.query(ci.CiclosProxyEstado).filter_by(simbolo="^IRX").one()
    est.ultima_fecha = hoy - timedelta(days=10)
    db_ingesta.query(BarraOHLCV).filter(BarraOHLCV.fecha > hoy - timedelta(days=10)).delete()
    db_ingesta.commit()
    res = ci.correr(db_ingesta, pausa_seg=0)
    assert res["reajustados"] == 0 and db_ingesta.query(BarraOHLCV).filter(BarraOHLCV.ticker == "^IRX@BENCH").count() >= barras_antes - 12


# -- API -----------------------------------------------------------------------------------------

URL = "/api/inversiones"


def _nivel(base: float, pend: float = 0.0, semanas: int = 170):
    return [(d, base + pend * i / (5 * semanas)) for i, d in enumerate(__import__("tests.ciclos_helpers", fromlist=["x"]).dias_habiles(semanas))]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from .ciclos_helpers import cartera_de_prueba
    sesion = cartera_de_prueba(tmp_path, monkeypatch)
    escribir_catalogo(tmp_path, monkeypatch, doc=_doc())
    s = sesion()
    cargar_series(s, {"^IRX": _nivel(5.0, -4.0), "^TNX": _nivel(4.0, 0.0), "^TYX": _nivel(4.5, 0.0)}, moneda="PCT")
    s.close()
    limpiar_cache()

    def override():
        sx = sesion()
        try:
            yield sx
        finally:
            sx.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_tasas_nivel_cambios_y_curva(client):
    d = client.get(f"{URL}/ciclos/tasas").json()
    assert d["estado"] == "ok" and [t["id"] for t in d["tasas"]] == ["tasa-3m", "tasa-10a", "tasa-30a"]
    t3, t10 = d["tasas"][0], d["tasas"][1]
    assert t10["nivel"] == pytest.approx(4.0) and t10["cambios"]["1A"]["pp"] == pytest.approx(0.0)
    assert t3["nivel"] < 2.0 and t3["cambios"]["1A"]["pp"] < -0.5                      # bajó: el cambio es negativo y en pp
    assert t3["minimo"] <= t3["nivel"] <= t3["maximo"]
    p = d["pendientes"][0]
    assert p["id"] == "10a-3m" and p["valor_pp"] == pytest.approx(t10["nivel"] - t3["nivel"], abs=0.05)
    assert p["invertida"] is False and p["semanas_52"] > 40
    assert [c["id"] for c in d["curva"]] == ["tasa-3m", "tasa-10a", "tasa-30a"]
    assert d["filas"] and set(d["filas"][-1]) >= {"fecha", "tasa-3m", "tasa-10a", "pendiente:10a-3m"}
    assert d["meta"]["moneda"] == "% anual" and "No representan las tasas de Argentina" in " ".join(d["meta"]["limitaciones"])


def test_api_tasas_la_curva_invertida_se_describe_sin_pronosticar(client):
    # 3 meses por encima de 10 años durante los últimos meses.
    from .ciclos_helpers import dias_habiles
    s = client.app.dependency_overrides[get_db]().__next__()
    s.query(BarraOHLCV).filter(BarraOHLCV.ticker == "^IRX@BENCH").delete()
    cargar_series(s, {"^IRX": [(d, 6.0) for d in dias_habiles(170)]}, moneda="PCT")
    s.close()
    limpiar_cache()
    d = client.get(f"{URL}/ciclos/tasas").json()
    p = d["pendientes"][0]
    assert p["invertida"] is True and p["valor_pp"] == pytest.approx(-2.0) and p["semanas_invertida_52"] == p["semanas_52"]
    textos = [d["lectura"], *d["meta"]["limitaciones"], *d["meta"]["advertencias"]]
    assert not [t for t in textos if PROHIBIDO.search(t)]


def test_api_tasas_sin_datos_lo_dice(tmp_path, monkeypatch):
    from .ciclos_helpers import cartera_de_prueba
    sesion = cartera_de_prueba(tmp_path, monkeypatch)
    escribir_catalogo(tmp_path, monkeypatch, doc=_doc())

    def override():
        sx = sesion()
        try:
            yield sx
        finally:
            sx.close()

    app.dependency_overrides[get_db] = override
    try:
        d = TestClient(app).get(f"{URL}/ciclos/tasas").json()
    finally:
        app.dependency_overrides.clear()
    assert d["estado"] == "sin_datos" and d["tasas"][0]["estado"] == "sin_datos" and d["tasas"][0]["motivo"]


def test_api_tasas_valida_los_anios(client):
    assert client.get(f"{URL}/ciclos/tasas", params={"anios": 0}).status_code == 422
    assert client.get(f"{URL}/ciclos/tasas", params={"anios": 99}).status_code == 422


def test_api_desfases_entre_una_tasa_y_un_grupo(client):
    d = client.get(f"{URL}/ciclos/relaciones/desfases", params={"a": "tasa-10a", "b": "tecnologia"}).json()
    assert d["nombres"] == {"tasa-10a": "Tesoro 10 años", "tecnologia": "Tecnología"}
    assert any("puntos porcentuales" in a for a in d["meta"]["advertencias"])
    assert d["estado"] in ("ok", "datos_insuficientes")


def test_api_catalogo_expone_tasas_y_pendientes(client):
    d = client.get(f"{URL}/ciclos/catalogo").json()
    assert [t["id"] for t in d["tasas"]] == ["tasa-3m", "tasa-10a", "tasa-30a"] and d["pendientes_curva"][0]["id"] == "10a-3m"


def test_api_estado_incluye_los_simbolos_de_tasas(client):
    sim = {s["simbolo"]: s for s in client.get(f"{URL}/ciclos/estado").json()["simbolos"]}
    assert sim["^TNX"]["rol"] == "tasa" and sim["^TNX"]["moneda"] == "PCT" and sim["^TNX"]["grupos"] == ["tasa-10a"]
