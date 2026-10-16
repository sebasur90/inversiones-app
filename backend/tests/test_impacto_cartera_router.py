"""`POST /inversiones/{carteras/X|consolidado}/impacto-compra` sobre una DB real en memoria."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, ClasificacionAuto, ConfiguracionCartera, IndiceMercado, InstrumentoInversion, MovimientoInversion,
    PrecioInstrumento, WatchlistItem, get_db,
)
from app.main import app
from app.services import clasificacion_analytics as ca
from app.services.inversiones_analytics import get_exposicion

URL = "/api/inversiones"
HOY = date.today()


def _inst(db, ticker, sector, pais, tipo="Accion", moneda="USD"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="NYSE",
                                moneda=moneda, sector=sector, pais=pais))


def _pos(db, ticker, cantidad, precio, cartera="Principal", con_precio=True):
    db.add(MovimientoInversion(fecha=date(2024, 1, 1), cartera=cartera, ticker=ticker, tipo_movimiento="compra",
                               cantidad=cantidad, precio=precio, moneda="USD", comision=0.0))
    if con_precio:
        db.add(PrecioInstrumento(fecha=date(2024, 6, 1), ticker=ticker, precio=precio, moneda="USD"))


@pytest.fixture
def sesion(monkeypatch):
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: [
        {"simbolo": "KO", "descripcion": "COCA COLA", "moneda": "ARS", "tipo": "CEDEAR"},
        {"simbolo": "KOD", "descripcion": "COCA COLA", "moneda": "USD", "tipo": "CEDEAR"},
        {"simbolo": "MSFT", "descripcion": "MICROSOFT", "moneda": "ARS", "tipo": "CEDEAR"},
        {"simbolo": "XYZ", "descripcion": "SIN DATOS", "moneda": "ARS", "tipo": "CEDEAR"},
    ])
    monkeypatch.setattr(ca, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    db.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    db.add(ClasificacionAuto(
        ticker_base="KO", simbolo_yahoo="KO", estado="ok", tipo="CEDEAR-acción", nombre="Coca-Cola",
        quote_type="EQUITY", sector="Consumo básico", industria="Bebidas sin alcohol",
        industria_raw="Beverages - Non-Alcoholic", pais="Estados Unidos", region="EEUU",
        intentos_fallidos=0, fecha_fundamentales=HOY,
    ))
    _inst(db, "KOD", "Consumo básico", "Estados Unidos", tipo="CEDEAR")
    _inst(db, "MSFT", "Tecnología", "Estados Unidos")
    _inst(db, "BBB", "Financiero", "Argentina")
    db.commit()
    _pos(db, "KOD", 10, 50.0)     # 500
    _pos(db, "MSFT", 10, 100.0)   # 1000
    _pos(db, "BBB", 10, 50.0)     # 500
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


def _eje(b, nombre):
    return next(e for e in b["ejes"] if e["eje"] == nombre)


def _fila(b, eje, etiqueta):
    return next(f for f in _eje(b, eje)["items"] if f["etiqueta"] == etiqueta)


def _simular(client, ticker="KO", monto=500, ruta="consolidado"):
    return client.post(f"{URL}/{ruta}/impacto-compra", json={"ticker": ticker, "monto_usd": monto})


def test_cedear_y_su_variante_son_un_solo_emisor(client):
    r = _simular(client, "KO", 500)
    assert r.status_code == 200, r.text
    b = r.json()
    ko = _fila(b, "Emisor", "KO")
    assert ko["antes_pct"] == 25.0 and ko["despues_pct"] == 40.0          # 500 → 1000 de 2500
    assert sorted(ko["tickers"]) == ["KO", "KOD"] and ko["nombre"] == "Coca-Cola"
    assert b["emisor"] == "KO" and b["ticker"] == "KO"
    assert not any(f["etiqueta"] == "KOD" for f in _eje(b, "Emisor")["items"])      # no aparece como emisor aparte
    assert any("Ya tenés KO en la cartera (KOD)" in o["texto"] for o in b["observaciones"])


def test_totales_y_peso_del_monto_usan_el_criterio_unico(client):
    b = _simular(client, "MSFT", 500).json()
    assert b["total"]["antes_usd"] == pytest.approx(2000.0) and b["total"]["despues_usd"] == pytest.approx(2500.0)
    assert b["total"]["despues_ars"] == pytest.approx(b["total"]["antes_ars"] + 500 * 1000)
    assert b["peso_monto_pct"] == pytest.approx(20.0)
    assert b["monto_ars"] == pytest.approx(500_000.0)


def test_cada_eje_suma_100_antes_y_despues(client):
    b = _simular(client, "KO", 500).json()
    for eje in b["ejes"]:
        assert sum(f["antes_pct"] for f in eje["items"]) == pytest.approx(100.0, abs=0.1), eje["eje"]
        assert sum(f["despues_pct"] for f in eje["items"]) == pytest.approx(100.0, abs=0.1), eje["eje"]


def test_el_antes_coincide_con_exposicion(client, sesion):
    b = _simular(client, "KO", 500).json()
    db = sesion()
    expo = {e["eje"]: {i["etiqueta"]: i for i in e["items"]} for e in get_exposicion(None, db)["ejes"]}
    db.close()
    for eje in ("Sector", "País", "Región", "Tipo de instrumento"):
        for fila in _eje(b, eje)["items"]:
            if fila["antes_pct"] == 0:
                continue                                          # sólo existe después de sumar el monto
            assert fila["antes_pct"] == pytest.approx(expo[eje][fila["etiqueta"]]["porcentaje"], abs=0.01), (eje, fila)
            assert fila["antes_usd"] == pytest.approx(expo[eje][fila["etiqueta"]]["valor_usd"], abs=0.01)
        assert {f["etiqueta"] for f in _eje(b, eje)["items"] if f["antes_pct"] > 0} == set(expo[eje])


def test_clasificacion_del_ticker_nuevo_viene_de_yahoo(client):
    b = _simular(client, "KO", 500).json()
    assert b["clasificacion"]["sector"] == "Consumo básico" and b["clasificacion"]["pais"] == "Estados Unidos"
    assert _fila(b, "Sector", "Consumo básico")["despues_pct"] == pytest.approx(40.0)
    assert _fila(b, "Sector", "Consumo básico")["afectada"] is True


def test_ticker_sin_clasificar_cae_en_el_bucket_residual_con_aviso(client):
    b = _simular(client, "XYZ", 250).json()
    assert _fila(b, "Sector", "Sin sector")["afectada"] is True
    assert any("«Sin sector»" in o["texto"] for o in b["observaciones"])


def test_umbral_de_pais_y_de_emisor_de_salud(client):
    b = _simular(client, "KO", 5000).json()
    pais = _fila(b, "País", "Estados Unidos")
    assert pais["antes_pct"] == 75.0 and pais["despues_pct"] == pytest.approx(92.86, abs=0.01)
    niveles = {(o["eje"], o["nivel"]) for o in b["observaciones"]}
    assert ("País", "revisar") in niveles and ("Emisor", "revisar") in niveles


def test_peso_maximo_configurado_en_la_cartera_se_respeta(client, sesion):
    db = sesion()
    db.add(ConfiguracionCartera(cartera=None, peso_maximo=45.0))
    db.commit()
    db.close()
    b = _simular(client, "KO", 500).json()           # KO queda en 40 % < 45 %
    assert not [o for o in b["observaciones"] if o["eje"] == "Emisor" and "pasaría" in o["texto"]]


def test_por_cartera_y_cartera_inexistente(client):
    assert _simular(client, "KO", 500, ruta="carteras/Principal").status_code == 200
    assert _simular(client, "KO", 500, ruta="carteras/NoExiste").status_code == 404


def test_ticker_desconocido_es_404_y_los_invalidos_422(client):
    assert _simular(client, "ZZZZ", 100).status_code == 404
    assert _simular(client, "a b", 100).status_code == 422
    assert _simular(client, "KO", 0).status_code == 422
    assert _simular(client, "KO", -5).status_code == 422
    assert _simular(client, "KO", 10 ** 12).status_code == 422
    assert client.post(f"{URL}/consolidado/impacto-compra", json={"ticker": "KO"}).status_code == 422


def test_ticker_de_la_watchlist_se_puede_simular(client, sesion):
    db = sesion()
    db.add(WatchlistItem(ticker="ZWL", nombre="ZWL", tipo_instrumento="Accion", sector="Energía", pais="Brasil"))
    db.commit()
    db.close()
    b = _simular(client, "ZWL", 300).json()
    assert _fila(b, "Sector", "Energía")["despues_usd"] == pytest.approx(300.0)


def test_sin_cotizacion_se_valua_al_costo_con_aviso_y_el_total_es_coherente(client, sesion):
    db = sesion()
    _inst(db, "CCC", "Salud", "Brasil")
    _pos(db, "CCC", 10, 20.0, con_precio=False)          # 200 al costo
    db.commit()
    db.close()
    b = _simular(client, "KO", 500).json()
    assert "CCC" in b["avisos"]["aproximadas"]
    assert b["total"]["antes_usd"] == pytest.approx(2200.0)


def test_cartera_vacia_el_monto_es_todo_y_avisa(client, sesion):
    db = sesion()
    db.query(MovimientoInversion).delete()
    db.commit()
    db.close()
    b = _simular(client, "KO", 300).json()
    assert b["peso_monto_pct"] == pytest.approx(100.0)
    assert _fila(b, "Emisor", "KO")["despues_pct"] == 100.0 and any("no tiene posiciones" in n for n in b["notas"])


def test_sin_mep_el_total_en_pesos_no_incluye_el_monto_y_lo_dice(client, sesion):
    db = sesion()
    db.query(IndiceMercado).delete()
    db.commit()
    db.close()
    r = _simular(client, "KO", 300)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["monto_ars"] == 0.0 and any("MEP" in n for n in b["notas"])


def test_simular_no_escribe_nada(client, sesion):
    def contar():
        db = sesion()
        try:
            return {t.name: db.execute(select(func.count()).select_from(t)).scalar() for t in Base.metadata.sorted_tables}
        finally:
            db.close()

    antes = contar()
    for ruta in ("consolidado", "carteras/Principal"):
        assert _simular(client, "KO", 700, ruta=ruta).status_code == 200
    assert _simular(client, "XYZ", 50).status_code == 200
    assert contar() == antes


def test_determinista_y_sin_cache_entre_montos(client):
    a, b = _simular(client, "KO", 500).json(), _simular(client, "KO", 500).json()
    assert a == b
    c = _simular(client, "KO", 1500).json()
    assert _fila(c, "Emisor", "KO")["despues_pct"] != _fila(a, "Emisor", "KO")["despues_pct"]


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

    for ticker, monto in (("KO", 500), ("KO", 5000), ("XYZ", 100)):
        b = _simular(client, ticker, monto).json()
        for t in textos({"obs": b["observaciones"], "notas": b["notas"]}):
            assert not prohibidas.search(t), t
