"""Impacto de sumar un monto a la cartera: pesos antes/después, umbrales de Salud, lenguaje."""
import re

import pytest

from app.services import impacto_cartera_engine as ice


def grupo(**valores):
    """`{etiqueta: usd}` → lista como la de `_agrupar` (pesos sobre el total del grupo)."""
    total = sum(valores.values())
    return [
        {"etiqueta": k, "valor_usd": v, "valor_ars": v * 1000, "porcentaje": round(v / total * 100, 2)}
        for k, v in sorted(valores.items(), key=lambda kv: -kv[1])
    ] if total > 0 else []


def eje_emisor(antes: dict, monto: float, emisor: str) -> ice.EjeEntrada:
    despues = dict(antes)
    despues[emisor] = despues.get(emisor, 0.0) + monto
    return ice.EjeEntrada(ice.EJE_EMISOR, grupo(**antes), grupo(**despues), emisor)


def datos(emisor="KO", monto=500.0, antes=2000.0, **kw) -> ice.Datos:
    return ice.Datos(ticker=emisor, emisor=emisor, monto_usd=monto, total_antes_usd=antes,
                     total_despues_usd=antes + monto, **kw)


def obs_de(res, eje=None):
    return [o for o in res["observaciones"] if eje is None or o["eje"] == eje]


def test_los_pesos_antes_y_despues_suman_la_compra_al_emisor():
    e = eje_emisor({"KO": 500.0, "MSFT": 1000.0, "GGAL": 500.0}, 500.0, "KO")
    r = ice.construir([e], datos())
    fila = next(f for f in r["ejes"][0]["items"] if f["etiqueta"] == "KO")
    assert fila["antes_pct"] == 25.0 and fila["despues_pct"] == 40.0
    assert fila["delta_pp"] == pytest.approx(15.0) and fila["afectada"] is True
    otra = next(f for f in r["ejes"][0]["items"] if f["etiqueta"] == "MSFT")
    assert otra["antes_pct"] == 50.0 and otra["despues_pct"] == 40.0 and otra["afectada"] is False
    assert r["peso_monto_pct"] == pytest.approx(20.0)


def test_un_emisor_nuevo_aparece_con_peso_antes_cero():
    r = ice.construir([eje_emisor({"MSFT": 1000.0}, 1000.0, "KO")], datos(antes=1000.0, monto=1000.0))
    fila = next(f for f in r["ejes"][0]["items"] if f["etiqueta"] == "KO")
    assert fila["antes_pct"] == 0.0 and fila["despues_pct"] == 50.0


def test_cartera_vacia_el_monto_es_el_100_por_ciento():
    r = ice.construir([eje_emisor({}, 300.0, "KO")], datos(antes=0.0, monto=300.0))
    assert r["peso_monto_pct"] == pytest.approx(100.0)
    assert r["ejes"][0]["antes"]["n_efectivo"] is None and r["ejes"][0]["despues"]["n_efectivo"] == pytest.approx(1.0)


def test_umbral_de_atencion_y_de_revisar_por_defecto():
    antes = {"A": 8000.0, "B": 1000.0, "KO": 1000.0}
    # KO 10 % → 21,7 %: cruza atención (20)
    atencion = obs_de(ice.construir([eje_emisor(antes, 1500.0, "KO")], datos(antes=10000.0, monto=1500.0)), "Emisor")
    assert atencion[0]["nivel"] == "atencion"
    assert "KO pasaría de 10,0 % a 21,7 % de la cartera, por encima del umbral de atención (20,0 %)." == atencion[0]["texto"]
    # 10 % → 18,2 %: no llega a 20
    assert not [o for o in obs_de(ice.construir([eje_emisor(antes, 1000.0, "KO")], datos(antes=10000.0, monto=1000.0)), "Emisor")
                if "pasaría de" in o["texto"]]
    # KO 10 % → 35,7 %: cruza revisar (30)
    revisar = obs_de(ice.construir([eje_emisor(antes, 4000.0, "KO")], datos(antes=10000.0, monto=4000.0)), "Emisor")
    assert revisar[0]["nivel"] == "revisar" and "umbral de revisar (30,0 %)" in revisar[0]["texto"]
    assert "umbrales de Salud de cartera por emisor" in revisar[0]["regla"]


