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
from .ohlcv_types import BarraCruda

BASE_URL = "https://analisistecnico.com.ar/services/datafeed"


def _valor(lista, i: int) -> float | None:
    if not isinstance(lista, list) or i >= len(lista):
        return None
    try:
        return float(lista[i])
    except (TypeError, ValueError):
        return None


def fetch_historico_ohlcv(ticker: str, desde: date, hasta: date) -> list[BarraCruda] | None:
    """Serie diaria de velas `[BarraCruda, ...]` de `ticker` en `[desde, hasta]`, ordenada por
    fecha. Los campos `o/h/l/v` ya vienen en la misma respuesta que el cierre — no hace falta una
    llamada extra, `fetch_historico_bono` (compatibilidad) sólo descartaba esos campos.

    Devuelve:
      - `None` si la petición falló (red caída, JSON inesperado, o `s != "ok"` — un símbolo
        desconocido, p.ej. una ON, responde `{"s": "error"}`),
      - `[]` si el símbolo existe pero no tuvo ruedas en el rango (`{"s": "no_data"}`) o no vino
        ningún cierre usable.
    Nunca lanza.

    Si una barra trae `o/h/l` pero son inconsistentes con el cierre (`mínimo` no contiene al
    menor de apertura/cierre, o `máximo` no contiene al mayor), se conserva `fecha`/`cierre` y se
    anulan `o/h/l`: una fuente inconsistente para una barra puntual no la vuelve inservible, sólo
    la degrada a close-only.
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
    aperturas, maximos, minimos, volumenes = data.get("o"), data.get("h"), data.get("l"), data.get("v")

    out: list[BarraCruda] = []
    for i, (ts, px) in enumerate(zip(tiempos, cierres)):
        try:
            # Las barras vienen con timestamp intradiario (hora de sesión, no medianoche); en UTC
            # cae siempre dentro del mismo día calendario de la rueda.
            fecha = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
            precio = float(px)
        except (TypeError, ValueError, OSError):
            continue
        if precio <= 0:
            continue

        o, h, l, v = _valor(aperturas, i), _valor(maximos, i), _valor(minimos, i), _valor(volumenes, i)
        if o is not None and h is not None and l is not None:
            if not (l <= min(o, precio) and h >= max(o, precio)):
                o = h = l = None
        out.append(BarraCruda(fecha=fecha, cierre=precio, apertura=o, maximo=h, minimo=l, volumen=v))

    out.sort(key=lambda b: b.fecha)
    return out


def fetch_historico_bono(ticker: str, desde: date, hasta: date) -> list[tuple[date, float]] | None:
    """Serie diaria `[(fecha, cierre), ...]` — wrapper de compatibilidad sobre
    `fetch_historico_ohlcv` para los llamadores que sólo necesitan el cierre (backfill de
    valuación en `precios.py`). Mismo contrato: `None` en fallo, `[]` sin ruedas."""
    barras = fetch_historico_ohlcv(ticker, desde, hasta)
    if barras is None:
        return None
    return [(b.fecha, b.cierre) for b in barras]
