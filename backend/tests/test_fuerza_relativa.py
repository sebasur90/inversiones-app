"""Fuerza relativa: motor puro, índices de referencia (benchmarks) y endpoint."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, BarraOHLCV, InstrumentoInversion, get_db
from app.main import app
from app.services import benchmarks, intervalos_engine as ie, ohlcv_analytics
from app.services import fuerza_relativa_engine as fr
from app.services.indicadores_engine import Barra
from app.services.market_data import yahoo
from app.services.market_data.ohlcv_types import BarraCruda

HOY = date.today()


def _b(fecha, cierre):
    return Barra(fecha=fecha, cierre=cierre)


# ── Motor puro ───────────────────────────────────────────────────────────────

def test_alinear_diario_arrastra_el_ultimo_cierre_del_indice_hasta_la_tolerancia():
    serie = [_b(date(2026, 3, d), 1.0) for d in (2, 3, 4, 5, 6, 16)]
    bench = [_b(date(2026, 3, 2), 10.0), _b(date(2026, 3, 4), 12.0), _b(date(2026, 3, 6), 14.0)]
    # El 3/3 el índice no operó → arrastra el del 2/3; el 5/3 → el del 4/3; el 16/3 está a 10 días → None.
    assert fr.alinear_benchmark(serie, bench) == [10.0, 10.0, 12.0, 12.0, 14.0, None]


def test_alinear_antes_del_inicio_del_indice_es_none():
    serie = [_b(date(2026, 3, 2), 1.0)]
    assert fr.alinear_benchmark(serie, [_b(date(2026, 3, 9), 10.0)]) == [None]
    assert fr.alinear_benchmark(serie, []) == [None]


def test_alinear_semanal_usa_el_mismo_periodo_y_no_la_misma_fecha():
    # La serie local cierra la semana el miércoles (feriados jueves y viernes); el índice, el viernes.
    serie = [_b(date(2026, 4, 1), 1.0), _b(date(2026, 4, 8), 1.0)]
    bench = [_b(date(2026, 3, 30), 10.0), _b(date(2026, 4, 3), 11.0), _b(date(2026, 4, 6), 12.0), _b(date(2026, 4, 10), 13.0)]
    assert fr.alinear_benchmark(serie, bench, ie.SEMANAL) == [11.0, 13.0]
    assert fr.alinear_benchmark(serie, bench, ie.MENSUAL) == [13.0, 13.0]


def test_fuerza_relativa_normaliza_a_100_en_la_primera_barra_visible():
    cierres = [10.0, 11.0, 12.0, 15.0]
    bench = [100.0, 100.0, 110.0, 110.0]
    out = fr.fuerza_relativa(cierres, bench, indice_desde=1, periodo_sma=2)
    # Base = 11/100 en la barra 1 → 100. La barra 0 queda en la misma escala (calentamiento).
    assert out["ratio"][1] == pytest.approx(100.0)
    assert out["ratio"][0] == pytest.approx(10 / 100 / (11 / 100) * 100)
    assert out["ratio"][2] == pytest.approx((12 / 110) / (11 / 100) * 100)
    assert out["sma"][2] == pytest.approx((out["ratio"][1] + out["ratio"][2]) / 2)


def test_activo_que_acompana_al_indice_queda_en_100():
    cierres = [50.0, 55.0, 60.5]
    bench = [100.0, 110.0, 121.0]
    assert fr.fuerza_relativa(cierres, bench)["ratio"] == pytest.approx([100.0, 100.0, 100.0])


def test_sin_barras_en_comun_todo_none():
    out = fr.fuerza_relativa([1.0, 2.0], [None, None])
    assert out == {"ratio": [None, None], "sma": [None, None]}


# ── Índices de referencia ────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_default_por_moneda():
    assert benchmarks.por_defecto("USD") == "SPY"
    assert benchmarks.por_defecto("ARS") == "^MERV"
    assert benchmarks.por_defecto("") == "SPY"


def _crudas(desde, n, cierre0=100.0):
    return [BarraCruda(fecha=desde + timedelta(days=i), cierre=cierre0 + i, apertura=cierre0 + i,
                       maximo=cierre0 + i + 1, minimo=cierre0 + i - 1, volumen=1e6) for i in range(n)]


def test_asegurar_baja_la_historia_una_sola_vez_y_guarda_con_su_moneda(db, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    llamadas = []

    def falso(simbolo, desde, hasta):
        llamadas.append(simbolo)
        return _crudas(HOY - timedelta(days=30), 40)           # incluye días de hoy en adelante

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", falso)
    assert benchmarks.asegurar(db, "^MERV") is True
    assert benchmarks.asegurar(db, "^MERV") is True
    assert llamadas == ["^MERV"]
    filas = db.query(BarraOHLCV).filter(BarraOHLCV.ticker == "^MERV@BENCH").all()
    assert filas and all(f.moneda == "ARS" and f.fuente == "yahoo" for f in filas)
    assert max(f.fecha for f in filas) < HOY                     # nunca persiste la rueda de hoy


def test_asegurar_sin_red_devuelve_false(db, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    assert benchmarks.asegurar(db, "SPY") is False               # conftest stubea Yahoo → None
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    assert benchmarks.asegurar(db, "SPY") is False


def test_refrescar_solo_toca_los_que_ya_existen_y_estan_atrasados(db, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    db.add(BarraOHLCV(ticker="SPY@BENCH", fecha=HOY - timedelta(days=20), cierre=100.0, apertura=100.0,
                      maximo=101.0, minimo=99.0, volumen=1.0, moneda="USD", fuente="yahoo"))
    db.commit()
    pedidos = []

    def falso(simbolo, desde, hasta):
        pedidos.append((simbolo, desde))
        return _crudas(desde, 25, 110.0)

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", falso)
    assert benchmarks.refrescar(db) > 0
    assert [p[0] for p in pedidos] == ["SPY"]                    # QQQ y ^MERV nunca se pidieron
    assert pedidos[0][1] == HOY - timedelta(days=27)             # solapa 7 días
    assert db.query(BarraOHLCV).filter(BarraOHLCV.ticker == "SPY@BENCH").count() > 1
    pedidos.clear()
    benchmarks.refrescar(db)
    assert pedidos == []                                         # ya al día


def test_los_indices_no_aparecen_como_series_de_un_ticker(db):
    db.add(BarraOHLCV(ticker="SPY@BENCH", fecha=HOY, cierre=1.0, moneda="USD", fuente="yahoo"))
    db.add(BarraOHLCV(ticker="GGAL", fecha=HOY, cierre=1.0, moneda="ARS", fuente="iol"))
    db.commit()
    assert set(ohlcv_analytics.variantes_de_ticker(db)) == {"GGAL"}


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)
    s = sesion()
    s.add(InstrumentoInversion(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))
    for i in range(120):
        f = HOY - timedelta(days=130 - i)
        c = 1000.0 * (1 + 0.002 * i)
        s.add(BarraOHLCV(ticker="GGAL", fecha=f, apertura=c, maximo=c * 1.01, minimo=c * 0.99, cierre=c,
                         volumen=1e5, moneda="ARS", fuente="yahoo"))
        # El Merval sube el doble de rápido que la acción → la fuerza relativa cae.
        m = 50000.0 * (1 + 0.004 * i)
        s.add(BarraOHLCV(ticker="^MERV@BENCH", fecha=f, apertura=m, maximo=m, minimo=m, cierre=m,
                         volumen=None, moneda="ARS", fuente="yahoo"))
    s.add(InstrumentoInversion(ticker="OSC", nombre="Oscilante", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))
    for i in range(100):
        f = HOY - timedelta(days=110 - i)
        fase = i % 20
        c = 100 + 2 * fase if fase <= 5 else 110 - 2 * (fase - 5) if fase <= 15 else 90 + 2 * (fase - 15)
        s.add(BarraOHLCV(ticker="OSC", fecha=f, apertura=c, maximo=c, minimo=c, cierre=c, volumen=1e5,
                         moneda="ARS", fuente="yahoo"))
    s.commit()
    s.close()

    def override():
        d = sesion()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_default_por_moneda_y_normalizacion(client):
    r = client.get("/api/inversiones/tecnico/GGAL/fuerza-relativa?variante=local")
    assert r.status_code == 200
    d = r.json()
    assert d["benchmark"] == "^MERV" and d["benchmark_moneda"] == "ARS" and d["advertencias"] == []
    assert len(d["fechas"]) == len(d["ratio"]) == len(d["sma"])
    assert d["ratio"][0] == pytest.approx(100.0)
    assert d["ratio"][-1] < 100.0                                # la acción le pierde al índice
    assert d["sma"][48] is None and d["sma"][49] is not None     # SMA(50) del ratio


def test_endpoint_respeta_desde_y_alinea_con_serie(client):
    desde = (HOY - timedelta(days=60)).isoformat()
    fr_ = client.get(f"/api/inversiones/tecnico/GGAL/fuerza-relativa?variante=local&desde={desde}").json()
    serie = client.get(f"/api/inversiones/tecnico/GGAL/serie?variante=local&desde={desde}").json()
    visibles = [b["fecha"] for b in serie["barras"][serie["indice_desde"]:]]
    assert fr_["fechas"] == visibles
    assert fr_["ratio"][0] == pytest.approx(100.0)               # base en la primera barra visible


def test_endpoint_semanal_y_benchmark_de_otra_moneda(client):
    d = client.get("/api/inversiones/tecnico/GGAL/fuerza-relativa?variante=local&intervalo=S").json()
    assert 15 <= len(d["fechas"]) <= 22 and d["ratio"][0] == pytest.approx(100.0)
    # SPY no está en la base y no hay red: se avisa; no se inventa nada.
    sin = client.get("/api/inversiones/tecnico/GGAL/fuerza-relativa?variante=local&benchmark=SPY").json()
    assert sin["advertencias"] == ["sin_benchmark"] and sin["ratio"] == []


def test_endpoint_validaciones(client):
    assert client.get("/api/inversiones/tecnico/GGAL/fuerza-relativa?benchmark=XXX").status_code == 422
    assert client.get("/api/inversiones/tecnico/NOEXISTE/fuerza-relativa").status_code == 404
    assert client.get("/api/inversiones/tecnico/GGAL/fuerza-relativa?intervalo=Z").status_code == 422


def test_serie_con_niveles_auto_devuelve_soportes_y_resistencias(client):
    sin = client.get("/api/inversiones/tecnico/OSC/serie?variante=local").json()
    assert sin["niveles_auto"] is None
    con = client.get("/api/inversiones/tecnico/OSC/serie?variante=local&niveles_auto=true").json()
    niveles = {(n["tipo"], round(n["precio"])): n["toques"] for n in con["niveles_auto"]}
    assert niveles == {("resistencia", 110): 5, ("soporte", 90): 4}
    assert all(set(n) >= {"precio", "toques", "ultima_fecha", "tipo", "puntaje"} for n in con["niveles_auto"])


def test_niveles_auto_se_calculan_sobre_el_tramo_visible(client):
    desde = (HOY - timedelta(days=30)).isoformat()
    corto = client.get(f"/api/inversiones/tecnico/OSC/serie?variante=local&niveles_auto=true&desde={desde}").json()
    assert corto["niveles_auto"] == []                           # en 30 días no hay dos toques del mismo nivel
