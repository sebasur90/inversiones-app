"""Cliente de data912.com — API pública de precios del mercado argentino, sin autenticación.

Los endpoints `/live/*` devuelven la foto intradiaria: una fila por especie, con último precio
en `c` (y puntas `px_bid`/`px_ask`). Probado desde el ambiente corporativo (con proxy) el
2026-08-28: responde 200 con User-Agent de navegador.

Los símbolos base (`AL30`, `S30S6`, `TZXD7`) cotizan en ARS **por lámina de 100 VN**; los
sufijos `C`/`D` son las variantes CCL/MEP en USD y no se usan acá. La diferencia de escala
contra la convención del Sheet (precio por 1 VN) la resuelve `precios.py` calibrando contra el
último precio manual de cada ticker, no acá.
"""
from .client import get_json

BASE_URL = "https://data912.com"

# Renta fija: soberanos hard-dollar y en pesos, ONs corporativas, letras/LECAPs.
_ENDPOINTS_RENTA_FIJA = ("live/arg_bonds", "live/arg_corp", "live/arg_notes")
# Renta variable: acciones locales y CEDEARs (lo usa la Ola 4).
_ENDPOINTS_RENTA_VARIABLE = ("live/arg_stocks", "live/arg_cedears")


def _precio_de_fila(row: dict) -> float | None:
    """Último precio operado (`c`); si no vino, el punto medio de las puntas."""
    c = _num(row.get("c"))
    if c is not None and c > 0:
        return c
    bid, ask = _num(row.get("px_bid")), _num(row.get("px_ask"))
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    for punta in (bid, ask):
        if punta is not None and punta > 0:
            return punta
    return None


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_live(endpoints: tuple[str, ...]) -> dict[str, float] | None:
    """Une los endpoints en `symbol -> último precio`. Devuelve None sólo si NINGUNO respondió
    (para que el llamador distinga "la API está caída" de "respondió pero sin ese ticker")."""
    out: dict[str, float] = {}
    alguno_respondio = False
    for ep in endpoints:
        data = get_json(f"{BASE_URL}/{ep}")
        if not isinstance(data, list):
            continue
        alguno_respondio = True
        for row in data:
            if not isinstance(row, dict):
                continue
            symbol = (row.get("symbol") or "").strip()
            precio = _precio_de_fila(row)
            if symbol and precio is not None:
                out.setdefault(symbol, precio)
    return out if alguno_respondio else None


def fetch_precios_renta_fija() -> dict[str, float] | None:
    """`symbol -> último precio` (ARS por lámina de 100 VN) para bonos, ONs y letras."""
    return _fetch_live(_ENDPOINTS_RENTA_FIJA)


def fetch_precios_renta_variable() -> dict[str, float] | None:
    """`symbol -> último precio` para acciones y CEDEARs (Ola 4)."""
    return _fetch_live(_ENDPOINTS_RENTA_VARIABLE)
