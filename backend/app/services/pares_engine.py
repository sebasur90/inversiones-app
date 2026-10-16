"""Elección del grupo de comparables (pares) de un emisor. Puro: sin DB ni red.

La pregunta que responde la pantalla de valuación es "¿está más barata o más cara que empresas
parecidas?". Un percentil contra un grupo mal elegido no dice nada, así que el criterio es
explícito y viaja con el resultado (`GrupoPares.criterio`) para mostrarlo:

**Acciones**: misma industria (la de Yahoo, p.ej. "Beverages - Non-Alcoholic") y tamaño parecido
(market cap entre 0,2x y 5x). Si no alcanzan `N_MIN`, se afloja el tamaño (0,05x-20x), después se
saca, y por último se completa con el mismo sector. Se ordenan por distancia de tamaño, con una
penalización si son de otra región: un banco argentino se compara primero con bancos argentinos.

**ETFs**: misma categoría de Yahoo ("Large Blend", "Technology"); si no alcanza, mismo sector y
región. Se ordenan por patrimonio (AUM): entre dos ETFs de S&P 500 importa el más líquido.

**Corrección manual**: `(automáticos − quitados) ∪ agregados`. Los agregados entran siempre, aunque
superen el tope.

Un mismo emisor puede aparecer con dos tickers (PETR3 y PBR → Yahoo `PBR`; GGAL local y su ADR):
cuenta una sola vez, y nunca como par de sí mismo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

K_DEFAULT = 8
N_MIN = 4
PENALIZACION_REGION = 0.5
DISTANCIA_SIN_TAMANO = 3.0
RANGOS_TAMANO = ((0.2, 5.0), (0.05, 20.0), None)


@dataclass(frozen=True)
class Candidato:
    ticker_base: str
    simbolo_yahoo: str | None
    nombre: str | None = None
    es_etf: bool = False
    sector: str | None = None
    industria_raw: str | None = None
    categoria: str | None = None
    region: str | None = None
    tamano_usd: float | None = None   # market cap (acciones) o AUM (ETFs)


@dataclass
class GrupoPares:
    pares: list[str] = field(default_factory=list)      # ticker_base, en orden
    criterio: str = ""
    automaticos: list[str] = field(default_factory=list)
    agregados: list[str] = field(default_factory=list)
    quitados: list[str] = field(default_factory=list)


def _clave(texto) -> str:
    return (texto or "").strip().lower()


def _distancia_tamano(a: float | None, b: float | None) -> float:
    if not a or not b or a <= 0 or b <= 0:
        return DISTANCIA_SIN_TAMANO
    return abs(math.log(a / b))


def _en_rango(tamano: float | None, ref: float | None, rango) -> bool:
    if rango is None:
        return True
    if not tamano or not ref:
        return False
    lo, hi = rango
    return lo <= tamano / ref <= hi


def deduplicar(universo: list[Candidato]) -> list[Candidato]:
    """Uno por símbolo de Yahoo. Entre dos tickers del mismo emisor queda el que coincide con el
    símbolo de Yahoo (el ADR `PBR` antes que `PETR3`), y si no, el más corto."""
    por_simbolo: dict[str, Candidato] = {}
    sin_simbolo: list[Candidato] = []
    for c in universo:
        if not c.simbolo_yahoo:
            sin_simbolo.append(c)
            continue
        actual = por_simbolo.get(c.simbolo_yahoo)
        if actual is None:
            por_simbolo[c.simbolo_yahoo] = c
            continue

        def _rank(x: Candidato):
            return (x.ticker_base != x.simbolo_yahoo, len(x.ticker_base), x.ticker_base)

        if _rank(c) < _rank(actual):
            por_simbolo[c.simbolo_yahoo] = c
    return list(por_simbolo.values()) + sin_simbolo


def _pares_accion(obj: Candidato, pool: list[Candidato], k: int) -> tuple[list[Candidato], str]:
    def _orden(c: Candidato):
        pen = PENALIZACION_REGION if (obj.region and c.region and c.region != obj.region) else 0.0
        return (_distancia_tamano(c.tamano_usd, obj.tamano_usd) + pen, c.ticker_base)

    misma_industria = [c for c in pool if obj.industria_raw and _clave(c.industria_raw) == _clave(obj.industria_raw)]
    elegidos: list[Candidato] = []
    criterio = ""
    for rango in RANGOS_TAMANO:
        elegidos = [c for c in misma_industria if _en_rango(c.tamano_usd, obj.tamano_usd, rango)]
        if len(elegidos) >= N_MIN:
            criterio = (
                "misma industria y tamaño parecido" if rango == RANGOS_TAMANO[0]
                else "misma industria, tamaño más amplio" if rango is not None
                else "misma industria"
            )
            break
    else:
        criterio = "misma industria" if elegidos else ""

    elegidos = sorted(elegidos, key=_orden)[:k]
    if len(elegidos) < N_MIN and obj.sector:
        ya = {c.ticker_base for c in elegidos}
        mismo_sector = sorted(
            (c for c in pool if c.ticker_base not in ya and _clave(c.sector) == _clave(obj.sector)),
            key=_orden,
        )
        if mismo_sector:
            elegidos += mismo_sector[: N_MIN - len(elegidos)]
            criterio = "misma industria, completado con el mismo sector" if criterio else "mismo sector"
    return elegidos, criterio


def _pares_etf(obj: Candidato, pool: list[Candidato], k: int) -> tuple[list[Candidato], str]:
    def _orden(c: Candidato):
        return (-(c.tamano_usd or 0.0), c.ticker_base)

    misma_cat = [c for c in pool if obj.categoria and _clave(c.categoria) == _clave(obj.categoria)]
    elegidos = sorted(misma_cat, key=_orden)[:k]
    criterio = "misma categoría" if elegidos else ""
    if len(elegidos) < N_MIN and (obj.sector or obj.region):
        ya = {c.ticker_base for c in elegidos}
        similares = sorted(
            (c for c in pool if c.ticker_base not in ya
             and _clave(c.sector) == _clave(obj.sector) and _clave(c.region) == _clave(obj.region)),
            key=_orden,
        )
        if similares:
            elegidos += similares[: max(N_MIN - len(elegidos), 0)]
            criterio = "misma categoría, completado con mismo sector y región" if criterio else "mismo sector y región"
    return elegidos, criterio


def elegir_pares(
    objetivo: Candidato,
    universo: list[Candidato],
    agregar: list[str] | None = None,
    quitar: list[str] | None = None,
    k: int = K_DEFAULT,
) -> GrupoPares:
    """El grupo de comparables de `objetivo` dentro de `universo` (ver docstring del módulo)."""
    agregar = [a.upper() for a in (agregar or [])]
    quitar_set = {q.upper() for q in (quitar or [])}

    pool = [
        c for c in deduplicar(universo)
        if c.ticker_base != objetivo.ticker_base
        and not (objetivo.simbolo_yahoo and c.simbolo_yahoo == objetivo.simbolo_yahoo)
        and c.es_etf == objetivo.es_etf
    ]
    if objetivo.es_etf:
        auto, criterio = _pares_etf(objetivo, pool, k)
    else:
        auto, criterio = _pares_accion(objetivo, pool, k)

    automaticos = [c.ticker_base for c in auto]
    final = [t for t in automaticos if t not in quitar_set]
    for a in agregar:
        if a not in final and a != objetivo.ticker_base:
            final.append(a)
    if agregar or quitar_set:
        criterio = (criterio + " (con correcciones manuales)") if criterio else "elegidos a mano"
    return GrupoPares(
        pares=final,
        criterio=criterio,
        automaticos=automaticos,
        agregados=[a for a in agregar if a != objetivo.ticker_base],
        quitados=sorted(quitar_set),
    )
