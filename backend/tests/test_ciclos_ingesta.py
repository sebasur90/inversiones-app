"""Ingesta de «Ciclos de mercado»: primera descarga entera, incremental con solape, reajuste de Yahoo,
corte por límite de tasa, estado de cobertura y uso del lock. Sin red: `fetch_cierres_lote` es una
función fija."""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, BarraOHLCV, CiclosProxyEstado
from app.services import ciclos_ingesta as ci
from app.services import sync_lock
from app.services.market_data import yahoo

HOY = date.today()
AYER = HOY - timedelta(days=1)
MITAD = HOY - timedelta(days=500)

CATALOGO = {
    "version": 1,
    "defecto_por_tipo": {"sector": {"benchmark": "spy"}, "pais": {"benchmark": "spy"}},
    "grupos": [
        {"id": "spy", "nombre": "S&P 500", "tipo": "region", "proxy": "SPY", "es_benchmark": True, "benchmark": None},
        {"id": "xlk", "nombre": "Tecnología", "tipo": "sector", "proxy": "XLK"},
        {"id": "bitcoin", "nombre": "Bitcoin", "tipo": "activo", "proxy": "BTC-USD", "benchmark": "spy",
         "tipo_rendimiento": "precio"},
        {"id": "brasil", "nombre": "Brasil", "tipo": "pais", "proxy": "EWZ",
         "indice_local": {"simbolo": "^BVSP", "moneda": "BRL"},
         "fx": {"simbolo": "BRL=X", "cotizacion": "local_por_usd"}},
        {"id": "argentina", "nombre": "Argentina", "tipo": "pais", "proxy": "ARGT",
         "indice_local": {"simbolo": "^MERV", "moneda": "ARS"}, "fx": {"simbolo": None, "cotizacion": "mep"}},
        {"id": "apagado", "nombre": "Apagado", "tipo": "commodity", "proxy": "ALI=F", "activo": False, "benchmark": "spy"},
    ],
}
SIMBOLOS = {"SPY", "XLK", "BTC-USD", "EWZ", "^BVSP", "BRL=X", "ARGT", "^MERV"}


def _valor(simbolo: str, d: date, factor: float = 1.0) -> float:
    return (100 + (d - date(2000, 1, 1)).days * 0.01 + len(simbolo)) * factor


def _serie(simbolo, desde, hasta, factor=1.0):
    out, d = [], desde
    while d <= hasta:
        out.append((d, _valor(simbolo, d, factor)))
        d += timedelta(days=1)
    return out


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def yahoo_falso(monkeypatch, tmp_path):
    """Yahoo con series sintéticas conocidas. `estado` permite cambiar lo que devuelve entre corridas."""
    ruta = tmp_path / "grupos.json"
    ruta.write_text(json.dumps(CATALOGO), encoding="utf-8")
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(ruta))
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(ci, "INICIO_HISTORIA", HOY - timedelta(days=900))      # series cortas: el test no depende del largo

    estado = {"fin": AYER, "factor": 1.0, "ausentes": set(), "limitado_desde_llamada": None, "pedidos": []}

    def _lote(simbolos, desde, hasta=None):
        estado["pedidos"].append((list(simbolos), desde))
        n = len(estado["pedidos"])
        if estado["limitado_desde_llamada"] and n >= estado["limitado_desde_llamada"]:
            return {}, True
        return {
            s: [(f, c) for f, c in _serie(s, desde, estado["fin"], estado["factor"])]
            for s in simbolos if s not in estado["ausentes"]
        }, False

    monkeypatch.setattr(yahoo, "fetch_cierres_lote", _lote)
    return estado


def _fechas(db, simbolo):
    return [f for (f,) in db.query(BarraOHLCV.fecha).filter(BarraOHLCV.ticker == f"{simbolo}@BENCH").order_by(BarraOHLCV.fecha)]


# -- puro --------------------------------------------------------------------------------------

def test_detectar_reajuste():
    guardado = {date(2024, 1, 2): 100.0, date(2024, 1, 3): 101.0}
    assert not ci.detectar_reajuste(guardado, [(date(2024, 1, 2), 100.0), (date(2024, 1, 3), 101.0)])
    assert not ci.detectar_reajuste(guardado, [(date(2024, 1, 4), 500.0)])           # sin fechas en común
    assert ci.detectar_reajuste(guardado, [(date(2024, 1, 3), 101.0 * 0.995)])       # dividendo: -0,5 %
    assert not ci.detectar_reajuste(guardado, [(date(2024, 1, 3), 101.0 * 1.00001)])  # ruido


