"""Régimen macro con series de FRED: catálogo, votos por serie, mayoría por eje, escenario, ingesta y API.

Series sintéticas de resultado conocido. Lo que se prueba: que cada serie vote lo que dice su cambio (con el sentido inverso
cuando corresponde), que un eje sin mayoría o con pocos votos no concluya, que sin los dos ejes no haya escenario y que un dato
viejo o ausente no vote ni se complete.
"""
import json
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, CiclosMacroEstado, CiclosMacroObs, get_db
from app.main import app
from app.services import ciclos_macro as cm
from app.services import ciclos_macro_catalogo as mc
from app.services import ciclos_macro_ingesta as ing
from app.services import ciclos_regimen as reg
from app.services.cache import limpiar_cache
from app.services.market_data import client

PROHIBIDO = re.compile(r"compr\w*|vend\w*|recomend\w*|conviene|deber[ií]a|pronostic\w*", re.IGNORECASE)
HOY = date(2026, 11, 3)


# -- series sintéticas ----------------------------------------------------------------------------

def _meses(n: int, fin: date = date(2026, 9, 1)) -> list[date]:
    out, d = [], fin
    for _ in range(n):
        out.append(d)
        d = date(d.year - (d.month == 1), 12 if d.month == 1 else d.month - 1, 1)
    return list(reversed(out))


def mensual(tasas_mensuales: list[float], base: float = 100.0, fin: date = date(2026, 9, 1)) -> list[tuple[date, float]]:
    """Nivel con crecimiento mensual conocido (una tasa por mes, de la más vieja a la más nueva)."""
    fechas = _meses(len(tasas_mensuales), fin)
    out, v = [], base
    for f, t in zip(fechas, tasas_mensuales):
        v *= 1 + t
        out.append((f, v))
    return out


def acelera(meses: int = 40) -> list[tuple[date, float]]:
    """Crece cada vez más rápido: la variación a 12 meses de hoy es mayor que la de hace 3 meses."""
    return mensual([0.001 + 0.0004 * i for i in range(meses)])


def desacelera(meses: int = 40) -> list[tuple[date, float]]:
    return mensual([0.02 - 0.0004 * i for i in range(meses)])


def semanal(valores: list[float], fin: date = date(2026, 10, 24)) -> list[tuple[date, float]]:
    return [(fin - timedelta(days=7 * (len(valores) - 1 - i)), v) for i, v in enumerate(valores)]


def diaria(valores: list[float], fin: date = date(2026, 11, 2)) -> list[tuple[date, float]]:
    return [(fin - timedelta(days=len(valores) - 1 - i), v) for i, v in enumerate(valores)]


def cat_prueba() -> mc.CatalogoMacro:
    return mc.construir({
        "meses_comparacion": 3, "minimo_votos": 3,
        "series": [
            {"id": "C1", "nombre": "Crec 1", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "variacion_12m", "sentido": 1},
            {"id": "C2", "nombre": "Crec 2", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "variacion_12m", "sentido": 1},
            {"id": "C3", "nombre": "Crec 3", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "nivel", "sentido": 1},
            {"id": "C4", "nombre": "Subsidios", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "variacion_12m", "sentido": -1},
            {"id": "I1", "nombre": "Infl 1", "eje": "inflacion", "frecuencia": "mensual", "transformacion": "variacion_12m", "sentido": 1},
            {"id": "I2", "nombre": "Infl 2", "eje": "inflacion", "frecuencia": "mensual", "transformacion": "variacion_12m", "sentido": 1},
            {"id": "I3", "nombre": "Infl 3", "eje": "inflacion", "frecuencia": "mensual", "transformacion": "nivel", "sentido": 1},
            {"id": "L1", "nombre": "Liquidez", "eje": "liquidez", "frecuencia": "mensual", "transformacion": "variacion_12m", "sentido": 1},
        ],
    })


def nivel_sube(meses: int = 40) -> list[tuple[date, float]]:
    return [(f, 1.0 + 0.05 * i) for i, f in enumerate(_meses(meses))]


