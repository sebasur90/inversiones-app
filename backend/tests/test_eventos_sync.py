"""Calendario de eventos: sincronización con proveedores falsos y con los reales parseando respuestas
controladas. Ninguna llamada a una API real."""
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, EstadoFuenteEventos, EventoInstrumento, EventoMercado, InstrumentoInversion, NoticiaMercado, get_db,
)
from app.main import app
from app.services.eventos import catalogo, eventos_sync, importacion
from app.services.eventos.proveedores import base as pb
from app.services.eventos.proveedores import gdelt, marketaux, yahoo_resultados
from app.services.market_data import yahoo

HOY = date(2026, 10, 27)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    ahora = datetime.utcnow()
    for t, tipo, nombre in (("AAPL", "CEDEAR", "Apple"), ("GGAL", "Acción", "Galicia")):
        s.add(InstrumentoInversion(ticker=t, nombre=nombre, tipo_instrumento=tipo, mercado="BCBA", moneda="ARS"))
    s.commit()
    yield s
    s.close()


class Falso(pb.ProveedorEventos):
    """Proveedor de prueba: devuelve lo que se le da y cuenta cuántas veces lo llamaron."""

    def __init__(self, nombre="falso", resultado=None, conf=(True, ""), limite=None, solo_revision=False):
        self.nombre = nombre
        self.etiqueta = nombre
        self._res = resultado or pb.ResultadoProveedor(estado=pb.ESTADO_OK)
        self._conf = conf
        self._limite = limite
        self.solo_revision = solo_revision
        self.llamadas = 0

    def configurado(self):
        return self._conf

    def limite_diario(self):
        return self._limite

    def max_por_corrida(self):
        return 3

    def obtener(self, ctx):
        self.llamadas += 1
        self.ctx = ctx
        return self._res


def _noticia(i, titulo, simbolo="AAPL", score=30.0, en_titulo=True, horas=0, url=None):
    return pb.NoticiaCruda(
        proveedor="falso", id_externo=f"n{i}", url=url or f"https://medio{i}.com/nota-{i}", titulo=titulo,
        fecha_publicacion=datetime(2026, 10, 20, 15) + timedelta(hours=horas), medio=f"medio{i}",
        entidades=[{"simbolo": simbolo, "nombre": "Apple Inc.", "match_score": score, "en_titulo": en_titulo, "pais": "us"}],
    )


def test_sin_token_queda_no_configurado_y_no_llama(db, monkeypatch):
    monkeypatch.delenv("MARKETAUX_API_TOKEN", raising=False)
    p = marketaux.Marketaux()
    r = eventos_sync.correr(db, [p], hoy=HOY)
    assert r["proveedores"]["marketaux"]["estado"] == "no_configurado"
    fila = db.get(EstadoFuenteEventos, "marketaux")
    assert fila.estado == "no_configurado" and "MARKETAUX_API_TOKEN" in fila.mensaje


def test_noticias_se_incorporan_y_una_segunda_corrida_no_duplica(db):
    res = pb.ResultadoProveedor(estado=pb.ESTADO_OK, noticias=[
        _noticia(1, "Apple quarterly earnings beat estimates on iPhone demand"),
        _noticia(2, "Apple earnings beat estimates on strong iPhone demand", horas=2),   # mismo hecho, otro medio
        _noticia(3, "Un día tranquilo", score=1, en_titulo=False),                      # dudosa: a revisión
    ], solicitudes=1)
    p = Falso(resultado=res)
    eventos_sync.correr(db, [p], hoy=HOY)
    eventos = db.query(EventoMercado).all()
    assert len(eventos) == 1
    e = eventos[0]
    assert e.categoria == "resultados" and e.origen == "proveedor" and e.verificacion == "multiples_fuentes"
    assert e.precision_fecha == "aproximada" and e.fecha_publicacion == datetime(2026, 10, 20, 15)
    assert db.query(NoticiaMercado).filter_by(evento_id=e.id).count() == 2
    assert db.query(NoticiaMercado).filter_by(estado="por_revisar").count() == 1
    v = db.query(EventoInstrumento).filter_by(evento_id=e.id, ticker="AAPL").one()
    assert v.tipo_relacion == "directa" and v.metodo == "automatico" and v.estado_revision == "propuesta"

    eventos_sync.correr(db, [p], hoy=HOY)
    assert db.query(EventoMercado).count() == 1
    assert db.query(NoticiaMercado).count() == 3