def test_filas_barras_solo_ruedas_cerradas_sin_duplicados_ni_basura():
    serie = [(HOY - timedelta(days=2), 10.0), (HOY - timedelta(days=2), 11.0), (AYER, 12.0),
             (HOY, 13.0), (HOY - timedelta(days=3), 0.0), (HOY - timedelta(days=4), -1.0)]
    filas = ci.filas_barras("SPY", "USD", serie, HOY)
    assert [(f["fecha"], f["cierre"]) for f in filas] == [(HOY - timedelta(days=2), 11.0), (AYER, 12.0)]
    assert filas[0]["ticker"] == "SPY@BENCH" and filas[0]["fuente"] == "yahoo" and filas[0]["apertura"] is None


def test_filas_barras_respeta_desde():
    filas = ci.filas_barras("SPY", "USD", [(HOY - timedelta(days=5), 1.0), (AYER, 2.0)], HOY, desde=HOY - timedelta(days=2))
    assert [f["cierre"] for f in filas] == [2.0]


def test_planificar_separa_completos_incrementales_y_al_dia():
    cerrada = ci.ultima_rueda_cerrada(HOY)
    estados = {
        "AL_DIA": CiclosProxyEstado(simbolo="AL_DIA", historia_completa=1),
        "ATRASADO": CiclosProxyEstado(simbolo="ATRASADO", historia_completa=1),
        "SIN_HISTORIA": CiclosProxyEstado(simbolo="SIN_HISTORIA", historia_completa=0),
    }
    ultimas = {"AL_DIA": cerrada, "ATRASADO": cerrada - timedelta(days=10), "SIN_HISTORIA": cerrada}
    completos, incrementales = ci.planificar(["AL_DIA", "ATRASADO", "SIN_HISTORIA", "NUEVO"], estados, ultimas, HOY)
    assert completos == ["SIN_HISTORIA", "NUEVO"]
    assert incrementales == {"ATRASADO": cerrada - timedelta(days=10 + ci.SOLAPE_DIAS)}


# -- corrida -----------------------------------------------------------------------------------

def test_primera_corrida_baja_la_historia_entera_de_los_simbolos_activos(db, yahoo_falso):
    res = ci.correr(db, pausa_seg=0)
    assert res["resultado"] == "ok" and res["completos"] == len(SIMBOLOS) and res["incrementales"] == 0
    pedidos = {s for lote, _ in yahoo_falso["pedidos"] for s in lote}
    assert pedidos == SIMBOLOS                                  # no baja los inactivos
    assert all(desde == ci.INICIO_HISTORIA for _, desde in yahoo_falso["pedidos"])
    fechas = _fechas(db, "SPY")
    assert fechas[0] == ci.INICIO_HISTORIA and fechas[-1] == AYER and HOY not in fechas


def test_guarda_con_la_clave_de_referencia_la_moneda_y_la_fuente(db, yahoo_falso):
    ci.correr(db, pausa_seg=0)
    monedas = {r.ticker: r.moneda for r in db.query(BarraOHLCV.ticker, BarraOHLCV.moneda).distinct()}
    assert monedas["SPY@BENCH"] == "USD" and monedas["^BVSP@BENCH"] == "BRL"
    assert monedas["BRL=X@BENCH"] == "FX" and monedas["^MERV@BENCH"] == "ARS"
    assert {r.fuente for r in db.query(BarraOHLCV.fuente).distinct()} == {"yahoo"}
    assert all(r.apertura is None for r in db.query(BarraOHLCV).limit(50))     # sólo cierres


def test_el_estado_resume_la_cobertura_real(db, yahoo_falso):
    ci.correr(db, pausa_seg=0)
    est = db.get(CiclosProxyEstado, "XLK")
    assert est.estado == "ok" and est.historia_completa == 1
    assert est.primera_fecha == ci.INICIO_HISTORIA and est.ultima_fecha == AYER
    assert est.n_barras == (AYER - ci.INICIO_HISTORIA).days + 1
    fila = next(x for x in ci.estado(db) if x["simbolo"] == "XLK")
    assert fila["grupos"] == ["xlk"] and fila["desactualizado"] is False and fila["estado"] == "ok"