def nivel_baja(meses: int = 40) -> list[tuple[date, float]]:
    return [(f, 10.0 - 0.05 * i) for i, f in enumerate(_meses(meses))]


def expansion_con_inflacion_a_la_baja() -> dict:
    return {"C1": acelera(), "C2": acelera(), "C3": nivel_sube(), "C4": desacelera(),     # subsidios desaceleran = crecimiento acelera
            "I1": desacelera(), "I2": desacelera(), "I3": nivel_baja()}


# -- catálogo -------------------------------------------------------------------------------------

def test_el_catalogo_real_tiene_las_series_de_cada_eje():
    cat = mc.cargar()
    assert not cat.errores
    assert {s.id for s in cat.por_eje("crecimiento")} == {"INDPRO", "PAYEMS", "CFNAIMA3", "IC4WSA"}
    assert {s.id for s in cat.por_eje("inflacion")} == {"CPIAUCSL", "PCEPILFE", "T5YIE"}
    assert {s.id for s in cat.por_eje("liquidez")} == {"WALCL", "M2SL"}
    assert cat.series["IC4WSA"].sentido == -1 and cat.minimo_votos == 3 and cat.meses_comparacion == 3


def test_una_serie_invalida_se_descarta_sola():
    cat = mc.construir({"series": [
        {"id": "OK", "nombre": "Ok", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "nivel"},
        {"id": "malo", "nombre": "Id en minúscula", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "nivel"},
        {"id": "EJE", "nombre": "Eje raro", "eje": "otro", "frecuencia": "mensual", "transformacion": "nivel"},
        {"id": "FREC", "nombre": "Frecuencia rara", "eje": "inflacion", "frecuencia": "anual", "transformacion": "nivel"},
        {"id": "SENT", "nombre": "Sentido raro", "eje": "inflacion", "frecuencia": "mensual", "transformacion": "nivel", "sentido": 2},
        {"id": "OK", "nombre": "Repetida", "eje": "inflacion", "frecuencia": "mensual", "transformacion": "nivel"},
    ], "minimo_votos": 0})
    assert list(cat.series) == ["OK"] and len(cat.errores) == 6


# -- una serie ------------------------------------------------------------------------------------

def _serie(sid, obs, cat=None):
    cat = cat or cat_prueba()
    return reg.evaluar_serie(cat.series[sid], obs, HOY, cat.meses_comparacion, cat.dias_maximos)


def test_una_serie_que_acelera_vota_acelerando_con_su_cambio_exacto():
    s = _serie("C1", acelera())
    assert s["estado"] == "ok" and s["voto"] == "acelerando" and s["tendencia"] == "sube"
    assert s["cambio"] == pytest.approx(s["valor"] - s["valor_previo"]) and s["cambio"] > 0
    assert s["fecha"] == date(2026, 9, 1) and s["fecha_previa"] == date(2026, 6, 1)


def test_variacion_12m_es_el_porcentaje_contra_un_anio_antes():
    obs = mensual([0.01] * 30)                                   # 1 % por mes → (1,01^12 − 1) = 12,68 % interanual
    s = _serie("C1", obs)
    assert s["valor"] == pytest.approx((1.01 ** 12 - 1) * 100, rel=1e-6) and s["cambio"] == pytest.approx(0, abs=1e-6)


def test_un_sentido_inverso_invierte_el_voto_pero_no_la_tendencia():
    s = _serie("C4", desacelera())                               # los pedidos de subsidio se desaceleran: el crecimiento acelera
    assert s["tendencia"] == "baja" and s["voto"] == "acelerando"


def test_un_cambio_exactamente_cero_no_vota():
    s = _serie("C3", [(f, 5.0) for f in _meses(40)])
    assert s["voto"] == "sin_cambio" and s["cambio"] == 0


