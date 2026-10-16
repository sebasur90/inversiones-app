"""Ingesta de clasificación y fundamentales: universo, prioridad, topes, backoff, corte por límite
de tasa, un solo commit y conversión a USD. Sin red: Yahoo se reemplaza por funciones fijas."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, ClasificacionAuto, ClasificacionOverride, FundamentalesSnapshot, IndiceMercado,
    IngestaFundamentales, InstrumentoInversion, ParOverride, WatchlistItem,
)
from app.services import fundamentales_ingesta as fi
from app.services import sync_lock
from app.services.market_data import yahoo

HOY = date.today()

CATALOGO = [
    {"simbolo": "KO", "descripcion": "Cedear Coca Cola", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "KOD", "descripcion": "Cedear Coca Cola", "moneda": "USD", "tipo": "CEDEAR"},
    {"simbolo": "PEP", "descripcion": "Cedear Pepsico", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "SPY", "descripcion": "Cedear SPDR S&P 500", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "PETR3", "descripcion": "Cedear Petroleo Brasileiro", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "PBR", "descripcion": "Cedear Petroleo Brasileiro", "moneda": "ARS", "tipo": "CEDEAR"},
    {"simbolo": "GGAL", "descripcion": "Grupo Financiero Galicia", "moneda": "ARS", "tipo": "Acción"},
    {"simbolo": "ALUA", "descripcion": "Aluar", "moneda": "ARS", "tipo": "Acción"},
    {"simbolo": "AL30", "descripcion": "Bono AL30", "moneda": "ARS", "tipo": "Bono"},
]
SEED = {"variantes": {}, "simbolos_yahoo": {"PETR3": "PBR", "GGAL": "GGAL"}, "exposicion": {}}

INFO = {
    "KO": {"quoteType": "EQUITY", "longName": "Coca-Cola", "sector": "Consumer Defensive",
           "industry": "Beverages - Non-Alcoholic", "country": "United States",
           "currency": "USD", "financialCurrency": "USD", "marketCap": 3.0e11, "trailingPE": 25.0},
    "PEP": {"quoteType": "EQUITY", "longName": "PepsiCo", "sector": "Consumer Defensive",
            "industry": "Beverages - Non-Alcoholic", "country": "United States",
            "currency": "USD", "marketCap": 2.0e11, "trailingPE": 20.0},
    "SPY": {"quoteType": "ETF", "longName": "SPDR S&P 500", "category": "Large Blend",
            "currency": "USD", "totalAssets": 5.0e11, "netExpenseRatio": 0.09},
    "PBR": {"quoteType": "EQUITY", "longName": "Petrobras", "sector": "Energy",
            "industry": "Oil & Gas Integrated", "country": "Brazil", "currency": "USD",
            "financialCurrency": "BRL", "marketCap": 8.0e10, "netIncomeToCommon": 1.0e11},
    "GGAL": {"quoteType": "EQUITY", "longName": "Galicia", "sector": "Financial Services",
             "industry": "Banks - Regional", "country": "Argentina", "currency": "USD",
             "financialCurrency": "ARS", "marketCap": 6.0e9, "netIncomeToCommon": 1.2e12},
    "ALUA.BA": {"quoteType": "EQUITY", "longName": "Aluar", "sector": "Basic Materials",
                "industry": "Aluminum", "country": "Argentina", "currency": "ARS",
                "financialCurrency": "USD", "marketCap": 3.0e12},
}
SERIE = [{"fecha": "2026-01-05", "cierre": 10.0}, {"fecha": "2026-10-05", "cierre": 12.0}]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def llamadas(monkeypatch):
    """Yahoo falso: responde `INFO`; registra qué símbolos se pidieron."""
    pedidos: list[str] = []

    def _fund(simbolo):
        pedidos.append(simbolo)
        if simbolo in INFO:
            return yahoo.ResultadoYahoo(yahoo.ESTADO_OK, datos=dict(INFO[simbolo]))
        return yahoo.ResultadoYahoo(yahoo.ESTADO_NO_ENCONTRADO)

    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(fi, "cargar_catalogo", lambda: CATALOGO)
    monkeypatch.setattr(fi, "cargar_seed", lambda: SEED)
    monkeypatch.setattr(yahoo, "fetch_fundamentales", _fund)
    monkeypatch.setattr(yahoo, "fetch_cierres_semanales",
                        lambda s, **k: yahoo.ResultadoYahoo(yahoo.ESTADO_OK, datos=list(SERIE)))
    monkeypatch.setattr(fi, "_cotizacion_fx", lambda par: {"BRLUSD=X": 0.2}.get(par))
    return pedidos


def _mep(db, valor=1000.0):
    db.add(IndiceMercado(fecha=HOY, mep=valor))
    db.commit()


def _correr(db, **kw):
    kw.setdefault("pausa_seg", 0)
    return fi.correr(db, **kw)


# ── universo ──────────────────────────────────────────────────────────────

def test_universo_colapsa_variantes_y_marca_renta_fija(db, llamadas):
    db.add(InstrumentoInversion(ticker="KOD", nombre="KO", tipo_instrumento="CEDEAR", mercado="BCBA", moneda="USD"))
    db.add(InstrumentoInversion(ticker="AL30", nombre="AL30", tipo_instrumento="Bono", mercado="BCBA", moneda="USD"))
    db.commit()
    u = fi.construir_universo(db)
    assert "KOD" not in u
    assert u["KO"].propio and u["KO"].tickers_locales == {"KO", "KOD"}
    assert u["KO"].simbolo_yahoo == "KO"
    assert u["PETR3"].simbolo_yahoo == "PBR" and u["PETR3"].metodo == "seed"
    assert u["ALUA"].simbolo_yahoo == "ALUA.BA"
    assert u["AL30"].metodo == "no_apto" and u["AL30"].propio


def test_universo_incluye_par_agregado_fuera_del_catalogo_y_override_de_simbolo(db, llamadas):
    from datetime import datetime
    db.add(ParOverride(ticker_base="KO", par="MNST", accion="agregar", fecha=datetime.utcnow()))
    db.add(ClasificacionOverride(ticker_base="ALUA", campo="simbolo_yahoo", valor="alua.ba",
                                 fecha_actualizacion=datetime.utcnow()))
    db.commit()
    u = fi.construir_universo(db)
    assert u["MNST"].simbolo_yahoo == "MNST"
    assert u["ALUA"].simbolo_yahoo == "ALUA.BA" and u["ALUA"].metodo == "manual"


# ── cola ──────────────────────────────────────────────────────────────────

def test_cola_prioriza_lo_propio_y_agrupa_por_simbolo(db, llamadas):
    db.add(WatchlistItem(ticker="PEP", nombre="Pepsi", tipo_instrumento="CEDEAR"))
    db.commit()
    u = fi.construir_universo(db)
    cola = fi.armar_cola(u, {}, HOY)
    assert cola[0].simbolo_yahoo == "PEP" and cola[0].prioridad == 1
    pbr = next(t for t in cola if t.simbolo_yahoo == "PBR")
    assert {e.ticker_base for e in pbr.emisores} == {"PBR", "PETR3"}
    assert all(t.simbolo_yahoo != "AL30" for t in cola)


def test_cola_respeta_frescura_y_backoff(db, llamadas):
    u = fi.construir_universo(db)
    estado = {
        "KO": ClasificacionAuto(ticker_base="KO", simbolo_yahoo="KO", estado="ok",
                                fecha_fundamentales=HOY - timedelta(days=3)),
        "PEP": ClasificacionAuto(ticker_base="PEP", simbolo_yahoo="PEP", estado="error",
                                 proximo_intento=HOY + timedelta(days=2)),
        "SPY": ClasificacionAuto(ticker_base="SPY", simbolo_yahoo="SPY", estado="ok",
                                 fecha_fundamentales=HOY - timedelta(days=30)),
    }
    simbolos = [t.simbolo_yahoo for t in fi.armar_cola(u, estado, HOY)]
    assert "KO" not in simbolos       # fresco
    assert "PEP" not in simbolos      # en backoff
    assert "SPY" in simbolos          # vencido


def test_cola_pares_de_lo_propio_antes_que_el_resto_vencido(db, llamadas):
    db.add(WatchlistItem(ticker="KO", nombre="KO", tipo_instrumento="CEDEAR"))
    db.commit()
    u = fi.construir_universo(db)
    viejo = HOY - timedelta(days=30)
    estado = {
        "KO": ClasificacionAuto(ticker_base="KO", simbolo_yahoo="KO", estado="ok",
                                industria_raw="Beverages - Non-Alcoholic", fecha_fundamentales=HOY),
        "PEP": ClasificacionAuto(ticker_base="PEP", simbolo_yahoo="PEP", estado="ok",
                                 industria_raw="Beverages - Non-Alcoholic", fecha_fundamentales=viejo),
        "SPY": ClasificacionAuto(ticker_base="SPY", simbolo_yahoo="SPY", estado="ok",
                                 industria_raw="Large Blend", fecha_fundamentales=viejo),
    }
    cola = [t for t in fi.armar_cola(u, estado, HOY) if t.simbolo_yahoo in ("PEP", "SPY")]
    assert [t.simbolo_yahoo for t in cola] == ["PEP", "SPY"]
    assert cola[0].prioridad == 2


def test_cola_simbolo_cambiado_se_repide_aunque_este_en_backoff(db, llamadas):
    u = fi.construir_universo(db)
    estado = {"PETR3": ClasificacionAuto(ticker_base="PETR3", simbolo_yahoo="PETR3.SA", estado="no_encontrado",
                                         proximo_intento=HOY + timedelta(days=80))}
    assert "PBR" in [t.simbolo_yahoo for t in fi.armar_cola(u, estado, HOY)]


# ── corrida ───────────────────────────────────────────────────────────────

def test_corrida_clasifica_guarda_snapshot_y_registra(db, llamadas):
    _mep(db)
    r = _correr(db)
    assert r["resultado"] == "ok"
    ko = db.get(ClasificacionAuto, "KO")
    assert ko.estado == "ok" and ko.sector == "Consumo básico" and ko.region == "EEUU"
    assert ko.industria == "Bebidas sin alcohol"
    spy = db.get(ClasificacionAuto, "SPY")
    assert spy.tipo == "CEDEAR-ETF" and spy.region == "EEUU"
    # PETR3 y PBR comparten el pedido y el snapshot
    assert llamadas.count("PBR") == 1
    assert db.get(ClasificacionAuto, "PETR3").sector == "Energía"
    snaps = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="PBR").all()
    assert len(snaps) == 1 and snaps[0].serie_semanal == SERIE
    fila = db.get(IngestaFundamentales, 1)
    assert fila.procesados == r["procesados"] and fila.resultado == "ok"
    assert r["cobertura"]["con_datos"] >= 6


def test_corrida_convierte_a_usd_y_marca_ratios_en_otra_moneda(db, llamadas):
    _mep(db, 1000.0)
    _correr(db)
    ko = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO").one()
    assert float(ko.market_cap_usd) == 3.0e11 and ko.ratios_precio_confiables == 1
    pbr = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="PBR").one()
    assert pbr.ratios_precio_confiables == 0
    assert pbr.metricas["_usd"]["netIncomeToCommon"] == pytest.approx(1.0e11 * 0.2)
    ggal = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="GGAL").one()
    assert ggal.metricas["_usd"]["netIncomeToCommon"] == pytest.approx(1.2e12 / 1000.0)
    alua = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="ALUA.BA").one()
    assert float(alua.market_cap_usd) == pytest.approx(3.0e12 / 1000.0)


def test_sin_mep_el_market_cap_en_pesos_queda_sin_dato(db, llamadas):
    _correr(db)
    alua = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="ALUA.BA").one()
    assert alua.market_cap_usd is None


def test_tope_por_corrida(db, llamadas):
    r = _correr(db, max_emisores=2)
    assert r["procesados"] == 2 and len(llamadas) == 2
    assert r["pendientes"] > 0


def test_corte_por_limite_de_tasa_guarda_lo_obtenido(db, llamadas, monkeypatch):
    def _fund(simbolo):
        llamadas.append(simbolo)
        if len(llamadas) >= 3:
            return yahoo.ResultadoYahoo(yahoo.ESTADO_RATE_LIMITED, error="429")
        return yahoo.ResultadoYahoo(yahoo.ESTADO_OK, datos=dict(INFO.get(simbolo, INFO["KO"])))
    monkeypatch.setattr(yahoo, "fetch_fundamentales", _fund)
    r = _correr(db)
    assert r["resultado"] == "rate_limited"
    assert r["procesados"] == 2 and len(llamadas) == 3
    assert db.query(ClasificacionAuto).filter_by(estado="ok").count() >= 2
    assert db.get(IngestaFundamentales, 1).rate_limited == 1


def test_corte_por_errores_seguidos(db, llamadas, monkeypatch):
    def _fund(simbolo):
        llamadas.append(simbolo)
        return yahoo.ResultadoYahoo(yahoo.ESTADO_ERROR, error="timeout")
    monkeypatch.setattr(yahoo, "fetch_fundamentales", _fund)
    r = _correr(db)
    assert len(llamadas) == fi.FALLOS_SEGUIDOS_CORTE
    assert r["fallidos"] == fi.FALLOS_SEGUIDOS_CORTE


def test_backoff_exponencial_y_no_encontrado(db, llamadas, monkeypatch):
    def _fund(simbolo):
        if simbolo == "KO":
            return yahoo.ResultadoYahoo(yahoo.ESTADO_ERROR, error="timeout")
        return yahoo.ResultadoYahoo(yahoo.ESTADO_NO_ENCONTRADO)
    monkeypatch.setattr(yahoo, "fetch_fundamentales", _fund)
    _correr(db, tickers=["KO", "PEP"])
    ko = db.get(ClasificacionAuto, "KO")
    assert ko.estado == "error" and ko.intentos_fallidos == 1
    assert ko.proximo_intento == HOY + timedelta(days=2)
    pep = db.get(ClasificacionAuto, "PEP")
    assert pep.estado == "no_encontrado"
    assert pep.proximo_intento == HOY + timedelta(days=fi.NO_ENCONTRADO_REINTENTO_DIAS)
    _correr(db, tickers=["KO"])
    ko = db.get(ClasificacionAuto, "KO")
    assert ko.intentos_fallidos == 2 and ko.proximo_intento == HOY + timedelta(days=4)


def test_error_suelto_no_borra_una_clasificacion_buena(db, llamadas, monkeypatch):
    _correr(db, tickers=["KO"])
    monkeypatch.setattr(yahoo, "fetch_fundamentales",
                        lambda s: yahoo.ResultadoYahoo(yahoo.ESTADO_ERROR, error="timeout"))
    _correr(db, tickers=["KO"])
    ko = db.get(ClasificacionAuto, "KO")
    assert ko.estado == "ok" and ko.sector == "Consumo básico" and ko.intentos_fallidos == 1


def test_actualizacion_fallida_deja_el_snapshot_anterior_intacto(db, llamadas, monkeypatch):
    """Si Yahoo falla, no se pierde ni se pisa la última foto buena: la valuación sigue usándola (y avisa su fecha)."""
    _correr(db, tickers=["KO"])
    antes = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO").one()
    metricas, fecha = dict(antes.metricas), antes.fecha
    monkeypatch.setattr(yahoo, "fetch_fundamentales",
                        lambda s: yahoo.ResultadoYahoo(yahoo.ESTADO_ERROR, error="timeout"))
    _correr(db, tickers=["KO"])
    despues = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO").all()
    assert len(despues) == 1 and despues[0].metricas == metricas and despues[0].fecha == fecha


def test_tickers_acepta_variantes(db, llamadas):
    _correr(db, tickers=["KOD"])
    assert llamadas == ["KO"]


def test_un_solo_commit(db, llamadas, monkeypatch):
    commits = []
    original = db.commit
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), original())[1])
    _correr(db)
    assert len(commits) == 1


def test_lock_del_sync_ocupado_descarta_la_corrida(db, llamadas, monkeypatch):
    monkeypatch.setattr(fi, "LOCK_ESCRITURA_TIMEOUT_SEG", 0.01)
    sync_lock.lock.acquire()
    try:
        r = _correr(db)
    finally:
        sync_lock.lock.release()
    assert r["resultado"] == "lock_ocupado"
    assert db.query(ClasificacionAuto).count() == 0


def test_ingesta_en_curso_no_se_superpone(db, llamadas):
    fi._lock_ingesta.acquire()
    try:
        assert _correr(db)["resultado"] == "en_curso"
    finally:
        fi._lock_ingesta.release()
    assert llamadas == []


def test_sin_apis_externas_no_pide_nada(db, llamadas, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    assert _correr(db)["resultado"] == "sin_fuentes"
    assert llamadas == []


def test_purga_snapshots_viejos(db, llamadas):
    for i in range(1, fi.SNAPSHOTS_RETENIDOS + 3):
        db.add(FundamentalesSnapshot(simbolo_yahoo="KO", fecha=HOY - timedelta(days=7 * i), metricas={}))
    db.commit()
    _correr(db, tickers=["KO"])
    assert db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO").count() == fi.SNAPSHOTS_RETENIDOS
    assert db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO", fecha=HOY).count() == 1


def test_serie_de_cinco_anios_solo_en_el_snapshot_mas_nuevo(db, llamadas, monkeypatch):
    pedidas = []

    def _serie(simbolo, semanas=56):
        pedidas.append(semanas)
        return yahoo.ResultadoYahoo(yahoo.ESTADO_OK, datos=list(SERIE))
    monkeypatch.setattr(yahoo, "fetch_cierres_semanales", _serie)
    db.add(FundamentalesSnapshot(simbolo_yahoo="KO", fecha=HOY - timedelta(days=7), metricas={},
                                 serie_semanal=[{"fecha": "2026-01-01", "cierre": 1.0}]))
    db.commit()
    _correr(db, tickers=["KO"])
    assert pedidas == [fi.SEMANAS_SERIE]
    viejo = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO", fecha=HOY - timedelta(days=7)).one()
    nuevo = db.query(FundamentalesSnapshot).filter_by(simbolo_yahoo="KO", fecha=HOY).one()
    assert viejo.serie_semanal is None and nuevo.serie_semanal == SERIE


def test_forzar_repide_lo_fresco(db, llamadas):
    _correr(db)
    llamadas.clear()
    assert _correr(db)["procesados"] == 0          # todo fresco: nada que hacer
    assert _correr(db, forzar=True)["procesados"] > 0
    assert "KO" in llamadas
