"""Catálogo de instrumentos de IOL: el universo de símbolos que se puede agregar a la watchlist.

Lee el archivo que produce `scripts/iol_catalogo.py` (ver su docstring para cómo se genera y qué
cuesta). La gracia de tomar el ticker de acá y no de texto libre es que **el símbolo es el de IOL
por construcción**: `market_data/precios.py` puede pedir la cotización y usarla tal cual, sin la
calibración de escala que hace falta cuando el ticker (y su unidad) vienen del Sheet.

El archivo NO trae un campo de tipo de instrumento: el tipo está implícito en el prefijo de
`paneles` (`"Acciones/CEDEARs"`, `"Bonos/Todos"`, ...). `_tipo_de` lo deriva a los strings que los
clasificadores de `precios.py` (`_es_cedear`, `_es_renta_variable`, `_es_renta_fija`, `_es_fci`) ya
reconocen, así que la familia de un instrumento del catálogo queda bien resuelta sin tocar aquello.
"""
import json
import os
from unicodedata import combining, normalize

# Prefijo de panel -> tipo. Los strings de la derecha los tienen que seguir matcheando los
# clasificadores de `market_data/precios.py`; ver `_TIPOS` en la docstring del módulo.
_TIPO_POR_PANEL = {
    "acciones": "Acción",
    "bonos": "Bono",
    "obligacionesnegociables": "ON",
    "letras": "Letra",
    "fci": "FCI",
}

# Orden de presentación de los chips de filtro en el frontend (de más a menos usado).
TIPOS = ("Acción", "CEDEAR", "Bono", "ON", "Letra", "FCI")

_MONEDAS = {
    "ar$": "ARS",
    "ars": "ARS",
    "peso_argentino": "ARS",
    "us$": "USD",
    "usd": "USD",
    "dolar_estadounidense": "USD",
}

_LIMITE_DEFAULT = 100

# Caché en memoria: (ruta, mtime) -> instrumentos ya normalizados. El archivo son ~2.300 entradas,
# releerlo por request sería gratis igual, pero la búsqueda corre sobre strings ya normalizados.
_cache: dict[tuple[str, float], list[dict]] = {}


def _catalogo_path() -> str:
    """Mismo patrón que `iol_auth._credentials_path()`: override por entorno, y si no, las dos
    ubicaciones conocidas en orden de frescura.

    `/app/data` primero porque es donde `scripts.iol_catalogo` deja la corrida más reciente (volumen
    `backend_data`); `/app/catalogos` es el snapshot versionado en el repo, montado read-only.
    """
    override = os.getenv("IOL_CATALOGO_FILE")
    if override:
        return override

    # Este módulo vive en `<raiz>/app/services/`, así que dos niveles arriba es `<raiz>`: `/app` en
    # el contenedor (donde está montado `catalogos/`) y `backend/` corriendo desde el repo. El
    # tercer candidato cubre ese segundo caso, donde `catalogos/` está en la raíz del repo.
    base = os.path.dirname(__file__)
    candidatos = (
        os.path.join(base, "..", "..", "data", "iol_catalogo.json"),
        os.path.join(base, "..", "..", "catalogos", "iol_catalogo.json"),
        os.path.join(base, "..", "..", "..", "catalogos", "iol_catalogo.json"),
    )
    for ruta in candidatos:
        if os.path.exists(ruta):
            return ruta
    return candidatos[-1]


def _sin_acentos(s: str) -> str:
    return "".join(c for c in normalize("NFD", s) if not combining(c)).lower().strip()


def _normalizar_moneda(moneda: str) -> str:
    """`AR$` / `peso_Argentino` -> ARS, `US$` / `dolar_Estadounidense` -> USD.

    El catálogo es inconsistente (los FCI usan una nomenclatura propia) y además **la moneda que
    declara no siempre es la real** -- hay ONs en dólares listadas como `AR$`. Por eso esto es sólo
    un default de display al dar de alta: la moneda buena es la que devuelve la fuente al cotizar,
    que es la que termina en `PrecioWatchlist.moneda` y la que muestra la pantalla.
    """
    return _MONEDAS.get(_sin_acentos(moneda or "").replace(" ", "_"), "ARS")


def _tipo_de(paneles: list[str]) -> str:
    """Tipo de instrumento a partir de los paneles en los que vive.

    Un símbolo puede estar en varios (78 lo están: `ALUA` es Merval + Merval 25 + Burcap + ...).
    `CEDEAR` gana sobre `Acción` porque es más específico y porque `precios.py` lo trata distinto
    (`_es_cedear` habilita resolver el subyacente en USD); para el resto alcanza el prefijo del
    primer panel, que en los casos multi-panel es siempre de la misma familia.
    """
    for panel in paneles:
        if "cedear" in _sin_acentos(panel):
            return "CEDEAR"
    for panel in paneles:
        prefijo = _sin_acentos(panel.split("/")[0]).replace(" ", "")
        tipo = _TIPO_POR_PANEL.get(prefijo)
        if tipo is not None:
            return tipo
    return ""