def test_un_dato_viejo_no_vota_ni_se_completa():
    viejo = mensual([0.01] * 30, fin=date(2026, 6, 1))           # último dato: junio, 155 días antes de HOY (límite 75)
    s = _serie("C1", viejo)
    assert s["estado"] == "desactualizada" and s["voto"] is None and "demasiado viejo" in s["motivo"]


def test_sin_historia_suficiente_no_vota():
    s = _serie("C1", mensual([0.01] * 8))                        # 8 meses: no alcanza para una variación a 12 meses
    assert s["estado"] == "sin_historia" and s["voto"] is None and s["valor"] is None


def test_sin_datos_lo_dice():
    s = _serie("C1", [])
    assert s["estado"] == "sin_datos" and s["voto"] is None and "todavía no se descargó" in s["motivo"]


# -- un eje y el escenario -------------------------------------------------------------------------

def test_mayoria_estricta_con_el_minimo_de_votos():
    def v(voto):
        return {"voto": voto}
    assert reg.evaluar_eje([v("acelerando"), v("acelerando"), v("desacelerando")], 3)["estado"] == "acelerando"
    assert reg.evaluar_eje([v("desacelerando"), v("desacelerando"), v("acelerando"), v("acelerando")], 3)["estado"] == "no_concluyente"
    pocos = reg.evaluar_eje([v("acelerando"), v("acelerando"), v(None), v("sin_cambio")], 3)
    assert pocos["estado"] == "no_concluyente" and "votaron 2 de 4" in pocos["motivo"]


def test_expansion_equilibrada_cuando_crece_mas_y_la_inflacion_baja():
    r = reg.evaluar(expansion_con_inflacion_a_la_baja(), cat_prueba(), HOY)
    assert r["estado"] == "disponible" and r["escenario"] == "Expansión equilibrada" and r["escenario_id"] == "expansion-equilibrada"
    assert r["ejes"]["crecimiento"]["estado"] == "acelerando" and r["ejes"]["inflacion"]["estado"] == "desacelerando"
    assert [e["id"] for e in r["escenarios"] if e["actual"]] == ["expansion-equilibrada"]
    assert r["dato_mas_reciente"] == date(2026, 9, 1)


@pytest.mark.parametrize("crec,infl,esperado", [
    ("acelera", "acelera", "Reflación"), ("acelera", "desacelera", "Expansión equilibrada"),
    ("desacelera", "acelera", "Estanflación"), ("desacelera", "desacelera", "Desinflación"),
])
def test_los_cuatro_escenarios(crec, infl, esperado):
    f = {"acelera": acelera, "desacelera": desacelera}
    n = {"acelera": nivel_sube, "desacelera": nivel_baja}
    inv = {"acelera": desacelera, "desacelera": acelera}                 # el sentido inverso de subsidios
    datos = {"C1": f[crec](), "C2": f[crec](), "C3": n[crec](), "C4": inv[crec](),
             "I1": f[infl](), "I2": f[infl](), "I3": n[infl]()}
    assert reg.evaluar(datos, cat_prueba(), HOY)["escenario"] == esperado


def test_si_un_eje_no_concluye_no_hay_escenario_y_se_explica():
    datos = expansion_con_inflacion_a_la_baja()
    datos["I2"] = acelera()                                              # inflación: 1 acelera, 2 desaceleran → igual hay mayoría
    datos["I1"], datos["I3"] = acelera(), desacelera()                   # ahora 2 aceleran y 1 desacelera → acelera
    assert reg.evaluar(datos, cat_prueba(), HOY)["ejes"]["inflacion"]["estado"] == "acelerando"
    datos.pop("I2"), datos.pop("I3")                                      # queda 1 solo voto en inflación: no alcanza
    r = reg.evaluar(datos, cat_prueba(), HOY)
    assert r["estado"] == "no_concluyente" and r["escenario"] is None and r["escenario_id"] is None
    assert "inflación" in r["aclaracion"] and "votaron 1 de 3" in r["aclaracion"]
    assert all(e["actual"] is False for e in r["escenarios"]) and r["falta"]