def test_segunda_corrida_al_dia_no_pide_nada(db, yahoo_falso):
    ci.correr(db, pausa_seg=0)
    yahoo_falso["pedidos"].clear()
    res = ci.correr(db, pausa_seg=0)
    assert res["resultado"] == "ok" and res["completos"] == 0 and res["incrementales"] == 0
    assert yahoo_falso["pedidos"] == []


def test_incremental_pide_con_solape_y_suma_solo_lo_nuevo(db, yahoo_falso):
    yahoo_falso["fin"] = HOY - timedelta(days=12)
    ci.correr(db, pausa_seg=0)
    antes = len(_fechas(db, "SPY"))
    yahoo_falso["pedidos"].clear()
    yahoo_falso["fin"] = AYER
    res = ci.correr(db, pausa_seg=0)
    assert res["completos"] == 0 and res["incrementales"] == len(SIMBOLOS) and res["reajustados"] == 0
    assert {desde for _, desde in yahoo_falso["pedidos"]} == {HOY - timedelta(days=12 + ci.SOLAPE_DIAS)}
    assert len(_fechas(db, "SPY")) == antes + 11
    assert db.get(CiclosProxyEstado, "SPY").ultima_fecha == AYER


def test_un_reajuste_de_yahoo_vuelve_a_bajar_la_serie_entera_en_una_sola_escala(db, yahoo_falso):
    yahoo_falso["fin"] = HOY - timedelta(days=12)
    ci.correr(db, pausa_seg=0)
    yahoo_falso["pedidos"].clear()
    yahoo_falso["fin"], yahoo_falso["factor"] = AYER, 0.97            # dividendo: toda la historia baja 3 %
    res = ci.correr(db, pausa_seg=0)
    assert res["reajustados"] == len(SIMBOLOS)
    assert any(desde == ci.INICIO_HISTORIA for _, desde in yahoo_falso["pedidos"])
    for d in (ci.INICIO_HISTORIA, MITAD, HOY - timedelta(days=15), AYER):
        fila = db.query(BarraOHLCV).filter_by(ticker="SPY@BENCH", fecha=d).one()
        assert float(fila.cierre) == pytest.approx(_valor("SPY", d, 0.97), rel=1e-6)
    assert db.get(CiclosProxyEstado, "SPY").reajustes == 1


def test_un_reajuste_sin_poder_rebajar_no_mezcla_escalas(db, yahoo_falso):
    yahoo_falso["fin"] = HOY - timedelta(days=12)
    ci.correr(db, pausa_seg=0)
    guardado = float(db.query(BarraOHLCV).filter_by(ticker="SPY@BENCH", fecha=MITAD).one().cierre)
    yahoo_falso["pedidos"].clear()
    yahoo_falso["fin"], yahoo_falso["factor"] = AYER, 0.97
    yahoo_falso["limitado_desde_llamada"] = 2                           # la 1ª (incremental) pasa, la re-descarga no
    res = ci.correr(db, tanda=100, pausa_seg=0)
    assert res["resultado"] == "rate_limited"
    assert db.get(CiclosProxyEstado, "SPY").ultima_fecha == HOY - timedelta(days=12)   # no sumó barras en otra escala
    assert float(db.query(BarraOHLCV).filter_by(ticker="SPY@BENCH", fecha=MITAD).one().cierre) == guardado


def test_un_simbolo_que_yahoo_no_devuelve_queda_no_encontrado_y_no_corta_al_resto(db, yahoo_falso):
    yahoo_falso["ausentes"] = {"EWZ"}
    res = ci.correr(db, pausa_seg=0)
    assert res["sin_datos"] == ["EWZ"]
    est = db.get(CiclosProxyEstado, "EWZ")
    assert est.estado == "no_encontrado" and est.n_barras == 0 and est.historia_completa == 0
    assert db.get(CiclosProxyEstado, "XLK").estado == "ok"
    assert _fechas(db, "EWZ") == []
    fila = next(x for x in ci.estado(db) if x["simbolo"] == "EWZ")
    assert fila["n_barras"] == 0 and fila["primera_fecha"] is None


