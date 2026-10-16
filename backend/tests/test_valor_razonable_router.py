"""`GET/PUT/DELETE /inversiones/valuacion/{ticker}/valor-razonable` sobre una DB con snapshots cargados."""
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, ClasificacionAuto, FundamentalesSnapshot, IndiceMercado, ValorSupuestos, get_db
from app.main import app
from app.services import clasificacion_analytics as ca

HOY = date.today()
URL = "/api/inversiones/valuacion"

# (val, fund, mcap): val > 1 = más cara. Todos los múltiplos escalan con `val` y no hay deuda neta
# (EV = capitalización), así que todos los métodos dan el mismo factor: mediana de los pares ÷ propio.
EMISORES = {
    "KO": (1.0, 1.0, 3.0e11),
    "PEP": (1.3, 1.2, 2.0e11),
    "MNST": (0.8, 0.9, 1.5e11),
    "KDP": (1.1, 0.8, 1.2e11),
    "CELH": (1.5, 1.4, 1.0e11),
}


def _metricas(val, fund, mcap, **extra):
    m = {
        "trailingPE": 20 * val, "forwardPE": 18 * val, "enterpriseToEbitda": 12 * val,
        "priceToSalesTrailing12Months": 3 * val, "priceToBook": 3 * val, "dividendYield": 2.0,
        "grossMargins": 0.4 * fund, "operatingMargins": 0.2 * fund, "profitMargins": 0.12 * fund,
        "returnOnEquity": 0.15 * fund, "returnOnAssets": 0.06 * fund, "debtToEquity": 60 / fund,
        "revenueGrowth": 0.06 * fund, "earningsGrowth": 0.08 * fund, "currency": "USD",
        "currentPrice": 100.0, "marketCap": mcap, "enterpriseValue": mcap,
        "_usd": {"market_cap": mcap, "freeCashflow": mcap * 0.04 / val},
    }
    m.update(extra)
    return m


