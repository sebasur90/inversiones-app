"""Cliente de yfinance para la serie del subyacente en USD (acción o ADR listado en EE.UU.).

yfinance hace su propio HTTP con `curl_cffi` — **no** pasa por `market_data.client`. Respeta
`HTTP_PROXY` / `HTTPS_PROXY` del entorno (ambiente corporativo, verificado), pero el manejo de
errores va acá: todo envuelto en `try/except`, se devuelve `None` ante cualquier fallo, nunca se
lanza.

Contrato calcado de `analisistecnico.fetch_historico_ohlcv` para que el orquestador no note la
diferencia: `list[BarraCruda]` ordenada por fecha, `None` si la petición falló, `[]` si el
símbolo existe pero no tuvo ruedas en el rango.

yfinance se traga los errores de red y devuelve un DataFrame vacío en vez de una excepción. Un
resultado vacío es ambiguo entre "no hubo ruedas" y "la red falló": se trata como `None` (fallo)
salvo que el rango pedido sea genuinamente sin ruedas (ventana corta que cae toda en fin de
semana).

**pandas no cruza este módulo**: el DataFrame se convierte a `list[BarraCruda]` acá mismo; el
resto del pipeline de análisis técnico es de listas puras de Python.

Convención de símbolos de Yahoo: el ticker pelado es el listado en EE.UU. (acción o ADR) y el
sufijo `.BA` es el listado local en BYMA. Para un CEDEAR el ticker local *es* el del subyacente
por construcción.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from .ohlcv_types import BarraCruda

logger = logging.getLogger("market_data.yahoo")

# Tope explícito por request. yfinance ya trae un default interno, pero pasarlo a mano deja el
# límite a la vista y lo fija aunque cambie el default de la librería. Un peor caso son decenas de
# llamadas secuenciales por sync (resolución + backfill del subyacente).
_YF_TIMEOUT = 30


def _num(x) -> float | None:
    """`float` finito, o `None` (incluye NaN de pandas, que no es igual a sí mismo)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _texto(x) -> str:
    try:
        return str(x).strip() if x is not None else ""
    except Exception:
        return ""


def _rango_tiene_ruedas(desde: date, hasta: date) -> bool:
    """¿`[desde, hasta]` contiene al menos un día hábil? Proxy sin calendario de feriados:
    cualquier ventana de 4+ días lo contiene; una más corta puede caer toda en fin de semana."""
    if (hasta - desde).days >= 4:
        return True
    d = desde
    while d <= hasta:
        if d.weekday() < 5:
            return True
        d += timedelta(days=1)
    return False


def fetch_historico_ohlcv(ticker: str, desde: date, hasta: date) -> list[BarraCruda] | None:
    """Serie diaria `[BarraCruda, ...]` de `ticker` en `[desde, hasta]`, ajustada por splits y
    dividendos (`auto_adjust=True`), ordenada por fecha.

    Devuelve `None` si la petición falló (red caída, yfinance ausente, DataFrame inesperado o
    vacío sobre un rango que sí tenía ruedas); `[]` si el símbolo existe pero el rango pedido no
    tuvo ninguna rueda. Nunca lanza.

    Si una barra trae `o/h/l` inconsistentes con el cierre se conserva `fecha`/`cierre` y se
    anulan `o/h/l` — igual criterio que `analisistecnico`.
    """
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover - yfinance está en requirements
        logger.warning("yfinance no está instalado; la serie del subyacente queda deshabilitada")
        return None

    try:
        t = yf.Ticker(ticker)
        # `end` es exclusivo en yfinance: +1 día para incluir la rueda de `hasta`.
        df = t.history(
            start=desde.isoformat(),
            end=(hasta + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=True,
            actions=False,
            raise_errors=False,
            timeout=_YF_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("yahoo: falló la serie histórica de %s: %s", ticker, exc)
        return None

    if df is None or getattr(df, "empty", True):
        return [] if not _rango_tiene_ruedas(desde, hasta) else None

    if not all(col in df.columns for col in ("Open", "High", "Low", "Close")):
        return None

    out: list[BarraCruda] = []
    for idx, fila in df.iterrows():
        try:
            fecha = idx.date()
        except (AttributeError, ValueError):
            continue
        cierre = _num(fila.get("Close"))
        if cierre is None or cierre <= 0:
            continue
        o, h, l, v = _num(fila.get("Open")), _num(fila.get("High")), _num(fila.get("Low")), _num(fila.get("Volume"))
        if o is not None and h is not None and l is not None:
            if not (l <= min(o, cierre) and h >= max(o, cierre)):
                o = h = l = None
        out.append(BarraCruda(fecha=fecha, cierre=cierre, apertura=o, maximo=h, minimo=l, volumen=v))

    out.sort(key=lambda b: b.fecha)
    return out


def fetch_info(ticker: str) -> dict | None:
    """`{"moneda", "mercado", "nombre"}` del símbolo en Yahoo.

    `moneda` (upper) y `mercado` salen de `fast_info` (más barato que `.info`); `nombre` se
    intenta desde `.get_info()` y degrada a `None` si esa llamada falla. Devuelve `None` si ni
    siquiera `fast_info` resolvió (símbolo inexistente o red caída).

    Sirve de guarda en la resolución del subyacente: sólo se acepta un subyacente con
    `moneda == "USD"`.
    """
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        return None

    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        moneda = _texto(fi.get("currency")).upper()
        mercado = _texto(fi.get("exchange"))
    except Exception as exc:
        logger.warning("yahoo: fast_info falló para %s: %s", ticker, exc)
        return None

    if not moneda and not mercado:
        return None

    nombre = None
    try:
        info = t.get_info() or {}
        nombre = _texto(info.get("longName") or info.get("shortName")) or None
    except Exception as exc:
        logger.warning("yahoo: get_info falló para %s (se sigue sin nombre): %s", ticker, exc)
        nombre = None

    return {"moneda": moneda, "mercado": mercado, "nombre": nombre}
