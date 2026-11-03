"""Cruce de Ciclos de mercado con la cartera: exposición por estado del ciclo, instrumentos de un grupo y simulador
de rotación. Cartera de juguete con un CEDEAR y su variante en pesos (un solo emisor), una posición sin sector ni país,
un tema superpuesto y un commodity."""
import re

import pytest
from app.database import Base, MovimientoInversion, PrecioInstrumento, RebalanceoObjetivo
from app.services import ciclos_analytics as ca
from app.services import ciclos_cartera as cart
from app.services.cache import limpiar_cache
from app.services.inversiones_analytics import get_exposicion

from .ciclos_helpers import TOTAL_CARTERA, cartera_de_prueba, pos

PROHIBIDO = re.compile(r"compr\w*|vend\w*|recomend\w*|conviene", re.IGNORECASE)


@pytest.fixture
def sesion(tmp_path, monkeypatch):
    return cartera_de_prueba(tmp_path, monkeypatch)


@pytest.fixture
def db(sesion):
    s = sesion()
    yield s
    s.close()


TOTAL = TOTAL_CARTERA


def _dim(res, nombre):
    return next(d for d in res["dimensiones"] if d["dimension"] == nombre)


def _item(dim, etiqueta):
    return next(i for i in dim["items"] if i["etiqueta"] == etiqueta)


def _eje(sim, nombre):
    return next(e for e in sim["ejes"] if e["eje"] == nombre)


# -- exposición --------------------------------------------------------------------------------

def test_los_ejes_coinciden_con_exposicion_y_suman_100(db):
    res = cart.exposicion(None, db)
    assert res["total_usd"] == pytest.approx(TOTAL)
    exp = {e["eje"]: e["items"] for e in get_exposicion(None, db)["ejes"]}
    for nombre in ("Sector", "Región", "País"):
        mio = {i["etiqueta"]: (i["valor_usd"], i["porcentaje"]) for i in _dim(res, nombre)["items"]}
        assert mio == {i["etiqueta"]: (i["valor_usd"], i["porcentaje"]) for i in exp[nombre]}
        assert sum(i["porcentaje"] for i in _dim(res, nombre)["items"]) == pytest.approx(100.0, abs=0.05)
        assert sum(p["porcentaje"] for p in _dim(res, nombre)["por_cuadrante"]) == pytest.approx(100.0, abs=0.05)


def test_el_capital_se_reparte_por_cuadrante_del_sector(db):
    sector = _dim(cart.exposicion(None, db), "Sector")
    tec = _item(sector, "Tecnología")
    assert tec["valor_usd"] == 1500.0 and tec["grupo_id"] == "tecnologia" and tec["cuadrante"] == "leading"
    assert _item(sector, "Consumo básico")["cuadrante"] == "improving"
    pesos = {p["cuadrante"]: p["porcentaje"] for p in sector["por_cuadrante"]}
    assert pesos["leading"] == pytest.approx(1500 / TOTAL * 100, abs=0.01) and pesos["improving"] == pytest.approx(700 / TOTAL * 100, abs=0.01)
    assert pesos["weakening"] == 0.0 and pesos["lagging"] == 0.0
    assert pesos["sin_estado"] == pytest.approx(700 / TOTAL * 100, abs=0.01)         # Materias primas + Financiero + Sin sector
    resumen = cart.exposicion(None, db)["resumen"]
    assert resumen["en_leading_pct"] == pesos["leading"] and resumen["sin_estado_pct"] == pesos["sin_estado"]
    assert "no es una recomendación" in resumen["lectura"]


def test_lo_que_no_tiene_estado_dice_por_que_y_no_se_descarta(db):
    sector = _dim(cart.exposicion(None, db), "Sector")
    sin_sector = _item(sector, "Sin sector")
    assert sin_sector["residual"] and sin_sector["rubro"] == "sin_clasificar" and sin_sector["valor_usd"] == 300.0
    assert _item(sector, "Financiero")["rubro"] == "sin_grupo" and "catálogo" in _item(sector, "Financiero")["motivo_sin_estado"]
    motivos = {d["motivo"]: d["porcentaje"] for d in sector["sin_estado_detalle"]}
    assert set(motivos) == {"sin_clasificar", "sin_grupo"}
    pais = _dim(cart.exposicion(None, db), "País")
    arg = _item(pais, "Argentina")
    assert arg["grupo_id"] == "argentina" and arg["rubro"] == "sin_datos"            # hay grupo pero no hay serie bajada


