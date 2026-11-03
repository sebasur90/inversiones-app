"""Régimen macro (preparado, sin datos), detector de señales sobre el historial semanal y registro de ese historial."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, CiclosEstadoHistorial
from app.services import ciclos_engine as eng
from app.services import ciclos_historial as hist
from app.services import ciclos_regimen as reg
from app.services import ciclos_senales_engine as se

from .ciclos_helpers import cargar_series, escribir_catalogo, fin, series_basicas

V0 = date(2024, 1, 5)          # un viernes


def _historial(secuencia: str, desde: date = V0, salteando: tuple = ()):
    nombres = {"L": "leading", "W": "weakening", "G": "lagging", "I": "improving"}
    return [{"semana": desde + timedelta(days=7 * i), "cuadrante": nombres[c]} for i, c in enumerate(secuencia) if i not in salteando]


# -- régimen sin datos (el régimen con datos está en test_ciclos_macro.py) ------------------------

def test_sin_datos_el_regimen_no_asigna_ningun_escenario():
    r = reg.evaluar()
    assert r["estado"] == "no_disponible" and r["escenario"] is None and r["escenario_id"] is None
    assert all(e["actual"] is False for e in r["escenarios"])
    assert "Todavía no se descargaron" in r["aclaracion"]


def test_los_cuatro_escenarios_cruzan_crecimiento_e_inflacion():
    tabla = {e["nombre"]: (e["crecimiento"], e["inflacion"]) for e in reg.evaluar()["escenarios"]}
    assert tabla == {
        "Reflación": ("acelerando", "acelerando"), "Expansión equilibrada": ("acelerando", "desacelerando"),
        "Estanflación": ("desacelerando", "acelerando"), "Desinflación": ("desacelerando", "desacelerando"),
    }


def test_sin_datos_dice_que_falta_y_el_contexto_no_clasifica():
    r = reg.evaluar()
    assert r["falta"] and all("todavía no se descargó" in f for f in r["falta"])
    assert set(r["ejes"]) == {"crecimiento", "inflacion"}
    assert set(r["contexto"]) == {"liquidez", "condiciones_financieras", "dolar"}
    assert all(s["voto"] is None for e in r["contexto"].values() for s in e)


def test_el_resultado_es_independiente_de_las_llamadas():
    a = reg.evaluar()
    a["escenarios"][0]["actual"] = True
    assert reg.evaluar()["escenarios"][0]["actual"] is False


# -- señales -----------------------------------------------------------------------------------

def _tipos(res):
    return [(e["tipo"], e["de"], e["a"], e["confirmado"]) for e in res["eventos"]]


def test_lagging_a_improving_confirmado():
    res = se.detectar(_historial("GGGGGIIII"))
    assert _tipos(res) == [("empieza_a_mejorar", "lagging", "improving", True)]
    assert res["estado_confirmado"] == "improving" and res["semanas_en_estado"] == 4


def test_improving_a_leading_y_liderazgo_sostenido():
    res = se.detectar(_historial("IIIIILLLL"))
    assert _tipos(res) == [("pasa_a_liderar", "improving", "leading", True)]
    assert res["liderazgo_sostenido"] is True
    assert se.detectar(_historial("IIIIILLL"))["liderazgo_sostenido"] is True
    assert se.detectar(_historial("IIIIILL"))["liderazgo_sostenido"] is False             # 2 semanas: todavía no es sostenido


def test_leading_a_weakening_y_perdida_de_fortaleza():
    res = se.detectar(_historial("LLLLLWWWW"))
    assert _tipos(res) == [("pierde_momentum", "leading", "weakening", True)]
    perdida = se.detectar(_historial("WWWWWGGGG"))
    assert _tipos(perdida) == [("pierde_fortaleza_relativa", "weakening", "lagging", True)]
    doble = se.detectar(_historial("LLLLLIIII"))
    assert _tipos(doble) == [("pierde_fortaleza_relativa", "leading", "improving", True)]     # RS-Ratio cruza por debajo de 100


def test_un_cambio_que_todavia_no_se_sostuvo_no_esta_confirmado():
    res = se.detectar(_historial("GGGGGIIW"[:7]))
    assert _tipos(res) == [("empieza_a_mejorar", "lagging", "improving", False)]
    assert res["estado_confirmado"] == "lagging"


def test_un_rebote_de_una_semana_no_genera_evento():
    assert se.detectar(_historial("LLLLLLWLLLLL"))["eventos"] == []


def test_una_semana_faltante_corta_la_serie_y_no_inventa_un_cambio():
    # Con una semana sin datos en el medio, sólo cuenta el tramo continuo final.
    res = se.detectar(_historial("GGGGGGIIIII", salteando=(7,)))
    assert res["semanas_descartadas"] > 0 and res["semanas_usadas"] == 3
    assert res["eventos"] == [] and res["estado_confirmado"] == "improving"


def test_sin_historial():
    res = se.detectar([])
    assert res["eventos"] == [] and res["estado_confirmado"] is None and res["semanas_usadas"] == 0 and res["liderazgo_sostenido"] is False


def test_la_confirmacion_se_ajusta():
    assert se.detectar(_historial("GGGGGII"), confirmacion=2)["eventos"][0]["confirmado"] is True
    assert se.detectar(_historial("GGGGGII"), confirmacion=3)["eventos"][0]["confirmado"] is False


def test_el_detector_no_envia_nada():
    """Es puro: lo único que importa es el motor de ciclos. Sin red, sin DB y sin el módulo de avisos."""
    import ast
    import inspect
    importados = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(se))):
        if isinstance(nodo, ast.Import):
            importados |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            importados.add(f"{'.' * nodo.level}{nodo.module or ''}:" + ",".join(sorted(a.name for a in nodo.names)))
    assert importados == {"__future__:annotations", ".:ciclos_engine"}


def test_los_eventos_describen_lo_ocurrido_sin_recomendar():
    import re
    for e in se.detectar(_historial("GGGGGIIIILLLLWWWW"))["eventos"]:
        assert set(e) == {"tipo", "desde", "de", "a", "semanas_sostenido", "confirmado"}
        assert not re.search(r"compr\w*|vend\w*|recomend\w*|conviene", " ".join(str(v) for v in e.values()), re.IGNORECASE)


# -- registro del historial --------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    escribir_catalogo(tmp_path, monkeypatch)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    cargar_series(s, series_basicas())
    yield s
    s.close()


def _filas(db):
    return db.query(CiclosEstadoHistorial).all()


def test_registra_solo_semanas_cerradas_y_con_la_version(db):
    res = hist.registrar(db, hoy=fin() + timedelta(days=1))          # sábado: la semana del viernes ya cerró
    filas = _filas(db)
    assert res["filas_nuevas"] == len(filas) > 0 and res["resultado"] == "ok"
    assert {f.version_algoritmo for f in filas} == {eng.VERSION_ALGORITMO}
    assert max(f.semana for f in filas) == fin() and all(f.ultima_fecha_datos == fin() for f in filas)
    assert {f.grupo_id for f in filas} >= {"tecnologia", "salud", "energia", "consumo-basico"}
    assert max(f.semana for f in db.query(CiclosEstadoHistorial).filter_by(grupo_id="tecnologia")) == fin()


def test_una_semana_abierta_no_se_registra(db):
    hist.registrar(db, hoy=fin())                                      # el mismo viernes: la semana todavía puede cambiar
    assert max(f.semana for f in _filas(db)) == fin() - timedelta(days=7)


def test_es_idempotente(db):
    hist.registrar(db, hoy=fin() + timedelta(days=1))
    n = len(_filas(db))
    assert hist.registrar(db, hoy=fin() + timedelta(days=1))["filas_nuevas"] == 0
    assert len(_filas(db)) == n


def test_agrega_solo_lo_nuevo_cuando_llega_una_semana_mas(db):
    hist.registrar(db, hoy=fin())
    n = len(_filas(db))
    nuevas = hist.registrar(db, hoy=fin() + timedelta(days=1))["filas_nuevas"]
    assert nuevas == len({f.grupo_id for f in _filas(db)}) and len(_filas(db)) == n + nuevas


def test_un_grupo_incompleto_o_desactualizado_no_deja_filas(db):
    from sqlalchemy import delete
    from app.database import BarraOHLCV
    db.execute(delete(BarraOHLCV).where(BarraOHLCV.ticker == "XLP@BENCH"))                    # sin serie
    corto = db.query(BarraOHLCV).filter(BarraOHLCV.ticker == "XLE@BENCH", BarraOHLCV.fecha > fin() - timedelta(days=7 * 8)).all()
    db.execute(delete(BarraOHLCV).where(BarraOHLCV.ticker == "XLE@BENCH", BarraOHLCV.fecha > fin() - timedelta(days=7 * 8)))   # desactualizado
    db.commit()
    assert corto
    res = hist.registrar(db, hoy=fin() + timedelta(days=1))
    grupos = {f.grupo_id for f in _filas(db)}
    assert "consumo-basico" not in grupos and "energia" not in grupos and {"tecnologia", "salud"} <= grupos
    assert {"consumo-basico", "energia"} <= set(res["omitidos"])


def test_el_historial_alimenta_al_detector(db):
    hist.registrar(db, hoy=fin() + timedelta(days=1), semanas=60)
    h = hist.historial_de(db, "tecnologia", "estados-unidos")
    assert h and h == sorted(h, key=lambda x: x["semana"])
    res = se.detectar(h)
    assert res["estado_confirmado"] == "leading" and res["semanas_usadas"] == len(h)
    assert hist.historial_de(db, "tecnologia", "global") == []


def test_la_ingesta_registra_el_historial_al_terminar(db, monkeypatch):
    from app.services import ciclos_ingesta as ci
    from app.services.market_data import yahoo
    series = series_basicas()
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(ci, "INICIO_HISTORIA", series["SPY"][0][0])
    from app.database import BarraOHLCV
    db.query(BarraOHLCV).delete()
    db.commit()
    nombres = {s: s for s in series}
    monkeypatch.setattr(yahoo, "fetch_cierres_lote", lambda simbolos, desde, hasta=None: (
        {s: [(f, c) for f, c in series[s] if desde <= f <= (hasta or fin())] for s in simbolos if s in nombres}, False))
    res = ci.correr(db, pausa_seg=0)
    assert res["resultado"] == "ok" and res["historial"]["resultado"] == "ok"
    assert res["historial"]["filas_nuevas"] > 0 and _filas(db)
