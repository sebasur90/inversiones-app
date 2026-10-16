"""Normalización pura de la clasificación: sector, país→región, ETFs, tipo, variantes de moneda,
símbolo en Yahoo y la precedencia de fuentes de `resolver`."""
import pytest

from app.services import clasificacion_engine as ce
from app.services.catalogo_instrumentos import cargar_catalogo
from app.services.clasificacion_seed import cargar_seed


# ── sector ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("Technology", "Tecnología"),
    ("tecnologia", "Tecnología"),
    ("Consumer Defensive", "Consumo básico"),
    ("Cosumo Masivo", "Consumo básico"),
    ("  consumo   masivo ", "Consumo básico"),
    ("Financial Services", "Financiero"),
    ("Utilities", "Servicios públicos"),
    ("Indice", "Diversificado"),
    ("Liquidez", "Liquidez"),
])
def test_sector_canonico(texto, esperado):
    assert ce.sector_canonico(texto) == esperado


def test_sector_desconocido_pasa_tal_cual():
    assert ce.sector_canonico(" Soberano ") == "Soberano"
    assert ce.sector_canonico("") is None
    assert ce.sector_canonico(None) is None


def test_industria_legible_traduce_o_deja_en_ingles():
    assert ce.industria_legible("Beverages - Non-Alcoholic") == "Bebidas sin alcohol"
    assert ce.industria_legible("Some Weird Industry") == "Some Weird Industry"


# ── país y región ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("pais,region", [
    ("United States", ce.REGION_EEUU),
    ("EEUU", ce.REGION_EEUU),
    ("AR", ce.REGION_ARGENTINA),
    ("Argentina", ce.REGION_ARGENTINA),
    ("Netherlands", ce.REGION_DESARROLLADOS),
    ("Japan", ce.REGION_DESARROLLADOS),
    ("Brazil", ce.REGION_EMERGENTES),
    ("Taiwan", ce.REGION_EMERGENTES),
    ("South Korea", ce.REGION_EMERGENTES),
    ("Uruguay", ce.REGION_EMERGENTES),
])
def test_region_de_pais(pais, region):
    assert ce.region_de_pais(pais) == region


def test_pais_sede_legal_no_tiene_region():
    assert ce.pais_canonico("Luxembourg") == "Luxemburgo"
    assert ce.clase_msci("Cayman Islands") == ce.CLASE_SEDE_LEGAL
    assert ce.region_de_pais("Luxembourg") is None


def test_pais_desconocido_pasa_tal_cual_sin_region():
    assert ce.pais_canonico("Atlantis") == "Atlantis"
    assert ce.region_de_pais("Atlantis") is None


def test_frontera_se_agrupa_con_emergentes():
    assert ce.clase_msci("Vietnam") == ce.CLASE_FRONTERA
    assert ce.region_de_pais("Vietnam") == ce.REGION_EMERGENTES


def test_region_canonica():
    assert ce.region_canonica("emergentes") == ce.REGION_EMERGENTES
    assert ce.region_canonica("usa") == ce.REGION_EEUU
    assert ce.region_canonica("") is None


# ── ETFs ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("categoria,sector,region", [
    ("Large Blend", "Diversificado", ce.REGION_EEUU),
    ("Technology", "Tecnología", ce.REGION_EEUU),
    ("Diversified Emerging Mkts", "Diversificado", ce.REGION_EMERGENTES),
    ("Latin America Stock", "Diversificado", ce.REGION_EMERGENTES),
    ("Foreign Large Blend", "Diversificado", ce.REGION_DESARROLLADOS),
    ("Japan Stock", "Diversificado", ce.REGION_DESARROLLADOS),
    ("Commodities Focused", "Materias primas", ce.REGION_GLOBAL),
    ("Equity Precious Metals", "Materiales", ce.REGION_GLOBAL),
    ("Digital Assets", "Cripto", ce.REGION_GLOBAL),
    ("Equity Energy", "Energía", ce.REGION_EEUU),
])
def test_clasificar_etf(categoria, sector, region):
    assert ce.clasificar_etf(categoria) == (sector, region)


