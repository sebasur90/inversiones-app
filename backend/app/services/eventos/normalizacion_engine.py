"""Normalización y deduplicación de noticias y eventos. Puro (sin DB ni red).

El contenido externo es **dato no confiable**: acá se valida y se limpia antes de que llegue a la base.

- URLs: sólo `http`/`https`, con host. La forma normalizada (sin `utm_*`, sin fragmento, sin `www.`, en
  minúsculas el esquema y el host, parámetros ordenados) es la clave para no guardar dos veces la misma
  noticia aunque llegue con distinto tracking.
- Texto: se reduce a texto plano (sin etiquetas ni entidades HTML) y se corta a un largo máximo. Nunca se
  guarda HTML externo para renderizar.
- Fechas: ISO 8601; con zona se pasa a UTC y se guarda naive (como el resto de la app). Fuera de
  1900–2100 se rechaza.

Duplicados de noticias: mismo id del proveedor, misma URL normalizada, o títulos parecidos (Jaccard de las
palabras significativas ≥ `UMBRAL_SIMILITUD`) publicados con menos de `VENTANA_HORAS` de diferencia. Es la
regla que evita crear un evento por cada medio que contó lo mismo.

Duplicados de eventos: misma categoría, fechas a ≤ `TOLERANCIA_DIAS_EVENTO` y títulos parecidos
(≥ `UMBRAL_SIMILITUD_EVENTO`).
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UMBRAL_SIMILITUD = 0.6
VENTANA_HORAS = 48
UMBRAL_SIMILITUD_EVENTO = 0.5
TOLERANCIA_DIAS_EVENTO = 2
MAX_URL = 2000
MAX_TITULO = 300
MAX_FRAGMENTO = 1000

_PARAMS_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|cmpid|ocid|smid|guccounter)$", re.I)
_ETIQUETA = re.compile(r"<[^>]*>")
_ESPACIOS = re.compile(r"\s+")
_PALABRA = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset("""
a al algo ante antes como con contra cual cuando de del desde donde dos durante e el ella ellas ellos en
entre era es esa ese esta este esto estos fue ha han hasta hay la las le les lo los mas mientras muy no
nos o otra otro para pero por porque que se segun ser si sin sobre su sus tambien tras un una uno unos y ya
about above after again against all also an and any are as at be because been before being below between
both but by can could did do does down during each few for from further had has have having he her here
his how i if in into is it its just more most new no nor not now of off on once only or other our out over
own same says said she should so some such than that the their them then there these they this those
through to too under until up very was we were what when where which while who why will with would you
""".split())


def url_valida(url) -> bool:
    if not isinstance(url, str) or not url or len(url) > MAX_URL:
        return False
    try:
        partes = urlsplit(url.strip())
    except ValueError:
        return False
    return partes.scheme.lower() in ("http", "https") and bool(partes.hostname)


def normalizar_url(url) -> str | None:
    """La forma canónica de una URL para deduplicar, o `None` si no es una URL `http(s)` válida."""
    if not url_valida(url):
        return None
    partes = urlsplit(url.strip())
    host = (partes.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    puerto = f":{partes.port}" if partes.port and partes.port not in (80, 443) else ""
    query = sorted((k, v) for k, v in parse_qsl(partes.query, keep_blank_values=False) if not _PARAMS_TRACKING.match(k))
    ruta = partes.path.rstrip("/") or ""
    return urlunsplit(("https", host + puerto, ruta, urlencode(query), ""))


def texto_plano(valor, maximo: int = MAX_FRAGMENTO) -> str | None:
    """Texto sin HTML, con los espacios colapsados y cortado a `maximo`. `None` si queda vacío."""
    if not isinstance(valor, str):
        return None
    limpio = html.unescape(_ETIQUETA.sub(" ", valor))
    limpio = _ESPACIOS.sub(" ", limpio).strip()
    if not limpio:
        return None
    return limpio if len(limpio) <= maximo else limpio[: maximo - 1].rstrip() + "…"


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def tokens(titulo) -> frozenset[str]:
    """Palabras significativas de un título: minúsculas, sin acentos, sin stopwords ES/EN, de 3+ letras
    (o números)."""
    if not isinstance(titulo, str):
        return frozenset()
    palabras = _PALABRA.findall(sin_acentos(titulo).lower())
    return frozenset(p for p in palabras if p not in STOPWORDS and (len(p) >= 3 or p.isdigit()))


def huella_titulo(titulo) -> str:
    """Los tokens ordenados, para guardar y comparar sin recalcular."""
    return " ".join(sorted(tokens(titulo)))


def similitud(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    """Jaccard entre dos conjuntos de tokens (0 si alguno está vacío)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parse_fecha(valor) -> datetime | None:
    """Un instante ISO 8601 (`2026-03-04T21:15:00Z`, `2026-03-04`, `20260304T211500Z`) en UTC naive, o
    `None` si no se puede leer o cae fuera de 1900–2100."""
    if isinstance(valor, datetime):
        dt = valor
    elif isinstance(valor, date):
        dt = datetime(valor.year, valor.month, valor.day)
    elif isinstance(valor, str) and valor.strip():
        s = valor.strip()
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T?(\d{2})(\d{2})(\d{2})Z?", s)
        if m:
            s = f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}+00:00"
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if not 1900 <= dt.year <= 2100:
        return None
    return dt


