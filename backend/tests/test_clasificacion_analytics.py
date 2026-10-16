"""Resolución única de la clasificación (`clasificacion_analytics`) y su efecto en las pantallas
que agrupan por tipo, sector y país."""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, ClasificacionAuto, ClasificacionOverride, IndiceMercado, InstrumentoInversion,
    MovimientoInversion, PrecioInstrumento, WatchlistItem,
)
from app.services import clasificacion_analytics as ca
from app.services.cache import limpiar_cache
from app.services.inversiones_analytics import get_exposicion

HOY = date.today()


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: [
        {"simbolo": "KO", "descripcion": "Coca Cola", "moneda": "ARS", "tipo": "CEDEAR"},
        {"simbolo": "KOD", "descripcion": "Coca Cola", "moneda": "USD", "tipo": "CEDEAR"},
        {"simbolo": "VIST", "descripcion": "Vista Energy", "moneda": "ARS", "tipo": "CEDEAR"},
    ])
    monkeypatch.setattr(ca, "cargar_seed", lambda: {
        "variantes": {}, "simbolos_yahoo": {}, "exposicion": {"VIST": {"pais": "Argentina"}},
    })
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    for ticker, sector, pais in (("KOD", "Cosumo Masivo", "AR"), ("VIST", "Energia", "AR"), ("AL30", "Soberano", "AR")):
        tipo = "Bono" if ticker == "AL30" else "CEDEAR"
        session.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento=tipo,
                                         mercado="BCBA", moneda="USD", sector=sector, pais=pais))
        session.add(MovimientoInversion(fecha=date(2024, 1, 2), cartera="c", ticker=ticker,
                                        tipo_movimiento="compra", cantidad=10, precio=100.0,
                                        moneda="USD", comision=0.0))
        session.add(PrecioInstrumento(fecha=HOY, ticker=ticker, precio=100.0, moneda="USD", fuente="sheet"))
    session.add(ClasificacionAuto(
        ticker_base="KO", simbolo_yahoo="KO", estado="ok", tipo="CEDEAR-acción",
        sector="Consumo básico", industria="Bebidas sin alcohol", pais="Estados Unidos",
        region="EEUU", intentos_fallidos=0,
    ))
    session.add(ClasificacionAuto(
        ticker_base="VIST", simbolo_yahoo="VIST", estado="ok", tipo="CEDEAR-acción",
        sector="Energía", pais="México", region="Emergentes", intentos_fallidos=0,
    ))
    session.commit()
    yield session
    session.close()


def _eje(exposicion, nombre):
    return {it["etiqueta"]: it["porcentaje"] for e in exposicion["ejes"] if e["eje"] == nombre for it in e["items"]}


def test_modo_sheet_devuelve_el_texto_crudo(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "false")
    c = ca.clasificaciones(db)
    assert c["KOD"].sector == "Cosumo Masivo" and c["KOD"].pais == "AR"
    exp = get_exposicion(None, db)
    assert set(_eje(exp, "Sector")) == {"Cosumo Masivo", "Energia", "Soberano"}


