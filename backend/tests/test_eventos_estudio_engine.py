"""Calendario de eventos: rueda de referencia, retornos alrededor del evento, ventanas incompletas, huecos,
benchmark y eventos superpuestos (motor puro) + endpoints de impacto y análisis con datos controlados."""
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, BarraOHLCV, EventoInstrumento, EventoMercado, WatchlistItem, get_db
from app.main import app
from app.services.eventos import estudio_engine as ee


def _ruedas(desde: date, n: int) -> list[date]:
    out, d = [], desde
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


FECHAS = _ruedas(date(2026, 3, 2), 60)          # lun 2-mar-2026 en adelante
SERIE = [(f, 100.0 + i, 1000.0) for i, f in enumerate(FECHAS)]   # sube 1 por rueda


def _ev(fecha, hora=None, zona=None, pub=None, programado=False, **kw):
    return {"id": kw.get("id", 1), "fecha_evento": fecha, "hora_evento": hora, "zona_horaria": zona,
            "fecha_publicacion": pub, "programado": programado, **kw}


def test_rueda_referencia_antes_y_despues_del_cierre():
    miercoles = date(2026, 3, 18)
    i = FECHAS.index(miercoles)
    antes = ee.rueda_referencia(FECHAS, _ev(miercoles, time(14, 0), "America/New_York", programado=True), ee.NYSE)
    assert antes["indice"] == i and "Antes del cierre" in antes["regla"]
    despues = ee.rueda_referencia(FECHAS, _ev(miercoles, time(16, 30), "America/New_York", programado=True), ee.NYSE)
    assert despues["indice"] == i + 1 and "Después del cierre" in despues["regla"]


def test_noticia_publicada_despues_del_cierre_cuenta_desde_la_rueda_siguiente():
    # 21:30 UTC = 17:30 en Nueva York (horario de verano): después del cierre.
    jueves = date(2026, 3, 19)
    r = ee.rueda_referencia(FECHAS, _ev(jueves, pub=datetime(2026, 3, 19, 21, 30)), ee.NYSE)
    assert r["fecha"] == date(2026, 3, 20) and r["conocimiento"]["fuente"] == "publicacion"
    # La misma noticia vista desde BYMA (cierre 17 h de Buenos Aires = 20 UTC): también después.
    assert ee.rueda_referencia(FECHAS, _ev(jueves, pub=datetime(2026, 3, 19, 21, 30)), ee.BYMA)["fecha"] == date(2026, 3, 20)
    # Publicada a las 13 UTC: antes del cierre de ambos.
    assert ee.rueda_referencia(FECHAS, _ev(jueves, pub=datetime(2026, 3, 19, 13, 0)), ee.BYMA)["fecha"] == jueves


def test_fin_de_semana_y_hora_desconocida():
    domingo = date(2026, 3, 15)
    r = ee.rueda_referencia(FECHAS, _ev(domingo), ee.NYSE)
    assert r["fecha"] == date(2026, 3, 16) and "no hubo rueda" in r["regla"]
    r = ee.rueda_referencia(FECHAS, _ev(date(2026, 3, 16)), ee.NYSE)
    assert r["fecha"] == date(2026, 3, 16) and "hora_desconocida" in r["avisos"]


def test_retornos_de_las_ventanas():
    t0 = 30
    w = ee.ventana(SERIE, t0, 5)
    c = lambda k: 100.0 + k
    assert w["previo_pct"] == round((c(29) / c(24) - 1) * 100, 4)
    assert w["rueda_pct"] == round((c(30) / c(29) - 1) * 100, 4)
    assert w["posterior_pct"] == round((c(35) / c(30) - 1) * 100, 4)
    assert w["acumulado_pct"] == round((c(35) / c(24) - 1) * 100, 4)
    assert w["fechas"] == {"inicio": FECHAS[24], "previa": FECHAS[29], "referencia": FECHAS[30], "fin": FECHAS[35]}
    assert w["observaciones"] == 12 and w["completa"] and w["volumen_relativo"] == 1.0


