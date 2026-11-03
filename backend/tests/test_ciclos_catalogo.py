"""Catálogo de «Ciclos de mercado»: el JSON real es válido, un grupo inválido se descarta sin romper
al resto, y los defaults, los símbolos a bajar y los períodos se resuelven como dice la doc."""
import json
from datetime import date

import pytest

from app.services import ciclos_catalogo as cc


def _g(id_, **kw):
    base = {"id": id_, "nombre": id_.title(), "tipo": "sector", "proxy": id_.upper()}
    base.update(kw)
    return base


DOC_BASE = {
    "version": 1,
    "defecto_por_tipo": {"sector": {"benchmark": "spy", "exclusivo": True}, "pais": {"benchmark": "spy"}},
    "grupos": [
        {"id": "spy", "nombre": "S&P 500", "tipo": "region", "proxy": "SPY", "es_benchmark": True, "benchmark": None},
    ],
}


def _doc(*grupos):
    d = json.loads(json.dumps(DOC_BASE))
    d["grupos"].extend(grupos)
    return d


# -- el catálogo real --------------------------------------------------------------------------

def test_el_catalogo_real_es_valido():
    cat = cc.cargar()
    assert cat.errores == []
    assert len(cat.grupos) >= 40
    assert {"estados-unidos", "global"} <= {g.id for g in cat.benchmarks()}


def test_el_catalogo_real_cubre_lo_pedido():
    ids = set(cc.cargar().grupos)
    # sectores, industrias, commodities separados, regiones y activos del pedido
    for esperado in ("tecnologia", "semiconductores", "software", "defensa", "oro", "plata", "petroleo", "cobre",
                     "agricultura", "soja", "metales-preciosos", "metales-industriales", "europa", "japon", "china",
                     "india", "brasil", "mexico", "argentina", "latinoamerica", "asia", "emergentes",
                     "desarrollados-ex-eeuu", "global", "bitcoin", "ethereum", "bonos-eeuu", "dolar",
                     "inteligencia-artificial", "transicion-energetica"):
        assert esperado in ids, esperado


def test_el_catalogo_real_no_repite_proxies_activos():
    proxies = [g.proxy for g in cc.cargar().activos() if g.proxy]
    assert len(proxies) == len(set(proxies))


def test_los_temas_son_listas_curadas_con_aviso():
    for g in cc.cargar().grupos.values():
        if g.tipo == "tema":
            assert g.lista_curada and g.nota


def test_las_commodities_de_futuros_avisan_del_roll():
    cat = cc.cargar()
    for id_ in ("petroleo", "gas-natural", "soja", "metales-industriales"):
        assert "roll" in (cat.grupos[id_].nota or "")


def test_cada_categoria_exclusiva_la_reclama_un_solo_grupo():
    reclamado = {}
    for g in cc.cargar().activos():
        for eje, valores in g.eje_cartera:
            for v in valores:
                assert (eje, v) not in reclamado, (eje, v)
                reclamado[(eje, v)] = g.id


# -- validación --------------------------------------------------------------------------------

def test_un_grupo_invalido_se_descarta_y_el_resto_sigue():
    cat = cc.construir(_doc(
        _g("xlk"),
        _g("malo", tipo="inventado"),
        _g("sin-proxy", proxy=None),
        _g("ID Raro"),
        _g("rend", tipo_rendimiento="magico"),
    ))
    assert set(cat.grupos) == {"spy", "xlk"}
    assert len(cat.errores) == 4


def test_se_aplican_los_defaults_por_tipo():
    g = cc.construir(_doc(_g("xlk"))).grupos["xlk"]
    assert g.benchmark == "spy" and g.exclusivo is True and g.moneda == "USD"
    assert g.fuente == "Yahoo Finance" and g.tipo_rendimiento == "total" and g.vistas == ("sector",)