def son_duplicadas(a: dict, b: dict, umbral: float = UMBRAL_SIMILITUD, ventana_horas: int = VENTANA_HORAS) -> bool:
    """¿Cuentan lo mismo? `a`/`b`: `{proveedor, id_externo, url_normalizada, tokens, fecha}`."""
    if a.get("id_externo") and a.get("proveedor") == b.get("proveedor") and a["id_externo"] == b.get("id_externo"):
        return True
    if a.get("url_normalizada") and a["url_normalizada"] == b.get("url_normalizada"):
        return True
    fa, fb = a.get("fecha"), b.get("fecha")
    if fa is None or fb is None or abs(fa - fb) > timedelta(hours=ventana_horas):
        return False
    return similitud(a.get("tokens") or frozenset(), b.get("tokens") or frozenset()) >= umbral


def agrupar_duplicados(items: list[dict], **kw) -> list[list[int]]:
    """Grupos de índices de `items` que son la misma noticia (unión transitiva). Cada grupo va ordenado
    por fecha y los grupos por su primera aparición. O(n²): se usa sobre una tanda de una corrida, no
    sobre toda la base."""
    padre = list(range(len(items)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if raiz(i) != raiz(j) and son_duplicadas(items[i], items[j], **kw):
                padre[raiz(j)] = raiz(i)
    grupos: dict[int, list[int]] = {}
    for i in range(len(items)):
        grupos.setdefault(raiz(i), []).append(i)
    salida = [sorted(g, key=lambda k: (items[k].get("fecha") or datetime.min, k)) for g in grupos.values()]
    return sorted(salida, key=lambda g: min(g))


def evento_duplicado(candidato: dict, existentes: list[dict]) -> dict | None:
    """El evento de `existentes` que es el mismo acontecimiento que `candidato`, o `None`.

    Cada dict: `{id?, categoria, fecha (date), tokens}`. Gana el más parecido.
    """
    mejor, mejor_sim = None, 0.0
    for e in existentes:
        if e.get("categoria") != candidato.get("categoria"):
            continue
        if abs((e["fecha"] - candidato["fecha"]).days) > TOLERANCIA_DIAS_EVENTO:
            continue
        sim = similitud(candidato.get("tokens") or frozenset(), e.get("tokens") or frozenset())
        if sim >= UMBRAL_SIMILITUD_EVENTO and sim > mejor_sim:
            mejor, mejor_sim = e, sim
    return mejor


def clave_dedup(categoria: str, fecha: date, titulo: str) -> str:
    """Una etiqueta estable del grupo de deduplicación: categoría, semana ISO y las palabras más largas del
    título. No decide la deduplicación (eso es `evento_duplicado`): sirve para indexar y auditar."""
    palabras = sorted(tokens(titulo), key=lambda p: (-len(p), p))[:4]
    anio, semana, _ = fecha.isocalendar()
    return f"{categoria}:{anio}-W{semana:02d}:{'-'.join(sorted(palabras))}"
