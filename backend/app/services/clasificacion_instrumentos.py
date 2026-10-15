"""Clasificadores de tipo de instrumento que comparten varios módulos.

Vive aparte, **sin importar nada del paquete**, porque `market_data/precios.py` ya importa
`ohlcv_analytics` y `ohlcv_analytics` necesita saber si un ticker es CEDEAR para decidir su serie de
referencia: si `es_cedear` viviera en `precios.py` esa dependencia sería un ciclo de imports.
"""
from unicodedata import combining, normalize


def sin_acentos(s: str) -> str:
    return "".join(c for c in normalize("NFD", s) if not combining(c)).lower().strip()


def es_cedear(tipo_instrumento: str) -> bool:
    """Un CEDEAR: el ticker local *es* el del subyacente por construcción, así que la resolución
    automática del subyacente es segura (no hace falta match de nombre)."""
    return "cedear" in sin_acentos(tipo_instrumento or "")
