"""Calendario de eventos: clasificación por reglas, importancia, confianza y asociación con instrumentos. Puro."""
from app.services.eventos import asociacion_engine as ae
from app.services.eventos import clasificacion_engine as ce


def test_clasifica_banco_central_con_importancia_alta_y_reglas_auditables():
    c = ce.clasificar("Fed holds interest rates steady, Powell signals cuts later this year")
    assert c["categoria"] == "banco_central"
    assert c["importancia"] == 3 and c["confianza"] == "alta"
    assert any("fed" in r for r in c["reglas"]) and c["version"] == ce.VERSION_REGLAS


def test_clasifica_en_castellano_y_sin_acentos():
    assert ce.clasificar("El BCRA bajó la tasa de interés de referencia")["categoria"] == "banco_central"
    assert ce.clasificar("Elecciones legislativas: qué se vota el domingo")["categoria"] == "elecciones"
    assert ce.clasificar("La inflación de septiembre fue 2,1 % según el INDEC")["categoria"] == "dato_macro"
    assert ce.clasificar("Nvidia acquires a chip startup in a $700 million deal")["categoria"] == "corporativo"
    assert ce.clasificar("EE.UU. impone aranceles del 25 % al acero")["categoria"] == "sanciones_aranceles"


def test_sin_terminos_queda_otro_con_confianza_baja():
    c = ce.clasificar("Un día tranquilo en la oficina")
    assert c["categoria"] == "otro" and c["confianza"] == "baja" and c["importancia"] == 1


def test_importancia_sube_si_menciona_algo_que_sigue_el_usuario():
    afuera = ce.clasificar("Apple quarterly results beat estimates")
    adentro = ce.clasificar("Apple quarterly results beat estimates", en_universo=True)
    assert afuera["categoria"] == "resultados"
    assert adentro["importancia"] == afuera["importancia"] + 1


def test_incorporacion_solo_con_criterios_claros():
    clara = {"categoria": "banco_central", "confianza": "alta", "importancia": 3}
    assert ce.decidir_incorporacion(clara, menciona_universo=True)[0]
    assert not ce.decidir_incorporacion(clara, menciona_universo=False)[0]
    assert not ce.decidir_incorporacion({**clara, "confianza": "baja"}, True)[0]
    assert not ce.decidir_incorporacion({**clara, "categoria": "otro"}, True)[0]
    assert not ce.decidir_incorporacion({**clara, "importancia": 1}, True)[0]
    assert ce.decidir_incorporacion({**clara, "categoria": "otro"}, False, fuente_programada=True)[0]


def test_confianza_de_datos_separada_de_la_clasificacion():
    assert ce.confianza_datos("fuente_oficial", "exacta", 1) == "alta"
    assert ce.confianza_datos("sin_verificar", "exacta", 2) == "alta"
    assert ce.confianza_datos("sin_verificar", "aproximada", 1) == "baja"
    assert ce.confianza_datos("rumor", "exacta", 5) == "baja"


UNIVERSO = {
    "AAPL": {"sector": "Tecnología", "pais": "Estados Unidos"},
    "MSFT": {"sector": "Tecnología", "pais": "Estados Unidos"},
    "VIST": {"sector": "Energía", "pais": "Argentina"},
    "GGAL": {"sector": "Financiero", "pais": "Argentina"},
}
SIMBOLOS = {"AAPL": ["AAPL"], "MSFT": ["MSFT"], "VIST": ["VIST"], "GGAL": ["GGAL"], "SPY": ["SPY"], "^MERV": ["^MERV"]}


def test_asociacion_directa_sector_y_relevancias_distintas():
    props = ae.proponer(
        categoria="regulacion", pais=None, texto="",
        entidades=[{"simbolo": "AAPL", "nombre": "Apple", "industria": "Technology", "match_score": 30, "en_titulo": True},
                   {"simbolo": "XYZ", "nombre": "Ajena", "match_score": 50, "en_titulo": True}],
        simbolo_a_tickers=SIMBOLOS, universo=UNIVERSO,
    )
    por = {p["ticker"]: p for p in props}
    assert por["AAPL"]["tipo_relacion"] == "directa" and por["AAPL"]["relevancia"] == 1.0
    assert por["MSFT"]["tipo_relacion"] == "sector" and por["MSFT"]["relevancia"] == ae.RELEVANCIA_SECTOR
    assert "VIST" not in por and "XYZ" not in por
    assert "Apple" in por["AAPL"]["justificacion"]


def test_mencion_debil_no_vincula():
    props = ae.proponer(categoria="corporativo", pais=None, texto="",
                        entidades=[{"simbolo": "AAPL", "match_score": 3, "en_titulo": False}],
                        simbolo_a_tickers=SIMBOLOS, universo=UNIVERSO)
    assert props == []


def test_asociacion_por_pais_con_indice_y_lapidas():
    props = ae.proponer(categoria="elecciones", pais="argentina", entidades=[], texto="",
                        simbolo_a_tickers=SIMBOLOS, universo=UNIVERSO, lapidas={"GGAL"})
    por = {p["ticker"]: p for p in props}
    assert por["^MERV"]["tipo_relacion"] == "indice"
    assert por["VIST"]["tipo_relacion"] == "pais" and por["VIST"]["relevancia"] < por["^MERV"]["relevancia"]
    assert "GGAL" not in por and "AAPL" not in por


def test_evento_global_solo_al_indice_amplio():
    props = ae.proponer(categoria="geopolitica", pais=None, entidades=[], texto="",
                        simbolo_a_tickers=SIMBOLOS, universo=UNIVERSO)
    assert [p["ticker"] for p in props] == ["SPY"]


def test_materia_prima_vincula_al_sector_expuesto():
    props = ae.proponer(categoria="materias_primas", pais=None, entidades=[], texto="opec recorta la produccion de petroleo",
                        simbolo_a_tickers=SIMBOLOS, universo=UNIVERSO)
    assert [p["ticker"] for p in props] == ["VIST"]
