"""Cliente del datafeed de analisistecnico.com.ar — API pública (TradingView UDF), sin auth.

`/history` devuelve la serie diaria completa de una especie en un rango, como arrays paralelos
`{s, t, o, h, l, c, v}` (sin paginar). Cubre renta fija soberana y provincial, Boncer/CER,
BONCAP/LECAP y dollar-linked — el mismo universo que `data912 /live/arg_bonds` +
`/live/arg_notes` — cotizada en **ARS por lámina de 100 VN** (misma escala que data912, así que
`precios.py` la calibra con la misma lógica de ratio contra el último precio manual del Sheet).

**No** cubre ONs corporativas (`/live/arg_corp`): para esos tickers devuelve `{"s": "error"}`.

Probado desde el ambiente corporativo (con proxy) el 2026-08-28: responde 200 con User-Agent de
navegador y trae series frescas al día.
"""
from datetime import date, datetime, timezone

from .client import get_json

BASE_URL = "https://analisistecnico.com.ar/services/datafeed"


def fetch_historico_bono(ticker: str, desde: date, hasta: date) -> list[tuple[date, float]] | None:
    """Serie diaria `[(fecha, cierre), ...]` de `ticker` en `[desde, hasta]`, ordenada por fecha.

    Devuelve:
      - `None` si la petición falló (red caída, JSON inesperado, o `s != "ok"` — un símbolo
        desconocido, p.ej. una ON, responde `{"s": "error"}`),
      - `[]` si el símbolo existe pero no tuvo ruedas en el rango (`{"s": "no_data"}`) o no vino
        ningún cierre usable.
    Nunca lanza.
    """
    desde_ts = int(datetime(desde.year, desde.month, desde.day, tzinfo=timezone.utc).timestamp())
    hasta_ts = int(datetime(hasta.year, hasta.month, hasta.day, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    url = f"{BASE_URL}/history?symbol={ticker}&resolution=D&from={desde_ts}&to={hasta_ts}"
    data = get_json(url)
    if not isinstance(data, dict):
        return None
    estado = data.get("s")
    if estado == "no_data":
        return []
    if estado != "ok":
        return None

    tiempos, cierres = data.get("t"), data.get("c")
    if not isinstance(tiempos, list) or not isinstance(cierres, list):
        return None

    out: list[tuple[date, float]] = []
    for ts, px in zip(tiempos, cierres):
        try:
            # Las barras vienen con timestamp intradiario (hora de sesión, no medianoche); en UTC
            # cae siempre dentro del mismo día calendario de la rueda.
            fecha = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
            precio = float(px)
        except (TypeError, ValueError, OSError):
            continue
        if precio > 0:
            out.append((fecha, precio))
    out.sort(key=lambda t: t[0])
    return out
