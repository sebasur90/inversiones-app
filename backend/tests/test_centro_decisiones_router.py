"""Centro de Decisiones de punta a punta sobre una DB en memoria con datos ficticios y deterministas.

Cubre: análisis con datos completos y con faltantes, métricas no aplicables (ETF, banco), cotización vieja, fechas
incompatibles, simulación de compra y venta sin tocar la cartera real, posición en pérdida, mantener vs. reasignar,
guardar/recuperar/revisar decisiones sin pisar nada, fuentes que fallan, ARS/USD y cartera individual/consolidado.
"""
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    AjustesAvisos, BarraOHLCV, Base, ClasificacionAuto, Decision, DecisionSnapshot, FundamentalesSnapshot, IndiceMercado,
    InstrumentoInversion, MovimientoInversion, PrecioInstrumento, get_db,
)
from app.main import app
from app.services import clasificacion_analytics as ca
from app.services import diario_decisiones, interpretacion, valor_razonable_analytics

URL = "/api/inversiones"
HOY = date.today()
PROHIBIDAS = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)
MEP = 1000.0

EMISORES = {   # (val, fund, mcap, periodo contable hace N días)
    "KO": (1.0, 1.0, 3.0e11, 40),
    "PEP": (1.3, 1.2, 2.0e11, 40),
    "MNST": (0.8, 0.9, 1.5e11, 40),
    "KDP": (1.1, 0.8, 1.2e11, 300),     # balance de otro trimestre: la comparación tiene que avisarlo
    "CELH": (1.5, 1.4, 1.0e11, 40),
}