def test_el_contexto_se_muestra_pero_no_vota_ni_cambia_el_escenario():
    base = expansion_con_inflacion_a_la_baja()
    sin = reg.evaluar(base, cat_prueba(), HOY)
    con = reg.evaluar({**base, "L1": desacelera()}, cat_prueba(), HOY)
    assert con["escenario"] == sin["escenario"]
    liquidez = con["contexto"]["liquidez"][0]
    assert liquidez["estado"] == "ok" and liquidez["voto"] is None and liquidez["clasifica"] is False


def test_el_texto_no_recomienda_ni_pronostica():
    r = reg.evaluar(expansion_con_inflacion_a_la_baja(), cat_prueba(), HOY)
    textos = [r["aclaracion"], *r["limitaciones"]]
    assert not [t for t in textos if PROHIBIDO.search(t)]


# -- parseo e ingesta -------------------------------------------------------------------------------

def test_el_csv_de_fred_omite_los_faltantes_y_rechaza_lo_que_no_es_la_serie():
    texto = "observation_date,PAYEMS\n2026-01-01,100\n2026-02-01,.\n2026-03-01,\n2026-04-01,102.5\n2026-04-01,103\nbasura\n"
    assert ing.parsear_csv(texto, "PAYEMS") == [(date(2026, 1, 1), 100.0), (date(2026, 4, 1), 103.0)]
    assert ing.parsear_csv(texto, "OTRA") == []
    assert ing.parsear_csv("<!DOCTYPE html><html>", "PAYEMS") == [] and ing.parsear_csv(None, "PAYEMS") == []


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    yield s
    s.close()


def _csv(sid, obs):
    return "observation_date," + sid + "\n" + "\n".join(f"{f.isoformat()},{v}" for f, v in obs) + "\n"


@pytest.fixture
def fred(monkeypatch, tmp_path):
    """FRED falso: sirve las series de `datos` y registra los pedidos."""
    ruta = tmp_path / "macro.json"
    ruta.write_text(json.dumps({"series": [
        {"id": "AAA", "nombre": "A", "eje": "crecimiento", "frecuencia": "mensual", "transformacion": "nivel"},
        {"id": "BBB", "nombre": "B", "eje": "inflacion", "frecuencia": "mensual", "transformacion": "nivel"},
        {"id": "CCC", "nombre": "C", "eje": "dolar", "frecuencia": "diaria", "transformacion": "nivel"},
    ]}), encoding="utf-8")
    monkeypatch.setenv("CICLOS_MACRO_FILE", str(ruta))
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    estado = {"datos": {k: nivel_sube() for k in ("AAA", "BBB", "CCC")}, "pedidos": [], "falla": {}}

    def get_text(url, *, params=None, timeout=20.0):
        sid = params["id"]
        estado["pedidos"].append((sid, params.get("cosd")))
        if sid in estado["falla"]:
            return estado["falla"][sid]
        return 200, _csv(sid, estado["datos"][sid])

    monkeypatch.setattr(ing, "get_text", get_text)
    return estado


def test_la_ingesta_baja_guarda_y_registra_la_cobertura(db, fred):
    r = ing.correr(db, pausa_seg=0)
    assert r["resultado"] == "ok" and r["bajadas"] == 3
    assert db.query(CiclosMacroObs).filter_by(serie_id="AAA").count() == 40
    est = db.query(CiclosMacroEstado).filter_by(serie_id="AAA").one()
    assert est.estado == "ok" and est.n_obs == 40 and est.ultima_fecha == date(2026, 9, 1) and est.error is None
    assert fred["pedidos"][0] == ("AAA", "2000-01-01")


def test_no_vuelve_a_bajar_lo_que_acaba_de_bajar_salvo_que_se_fuerce(db, fred):
    ing.correr(db, pausa_seg=0)
    assert ing.correr(db, pausa_seg=0)["resultado"] == "al_dia" and len(fred["pedidos"]) == 3
    assert ing.correr(db, forzar=True, pausa_seg=0)["bajadas"] == 3 and len(fred["pedidos"]) == 6


