"""Clasificación de noticias en categorías de evento, importancia y confianza. Puro y auditable.

Sin IA: reglas explícitas por palabras clave (castellano e inglés) sobre el título y el fragmento. Cada
regla que se aplica queda escrita en `reglas` para que se pueda ver por qué una noticia terminó donde
terminó. Las reglas tienen versión (`VERSION_REGLAS`): un cambio de reglas no reinterpreta en silencio lo
ya guardado.

Tres conceptos separados (ninguno es una predicción de la dirección del precio):
- **importancia** (1–3): cuánto puede mover al mercado en general el tipo de acontecimiento;
- **confianza** de la clasificación (`alta|media|baja`): qué tan clara fue la categoría;
- la **relevancia para un instrumento** se calcula aparte, en `asociacion_engine`.

Puntaje de una categoría: cada término que aparece suma su peso; si aparece en el título vale el doble.
Gana la de mayor puntaje. Confianza: `alta` si el ganador suma ≥ 4 y le saca ≥ 2 al segundo; `media` si
suma ≥ 2; si no, `baja` (y la categoría queda `otro`).

**Incorporación automática** (`decidir_incorporacion`): una noticia se convierte sola en evento sólo si
viene de una fuente programada u oficial, o si a la vez: la categoría no es `otro`, la confianza no es
`baja`, la importancia es ≥ 2 y menciona con fuerza (`match_score ≥ UMBRAL_MATCH` o en el título) a un
instrumento del universo de la app. Todo lo demás va a la bandeja de revisión: nada dudoso entra solo.
"""
from __future__ import annotations

import re

from .normalizacion_engine import sin_acentos

VERSION_REGLAS = 1
UMBRAL_MATCH = 10.0   # escala de Marketaux (no acotada a 1; 12–35 en noticias que hablan de la empresa)

