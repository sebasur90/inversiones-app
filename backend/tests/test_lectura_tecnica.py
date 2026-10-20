"""Lectura del gráfico ("Qué dice el gráfico"): motor puro y endpoint."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, BarraOHLCV, InstrumentoInversion, get_db
from app.main import app
from app.services import lectura_tecnica_engine as lt
from app.services.indicadores_engine import Barra

HOY = date.today()


def _barras(cierres):
    inicio = date(2026, 1, 1)
    return [Barra(fecha=inicio + timedelta(days=i), cierre=c, maximo=c, minimo=c) for i, c in enumerate(cierres)]


def _oscilante(n=100):
    """Ondas entre 90 y 110 con período 20: soporte en 90 y resistencia en 110."""
    out = []
    for i in range(n):
        fase = i % 20
        out.append(100 + 2 * fase if fase <= 5 else 110 - 2 * (fase - 5) if fase <= 15 else 90 + 2 * (fase - 15))
    return out


# ── Tendencia ────────────────────────────────────────────────────────────────

def test_tendencia_alcista_con_precio_arriba_y_media_subiendo():
    t = lt.tendencia([100.0 + i for i in range(70)])
    assert t["estado"] == "alcista"
    assert t["distancia_pct"] > 0 and t["pendiente_pct"] > 0
    assert t["sma"] == pytest.approx(sum(range(120, 170)) / 50)
    assert (t["periodo_sma"], t["ruedas_pendiente"]) == (50, 10)


def test_tendencia_bajista_con_precio_abajo_y_media_bajando():
    assert lt.tendencia([200.0 - i for i in range(70)])["estado"] == "bajista"


def test_tendencia_mixta_si_el_precio_cruza_la_media_antes_de_que_gire():
    # Subió 70 ruedas y la última se desplomó: el precio queda abajo de una media que sigue subiendo.
    t = lt.tendencia([100.0 + i for i in range(70)] + [50.0])
    assert t["estado"] == "mixta" and t["distancia_pct"] < 0 and t["pendiente_pct"] > 0


def test_tendencia_sin_historia_suficiente_es_none():
    assert lt.tendencia([100.0] * 59) is None


# ── Momentum ─────────────────────────────────────────────────────────────────

def test_momentum_por_umbrales_de_rsi():
    assert lt.momentum([100.0 + i for i in range(30)])["estado"] == "sobrecompra"
    assert lt.momentum([100.0 - i for i in range(30)])["estado"] == "sobreventa"
    m = lt.momentum([100.0 + (i % 2) for i in range(30)])
    assert m["estado"] == "neutral" and 30 <= m["rsi"] <= 70 and m["periodo_rsi"] == 14


def test_momentum_sin_historia_es_none():
    assert lt.momentum([100.0] * 5) is None


# ── Niveles ──────────────────────────────────────────────────────────────────

def test_niveles_cercanos_toma_el_soporte_y_la_resistencia_que_encierran_el_cierre():
    barras = _barras(_oscilante())
    soporte, resistencia = lt.niveles_cercanos(barras)
    cierre = barras[-1].cierre
    assert round(soporte["precio"]) == 90 and round(resistencia["precio"]) == 110
    assert soporte["distancia_pct"] == pytest.approx((soporte["precio"] / cierre - 1) * 100)
    assert soporte["distancia_pct"] < 0 < resistencia["distancia_pct"]
    assert soporte["toques"] >= 2


def test_niveles_sin_pivotes_quedan_vacios():
    assert lt.niveles_cercanos(_barras([100.0 + i for i in range(40)])) == (None, None)
    assert lt.niveles_cercanos([]) == (None, None)


# ── Fuerza relativa ──────────────────────────────────────────────────────────

def _ventana(inicio, fin):
    n = lt.RUEDAS_FUERZA + 1
    return [inicio + (fin - inicio) * i / (n - 1) for i in range(n)]


def test_fuerza_relativa_en_puntos_contra_el_indice():
    f = lt.fuerza_relativa(_ventana(100, 110), _ventana(1000, 1050))
    assert f["estado"] == "mejor"
    assert f["retorno_pct"] == pytest.approx(10.0) and f["retorno_benchmark_pct"] == pytest.approx(5.0)
    assert f["diferencia_puntos"] == pytest.approx(5.0) and f["ruedas"] == lt.RUEDAS_FUERZA
    assert lt.fuerza_relativa(_ventana(100, 105), _ventana(1000, 1100))["estado"] == "peor"
    assert lt.fuerza_relativa(_ventana(100, 105), _ventana(1000, 1055))["estado"] == "parecida"


def test_fuerza_relativa_sin_indice_en_las_puntas_es_none():
    bench = _ventana(1000, 1050)
    bench[0] = None
    assert lt.fuerza_relativa(_ventana(100, 110), bench) is None
    assert lt.fuerza_relativa([100.0] * 10, [1000.0] * 10) is None


def test_leer_sin_barras_no_inventa_nada():
    out = lt.leer([])
    assert out == {
        "fecha": None, "ultimo_cierre": None, "tendencia": None, "momentum": None,
        "soporte": None, "resistencia": None, "fuerza_relativa": None,
    }


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
        # El Merval sube el doble de rápido: la acción le pierde.
        m = 50000.0 * (1 + 0.004 * i)
        s.add(BarraOHLCV(ticker="^MERV@BENCH", fecha=f, apertura=m, maximo=m, minimo=m, cierre=m,
                         volumen=None, moneda="ARS", fuente="yahoo"))
    s.add(InstrumentoInversion(ticker="OSC", nombre="Oscilante", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))
    for i, c in enumerate(_oscilante()):
        s.add(BarraOHLCV(ticker="OSC", fecha=HOY - timedelta(days=110 - i), apertura=c, maximo=c, minimo=c,
                         cierre=c, volumen=1e5, moneda="ARS", fuente="yahoo"))
    s.add(InstrumentoInversion(ticker="KO", nombre="Coca-Cola", tipo_instrumento="Accion", mercado="NYSE", moneda="USD"))
    for i in range(80):
        c = 60.0 + 0.1 * i
        s.add(BarraOHLCV(ticker="KO", fecha=HOY - timedelta(days=90 - i), apertura=c, maximo=c, minimo=c,
                         cierre=c, volumen=1e5, moneda="USD", fuente="yahoo"))
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


def test_endpoint_lectura_completa(client):
    r = client.get("/api/inversiones/tecnico/GGAL/lectura")
    assert r.status_code == 200
    d = r.json()
    assert d["variante"] == "local" and d["moneda"] == "ARS"
    assert d["ultimo_cierre"] == pytest.approx(1000.0 * (1 + 0.002 * 119))
    assert d["tendencia"]["estado"] == "alcista"
    assert d["momentum"]["estado"] == "sobrecompra"           # subió todas las ruedas
    assert d["benchmark"] == "^MERV" and d["benchmark_nombre"]
    assert d["fuerza_relativa"]["estado"] == "peor"


def test_endpoint_niveles_cercanos(client):
    d = client.get("/api/inversiones/tecnico/OSC/lectura?variante=local").json()
    assert round(d["soporte"]["precio"]) == 90 and round(d["resistencia"]["precio"]) == 110
    assert d["tendencia"]["estado"] in ("alcista", "bajista", "mixta")


def test_endpoint_sin_indice_en_la_base_no_sale_a_bajarlo(client):
    d = client.get("/api/inversiones/tecnico/KO/lectura").json()
    assert d["moneda"] == "USD" and d["tendencia"]["estado"] == "alcista"
    assert d["benchmark"] is None and d["fuerza_relativa"] is None


def test_endpoint_validaciones(client):
    assert client.get("/api/inversiones/tecnico/NOEXISTE/lectura").status_code == 404
    assert client.get("/api/inversiones/tecnico/GGAL/lectura?variante=xx").status_code == 422