def test_cada_descarga_reemplaza_la_serie_entera_por_la_version_vigente(db, fred):
    ing.correr(db, pausa_seg=0)
    fred["datos"]["AAA"] = [(f, v * 2) for f, v in nivel_sube(30)]          # revisada: más corta y con otros valores
    ing.correr(db, forzar=True, pausa_seg=0)
    filas = db.query(CiclosMacroObs).filter_by(serie_id="AAA").order_by(CiclosMacroObs.fecha).all()
    assert len(filas) == 30 and float(filas[-1].valor) == pytest.approx(nivel_sube(30)[-1][1] * 2)


def test_una_descarga_mala_no_pisa_lo_guardado(db, fred):
    ing.correr(db, pausa_seg=0)
    fred["falla"]["AAA"] = (200, "<!DOCTYPE html><html>no es un csv</html>")
    fred["falla"]["BBB"] = (503, "")
    r = ing.correr(db, forzar=True, pausa_seg=0)
    assert r["resultado"] == "parcial" and set(r["errores"]) == {"AAA", "BBB"} and r["bajadas"] == 1
    assert db.query(CiclosMacroObs).filter_by(serie_id="AAA").count() == 40            # sigue la versión anterior
    est = db.query(CiclosMacroEstado).filter_by(serie_id="AAA").one()
    assert est.estado == "ok" and "no trae una serie válida" in est.error


def test_si_fred_no_responde_se_corta_la_corrida(db, fred):
    for sid in ("AAA", "BBB", "CCC"):
        fred["falla"][sid] = (None, None)
    r = ing.correr(db, pausa_seg=0)
    assert r["resultado"] == "error" and r["bajadas"] == 0 and len(fred["pedidos"]) == ing.MAX_FALLOS_DE_RED_SEGUIDOS
    assert db.query(CiclosMacroEstado).filter_by(serie_id="CCC").one().estado == "error"


def test_sin_apis_externas_no_hace_red(db, fred, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    assert ing.correr(db)["resultado"] == "sin_fuentes" and not fred["pedidos"]


def test_correr_seguro_nunca_lanza(db, monkeypatch):
    monkeypatch.setattr(ing, "correr", lambda *a, **k: 1 / 0)
    assert ing.correr_seguro(db)["resultado"] == "error"


# -- adaptador y API ---------------------------------------------------------------------------------

def test_el_regimen_lee_lo_guardado_y_trae_el_estado_de_la_descarga(db, fred):
    ing.correr(db, pausa_seg=0)
    r = cm.regimen(db, HOY)
    serie = r["ejes"]["crecimiento"]["series"][0]
    assert serie["id"] == "AAA" and serie["estado"] == "ok" and serie["descarga"]["estado"] == "ok" and serie["descarga"]["n_obs"] == 40
    assert r["ultima_actualizacion"] is not None and r["estado"] == "no_concluyente"      # con una serie por eje no alcanza el mínimo


@pytest.fixture
def client_api(db, fred):
    engine = db.get_bind()

    def override():
        s = Session(engine)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    limpiar_cache()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_regimen_sin_datos(client_api):
    d = client_api.get("/api/inversiones/ciclos/regimen").json()
    assert d["estado"] == "no_disponible" and d["escenario"] is None and set(d["ejes"]) == {"crecimiento", "inflacion"}
    assert d["fuente"].startswith("FRED") and d["limitaciones"]


def test_api_regimen_con_series_y_en_el_panorama(client_api, db):
    ing.correr(db, pausa_seg=0)
    limpiar_cache()
    d = client_api.get("/api/inversiones/ciclos/regimen").json()
    assert d["ejes"]["crecimiento"]["series"][0]["voto"] == "acelerando" and d["contexto"]["dolar"][0]["voto"] is None
    assert d["meses_comparacion"] == 3 and d["minimo_votos"] == 3