def test_un_grupo_puede_pisar_el_default():
    g = cc.construir(_doc(_g("xlk", exclusivo=False, benchmark="spy", vistas=["sector", "tema"]))).grupos["xlk"]
    assert g.exclusivo is False and g.vistas == ("sector", "tema")


def test_benchmark_inexistente_o_que_no_es_benchmark_descarta_el_grupo():
    cat = cc.construir(_doc(_g("a", benchmark="nada"), _g("b", benchmark="a"), _g("c", tipo="activo", benchmark=None)))
    assert set(cat.grupos) == {"spy"}


def test_descartar_un_grupo_arrastra_a_los_que_dependen_de_el():
    cat = cc.construir(_doc(_g("hijo", padre="malo"), _g("malo", tipo="inventado")))
    assert set(cat.grupos) == {"spy"}
    assert any("hijo" in e for e in cat.errores)


def test_ciclo_de_padres_se_descarta():
    cat = cc.construir(_doc(_g("a", padre="b"), _g("b", padre="a"), _g("ok")))
    assert set(cat.grupos) == {"spy", "ok"}


def test_categoria_exclusiva_repetida_descarta_al_segundo():
    cat = cc.construir(_doc(
        _g("a", eje_cartera=[{"eje": "sector", "valores": ["Salud"]}]),
        _g("b", eje_cartera=[{"eje": "sector", "valores": ["Salud", "Energía"]}]),
    ))
    assert "a" in cat.grupos and "b" not in cat.grupos


def test_eje_de_cartera_invalido_descarta_el_grupo():
    cat = cc.construir(_doc(_g("a", eje_cartera=[{"eje": "moneda", "valores": ["USD"]}])))
    assert "a" not in cat.grupos


def test_clave_de_cartera_desconocida_descarta_el_grupo():
    assert "a" not in cc.construir(_doc(_g("a", cartera={"color": ["rojo"]}))).grupos


def test_id_repetido_descarta_el_segundo():
    cat = cc.construir(_doc(_g("a"), _g("a", nombre="Otro")))
    assert cat.grupos["a"].nombre == "A"
    assert any("repetido" in e for e in cat.errores)


def test_sintetico_valido_sin_proxy():
    cat = cc.construir(_doc(
        _g("a"), _g("b"),
        _g("canasta", proxy=None, sintetico={"metodo": "equiponderado_semanal", "miembros": ["a", "b"]}),
    ))
    assert cat.grupos["canasta"].sintetico == {"metodo": "equiponderado_semanal", "miembros": ["a", "b"]}


def test_sintetico_invalido():
    cat = cc.construir(_doc(
        _g("a"), _g("b"),
        _g("poco", proxy=None, sintetico={"metodo": "equiponderado_semanal", "miembros": ["a"]}),
        _g("metodo", proxy=None, sintetico={"metodo": "magico", "miembros": ["a", "b"]}),
        _g("ambos", sintetico={"metodo": "equiponderado_semanal", "miembros": ["a", "b"]}),
        _g("canasta", proxy=None, sintetico={"metodo": "equiponderado_semanal", "miembros": ["a", "b"]}),
        _g("sobre-canasta", proxy=None, sintetico={"metodo": "equiponderado_semanal", "miembros": ["a", "canasta"]}),
    ))
    assert set(cat.grupos) == {"spy", "a", "b", "canasta"}


def test_fx_y_indice_local_se_validan():
    cat = cc.construir(_doc(
        _g("ok", tipo="pais", indice_local={"simbolo": "^BVSP", "moneda": "BRL"}, fx={"simbolo": "BRL=X", "cotizacion": "local_por_usd"}),
        _g("mep", tipo="pais", fx={"simbolo": None, "cotizacion": "mep"}),
        _g("sin-simbolo", tipo="pais", fx={"cotizacion": "usd_por_local"}),
        _g("cot", tipo="pais", fx={"simbolo": "X", "cotizacion": "raro"}),
    ))
    assert {"ok", "mep"} <= set(cat.grupos) and not {"sin-simbolo", "cot"} & set(cat.grupos)


