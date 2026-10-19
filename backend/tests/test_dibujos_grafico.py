"""Dibujos manuales del gráfico técnico: validación y CRUD del endpoint."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, DibujoGrafico, InstrumentoInversion, WatchlistItem, get_db
from app.main import app
from app.services import dibujos_grafico as dg

F1, F2 = date(2026, 3, 2), date(2026, 4, 6)


def _base(**extra):
    return {"variante": "local", "tipo": "horizontal", "fecha1": F1, "precio1": 100.0, **extra}


# ── Validación ───────────────────────────────────────────────────────────────

def test_validar_casos_validos():
    assert dg.validar(_base()) is None
    assert dg.validar(_base(tipo="tendencia", fecha2=F2, precio2=120.0)) is None
    assert dg.validar(_base(tipo="fibonacci", fecha2=F2, precio2=80.0, color="#AABBCC")) is None


@pytest.mark.parametrize("datos,codigo", [
    (_base(tipo="circulo"), "tipo_invalido"),
    (_base(variante="otra"), "variante_invalida"),
    (_base(precio1=0.0), "precio_invalido"),
    (_base(precio1=-5.0), "precio_invalido"),
    (_base(tipo="tendencia", fecha2=F2, precio2=-1.0), "precio_invalido"),
    (_base(tipo="tendencia"), "falta_segundo_punto"),
    (_base(tipo="fibonacci", fecha2=F2), "falta_segundo_punto"),
    (_base(tipo="tendencia", precio2=90.0), "falta_segundo_punto"),
    (_base(fecha2=F2, precio2=90.0), "segundo_punto_sobra"),
    (_base(tipo="tendencia", fecha2=F1, precio2=90.0), "mismo_dia"),
    (_base(tipo="fibonacci", fecha2=F2, precio2=100.0), "mismo_precio"),
    (_base(color="rojo"), "color_invalido"),
    (_base(color="#12345"), "color_invalido"),
])
def test_validar_rechaza(datos, codigo):
    assert dg.validar(datos) == codigo


def test_tendencia_acepta_el_mismo_precio_en_dias_distintos():
    assert dg.validar(_base(tipo="tendencia", fecha2=F2, precio2=100.0)) is None   # canal horizontal


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)
    s = sesion()
    s.add(InstrumentoInversion(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))
    s.add(WatchlistItem(ticker="MSFT", nombre="Microsoft", tipo_instrumento="CEDEAR", mercado="BCBA", moneda="ARS"))
    s.commit()
    s.close()

    def override():
        d = sesion()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override
    c = TestClient(app)
    c.sesion = sesion
    yield c
    app.dependency_overrides.clear()


def _json(**extra):
    return {"variante": "local", "tipo": "horizontal", "fecha1": "2026-03-02", "precio1": 100.0, **extra}


URL = "/api/inversiones/tecnico/GGAL/dibujos"


def test_crud_completo(client):
    r = client.post(URL, json=_json())
    assert r.status_code == 201
    h = r.json()
    assert h["color"] == "#fbbf24" and h["fecha2"] is None and h["ticker"] == "GGAL"

    t = client.post(URL, json=_json(tipo="tendencia", fecha2="2026-04-06", precio2=120.5, color="#112233")).json()
    assert t["color"] == "#112233" and t["precio2"] == 120.5
    assert [d["id"] for d in client.get(URL).json()] == [h["id"], t["id"]]

    nuevo = client.put(f"{URL}/{t['id']}", json=_json(tipo="fibonacci", fecha2="2026-04-07", precio2=90.0)).json()
    assert nuevo["tipo"] == "fibonacci" and nuevo["precio2"] == 90.0 and nuevo["color"] == "#c084fc"

    assert client.delete(f"{URL}/{h['id']}").status_code == 204
    assert [d["id"] for d in client.get(URL).json()] == [t["id"]]


def test_get_filtra_por_variante(client):
    client.post(URL, json=_json())
    client.post(URL, json=_json(variante="subyacente", precio1=500.0))
    assert len(client.get(URL).json()) == 2
    solo = client.get(f"{URL}?variante=subyacente").json()
    assert len(solo) == 1 and solo[0]["precio1"] == 500.0
    assert client.get(f"{URL}?variante=xx").status_code == 422


def test_validaciones_devuelven_422_con_mensaje(client):
    r = client.post(URL, json=_json(tipo="tendencia"))
    assert r.status_code == 422 and "dos puntos" in r.json()["detail"]
    assert client.post(URL, json=_json(tipo="fibonacci", fecha2="2026-04-06", precio2=100.0)).status_code == 422
    creado = client.post(URL, json=_json()).json()
    assert client.put(f"{URL}/{creado['id']}", json=_json(precio1=0)).status_code == 422
    assert client.get(URL).json()[0]["precio1"] == 100.0           # el PUT inválido no cambió nada


def test_ticker_desconocido_y_dibujo_ajeno(client):
    assert client.get("/api/inversiones/tecnico/NOEXISTE/dibujos").status_code == 404
    assert client.post("/api/inversiones/tecnico/NOEXISTE/dibujos", json=_json()).status_code == 404
    d = client.post(URL, json=_json()).json()
    # El id existe pero es de GGAL: por MSFT no se puede ni leer, ni cambiar, ni borrar.
    otro = "/api/inversiones/tecnico/MSFT/dibujos"
    assert client.put(f"{otro}/{d['id']}", json=_json()).status_code == 404
    assert client.delete(f"{otro}/{d['id']}").status_code == 404
    assert client.delete(f"{URL}/9999").status_code == 404
    assert client.get(otro).json() == []


def test_tope_por_ticker(client):
    for _ in range(dg.MAX_POR_TICKER):
        assert client.post(URL, json=_json()).status_code == 201
    r = client.post(URL, json=_json())
    assert r.status_code == 422 and "Máximo" in r.json()["detail"]
    # Otro ticker no comparte el tope.
    assert client.post("/api/inversiones/tecnico/MSFT/dibujos", json=_json()).status_code == 201


def test_sacar_un_ticker_de_la_watchlist_borra_sus_dibujos_salvo_que_este_en_cartera(client):
    from app.services import watchlist_analytics as wa
    client.post("/api/inversiones/tecnico/MSFT/dibujos", json=_json())
    client.post(URL, json=_json())                                  # GGAL está en cartera
    db = client.sesion()
    db.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))
    db.commit()
    assert wa.eliminar(db, "MSFT") and wa.eliminar(db, "GGAL")
    db.commit()
    assert [d.ticker for d in db.query(DibujoGrafico).all()] == ["GGAL"]
    db.close()