def test_modo_auto_variante_hereda_la_clasificacion_del_emisor(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    c = ca.clasificaciones(db)
    assert c["KOD"].sector == "Consumo básico" and c["KOD"].fuentes["sector"] == "yahoo"
    assert c["KOD"].pais == "Estados Unidos" and c["KOD"].region == "EEUU"
    assert c["KOD"].tipo == "CEDEAR-acción" and c["KOD"].tipo_base == "CEDEAR"


def test_modo_auto_seed_y_renta_fija(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    c = ca.clasificaciones(db)
    assert c["VIST"].pais == "Argentina" and c["VIST"].region == "Argentina"
    assert c["AL30"].sector == "Soberano" and c["AL30"].pais == "Argentina"


def test_override_manual_gana(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    db.add(ClasificacionOverride(ticker_base="KO", campo="sector", valor="Tecnología",
                                 fecha_actualizacion=datetime.utcnow()))
    db.commit()
    assert ca.clasificaciones(db)["KOD"].sector == "Tecnología"


def test_watchlist_cedear_ignora_pais_argentina_del_alta(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    db.add(WatchlistItem(ticker="KO", nombre="KO", tipo_instrumento="CEDEAR", pais="argentina"))
    db.commit()
    assert ca.clasificaciones(db)["KO"].pais == "Estados Unidos"


def test_el_total_de_cada_eje_no_cambia_entre_modos(db, monkeypatch):
    totales = {}
    for modo in ("false", "true"):
        monkeypatch.setenv("CLASIFICACION_AUTO", modo)
        limpiar_cache()
        exp = get_exposicion(None, db)
        totales[modo] = {e["eje"]: round(sum(it["valor_usd"] for it in e["items"]), 2) for e in exp["ejes"]}
    for eje, total in totales["false"].items():
        assert totales["true"][eje] == total


def test_diferencias(db):
    difs = {d["ticker"]: d for d in ca.diferencias(db)}
    assert difs["KOD"]["ticker_base"] == "KO"
    assert difs["KOD"]["cambios"]["sector"] == {"antes": "Cosumo Masivo", "despues": "Consumo básico", "fuente": "yahoo"}
    assert difs["VIST"]["cambios"]["pais"]["fuente"] == "seed"
    assert "sector" not in difs.get("AL30", {}).get("cambios", {})


# ── Paso B: precedencia activa en las pantallas ───────────────────────────

from app.database import RebalanceoObjetivo  # noqa: E402
from app.services.descomposicion_analytics import get_descomposicion  # noqa: E402
from app.services.inversiones_analytics import get_rebalanceo  # noqa: E402


def test_exposicion_suma_eje_region_solo_en_modo_auto(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    region = _eje(get_exposicion(None, db), "Región")
    assert set(region) == {"EEUU", "Argentina"}
    assert region["Argentina"] == pytest.approx(200 / 3, abs=0.01)   # VIST (seed) + AL30
    limpiar_cache()
    monkeypatch.setenv("CLASIFICACION_AUTO", "false")
    assert _eje(get_exposicion(None, db), "Región") == {}


def test_rebalanceo_canoniza_objetivos_y_avisa_huerfanos(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    for eje, cat, pct in (("Sector", "consumo masivo", 40), ("Sector", "Soberano", 30),
                          ("Sector", "Cripto", 30), ("Tipo", "Cedear", 70), ("Región", "eeuu", 50)):
        db.add(RebalanceoObjetivo(cartera=None, eje=eje, categoria=cat, porcentaje_objetivo=pct))
    db.commit()
    reb = get_rebalanceo(None, db)
    ejes = {e["eje"]: e for e in reb["ejes"]}
    sector = {it["etiqueta"]: it for it in ejes["Sector"]["items"]}
    assert sector["Consumo básico"]["porcentaje_actual"] == pytest.approx(100 / 3, abs=0.01)
    tipo = {it["etiqueta"]: it for it in ejes["Tipo"]["items"]}
    assert tipo["CEDEAR"]["porcentaje_actual"] == pytest.approx(200 / 3, abs=0.01)
    assert {it["etiqueta"] for it in ejes["Región"]["items"]} == {"EEUU"}
    # "Soberano" no es del vocabulario pero AL30 lo tiene: no es huérfano. "Cripto" sí es del
    # vocabulario. Nada huérfano acá…
    assert reb["objetivos_sin_equivalente"] == []
    db.add(RebalanceoObjetivo(cartera=None, eje="Sector", categoria="Agro raro", porcentaje_objetivo=5))
    db.commit()
    assert get_rebalanceo(None, db)["objetivos_sin_equivalente"] == ["Sector: Agro raro"]


def test_descomposicion_por_region(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    d = get_descomposicion(None, db)
    assert d["niveles"][1] == "Región"
    rv = next(n for n in d["raiz"] if n["etiqueta"] == "Renta variable")
    assert {h["etiqueta"] for h in rv["hijos"]} == {"EEUU", "Argentina"}


def test_ticker_con_movimientos_sin_ficha_se_clasifica(db, monkeypatch):
    monkeypatch.setenv("CLASIFICACION_AUTO", "true")
    db.add(MovimientoInversion(fecha=date(2024, 1, 2), cartera="c", ticker="KO", tipo_movimiento="compra",
                               cantidad=1, precio=10.0, moneda="USD", comision=0.0))
    db.commit()
    assert ca.clasificaciones(db)["KO"].sector == "Consumo básico"


def test_equivalencia_con_tablas_vacias_y_sheet_canonico(monkeypatch):
    """Sin nada de Yahoo ni correcciones y con un Sheet ya escrito en el vocabulario canónico,
    los dos modos dan las mismas etiquetas en todos los ejes que existían."""
    monkeypatch.setattr(ca, "cargar_catalogo", lambda: [])
    monkeypatch.setattr(ca, "cargar_seed", lambda: {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}})
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    s.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    for t, tipo, sector, pais in (("GGAL", "Acción", "Financiero", "Argentina"),
                                  ("AL30", "Bono", "Soberano", "Argentina"),
                                  ("FCI1", "FCI", "Liquidez", "Argentina")):
        s.add(InstrumentoInversion(ticker=t, nombre=t, tipo_instrumento=tipo, mercado="BCBA",
                                   moneda="USD", sector=sector, pais=pais))
        s.add(MovimientoInversion(fecha=date(2024, 1, 2), cartera="c", ticker=t, tipo_movimiento="compra",
                                  cantidad=1, precio=100.0, moneda="USD", comision=0.0))
        s.add(PrecioInstrumento(fecha=HOY, ticker=t, precio=100.0, moneda="USD", fuente="sheet"))
    s.commit()
    salidas = {}
    for modo in ("false", "true"):
        monkeypatch.setenv("CLASIFICACION_AUTO", modo)
        limpiar_cache()
        salidas[modo] = {e["eje"]: e["items"] for e in get_exposicion(None, s)["ejes"]}
    for eje, items in salidas["false"].items():
        assert salidas["true"][eje] == items, eje
    assert set(salidas["true"]) - set(salidas["false"]) == {"Región"}
    s.close()
