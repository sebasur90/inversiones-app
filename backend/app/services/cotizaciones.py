"""Fetch USD exchange rates from dolarapi.com (used as fallback for MEP lookups)."""
import httpx
from datetime import date
from sqlalchemy.orm import Session


DOLAR_API_URL = "https://dolarapi.com/v1/dolares"

TYPE_MAP = {
    "oficial": "oficial",
    "blue": "blue",
    "bolsa": "mep",
    "contadoconliqui": "mep",
    "mayorista": "mayorista",
}


async def fetch_and_cache_today(db: Session) -> bool:
    """Validate connection to dolarapi.com on startup."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DOLAR_API_URL)
            resp.raise_for_status()
        return True
    except Exception:
        return False


def get_rates_for_date(target_date: date, db: Session) -> dict:
    """Get rates for a given date. Currently unused (MEP comes from IndiceMercado)."""
    return {}