def test_sin_cruzar_el_umbral_no_hay_observacion_de_peso():
    r = ice.construir([eje_emisor({"A": 5000.0, "B": 4000.0, "KO": 1000.0}, 500.0, "KO")], datos(antes=10000.0, monto=500.0))
    assert not [o for o in obs_de(r, "Emisor") if "pasaría" in o["texto"] or "ya pesaba" in o["texto"]]


def test_peso_maximo_configurado_pasa_a_ser_el_umbral_de_atencion():
    antes = {"A": 5000.0, "B": 4000.0, "KO": 1000.0}
    e = eje_emisor(antes, 1500.0, "KO")        # KO 10 % → 21,7 %
    por_defecto = obs_de(ice.construir([e], datos(antes=10000.0, monto=1500.0)), "Emisor")
    configurado = obs_de(ice.construir([e], datos(antes=10000.0, monto=1500.0, peso_maximo=15.0)), "Emisor")
    assert por_defecto[0]["nivel"] == "atencion"                       # supera 20
    assert configurado[0]["nivel"] == "atencion" and "15,0 %" in configurado[0]["texto"]
    assert "peso máximo configurado" in configurado[0]["regla"] and "22,5 %" in configurado[0]["regla"]
    # con un máximo de 40 no hay nada que decir
    assert not [o for o in obs_de(ice.construir([e], datos(antes=10000.0, monto=1500.0, peso_maximo=40.0)), "Emisor")
                if "pasaría" in o["texto"]]


def test_si_ya_superaba_el_umbral_lo_dice():
    e = eje_emisor({"KO": 4000.0, "A": 6000.0}, 1000.0, "KO")           # 40 % → 45,5 %
    o = obs_de(ice.construir([e], datos(antes=10000.0, monto=1000.0)), "Emisor")
    assert o[0]["nivel"] == "revisar" and "ya pesaba 40,0 %" in o[0]["texto"]


def test_pais_cruza_los_umbrales_de_salud_solo_si_el_peso_sube():
    antes = {"Estados Unidos": 6000.0, "Argentina": 4000.0}
    e = ice.EjeEntrada("País", grupo(**antes), grupo(**{"Estados Unidos": 9000.0, "Argentina": 4000.0}), "Estados Unidos")
    assert obs_de(ice.construir([e], datos(antes=10000.0, monto=3000.0)), "País") == []        # 69,2 % < 70 %
    e2 = ice.EjeEntrada("País", grupo(**antes), grupo(**{"Estados Unidos": 11000.0, "Argentina": 4000.0}), "Estados Unidos")
    o2 = obs_de(ice.construir([e2], datos(antes=10000.0, monto=5000.0)), "País")
    assert o2[0]["nivel"] == "atencion" and "pasaría de 60,0 % a 73,3 %" in o2[0]["texto"]
    # justo en el umbral (70 %) ya es atención: el umbral es "desde"
    e3 = ice.EjeEntrada("País", grupo(**antes), grupo(**{"Estados Unidos": 6000.0, "Argentina": 14000.0}), "Argentina")
    o3 = obs_de(ice.construir([e3], datos(antes=10000.0, monto=10000.0)), "País")
    assert o3[0]["nivel"] == "atencion" and "Argentina pasaría de 40,0 % a 70,0 %" in o3[0]["texto"]
    # un país que no sube de peso no genera observación aunque esté por encima del umbral
    e4 = ice.EjeEntrada("País", grupo(**{"Estados Unidos": 8000.0, "Argentina": 2000.0}),
                        grupo(**{"Estados Unidos": 8000.0, "Argentina": 4000.0}), "Argentina")
    assert obs_de(ice.construir([e4], datos(antes=10000.0, monto=2000.0)), "País") == []


def test_pais_residual_no_cuenta_como_concentracion_geografica():
    e = ice.EjeEntrada("País", grupo(**{"Sin país": 1000.0}), grupo(**{"Sin país": 9000.0}), "Sin país")
    assert obs_de(ice.construir([e], datos(antes=1000.0, monto=8000.0)), "País")[0]["nivel"] == "info"


