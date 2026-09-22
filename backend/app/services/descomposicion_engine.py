"""Motor puro de "Descomposición de cartera": arma el árbol jerárquico Familia → País →
Sector → Ticker a partir de posiciones ya valorizadas.

Sin dependencias de `Session`/DB — recibe la lista de posiciones (una por ticker, ya con su
ficha de `Instrumentos` resuelta) y devuelve la estructura de árbol lista para servir.

**Las familias ("Renta fija" / "Renta variable" / "Fondos" / "Liquidez") no existen como dato
en el Sheet**: se derivan de `tipo_instrumento` y `sector` con las mismas heurísticas que ya
usa el resto del repo para no duplicar criterio —
`market_data.precios._es_renta_fija/_es_renta_variable/_es_fci` y
`salud_engine.SECTORES_LIQUIDOS`. No se inventa ninguna clasificación nueva.
"""
from .market_data.precios import _es_fci, _es_renta_fija, _es_renta_variable
from .salud_engine import SECTORES_LIQUIDOS

NIVELES = ("Familia", "País", "Sector", "Ticker")

SIN_CLASIFICAR = "Sin clasificar"

# Orden fijo del nivel 1: el árbol se lee siempre igual, sin importar cuánto pese cada familia
# hoy. Cualquier familia no contemplada (no debería pasar, ver `familia_de`) cae después de
# "Otros" y antes de "Sin clasificar".
ORDEN_FAMILIAS = ("Renta fija", "Renta variable", "Fondos", "Liquidez", "Otros", SIN_CLASIFICAR)


def familia_de(tipo_instrumento: str | None, sector: str | None, con_ficha: bool) -> str:
    """Familia EXCLUYENTE de un instrumento — el primer match gana, para que los pesos del
    nivel 1 sumen siempre 100%.

    Orden de prioridad (deliberado):
    1. Sin ficha en `Instrumentos` (el ticker no está en el Sheet) → "Sin clasificar".
    2. `sector` contiene "liquidez" → "Liquidez". Gana sobre el tipo: si el usuario marcó a
       mano un FCI como Liquidez en el Sheet, ese dato explícito manda sobre el derivado.
    3. `_es_fci(tipo)` → "Fondos" (FCIs que no se marcaron como Liquidez).
    4. `_es_renta_fija(tipo)` → "Renta fija".
    5. `_es_renta_variable(tipo)` → "Renta variable".
    6. Nada matcheó → "Otros".

    A propósito NO se reutiliza `salud_engine._es_liquido` completo: su regla de "vence en
    menos de 365 días" sacaría bonos cortos de "Renta fija" y los mandaría a "Liquidez", que
    acá rompería la lectura por familia de instrumento. Sólo se toma la lista de sectores.
    """
    if not con_ficha:
        return SIN_CLASIFICAR
    sector_norm = (sector or "").strip().lower()
    if any(s in sector_norm for s in SECTORES_LIQUIDOS):
        return "Liquidez"
    tipo = tipo_instrumento or ""
    if _es_fci(tipo):
        return "Fondos"
    if _es_renta_fija(tipo):
        return "Renta fija"
    if _es_renta_variable(tipo):
        return "Renta variable"
    return "Otros"


def _etiqueta_familia(p: dict) -> str:
    return familia_de(p.get("tipo_instrumento"), p.get("sector"), p.get("con_ficha", True))


def _etiqueta_pais(p: dict) -> str:
    return p.get("pais") or SIN_CLASIFICAR


def _etiqueta_sector(p: dict) -> str:
    return p.get("sector") or SIN_CLASIFICAR


def _etiqueta_ticker(p: dict) -> str:
    return p["ticker"]


_ETIQUETA_POR_NIVEL = {
    "Familia": _etiqueta_familia,
    "País": _etiqueta_pais,
    "Sector": _etiqueta_sector,
    "Ticker": _etiqueta_ticker,
}


def _agrupar_por(posiciones: list[dict], etiqueta_fn) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for p in posiciones:
        grupos.setdefault(etiqueta_fn(p), []).append(p)
    return grupos


def _ordenar_etiquetas(nivel: str, grupos: dict[str, list[dict]]) -> list[str]:
    """Familia: orden fijo (`ORDEN_FAMILIAS`). Resto: por valor descendente, con el bucket
    "Sin clasificar" siempre al final (aunque pese más que algún hermano)."""
    if nivel == "Familia":
        presentes = [f for f in ORDEN_FAMILIAS if f in grupos]
        extra = [e for e in grupos if e not in ORDEN_FAMILIAS]
        return presentes + extra

    normales = sorted(
        (e for e in grupos if e != SIN_CLASIFICAR),
        key=lambda e: -sum(p["valor_usd"] for p in grupos[e]),
    )
    if SIN_CLASIFICAR in grupos:
        normales.append(SIN_CLASIFICAR)
    return normales


def _nivel(posiciones: list[dict], profundidad: int, total_usd: float, valor_padre_usd: float) -> list[dict]:
    if profundidad >= len(NIVELES) or not posiciones:
        return []

    nombre_nivel = NIVELES[profundidad]
    grupos = _agrupar_por(posiciones, _ETIQUETA_POR_NIVEL[nombre_nivel])
    orden = _ordenar_etiquetas(nombre_nivel, grupos)

    nodos = []
    for etiqueta in orden:
        items = grupos[etiqueta]
        valor_usd = sum(p["valor_usd"] for p in items)
        valor_ars = sum(p["valor_ars"] for p in items)
        nodo = {
            "clave": etiqueta,
            "etiqueta": etiqueta,
            "nivel": nombre_nivel,
            "valor_usd": round(valor_usd, 2),
            "valor_ars": round(valor_ars, 2),
            # Sobre el TOTAL de la cartera: no cambia al bajar de nivel.
            "porcentaje": round(valor_usd / total_usd * 100, 2) if total_usd > 0 else 0.0,
            # Sobre el nodo padre: es lo que suma 100% entre hermanos (lo que pinta el donut).
            "porcentaje_padre": round(valor_usd / valor_padre_usd * 100, 2) if valor_padre_usd > 0 else 0.0,
            "instrumentos": len({p["ticker"] for p in items}),
            "sin_clasificar": etiqueta == SIN_CLASIFICAR,
            "tipo_instrumento": None,
            "nombre": None,
            "hijos": [],
        }
        if nombre_nivel == "Ticker":
            # Cada grupo de este nivel es una sola posición (ya consolidada por ticker).
            p = items[0]
            nodo["tipo_instrumento"] = p.get("tipo_instrumento")
            nodo["nombre"] = p.get("nombre")
        else:
            nodo["hijos"] = _nivel(items, profundidad + 1, total_usd, valor_usd)
        nodos.append(nodo)
    return nodos


def construir_arbol(posiciones: list[dict], total_usd: float, total_ars: float) -> list[dict]:
    """Árbol de 4 niveles (Familia → País → Sector → Ticker) a partir de posiciones ya
    valorizadas (una por ticker). `total_usd`/`total_ars` son el total de cartera: sirven de
    denominador estable para `porcentaje` en todos los niveles.

    Cada posición esperada como:
        {ticker, nombre, tipo_instrumento, sector, pais, con_ficha, valor_usd, valor_ars}
    """
    if total_usd <= 0 or not posiciones:
        return []
    return _nivel(posiciones, 0, total_usd, total_usd)
