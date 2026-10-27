"""Qué instrumentos de la app se relacionan con un evento, con qué tipo de relación y cuánta relevancia.
Puro.

Niveles, de más a menos directos (la relevancia es para ese instrumento, no para el mercado):

- **directa** — la noticia menciona con fuerza a la empresa (balance, quiebra, adquisición, sanción a esa
  empresa): relevancia 1.0 si aparece en el título; si no, entre 0.6 y 0.9 según el `match_score`.
- **sector** — sólo para categorías que afectan a un sector entero (regulación, aranceles, materias
  primas, tecnología, crisis financiera): los instrumentos del universo del mismo sector que la empresa
  mencionada, o el sector de la materia prima (petróleo → Energía). Relevancia 0.5.
- **país** — elecciones, política, bancos centrales, datos macro y conflictos de un país: los
  instrumentos del universo de ese país, relevancia 0.35, y el índice de ese mercado (`^MERV`, `SPY`)
  como `indice`, 0.5.
- Un acontecimiento global sin país (una guerra, una crisis bancaria) se vincula sólo al índice amplio
  (`SPY`), 0.4: vincularlo a cada ticker sería afirmar algo que no se sabe.

Nunca se proponen más de `MAX_AUTOMATICOS` vínculos. Las lápidas (vínculos que el usuario descartó) y los
vínculos manuales no se tocan: la corrección del usuario manda. Todo vínculo automático entra como
`propuesta` con su justificación escrita.
"""
from __future__ import annotations

from ..clasificacion_engine import pais_canonico, sector_canonico
from .clasificacion_engine import UMBRAL_MATCH, mencion_fuerte

MAX_AUTOMATICOS = 15
RELEVANCIA_SECTOR = 0.5
RELEVANCIA_PAIS = 0.35
RELEVANCIA_INDICE_PAIS = 0.5
RELEVANCIA_INDICE_GLOBAL = 0.4

CATEGORIAS_SECTORIALES = ("regulacion", "sanciones_aranceles", "materias_primas", "tecnologia_sector", "crisis_financiera")
CATEGORIAS_PAIS = ("elecciones", "politica", "banco_central", "dato_macro", "geopolitica", "sanciones_aranceles")
CATEGORIAS_GLOBALES = ("geopolitica", "crisis_financiera", "sanciones_aranceles")

INDICE_POR_PAIS = {"Argentina": "^MERV", "Estados Unidos": "SPY"}

# Sector afectado por una materia prima mencionada en el texto (ya sin acentos y en minúsculas).
SECTOR_POR_MATERIA_PRIMA = {
    "oil": "Energía", "petroleo": "Energía", "crude": "Energía", "brent": "Energía", "wti": "Energía",
    "opec": "Energía", "opep": "Energía", "natural gas": "Energía", "gas natural": "Energía",
    "copper": "Materiales", "cobre": "Materiales", "lithium": "Materiales", "litio": "Materiales",
    "gold": "Materiales", "soja": "Consumo básico", "soybean": "Consumo básico", "wheat": "Consumo básico",
    "trigo": "Consumo básico",
}


def _relevancia_directa(ent: dict) -> float:
    if ent.get("en_titulo"):
        return 1.0
    match = ent.get("match_score") or 0
    return round(min(0.9, 0.6 + max(0.0, match - UMBRAL_MATCH) / 100), 3)


def proponer(
    *, categoria: str, pais: str | None, entidades: list[dict], texto: str,
    simbolo_a_tickers: dict[str, list[str]], universo: dict[str, dict],
    lapidas: set[str] = frozenset(), manuales: set[str] = frozenset(),
) -> list[dict]:
    """Vínculos propuestos `[{ticker, tipo_relacion, relevancia, justificacion}]`, de más a menos relevante.

    - `entidades`: las del proveedor ya normalizadas (`simbolo`, `nombre`, `industria`, `pais`,
      `match_score`, `en_titulo`).
    - `simbolo_a_tickers`: símbolo del proveedor (el de EE.UU. o `GGAL.BA`) → tickers de la app.
    - `universo`: `{ticker: {sector, pais}}` de cartera ∪ watchlist.
    - `texto`: título + fragmento sin acentos y en minúsculas (para las materias primas).
    """
    propuestas: dict[str, dict] = {}
    bloqueados = set(lapidas) | set(manuales)

    def proponer_uno(ticker: str, tipo: str, relevancia: float, motivo: str) -> None:
        if ticker in bloqueados:
            return
        actual = propuestas.get(ticker)
        if actual is None or relevancia > actual["relevancia"]:
            propuestas[ticker] = {"ticker": ticker, "tipo_relacion": tipo, "relevancia": relevancia, "justificacion": motivo}

    directos: list[str] = []
    for ent in entidades:
        simbolo = (ent.get("simbolo") or "").upper()
        tickers = simbolo_a_tickers.get(simbolo) or []
        if not tickers or not mencion_fuerte(ent):
            continue
        donde = "en el título" if ent.get("en_titulo") else f"en el texto (coincidencia {ent.get('match_score') or 0:.0f})"
        for t in tickers:
            proponer_uno(t, "directa", _relevancia_directa(ent), f"La noticia menciona a {ent.get('nombre') or simbolo} ({simbolo}) {donde}")
            directos.append(t)

    if categoria in CATEGORIAS_SECTORIALES:
        sectores: dict[str, str] = {}
        for t in directos:
            s = (universo.get(t) or {}).get("sector")
            if s:
                sectores.setdefault(s, f"Mismo sector ({s}) que {t}")
        for ent in entidades:
            s = sector_canonico(ent.get("industria"))
            if s and mencion_fuerte(ent):
                sectores.setdefault(s, f"Sector de {ent.get('nombre') or ent.get('simbolo')} ({s})")
        if categoria == "materias_primas":
            for termino, s in SECTOR_POR_MATERIA_PRIMA.items():
                if f" {termino} " in f" {texto} ":
                    sectores.setdefault(s, f"Sector expuesto a «{termino}» ({s})")
        for t, info in sorted(universo.items()):
            motivo = sectores.get(info.get("sector") or "")
            if motivo and t not in directos:
                proponer_uno(t, "sector", RELEVANCIA_SECTOR, motivo)

    pais_c = pais_canonico(pais) if pais else None
    if categoria in CATEGORIAS_PAIS and pais_c:
        indice = INDICE_POR_PAIS.get(pais_c)
        if indice:
            proponer_uno(indice, "indice", RELEVANCIA_INDICE_PAIS, f"Índice del mercado de {pais_c}")
        for t, info in sorted(universo.items()):
            if info.get("pais") == pais_c and t not in directos:
                proponer_uno(t, "pais", RELEVANCIA_PAIS, f"Emisor de {pais_c}, país del acontecimiento")
    elif categoria in CATEGORIAS_GLOBALES and not pais_c:
        proponer_uno("SPY", "indice", RELEVANCIA_INDICE_GLOBAL, "Acontecimiento global: se compara contra el mercado amplio")

    orden = sorted(propuestas.values(), key=lambda p: (-p["relevancia"], p["ticker"]))
    return orden[:MAX_AUTOMATICOS]