def test_cae_en_un_bucket_residual_se_avisa_como_info():
    e = ice.EjeEntrada("Sector", grupo(**{"Tecnología": 1000.0}), grupo(**{"Tecnología": 1000.0, "Sin sector": 500.0}), "Sin sector")
    o = obs_de(ice.construir([e], datos(antes=1000.0, monto=500.0)), "Sector")
    assert len(o) == 1 and o[0]["nivel"] == "info" and "«Sin sector»" in o[0]["texto"]


def test_diversificacion_por_emisor_baja_de_nivel():
    antes = {"A": 4000.0, "B": 3000.0, "C": 2000.0, "D": 1000.0}            # N efectivo ≈ 3,33
    e = eje_emisor(antes, 6000.0, "A")                                      # A pasa a 62,5 %: N efectivo ≈ 1,9
    o = [x for x in obs_de(ice.construir([e], datos(emisor="A", antes=10000.0, monto=6000.0)), "Emisor")
         if "diversificación" in x["texto"]]
    assert o and o[0]["nivel"] == "revisar" and "umbrales de Salud de cartera" in o[0]["regla"]


def test_diversificacion_mejora_se_informa_como_info():
    antes = {"A": 5000.0, "B": 2000.0, "C": 2000.0, "D": 1000.0}           # N efectivo ≈ 2,9 (revisar: < 3)
    e = eje_emisor(antes, 1000.0, "D")                                      # → 3,3 (atención)
    o = [x for x in obs_de(ice.construir([e], datos(emisor="D", antes=10000.0, monto=1000.0)), "Emisor")
         if "diversificación" in x["texto"]]
    assert o and o[0]["nivel"] == "info" and "subiría" in o[0]["texto"]


def test_emisor_que_ya_esta_en_cartera_se_avisa():
    e = eje_emisor({"KO": 500.0, "MSFT": 1500.0}, 100.0, "KO")
    r = ice.construir([e], datos(antes=2000.0, monto=100.0, emisor_en_cartera=["KOD"]))
    assert any("Ya tenés KO en la cartera (KOD)" in o["texto"] for o in r["observaciones"])


def test_las_observaciones_van_de_mas_a_menos_urgente():
    antes = {"KO": 1000.0, "A": 9000.0}
    e = eje_emisor(antes, 9000.0, "KO")
    pais = ice.EjeEntrada("País", grupo(**{"Sin país": 10000.0}), grupo(**{"Sin país": 19000.0}), "Sin país")
    r = ice.construir([e, pais], datos(antes=10000.0, monto=9000.0, emisor_en_cartera=["KOD"]))
    niveles = [o["nivel"] for o in r["observaciones"]]
    orden = {"revisar": 0, "atencion": 1, "info": 2}
    assert niveles == sorted(niveles, key=orden.get)


def test_determinista():
    e = eje_emisor({"KO": 500.0, "MSFT": 1000.0, "GGAL": 500.0}, 500.0, "KO")
    assert ice.construir([e], datos()) == ice.construir([e], datos())


def test_nunca_dice_compra_ni_venta():
    prohibidas = re.compile(r"\b(compr\w*|vend\w*|recomend\w*)\b", re.IGNORECASE)
    casos = [
        ([eje_emisor({"KO": 4000.0, "A": 6000.0}, 1000.0, "KO")], datos(antes=10000.0, monto=1000.0, emisor_en_cartera=["KOD"])),
        ([eje_emisor({"A": 8000.0, "B": 1000.0, "KO": 1000.0}, 4000.0, "KO")], datos(antes=10000.0, monto=4000.0)),
        ([ice.EjeEntrada("Sector", grupo(Tec=1.0), grupo(Tec=1.0, **{"Sin sector": 1.0}), "Sin sector")], datos(antes=1.0, monto=1.0)),
        ([ice.EjeEntrada("País", grupo(**{"Estados Unidos": 7.0, "AR": 3.0}), grupo(**{"Estados Unidos": 12.0, "AR": 3.0}), "Estados Unidos")],
         datos(antes=10.0, monto=5.0)),
    ]
    for ejes, d in casos:
        r = ice.construir(ejes, d)
        for o in r["observaciones"]:
            assert not prohibidas.search(o["texto"]), o["texto"]
            assert not prohibidas.search(o["regla"]), o["regla"]