def test_un_limite_de_tasa_corta_guarda_lo_obtenido_y_no_marca_no_encontrado(db, yahoo_falso):
    yahoo_falso["limitado_desde_llamada"] = 2
    res = ci.correr(db, tanda=3, pausa_seg=0)
    assert res["resultado"] == "rate_limited"
    assert len(yahoo_falso["pedidos"]) == 2                              # no siguió pidiendo
    estados = {e.simbolo: e for e in db.query(CiclosProxyEstado)}
    assert sum(1 for e in estados.values() if e.estado == "ok") == 3
    pendientes = [e for e in estados.values() if e.estado != "ok"]
    assert pendientes and all(e.estado == "error" and "límite" in e.error for e in pendientes)
    # La corrida siguiente retoma sólo lo que faltó, sin perder lo ya guardado.
    yahoo_falso["limitado_desde_llamada"] = None
    yahoo_falso["pedidos"].clear()
    res = ci.correr(db, tanda=3, pausa_seg=0)
    assert res["resultado"] == "ok" and res["completos"] == len(pendientes)
    assert all(e.estado == "ok" for e in db.query(CiclosProxyEstado))


def test_pide_en_tandas(db, yahoo_falso):
    ci.correr(db, tanda=3, pausa_seg=0)
    assert [len(lote) for lote, _ in yahoo_falso["pedidos"]] == [3, 3, 2]


def test_estado_marca_desactualizado(db, yahoo_falso):
    yahoo_falso["fin"] = HOY - timedelta(days=30)
    ci.correr(db, pausa_seg=0)
    assert all(x["desactualizado"] for x in ci.estado(db))


def test_sin_fuentes_externas_no_hace_nada(db, yahoo_falso, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    assert ci.correr(db, pausa_seg=0)["resultado"] == "sin_fuentes"
    assert yahoo_falso["pedidos"] == [] and db.query(BarraOHLCV).count() == 0


def test_catalogo_vacio_no_hace_nada(db, monkeypatch, tmp_path):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(tmp_path / "no-existe.json"))
    assert ci.correr(db, pausa_seg=0)["resultado"] == "catalogo_vacio"


def test_si_el_sync_no_suelta_el_lock_se_descarta_la_corrida(db, yahoo_falso, monkeypatch):
    monkeypatch.setattr(ci, "LOCK_ESCRITURA_TIMEOUT_SEG", 0.05)
    assert sync_lock.lock.acquire(timeout=1)
    try:
        assert ci.correr(db, pausa_seg=0)["resultado"] == "lock_ocupado"
    finally:
        sync_lock.lock.release()
    assert db.query(BarraOHLCV).count() == 0


def test_dos_corridas_a_la_vez_no_se_pisan(db, yahoo_falso):
    assert ci._lock_ingesta.acquire(blocking=False)
    try:
        assert ci.correr(db, pausa_seg=0)["resultado"] == "en_curso"
    finally:
        ci._lock_ingesta.release()


def test_no_toca_otras_series_de_serie_ohlcv(db, yahoo_falso):
    db.add(BarraOHLCV(ticker="AAPL", fecha=AYER, cierre=1, moneda="ARS", fuente="iol"))
    db.add(BarraOHLCV(ticker="AAPL@SUB", fecha=AYER, cierre=2, moneda="USD", fuente="yahoo"))
    db.commit()
    ci.correr(db, pausa_seg=0)
    assert db.query(BarraOHLCV).filter(BarraOHLCV.ticker.in_(["AAPL", "AAPL@SUB"])).count() == 2


def test_una_descarga_entera_reemplaza_lo_que_habia_de_ese_simbolo(db, yahoo_falso):
    # Lo que dejó `benchmarks.py` (con velas) de una escala anterior no se mezcla con la serie nueva.
    db.add(BarraOHLCV(ticker="SPY@BENCH", fecha=MITAD, apertura=1, maximo=3, minimo=1, cierre=2,
                      moneda="USD", fuente="yahoo"))
    db.commit()
    ci.correr(db, pausa_seg=0)
    fila = db.query(BarraOHLCV).filter_by(ticker="SPY@BENCH", fecha=MITAD).one()
    assert float(fila.cierre) == pytest.approx(_valor("SPY", MITAD))
