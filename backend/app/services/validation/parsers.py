"""Parsers relocados desde inversiones_sync.py."""
import unicodedata
from datetime import date
from dateutil import parser as dateutil_parser

TIPOS_MOVIMIENTO = {
    "compra": "compra",
    "venta": "venta",
    "dividendo": "dividendo",
    "cupon": "cupon",
    "renta": "dividendo",
    "amortizacion": "amortizacion",
}

MONEDAS_VALIDAS = ("ARS", "USD")

EJES_REBALANCEO = {"cartera": "Cartera", "tipo": "Tipo", "sector": "Sector", "ticker": "Ticker"}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _normalize_tipo_movimiento(raw: str) -> str | None:
    key = _strip_accents(raw).strip().lower()
    return TIPOS_MOVIMIENTO.get(key)


def _parse_fecha(raw: str) -> date | None:
    from datetime import datetime

    if raw is None or raw == "":
        return None

    # Si ya es datetime/date, devolverlo
    if isinstance(raw, date):
        return raw
    if isinstance(raw, datetime):
        return raw.date()

    raw = str(raw).strip()
    if not raw:
        return None

    # Intentar ISO format primero (YYYY-MM-DD)
    try:
        return date.fromisoformat(raw.split()[0])  # Separar fecha de hora si existe
    except ValueError:
        pass

    # Luego intentar con dayfirst=True para formatos ambiguos (DD/MM/YYYY, etc)
    try:
        return dateutil_parser.parse(raw, dayfirst=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def _parse_numero(raw: str, es_indice: bool = False) -> float | None:
    """Parsea un número admitiendo notación ARS ("1.234,56") o US ("1,234.56").

    Cuando el número trae un único separador ("," o "."), es ambiguo: puede ser decimal
    ("1,5") o separador de miles ("1.519" = 1519). Con un solo "," se asume separador de
    miles si todos los grupos después tienen 3 dígitos (ej. "1,234" = 1234), igual para
    todos los campos. Con un solo "." eso solo se asume para CER/MEP (es_indice=True), ya
    que el Sheet los carga sin decimales (ej. "1.519" = 1519); para Cantidad/Precio/Comisión
    un "." aislado siempre se toma como decimal, porque esos campos pueden llevar
    legítimamente 3 decimales (ej. "1519.384").
    """
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace(" ", "").replace("$", "").replace("US$", "").replace("USD", "").replace("ARS", "")
    try:
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            partes = s.split(",")
            if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
        elif "." in s:
            partes = s.split(".")
            if es_indice and len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                s = s.replace(".", "")
        return float(s)
    except ValueError:
        return None


def _parse_nivel_precio(modo_raw, valor_raw) -> tuple[str | None, float | None, str | None]:
    """Parsea un par (Modo, Valor) de precio objetivo/stop loss. Devuelve (modo, valor, error)."""
    modo = (modo_raw or "").strip()
    valor_str = (valor_raw or "").strip()
    tiene_modo = bool(modo) and modo.lower() != "nan"
    tiene_valor = bool(valor_str) and valor_str.lower() != "nan"

    if not tiene_modo and not tiene_valor:
        return None, None, None
    if tiene_modo != tiene_valor:
        return None, None, "Modo y Valor deben completarse juntos"

    modo_normalizado = modo.strip().capitalize()
    if modo_normalizado not in ("Porcentaje", "Fijo"):
        return None, None, f"Modo desconocido: {modo}"

    valor = _parse_numero(valor_str)
    if valor is None:
        return None, None, f"Valor numérico inválido: {valor_str}"

    return modo_normalizado, valor, None