def _normalizar(entrada: dict) -> dict | None:
    simbolo = (entrada.get("simbolo") or "").strip()
    if not simbolo:
        return None
    paneles = entrada.get("paneles") or []
    if isinstance(paneles, str):
        paneles = [paneles]
    descripcion = (entrada.get("descripcion") or "").strip() or simbolo
    return {
        "simbolo": simbolo,
        "descripcion": descripcion,
        "tipo": _tipo_de(paneles),
        "moneda": _normalizar_moneda(entrada.get("moneda") or ""),
        "mercado": (entrada.get("mercado") or "").strip().upper() or "BCBA",
        "paneles": paneles,
        # Precalculado para la búsqueda: evita re-normalizar 2.300 strings en cada tecla.
        "_simbolo_norm": _sin_acentos(simbolo),
        "_descripcion_norm": _sin_acentos(descripcion),
    }


def cargar_catalogo() -> list[dict]:
    """Los instrumentos del catálogo, normalizados. Lista vacía si el archivo no está o no se puede
    leer: la watchlist tiene que seguir mostrándose aunque no haya catálogo montado."""
    ruta = _catalogo_path()
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        return []

    clave = (ruta, mtime)
    if clave in _cache:
        return _cache[clave]

    try:
        with open(ruta, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []

    crudos = data.get("instrumentos") if isinstance(data, dict) else data
    if not isinstance(crudos, list):
        return []

    instrumentos = []
    vistos: set[str] = set()
    for entrada in crudos:
        if not isinstance(entrada, dict):
            continue
        item = _normalizar(entrada)
        if item is None or item["simbolo"].upper() in vistos:
            continue
        vistos.add(item["simbolo"].upper())
        instrumentos.append(item)

    _cache.clear()  # sólo interesa la última versión del archivo
    _cache[clave] = instrumentos
    return instrumentos


def obtener(simbolo: str) -> dict | None:
    """La entrada del catálogo para un símbolo exacto (sin distinguir mayúsculas), o None."""
    buscado = (simbolo or "").strip().upper()
    if not buscado:
        return None
    for item in cargar_catalogo():
        if item["simbolo"].upper() == buscado:
            return item
    return None


def _publico(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def conteos_por_tipo(instrumentos: list[dict]) -> dict[str, int]:
    conteos = {tipo: 0 for tipo in TIPOS}
    for item in instrumentos:
        if item["tipo"] in conteos:
            conteos[item["tipo"]] += 1
    return conteos


def buscar(q: str = "", tipo: str = "", limite: int = _LIMITE_DEFAULT) -> dict:
    """Busca en el catálogo por símbolo o descripción.

    Devuelve `{total, conteos_por_tipo, items}`. `total` y `conteos_por_tipo` se calculan sobre
    **todo** lo que matchea `q` (sin aplicar `tipo` ni `limite`), que es lo que necesitan los chips
    de filtro para mostrar cuántos hay de cada familia sin pedir el catálogo entero.

    Orden de relevancia: símbolo exacto, símbolo que empieza con `q`, descripción que empieza con
    `q`, el resto; a igualdad, alfabético por símbolo.
    """
    consulta = _sin_acentos(q or "")
    universo = cargar_catalogo()

    if consulta:
        universo = [
            item for item in universo
            if consulta in item["_simbolo_norm"] or consulta in item["_descripcion_norm"]
        ]

    conteos = conteos_por_tipo(universo)

    filtrados = [item for item in universo if item["tipo"] == tipo] if tipo else universo

    def _relevancia(item: dict) -> tuple[int, str]:
        if not consulta:
            return (0, item["_simbolo_norm"])
        if item["_simbolo_norm"] == consulta:
            return (0, item["_simbolo_norm"])
        if item["_simbolo_norm"].startswith(consulta):
            return (1, item["_simbolo_norm"])
        if item["_descripcion_norm"].startswith(consulta):
            return (2, item["_simbolo_norm"])
        if consulta in item["_simbolo_norm"]:
            return (3, item["_simbolo_norm"])
        return (4, item["_simbolo_norm"])

    ordenados = sorted(filtrados, key=_relevancia)
    tope = max(1, limite)
    return {
        "total": len(filtrados),
        "conteos_por_tipo": conteos,
        "items": [_publico(item) for item in ordenados[:tope]],
    }