def _epoch(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _metricas(val, fund, mcap, dias_balance):
    return {
        "trailingPE": 20 * val, "forwardPE": 18 * val, "enterpriseToEbitda": 12 * val,
        "priceToSalesTrailing12Months": 3 * val, "priceToBook": 3 * val, "dividendYield": 2.5,
        "grossMargins": 0.4 * fund, "operatingMargins": 0.2 * fund, "profitMargins": 0.12 * fund,
        "returnOnEquity": 0.15 * fund, "returnOnAssets": 0.06 * fund, "debtToEquity": 60 / fund,
        "revenueGrowth": 0.06 * fund, "earningsGrowth": 0.08 * fund, "currency": "USD", "beta": 0.7,
        "payoutRatio": 0.6, "currentRatio": 1.3, "mostRecentQuarter": _epoch(HOY - timedelta(days=dias_balance)),
        "currentPrice": 100.0, "marketCap": mcap, "enterpriseValue": mcap,
        "_usd": {"market_cap": mcap, "freeCashflow": mcap * 0.04 / val},
    }


def _serie(semilla: float):
    return [{"fecha": (HOY - timedelta(weeks=104 - i)).isoformat(),
             "cierre": 50.0 + i * 0.3 + (3.0 if i % 4 == 0 else 0.0) * semilla} for i in range(105)]


def _barras(db, ticker, n=300, hasta=None):
    hasta = hasta or HOY - timedelta(days=1)
    for i in range(n):
        f = hasta - timedelta(days=n - 1 - i)
        c = 40.0 + i * 0.03 + (1.5 if i % 7 == 0 else 0.0)
        db.add(BarraOHLCV(ticker=ticker, fecha=f, apertura=c, maximo=c + 1, minimo=c - 1, cierre=c, volumen=1000,
                          moneda="USD", fuente="api"))


@pytest.fixture
def sesion(monkeypatch):
    catalogo = [{"simbolo": t, "descripcion": t, "moneda": "ARS", "tipo": "CEDEAR"} for t in EMISORES] + [
        {"simbolo": "SPYX", "descripcion": "ETF", "moneda": "ARS", "tipo": "CEDEAR"},
        {"simbolo": "BANCO", "descripcion": "BANCO", "moneda": "ARS", "tipo": "Acción"},
        {"simbolo": "MSFT", "descripcion": "MICROSOFT", "moneda": "ARS", "tipo": "CEDEAR"},
    ]
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: catalogo)
    monkeypatch.setattr(ca, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=MEP))
    for i, (t, (val, fund, mcap, dias)) in enumerate(EMISORES.items()):
        db.add(ClasificacionAuto(
            ticker_base=t, simbolo_yahoo=t, estado="ok", tipo="CEDEAR-acción", nombre=f"{t} Inc", quote_type="EQUITY",
            sector="Consumo básico", industria="Bebidas sin alcohol", industria_raw="Beverages - Non-Alcoholic",
            pais="Estados Unidos", region="EEUU", intentos_fallidos=0, fecha_fundamentales=HOY,
        ))
        db.add(FundamentalesSnapshot(simbolo_yahoo=t, fecha=HOY, moneda="USD", market_cap_usd=mcap,
                                     ratios_precio_confiables=1, metricas=_metricas(val, fund, mcap, dias),
                                     serie_semanal=_serie(1 + i * 0.2)))
    db.add(ClasificacionAuto(ticker_base="SPYX", simbolo_yahoo="SPYX", estado="ok", tipo="CEDEAR-ETF", nombre="ETF",
                             quote_type="ETF", sector="Consumo básico", industria=None, pais="Estados Unidos", region="EEUU",
                             intentos_fallidos=0, fecha_fundamentales=HOY))
    db.add(FundamentalesSnapshot(simbolo_yahoo="SPYX", fecha=HOY, moneda="USD", market_cap_usd=5e11, ratios_precio_confiables=1,
                                 metricas={"netExpenseRatio": 0.09, "yield": 0.015, "priceToBook": 4.0, "currency": "USD",
                                           "currentPrice": 400.0, "_usd": {"market_cap": 5e11}},
                                 serie_semanal=_serie(1)))
    db.add(ClasificacionAuto(ticker_base="BANCO", simbolo_yahoo="BANCO", estado="ok", tipo="Acción", nombre="Banco",
                             quote_type="EQUITY", sector="Financiero", industria="Bancos", industria_raw="Banks - Regional",
                             pais="Estados Unidos", region="EEUU", intentos_fallidos=0, fecha_fundamentales=HOY))
    db.add(FundamentalesSnapshot(simbolo_yahoo="BANCO", fecha=HOY, moneda="USD", market_cap_usd=1.5e11, ratios_precio_confiables=1,
                                 metricas=_metricas(0.7, 1.0, 1.5e11, 40), serie_semanal=_serie(1)))
    for t, sector in (("KO", "Consumo básico"), ("MSFT", "Tecnología"), ("BBB", "Financiero")):
        db.add(InstrumentoInversion(ticker=t, nombre=t, tipo_instrumento="CEDEAR" if t != "BBB" else "Accion",
                                    mercado="BYMA", moneda="USD", sector=sector, pais="Estados Unidos"))
    db.commit()
    for t, cant, precio, actual in (("KO", 10, 50.0, 50.0), ("MSFT", 10, 100.0, 100.0), ("BBB", 10, 50.0, 50.0)):
        db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera="Principal", ticker=t, tipo_movimiento="compra",
                                   cantidad=cant, precio=precio, moneda="USD", comision=precio * cant * 0.005))
        db.add(PrecioInstrumento(fecha=HOY - timedelta(days=1), ticker=t, precio=actual, moneda="USD"))
    _barras(db, "KO")
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