def test_ventana_incompleta_no_se_rellena():
    w = ee.ventana(SERIE, 58, 5)
    assert w["posterior_pct"] is None and w["acumulado_pct"] is None
    assert "ventana_incompleta_despues" in w["motivos"] and not w["completa"]
    assert w["rueda_pct"] is not None
    w = ee.ventana(SERIE, 59, 1)
    assert "sin_datos_posteriores" in w["motivos"]
    w = ee.ventana(SERIE, 2, 5)
    assert w["previo_pct"] is None and "ventana_incompleta_antes" in w["motivos"]


def test_huecos_en_la_serie_se_avisan():
    con_hueco = SERIE[:30] + [(f + timedelta(days=20), c, v) for f, c, v in SERIE[30:]]
    assert "huecos" in ee.ventana(con_hueco, 30, 5)["motivos"]


def test_benchmark_en_las_mismas_fechas_y_ausente():
    bench = [(f, 200.0) for f in FECHAS]          # índice plano
    w = ee.ventana(SERIE, 30, 5, bench)
    assert w["bench_posterior_pct"] == 0.0 and w["dif_posterior_pct"] == w["posterior_pct"]
    # Benchmark que termina antes: sin dato, no inventado.
    w = ee.ventana(SERIE, 30, 5, bench[:20])
    assert w["bench_posterior_pct"] is None and w["dif_posterior_pct"] is None


def test_analizar_eventos_futuros_y_superpuestos():
    futuro = ee.analizar(SERIE, _ev(FECHAS[-1] + timedelta(days=30)), ee.NYSE)
    assert futuro["ventanas"] == [] and "sin_datos_posteriores" in futuro["avisos"]
    otros = [_ev(FECHAS[31], id=2, titulo="Otro", categoria="dato_macro", importancia=2),
             _ev(FECHAS[30], id=3, titulo="Mismo día", categoria="banco_central", importancia=3)]
    r = ee.analizar(SERIE, _ev(FECHAS[30]), ee.NYSE, otros=otros)
    assert [s["evento_id"] for s in r["superpuestos"]] == [3, 2]
    assert r["superpuestos"][1]["ventanas"] == [1, 5, 20]
    assert "otro_evento_misma_rueda" in r["avisos"]
    assert [w["n"] for w in r["ventanas"]] == [1, 5, 20]
    assert "no demuestra" in r["leyenda"]


def test_patron_pide_muestra_minima():
    base = ee.retornos_base(SERIE, 5)
    pocos = ee.patron([{"posterior_pct": 1.0}] * 3, base)
    assert not pocos["suficiente"] and pocos["mediana_posterior_pct"] is None
    muchos = ee.patron([{"posterior_pct": v} for v in (1, 2, -1, 3, 4, 5, -2, 6)], base)
    assert muchos["suficiente"] and muchos["mediana_posterior_pct"] == 2.5 and muchos["positivos_pct"] == 75.0


