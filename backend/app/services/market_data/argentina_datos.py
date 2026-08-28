"""Cliente de ArgentinaDatos (api.argentinadatos.com) — API pública, sin autenticación, MIT.

Fuente de origen BCRA/INDEC. Probado desde el ambiente corporativo (con proxy) el 2026-08-28:
responde 200 con User-Agent de navegador; con el User-Agent por defecto de Python devuelve 403.
"""
from datetime import date, datetime
from .client import get_json

BASE_URL = "https://api.argentinadatos.com/v1"


def _parse_fecha(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def fetch_uva_serie() -> list[tuple[date, float]] | None:
    """Serie diaria del índice UVA (BCRA), desde 2016.

    La app usa el CER únicamente como *ratio entre dos fechas* (nunca como valor absoluto:
    ver `_cer_indice` en inversiones_analytics.py), y la UVA es el CER escalado por una
    constante — esa constante se cancela en cualquier ratio, así que esta serie sirve tal
    cual como reemplazo/complemento del CER sin necesidad de reconstruirlo.
    """
    data = get_json(f"{BASE_URL}/finanzas/indices/uva")
    if not isinstance(data, list):
        return None
    out = []
    for item in data:
        fecha = _parse_fecha(item.get("fecha", ""))
        valor = item.get("valor")
        if fecha is None or valor is None:
            continue
        try:
            out.append((fecha, float(valor)))
        except (TypeError, ValueError):
            continue
    return out or None


def fetch_dolar_mep_historico() -> list[tuple[date, float]] | None:
    """Serie diaria de dólar MEP ("bolsa"), desde 2018. Valor = promedio compra/venta."""
    data = get_json(f"{BASE_URL}/cotizaciones/dolares/bolsa")
    if not isinstance(data, list):
        return None
    out = []
    for item in data:
        fecha = _parse_fecha(item.get("fecha", ""))
        compra = item.get("compra")
        venta = item.get("venta")
        if fecha is None or (compra is None and venta is None):
            continue
        try:
            if compra is not None and venta is not None:
                valor = (float(compra) + float(venta)) / 2
            else:
                valor = float(venta if venta is not None else compra)
        except (TypeError, ValueError):
            continue
        out.append((fecha, valor))
    return out or None


def fetch_inflacion_mensual() -> list[tuple[date, float]] | None:
    """Serie mensual de inflación INDEC: (fecha_fin_de_mes, variación % de ese mes)."""
    data = get_json(f"{BASE_URL}/finanzas/indices/inflacion")
    if not isinstance(data, list):
        return None
    out = []
    for item in data:
        fecha = _parse_fecha(item.get("fecha", ""))
        valor = item.get("valor")
        if fecha is None or valor is None:
            continue
        try:
            out.append((fecha, float(valor)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda t: t[0])
    return out or None