def test_etf_sin_categoria_queda_sin_clasificar():
    assert ce.clasificar_etf(None) == (None, None)


# ── tipo ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,base", [
    ("CEDEAR", "CEDEAR"),
    ("ETF", "CEDEAR"),
    ("Acción", "Acción"),
    ("Accion", "Acción"),
    ("Bono", "Bono"),
    ("BONCER", "Bono"),
    ("Obligacion Negociable", "ON"),
    ("ON", "ON"),
    ("LECAP", "Letra"),
    ("Letra", "Letra"),
    ("FCI", "FCI"),
    ("Fondo Comun de Inversion", "FCI"),
    ("Cripto", None),
])
def test_tipo_base_de(texto, base):
    assert ce.tipo_base_de(texto) == base


def test_tipo_fino_distingue_etf_por_quote_type():
    assert ce.tipo_fino("CEDEAR", "ETF") == ce.TIPO_CEDEAR_ETF
    assert ce.tipo_fino("CEDEAR", "EQUITY") == ce.TIPO_CEDEAR_ACCION
    assert ce.tipo_fino("CEDEAR", None) == ce.TIPO_CEDEAR_ACCION
    assert ce.tipo_fino("Acción", "EQUITY") == ce.TIPO_ACCION
    assert ce.tipo_base_de_fino(ce.TIPO_CEDEAR_ETF) == ce.TIPO_BASE_CEDEAR


# ── variantes de moneda ───────────────────────────────────────────────────

def _e(simbolo, descripcion, moneda):
    return {"simbolo": simbolo, "descripcion": descripcion, "moneda": moneda}


def test_mapa_variantes_reglas():
    catalogo = [
        _e("AAPL", "Cedear Apple Inc.", "ARS"),
        _e("AAPLC", "Cedear Apple Inc.", "USD"),
        _e("AAPLD", "Cedear Apple Inc. Esc.", "USD"),
        _e("ABT", "Cedear Abbott Laboratories", "ARS"),
        _e("ABTC", "Cedear Abbott Laboratories Esc", "USD"),
        _e("BB", "Cedear Blackberry", "ARS"),
        _e("BBD", "Cedear Banco Bradesco S.A.", "ARS"),   # en pesos: no es variante de BB
        _e("BA", "Cedear The Boeing Company", "ARS"),
        _e("BA.C", "Cedear Bank Of America Corpora", "ARS"),
        _e("BA.CD", "Cedear Bank Of America Corp.", "USD"),
        _e("BMA", "Banco Macro", "ARS"),
        _e("BMA.D", "Banco Macro", "USD"),
        _e("XYZ", "Cedear Block Inc", "ARS"),
        _e("XYZD", "Cedear Otra Empresa Totalmente", "USD"),  # descripción distinta
    ]
    mapa = ce.mapa_variantes(catalogo, {"GOGLD": "GOOGL"})
    assert mapa["AAPLC"] == "AAPL"
    assert mapa["AAPLD"] == "AAPL"
    assert mapa["ABTC"] == "ABT"
    assert mapa["BA.CD"] == "BA.C"
    assert mapa["BMA.D"] == "BMA"
    assert mapa["GOGLD"] == "GOOGL"
    assert "BBD" not in mapa
    assert "BA.C" not in mapa
    assert "XYZD" not in mapa
    assert ce.ticker_base("aapld", mapa) == "AAPL"
    assert ce.ticker_base("KO", mapa) == "KO"


def test_mapa_variantes_sobre_catalogo_real():
    """El catálogo versionado: 935 símbolos CEDEAR colapsan a ~400 emisores, sin falsos
    positivos conocidos."""
    catalogo = cargar_catalogo()
    if not catalogo:
        pytest.skip("catálogo no montado")
    seed = cargar_seed()
    mapa = ce.mapa_variantes(catalogo, seed["variantes"])
    cedears = {e["simbolo"].upper() for e in catalogo if e["tipo"] == "CEDEAR"}
    bases = {ce.ticker_base(s, mapa) for s in cedears}
    assert 380 <= len(bases) <= 420
    assert mapa.get("BBD") is None
    assert mapa.get("BA.C") is None
    assert mapa.get("ABEV3") is None
    assert mapa["YPFDD"] == "YPFD"
    assert mapa["TECOD"] == "TECO2"
    assert mapa["VAL3D"] == "VALE3"
    # Ninguna base es a su vez variante.
    assert not (set(mapa.values()) & set(mapa))