def test_solo_revision_nunca_crea_eventos(db):
    res = pb.ResultadoProveedor(estado=pb.ESTADO_OK, noticias=[_noticia(1, "Fed raises interest rates, Powell says")])
    eventos_sync.correr(db, [Falso(resultado=res, solo_revision=True)], hoy=HOY)
    assert db.query(EventoMercado).count() == 0
    assert db.query(NoticiaMercado).filter_by(estado="por_revisar").count() == 1


def test_eventos_programados_respetan_ediciones_y_lapidas(db):
    crudo = lambda fecha, estado="previsto": pb.EventoCrudo(
        proveedor="yahoo_resultados", id_externo="AAPL:x", titulo="Resultados trimestrales de Apple", categoria="resultados",
        fecha_evento=fecha, estado=estado, programado=True,
        tickers=[{"ticker": "AAPL", "tipo_relacion": "directa", "relevancia": 1.0, "justificacion": "Balance"}],
    )
    p = Falso(nombre="yahoo_resultados", resultado=pb.ResultadoProveedor(estado=pb.ESTADO_OK, eventos=[crudo(date(2026, 11, 2))]))
    eventos_sync.correr(db, [p], hoy=HOY)
    e = db.query(EventoMercado).one()
    assert e.importancia == 1   # resultados de una empresa sin tenencia (no hay movimientos)
    v = db.query(EventoInstrumento).filter_by(evento_id=e.id).one()
    assert v.estado_revision == "confirmada"

    # El proveedor mueve la fecha: se actualiza y queda reprogramado.
    p._res = pb.ResultadoProveedor(estado=pb.ESTADO_OK, eventos=[crudo(date(2026, 11, 5))])
    eventos_sync.correr(db, [p], hoy=HOY)
    db.refresh(e)
    assert e.fecha_evento == date(2026, 11, 5) and e.estado == "reprogramado"

    # El usuario corrige el título: el proveedor ya no lo pisa.
    e.titulo, e.campos_editados = "Balance Apple (mi nota)", ["titulo"]
    db.commit()
    eventos_sync.correr(db, [p], hoy=HOY)
    db.refresh(e)
    assert e.titulo == "Balance Apple (mi nota)"

    # Descartado: no se recrea ni se actualiza.
    e.descartado = 1
    db.commit()
    p._res = pb.ResultadoProveedor(estado=pb.ESTADO_OK, eventos=[crudo(date(2026, 11, 9))])
    eventos_sync.correr(db, [p], hoy=HOY)
    assert db.query(EventoMercado).count() == 1
    db.refresh(e)
    assert e.fecha_evento == date(2026, 11, 5)


