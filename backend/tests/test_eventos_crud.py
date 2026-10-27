"""Calendario de eventos: alta, edición y baja manual, lápidas de importados, fusión, vínculos con varios
instrumentos, bandeja de noticias y filtros del listado (endpoints + servicio)."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, EventoInstrumento, EventoMercado, NoticiaMercado, get_db
from app.main import app


@pytest.fixture
def entorno():
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


def _evento(**kw):
    base = {"titulo": "Decisión de tasas de la Fed", "categoria": "banco_central", "fecha_evento": "2026-03-18",
            "importancia": 3, "pais": "Estados Unidos"}
    base.update(kw)
    return base


def _importado(s, **kw) -> EventoMercado:
    ahora = datetime.utcnow()
    datos = dict(titulo="Balance de Apple", categoria="resultados", fecha_evento=date(2026, 1, 29),
                 origen="proveedor", proveedor="yahoo_resultados", id_externo="AAPL:2026-01-29",
                 fecha_creacion=ahora, fecha_actualizacion=ahora)
    datos.update(kw)
    e = EventoMercado(**datos)
    s.add(e)
    s.commit()
    return e


def test_alta_edicion_y_borrado_manual(entorno):
    client, Sesion = entorno
    r = client.post("/api/inversiones/eventos", json=_evento(
        hora_evento="14:00", zona_horaria="America/New_York", fecha_publicacion="2026-03-18T18:00:00Z",
        instrumentos=[{"ticker": "spy", "tipo_relacion": "indice", "relevancia": 0.6},
                      {"ticker": "AAPL", "tipo_relacion": "macro", "relevancia": 0.3, "justificacion": "tasas"}],
    ))
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["origen"] == "manual" and ev["hora_evento"] == "14:00"
    # La fecha del evento y la de publicación quedan separadas.
    assert ev["fecha_evento"] == "2026-03-18" and ev["fecha_publicacion"].startswith("2026-03-18T18:00")
    assert [v["ticker"] for v in ev["instrumentos"]] == ["SPY", "AAPL"]
    assert ev["estado"] == "concluido"   # fecha pasada sin estado explícito

    r = client.patch(f"/api/inversiones/eventos/{ev['id']}", json={"titulo": "Fed: tasas sin cambios", "fijado": True})
    assert r.status_code == 200
    assert r.json()["titulo"] == "Fed: tasas sin cambios" and r.json()["fijado"] is True
    # Un evento manual no acumula `campos_editados`: es todo del usuario.
    assert r.json()["campos_editados"] == []

    assert client.delete(f"/api/inversiones/eventos/{ev['id']}").status_code == 204
    assert client.get(f"/api/inversiones/eventos/{ev['id']}").status_code == 404
    with Sesion() as s:
        assert s.query(EventoInstrumento).count() == 0


def test_evento_sin_ticker_es_valido(entorno):
    client, _ = entorno
    r = client.post("/api/inversiones/eventos", json=_evento(titulo="Inicio de la guerra", categoria="geopolitica"))
    assert r.status_code == 201
    assert r.json()["instrumentos"] == []


@pytest.mark.parametrize("cambio,mensaje", [
    ({"categoria": "astrologia"}, "categoría"),
    ({"url_fuente": "javascript:alert(1)"}, "URL"),
    ({"fecha_fin": "2026-03-01"}, "finalización"),
    ({"zona_horaria": "Marte/Olympus"}, "zona horaria"),
    ({"instrumentos": [{"ticker": "NO VALIDO!"}]}, "ticker"),
    ({"precision_fecha": "a ojo"}, "precisión"),
])
def test_validaciones(entorno, cambio, mensaje):
    client, _ = entorno
    r = client.post("/api/inversiones/eventos", json=_evento(**cambio))
    assert r.status_code == 422
    assert mensaje.lower() in r.json()["detail"].lower()


def test_editar_importado_marca_campos_y_borrar_lo_descarta(entorno):
    client, Sesion = entorno
    with Sesion() as s:
        eid = _importado(s).id
    r = client.patch(f"/api/inversiones/eventos/{eid}", json={"fecha_evento": "2026-01-30", "notas": "lo corrí un día"})
    assert r.status_code == 200
    assert set(r.json()["campos_editados"]) == {"fecha_evento", "notas"}

    r = client.delete(f"/api/inversiones/eventos/{eid}")
    assert r.status_code == 200 and r.json() == {"resultado": "descartado"}
    with Sesion() as s:
        e = s.get(EventoMercado, eid)
        assert e is not None and e.descartado == 1
    # Descartado: no aparece en el listado salvo que se pida.
    assert client.get("/api/inversiones/eventos").json()["total"] == 0
    assert client.get("/api/inversiones/eventos", params={"incluir_descartados": True}).json()["total"] == 1


def test_fusionar_mueve_noticias_y_vinculos(entorno):
    client, Sesion = entorno
    a = client.post("/api/inversiones/eventos", json=_evento(instrumentos=[{"ticker": "SPY"}, {"ticker": "QQQ"}])).json()
    b = client.post("/api/inversiones/eventos", json=_evento(titulo="Fed mantiene tasas", url_fuente="https://federalreserve.gov/x",
                                                               instrumentos=[{"ticker": "SPY", "relevancia": 0.4}])).json()
    with Sesion() as s:
        s.add(NoticiaMercado(proveedor="marketaux", id_externo="n1", url="https://a.com/1", url_normalizada="https://a.com/1",
                             titulo="Fed", fecha_publicacion=datetime(2026, 3, 18), fecha_captura=datetime.utcnow(),
                             evento_id=a["id"], estado="asociada"))
        s.commit()
    r = client.post(f"/api/inversiones/eventos/{a['id']}/fusionar", json={"destino_id": b["id"]})
    assert r.status_code == 200
    destino = r.json()
    assert destino["n_noticias"] == 1
    por_ticker = {v["ticker"]: v for v in destino["instrumentos"]}
    assert set(por_ticker) == {"SPY", "QQQ"} and por_ticker["SPY"]["relevancia"] == 0.4   # el del destino manda
    # El absorbido deja de listarse.
    ids = [e["id"] for e in client.get("/api/inversiones/eventos").json()["eventos"]]
    assert ids == [b["id"]]
    assert client.post(f"/api/inversiones/eventos/{b['id']}/fusionar", json={"destino_id": b["id"]}).status_code == 422


def test_vinculos_varios_tickers_y_lapida_de_automatico(entorno):
    client, Sesion = entorno
    with Sesion() as s:
        eid = _importado(s).id
        s.add_all([
            EventoInstrumento(evento_id=eid, ticker="AAPL", tipo_relacion="directa", metodo="automatico", relevancia=1,
                              estado_revision="propuesta", fecha_creacion=datetime.utcnow()),
            EventoInstrumento(evento_id=eid, ticker="MSFT", tipo_relacion="sector", metodo="automatico", relevancia=0.5,
                              estado_revision="propuesta", fecha_creacion=datetime.utcnow()),
        ])
        s.commit()
    r = client.put(f"/api/inversiones/eventos/{eid}/instrumentos/AAPL", json={"ticker": "AAPL", "estado_revision": "confirmada"})
    assert r.status_code == 200 and r.json()["metodo"] == "manual" and r.json()["estado_revision"] == "confirmada"
    # Quitar un vínculo automático lo deja como lápida (la asociación automática no lo revive).
    assert client.delete(f"/api/inversiones/eventos/{eid}/instrumentos/MSFT").status_code == 204
    with Sesion() as s:
        msft = s.query(EventoInstrumento).filter_by(evento_id=eid, ticker="MSFT").one()
        assert msft.estado_revision == "descartada"
    # Filtrar por ticker ignora los vínculos descartados.
    assert client.get("/api/inversiones/eventos", params={"ticker": "MSFT"}).json()["total"] == 0
    assert client.get("/api/inversiones/eventos", params={"ticker": "AAPL"}).json()["total"] == 1


def test_filtros_combinables_y_busqueda(entorno):
    client, _ = entorno
    hoy = date.today()
    client.post("/api/inversiones/eventos", json=_evento(titulo="Elecciones legislativas", categoria="elecciones",
                                                         pais="Argentina", importancia=3, fecha_evento=f"{hoy.year + 1}-10-25"))
    client.post("/api/inversiones/eventos", json=_evento(titulo="Balance de Galicia", categoria="resultados", pais="Argentina",
                                                         importancia=2, entidades={"sectores": ["Financiero"], "empresas": ["Grupo Galicia"]},
                                                         instrumentos=[{"ticker": "GGAL"}]))
    client.post("/api/inversiones/eventos", json=_evento())
    g = lambda **p: client.get("/api/inversiones/eventos", params=p).json()
    assert g()["total"] == 3
    assert g(pais="Argentina")["total"] == 2
    assert g(pais="Argentina", importancia_min=3)["total"] == 1
    assert g(temporalidad="futuros")["eventos"][0]["titulo"] == "Elecciones legislativas"
    assert g(temporalidad="futuros")["eventos"][0]["es_futuro"] is True
    assert g(sector="financiero")["total"] == 1
    assert g(q="galicia")["total"] == 1          # por empresa en entidades
    assert g(q="ggal")["total"] == 1             # por ticker
    assert g(categoria="resultados,elecciones")["total"] == 2
    assert g(desde="2026-03-01", hasta="2026-03-31")["total"] == 2
    assert g(limite=1, page=2)["eventos"][0]["id"] is not None and g(limite=1)["total"] == 3
    assert g(origen="proveedor")["total"] == 0
    assert client.get("/api/inversiones/eventos", params={"desde": "2026-04-01", "hasta": "2026-03-01"}).status_code == 422


def test_bandeja_crear_evento_desde_noticia_y_descartar(entorno):
    client, Sesion = entorno
    with Sesion() as s:
        n1 = NoticiaMercado(proveedor="marketaux", id_externo="n1", url="https://a.com/1", url_normalizada="https://a.com/1",
                            titulo="Nvidia anuncia compra de una startup", fecha_publicacion=datetime(2026, 5, 2, 22, 30),
                            fecha_captura=datetime.utcnow(), categoria_sugerida="corporativo", estado="por_revisar")
        n2 = NoticiaMercado(proveedor="marketaux", id_externo="n2", url="https://a.com/2", url_normalizada="https://a.com/2",
                            titulo="Rumor sin fuente", fecha_publicacion=datetime(2026, 5, 3), fecha_captura=datetime.utcnow(),
                            estado="por_revisar")
        s.add_all([n1, n2])
        s.commit()
        id1, id2 = n1.id, n2.id
    assert client.get("/api/inversiones/eventos/noticias").json()["total"] == 2
    r = client.post(f"/api/inversiones/eventos/noticias/{id1}/crear-evento", json={})
    assert r.status_code == 201
    ev = r.json()
    assert ev["categoria"] == "corporativo" and ev["fecha_evento"] == "2026-05-02"
    assert ev["fecha_publicacion"].startswith("2026-05-02T22:30") and ev["n_noticias"] == 1
    assert client.post(f"/api/inversiones/eventos/noticias/{id2}/descartar").json()["estado"] == "descartada"
    assert client.get("/api/inversiones/eventos/noticias").json()["total"] == 0


def test_opciones_incluyen_valores_validos_y_existentes(entorno):
    client, _ = entorno
    client.post("/api/inversiones/eventos", json=_evento(entidades={"sectores": ["Tecnología"]}, instrumentos=[{"ticker": "NVDA"}]))
    o = client.get("/api/inversiones/eventos/opciones").json()
    assert {"valor": "elecciones", "etiqueta": "Elecciones"} in o["categorias"]
    assert "Estados Unidos" in o["paises"] and "Tecnología" in o["sectores"]
    assert {"NVDA", "SPY", "^MERV"} <= set(o["tickers"])