# ── símbolo en Yahoo ──────────────────────────────────────────────────────

def test_simbolo_yahoo_precedencia():
    seed = {"YPFD": "YPF", "PETR3": "PBR"}
    assert ce.simbolo_yahoo("KO", "CEDEAR") == ("KO", ce.METODO_IDENTIDAD)
    assert ce.simbolo_yahoo("BRK.B", "CEDEAR") == ("BRK-B", ce.METODO_IDENTIDAD)
    assert ce.simbolo_yahoo("ALUA", "Acción") == ("ALUA.BA", ce.METODO_BA)
    assert ce.simbolo_yahoo("YPFD", "Acción", seed) == ("YPF", ce.METODO_SEED)
    assert ce.simbolo_yahoo("MSFT", "CEDEAR", seed, subyacente_resuelto="MSFT") == ("MSFT", ce.METODO_SUBYACENTE)
    assert ce.simbolo_yahoo("KO", "CEDEAR", seed, override="ko") == ("KO", ce.METODO_MANUAL)
    assert ce.simbolo_yahoo("AL30", "Bono", seed) == (None, ce.METODO_NO_APTO)
    assert ce.simbolo_yahoo("BKC*", "CEDEAR") == (None, ce.METODO_NO_APTO)


def test_seed_real_se_lee_sin_doc():
    seed = cargar_seed()
    assert "_DOC" not in seed["simbolos_yahoo"]
    assert seed["simbolos_yahoo"].get("BRKB") is None  # lo resuelve la regla, no el seed
    assert seed["simbolos_yahoo"]["YPFD"] == "YPF"
    assert seed["exposicion"]["VIST"] == {"pais": "Argentina"}


# ── traducción de Yahoo ───────────────────────────────────────────────────

def test_clasificar_desde_yahoo_accion():
    info = {"quoteType": "EQUITY", "sector": "Consumer Defensive",
            "industry": "Beverages - Non-Alcoholic", "country": "United States",
            "longName": "The Coca-Cola Company"}
    c = ce.clasificar_desde_yahoo(info, "CEDEAR")
    assert c["tipo"] == ce.TIPO_CEDEAR_ACCION
    assert c["sector"] == "Consumo básico"
    assert c["industria"] == "Bebidas sin alcohol"
    assert c["industria_raw"] == "Beverages - Non-Alcoholic"
    assert c["pais"] == "Estados Unidos"
    assert c["region"] == ce.REGION_EEUU
    assert c["nombre"] == "The Coca-Cola Company"


def test_clasificar_desde_yahoo_etf():
    info = {"quoteType": "ETF", "category": "Diversified Emerging Mkts", "fundFamily": "iShares"}
    c = ce.clasificar_desde_yahoo(info, "CEDEAR")
    assert c["tipo"] == ce.TIPO_CEDEAR_ETF
    assert c["sector"] == "Diversificado"
    assert c["region"] == ce.REGION_EMERGENTES
    assert c["pais"] is None
    assert c["categoria_etf_raw"] == "Diversified Emerging Mkts"


def test_clasificar_desde_yahoo_accion_local():
    info = {"quoteType": "EQUITY", "sector": "Financial Services", "country": "Argentina"}
    c = ce.clasificar_desde_yahoo(info, "Acción")
    assert c["tipo"] == ce.TIPO_ACCION
    assert c["region"] == ce.REGION_ARGENTINA


# ── resolver ──────────────────────────────────────────────────────────────

AUTO_KO = {"tipo": ce.TIPO_CEDEAR_ACCION, "sector": "Consumo básico", "industria": "Bebidas sin alcohol",
           "pais": "Estados Unidos", "region": ce.REGION_EEUU}


