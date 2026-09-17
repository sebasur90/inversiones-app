"""Catálogo de instrumentos de IOL: clasificación por panel, normalización y búsqueda."""
import json

import pytest

from app.services import catalogo_instrumentos as cat


def _escribir_catalogo(tmp_path, instrumentos, monkeypatch):
    ruta = tmp_path / "iol_catalogo.json"
    ruta.write_text(json.dumps({
        "generado": "2026-08-29", "total": len(instrumentos), "instrumentos": instrumentos,
    }), encoding="utf-8")
    monkeypatch.setenv("IOL_CATALOGO_FILE", str(ruta))
    cat._cache.clear()
    return ruta


@pytest.fixture
def catalogo(tmp_path, monkeypatch):
    _escribir_catalogo(tmp_path, [
        {"simbolo": "ALUA", "descripcion": "Aluar", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Acciones/Merval", "Acciones/Burcap"]},
        {"simbolo": "AAPL", "descripcion": "Cedear Apple Inc", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Acciones/CEDEARs"]},
        {"simbolo": "AL30", "descripcion": "BONO REP ARG USD", "moneda": "US$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Bonos/Todos", "Bonos/Soberanos en dólares"]},
        {"simbolo": "MR36O", "descripcion": "On Gmctr Cl.36", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["ObligacionesNegociables/Todas"]},
        {"simbolo": "S30J5", "descripcion": "Lecap Vto 30/06", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Letras/Todas"]},
        {"simbolo": "PREMIER", "descripcion": "Fondo Premier Renta", "moneda": "peso_Argentino",
         "mercado": "bcba", "pais": "argentina", "paneles": ["FCI/Todos"]},
    ], monkeypatch)
    yield
    cat._cache.clear()


# ── Clasificación ─────────────────────────────────────────────────────────────

def test_tipo_sale_del_prefijo_del_panel(catalogo):
    tipos = {i["simbolo"]: i["tipo"] for i in cat.buscar(limite=99)["items"]}
    assert tipos == {
        "ALUA": "Acción", "AAPL": "CEDEAR", "AL30": "Bono",
        "MR36O": "ON", "S30J5": "Letra", "PREMIER": "FCI",
    }


def test_cedear_gana_sobre_accion(catalogo):
    """Los CEDEARs viven en un panel de `Acciones/`: sin esta precedencia quedarían como acciones
    locales y `_es_cedear` no habilitaría la serie del subyacente en USD."""
    assert cat.obtener("AAPL")["tipo"] == "CEDEAR"


def test_tipos_matchean_los_clasificadores_de_market_data(catalogo):
    """El contrato que hace que un instrumento del catálogo se pueda cotizar: los strings de `tipo`
    tienen que caer en la familia correcta de `market_data/precios.py`."""
    from app.services.market_data import precios

    assert precios._es_renta_variable("Acción")
    assert precios._es_renta_variable("CEDEAR") and precios._es_cedear("CEDEAR")
    assert precios._es_renta_fija("Bono")
    assert precios._es_renta_fija("ON")
    assert precios._es_renta_fija("Letra")
    assert precios._es_fci("FCI")


def test_panel_desconocido_no_rompe(tmp_path, monkeypatch):
    _escribir_catalogo(tmp_path, [
        {"simbolo": "XX", "descripcion": "Raro", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Futuros/Oro"]},
    ], monkeypatch)
    assert cat.obtener("XX")["tipo"] == ""
    cat._cache.clear()


# ── Normalización ─────────────────────────────────────────────────────────────

def test_normaliza_moneda_y_mercado(catalogo):
    """El catálogo es inconsistente: los FCI usan `peso_Argentino` y `bcba` en minúscula."""
    assert cat.obtener("ALUA")["moneda"] == "ARS"
    assert cat.obtener("AL30")["moneda"] == "USD"
    fci = cat.obtener("PREMIER")
    assert fci["moneda"] == "ARS"
    assert fci["mercado"] == "BCBA"


# ── Búsqueda ──────────────────────────────────────────────────────────────────

def test_busca_por_simbolo_y_por_descripcion(catalogo):
    assert [i["simbolo"] for i in cat.buscar("alua")["items"]] == ["ALUA"]
    assert [i["simbolo"] for i in cat.buscar("gmctr")["items"]] == ["MR36O"]


def test_busqueda_ignora_acentos_y_mayusculas(catalogo):
    assert [i["simbolo"] for i in cat.buscar("SOBERANOS EN DOLARES")["items"]] == []
    assert [i["simbolo"] for i in cat.buscar("Bono Rep Arg")["items"]] == ["AL30"]


def test_el_match_exacto_de_simbolo_va_primero(tmp_path, monkeypatch):
    _escribir_catalogo(tmp_path, [
        {"simbolo": "ALUAX", "descripcion": "Otro", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Acciones/Merval"]},
        {"simbolo": "ALUA", "descripcion": "Aluar", "moneda": "AR$", "mercado": "BCBA",
         "pais": "argentina", "paneles": ["Acciones/Merval"]},
    ], monkeypatch)
    assert [i["simbolo"] for i in cat.buscar("ALUA")["items"]] == ["ALUA", "ALUAX"]
    cat._cache.clear()


def test_filtro_por_tipo_no_cambia_los_conteos(catalogo):
    """Los chips tienen que seguir mostrando cuántos hay de cada familia aunque uno esté activo."""
    sin_filtro = cat.buscar()
    con_filtro = cat.buscar(tipo="Bono")

    assert [i["simbolo"] for i in con_filtro["items"]] == ["AL30"]
    assert con_filtro["total"] == 1
    assert con_filtro["conteos_por_tipo"] == sin_filtro["conteos_por_tipo"]
    assert con_filtro["conteos_por_tipo"]["CEDEAR"] == 1


def test_total_es_previo_al_limite(catalogo):
    r = cat.buscar(limite=2)
    assert len(r["items"]) == 2
    assert r["total"] == 6


def test_no_expone_los_campos_internos_de_busqueda(catalogo):
    assert not [k for k in cat.buscar()["items"][0] if k.startswith("_")]


# ── Ausencia del archivo ──────────────────────────────────────────────────────

def test_catalogo_ausente_no_rompe(tmp_path, monkeypatch):
    """Sin catálogo montado la watchlist tiene que seguir mostrándose; no se puede dar de alta."""
    monkeypatch.setenv("IOL_CATALOGO_FILE", str(tmp_path / "no-existe.json"))
    cat._cache.clear()
    assert cat.cargar_catalogo() == []
    assert cat.obtener("ALUA") is None
    assert cat.buscar("ALUA")["items"] == []


def test_catalogo_corrupto_no_rompe(tmp_path, monkeypatch):
    ruta = tmp_path / "roto.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    monkeypatch.setenv("IOL_CATALOGO_FILE", str(ruta))
    cat._cache.clear()
    assert cat.cargar_catalogo() == []


# ── El catálogo real del repo ─────────────────────────────────────────────────

def test_el_catalogo_versionado_se_lee_y_clasifica():
    """Contra el archivo real: si alguien regenera el catálogo y cambia el formato, esto avisa."""
    cat._cache.clear()
    instrumentos = cat.cargar_catalogo()
    if not instrumentos:
        pytest.skip("catálogo no montado en este entorno")

    conteos = cat.conteos_por_tipo(instrumentos)
    assert conteos["CEDEAR"] > 500
    assert conteos["ON"] > 500
    assert conteos["Acción"] > 50
    sin_tipo = [i["simbolo"] for i in instrumentos if not i["tipo"]]
    assert not sin_tipo, f"instrumentos sin clasificar: {sin_tipo[:5]}"
    assert {i["moneda"] for i in instrumentos} <= {"ARS", "USD"}