def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("ticker", "ticker_base", "nombre", "regla_aplicada", "clave", "tipo", "accion_elegida"):
                continue
            yield from _textos(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textos(v)


def _sin_palabras_prohibidas(b):
    malas = [t for t in _textos(b) if PROHIBIDAS.search(t)]
    assert malas == [], malas[:5]


def _conteos(sesion):
    db = sesion()
    try:
        return (db.scalar(select(func.count()).select_from(MovimientoInversion)),
                db.scalar(select(func.count()).select_from(PrecioInstrumento)))
    finally:
        db.close()


# ── Análisis ────────────────────────────────────────────────────────────────

def test_analisis_con_datos_completos(client):
    r = client.get(f"{URL}/decisiones/analisis/KO")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["estado"] == "ok" and b["ticker_base"] == "KO"
    ev = b["evaluacion"]
    assert {d["clave"] for d in ev["dimensiones"]} == {"fundamentales", "valoracion", "riesgo", "tecnico", "encaje"}
    assert all(d["puntaje"] is not None for d in ev["dimensiones"]), ev["dimensiones"]
    assert ev["orden"]["puntaje"] is not None
    assert b["tecnico"]["ultimo_cierre"] is not None and b["tecnico"]["atr"] is not None
    assert b["escenarios"]["estado"] == "ok" and b["escenarios"]["fuente_precio"] == "serie:local"
    assert {a["ticker"] for a in b["alternativas"]["items"]} == {"PEP", "MNST", "KDP", "CELH"}
    assert b["alternativas"]["metodo"] and set(b["alternativas"]["robustez"]) == {"fundamental", "tecnico", "combinado"}
    assert b["conclusion"]["tipo"] in {"alternativa_mas_atractiva", "interesante_pendiente", "valoracion_exigente",
                                       "riesgo_elevado", "datos_insuficientes", "ninguna_superior"}
    assert len(b["conclusion"]["respuestas"]) == 9 and b["conclusion"]["evidencia_en_contra"]
    assert b["versiones"]["evaluacion"] == 1 and b["versiones"]["diagnostico"] == 2
    assert {f["dato"] for f in b["fuentes"]} >= {"Fundamentales y múltiplos", "Tipo de cambio MEP"}
    assert b["riesgo"]["volatilidad"] is not None and b["riesgo"]["moneda_serie"] == "USD"
    for f in b["resumen"]:
        assert interpretacion.validar_cifras(f["texto"], b) == []
    _sin_palabras_prohibidas(b)


def test_analisis_con_datos_faltantes_no_inventa(client):
    b = client.get(f"{URL}/decisiones/analisis/ZZZZ").json()
    assert b["estado"] == "ok"
    assert b["secciones"]["diagnostico"]["estado"] == "sin_datos"
    assert b["evaluacion"]["orden"]["puntaje"] is None and b["evaluacion"]["orden"]["incompleto"]
    assert all(d["puntaje"] is None for d in b["evaluacion"]["dimensiones"] if d["clave"] != "encaje")
    assert b["conclusion"]["tipo"] == "datos_insuficientes"
    assert b["escenarios"]["estado"] == "sin_datos"


def test_comparar_con_metricas_no_aplicables_las_deja_afuera(client):
    b = client.get(f"{URL}/decisiones/analisis/KO", params={"con": "SPYX,BANCO,PEP,MNST"}).json()
    items = {a["ticker"] for a in b["alternativas"]["items"]}
    assert "SPYX" not in items and "BANCO" not in items and {"PEP", "MNST"} <= items
    rechazadas = {r["ticker"] for r in b["comparador"]["rechazadas"]}
    assert {"SPYX", "BANCO"} <= rechazadas


def test_fechas_incompatibles_se_advierten(client):
    b = client.get(f"{URL}/decisiones/analisis/KO").json()
    adv = b["alternativas"]["advertencias_fechas"]
    assert any(a.startswith("KDP") and "trimestres distintos" in a for a in adv)


def test_cotizacion_desactualizada_levanta_bandera(client, sesion):
    db = sesion()
    db.query(BarraOHLCV).filter(BarraOHLCV.fecha > HOY - timedelta(days=30)).delete()
    db.query(PrecioInstrumento).delete()
    db.add(PrecioInstrumento(fecha=HOY - timedelta(days=40), ticker="KO", precio=50.0, moneda="USD"))
    db.commit()
    db.close()
    b = client.get(f"{URL}/decisiones/analisis/KO").json()
    assert any(f["clave"] == "precio_viejo" for f in b["evaluacion"]["banderas"])


def test_una_fuente_que_falla_deja_su_seccion_no_disponible(client, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("fuente caída")

    monkeypatch.setattr(valor_razonable_analytics, "calcular", rompe)
    b = client.get(f"{URL}/decisiones/analisis/KO", params={"horizonte": "mediano"}).json()
    assert b["estado"] == "ok"
    assert b["secciones"]["valor_razonable"]["estado"] == "no_disponible"
    assert b["valor_razonable"] is None and b["evaluacion"]["orden"]["puntaje"] is not None


def test_moneda_ars_marca_el_riesgo_de_divisa_del_cedear(client):
    b = client.get(f"{URL}/decisiones/analisis/KO", params={"moneda": "ARS"}).json()
    riesgo = next(d for d in b["evaluacion"]["dimensiones"] if d["clave"] == "riesgo")
    assert any("Sigue al dólar" in f["texto"] for f in riesgo["factores"])


def test_cartera_individual_y_validaciones(client):
    assert client.get(f"{URL}/decisiones/analisis/KO", params={"cartera": "Principal"}).json()["cartera"] == "Principal"
    assert client.get(f"{URL}/decisiones/analisis/KO", params={"cartera": "NoExiste"}).status_code == 404
    assert client.get(f"{URL}/decisiones/analisis/KO", params={"horizonte": "eterno"}).status_code == 422
    assert client.get(f"{URL}/decisiones/analisis/K$O").status_code == 422
    assert client.get(f"{URL}/decisiones/analisis/KO", params={"con": "A,B,C,D,E,F,G"}).status_code == 422


# ── Preferencias, exploración, facetas ──────────────────────────────────────

def test_preferencias_defaults_guardado_y_validacion(client):
    b = client.get(f"{URL}/decisiones/preferencias").json()
    assert b["horizonte"] == "largo" and b["tolerancia"] is None and b["pesos_tabla"]
    r = client.put(f"{URL}/decisiones/preferencias", json={"horizonte": "corto", "enfoque": "tecnico", "tolerancia": "baja"})
    assert r.status_code == 200 and r.json()["pesos_efectivos"]["tecnico"] == 50
    assert client.get(f"{URL}/decisiones/preferencias").json()["horizonte"] == "corto"
    assert client.put(f"{URL}/decisiones/preferencias", json={"pesos": {"riesgo": 500}}).status_code == 422


def test_explorar_y_facetas(client):
    f = client.get(f"{URL}/decisiones/facetas").json()
    assert {x["valor"] for x in f["sectores"]} >= {"Consumo básico", "Financiero"}
    assert f["cobertura"]["con_fundamentales"] >= 6 and f["tematicas_no_cubiertas"]
    b = client.get(f"{URL}/decisiones/explorar", params={"sector": "Consumo básico"}).json()
    assert b["total"] >= 5 and all(i["sector"] == "Consumo básico" for i in b["items"])
    assert b["pesos"]["tecnico"] == 0 and b["pesos"]["encaje"] == 0
    d = client.get(f"{URL}/decisiones/explorar", params={"tematica": "dividendos"}).json()
    assert d["tematica"]["clave"] == "dividendos" and d["total"] >= 1
    assert client.get(f"{URL}/decisiones/explorar", params={"tematica": "ia"}).status_code == 422


# ── Simulador ───────────────────────────────────────────────────────────────

def _eje(b, nombre):
    return next(e for e in b["ejes"] if e["eje"] == nombre)


def test_simular_compra_no_altera_la_cartera_real(client, sesion):
    antes = _conteos(sesion)
    r = client.post(f"{URL}/consolidado/simular-decision", json={"operaciones": [{"ticker": "PEP", "monto_usd": 500}]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total"]["antes_usd"] == pytest.approx(2000.0) and b["total"]["despues_usd"] == pytest.approx(2500.0)
    assert b["total"]["despues_ars"] == pytest.approx(b["total"]["antes_ars"] + 500 * MEP)
    assert _conteos(sesion) == antes
    assert {e["eje"] for e in b["ejes"]} >= {"Emisor", "Sector", "Moneda"}
    for e in b["ejes"]:
        assert sum(f["despues_pct"] for f in e["items"]) == pytest.approx(100.0, abs=0.1), e["eje"]


def test_simular_venta_no_registra_movimientos_y_estima_resultado(client, sesion):
    antes = _conteos(sesion)
    b = client.post(f"{URL}/carteras/Principal/simular-decision",
                    json={"operaciones": [{"ticker": "KO", "monto_usd": -250}]}).json()
    assert _conteos(sesion) == antes
    v = b["ventas"][0]
    assert v["fraccion"] == pytest.approx(0.5) and v["cantidad_estimada"] == pytest.approx(5.0)
    assert v["resultado_estimado_usd"] is not None
    assert b["liquidez_usd"] == pytest.approx(250.0)
    assert any(f["etiqueta"] == "Liquidez (simulada)" for f in _eje(b, "Emisor")["items"])
    assert b["comision_estimada_usd"] == pytest.approx(250 * 0.005)
    assert any("Impuestos: no calculados" in s for s in b["supuestos"])
    _sin_palabras_prohibidas({k: b[k] for k in ("observaciones", "supuestos", "exacto", "notas")})


def test_simular_reduccion_mayor_a_la_tenencia_es_422(client):
    r = client.post(f"{URL}/consolidado/simular-decision", json={"operaciones": [{"ticker": "KO", "monto_usd": -5000}]})
    assert r.status_code == 422
    r = client.post(f"{URL}/consolidado/simular-decision", json={"operaciones": [{"ticker": "PEP", "monto_usd": -10}]})
    assert r.status_code == 422


def test_simulador_coincide_con_impacto_compra_para_una_suma(client):
    viejo = client.post(f"{URL}/consolidado/impacto-compra", json={"ticker": "PEP", "monto_usd": 500}).json()
    nuevo = client.post(f"{URL}/consolidado/simular-decision", json={"operaciones": [{"ticker": "PEP", "monto_usd": 500}]}).json()
    for nombre in ("Emisor", "Sector", "País"):
        a = {f["etiqueta"]: (round(f["antes_pct"], 6), round(f["despues_pct"], 6)) for f in _eje(viejo, nombre)["items"]}
        b = {f["etiqueta"]: (round(f["antes_pct"], 6), round(f["despues_pct"], 6)) for f in _eje(nuevo, nombre)["items"]}
        assert a == b, nombre


def test_reasignar_suma_y_resta_en_la_misma_simulacion(client):
    b = client.post(f"{URL}/consolidado/simular-decision", json={"operaciones": [
        {"ticker": "KO", "monto_usd": -250}, {"ticker": "PEP", "monto_usd": 250}]}).json()
    assert b["liquidez_usd"] == 0 and b["total"]["despues_usd"] == pytest.approx(b["total"]["antes_usd"])
    emisor = {f["etiqueta"]: f for f in _eje(b, "Emisor")["items"]}
    assert emisor["KO"]["despues_pct"] == pytest.approx(12.5) and emisor["PEP"]["despues_pct"] == pytest.approx(12.5)


# ── Posición existente ──────────────────────────────────────────────────────

def _opciones_texto(b):
    return {o["clave"]: (sorted(o["a_favor"]), sorted(o["en_contra"])) for o in b["opciones"]}


def _precio_de_entrada(sesion, precio):
    db = sesion()
    # la comisión acompaña al precio para que la tasa promedio (y el costo estimado) no cambie
    db.query(MovimientoInversion).filter(MovimientoInversion.ticker == "KO").update(
        {"precio": precio, "comision": precio * 10 * 0.005})
    db.commit()
    db.close()


def test_posicion_en_perdida_no_empuja_a_salir(client, sesion):
    _precio_de_entrada(sesion, 30.0)
    ganancia = client.get(f"{URL}/decisiones/posicion/KO").json()
    _precio_de_entrada(sesion, 120.0)
    perdida = client.get(f"{URL}/decisiones/posicion/KO").json()
    assert perdida["situacion"]["no_realizado_usd"] < 0 < ganancia["situacion"]["no_realizado_usd"]
    assert _opciones_texto(perdida) == _opciones_texto(ganancia)
    assert perdida["situacion"]["nota_resultado"]
    _sin_palabras_prohibidas({"o": perdida["opciones"], "s": perdida["situacion"]["nota_resultado"]})


def test_posicion_compara_mantener_con_reasignar_y_liquidez(client):
    b = client.get(f"{URL}/decisiones/posicion/KO", params={"cartera": "Principal"}).json()
    assert [o["clave"] for o in b["opciones"]] == ["mantener", "aumentar", "reducir", "salir"]
    assert b["reasignaciones"] and b["reasignaciones"][0]["simulacion"]["liquidez_usd"] == 0
    assert b["liquidez"]["simulacion"]["liquidez_usd"] == pytest.approx(250.0)
    assert b["situacion"]["peso_emisor_pct"] == pytest.approx(25.0)      # 500 de 2000
    assert client.get(f"{URL}/decisiones/posicion/PEP").status_code == 404


# ── Diario de decisiones ────────────────────────────────────────────────────

def _crear(client, **kw):
    body = {"modo": "oportunidad", "ticker": "KO", "accion_elegida": "esperar_tecnica", "nota": "mi tesis",
            "revisar_en_dias": 30, **kw}
    r = client.post(f"{URL}/decisiones", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_guardar_y_recuperar_una_decision(client):
    d = _crear(client)
    assert d["ticker_base"] == "KO" and d["accion_elegida"] == "esperar_tecnica" and d["ejecutada"] is False
    assert d["snapshot"]["evaluacion"]["orden"] and d["conclusion"]["tipo"]
    assert d["versiones"]["evaluacion"] == 1 and d["calidad"]["cobertura"] > 0
    assert d["condiciones"]["invalidacion"] and d["condiciones"]["entrada"]["escenario"] == "esperar_tecnica"
    assert {a["ticker"] for a in d["alternativas"]} >= {"KO", "PEP"}
    assert d["revisar_el"] == (date.today() + timedelta(days=30)).isoformat()
    assert client.get(f"{URL}/decisiones/{d['id']}").json()["snapshot"] == d["snapshot"]
    assert [x["id"] for x in client.get(f"{URL}/decisiones").json()] == [d["id"]]
    assert client.get(f"{URL}/decisiones/9999").status_code == 404


def test_validaciones_al_guardar(client):
    r = client.post(f"{URL}/decisiones", json={"modo": "oportunidad", "ticker": "KO", "accion_elegida": "salir"})
    assert r.status_code == 422
    r = client.post(f"{URL}/decisiones", json={"modo": "oportunidad", "ticker": "KO", "accion_elegida": "elegir_alternativa",
                                               "alternativa_elegida": "ZZZ"})
    assert r.status_code == 422
    r = client.post(f"{URL}/decisiones", json={"modo": "posicion", "ticker": "PEP", "accion_elegida": "mantener"})
    assert r.status_code == 404


def test_el_cliente_no_puede_inyectar_numeros(client):
    r = client.post(f"{URL}/decisiones", json={"modo": "oportunidad", "ticker": "KO", "accion_elegida": "ninguna",
                                               "orden": 99, "conclusion": {"tipo": "inventada"}})
    assert r.status_code == 201
    assert r.json()["conclusion"]["tipo"] != "inventada" and r.json()["orden"] != 99


def test_revision_no_sobrescribe_la_decision(client, sesion):
    d = _crear(client)
    r1 = client.post(f"{URL}/decisiones/{d['id']}/revisiones", json={"evaluacion_proceso": "bien", "nota": "ok"})
    assert r1.status_code == 201, r1.text
    c = r1.json()["comparacion"]
    assert c["precio"]["referencia"] is not None and c["dimensiones"] and c["supuestos"] and c["condiciones"]
    assert c["resultado"] is None    # no se marcó ejecutada: no se asume
    client.post(f"{URL}/decisiones/{d['id']}/revisiones", json={})
    det = client.get(f"{URL}/decisiones/{d['id']}").json()
    assert len(det["revisiones"]) == 2 and det["n_revisiones"] == 2
    assert det["snapshot"] == d["snapshot"] and det["conclusion"] == d["conclusion"]
    db = sesion()
    assert db.query(DecisionSnapshot).filter_by(decision_id=d["id"], tipo="inicial").count() == 1
    assert db.query(DecisionSnapshot).filter_by(decision_id=d["id"], tipo="revision").count() == 2
    db.close()
    # el usuario califica una revisión sin tocar la comparación
    rv = client.patch(f"{URL}/decisiones/revisiones/{r1.json()['id']}", json={"evaluacion_proceso": "regular"}).json()
    assert rv["evaluacion_proceso"] == "regular" and rv["comparacion"] == r1.json()["comparacion"]


def test_patch_solo_edita_campos_del_usuario(client):
    d = _crear(client)
    r = client.patch(f"{URL}/decisiones/{d['id']}", json={"ejecutada": True, "nota": "la hice", "estado": "cerrada"})
    assert r.status_code == 200
    b = r.json()
    assert b["ejecutada"] and b["nota"] == "la hice" and b["estado"] == "cerrada" and b["conclusion"] == d["conclusion"]
    assert client.patch(f"{URL}/decisiones/{d['id']}", json={"revisar_el": "2000-01-01"}).status_code == 422
    assert client.delete(f"{URL}/decisiones/{d['id']}").status_code == 204
    assert client.get(f"{URL}/decisiones/{d['id']}").status_code == 404


def test_decision_de_posicion_guarda_la_foto_de_la_posicion(client):
    d = _crear(client, modo="posicion", accion_elegida="mantener", cartera="Principal")
    assert d["modo"] == "posicion" and d["snapshot"]["opciones"] and d["snapshot"]["analisis"]["evaluacion"]
    # la tesis de esa decisión aparece al volver a mirar la posición
    b = client.get(f"{URL}/decisiones/posicion/KO", params={"cartera": "Principal"}).json()
    assert b["tesis"]["existe"] is True


def test_pendientes_aprendizaje_y_aviso(client, sesion, monkeypatch):
    d = _crear(client)
    assert client.get(f"{URL}/decisiones/pendientes").json() == []
    db = sesion()
    db.query(Decision).filter(Decision.id == d["id"]).update({"revisar_el": HOY - timedelta(days=1)})
    db.commit()
    db.close()
    pend = client.get(f"{URL}/decisiones/pendientes").json()
    assert [p["id"] for p in pend] == [d["id"]] and pend[0]["motivos"]

    enviados = []
    from app.services.notificaciones import telegram
    monkeypatch.setattr(telegram, "enviar", lambda texto, parse_mode=None: (enviados.append(texto) or (True, None)))
    db = sesion()
    res = diario_decisiones.avisar_revisiones(db)
    assert res["entregado"] and len(enviados) == 1 and "DECISIÓN PARA REVISAR" in enviados[0]
    assert diario_decisiones.avisar_revisiones(db)["eventos"] == 0      # una vez por evento
    _sin_palabras_prohibidas(enviados)
    db.close()

    ap = client.get(f"{URL}/decisiones/aprendizaje").json()
    assert ap["decisiones"] == 1
    assert all(p["tono"] == "insuficiente" for p in ap["patrones"])     # 1 decisión: nada concluye


def test_aviso_apagado_se_marca_sin_mandar(client, sesion, monkeypatch):
    d = _crear(client)
    assert client.put(f"{URL}/alertas/config", json={"avisar_revision_decision": False}).json()["avisar_revision_decision"] is False
    db = sesion()
    db.query(Decision).filter(Decision.id == d["id"]).update({"revisar_el": HOY - timedelta(days=1)})
    db.commit()
    from app.services.notificaciones import telegram
    monkeypatch.setattr(telegram, "enviar", lambda *a, **k: pytest.fail("no debería mandar"))
    assert diario_decisiones.avisar_revisiones(db)["motivo"] == "aviso silenciado"
    assert db.query(Decision).get(d["id"]).aviso_revision_en is not None
    assert db.query(AjustesAvisos).first().avisar_revision_decision == 0
    db.close()