def test_posiciones_sin_clasificar_se_listan(db):
    sc = {s["ticker"]: s for s in cart.exposicion(None, db)["sin_clasificar"]}
    assert "NOSEC" in sc and sc["NOSEC"]["valor_usd"] == 300.0 and "sector" in sc["NOSEC"]["faltan"] and "país" in sc["NOSEC"]["faltan"]
    assert sc["NOSEC"]["porcentaje"] == pytest.approx(300 / TOTAL * 100, abs=0.01)


def test_industrias_commodities_y_temas_se_superponen_pero_no_se_suman(db):
    res = cart.exposicion(None, db)
    sup = {s["grupo_id"]: s for s in res["superpuestas"]}
    nvda = round(500 / TOTAL * 100, 2)
    assert sup["semiconductores"]["porcentaje"] == nvda and sup["inteligencia-artificial"]["porcentaje"] == nvda
    assert sup["semiconductores"]["emisores"] == ["NVDA"] and sup["inteligencia-artificial"]["lista_curada"] is True
    assert res["uniones_pct"]["industria"] == nvda and res["uniones_pct"]["tema"] == nvda      # NVDA cuenta una vez por tipo
    gld = round(200 / TOTAL * 100, 2)
    assert sup["oro"]["porcentaje"] == gld and sup["commodities-amplios"]["porcentaje"] == gld      # el oro también es un commodity
    assert res["uniones_pct"]["commodity"] == gld                                                    # …pero la unión lo cuenta una vez
    assert "tecnologia" not in sup and "no se suman" in res["aviso_superpuestos"]


def test_un_cedear_y_su_variante_en_pesos_son_un_solo_emisor(db):
    inst = cart.instrumentos_de_grupo(None, db, "consumo-basico")
    assert len(inst["instrumentos"]) == 1
    ko = inst["instrumentos"][0]
    assert ko["emisor"] == "KO" and ko["tickers"] == ["KO", "KOD"] and ko["valor_usd"] == pytest.approx(700.0)
    assert ko["peso_cartera_pct"] == pytest.approx(700 / TOTAL * 100, abs=0.01) and ko["peso_en_grupo_pct"] == 100.0
    assert ko["clasificacion"]["sector"] == "Consumo básico" and ko["nombre"] in ("KOD", "KO", "Coca-Cola")
    assert inst["exposicion_pct"] == pytest.approx(700 / TOTAL * 100, abs=0.01)


def test_instrumentos_del_grupo_con_peso_resultado_y_clasificacion(db):
    inst = cart.instrumentos_de_grupo(None, db, "tecnologia")
    assert [i["emisor"] for i in inst["instrumentos"]] == ["MSFT", "NVDA"]
    assert sum(i["peso_en_grupo_pct"] for i in inst["instrumentos"]) == pytest.approx(100.0, abs=0.01)
    assert inst["exposicion_usd"] == 1500.0 and inst["estado"]["cuadrante"] == "leading"
    msft = inst["instrumentos"][0]
    assert msft["rendimiento_pct"] == pytest.approx(0.0, abs=0.01) and msft["resultado_usd"] == pytest.approx(0.0, abs=0.01)
    assert msft["clasificacion"]["industria"] == "Software de infraestructura" and msft["clasificacion"]["region"] == "EEUU"
    assert inst["resultado_usd"] == pytest.approx(0.0, abs=0.05) and inst["resultado_parcial"] is False


def test_un_grupo_superpuesto_muestra_su_regla_y_el_aviso(db):
    inst = cart.instrumentos_de_grupo(None, db, "inteligencia-artificial")
    assert [i["emisor"] for i in inst["instrumentos"]] == ["NVDA"]
    assert inst["regla"]["tickers"] == ["NVDA"] and inst["regla"]["industria"] == ["Semiconductores"] and inst["regla"]["proxy"] == "AIQ"
    assert any("superponerse" in a for a in inst["avisos"]) and any("lista curada" in a for a in inst["avisos"])


def test_un_grupo_sin_exposicion_devuelve_lista_vacia(db):
    inst = cart.instrumentos_de_grupo(None, db, "europa")
    assert inst["instrumentos"] == [] and inst["exposicion_usd"] == 0.0 and inst["resultado_usd"] is None
    with pytest.raises(ca.NoEncontrado):
        cart.instrumentos_de_grupo(None, db, "nada")


def test_una_posicion_sin_cotizacion_ni_costo_completo_no_inventa_rendimiento(db):
    db.query(PrecioInstrumento).filter_by(ticker="NVDA").delete()
    db.commit()
    limpiar_cache()
    nvda = next(i for i in cart.instrumentos_de_grupo(None, db, "tecnologia")["instrumentos"] if i["emisor"] == "NVDA")
    assert nvda["valor_usd"] == 500.0                                    # sigue en la cartera, valuada al costo
    assert nvda["rendimiento_pct"] is None and "falta cotización" in nvda["rendimiento_no_calculable"]