# (término, peso). Un término termina en `*` = prefijo ("eleccion*" cubre "elecciones").
TERMINOS: dict[str, tuple[tuple[str, int], ...]] = {
    "elecciones": (
        ("eleccion*", 3), ("election*", 3), ("electoral", 2), ("comicios", 3), ("balotaje", 3), ("runoff", 2),
        ("primarias", 2), ("primaries", 2), ("ballot", 2), ("votacion", 1), ("voters", 1), ("midterm*", 3),
    ),
    "banco_central": (
        ("fomc", 4), ("federal reserve", 4), ("reserva federal", 4), ("bcra", 4), ("banco central", 3),
        ("central bank", 3), ("ecb", 3), ("bce", 2), ("copom", 4), ("powell", 2), ("lagarde", 2),
        ("rate cut*", 3), ("rate hike*", 3), ("interest rate*", 2), ("tasa de interes", 2), ("tasas de interes", 2),
        ("recorte de tasas", 3), ("suba de tasas", 3), ("baja de tasas", 3), ("monetary policy", 2),
        ("politica monetaria", 2), ("fed", 2),
    ),
    "dato_macro": (
        ("inflation", 3), ("inflacion", 3), ("cpi", 3), ("ipc", 3), ("pce", 2), ("payroll*", 3), ("nonfarm", 3),
        ("unemployment", 2), ("desempleo", 2), ("desocupacion", 2), ("gdp", 3), ("pbi", 3), ("pib", 3),
        ("retail sales", 2), ("pmi", 2), ("indec", 3), ("jobs report", 3), ("recession", 2), ("recesion", 2),
    ),
    "resultados": (
        ("earnings", 3), ("quarterly results", 4), ("quarterly revenue", 3), ("revenue", 1), ("eps", 2),
        ("guidance", 2), ("beats estimates", 3), ("misses estimates", 3), ("beat estimates", 3),
        ("resultados trimestrales", 4), ("balance trimestral", 4), ("ganancias trimestrales", 3),
        ("trimestre", 1), ("quarter", 1), ("profit", 1), ("ganancia*", 1),
    ),
    "corporativo": (
        ("merger", 3), ("acquisition", 3), ("acquire*", 3), ("takeover", 3), ("buyout", 3), ("tender offer", 4),
        ("ipo", 3), ("fusion", 3), ("adquisicion", 3), ("adquiere", 3), ("adquirir", 2), ("oferta publica", 3),
        ("opa", 3), ("spin off", 2), ("spinoff", 2), ("stock split", 3), ("buyback", 2), ("recompra", 2),
        ("ceo", 1), ("dividend*", 1),
    ),
    "crisis_financiera": (
        ("bankruptcy", 4), ("chapter 11", 4), ("quiebra", 4), ("default", 3), ("bailout", 4), ("rescate", 2),
        ("bank run", 4), ("insolvency", 3), ("insolvencia", 3), ("concurso preventivo", 4), ("liquidity crisis", 4),
        ("crisis de liquidez", 4), ("debt restructuring", 3), ("reestructuracion de deuda", 3), ("collapse*", 2),
        ("colapso", 2),
    ),
    "geopolitica": (
        ("war", 3), ("guerra", 3), ("invasion", 3), ("invade*", 3), ("missile*", 3), ("misil*", 3),
        ("airstrike*", 3), ("ceasefire", 3), ("alto el fuego", 3), ("troops", 2), ("tropas", 2), ("military", 2),
        ("militar*", 2), ("conflict", 2), ("conflicto", 2), ("attack*", 1), ("ataque*", 1), ("nato", 2), ("otan", 2),
    ),
    "sanciones_aranceles": (
        ("sanction*", 3), ("sancion*", 3), ("tariff*", 4), ("arancel*", 4), ("embargo", 3), ("export controls", 3),
        ("trade war", 4), ("guerra comercial", 4), ("import duties", 3), ("derechos de importacion", 3),
        ("retenciones", 2),
    ),
    "regulacion": (
        ("regulation*", 3), ("regulacion*", 3), ("regulator*", 3), ("antitrust", 3), ("antimonopolio", 3),
        ("sec", 2), ("cnv", 3), ("fine*", 1), ("multa*", 2), ("lawsuit", 2), ("demanda", 1), ("ftc", 3),
        ("doj", 2), ("approval", 1), ("aprobacion", 1), ("fda", 3),
    ),
    "politica": (
        ("president", 2), ("presidente", 2), ("government", 1), ("gobierno", 1), ("minister", 2), ("ministro", 2),
        ("resign*", 3), ("renuncia*", 3), ("decree", 2), ("decreto", 2), ("congress", 2), ("congreso", 2),
        ("senate", 2), ("senado", 2), ("reform", 2), ("reforma", 2), ("impeachment", 3), ("juicio politico", 3),
        ("shutdown", 3),
    ),
    "materias_primas": (
        ("oil", 3), ("petroleo", 3), ("crude", 3), ("brent", 3), ("wti", 3), ("opec", 4), ("opep", 4),
        ("gold", 2), ("oro", 1), ("copper", 2), ("cobre", 2), ("soja", 3), ("soybean*", 3), ("wheat", 2),
        ("trigo", 2), ("natural gas", 3), ("gas natural", 3), ("lithium", 3), ("litio", 3), ("commodit*", 2),
    ),
    "tecnologia_sector": (
        ("artificial intelligence", 3), ("inteligencia artificial", 3), ("ai chip*", 3), ("semiconductor*", 3),
        ("chips", 2), ("breakthrough", 2), ("descubrimiento", 2), ("patent*", 1), ("quantum", 2), ("cuantica", 2),
        ("data center*", 2), ("chatbot", 2),
    ),
}

# Términos que suben la importancia de una categoría a 3 (alta).
TERMINOS_ALTA: dict[str, tuple[str, ...]] = {
    "banco_central": ("fomc", "federal reserve", "reserva federal", "bcra", "fed", "powell"),
    "elecciones": ("presidential", "presidencial*", "general election", "elecciones generales", "midterm*", "balotaje"),
    "geopolitica": ("war", "guerra", "invasion", "invade*", "nuclear"),
    "crisis_financiera": ("bank run", "bailout", "chapter 11", "default", "quiebra"),
    "sanciones_aranceles": ("tariff*", "arancel*", "trade war", "guerra comercial"),
}

IMPORTANCIA_BASE = {
    "elecciones": 2, "banco_central": 2, "dato_macro": 2, "resultados": 1, "corporativo": 2,
    "crisis_financiera": 2, "geopolitica": 2, "sanciones_aranceles": 2, "regulacion": 1, "politica": 1,
    "materias_primas": 1, "tecnologia_sector": 1, "otro": 1,
}


