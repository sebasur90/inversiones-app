"""Normalización de la clasificación de instrumentos: tipo, sector, industria, país y región.

Funciones **puras** (sin DB ni red). Las consumen la ingesta de fundamentales (que traduce lo que
devuelve Yahoo), el resolutor de `clasificacion_analytics` (que decide qué fuente manda para cada
campo) y la valuación contra pares.

Por qué existe: hasta acá sector y país eran texto libre del Sheet (KO con `País=AR`, "Cosumo
Masivo", "Indice" como sector) y la watchlist no tenía ninguno de los dos. Esto define **un único
vocabulario** —11 sectores en castellano, cinco regiones, tipos finos— y la traducción a él desde
las tres fuentes posibles: Yahoo, el Sheet y lo que el usuario corrija a mano.

Reglas de diseño:
- Un texto que no se reconoce **pasa tal cual** (recortado): nunca se inventa una categoría. Un
  sector "Soberano" del Sheet sigue siendo "Soberano".
- "Liquidez" en el sector del Sheet es un **rol** (FCIs que funcionan como caja, ver
  `salud_engine.SECTORES_LIQUIDOS`), no un sector: ninguna fuente automática lo pisa.
- La renta fija y los FCI quedan fuera de la clasificación automática en esta etapa: para ellos
  manda el Sheet (Yahoo no los cubre).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .clasificacion_instrumentos import es_cedear, sin_acentos

# ---------------------------------------------------------------------------------------------
# Vocabulario canónico
# ---------------------------------------------------------------------------------------------

REGION_EEUU = "EEUU"
REGION_ARGENTINA = "Argentina"
REGION_DESARROLLADOS = "Desarrollados ex-EEUU"
REGION_EMERGENTES = "Emergentes"
REGION_GLOBAL = "Global"
REGIONES = (REGION_EEUU, REGION_ARGENTINA, REGION_DESARROLLADOS, REGION_EMERGENTES, REGION_GLOBAL)

SECTORES = (
    "Tecnología",
    "Comunicaciones",
    "Consumo discrecional",
    "Consumo básico",
    "Energía",
    "Financiero",
    "Salud",
    "Industria",
    "Materiales",
    "Inmobiliario",
    "Servicios públicos",
)
# Sectores que sólo aparecen en ETFs (o en la renta fija/caja del Sheet).
SECTORES_EXTRA = ("Diversificado", "Materias primas", "Cripto", "Renta fija", "Liquidez")

TIPO_ACCION = "Acción"
TIPO_CEDEAR_ACCION = "CEDEAR-acción"
TIPO_CEDEAR_ETF = "CEDEAR-ETF"
TIPO_BONO = "Bono"
TIPO_ON = "ON"
TIPO_LETRA = "Letra"
TIPO_FCI = "FCI"
TIPOS = (TIPO_ACCION, TIPO_CEDEAR_ACCION, TIPO_CEDEAR_ETF, TIPO_BONO, TIPO_ON, TIPO_LETRA, TIPO_FCI)

# `tipo_base`: la familia gruesa. Es la que entienden los objetivos de Rebalanceo y lo que hoy
# decide `_es_cedear/_es_renta_*`; el tipo fino sólo distingue acción de ETF dentro de CEDEAR.
TIPO_BASE_CEDEAR = "CEDEAR"
TIPOS_BASE = (TIPO_ACCION, TIPO_BASE_CEDEAR, TIPO_BONO, TIPO_ON, TIPO_LETRA, TIPO_FCI)
TIPOS_BASE_SIN_AUTO = frozenset({TIPO_BONO, TIPO_ON, TIPO_LETRA, TIPO_FCI})

CAMPOS = ("tipo", "sector", "industria", "pais", "region")

FUENTE_MANUAL = "manual"
FUENTE_SEED = "seed"
FUENTE_YAHOO = "yahoo"
FUENTE_SHEET = "sheet"


def _clave(texto) -> str:
    """Forma de comparación: sin acentos, minúsculas, espacios colapsados."""
    return re.sub(r"\s+", " ", sin_acentos(str(texto or ""))).strip()


def _limpio(texto) -> str | None:
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    return t or None


# ---------------------------------------------------------------------------------------------
# Sector
# ---------------------------------------------------------------------------------------------

# Sector de Yahoo (inglés, clasificación de Morningstar) y sinónimos en castellano que aparecen
# en el Sheet -> sector canónico. Claves en forma `_clave`.
ALIAS_SECTOR: dict[str, str] = {}


def _alias(canonico: str, *claves: str) -> None:
    ALIAS_SECTOR[_clave(canonico)] = canonico
    for c in claves:
        ALIAS_SECTOR[_clave(c)] = canonico


_alias("Tecnología", "technology", "tech", "it", "informatica", "tecnologica", "tecnologicas",
       "software", "semiconductores", "information technology")
_alias("Comunicaciones", "communication services", "communications", "telecomunicaciones",
       "telecom", "telecomunicacion", "medios", "media")
_alias("Consumo discrecional", "consumer cyclical", "consumer discretionary", "consumo ciclico",
       "consumo no basico", "retail")
_alias("Consumo básico", "consumer defensive", "consumer staples", "consumo masivo",
       "cosumo masivo", "consumo defensivo", "alimentos", "alimentacion")
_alias("Energía", "energy", "petroleo", "petroleo y gas", "oil & gas", "oil and gas",
       "hidrocarburos")
_alias("Financiero", "financial services", "financials", "financial", "finanzas", "financieras",
       "financiera", "bancos", "banca", "bancario")
_alias("Salud", "healthcare", "health care", "health", "farmaceutica", "farmaceuticas", "pharma")
_alias("Industria", "industrials", "industrial", "industriales")
_alias("Materiales", "basic materials", "materials", "materiales basicos", "mineria",
       "siderurgia")
_alias("Inmobiliario", "real estate", "reit", "reits", "inmobiliaria", "inmobiliarias")
_alias("Servicios públicos", "utilities", "utility", "servicios publicos")
_alias("Diversificado", "indice", "indices", "index", "diversificada", "broad market")
_alias("Materias primas", "commodities", "commodity", "materia prima")
_alias("Cripto", "crypto", "criptomonedas", "cripto activos", "criptoactivos",
       "digital assets")
_alias("Renta fija", "fixed income")
_alias("Liquidez")


def sector_canonico(texto) -> str | None:
    """Sector en el vocabulario canónico, o el texto original (recortado) si no se reconoce.

    Sirve igual para el sector de Yahoo ("Consumer Defensive"), para el del Sheet ("Cosumo
    Masivo", "tecnologia") y para la categoría de un objetivo de Rebalanceo. Nunca inventa: lo que
    no está en `ALIAS_SECTOR` vuelve como vino.
    """
    limpio = _limpio(texto)
    if limpio is None:
        return None
    return ALIAS_SECTOR.get(_clave(limpio), limpio)


def es_liquidez(sector) -> bool:
    return "liquidez" in _clave(sector)


# ---------------------------------------------------------------------------------------------
# Industria
# ---------------------------------------------------------------------------------------------

# Las industrias más comunes del universo de CEDEARs. Una que no esté acá se muestra en inglés:
# traducir mal es peor que no traducir.
_INDUSTRIAS_ES = {
    "semiconductors": "Semiconductores",
    "semiconductor equipment & materials": "Equipos para semiconductores",
    "software - infrastructure": "Software de infraestructura",
    "software - application": "Software de aplicaciones",
    "consumer electronics": "Electrónica de consumo",
    "computer hardware": "Hardware",
    "communication equipment": "Equipos de comunicación",
    "information technology services": "Servicios de TI",
    "internet content & information": "Internet: contenidos",
    "internet retail": "Comercio electrónico",
    "telecom services": "Telecomunicaciones",
    "entertainment": "Entretenimiento",
    "electronic gaming & multimedia": "Videojuegos",
    "beverages - non-alcoholic": "Bebidas sin alcohol",
    "beverages - brewers": "Cerveceras",
    "beverages - wineries & distilleries": "Bodegas y destilerías",
    "household & personal products": "Cuidado personal y hogar",
    "packaged foods": "Alimentos envasados",
    "tobacco": "Tabaco",
    "discount stores": "Hipermercados",
    "grocery stores": "Supermercados",
    "farm products": "Agro",
    "confectioners": "Golosinas",
    "restaurants": "Restaurantes",
    "auto manufacturers": "Automotrices",
    "apparel retail": "Indumentaria (minorista)",
    "footwear & accessories": "Calzado y accesorios",
    "home improvement retail": "Mejoras para el hogar",
    "specialty retail": "Comercio especializado",
    "travel services": "Servicios de viaje",
    "lodging": "Hotelería",
    "resorts & casinos": "Casinos y resorts",
    "oil & gas integrated": "Petroleras integradas",
    "oil & gas e&p": "Petróleo y gas: exploración y producción",
    "oil & gas midstream": "Petróleo y gas: transporte",
    "oil & gas refining & marketing": "Refinación",
    "oil & gas equipment & services": "Servicios petroleros",
    "uranium": "Uranio",
    "banks - diversified": "Bancos diversificados",
    "banks - regional": "Bancos regionales",
    "credit services": "Servicios de crédito",
    "capital markets": "Mercados de capitales",
    "asset management": "Gestión de activos",
    "insurance - diversified": "Seguros diversificados",
    "insurance brokers": "Brokers de seguros",
    "financial data & stock exchanges": "Datos financieros y bolsas",
    "drug manufacturers - general": "Laboratorios",
    "drug manufacturers - specialty & generic": "Laboratorios (genéricos)",
    "biotechnology": "Biotecnología",
    "medical devices": "Dispositivos médicos",
    "healthcare plans": "Prepagas",
    "diagnostics & research": "Diagnóstico e investigación",
    "aerospace & defense": "Aeroespacial y defensa",
    "airlines": "Aerolíneas",
    "railroads": "Ferrocarriles",
    "integrated freight & logistics": "Logística",
    "farm & heavy construction machinery": "Maquinaria pesada",
    "specialty industrial machinery": "Maquinaria industrial",
    "conglomerates": "Conglomerados",
    "gold": "Oro",
    "silver": "Plata",
    "copper": "Cobre",
    "steel": "Acero",
    "aluminum": "Aluminio",
    "other industrial metals & mining": "Minería",
    "agricultural inputs": "Insumos agrícolas",
    "specialty chemicals": "Química especializada",
    "chemicals": "Química",
    "building materials": "Materiales de construcción",
    "utilities - regulated electric": "Eléctricas reguladas",
    "utilities - independent power producers": "Generación eléctrica",
    "utilities - regulated gas": "Distribución de gas",
    "utilities - renewable": "Energías renovables",
    "utilities - diversified": "Servicios públicos diversificados",
    "reit - retail": "REIT comercial",
    "real estate - diversified": "Inmobiliarias diversificadas",
    "solar": "Solar",
}


def industria_legible(industria_raw) -> str | None:
    limpio = _limpio(industria_raw)
    if limpio is None:
        return None
    return _INDUSTRIAS_ES.get(_clave(limpio), limpio)


# ---------------------------------------------------------------------------------------------
# País y región
# ---------------------------------------------------------------------------------------------

CLASE_DESARROLLADO = "desarrollado"
CLASE_EMERGENTE = "emergente"
CLASE_FRONTERA = "frontera"
CLASE_STANDALONE = "standalone"
CLASE_SEDE_LEGAL = "sede_legal"

# País canónico (castellano) -> (clase MSCI, sinónimos). Los sinónimos cubren el nombre en inglés
# de Yahoo y lo que suele aparecer en el Sheet (códigos ISO, abreviaturas).
_PAISES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Estados Unidos": (CLASE_DESARROLLADO, ("united states", "usa", "us", "eeuu", "ee.uu.", "ee uu",
                                            "estados unidos de america", "united states of america")),
    "Argentina": (CLASE_STANDALONE, ("ar", "arg")),
    # Desarrollados
    "Canadá": (CLASE_DESARROLLADO, ("canada", "ca")),
    "Austria": (CLASE_DESARROLLADO, ("at",)),
    "Bélgica": (CLASE_DESARROLLADO, ("belgium", "be")),
    "Dinamarca": (CLASE_DESARROLLADO, ("denmark", "dk")),
    "Finlandia": (CLASE_DESARROLLADO, ("finland", "fi")),
    "Francia": (CLASE_DESARROLLADO, ("france", "fr")),
    "Alemania": (CLASE_DESARROLLADO, ("germany", "de")),
    "Irlanda": (CLASE_DESARROLLADO, ("ireland", "ie")),
    "Israel": (CLASE_DESARROLLADO, ("il",)),
    "Italia": (CLASE_DESARROLLADO, ("italy", "it")),
    "Países Bajos": (CLASE_DESARROLLADO, ("netherlands", "the netherlands", "holanda", "nl")),
    "Noruega": (CLASE_DESARROLLADO, ("norway", "no")),
    "Portugal": (CLASE_DESARROLLADO, ("pt",)),
    "España": (CLASE_DESARROLLADO, ("spain", "es")),
    "Suecia": (CLASE_DESARROLLADO, ("sweden", "se")),
    "Suiza": (CLASE_DESARROLLADO, ("switzerland", "ch")),
    "Reino Unido": (CLASE_DESARROLLADO, ("united kingdom", "uk", "gb", "inglaterra", "great britain")),
    "Australia": (CLASE_DESARROLLADO, ("au",)),
    "Hong Kong": (CLASE_DESARROLLADO, ("hk",)),
    "Japón": (CLASE_DESARROLLADO, ("japan", "jp")),
    "Nueva Zelanda": (CLASE_DESARROLLADO, ("new zealand", "nz")),
    "Singapur": (CLASE_DESARROLLADO, ("singapore", "sg")),
    # Emergentes
    "Brasil": (CLASE_EMERGENTE, ("brazil", "br")),
    "Chile": (CLASE_EMERGENTE, ("cl",)),
    "Colombia": (CLASE_EMERGENTE, ("co",)),
    "México": (CLASE_EMERGENTE, ("mexico", "mx")),
    "Perú": (CLASE_EMERGENTE, ("peru", "pe")),
    "República Checa": (CLASE_EMERGENTE, ("czech republic", "czechia", "cz")),
    "Egipto": (CLASE_EMERGENTE, ("egypt", "eg")),
    "Grecia": (CLASE_EMERGENTE, ("greece", "gr")),
    "Hungría": (CLASE_EMERGENTE, ("hungary", "hu")),
    "Kuwait": (CLASE_EMERGENTE, ("kw",)),
    "Polonia": (CLASE_EMERGENTE, ("poland", "pl")),
    "Qatar": (CLASE_EMERGENTE, ("qa",)),
    "Arabia Saudita": (CLASE_EMERGENTE, ("saudi arabia", "sa")),
    "Sudáfrica": (CLASE_EMERGENTE, ("south africa", "za")),
    "Turquía": (CLASE_EMERGENTE, ("turkey", "turkiye", "tr")),
    "Emiratos Árabes Unidos": (CLASE_EMERGENTE, ("united arab emirates", "uae", "ae")),
    "China": (CLASE_EMERGENTE, ("cn",)),
    "India": (CLASE_EMERGENTE, ("in",)),
    "Indonesia": (CLASE_EMERGENTE, ("id",)),
    "Corea del Sur": (CLASE_EMERGENTE, ("south korea", "korea", "republic of korea", "kr", "corea")),
    "Malasia": (CLASE_EMERGENTE, ("malaysia", "my")),
    "Filipinas": (CLASE_EMERGENTE, ("philippines", "ph")),
    "Taiwán": (CLASE_EMERGENTE, ("taiwan", "tw")),
    "Tailandia": (CLASE_EMERGENTE, ("thailand", "th")),
    # Frontera / sin clasificar por MSCI: se agrupan con emergentes.
    "Uruguay": (CLASE_FRONTERA, ("uy",)),
    "Panamá": (CLASE_FRONTERA, ("panama", "pa")),
    "Vietnam": (CLASE_FRONTERA, ("vn",)),
    "Nigeria": (CLASE_FRONTERA, ("ng",)),
    "Kazajistán": (CLASE_FRONTERA, ("kazakhstan", "kz")),
    "Kenia": (CLASE_FRONTERA, ("kenya", "ke")),
    "Marruecos": (CLASE_FRONTERA, ("morocco", "ma")),
    "Rumania": (CLASE_FRONTERA, ("romania", "ro")),
    # Sede legal: el domicilio societario no dice nada de la exposición económica. Se conservan
    # como país pero sin región, para que el seed o el usuario la corrijan.
    "Luxemburgo": (CLASE_SEDE_LEGAL, ("luxembourg", "lu")),
    "Bermudas": (CLASE_SEDE_LEGAL, ("bermuda", "bm")),
    "Islas Caimán": (CLASE_SEDE_LEGAL, ("cayman islands", "ky")),
    "Islas Vírgenes Británicas": (CLASE_SEDE_LEGAL, ("british virgin islands", "vg")),
    "Jersey": (CLASE_SEDE_LEGAL, ("je",)),
    "Guernsey": (CLASE_SEDE_LEGAL, ("gg",)),
    "Bahamas": (CLASE_SEDE_LEGAL, ("bs",)),
    "Curazao": (CLASE_SEDE_LEGAL, ("curacao", "cw")),
}

_PAIS_POR_CLAVE: dict[str, str] = {}
for _canon, (_clase, _sins) in _PAISES.items():
    _PAIS_POR_CLAVE[_clave(_canon)] = _canon
    for _s in _sins:
        _PAIS_POR_CLAVE[_clave(_s)] = _canon


def pais_canonico(texto) -> str | None:
    """País en castellano, o el texto original si no se reconoce."""
    limpio = _limpio(texto)
    if limpio is None:
        return None
    return _PAIS_POR_CLAVE.get(_clave(limpio), limpio)


def clase_msci(pais) -> str | None:
    canon = pais_canonico(pais)
    if canon is None or canon not in _PAISES:
        return None
    return _PAISES[canon][0]


def region_de_pais(pais) -> str | None:
    """Región del país según la clasificación de MSCI.

    Argentina es "standalone" para MSCI pero acá es una región propia (es el mercado local). La
    frontera se agrupa con emergentes. Un país de sede legal (Luxemburgo, Caimán…) no tiene
    región: no dice dónde está el negocio.
    """
    canon = pais_canonico(pais)
    if canon == "Estados Unidos":
        return REGION_EEUU
    if canon == "Argentina":
        return REGION_ARGENTINA
    clase = clase_msci(canon)
    if clase == CLASE_DESARROLLADO:
        return REGION_DESARROLLADOS
    if clase in (CLASE_EMERGENTE, CLASE_FRONTERA):
        return REGION_EMERGENTES
    return None


def region_canonica(texto) -> str | None:
    """Una región escrita a mano ("emergentes", "eeuu", "global") en su forma canónica."""
    clave = _clave(texto)
    if not clave:
        return None
    for region in REGIONES:
        if _clave(region) == clave:
            return region
    alias = {
        "usa": REGION_EEUU, "estados unidos": REGION_EEUU, "us": REGION_EEUU,
        "arg": REGION_ARGENTINA, "ar": REGION_ARGENTINA,
        "desarrollados": REGION_DESARROLLADOS, "desarrollados ex eeuu": REGION_DESARROLLADOS,
        "desarrollado": REGION_DESARROLLADOS, "developed": REGION_DESARROLLADOS,
        "emergente": REGION_EMERGENTES, "emerging": REGION_EMERGENTES, "em": REGION_EMERGENTES,
        "mundo": REGION_GLOBAL, "world": REGION_GLOBAL,
    }
    return alias.get(clave, _limpio(texto))


# ---------------------------------------------------------------------------------------------
# ETFs: región y sector desde la categoría de Yahoo
# ---------------------------------------------------------------------------------------------

# (subcadena de la categoría, sector). La primera que matchea gana: lo específico va arriba.
_SECTOR_POR_CATEGORIA = (
    ("digital assets", "Cripto"),
    ("precious metals", "Materiales"),
    ("commodities", "Materias primas"),
    ("technology", "Tecnología"),
    ("communications", "Comunicaciones"),
    ("consumer cyclical", "Consumo discrecional"),
    ("consumer defensive", "Consumo básico"),
    ("energy", "Energía"),
    ("financial", "Financiero"),
    ("health", "Salud"),
    ("industrials", "Industria"),
    ("infrastructure", "Industria"),
    ("natural resources", "Materiales"),
    ("real estate", "Inmobiliario"),
    ("utilities", "Servicios públicos"),
    ("bond", "Renta fija"),
    ("government", "Renta fija"),
    ("treasury", "Renta fija"),
    ("muni", "Renta fija"),
)

_EMERGENTES_CATEGORIA = ("emerging", "latin america", "china", "india", "pacific/asia ex-japan",
                         "miscellaneous region", "brazil")
_DESARROLLADOS_CATEGORIA = ("foreign", "europe", "japan", "diversified pacific")
_GLOBAL_CATEGORIA = ("global", "world", "commodities", "precious metals", "digital assets")


def clasificar_etf(categoria) -> tuple[str | None, str | None]:
    """`(sector, region)` de un ETF a partir de la `category` de Yahoo.

    Un ETF sin categoría queda sin clasificar (no se asume EEUU): mejor un hueco visible que un
    dato inventado.
    """
    clave = _clave(categoria)
    if not clave:
        return None, None
    sector = "Diversificado"
    for sub, sec in _SECTOR_POR_CATEGORIA:
        if sub in clave:
            sector = sec
            break
    if any(s in clave for s in _EMERGENTES_CATEGORIA):
        region = REGION_EMERGENTES
    elif any(s in clave for s in _DESARROLLADOS_CATEGORIA):
        region = REGION_DESARROLLADOS
    elif any(s in clave for s in _GLOBAL_CATEGORIA):
        region = REGION_GLOBAL
    else:
        region = REGION_EEUU
    return sector, region


# ---------------------------------------------------------------------------------------------
# Tipo
# ---------------------------------------------------------------------------------------------

def tipo_base_de(tipo_texto) -> str | None:
    """Familia gruesa a partir de un tipo en texto libre (Sheet, catálogo o tipo fino).

    Mismas subcadenas que `market_data/precios.py` (`_es_cedear`, `_es_renta_fija`, ...), que no
    se tocan: esto sólo las ordena en un vocabulario cerrado. `None` si no se reconoce.
    """
    t = _clave(tipo_texto)
    if not t:
        return None
    tokens = set(re.split(r"[\s/\-]+", t))
    if es_cedear(t):
        return TIPO_BASE_CEDEAR
    if "fci" in tokens or "fondo comun" in t:
        return TIPO_FCI
    if "obligacion negociable" in t or tokens & {"on", "ons"}:
        return TIPO_ON
    if "letra" in t or "lecap" in t or "lede" in t or "lecer" in t:
        return TIPO_LETRA
    if "bono" in t or "boncer" in t:
        return TIPO_BONO
    if "accion" in t:
        return TIPO_ACCION
    return None


def tipo_fino(tipo_catalogo, quote_type=None) -> str | None:
    """Tipo fino: distingue acción de ETF dentro de los CEDEARs (por el `quoteType` de Yahoo).

    Un CEDEAR sin `quoteType` (Yahoo todavía no respondió) queda como "CEDEAR-acción" sólo si
    Yahoo no dijo nada: la mayoría del universo son acciones, y la ingesta lo corrige al llegar.
    """
    base = tipo_base_de(tipo_catalogo)
    if base == TIPO_BASE_CEDEAR or (base is None and _clave(quote_type) == "etf"):
        return TIPO_CEDEAR_ETF if _clave(quote_type) == "etf" else TIPO_CEDEAR_ACCION
    return base


def tipo_base_de_fino(tipo) -> str | None:
    if tipo in (TIPO_CEDEAR_ACCION, TIPO_CEDEAR_ETF):
        return TIPO_BASE_CEDEAR
    return tipo_base_de(tipo)


# ---------------------------------------------------------------------------------------------
# Símbolos: variantes de moneda y símbolo en Yahoo
# ---------------------------------------------------------------------------------------------

_SUFIJOS_VARIANTE = (".D", ".C", "D", "C")
_RUIDO_DESCRIPCION = re.compile(r"\b(cedears?|esc\.?|escrit\w*|adr|etf|usd?c?|the|inc|corp\w*|co|sa|s\.a\.?)\b")


# Palabras que comparten emisoras distintas: no prueban que dos descripciones sean la misma.
_PALABRAS_GENERICAS = frozenset({
    "bank", "banco", "group", "grupo", "holding", "holdings", "select", "sector", "spdr", "state",
    "street", "trust", "ishares", "index", "fund", "international", "company", "corporation",
    "limited", "global",
})


def _descripcion_comparable(texto: str) -> str:
    t = _clave(texto)
    t = _RUIDO_DESCRIPCION.sub(" ", t)
    return re.sub(r"[^a-z0-9]", "", t)


def _palabras_distintivas(texto: str) -> set[str]:
    t = _RUIDO_DESCRIPCION.sub(" ", _clave(texto))
    return {p for p in re.split(r"[^a-z0-9]+", t) if len(p) >= 4 and p not in _PALABRAS_GENERICAS}


def _descripciones_parecidas(a: str, b: str) -> bool:
    """¿Son la misma emisora? El catálogo trunca descripciones a ~30 caracteres, agrega
    "Esc."/"USD" en las variantes y a veces abrevia ("Bristol M. Squibb"), así que alcanza con
    que coincida el prefijo o que compartan una palabra distintiva. Es una condición más, no la
    única: además hace falta el sufijo de variante y el cruce de moneda (ver `mapa_variantes`)."""
    da, db = _descripcion_comparable(a), _descripcion_comparable(b)
    if not da or not db:
        return False
    n = min(len(da), len(db), 18)
    if difflib.SequenceMatcher(None, da[:n], db[:n]).ratio() >= 0.8:
        return True
    return bool(_palabras_distintivas(a) & _palabras_distintivas(b))


def mapa_variantes(catalogo: list[dict], variantes_seed: dict[str, str] | None = None) -> dict[str, str]:
    """`{simbolo_variante: ticker_base}` para las variantes de moneda del catálogo de IOL.

    Un mismo emisor cotiza en pesos (`AAPL`), dólar cable (`AAPLC`) y MEP (`AAPLD`). Para
    clasificarlo y buscarle pares es **uno solo**. Una variante es: el símbolo base más un sufijo
    `D`/`C`/`.D`/`.C`, cotizando en dólares cuando la base cotiza en pesos, y con la misma
    emisora en la descripción. Las tres condiciones hacen falta: `BBD` (Bradesco, en pesos) no es
    variante de `BB` (BlackBerry) y `BA.C` (Bank of America) no lo es de `BA` (Boeing).

    `catalogo` son las entradas de `catalogo_instrumentos.cargar_catalogo()` (con `simbolo`,
    `descripcion`, `moneda`). `variantes_seed` agrega los casos que la regla no ve (`GOGLD` ->
    `GOOGL`, `TGN4D` -> `TGNO4`).
    """
    por_simbolo = {e["simbolo"].upper(): e for e in catalogo if e.get("simbolo")}
    mapa: dict[str, str] = {}
    for simbolo, entrada in por_simbolo.items():
        if (entrada.get("moneda") or "").upper() != "USD":
            continue
        for sufijo in _SUFIJOS_VARIANTE:
            if not simbolo.endswith(sufijo) or len(simbolo) <= len(sufijo):
                continue
            base = simbolo[: -len(sufijo)]
            entrada_base = por_simbolo.get(base)
            if entrada_base is None or (entrada_base.get("moneda") or "").upper() != "ARS":
                continue
            if _descripciones_parecidas(entrada.get("descripcion", ""), entrada_base.get("descripcion", "")):
                mapa[simbolo] = base
                break
    for variante, base in (variantes_seed or {}).items():
        mapa[variante.upper()] = base.upper()
    # Cadenas (`BA.CD` -> `BA.C`, que no es variante de nada) ya quedan resueltas; por las dudas
    # se aplana para que ninguna base sea a su vez variante.
    for variante in list(mapa):
        destino = mapa[variante]
        vistos = {variante}
        while destino in mapa and destino not in vistos:
            vistos.add(destino)
            destino = mapa[destino]
        mapa[variante] = destino
    return mapa


def ticker_base(simbolo, variantes: dict[str, str]) -> str:
    s = (simbolo or "").strip().upper()
    return variantes.get(s, s)


METODO_MANUAL = "manual"
METODO_SEED = "seed"
METODO_SUBYACENTE = "subyacente"
METODO_IDENTIDAD = "identidad"
METODO_BA = "ba"
METODO_NO_APTO = "no_apto"


def simbolo_yahoo(
    ticker: str,
    tipo_base: str | None,
    simbolos_seed: dict[str, str] | None = None,
    subyacente_resuelto: str | None = None,
    override: str | None = None,
) -> tuple[str | None, str]:
    """`(simbolo_en_yahoo, metodo)` del emisor `ticker` (ya en su forma base).

    Precedencia: override del usuario > seed versionado > subyacente ya resuelto por el pipeline
    de precios (`EstadoMarketDataTicker.simbolo_subyacente`, sólo si quedó `ok`) > regla general.
    La regla general: un CEDEAR es el mismo símbolo en EE.UU. (con `.`→`-`, que es como Yahoo
    escribe las clases: `BRK.B`→`BRK-B`); una acción local es `TICKER.BA`. Renta fija y FCI no
    tienen símbolo en Yahoo.
    """
    t = (ticker or "").strip().upper()
    if not t:
        return None, METODO_NO_APTO
    if override:
        return override.strip().upper(), METODO_MANUAL
    if simbolos_seed and t in simbolos_seed:
        return simbolos_seed[t], METODO_SEED
    if tipo_base in TIPOS_BASE_SIN_AUTO:
        return None, METODO_NO_APTO
    if subyacente_resuelto:
        return subyacente_resuelto.strip().upper(), METODO_SUBYACENTE
    if tipo_base == TIPO_BASE_CEDEAR:
        if not re.fullmatch(r"[A-Z0-9.\-]+", t):
            return None, METODO_NO_APTO
        return t.replace(".", "-"), METODO_IDENTIDAD
    if tipo_base == TIPO_ACCION:
        return f"{t}.BA", METODO_BA
    return None, METODO_NO_APTO


# ---------------------------------------------------------------------------------------------
# Traducción de la respuesta de Yahoo
# ---------------------------------------------------------------------------------------------

def clasificar_desde_yahoo(info: dict, tipo_base: str | None) -> dict:
    """Los campos normalizados de clasificación a partir de lo que devolvió Yahoo.

    `info` es la salida de `yahoo.fetch_fundamentales` (claves de `get_info()` ya filtradas). Una
    acción toma sector/industria/país directo; un ETF los deriva de su `category`.
    """
    quote_type = _limpio(info.get("quoteType"))
    es_etf = _clave(quote_type) == "etf"
    pais_raw = _limpio(info.get("country"))
    sector_raw = _limpio(info.get("sector"))
    industria_raw = _limpio(info.get("industry"))
    categoria = _limpio(info.get("category"))

    if es_etf:
        sector, region = clasificar_etf(categoria)
        pais = None
        industria = categoria
    else:
        sector = sector_canonico(sector_raw)
        pais = pais_canonico(pais_raw)
        region = region_de_pais(pais)
        industria = industria_legible(industria_raw)

    if tipo_base == TIPO_ACCION:
        tipo = TIPO_ACCION
    else:
        tipo = tipo_fino(tipo_base or "", quote_type)

    return {
        "quote_type": quote_type,
        "nombre": _limpio(info.get("longName") or info.get("shortName")),
        "tipo": tipo,
        "sector_raw": sector_raw,
        "sector": sector,
        "industria_raw": industria_raw if not es_etf else categoria,
        "industria": industria,
        "pais_raw": pais_raw,
        "pais": pais,
        "region": region,
        "clase_msci": clase_msci(pais) if pais else None,
        "categoria_etf_raw": categoria,
        "fund_family": _limpio(info.get("fundFamily")),
    }


# ---------------------------------------------------------------------------------------------
# Resolución: qué fuente manda para cada campo
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ClasificacionResuelta:
    """La clasificación final de un ticker, con la fuente de cada campo.

    `fuentes[campo]` ∈ {"manual", "seed", "yahoo", "sheet", None}. `None` = sin dato.
    """
    tipo: str | None = None
    tipo_base: str | None = None
    sector: str | None = None
    industria: str | None = None
    pais: str | None = None
    region: str | None = None
    fuentes: dict = field(default_factory=dict)

    def get(self, campo: str):
        return getattr(self, campo, None)


def _primero(*candidatos: tuple[object, str]) -> tuple[object, str | None]:
    for valor, fuente in candidatos:
        if valor not in (None, ""):
            return valor, fuente
    return None, None


def resolver(
    override: dict | None = None,
    seed: dict | None = None,
    auto: dict | None = None,
    sheet: dict | None = None,
) -> ClasificacionResuelta:
    """Clasificación final, campo por campo: manual > seed > yahoo > sheet.

    - `override`: lo que el usuario corrigió desde la app (`{campo: valor}`).
    - `seed`: correcciones versionadas (`catalogos/clasificacion_seed.json`, p.ej. VIST→Argentina).
    - `auto`: lo que se derivó de Yahoo (`clasificacion_auto`, ya normalizado).
    - `sheet`: la ficha del Sheet o de la watchlist (`tipo_instrumento`, `sector`, `pais`), cruda.

    Excepciones, en orden:
    - "Liquidez" en el sector del Sheet es un rol: gana sobre seed y Yahoo (no sobre el usuario).
    - Renta fija y FCI no tienen clasificación automática: para ellos el Sheet gana sobre Yahoo
      en sector y país.
    - El país "Argentina" del Sheet en un CEDEAR es la plaza donde cotiza, no el emisor: se
      ignora (KO, SPY y EWZ figuraban así).
    """
    override = override or {}
    seed = seed or {}
    auto = auto or {}
    sheet = sheet or {}

    # -- tipo --
    tipo_sheet_raw = _limpio(sheet.get("tipo_instrumento"))
    tipo_sheet = tipo_base_de(tipo_sheet_raw) or tipo_sheet_raw
    if tipo_sheet == TIPO_BASE_CEDEAR:
        tipo_sheet = TIPO_CEDEAR_ETF if "etf" in _clave(tipo_sheet_raw).split() else TIPO_CEDEAR_ACCION
    tipo, f_tipo = _primero(
        (override.get("tipo"), FUENTE_MANUAL),
        (seed.get("tipo"), FUENTE_SEED),
        (auto.get("tipo"), FUENTE_YAHOO),
        (tipo_sheet, FUENTE_SHEET),
    )
    base = tipo_base_de_fino(tipo)
    sin_auto = base in TIPOS_BASE_SIN_AUTO

    # -- sector --
    sector_sheet = sector_canonico(sheet.get("sector"))
    candidatos_sector = [(sector_canonico(override.get("sector")), FUENTE_MANUAL)]
    if es_liquidez(sector_sheet):
        candidatos_sector.append(("Liquidez", FUENTE_SHEET))
    if sin_auto:
        candidatos_sector.append((sector_sheet, FUENTE_SHEET))
    candidatos_sector += [
        (sector_canonico(seed.get("sector")), FUENTE_SEED),
        (auto.get("sector"), FUENTE_YAHOO),
        (sector_sheet, FUENTE_SHEET),
    ]
    sector, f_sector = _primero(*candidatos_sector)

    # -- industria --
    industria, f_industria = _primero(
        (_limpio(override.get("industria")), FUENTE_MANUAL),
        (_limpio(seed.get("industria")), FUENTE_SEED),
        (auto.get("industria"), FUENTE_YAHOO),
    )

    # -- país --
    pais_sheet = pais_canonico(sheet.get("pais"))
    if base == TIPO_BASE_CEDEAR and pais_sheet == "Argentina":
        pais_sheet = None
    candidatos_pais = [(pais_canonico(override.get("pais")), FUENTE_MANUAL)]
    if sin_auto:
        candidatos_pais.append((pais_sheet, FUENTE_SHEET))
    candidatos_pais += [
        (pais_canonico(seed.get("pais")), FUENTE_SEED),
        (auto.get("pais"), FUENTE_YAHOO),
        (pais_sheet, FUENTE_SHEET),
    ]
    pais, f_pais = _primero(*candidatos_pais)

    # -- región --
    # Una corrección de país (manual o seed) arrastra la región salvo que también se haya
    # corregido la región: si no, MELI con país corregido seguiría en la región de su sede.
    candidatos_region = [
        (region_canonica(override.get("region")), FUENTE_MANUAL),
        (region_canonica(seed.get("region")), FUENTE_SEED),
    ]
    if f_pais in (FUENTE_MANUAL, FUENTE_SEED):
        candidatos_region.append((region_de_pais(pais), f_pais))
    if not sin_auto:
        candidatos_region.append((auto.get("region"), FUENTE_YAHOO))
    candidatos_region.append((region_de_pais(pais), f_pais))
    region, f_region = _primero(*candidatos_region)

    return ClasificacionResuelta(
        tipo=tipo,
        tipo_base=base,
        sector=sector,
        industria=industria,
        pais=pais,
        region=region,
        fuentes={
            "tipo": f_tipo,
            "sector": f_sector,
            "industria": f_industria,
            "pais": f_pais,
            "region": f_region,
        },
    )