# ── Endpoints ───────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    s = Sesion()
    s.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Acción", mercado="BCBA", moneda="ARS"))
    for i, f in enumerate(FECHAS[:40]):
        s.add(BarraOHLCV(ticker="GGAL", fecha=f, apertura=100 + i, maximo=101 + i, minimo=99 + i, cierre=100 + i,
                         volumen=1000, moneda="ARS", fuente="test"))
    ahora = datetime.utcnow()
    pasado = EventoMercado(titulo="Balance de Galicia", categoria="resultados", fecha_evento=FECHAS[20], origen="manual",
                           importancia=2, fecha_creacion=ahora, fecha_actualizacion=ahora)
    futuro = EventoMercado(titulo="Elecciones", categoria="elecciones", fecha_evento=FECHAS[39] + timedelta(days=40),
                           origen="manual", importancia=3, estado="previsto", precision_fecha="aproximada",
                           fecha_creacion=ahora, fecha_actualizacion=ahora)
    descartado = EventoMercado(titulo="No aplica", categoria="corporativo", fecha_evento=FECHAS[10], origen="manual",
                               importancia=2, fecha_creacion=ahora, fecha_actualizacion=ahora)
    s.add_all([pasado, futuro, descartado])
    s.flush()
    s.add_all([
        EventoInstrumento(evento_id=pasado.id, ticker="GGAL", tipo_relacion="directa", relevancia=1, fecha_creacion=ahora),
        EventoInstrumento(evento_id=futuro.id, ticker="GGAL", tipo_relacion="pais", relevancia=0.35, fecha_creacion=ahora),
        EventoInstrumento(evento_id=descartado.id, ticker="GGAL", tipo_relacion="directa", relevancia=1,
                          estado_revision="descartada", fecha_creacion=ahora),
    ])
    s.commit()
    ids = {"pasado": pasado.id, "futuro": futuro.id}
    s.close()

    def override():
        ses = Sesion()
        try:
            yield ses
        finally:
            ses.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app), ids
    app.dependency_overrides.clear()


def test_impacto_serie_termina_en_la_ultima_barra_y_futuros_sin_precio(client):
    c, ids = client
    r = c.get("/api/inversiones/eventos/impacto/GGAL", params={"benchmark": "ninguno", "hasta": "2026-12-31"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ultima_fecha"] == FECHAS[39].isoformat() and d["serie"][-1]["fecha"] == FECHAS[39].isoformat()
    assert len(d["serie"]) == 40 and d["mercado"] == "BYMA"
    marcas = {m["evento_id"]: m for m in d["marcas"]}
    assert set(marcas) == {ids["pasado"], ids["futuro"]}           # el descartado no aparece
    assert marcas[ids["futuro"]]["futuro"] is True and marcas[ids["futuro"]]["fecha_referencia"] is None
    assert marcas[ids["pasado"]]["futuro"] is False and marcas[ids["pasado"]]["fecha_referencia"] == FECHAS[20].isoformat()
    assert all("cierre" not in m for m in d["marcas"])
    # Filtro por categoría.
    d = c.get("/api/inversiones/eventos/impacto/GGAL", params={"benchmark": "ninguno", "categoria": "elecciones",
                                                               "hasta": "2026-12-31"}).json()
    assert [m["evento_id"] for m in d["marcas"]] == [ids["futuro"]]


def test_analisis_del_evento_y_ticker_fuera_del_universo(client):
    c, ids = client
    r = c.get(f"/api/inversiones/eventos/{ids['pasado']}/analisis/GGAL", params={"benchmark": "ninguno"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["referencia"]["fecha"] == FECHAS[20].isoformat()
    w5 = next(w for w in d["ventanas"] if w["n"] == 5)
    assert w5["posterior_pct"] == round((125 / 120 - 1) * 100, 4) and w5["completa"]
    assert d["benchmark"] is None
    lista = c.get(f"/api/inversiones/eventos/{ids['pasado']}/analisis", params={"benchmark": "ninguno"}).json()
    assert [a["ticker"] for a in lista] == ["GGAL"]
    assert c.get("/api/inversiones/eventos/impacto/NOEXISTE").status_code == 404
    # Futuro: no hay datos posteriores, no se inventan.
    f = c.get(f"/api/inversiones/eventos/{ids['futuro']}/analisis/GGAL", params={"benchmark": "ninguno"}).json()
    assert f["ventanas"] == [] and "sin_datos_posteriores" in f["avisos"]


def test_patron_por_categoria(client):
    c, _ = client
    d = c.get("/api/inversiones/eventos/patron/GGAL", params={"categoria": "resultados", "n": 5}).json()
    assert d["casos_validos"] == 1 and d["suficiente"] is False and d["mediana_posterior_pct"] is None
    assert c.get("/api/inversiones/eventos/patron/GGAL", params={"categoria": "astrologia"}).status_code == 422