def test_manual_intacto_y_duplicado_no_se_crea(db):
    ahora = datetime.utcnow()
    db.add(EventoMercado(titulo="Resultados trimestrales de Apple", categoria="resultados", fecha_evento=date(2026, 11, 2),
                         origen="manual", notas="mía", fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()
    crudo = pb.EventoCrudo(proveedor="yahoo_resultados", id_externo="AAPL:2026-11-02", titulo="Resultados trimestrales de Apple",
                           categoria="resultados", fecha_evento=date(2026, 11, 2))
    eventos_sync.correr(db, [Falso(resultado=pb.ResultadoProveedor(estado=pb.ESTADO_OK, eventos=[crudo]))], hoy=HOY)
    assert db.query(EventoMercado).count() == 1
    assert db.query(EventoMercado).one().notas == "mía"


def test_cupo_diario_respetado(db):
    p = Falso(limite=4)
    eventos_sync.correr(db, [p], hoy=HOY)
    assert p.ctx.solicitudes_disponibles == 3
    db.get(EstadoFuenteEventos, "falso").solicitudes_hoy = 4
    db.commit()
    p.llamadas = 0
    r = eventos_sync.correr(db, [p], hoy=HOY)
    assert p.llamadas == 0 and r["proveedores"]["falso"]["estado"] == "cupo_agotado"
    # Al día siguiente el cupo vuelve.
    eventos_sync.correr(db, [p], hoy=HOY + timedelta(days=1))
    assert p.llamadas == 1


def test_proveedor_que_explota_no_rompe_y_datos_locales_quedan(db):
    class Roto(Falso):
        def obtener(self, ctx):
            raise RuntimeError("boom")

    ahora = datetime.utcnow()
    db.add(EventoMercado(titulo="Mío", categoria="otro", fecha_evento=date(2026, 1, 1), origen="manual",
                         fecha_creacion=ahora, fecha_actualizacion=ahora))
    db.commit()
    r = eventos_sync.correr(db, [Roto(nombre="roto")], hoy=HOY)
    assert r["proveedores"]["roto"]["estado"] == "error"
    assert db.query(EventoMercado).count() == 1


# ── Proveedores reales con respuestas controladas ───────────────────────────────────────────

ARTICULO = {
    "uuid": "u-1", "title": "<b>Apple</b> beats quarterly earnings estimates", "description": "Strong <i>iPhone</i> sales.",
    "url": "https://www.reuters.com/apple?utm_source=x", "language": "en", "published_at": "2026-10-20T21:30:00.000000Z",
    "source": "reuters.com",
    "entities": [{"symbol": "AAPL", "name": "Apple Inc.", "type": "equity", "industry": "Technology", "country": "us",
                  "match_score": 34.29, "sentiment_score": 0.5, "highlights": [{"highlighted_in": "title", "highlight": "x"}]}],
}


def test_marketaux_parsea_y_limpia_html(monkeypatch):
    n = marketaux.parsear_articulo(ARTICULO)
    assert n.titulo == "Apple beats quarterly earnings estimates" and n.fragmento == "Strong iPhone sales."
    assert n.fecha_publicacion == datetime(2026, 10, 20, 21, 30)
    assert n.entidades[0]["en_titulo"] and n.entidades[0]["match_score"] == 34.29
    assert marketaux.parsear_articulo({**ARTICULO, "url": "javascript:alert(1)"}) is None
    assert marketaux.parsear_articulo({**ARTICULO, "published_at": "ayer"}) is None


@pytest.mark.parametrize("status,estado", [(402, "cupo_agotado"), (429, "rate_limited"), (401, "error"), (None, "error"), (500, "error")])
def test_marketaux_errores_de_la_api(monkeypatch, status, estado):
    monkeypatch.setenv("MARKETAUX_API_TOKEN", "secreto")
    llamadas = []

    def falso(method, url, **kw):
        llamadas.append(kw["params"])
        return status, None

    monkeypatch.setattr(marketaux, "request_json", falso)
    ctx = pb.ContextoProveedor(hoy=HOY, simbolos=[pb.SimboloUniverso("AAPL", ["AAPL"])], solicitudes_disponibles=3)
    r = marketaux.Marketaux().obtener(ctx)
    assert r.estado == estado and r.solicitudes == 1 and len(llamadas) == 1
    assert "secreto" not in r.mensaje


def test_marketaux_reparte_el_cupo_entre_tandas_y_macro(monkeypatch):
    monkeypatch.setenv("MARKETAUX_API_TOKEN", "secreto")
    params = []
    monkeypatch.setattr(marketaux, "request_json", lambda m, u, **kw: (params.append(kw["params"]) or (200, {"data": [ARTICULO]})))
    simbolos = [pb.SimboloUniverso(f"S{i:02d}", [f"S{i:02d}"]) for i in range(12)] + [pb.SimboloUniverso("GGAL.BA", ["GGAL"], es_accion_local=True)]
    ctx = pb.ContextoProveedor(hoy=HOY, simbolos=simbolos, solicitudes_disponibles=3, rotacion=1)
    r = marketaux.Marketaux().obtener(ctx)
    assert r.solicitudes == 3 and r.estado == "ok"
    assert [("symbols" in p, "search" in p) for p in params] == [(True, False), (True, False), (False, True)]
    assert params[0]["symbols"] == "S04,S05,S06,S07,S08"     # sigue la ronda donde quedó (GGAL.BA va como GGAL, primera)
    assert all(p["api_token"] == "secreto" for p in params)
    assert r.rotacion == 0


def test_marketaux_corrida_completa_por_el_orquestador(db, monkeypatch):
    monkeypatch.setenv("MARKETAUX_API_TOKEN", "secreto")
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(marketaux, "request_json", lambda m, u, **kw: (200, {"data": [ARTICULO]}))
    eventos_sync.correr(db, [marketaux.Marketaux()], hoy=HOY)
    fila = db.get(EstadoFuenteEventos, "marketaux")
    assert fila.estado == "ok" and fila.solicitudes_hoy >= 1
    assert db.query(NoticiaMercado).count() == 1
    assert db.query(EventoMercado).filter_by(categoria="resultados").count() == 1


def test_yahoo_resultados_estimada_y_futura(monkeypatch):
    filas = [
        {"fecha": date(2026, 7, 30), "hora": time(16, 30), "eps_estimado": 1.4, "eps_reportado": 1.5, "sorpresa_pct": 7.1, "estimada": False},
        {"fecha": date(2027, 1, 28), "hora": None, "eps_estimado": 2.1, "eps_reportado": None, "sorpresa_pct": None, "estimada": True},
        {"fecha": date(2010, 1, 1), "hora": None, "eps_estimado": None, "eps_reportado": None, "sorpresa_pct": None, "estimada": False},
    ]
    evs = yahoo_resultados.eventos_de("AAPL", "Apple", ["AAPL"], filas, HOY)
    assert len(evs) == 2
    pasado, futuro = evs
    assert pasado.estado == "concluido" and pasado.hora_evento == time(16, 30) and pasado.zona_horaria == "America/New_York"
    assert "+7.1 %" in pasado.descripcion
    assert futuro.estado == "previsto" and futuro.precision_fecha == "aproximada" and futuro.hora_evento is None


def test_yahoo_resultados_corta_ante_rate_limit(monkeypatch):
    monkeypatch.setattr(yahoo_resultados, "PAUSA_SEG", 0)
    monkeypatch.setattr(yahoo, "fetch_fechas_resultados", lambda s: yahoo.ResultadoYahoo(yahoo.ESTADO_RATE_LIMITED))
    ctx = pb.ContextoProveedor(hoy=HOY, simbolos=[pb.SimboloUniverso("AAPL", ["AAPL"]), pb.SimboloUniverso("MSFT", ["MSFT"])],
                               solicitudes_disponibles=5)
    r = yahoo_resultados.YahooResultados().obtener(ctx)
    assert r.estado == "rate_limited" and r.solicitudes == 1


def test_gdelt_429_y_parseo(monkeypatch):
    monkeypatch.setattr(gdelt, "PAUSA_SEG", 0)
    monkeypatch.setattr(gdelt, "request_json", lambda m, u, **kw: (429, None))
    r = gdelt.Gdelt().obtener(pb.ContextoProveedor(hoy=HOY, simbolos=[], solicitudes_disponibles=2))
    assert r.estado == "rate_limited" and r.solicitudes == 1
    art = {"url": "https://example.com/a", "title": "Tariffs <em>rise</em>", "seendate": "20261020T101500Z",
           "domain": "example.com", "language": "English", "sourcecountry": "United States"}
    monkeypatch.setattr(gdelt, "request_json", lambda m, u, **kw: (200, {"articles": [art, {"url": "ftp://x"}]}))
    r = gdelt.Gdelt().obtener(pb.ContextoProveedor(hoy=HOY, simbolos=[], solicitudes_disponibles=1))
    assert r.estado == "ok" and len(r.noticias) == 1
    assert r.noticias[0].titulo == "Tariffs rise" and r.noticias[0].fecha_publicacion == datetime(2026, 10, 20, 10, 15)
    assert not gdelt.Gdelt().habilitado()[0]   # apagado por default


# ── Importación y catálogo ─────────────────────────────────────────────────────────────────

def test_importacion_valida_e_idempotente(entorno_api):
    client, Sesion = entorno_api
    datos = {"eventos": [
        {"id": "ar-2027", "titulo": "Elecciones generales", "categoria": "elecciones", "fecha": "2027-10-24",
         "url_fuente": "https://www.electoral.gob.ar/", "pais": "Argentina", "importancia": 3, "verificacion": "fuente_oficial"},
        {"id": "malo", "titulo": "Sin fuente", "categoria": "elecciones", "fecha": "2027-01-01"},
        {"id": "fed-x", "titulo": "Reunión FOMC", "categoria": "banco_central", "fecha": "2027-01-27", "hora": "14:00",
         "zona_horaria": "America/New_York", "url_fuente": "https://www.federalreserve.gov/", "precision": "exacta"},
    ]}
    r = client.post("/api/inversiones/eventos/importar", json=datos).json()
    assert r["recibidos"] == 3 and r["nuevos"] == 2 and len(r["errores"]) == 1 and "url_fuente" in r["errores"][0]
    r2 = client.post("/api/inversiones/eventos/importar", json=datos).json()
    assert r2["nuevos"] == 0 and r2["sin_cambios"] == 2
    lista = client.get("/api/inversiones/eventos", params={"temporalidad": "futuros"}).json()
    elecciones = next(e for e in lista["eventos"] if e["categoria"] == "elecciones")
    assert elecciones["estado"] == "previsto" and elecciones["confianza_datos"] == "alta"
    assert any(v["ticker"] == "^MERV" for v in elecciones["instrumentos"])   # propuesto por país


def test_fuentes_endpoint_sin_secretos(entorno_api, monkeypatch):
    client, _ = entorno_api
    monkeypatch.setenv("MARKETAUX_API_TOKEN", "super-secreto")
    r = client.get("/api/inversiones/eventos/fuentes")
    assert r.status_code == 200
    assert "super-secreto" not in r.text
    nombres = {f["proveedor"]: f for f in r.json()["fuentes"]}
    assert nombres["marketaux"]["configurado"] is True and nombres["gdelt"]["habilitado"] is False


def test_catalogo_solo_pasado_con_fuentes_y_siembra_idempotente(db):
    archivo, crudos, errores = catalogo.cargar()
    assert errores == [] and len(crudos) >= 30
    creado = date.fromisoformat(archivo["creado"])
    assert all(c.fecha_evento <= creado for c in crudos)
    assert all(c.url_fuente.startswith("https://") for c in crudos)
    assert all(c.verificacion == "catalogo_revisar" for c in crudos)
    catalogo.sembrar(db, con_vinculos=False)
    n = db.query(EventoMercado).count()
    assert n == len(crudos)
    primero = db.query(EventoMercado).first()
    primero.descartado = 1
    db.commit()
    catalogo.sembrar(db, con_vinculos=False)
    assert db.query(EventoMercado).count() == n
    assert db.get(EventoMercado, primero.id).descartado == 1


def test_parsear_importacion_rechaza_fechas_y_ids_invalidos():
    evs, errs = importacion.parsear([
        {"id": "a b", "titulo": "x", "categoria": "otro", "fecha": "2026-01-01", "url_fuente": "https://a.com"},
        {"id": "ok", "titulo": "x", "categoria": "otro", "fecha": "2026-13-01", "url_fuente": "https://a.com"},
        {"id": "ok2", "titulo": "x", "categoria": "otro", "fecha": "2026-01-01", "fecha_fin": "2025-01-01", "url_fuente": "https://a.com"},
        {"id": "ok3", "titulo": "x", "categoria": "otro", "fecha": "2026-01-01", "url_fuente": "https://a.com", "tickers": [{"ticker": "!!"}]},
        {"id": "ok4", "titulo": "x", "categoria": "otro", "fecha": "2026-01-01", "url_fuente": "https://a.com"},
        {"id": "ok4", "titulo": "y", "categoria": "otro", "fecha": "2026-01-01", "url_fuente": "https://a.com"},
    ], proveedor="t", origen="importacion", hoy=HOY)
    assert [e.id_externo for e in evs] == ["ok4"] and len(errs) == 5


@pytest.fixture
def entorno_api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)

    def override():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app), Sesion
    app.dependency_overrides.clear()
