"""Adaptador de Ciclos de mercado sobre series sintéticas guardadas en `serie_ohlcv`: panorama, detalle, relaciones
y países. Los estados de rotación salen de perfiles de fortaleza relativa de resultado conocido; los rendimientos se
verifican contra un cálculo independiente."""
import math
import random
from bisect import bisect_right
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, CiclosProxyEstado, IndiceMercado
from app.services import ciclos_analytics as ca
from app.services import ciclos_engine as eng

from .ciclos_helpers import (
    DOC, SEMANAS, benchmark, cargar_series, con_rs, dias_habiles, escribir_catalogo, fin, lunes_inicial, perfil, series_basicas,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    escribir_catalogo(tmp_path, monkeypatch)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    yield s
    s.close()


def _por_id(res):
    return {g["id"]: g for g in res["grupos"]}


def _cierre_en_o_antes(serie, objetivo):
    fechas = [f for f, _ in serie]
    return serie[bisect_right(fechas, objetivo) - 1][1]


def _mep_diario(db, base=1000.0, tasa=0.001):
    d0, d1 = lunes_inicial() - timedelta(days=10), fin() + timedelta(days=3)
    n = (d1 - d0).days
    db.add_all([IndiceMercado(fecha=d0 + timedelta(days=k), mep=base * (1 + tasa) ** k) for k in range(n + 1)])
    db.commit()
    return lambda f: base * (1 + tasa) ** (f - d0).days


# -- panorama ----------------------------------------------------------------------------------

def test_el_catalogo_de_prueba_es_valido(db):
    from app.services import ciclos_catalogo as cc
    assert cc.cargar().errores == []


def test_panorama_ubica_cada_sector_en_su_cuadrante(db):
    cargar_series(db, series_basicas())
    res = ca.panorama(db, "sector", periodo="6M")
    grupos = _por_id(res)
    assert {k: grupos[k]["rrg"]["actual"]["cuadrante"] for k in ("tecnologia", "salud", "energia", "consumo-basico")} == {
        "tecnologia": "leading", "salud": "lagging", "energia": "weakening", "consumo-basico": "improving"}
    assert res["filtros"]["benchmark"] == "estados-unidos" and res["benchmark"]["proxy"] == "SPY"
    assert res["cobertura"]["con_rotacion"] == 4 and res["cobertura"]["sin_datos"] == []
    assert "estados-unidos" not in grupos                              # el benchmark no se mide contra sí mismo


def test_la_trayectoria_termina_en_el_punto_actual_y_se_limita(db):
    cargar_series(db, series_basicas())
    g = _por_id(ca.panorama(db, "sector", periodo="1A"))["tecnologia"]["rrg"]
    assert g["trayectoria"][-1] == g["actual"] and 2 <= len(g["trayectoria"]) <= 13
    corta = _por_id(ca.panorama(db, "sector", periodo="3M"))["tecnologia"]["rrg"]["trayectoria"]
    assert len(corta) == 13 and corta[-1]["fecha"] == g["actual"]["fecha"]


def test_meta_dice_fuente_fecha_periodo_moneda_benchmark_y_tipo(db):
    cargar_series(db, series_basicas())
    meta = ca.panorama(db, "sector", periodo="6M")["meta"]
    assert "Yahoo Finance" in meta["fuente"] and meta["moneda"] == "USD" and meta["tipo_rendimiento"] == "total"
    assert meta["ultima_fecha_datos"] == fin() and meta["periodo"]["hasta"] == fin()
    assert meta["periodo"]["desde"] == eng.restar_meses(fin(), 6)
    assert meta["benchmark"] == {"id": "estados-unidos", "nombre": "Estados Unidos", "proxy": "SPY"}
    assert any("proxy" in x for x in meta["limitaciones"]) and any("pasado" in x for x in meta["limitaciones"])


def test_los_rendimientos_coinciden_con_un_calculo_independiente(db):
    series = series_basicas()
    cargar_series(db, series)
    res = ca.panorama(db, "sector")
    tec, spy = series["XLK"], series["SPY"]
    for h, meses in (("3M", 3), ("1A", 12), ("3A", 36)):
        desde = eng.restar_meses(fin(), meses)
        ra = _cierre_en_o_antes(tec, fin()) / _cierre_en_o_antes(tec, desde) - 1
        rb = _cierre_en_o_antes(spy, fin()) / _cierre_en_o_antes(spy, desde) - 1
        celda = _por_id(res)["tecnologia"]["rendimientos"][h]
        assert celda["absoluto"] == pytest.approx(ra) and celda["relativo"] == pytest.approx((1 + ra) / (1 + rb) - 1)
    assert res["fechas_horizontes"]["1A"] == {"desde": eng.restar_meses(fin(), 12), "hasta": fin()}


def test_5A_y_10A_no_aparecen_sin_cobertura_real(db):
    cargar_series(db, series_basicas())
    res = ca.panorama(db, "sector")
    assert res["horizontes"] == ["1M", "3M", "6M", "1A", "3A"]
    celda = _por_id(res)["tecnologia"]["rendimientos"]["5A"]
    assert celda["absoluto"] is None and celda["motivo"] == "sin datos suficientes"


def test_un_grupo_sin_datos_se_muestra_con_su_motivo(db):
    series = series_basicas()
    del series["XLP"]
    cargar_series(db, series)
    db.add(CiclosProxyEstado(simbolo="XLP", estado="no_encontrado", n_barras=0, error="Yahoo no devolvió datos"))
    db.commit()
    res = ca.panorama(db, "sector")
    g = _por_id(res)["consumo-basico"]
    assert g["rrg"]["estado"] == "sin_datos" and "Yahoo no devolvió datos para XLP" in g["rrg"]["motivo"]
    assert res["cobertura"]["sin_datos"][0]["id"] == "consumo-basico" and res["cobertura"]["con_rotacion"] == 3
    assert any("sin datos" in a for a in res["meta"]["advertencias"])


def test_un_grupo_que_nunca_se_descargo_lo_dice(db):
    series = series_basicas()
    del series["XLP"]
    cargar_series(db, series)
    motivo = _por_id(ca.panorama(db, "sector"))["consumo-basico"]["rrg"]["motivo"]
    assert "todavía no se descargó XLP" in motivo


def test_historia_corta_queda_como_insuficiente_y_no_se_inventa(db):
    series = series_basicas()
    series["XLK"] = series["XLK"][-5 * 20:]                      # 20 semanas
    cargar_series(db, series)
    res = ca.panorama(db, "sector")
    g = _por_id(res)["tecnologia"]
    assert g["rrg"]["estado"] == "datos_insuficientes" and g["rrg"]["actual"] is None and g["rrg"]["trayectoria"] == []
    assert res["cobertura"]["insuficientes"][0]["id"] == "tecnologia"
    assert g["rendimientos"]["1A"]["absoluto"] is None


def test_un_grupo_desactualizado_no_se_dibuja_como_actual(db):
    series = series_basicas()
    series["XLK"] = series["XLK"][:-5 * 8]                       # termina 8 semanas antes
    cargar_series(db, series)
    res = ca.panorama(db, "sector")
    g = _por_id(res)["tecnologia"]["rrg"]
    assert g["estado"] == "desactualizado" and g["actual"] is None and g["trayectoria"] == []
    assert res["cobertura"]["desactualizados"][0]["id"] == "tecnologia"


def test_sin_benchmark_con_datos_no_se_calcula_nada(db):
    series = series_basicas()
    del series["SPY"]
    cargar_series(db, series)
    res = ca.panorama(db, "sector")
    assert res["grupos"] == [] and "no tiene datos" in res["motivo"] and res["meta"]["advertencias"]


def test_benchmark_elegido_y_filtro_de_grupos(db):
    cargar_series(db, series_basicas())
    res = ca.panorama(db, "sector", benchmark="global", grupos=("tecnologia", "salud"))
    assert [g["id"] for g in res["grupos"]] == ["tecnologia", "salud"]
    assert res["filtros"]["benchmark"] == "global" and res["meta"]["benchmark"]["proxy"] == "ACWI"
    assert any("habitual" in a for a in res["meta"]["advertencias"])


@pytest.mark.parametrize("kw, mensaje", [
    ({"tipo": "inventado"}, "tipo inválido"), ({"periodo": "9M"}, "período inválido"), ({"moneda": "EUR"}, "moneda inválida"),
    ({"ventana": 1}, "ventana"), ({"grupos": ("europa",)}, "no son de tipo"),
])
def test_panorama_valida_los_parametros(db, kw, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        ca.panorama(db, **{"tipo": "sector", **kw})


def test_benchmark_inexistente_es_not_found(db):
    with pytest.raises(ca.NoEncontrado):
        ca.panorama(db, "sector", benchmark="tecnologia")           # existe, pero no es un benchmark
    with pytest.raises(ca.NoEncontrado):
        ca.panorama(db, "sector", benchmark="nada")


def test_el_rendimiento_en_pesos_aplica_el_mep_de_cada_fecha_y_la_rotacion_no_cambia(db):
    series = series_basicas()
    cargar_series(db, series)
    mep = _mep_diario(db)
    usd = _por_id(ca.panorama(db, "sector", moneda="USD"))["tecnologia"]
    ars = ca.panorama(db, "sector", moneda="ARS")
    g = _por_id(ars)["tecnologia"]
    desde = eng.restar_meses(fin(), 12)
    esperado = (_cierre_en_o_antes(series["XLK"], fin()) * mep(fin())) / (_cierre_en_o_antes(series["XLK"], desde) * mep(desde)) - 1
    assert g["rendimientos"]["1A"]["absoluto"] == pytest.approx(esperado, rel=5e-3)
    assert g["rendimientos"]["1A"]["absoluto"] > usd["rendimientos"]["1A"]["absoluto"]
    assert g["rrg"]["actual"] == usd["rrg"]["actual"]                      # los cuadrantes se calculan en dólares
    assert ars["meta"]["moneda"] == "ARS" and any("en dólares" in a for a in ars["meta"]["advertencias"])


def test_en_pesos_sin_mep_no_hay_rendimientos_pero_si_rotacion(db):
    cargar_series(db, series_basicas())
    res = ca.panorama(db, "sector", moneda="ARS")
    g = _por_id(res)["tecnologia"]
    assert g["rendimientos"]["1A"]["absoluto"] is None and g["rrg"]["estado"] == "ok"
    assert any("MEP" in a for a in res["meta"]["advertencias"])


def test_una_fecha_sin_mep_se_descarta_no_se_completa(db):
    series = series_basicas()
    cargar_series(db, series)
    f0 = fin() - timedelta(days=200)
    db.add_all([IndiceMercado(fecha=f0 + timedelta(days=k), mep=1000.0 + k) for k in range(100)])    # sólo cubre 100 días
    db.commit()
    res = ca.panorama(db, "sector", moneda="ARS")
    assert _por_id(res)["tecnologia"]["rendimientos"]["1A"]["absoluto"] is None
    assert any("descartaron" in a for a in res["meta"]["advertencias"])


def test_cambios_de_liderazgo_confirmados_recientes(db):
    series = series_basicas()
    # Salud: sube, se estanca y cae durante 14 semanas: el paso a Lagging ocurrió hace unas 14 semanas.
    series["XLV"] = con_rs(series["SPY"], perfil(("plano", SEMANAS - 70), ("crece", 1.015, 30), ("plano", 26), ("crece", 0.985, 14)))
    cargar_series(db, series)
    cambios = ca.panorama(db, "sector")["cambios_liderazgo"]
    salud = [c for c in cambios if c["grupo_id"] == "salud"]
    assert salud and salud[0]["a"] == "lagging" and salud[0]["de"] == "weakening" and salud[0]["semanas"] >= 3
    assert all((fin() - c["desde"]).days <= 26 * 7 for c in cambios)
    assert [c["desde"] for c in cambios] == sorted((c["desde"] for c in cambios), reverse=True)


def test_un_cambio_viejo_no_figura_entre_los_recientes(db):
    series = series_basicas()
    # La misma historia pero con la caída de 38 semanas: el paso a Lagging fue hace ~37 semanas (> 26).
    series["XLV"] = con_rs(series["SPY"], perfil(("plano", SEMANAS - 80), ("crece", 1.015, 30), ("plano", 12), ("crece", 0.985, 38)))
    cargar_series(db, series)
    res = ca.panorama(db, "sector")
    assert not [c for c in res["cambios_liderazgo"] if c["grupo_id"] == "salud"]
    assert _por_id(res)["salud"]["rrg"]["ultimo_cambio"]["cuadrante"] == "lagging"      # el cambio existe, sólo que no es reciente


def test_el_regimen_macro_no_se_inventa(db):
    cargar_series(db, series_basicas())
    r = ca.panorama(db, "sector")["regimen"]
    assert r["estado"] == "no_disponible" and r["escenario"] is None and any("Producción industrial" in f for f in r["falta"])
    assert "Todavía no se descargaron" in r["aclaracion"] and all(e["actual"] is False for e in r["escenarios"])


def test_los_temas_y_commodities_se_listan_por_su_tipo(db):
    series = series_basicas()
    series.update({"AIQ": series["XLK"], "GLD": series["XLV"], "DBC": series["XLE"]})
    cargar_series(db, series)
    assert [g["id"] for g in ca.panorama(db, "tema")["grupos"]] == ["inteligencia-artificial"]
    assert [g["id"] for g in ca.panorama(db, "commodity")["grupos"]] == ["commodities-amplios", "oro"]
    assert [g["id"] for g in ca.panorama(db, "activo")["grupos"]] == ["oro"]       # `vistas`: el oro también es un activo
    g = _por_id(ca.panorama(db, "commodity"))["commodities-amplios"]
    assert "roll" in g["nota"]


def test_mezclar_rendimiento_total_y_de_precio_se_advierte(db, tmp_path, monkeypatch):
    import json
    doc = json.loads(json.dumps(DOC))
    for g in doc["grupos"]:
        if g["id"] == "salud":
            g["tipo_rendimiento"] = "precio"
    escribir_catalogo(tmp_path, monkeypatch, doc)
    cargar_series(db, series_basicas())
    meta = ca.panorama(db, "sector")["meta"]
    assert meta["tipo_rendimiento"] == "mixto" and any("no es homogénea" in a for a in meta["advertencias"])


# -- detalle -----------------------------------------------------------------------------------

def test_detalle_normaliza_a_base_100_con_benchmark_y_relativo(db):
    cargar_series(db, series_basicas())
    d = ca.detalle(db, "tecnologia", horizonte="1A")
    assert d["estado"] == "ok" and d["benchmark"]["id"] == "estados-unidos"
    f0, f1 = d["filas"][0], d["filas"][-1]
    assert f0["tecnologia"] == 100.0 and f0["estados-unidos"] == 100.0 and f0["relativo"] == pytest.approx(100.0)
    assert f1["relativo"] == pytest.approx(100.0 * f1["tecnologia"] / f1["estados-unidos"])
    assert d["rango"]["desde_pedido"] == eng.restar_meses(fin(), 12) and d["rango"]["recortado"] is False
    assert [s["rol"] for s in d["series"]] == ["grupo", "benchmark"]
    assert d["rotacion"]["transiciones"] is not None and d["rotacion"]["puntos"]
    assert d["meta"]["periodo"] == {"desde": eng.restar_meses(fin(), 12), "hasta": fin()}


def test_detalle_con_grupos_adicionales(db):
    cargar_series(db, series_basicas())
    d = ca.detalle(db, "tecnologia", con=("salud", "energia"), horizonte="1A")
    assert [s["rol"] for s in d["series"]] == ["grupo", "benchmark", "adicional", "adicional"]
    assert {"tecnologia", "salud", "energia", "estados-unidos"} <= set(d["filas"][0])
    assert d["periodo_analizado"]["grupos"]["salud"]["relativo"] is not None
    with pytest.raises(ValueError, match="hasta 5"):
        ca.detalle(db, "tecnologia", con=("a", "b", "c", "d", "e", "f"))
    with pytest.raises(ca.NoEncontrado):
        ca.detalle(db, "tecnologia", con=("nada",))


def test_detalle_5A_sin_cobertura_se_recorta_y_lo_avisa(db):
    series = series_basicas()
    cargar_series(db, series)
    d = ca.detalle(db, "tecnologia", horizonte="5A")
    assert d["rango"]["recortado"] is True and 0 <= (d["rango"]["desde_efectivo"] - series["XLK"][0][0]).days < 7
    assert any("empieza antes de que haya datos" in a for a in d["meta"]["advertencias"])
    assert d["rango"]["paso"] == "S"                                  # más de tres años: gráfico semanal


def test_detalle_de_un_periodo_historico_del_catalogo_usa_sus_fechas_exactas(db):
    cargar_series(db, series_basicas())
    d = ca.detalle(db, "tecnologia", periodo_id="tramo")
    assert d["rango"]["desde_pedido"] == fin() - timedelta(days=300) and d["rango"]["hasta_pedido"] == fin() - timedelta(days=100)
    assert "Un tramo" in d["rango"]["etiqueta"]
    assert d["periodo_analizado"]["desde"] == d["rango"]["desde_pedido"] and d["periodo_analizado"]["hasta"] == d["rango"]["hasta_pedido"]
    with pytest.raises(ca.NoEncontrado):
        ca.detalle(db, "tecnologia", periodo_id="nada")


def test_detalle_con_fechas_libres_y_validaciones(db):
    cargar_series(db, series_basicas())
    d = ca.detalle(db, "tecnologia", desde=fin() - timedelta(days=100), hasta=fin() - timedelta(days=10))
    assert d["rango"]["etiqueta"] == "fechas elegidas"
    with pytest.raises(ValueError, match="anterior"):
        ca.detalle(db, "tecnologia", desde=fin(), hasta=fin() - timedelta(days=10))
    with pytest.raises(ValueError, match="horizonte"):
        ca.detalle(db, "tecnologia", horizonte="7A")
    with pytest.raises(ValueError, match="moneda"):
        ca.detalle(db, "tecnologia", moneda="BRL")


def test_detalle_de_grupos_inexistentes_o_apagados(db):
    with pytest.raises(ca.NoEncontrado):
        ca.detalle(db, "nada")
    with pytest.raises(ca.NoEncontrado):
        ca.detalle(db, "apagado")


def test_detalle_sin_datos_dice_por_que(db):
    cargar_series(db, {"SPY": benchmark()})
    d = ca.detalle(db, "tecnologia")
    assert d["estado"] == "sin_datos" and "XLK" in d["motivo"] and d["filas"] == [] and d["rotacion"] is None
    assert any("no tiene datos" in a for a in d["meta"]["advertencias"])


def test_detalle_de_un_grupo_que_es_benchmark_se_mide_contra_el_otro(db):
    cargar_series(db, series_basicas())
    d = ca.detalle(db, "estados-unidos")
    assert d["benchmark"]["id"] == "global" and d["estado"] == "ok"
    assert ca.detalle(db, "global")["benchmark"]["id"] == "estados-unidos"


def test_detalle_trae_hijos_y_regla_de_pertenencia(db):
    cargar_series(db, series_basicas())
    d = ca.detalle(db, "tecnologia")
    assert [h["id"] for h in d["grupo"]["hijos"]] == ["semiconductores"]
    assert d["grupo"]["pertenencia"] == {"exacta_sector": ["Tecnología"]}


def test_detalle_en_pesos_convierte_las_series_pero_no_la_rotacion(db):
    cargar_series(db, series_basicas())
    mep = _mep_diario(db)
    usd, ars = ca.detalle(db, "tecnologia", horizonte="1A"), ca.detalle(db, "tecnologia", horizonte="1A", moneda="ARS")
    assert ars["rotacion"]["actual"] == usd["rotacion"]["actual"]
    f0 = ars["filas"][0]["fecha"]
    f1 = ars["filas"][-1]["fecha"]
    assert ars["filas"][-1]["tecnologia"] / usd["filas"][-1]["tecnologia"] == pytest.approx(mep(f1) / mep(f0), rel=5e-3)


# -- relaciones --------------------------------------------------------------------------------

def _semanal(retornos, base=100.0, semanas=130):
    """Serie sólo de viernes, de `semanas` datos, a partir de retornos semanales."""
    viernes = [fin() - timedelta(days=7 * (semanas - 1 - i)) for i in range(semanas)]
    precios, p = [], base
    for i in range(semanas):
        if i:
            p *= 1 + retornos[i - 1]
        precios.append(p)
    return list(zip(viernes, precios))


RETS = [0.02 * math.sin(i) for i in range(1, 140)]


def test_correlaciones_positiva_negativa_y_muestra(db):
    cargar_series(db, {"XLK": _semanal(RETS), "XLV": _semanal(RETS), "XLE": _semanal([-r for r in RETS])})
    res = ca.correlaciones(db, ids=("tecnologia", "salud", "energia"), periodo="1A")
    assert res["estado"] == "ok" and res["frecuencia"] == "semanal" and res["ids"] == ["tecnologia", "salud", "energia"]
    m = res["matriz"]
    assert m[0][1] == pytest.approx(1.0) and m[0][2] == pytest.approx(-1.0) and m[0][0] == 1.0
    par = res["pares"][0]
    assert par["n_obs"] >= 50 and res["n_periodos"] >= 50 and res["periodo_efectivo"]["hasta"] == fin()
    assert any("causalidad" in a for a in res["meta"]["advertencias"]) and res["meta"]["moneda"] == "USD"
    assert res["nombres"]["tecnologia"] == "Tecnología" and res["escala"]


def test_correlaciones_con_pocas_observaciones_no_dan_valor(db):
    cargar_series(db, {"XLK": _semanal(RETS), "XLV": _semanal(RETS)})
    res = ca.correlaciones(db, ids=("tecnologia", "salud"), periodo="3M", frecuencia="semanal")
    assert res["pares"][0]["n_obs"] <= 13
    cargar_series(db, {"XLE": _semanal(RETS, semanas=6)})
    corto = ca.correlaciones(db, ids=("tecnologia", "energia"), periodo="1A")
    assert corto["pares"][0]["valor"] is None and corto["pares"][0]["estado"] == "datos_insuficientes"
    assert any("sin valor" in a for a in corto["meta"]["advertencias"])


def test_correlaciones_deja_visibles_los_grupos_sin_datos(db):
    cargar_series(db, {"XLK": _semanal(RETS), "XLV": _semanal(RETS)})
    res = ca.correlaciones(db, ids=("tecnologia", "salud", "energia"), periodo="1A")
    assert [x["id"] for x in res["sin_datos"]] == ["energia"] and res["ids"] == ["tecnologia", "salud"]
    solo = ca.correlaciones(db, ids=("tecnologia", "energia"), periodo="1A")
    assert solo["estado"] == "datos_insuficientes" and solo["matriz"] is None


def test_correlaciones_valida(db):
    with pytest.raises(ValueError, match="entre 2 y"):
        ca.correlaciones(db, ids=("tecnologia",))
    with pytest.raises(ValueError, match="período inválido"):
        ca.correlaciones(db, ids=("tecnologia", "salud"), periodo="5A")
    with pytest.raises(ValueError, match="frecuencia"):
        ca.correlaciones(db, ids=("tecnologia", "salud"), frecuencia="mensual")
    with pytest.raises(ca.NoEncontrado):
        ca.correlaciones(db, ids=("tecnologia", "nada"))
    with pytest.raises(ValueError, match="entre 2 y 15"):
        ca.correlaciones(db, ids=tuple(f"g{i}" for i in range(16)))


def test_correlacion_diaria_usa_las_ruedas_del_sp500(db):
    cargar_series(db, series_basicas())
    res = ca.correlaciones(db, ids=("tecnologia", "salud"), periodo="3M")
    assert res["frecuencia"] == "diaria" and res["n_periodos"] >= 50 and res["pares"][0]["n_obs"] >= 50
    cargar_series(db, {"SPY": []})
    # sin la serie de referencia no se puede fijar la grilla diaria
    from sqlalchemy import delete
    from app.database import BarraOHLCV
    db.execute(delete(BarraOHLCV).where(BarraOHLCV.ticker == "SPY@BENCH"))
    db.commit()
    with pytest.raises(ValueError, match="serie de referencia"):
        ca.correlaciones(db, ids=("tecnologia", "salud"), periodo="3M")


def test_correlaciones_por_defecto_usa_el_conjunto_del_pedido_que_exista_en_el_catalogo(db):
    cargar_series(db, series_basicas())
    res = ca.correlaciones(db, periodo="1A")
    assert set(res["ids"]) == {"tecnologia", "energia", "consumo-basico"}
    assert {"semiconductores", "oro", "emergentes", "brasil"} <= {x["id"] for x in res["sin_datos"]}   # del conjunto, sin series


def test_desfases_recupera_el_atraso_conocido(db):
    rnd = random.Random(5)
    r = [rnd.uniform(-0.03, 0.03) for _ in range(139)]
    b_rets = [rnd.uniform(-0.03, 0.03) for _ in range(3)] + r[:-3]
    cargar_series(db, {"GLD": _semanal(r), "ACWI": _semanal(b_rets)})
    res = ca.desfases(db, a="oro", b="global", meses=36)
    assert res["estado"] == "ok" and res["mejor"]["desfase_semanas"] == 3 and res["mejor"]["valor"] > 0.95
    assert len(res["desfases"]) == 17 and res["banda_azar"] == pytest.approx(1.96 / math.sqrt(res["desfases"][8]["n_obs"]))
    assert any("azar" in a for a in res["meta"]["advertencias"]) and "no una predicción" in res["lectura"]
    assert res["nombres"] == {"oro": "Oro", "global": "Global"}


def test_desfases_valida_y_dice_cuando_no_alcanza(db):
    assert ca.desfases(db, a="oro", b="oro")["estado"] == "datos_insuficientes"
    cargar_series(db, {"GLD": _semanal(RETS)})
    assert ca.desfases(db, a="oro", b="global")["sin_datos"][0]["id"] == "global"
    with pytest.raises(ValueError, match="entre 12 y 120"):
        ca.desfases(db, a="oro", b="global", meses=6)
    with pytest.raises(ca.NoEncontrado):
        ca.desfases(db, a="oro", b="nada")


def test_comparacion_mismo_periodo_relativo_y_series_normalizadas(db):
    cargar_series(db, series_basicas())
    res = ca.comparacion(db, ids=("tecnologia", "salud"), benchmark="estados-unidos")
    assert res["estado"] == "ok" and res["periodo"]["ajustado"] is False and res["periodo"]["desde"] == eng.restar_meses(fin(), 36)
    tec = next(g for g in res["grupos"] if g["id"] == "tecnologia")
    assert tec["retorno"] is not None and tec["relativo"] is not None and tec["volatilidad"]["estado"] == "ok"
    assert tec["rotacion_actual"]["cuadrante"] == "leading" and res["filas"][0]["tecnologia"] == 100.0
    assert res["meta"]["benchmark"]["proxy"] == "SPY" and res["paso"] == "D"


def test_comparacion_acorta_al_grupo_con_menos_historia_y_lo_avisa(db):
    series = series_basicas()
    series["XLV"] = series["XLV"][-5 * 60:]                    # sólo 60 semanas
    cargar_series(db, series)
    res = ca.comparacion(db, ids=("tecnologia", "salud"))
    assert res["periodo"]["ajustado"] is True and res["periodo"]["desde"] == series["XLV"][0][0]
    assert any("se acortó" in a for a in res["meta"]["advertencias"])


def test_comparacion_con_un_grupo_sin_datos_y_un_periodo_del_catalogo(db):
    series = series_basicas()
    del series["XLE"]
    cargar_series(db, series)
    res = ca.comparacion(db, ids=("tecnologia", "salud", "energia"), periodo_id="tramo")
    assert [x["id"] for x in res["sin_datos"]] == ["energia"] and len(res["grupos"]) == 3
    assert next(g for g in res["grupos"] if g["id"] == "energia")["retorno"] is None
    assert res["etiqueta_periodo"].startswith("período") and res["periodos"][0]["id"] == "tramo"


def test_comparacion_valida(db):
    with pytest.raises(ValueError, match="entre 2 y 6"):
        ca.comparacion(db, ids=("tecnologia",))
    assert ca.comparacion(db, ids=("tecnologia", "salud"))["estado"] == "sin_datos"


# -- países ------------------------------------------------------------------------------------

def _crece_diaria(g, base=100.0):
    return [(d, base * g ** k) for k, d in enumerate(dias_habiles())]


def _esperado(serie, meses):
    desde = eng.restar_meses(serie[-1][0], meses)
    return _cierre_en_o_antes(serie, serie[-1][0]) / _cierre_en_o_antes(serie, desde) - 1


def test_pais_separa_etf_en_usd_indice_local_y_tipo_de_cambio(db):
    proxy, indice, fx = _crece_diaria(1.0005), _crece_diaria(1.0008, 1000), _crece_diaria(1.0003, 5)
    cargar_series(db, {"EWZ": proxy, "^BVSP": indice, "BRL=X": fx, "ACWI": benchmark(0.0003)})
    res = ca.pais(db, "brasil", meses=12)
    d = res["descomposicion"]["1A"]
    r_proxy, r_local, r_fx = _esperado(proxy, 12), _esperado(indice, 12), _esperado(fx, 12)
    assert d["proxy_usd"] == pytest.approx(r_proxy) and d["indice_local"] == pytest.approx(r_local)
    assert d["efecto_fx"] == pytest.approx(1 / (1 + r_fx) - 1)
    assert d["indice_local_usd"] == pytest.approx((1 + r_local) / (1 + r_fx) - 1)
    # La tabla guarda 6 decimales: la diferencia de dos números casi iguales necesita tolerancia absoluta.
    assert d["diferencia_vehiculo"] == pytest.approx(r_proxy - d["indice_local_usd"], abs=1e-7) and d["completa"] is True
    assert set(res["descomposicion"]) == {"3M", "6M", "1A", "3A"}
    assert any("no equivale" in a for a in res["meta"]["advertencias"])
    assert res["moneda_local_vs_usd"][0]["valor"] == 100.0 and res["moneda_local_vs_usd"][-1]["valor"] < 100.0   # el real se depreció
    assert [c["id"] for c in res["comparaciones"]] == [] and res["macro"]["estado"] == "no_disponible"


def test_pais_con_el_indice_local_desactualizado_o_sin_fx_no_estima(db):
    proxy = _crece_diaria(1.0005)
    cargar_series(db, {"EWZ": proxy, "^BVSP": _crece_diaria(1.0008, 1000)[:-5 * 8], "ACWI": benchmark(0.0003)})
    res = ca.pais(db, "brasil", meses=12)
    d = res["descomposicion"]["1A"]
    assert d["indice_local"] is None and d["efecto_fx"] is None and d["completa"] is False
    assert "desactualizado" in " ".join(res["meta"]["advertencias"]) and d["proxy_usd"] is not None
    assert d["motivos"]["efecto_fx"] == "el tipo de cambio no tiene datos"
    assert "último dato" in d["motivos"]["indice_local"]


def test_argentina_usa_el_mep_de_la_app_como_tipo_de_cambio_y_trae_macro(db):
    proxy, merv = _crece_diaria(1.0005), _crece_diaria(1.002, 1000)
    cargar_series(db, {"ARGT": proxy, "^MERV": merv, "ACWI": benchmark(0.0003)}, moneda="USD")
    mep = _mep_diario(db, 1000.0, 0.001)
    d = ca.pais(db, "argentina", meses=12)["descomposicion"]["1A"]
    hasta = proxy[-1][0]
    r_mep = mep(hasta) / mep(eng.restar_meses(hasta, 12)) - 1
    assert d["efecto_fx"] == pytest.approx(1 / (1 + r_mep) - 1, rel=5e-3) and d["completa"] is True
    macro = ca.pais(db, "argentina")["macro"]
    assert macro["estado"] == "parcial" and macro["ultimo"]["mep"]["valor"] > 0 and "INDEC" in macro["motivo"]


def test_pais_relacion_con_commodities_se_marca_como_correlacion_observada(db):
    cargar_series(db, {"EWZ": _semanal(RETS[::-1]), "DBC": _semanal(RETS)})
    rel = ca.pais(db, "brasil")["relacion_commodities"]
    assert rel["valor"] is not None and rel["n_obs"] >= 100 and "no una medida de exposición" in rel["lectura"]


def test_pais_valida_y_maneja_grupos_sin_datos(db):
    with pytest.raises(ValueError, match="meses"):
        ca.pais(db, "brasil", meses=5)
    with pytest.raises(ca.NoEncontrado, match="no es un país"):
        ca.pais(db, "tecnologia")
    sin = ca.pais(db, "brasil")
    assert sin["estado"] == "sin_datos" and "EWZ" in sin["motivo"] and sin["descomposicion"] is None


def test_la_ficha_ofrece_las_comparaciones_regionales_del_catalogo(db):
    cargar_series(db, {"VGK": _crece_diaria(1.0004), "ACWI": benchmark(0.0003)})
    res = ca.pais(db, "europa")
    assert [c["id"] for c in res["comparaciones"]] == ["eeuu-europa"]


# -- estados para la cartera -------------------------------------------------------------------

def test_estados_de_rotacion_incluye_a_los_benchmarks_midiendolos_entre_si(db):
    cargar_series(db, series_basicas())
    est = ca.estados_de_rotacion(db)
    assert est["tecnologia"]["cuadrante"] == "leading" and est["tecnologia"]["benchmark"] == "estados-unidos"
    assert est["estados-unidos"]["benchmark"] == "global" and est["global"]["benchmark"] == "estados-unidos"
    assert est["europa"]["estado"] == "sin_datos"
    elegido = ca.estados_de_rotacion(db, benchmark="global")
    assert elegido["tecnologia"]["benchmark"] == "global" and elegido["global"]["benchmark"] == "estados-unidos"