@pytest.fixture
def sesion(monkeypatch):
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: [
        {"simbolo": t, "descripcion": t, "moneda": "ARS", "tipo": "CEDEAR"} for t in EMISORES
    ] + [{"simbolo": "KOD", "descripcion": "KO", "moneda": "USD", "tipo": "CEDEAR"}])
    monkeypatch.setattr(ca, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    for t, (val, fund, mcap) in EMISORES.items():
        db.add(ClasificacionAuto(
            ticker_base=t, simbolo_yahoo=t, estado="ok", tipo="CEDEAR-acción", nombre=f"{t} Inc",
            quote_type="EQUITY", sector="Consumo básico", industria="Bebidas sin alcohol",
            industria_raw="Beverages - Non-Alcoholic", pais="Estados Unidos", region="EEUU",
            intentos_fallidos=0, fecha_fundamentales=HOY,
        ))
        extra = {"targetMeanPrice": 130.0, "targetLowPrice": 110.0, "targetHighPrice": 150.0,
                 "numberOfAnalystOpinions": 20} if t == "KO" else {}
        db.add(FundamentalesSnapshot(
            simbolo_yahoo=t, fecha=HOY, moneda="USD", market_cap_usd=mcap, ratios_precio_confiables=1,
            metricas=_metricas(val, fund, mcap, **extra),
            serie_semanal=[{"fecha": (HOY - timedelta(weeks=52 - i)).isoformat(), "cierre": 50.0 + i} for i in range(53)],
        ))
    db.commit()
    db.close()
    return Sesion


@pytest.fixture
def client(sesion):
    def override():
        s = sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _esc(b, clave):
    return next(e for e in b["escenarios"] if e["clave"] == clave)


def test_valor_razonable_con_los_pares_automaticos(client):
    r = client.get(f"{URL}/KO/valor-razonable")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["estado"] == "ok" and b["version_reglas"] == 1 and b["ticker_base"] == "KO"
    assert b["precio"] == 100.0 and b["moneda"] == "USD" and b["elegido_por_usuario"] is False
    # mediana de val de los pares (0,8 / 1,1 / 1,3 / 1,5) = 1,2 → valor base 120; Q1 = 1,025; Q3 = 1,35
    assert _esc(b, "base")["valor"] == pytest.approx(120.0)
    assert _esc(b, "pesimista")["valor"] == pytest.approx(102.5)
    assert _esc(b, "optimista")["valor"] == pytest.approx(135.0)
    # margen de seguridad y potencial por separado
    assert _esc(b, "base")["margen_seguridad"] == pytest.approx(20 / 120)
    assert _esc(b, "base")["potencial"] == pytest.approx(0.20)
    assert {m["clave"] for m in b["metodos"] if m["estado"] == "usado"} == {
        "pe", "forward_pe", "ev_ebitda", "ps", "p_fcf", "pb"}
    assert {p["ticker_base"] for p in b["pares"]} == {"PEP", "MNST", "KDP", "CELH"}
    assert b["supuestos"]["por_defecto"] is True and b["limites"] and b["salvedad"]
    assert b["lectura"] == "por_debajo"      # 100 < pesimista 102,5


def test_la_variante_de_moneda_resuelve_el_mismo_emisor(client):
    assert client.get(f"{URL}/KOD/valor-razonable").json()["ticker_base"] == "KO"


def test_la_referencia_de_analistas_va_aparte_y_no_cambia_el_valor(client):
    b = client.get(f"{URL}/KO/valor-razonable").json()
    assert b["analistas"] == {"media": 130.0, "minimo": 110.0, "maximo": 150.0, "n": 20}
    assert _esc(b, "base")["valor"] == pytest.approx(120.0)
    assert client.get(f"{URL}/PEP/valor-razonable").json()["analistas"] is None


def test_con_elige_el_grupo_de_referencia_y_con_pocos_no_concluye(client):
    b = client.get(f"{URL}/KO/valor-razonable", params={"con": "PEP,MNST"}).json()
    assert b["elegido_por_usuario"] is True and b["estado"] == "sin_conclusion"
    assert b["escenarios"] == [] and any("sólo 2 pares" in f for f in b["faltantes"])


def test_ticker_sin_datos_responde_sin_datos(client):
    b = client.get(f"{URL}/ZZZZ/valor-razonable").json()
    assert b["estado"] == "sin_datos" and b["escenarios"] == [] and b["faltantes"]


def test_guardar_supuestos_recalcula_y_el_cache_no_devuelve_lo_viejo(client):
    antes = client.get(f"{URL}/KO/valor-razonable").json()
    r = client.put(f"{URL}/KO/valor-razonable/supuestos", json={"ajuste_pct": -10.0, "excluir": [], "multiplos": {}})
    assert r.status_code == 200, r.text
    despues = r.json()
    assert _esc(despues, "base")["valor"] == pytest.approx(_esc(antes, "base")["valor"] * 0.9)
    assert despues["supuestos"]["ajuste_pct"] == -10.0 and despues["supuestos"]["por_defecto"] is False
    # el GET siguiente ve los supuestos guardados
    assert client.get(f"{URL}/KO/valor-razonable").json()["supuestos"]["ajuste_pct"] == -10.0


def test_los_supuestos_son_del_emisor_y_valen_para_su_variante(client):
    client.put(f"{URL}/KOD/valor-razonable/supuestos", json={"ajuste_pct": 5.0})
    assert client.get(f"{URL}/KO/valor-razonable").json()["supuestos"]["ajuste_pct"] == 5.0


def test_supuestos_vacios_o_delete_restablecen(client, sesion):
    client.put(f"{URL}/KO/valor-razonable/supuestos", json={"ajuste_pct": 20.0})
    db = sesion()
    assert db.query(ValorSupuestos).count() == 1
    db.close()
    r = client.put(f"{URL}/KO/valor-razonable/supuestos", json={})
    assert r.json()["supuestos"]["por_defecto"] is True
    db = sesion()
    assert db.query(ValorSupuestos).count() == 0
    db.close()
    client.put(f"{URL}/KO/valor-razonable/supuestos", json={"excluir": ["ps"]})
    assert client.get(f"{URL}/KO/valor-razonable").json()["supuestos"]["excluir"] == ["ps"]
    assert client.delete(f"{URL}/KO/valor-razonable/supuestos").json()["supuestos"]["por_defecto"] is True


@pytest.mark.parametrize("cuerpo", [{"ajuste_pct": 99}, {"excluir": ["magia"]}, {"multiplos": {"pe": -1}}])
def test_supuestos_invalidos_dan_422_y_no_se_guardan(client, sesion, cuerpo):
    r = client.put(f"{URL}/KO/valor-razonable/supuestos", json=cuerpo)
    assert r.status_code == 422 and r.json()["detail"]
    db = sesion()
    assert db.query(ValorSupuestos).count() == 0
    db.close()


def test_multiplo_manual_pasa_por_la_api(client):
    r = client.put(f"{URL}/KO/valor-razonable/supuestos", json={"multiplos": {"pe": 30.0}})
    pe = next(m for m in r.json()["metodos"] if m["clave"] == "pe")
    assert pe["manual"] is True and pe["valores"]["base"] == pytest.approx(150.0)    # 100 × 30 ÷ 20


def test_con_admite_un_maximo_de_emisores(client):
    r = client.get(f"{URL}/KO/valor-razonable", params={"con": ",".join(f"T{i}" for i in range(30))})
    assert r.status_code == 422


def test_ningun_texto_de_la_respuesta_dice_compra_o_venta(client):
    prohibidas = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)

    def textos(o):
        if isinstance(o, str):
            yield o
        elif isinstance(o, dict):
            for v in o.values():
                yield from textos(v)
        elif isinstance(o, list):
            for v in o:
                yield from textos(v)

    for t in textos(client.get(f"{URL}/KO/valor-razonable").json()):
        assert not prohibidas.search(t), t