def test_resolver_yahoo_gana_al_sheet():
    r = ce.resolver(auto=AUTO_KO, sheet={"tipo_instrumento": "CEDEAR", "sector": "Cosumo Masivo", "pais": "AR"})
    assert r.sector == "Consumo básico" and r.fuentes["sector"] == "yahoo"
    assert r.pais == "Estados Unidos" and r.fuentes["pais"] == "yahoo"
    assert r.region == ce.REGION_EEUU
    assert r.tipo_base == ce.TIPO_BASE_CEDEAR


def test_resolver_manual_gana_a_todo():
    r = ce.resolver(override={"sector": "tecnologia", "region": "global"}, auto=AUTO_KO)
    assert r.sector == "Tecnología" and r.fuentes["sector"] == "manual"
    assert r.region == ce.REGION_GLOBAL and r.fuentes["region"] == "manual"
    assert r.pais == "Estados Unidos"


def test_resolver_pais_corregido_arrastra_region():
    auto = {"tipo": ce.TIPO_CEDEAR_ACCION, "pais": "Luxemburgo", "region": None}
    r = ce.resolver(seed={"pais": "Argentina"}, auto=auto)
    assert r.pais == "Argentina" and r.fuentes["pais"] == "seed"
    assert r.region == ce.REGION_ARGENTINA and r.fuentes["region"] == "seed"


def test_resolver_seed_region_sin_pais():
    auto = {"tipo": ce.TIPO_CEDEAR_ACCION, "pais": "Uruguay", "region": ce.REGION_EMERGENTES}
    r = ce.resolver(seed={"region": "Emergentes"}, auto=auto)
    assert r.pais == "Uruguay"
    assert r.region == ce.REGION_EMERGENTES and r.fuentes["region"] == "seed"


def test_resolver_cedear_ignora_argentina_del_sheet():
    r = ce.resolver(sheet={"tipo_instrumento": "CEDEAR", "sector": "Indice", "pais": "AR"})
    assert r.pais is None and r.region is None
    assert r.sector == "Diversificado" and r.fuentes["sector"] == "sheet"
    assert r.tipo == ce.TIPO_CEDEAR_ACCION


def test_resolver_accion_local_conserva_argentina_del_sheet():
    r = ce.resolver(sheet={"tipo_instrumento": "Acción", "pais": "AR"})
    assert r.pais == "Argentina" and r.region == ce.REGION_ARGENTINA


def test_resolver_liquidez_del_sheet_gana_a_yahoo():
    auto = {"tipo": ce.TIPO_CEDEAR_ETF, "sector": "Renta fija", "region": ce.REGION_EEUU}
    r = ce.resolver(auto=auto, sheet={"tipo_instrumento": "ETF", "sector": "Liquidez"})
    assert r.sector == "Liquidez" and r.fuentes["sector"] == "sheet"
    # ...pero no a una corrección manual
    r2 = ce.resolver(override={"sector": "Renta fija"}, auto=auto, sheet={"sector": "Liquidez"})
    assert r2.sector == "Renta fija"


def test_resolver_renta_fija_usa_el_sheet():
    r = ce.resolver(
        seed={"pais": "Estados Unidos"},
        sheet={"tipo_instrumento": "Bono", "sector": "Soberano", "pais": "AR"},
    )
    assert r.tipo == ce.TIPO_BONO and r.tipo_base == ce.TIPO_BONO
    assert r.sector == "Soberano" and r.fuentes["sector"] == "sheet"
    assert r.pais == "Argentina" and r.fuentes["pais"] == "sheet"
    assert r.region == ce.REGION_ARGENTINA


def test_resolver_sin_datos():
    r = ce.resolver()
    assert r.tipo is None and r.sector is None and r.region is None
    assert all(v is None for v in r.fuentes.values())


def test_resolver_tipo_etf_desde_sheet():
    r = ce.resolver(sheet={"tipo_instrumento": "ETF"})
    assert r.tipo == ce.TIPO_CEDEAR_ETF