def test_consolidado_suma_las_carteras_y_una_cartera_sola_no_ve_las_otras(db):
    pos(db, "MSFT", 5, 100.0, cartera="Otra", con_precio=False)
    db.commit()
    limpiar_cache()
    todo, principal, otra = cart.exposicion(None, db), cart.exposicion("Principal", db), cart.exposicion("Otra", db)
    assert todo["total_usd"] == pytest.approx(TOTAL + 500) and principal["total_usd"] == pytest.approx(TOTAL) and otra["total_usd"] == pytest.approx(500)
    assert _item(_dim(todo, "Sector"), "Tecnología")["valor_usd"] == 2000.0
    assert _item(_dim(otra, "Sector"), "Tecnología")["porcentaje"] == 100.0
    inst = cart.instrumentos_de_grupo(None, db, "tecnologia")
    assert next(i for i in inst["instrumentos"] if i["emisor"] == "MSFT")["valor_usd"] == 1500.0    # MSFT en dos carteras, un solo emisor


def test_sin_series_la_cartera_aparece_sin_estado_y_lo_avisa(db):
    from sqlalchemy import delete
    from app.database import BarraOHLCV
    db.execute(delete(BarraOHLCV))
    db.commit()
    limpiar_cache()
    res = cart.exposicion(None, db)
    assert res["resumen"]["en_leading_pct"] == 0.0 and res["resumen"]["sin_estado_pct"] == pytest.approx(100.0, abs=0.05)
    assert any("Todavía no hay estados" in a for a in res["advertencias"])


# -- simulador de rotación ---------------------------------------------------------------------

def test_la_rotacion_traslada_el_porcentaje_de_forma_proporcional(db):
    sim = cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    monto = TOTAL * 0.05
    assert sim["rotacion"]["monto_usd"] == pytest.approx(monto, abs=0.01) and sim["rotacion"]["pct_del_origen"] == pytest.approx(monto / 1500 * 100, abs=0.01)
    pos = {p["ticker"]: p for p in sim["rotacion"]["posiciones_origen"]}
    f = 1 - monto / 1500
    assert pos["MSFT"]["despues_usd"] == pytest.approx(1000 * f, abs=0.01) and pos["NVDA"]["despues_usd"] == pytest.approx(500 * f, abs=0.01)
    assert sim["total"]["antes_usd"] == pytest.approx(TOTAL) and sim["total"]["despues_usd"] == pytest.approx(TOTAL)   # sólo se mueve, no se agrega


def test_la_rotacion_cambia_sector_emisor_e_instrumento(db):
    sim = cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    sector = {f["etiqueta"]: f for f in _eje(sim, "Sector")["items"]}
    assert sector["Tecnología"]["delta_pp"] == pytest.approx(-5.0, abs=0.01) and sector["Salud"]["delta_pp"] == pytest.approx(5.0, abs=0.01)
    emisor = {f["etiqueta"]: f for f in _eje(sim, "Emisor")["items"]}
    assert emisor["Destino: Salud"]["despues_pct"] == pytest.approx(5.0, abs=0.01) and emisor["Destino: Salud"]["antes_pct"] == 0.0
    assert emisor["KO"]["tickers"] == ["KO", "KOD"]                                  # el emisor único también vale acá
    assert any(f["etiqueta"] == "Destino: Salud" for f in _eje(sim, "Instrumento")["items"])
    assert {e["eje"] for e in sim["ejes"]} == {"Emisor", "Instrumento", "Sector", "País", "Región"}


def test_el_destino_toma_pais_y_region_del_catalogo_y_lo_que_no_define_queda_sin_dato(db):
    sim = cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    assert sim["rotacion"]["destino"]["clasificacion"] == {"sector": "Salud", "pais": "Estados Unidos", "region": "EEUU"}
    # Destino sin país ni región (la Argentina define ambos; Mercados emergentes sólo región)
    sim2 = cart.simular_rotacion(None, db, "tecnologia", "emergentes", 5)
    assert sim2["rotacion"]["destino"]["clasificacion"] == {"sector": None, "pais": None, "region": "Emergentes"}
    pais = {f["etiqueta"]: f for f in _eje(sim2, "País")["items"]}
    assert pais["Sin país"]["delta_pp"] > 0
    assert any("no define sector" in o["texto"] for o in sim2["observaciones"])


