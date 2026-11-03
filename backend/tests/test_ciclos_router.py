"""Endpoints de Ciclos de mercado sobre una DB en memoria con catálogo, series y cartera de juguete: forma de las
respuestas, errores 404/422, cartera y consolidado, y que ninguna simulación escriba."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, MovimientoInversion, get_db
from app.main import app
from app.routers import ciclos as router_ciclos
from app.services import ciclos_historial
from app.services.cache import limpiar_cache

from .ciclos_helpers import TOTAL_CARTERA, cartera_de_prueba, fin, pos

URL = "/api/inversiones"


@pytest.fixture
def sesion(tmp_path, monkeypatch):
    return cartera_de_prueba(tmp_path, monkeypatch)


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


# -- catálogo y estado -------------------------------------------------------------------------

def test_catalogo(client):
    r = client.get(f"{URL}/ciclos/catalogo")
    assert r.status_code == 200
    b = r.json()
    assert b["errores"] == [] and {g["id"] for g in b["grupos"]} >= {"tecnologia", "oro", "apagado"}
    apagado = next(g for g in b["grupos"] if g["id"] == "apagado")
    assert apagado["activo"] is False
    tec = next(g for g in b["grupos"] if g["id"] == "tecnologia")
    assert tec["pertenencia"] == {"exacta_sector": ["Tecnología"]} and tec["benchmark"] == "estados-unidos" and tec["exclusivo"] is True
    assert b["comparaciones"][0]["id"] == "eeuu-europa" and b["pares_desfase"][0]["grupos"] == ["oro", "global"]
    assert b["periodos"][0]["id"] == "tramo"


def test_estado_de_cobertura(client):
    b = client.get(f"{URL}/ciclos/estado").json()
    assert b["con_datos"] == 0 and b["sin_datos"] == len(b["simbolos"]) > 0           # nada se descargó con la ingesta
    xlk = next(s for s in b["simbolos"] if s["simbolo"] == "XLK")
    assert xlk["estado"] == "sin_intentar" and xlk["grupos"] == ["tecnologia"] and xlk["rol"] == "proxy"


def test_refrescar_responde_enseguida_y_corre_en_segundo_plano(client, monkeypatch):
    lanzados = []

    class Hilo:
        def __init__(self, target, daemon, name):
            lanzados.append((target, name))

        def start(self):
            lanzados.append("start")

    monkeypatch.setattr(router_ciclos.threading, "Thread", Hilo)
    r = client.post(f"{URL}/ciclos/refrescar")
    assert r.status_code == 202 and r.json() == {"resultado": "iniciado"} and lanzados[-1] == "start"


# -- panorama y detalle ------------------------------------------------------------------------

def test_panorama_200_con_la_forma_completa(client):
    r = client.get(f"{URL}/ciclos/panorama", params={"tipo": "sector", "periodo": "6M"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert {"filtros", "opciones", "regimen", "benchmark", "grupos", "horizontes", "fechas_horizontes", "cambios_liderazgo", "cobertura", "meta"} <= set(b)
    tec = next(g for g in b["grupos"] if g["id"] == "tecnologia")
    assert tec["rrg"]["actual"]["cuadrante"] == "leading" and tec["rrg"]["trayectoria"]
    assert b["meta"]["moneda"] == "USD" and b["meta"]["benchmark"]["proxy"] == "SPY" and b["meta"]["ultima_fecha_datos"] == fin().isoformat()
    assert b["regimen"]["estado"] == "no_disponible" and b["horizontes"][:4] == ["1M", "3M", "6M", "1A"]
    assert tec["rendimientos"]["1A"]["absoluto"] is not None


def test_panorama_filtros(client):
    b = client.get(f"{URL}/ciclos/panorama", params={"tipo": "sector", "benchmark": "global", "grupos": "tecnologia,salud", "moneda": "ARS"}).json()
    assert [g["id"] for g in b["grupos"]] == ["tecnologia", "salud"] and b["filtros"]["benchmark"] == "global"
    assert b["meta"]["moneda"] == "ARS"


@pytest.mark.parametrize("params, codigo", [
    ({"tipo": "inventado"}, 422), ({"moneda": "EUR"}, 422), ({"periodo": "9M"}, 422), ({"ventana": 1}, 422),
    ({"cola": 0}, 422), ({"grupos": "europa"}, 422), ({"benchmark": "nada"}, 404), ({"benchmark": "tecnologia"}, 404),
])
def test_panorama_errores(client, params, codigo):
    assert client.get(f"{URL}/ciclos/panorama", params=params).status_code == codigo


def test_detalle(client):
    r = client.get(f"{URL}/ciclos/grupos/tecnologia", params={"horizonte": "1A", "con": "salud"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["grupo"]["id"] == "tecnologia" and b["estado"] == "ok" and b["rotacion"]["actual"]["cuadrante"] == "leading"
    assert [s["rol"] for s in b["series"]] == ["grupo", "benchmark", "adicional"] and b["filas"][0]["tecnologia"] == 100.0
    assert b["meta"]["periodo"]["hasta"] == fin().isoformat() and b["periodos"][0]["id"] == "tramo"


def test_detalle_de_un_periodo_y_fechas(client):
    assert client.get(f"{URL}/ciclos/grupos/tecnologia", params={"periodo_id": "tramo"}).status_code == 200
    r = client.get(f"{URL}/ciclos/grupos/tecnologia", params={"desde": (fin() - timedelta(days=90)).isoformat(), "hasta": fin().isoformat()})
    assert r.status_code == 200 and r.json()["rango"]["etiqueta"] == "fechas elegidas"


@pytest.mark.parametrize("ruta, params, codigo", [
    ("nada", {}, 404), ("apagado", {}, 404), ("tecnologia", {"periodo_id": "nada"}, 404), ("tecnologia", {"con": "nada"}, 404),
    ("tecnologia", {"horizonte": "7A"}, 422), ("tecnologia", {"moneda": "BRL"}, 422), ("tecnologia", {"desde": "2025-01-01", "hasta": "2024-01-01"}, 422),
    ("tecnologia", {"desde": "no-es-fecha"}, 422), ("tecnologia", {"con": "a,b,c,d,e,f"}, 422),
])
def test_detalle_errores(client, ruta, params, codigo):
    assert client.get(f"{URL}/ciclos/grupos/{ruta}", params=params).status_code == codigo


def test_pais(client):
    r = client.get(f"{URL}/ciclos/paises/europa")
    assert r.status_code == 200 and r.json()["estado"] == "sin_datos"                     # no hay serie de VGK en la DB de prueba
    assert client.get(f"{URL}/ciclos/paises/tecnologia").status_code == 404
    assert client.get(f"{URL}/ciclos/paises/nada").status_code == 404
    assert client.get(f"{URL}/ciclos/paises/europa", params={"meses": 5}).status_code == 422


def test_senales_sin_y_con_historial(client, sesion):
    r = client.get(f"{URL}/ciclos/grupos/tecnologia/senales")
    assert r.status_code == 200 and r.json()["eventos"] == [] and r.json()["estado_confirmado"] is None
    assert "no es una predicción" in r.json()["aviso"]
    db = sesion()
    ciclos_historial.registrar(db, hoy=fin() + timedelta(days=1), semanas=60)
    db.close()
    b = client.get(f"{URL}/ciclos/grupos/tecnologia/senales").json()
    assert b["estado_confirmado"] == "leading" and b["benchmark_id"] == "estados-unidos" and b["confirmacion_semanas"] == 3
    assert client.get(f"{URL}/ciclos/grupos/nada/senales").status_code == 404
    assert client.get(f"{URL}/ciclos/grupos/tecnologia/senales", params={"benchmark": "nada"}).status_code == 404


# -- relaciones --------------------------------------------------------------------------------

def test_correlaciones(client):
    r = client.get(f"{URL}/ciclos/relaciones/correlaciones", params={"ids": "tecnologia,salud,energia", "periodo": "1A"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["estado"] == "ok" and len(b["matriz"]) == 3 and b["matriz"][0][0] == 1.0 and b["pares"][0]["n_obs"] > 0
    assert any("causalidad" in a for a in b["meta"]["advertencias"])
    assert client.get(f"{URL}/ciclos/relaciones/correlaciones", params={"ids": "tecnologia"}).status_code == 422
    assert client.get(f"{URL}/ciclos/relaciones/correlaciones", params={"ids": "tecnologia,nada"}).status_code == 404
    assert client.get(f"{URL}/ciclos/relaciones/correlaciones", params={"ids": "tecnologia,salud", "periodo": "5A"}).status_code == 422


def test_desfases(client):
    r = client.get(f"{URL}/ciclos/relaciones/desfases", params={"a": "tecnologia", "b": "salud"})
    assert r.status_code == 200 and len(r.json()["desfases"]) == 17 and "no una predicción" in r.json()["lectura"]
    assert client.get(f"{URL}/ciclos/relaciones/desfases", params={"a": "tecnologia"}).status_code == 422
    assert client.get(f"{URL}/ciclos/relaciones/desfases", params={"a": "tecnologia", "b": "nada"}).status_code == 404
    assert client.get(f"{URL}/ciclos/relaciones/desfases", params={"a": "tecnologia", "b": "salud", "meses": 3}).status_code == 422


def test_comparacion(client):
    r = client.get(f"{URL}/ciclos/relaciones/comparacion", params={"ids": "tecnologia,salud", "benchmark": "estados-unidos"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["estado"] == "ok" and {g["id"] for g in b["grupos"]} == {"tecnologia", "salud"} and b["filas"]
    assert client.get(f"{URL}/ciclos/relaciones/comparacion", params={"ids": "tecnologia"}).status_code == 422
    assert client.get(f"{URL}/ciclos/relaciones/comparacion", params={"ids": "tecnologia,nada"}).status_code == 404
    assert client.get(f"{URL}/ciclos/relaciones/comparacion").status_code == 422


# -- cartera -----------------------------------------------------------------------------------

def test_cartera_y_consolidado(client):
    for ruta in ("carteras/Principal", "consolidado"):
        r = client.get(f"{URL}/{ruta}/ciclos/cartera")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["total_usd"] == pytest.approx(TOTAL_CARTERA) and {d["dimension"] for d in b["dimensiones"]} == {"Sector", "Región", "País"}
        assert b["resumen"]["en_leading_pct"] > 0 and b["uniones_pct"]["tema"] > 0 and b["sin_clasificar"]
    assert client.get(f"{URL}/carteras/NoExiste/ciclos/cartera").status_code == 404
    assert client.get(f"{URL}/consolidado/ciclos/cartera", params={"benchmark": "nada"}).status_code == 404


def test_instrumentos_de_un_grupo(client):
    r = client.get(f"{URL}/carteras/Principal/ciclos/grupos/consumo-basico/instrumentos")
    assert r.status_code == 200
    b = r.json()
    assert [i["emisor"] for i in b["instrumentos"]] == ["KO"] and b["instrumentos"][0]["tickers"] == ["KO", "KOD"]
    assert client.get(f"{URL}/consolidado/ciclos/grupos/tecnologia/instrumentos").json()["exposicion_usd"] == 1500.0
    assert client.get(f"{URL}/consolidado/ciclos/grupos/nada/instrumentos").status_code == 404
    assert client.get(f"{URL}/carteras/NoExiste/ciclos/grupos/tecnologia/instrumentos").status_code == 404


def test_simular_una_rotacion(client):
    r = client.post(f"{URL}/carteras/Principal/ciclos/simular", json={"origen": "tecnologia", "destino": "salud", "pct": 5})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["rotacion"]["monto_usd"] == pytest.approx(TOTAL_CARTERA * 0.05, abs=0.01) and {e["eje"] for e in b["ejes"]} >= {"Emisor", "Sector", "País"}
    assert any(o["eje"] == "Ciclos" for o in b["observaciones"]) and b["supuestos"]
    assert client.post(f"{URL}/consolidado/ciclos/simular", json={"origen": "tecnologia", "destino": "energia", "pct": 10}).status_code == 200


@pytest.mark.parametrize("cuerpo, codigo", [
    ({"origen": "tecnologia", "destino": "salud", "pct": 0}, 422), ({"origen": "tecnologia", "destino": "salud", "pct": 60}, 422),
    ({"origen": "tecnologia", "destino": "tecnologia", "pct": 5}, 422), ({"origen": "europa", "destino": "salud", "pct": 5}, 422),
    ({"origen": "tecnologia", "destino": "nada", "pct": 5}, 404), ({"origen": "nada", "destino": "salud", "pct": 5}, 404),
    ({"origen": "tecnologia", "destino": "salud"}, 422), ({"origen": "", "destino": "salud", "pct": 5}, 422),
    ({"origen": "tecnologia", "destino": "salud", "pct": "mucho"}, 422),
])
def test_simular_errores(client, cuerpo, codigo):
    assert client.post(f"{URL}/consolidado/ciclos/simular", json=cuerpo).status_code == codigo


def test_simular_con_cartera_inexistente(client):
    assert client.post(f"{URL}/carteras/NoExiste/ciclos/simular", json={"origen": "tecnologia", "destino": "salud", "pct": 5}).status_code == 404


def test_simular_no_escribe_ni_cambia_la_cartera(client, sesion):
    db = sesion()
    antes = {t.name: db.execute(t.select()).fetchall() for t in Base.metadata.sorted_tables}
    db.close()
    for _ in range(3):
        assert client.post(f"{URL}/carteras/Principal/ciclos/simular", json={"origen": "tecnologia", "destino": "salud", "pct": 5}).status_code == 200
    db = sesion()
    despues = {t.name: db.execute(t.select()).fetchall() for t in Base.metadata.sorted_tables}
    assert antes == despues and db.query(MovimientoInversion).count() == 7
    db.close()
    limpiar_cache()
    assert client.get(f"{URL}/carteras/Principal/ciclos/cartera").json()["total_usd"] == pytest.approx(TOTAL_CARTERA)
