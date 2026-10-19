"""Ingesta del mapa de mercado: universo, conversión de lo local a USD, upsert idempotente, corte
por límite de tasa y uso del lock. Sin red: la descarga en lote de Yahoo es una función fija."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, IndiceMercado, VariacionMercado
from app.services import mapa_mercado_ingesta as mi
from app.services.market_data import yahoo

HOY = date.today()

CATALOGO = [
    {"simbolo": "KO", "descripcion": "Cedear Coca Cola", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "KOD", "descripcion": "Cedear Coca Cola", "moneda": "USD", "tipo": "CEDEAR"},
    {"simbolo": "PEP", "descripcion": "Cedear Pepsico", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "ALUA", "descripcion": "Aluar", "moneda": "ARS", "tipo": "Acción"},
    {"simbolo": "AL30", "descripcion": "Bono AL30", "moneda": "ARS", "tipo": "Bono"},
]
SEED = {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}}


def _serie(base: float, dias: int = 40, ultimo: float | None = None):
    desde = HOY - timedelta(days=dias)
    serie = [(desde + timedelta(days=i), base) for i in range(dias + 1)]
    if ultimo is not None:
        serie[-1] = (serie[-1][0], ultimo)
    return serie


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def yahoo_falso(monkeypatch):
    pedidos: list[list[str]] = []
    datos = {
        "KO": _serie(60.0, ultimo=63.0),
        "PEP": _serie(150.0),
        "ALUA.BA": _serie(1000.0, ultimo=1100.0),
    }

    def _lote(simbolos, desde, hasta=None):
        pedidos.append(list(simbolos))
        return {s: datos[s] for s in simbolos if s in datos}, False

    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(mi, "construir_universo", __import__("app.services.fundamentales_ingesta", fromlist=["x"]).construir_universo)
    from app.services import fundamentales_ingesta as fi
    monkeypatch.setattr(fi, "cargar_catalogo", lambda: CATALOGO)
    monkeypatch.setattr(fi, "cargar_seed", lambda: SEED)
    monkeypatch.setattr(yahoo, "fetch_cierres_lote", _lote)
    return pedidos


def _mep(db, valor=1000.0):
    for i in range(0, 60):
        db.add(IndiceMercado(fecha=HOY - timedelta(days=i), mep=valor))
    db.commit()


def test_simbolos_aptos_sin_renta_fija_ni_variantes_repetidas(db, yahoo_falso):
    assert mi.simbolos_aptos(db) == ["ALUA.BA", "KO", "PEP"]


def test_corrida_guarda_una_foto_por_simbolo(db, yahoo_falso):
    _mep(db)
    res = mi.correr(db, pausa_seg=0)
    assert res["resultado"] == "ok" and res["con_datos"] == 3
    filas = {f.simbolo_yahoo: f for f in db.query(VariacionMercado)}
    assert float(filas["KO"].var_1d) == pytest.approx(0.05)
    assert filas["KO"].moneda == "USD"


def test_las_acciones_locales_se_convierten_a_usd_con_el_mep(db, yahoo_falso):
    _mep(db, 1000.0)
    mi.correr(db, pausa_seg=0)
    f = db.get(VariacionMercado, "ALUA.BA")
    assert f.moneda == "USD"
    assert float(f.cierre) == pytest.approx(1.1)          # 1100 ARS / 1000 MEP
    assert float(f.var_1d) == pytest.approx(0.10)


def test_sin_mep_la_variacion_local_queda_en_pesos_y_lo_dice(db, yahoo_falso):
    mi.correr(db, pausa_seg=0)
    f = db.get(VariacionMercado, "ALUA.BA")
    assert f.moneda == "ARS"
    assert float(f.cierre) == pytest.approx(1100.0)


def test_correr_dos_veces_no_duplica_filas(db, yahoo_falso):
    _mep(db)
    mi.correr(db, pausa_seg=0)
    mi.correr(db, pausa_seg=0)
    assert db.query(VariacionMercado).count() == 3


def test_pide_en_tandas(db, yahoo_falso):
    _mep(db)
    mi.correr(db, tanda=2, pausa_seg=0)
    assert [len(t) for t in yahoo_falso] == [2, 1]


def test_un_simbolo_que_yahoo_no_devuelve_no_corta_al_resto(db, yahoo_falso, monkeypatch):
    _mep(db)
    original = yahoo.fetch_cierres_lote
    monkeypatch.setattr(yahoo, "fetch_cierres_lote",
                        lambda s, d, h=None: ({k: v for k, v in original(s, d, h)[0].items() if k != "PEP"}, False))
    res = mi.correr(db, pausa_seg=0)
    assert res["con_datos"] == 2
    assert db.get(VariacionMercado, "PEP") is None


def test_un_limite_de_tasa_corta_y_guarda_lo_ya_obtenido(db, yahoo_falso, monkeypatch):
    _mep(db)
    llamadas = []

    def _lote(simbolos, desde, hasta=None):
        llamadas.append(list(simbolos))
        if len(llamadas) == 1:
            return {"KO": _serie(60.0, ultimo=63.0)}, False
        return {}, True

    monkeypatch.setattr(yahoo, "fetch_cierres_lote", _lote)
    res = mi.correr(db, tanda=1, pausa_seg=0)
    assert res["resultado"] == "rate_limited"
    assert len(llamadas) == 2          # no siguió pidiendo
    assert db.get(VariacionMercado, "KO") is not None


def test_sin_fuentes_externas_no_hace_nada(db, yahoo_falso, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    assert mi.correr(db, pausa_seg=0)["resultado"] == "sin_fuentes"
    assert yahoo_falso == []


def test_una_corrida_en_curso_no_arranca_otra(db, yahoo_falso):
    assert mi._lock_ingesta.acquire(blocking=False)
    try:
        assert mi.correr(db, pausa_seg=0)["resultado"] == "en_curso"
    finally:
        mi._lock_ingesta.release()


def test_calcular_es_puro():
    out = mi.calcular({"KO": _serie(60.0, ultimo=63.0)}, {}, HOY)
    assert out["KO"][1] == "USD" and out["KO"][0].var_1d == pytest.approx(0.05)