def test_la_simulacion_describe_el_estado_actual_sin_recomendar(db):
    sim = cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    estado = next(o for o in sim["observaciones"] if o["eje"] == "Ciclos")
    assert "Leading" in estado["texto"] and "Lagging" in estado["texto"] and "no una señal" in estado["texto"]
    for texto in [o["texto"] for o in sim["observaciones"]] + sim["supuestos"] + sim["notas"]:
        assert not PROHIBIDO.search(texto), texto
    assert sim["rotacion"]["origen"]["estado"]["cuadrante"] == "leading" and sim["rotacion"]["destino"]["estado"]["cuadrante"] == "lagging"
    assert any("No se estima ningún rendimiento futuro" in s for s in sim["supuestos"])


def test_la_simulacion_usa_los_umbrales_de_salud(db):
    sim = cart.simular_rotacion(None, db, "tecnologia", "salud", 51)          # casi todo Tecnología hacia un solo destino
    niveles = {o["nivel"] for o in sim["observaciones"]}
    assert "revisar" in niveles or "atencion" in niveles
    assert any("Destino: Salud" in o["texto"] for o in sim["observaciones"] if o["nivel"] != "info")


def test_la_simulacion_no_escribe_nada(db):
    antes = {t.name: db.execute(t.select()).fetchall() for t in Base.metadata.sorted_tables if t.name != "serie_ohlcv"}
    cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    cart.simular_rotacion("Principal", db, "tecnologia", "energia", 10)
    assert not db.new and not db.dirty and not db.deleted
    db.rollback()
    despues = {t.name: db.execute(t.select()).fetchall() for t in Base.metadata.sorted_tables if t.name != "serie_ohlcv"}
    assert antes == despues
    limpiar_cache()
    assert {e["eje"]: e["items"] for e in get_exposicion(None, db)["ejes"]}["Sector"][0]["valor_usd"] == 1500.0


def test_diferencias_contra_objetivos_antes_y_despues(db):
    assert cart.simular_rotacion(None, db, "tecnologia", "salud", 5)["rebalanceo"] == []
    db.add(RebalanceoObjetivo(cartera=None, eje="Sector", categoria="Tecnología", porcentaje_objetivo=40))
    db.add(RebalanceoObjetivo(cartera=None, eje="Sector", categoria="Salud", porcentaje_objetivo=10))
    db.commit()
    limpiar_cache()
    reb = next(r for r in cart.simular_rotacion(None, db, "tecnologia", "salud", 5)["rebalanceo"] if r["eje"] == "Sector")
    assert reb["desvio_despues_pp"] < reb["desvio_antes_pp"]
    assert {i["etiqueta"] for i in reb["items"]} == {"Tecnología", "Salud"}


def test_una_cartera_sola_y_el_consolidado(db):
    pos(db, "MSFT", 5, 100.0, cartera="Otra", con_precio=False)
    db.commit()
    limpiar_cache()
    uno = cart.simular_rotacion("Otra", db, "tecnologia", "salud", 10)
    assert uno["total"]["antes_usd"] == pytest.approx(500.0) and uno["rotacion"]["origen"]["exposicion_pct"] == 100.0
    todo = cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    assert todo["total"]["antes_usd"] == pytest.approx(TOTAL + 500)


@pytest.mark.parametrize("pct", [0, -5, 101, True, "5", None, float("nan")])
def test_porcentajes_invalidos(db, pct):
    with pytest.raises(ValueError, match="porcentaje"):
        cart.simular_rotacion(None, db, "tecnologia", "salud", pct)


def test_validaciones_del_simulador(db):
    with pytest.raises(ValueError, match="el mismo"):
        cart.simular_rotacion(None, db, "tecnologia", "tecnologia", 5)
    with pytest.raises(ValueError, match="no tiene exposición"):
        cart.simular_rotacion(None, db, "europa", "salud", 5)
    with pytest.raises(ValueError, match="pesa 51.7 %"):
        cart.simular_rotacion(None, db, "tecnologia", "salud", 60)
    with pytest.raises(ca.NoEncontrado):
        cart.simular_rotacion(None, db, "tecnologia", "nada", 5)
    with pytest.raises(ca.NoEncontrado):
        cart.simular_rotacion(None, db, "apagado", "salud", 5)


def test_cartera_sin_posiciones(db):
    db.query(MovimientoInversion).delete()
    db.commit()
    limpiar_cache()
    with pytest.raises(ValueError, match="no tiene posiciones valuadas"):
        cart.simular_rotacion(None, db, "tecnologia", "salud", 5)
    res = cart.exposicion(None, db)
    assert res["total_usd"] == 0 and res["superpuestas"] == [] and res["sin_clasificar"] == []
    assert all(d["items"] == [] and all(p["porcentaje"] == 0.0 for p in d["por_cuadrante"]) for d in res["dimensiones"])