def test_simbolos_incluye_proxy_indice_y_fx_pero_no_inactivos_ni_mep():
    cat = cc.construir(_doc(
        _g("br", tipo="pais", proxy="EWZ", indice_local={"simbolo": "^BVSP", "moneda": "BRL"},
           fx={"simbolo": "BRL=X", "cotizacion": "local_por_usd"}),
        _g("ar", tipo="pais", proxy="ARGT", indice_local={"simbolo": "^MERV", "moneda": "ARS"},
           fx={"simbolo": None, "cotizacion": "mep"}),
        _g("apagado", proxy="ALI=F", activo=False),
    ))
    s = cat.simbolos()
    assert set(s) == {"SPY", "EWZ", "^BVSP", "BRL=X", "ARGT", "^MERV"}
    assert s["^BVSP"].moneda == "BRL" and s["^BVSP"].rol == cc.ROL_INDICE
    assert s["BRL=X"].moneda == cc.MONEDA_FX and s["BRL=X"].rol == cc.ROL_FX
    assert s["EWZ"].moneda == "USD"


def test_un_grupo_inactivo_sigue_en_el_catalogo_pero_no_en_activos():
    cat = cc.construir(_doc(_g("apagado", activo=False)))
    assert "apagado" in cat.grupos and "apagado" not in {g.id for g in cat.activos()}


# -- períodos ----------------------------------------------------------------------------------

def test_periodos_validos_e_invalidos():
    cat = cc.construir(_doc(), {"periodos": [
        {"id": "a", "nombre": "A", "desde": "2020-02-19", "hasta": "2020-03-23"},
        {"id": "abierto", "nombre": "Abierto", "desde": "2022-10-12", "hasta": None},
        {"id": "al-reves", "nombre": "R", "desde": "2020-03-23", "hasta": "2020-02-19"},
        {"id": "mala-fecha", "nombre": "M", "desde": "ayer"},
        {"id": "a", "nombre": "Repetido", "desde": "2021-01-01", "hasta": "2021-02-01"},
    ]})
    assert [p["id"] for p in cat.periodos] == ["a", "abierto"]
    assert cat.periodos[0]["desde"] == date(2020, 2, 19) and cat.periodos[1]["hasta"] is None
    assert len(cat.errores) == 3


def test_los_periodos_reales_son_validos_y_ordenados():
    periodos = cc.cargar().periodos
    assert len(periodos) >= 6
    assert all(p["hasta"] is None or p["hasta"] > p["desde"] for p in periodos)


# -- archivos ----------------------------------------------------------------------------------

def test_archivo_ausente_equivale_a_catalogo_vacio(monkeypatch, tmp_path):
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(tmp_path / "no-existe.json"))
    cat = cc.cargar()
    assert cat.grupos == {} and cat.errores


def test_archivo_roto_equivale_a_catalogo_vacio(monkeypatch, tmp_path):
    roto = tmp_path / "roto.json"
    roto.write_text("{no es json", encoding="utf-8")
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(roto))
    cat = cc.cargar()
    assert cat.grupos == {} and any("ilegible" in e for e in cat.errores)


def test_se_relee_cuando_cambia_el_archivo(monkeypatch, tmp_path):
    ruta = tmp_path / "grupos.json"
    ruta.write_text(json.dumps(_doc(_g("a"))), encoding="utf-8")
    monkeypatch.setenv("CICLOS_CATALOGO_FILE", str(ruta))
    assert "a" in cc.cargar().grupos
    ruta.write_text(json.dumps(_doc(_g("b"))), encoding="utf-8")
    import os
    os.utime(ruta, (ruta.stat().st_atime + 10, ruta.stat().st_mtime + 10))
    assert "b" in cc.cargar().grupos and "a" not in cc.cargar().grupos