def _patron(termino: str) -> re.Pattern:
    prefijo = termino.endswith("*")
    cuerpo = re.escape(termino.rstrip("*")).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{cuerpo}" + (r"\w*" if prefijo else r"\b"))


_PATRONES = {cat: tuple((_patron(t), t, p) for t, p in terms) for cat, terms in TERMINOS.items()}
_PATRONES_ALTA = {cat: tuple((_patron(t), t) for t in terms) for cat, terms in TERMINOS_ALTA.items()}


def _normal(texto: str | None) -> str:
    return sin_acentos(texto or "").lower()


def clasificar(titulo: str, fragmento: str | None = None, en_universo: bool = False) -> dict:
    """`{categoria, confianza, importancia, puntajes, reglas, version}`.

    `en_universo`: la noticia menciona con fuerza a un instrumento que el usuario sigue (cartera o watchlist);
    sube en uno la importancia de los resultados y anuncios corporativos (para el usuario importan más que
    los de una empresa ajena).
    """
    t, f = _normal(titulo), _normal(fragmento)
    puntajes: dict[str, int] = {}
    reglas: list[str] = []
    for cat, patrones in _PATRONES.items():
        total = 0
        for patron, termino, peso in patrones:
            if patron.search(t):
                total += 2 * peso
                reglas.append(f"{cat}: «{termino}» en el título (+{2 * peso})")
            elif f and patron.search(f):
                total += peso
                reglas.append(f"{cat}: «{termino}» en el texto (+{peso})")
        if total:
            puntajes[cat] = total
    orden = sorted(puntajes.items(), key=lambda kv: (-kv[1], kv[0]))
    primero = orden[0] if orden else ("otro", 0)
    segundo = orden[1][1] if len(orden) > 1 else 0
    if primero[1] >= 4 and primero[1] - segundo >= 2:
        confianza = "alta"
    elif primero[1] >= 2:
        confianza = "media"
    else:
        confianza = "baja"
    categoria = primero[0] if confianza != "baja" else "otro"
    reglas.append(f"categoría «{categoria}» con puntaje {primero[1]} (segundo: {segundo}) → confianza {confianza}")

    importancia = IMPORTANCIA_BASE.get(categoria, 1)
    for patron, termino in _PATRONES_ALTA.get(categoria, ()):
        if patron.search(t) or (f and patron.search(f)):
            importancia = 3
            reglas.append(f"importancia alta por «{termino}»")
            break
    if en_universo and categoria in ("resultados", "corporativo", "crisis_financiera", "regulacion") and importancia < 3:
        importancia += 1
        reglas.append("importancia +1: menciona a un instrumento que seguís (cartera o watchlist)")
    return {
        "categoria": categoria, "confianza": confianza, "importancia": importancia,
        "puntajes": dict(orden), "reglas": reglas, "version": VERSION_REGLAS,
    }


def mencion_fuerte(entidad: dict) -> bool:
    """La noticia habla de verdad de esa entidad (no una mención al pasar)."""
    return bool(entidad.get("en_titulo")) or (entidad.get("match_score") or 0) >= UMBRAL_MATCH


def decidir_incorporacion(clasificacion: dict, menciona_universo: bool, fuente_programada: bool = False) -> tuple[bool, str]:
    """`(incorporar_sola, motivo)`. Ver la regla en el docstring del módulo."""
    if fuente_programada:
        return True, "evento programado de una fuente oficial o de calendario"
    if clasificacion["categoria"] == "otro":
        return False, "no se pudo clasificar con claridad"
    if clasificacion["confianza"] == "baja":
        return False, "clasificación con confianza baja"
    if clasificacion["importancia"] < 2:
        return False, "importancia baja para incorporarse sola"
    if not menciona_universo:
        return False, "no menciona con fuerza a ningún instrumento de la app"
    return True, "categoría clara, importancia media o alta y mención fuerte de un instrumento de la app"


def confianza_datos(verificacion: str, precision_fecha: str, n_fuentes: int) -> str:
    """Calidad de la evidencia y certeza de la fecha (no de la clasificación)."""
    if verificacion == "rumor" or precision_fecha in ("anio", "desconocida"):
        return "baja"
    firme = verificacion in ("fuente_oficial", "verificado_usuario") or n_fuentes >= 2
    if firme and precision_fecha == "exacta":
        return "alta"
    if firme or precision_fecha == "exacta":
        return "media"
    return "baja"
