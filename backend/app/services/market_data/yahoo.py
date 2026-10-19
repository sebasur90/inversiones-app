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


def fetch_cierres_lote(
    simbolos: list[str], desde: date, hasta: date | None = None,
) -> tuple[dict[str, list[tuple[date, float]]], bool]:
    """Cierres diarios ajustados de varios símbolos en una sola llamada: `({simbolo: [(fecha, cierre)]}, rate_limited)`.

    Es lo que permite medir la variación de ~460 emisores sin 460 requests. Un símbolo que Yahoo
    no devuelve (o devuelve vacío) simplemente no aparece en el resultado: no corta al resto. Ante
    un límite de tasa se devuelve lo que haya y `rate_limited=True`, para que quien llama deje de
    pedir. Nunca lanza.
    """
    if not simbolos:
        return {}, False
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover - yfinance está en requirements
        return {}, False

    hasta = hasta or date.today()
    try:
        df = yf.download(
            list(simbolos),
            start=desde.isoformat(),
            end=(hasta + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=True,
            actions=False,
            group_by="ticker",
            threads=False,
            progress=False,
            timeout=_YF_TIMEOUT,
        )
    except Exception as exc:
        if _es_rate_limit(exc):
            logger.warning("yahoo: límite de tasa en la descarga en lote: %s", exc)
            return {}, True
        logger.warning("yahoo: falló la descarga en lote de %d símbolos: %s", len(simbolos), exc)
        return {}, False

    if df is None or getattr(df, "empty", True):
        return {}, False

    out: dict[str, list[tuple[date, float]]] = {}
    # Con un solo símbolo yfinance devuelve columnas planas aunque se pida group_by="ticker".
    multi = getattr(df.columns, "nlevels", 1) > 1
    for simbolo in simbolos:
        try:
            sub = df[simbolo] if multi else df
            if "Close" not in sub.columns:
                continue
            serie: list[tuple[date, float]] = []
            for idx, valor in sub["Close"].items():
                cierre = _num(valor)
                if cierre is None or cierre <= 0:
                    continue
                serie.append((idx.date(), cierre))
        except (KeyError, AttributeError, ValueError):
            continue
        if serie:
            serie.sort(key=lambda p: p[0])
            out[simbolo] = serie
    return out, False


def fetch_ultimo_precio(ticker: str) -> dict | None:
    """`{"precio", "moneda"}` del último precio conocido de `ticker`, o `None` si no se pudo.

    Sale de `fast_info` (la misma vía barata que `fetch_info`), que durante la rueda devuelve el
    precio **intradía**. Eso es justamente para qué existe: la serie `TICKER@SUB` sólo se refresca
    en el sync de la tarde, así que una zona en dólares cruzada al mediodía avisaría recién a la
    noche. El job liviano de precios llama a esto.

    La moneda viaja y no se asume: una zona en dólares que se comparara contra un precio en otra
    moneda daría un aviso falso. Quien la consume exige `USD`.

    Nunca lanza: cualquier fallo es `None` y el job sigue con los demás tickers.
    """
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        return None

    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        # yfinance cambió el nombre de esta clave entre versiones y `fast_info` no es un dict
        # común: se prueban las dos grafías antes de darla por perdida.
        precio = _num(fi.get("last_price") if hasattr(fi, "get") else None)
        if precio is None:
            precio = _num(getattr(fi, "last_price", None))
        moneda = _texto(fi.get("currency") if hasattr(fi, "get") else None).upper()
    except Exception as exc:
        logger.warning("yahoo: fast_info falló para %s: %s", ticker, exc)
        return None

    if precio is None or precio <= 0:
        return None
    return {"precio": precio, "moneda": moneda}


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


# ---------------------------------------------------------------------------------------------
# Fundamentales (clasificación + valuación contra pares)
# ---------------------------------------------------------------------------------------------

# Lista blanca de claves de `get_info()`. Lo que no está acá no se guarda: `get_info()` devuelve
# ~150 claves (direcciones, empleados, resúmenes de negocio) que inflarían la DB sin uso, y fijar
# la lista deja a la vista de qué depende la valuación si yfinance cambia nombres.
CLAVES_TEXTO = (
    "quoteType", "longName", "shortName", "sector", "industry", "country", "category",
    "fundFamily", "currency", "financialCurrency", "exchange", "website",
)
CLAVES_NUMERO = (
    # tamaño
    "marketCap", "enterpriseValue", "totalAssets", "sharesOutstanding",
    # valuación
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda", "enterpriseToRevenue",
    "priceToSalesTrailing12Months", "pegRatio", "trailingPegRatio", "dividendYield",
    "trailingAnnualDividendYield", "yield", "freeCashflow",
    # calidad
    "grossMargins", "operatingMargins", "profitMargins", "ebitdaMargins", "returnOnEquity",
    "returnOnAssets", "debtToEquity",
    # crecimiento
    "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
    # magnitudes para recalcular ratios en otra moneda
    "netIncomeToCommon", "totalRevenue", "ebitda", "trailingEps", "forwardEps", "bookValue",
    # período contable al que corresponden los datos (epoch en segundos), solidez del dividendo y liquidez
    "mostRecentQuarter", "payoutRatio", "currentRatio",
    # consenso de analistas: referencia externa del valor razonable (no entra al cálculo)
    "targetMeanPrice", "targetLowPrice", "targetHighPrice", "numberOfAnalystOpinions",
    # precio y riesgo
    "currentPrice", "regularMarketPrice", "previousClose", "beta", "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    # ETFs
    "netExpenseRatio", "annualReportExpenseRatio", "ytdReturn", "threeYearAverageReturn",
    "fiveYearAverageReturn",
)

ESTADO_OK = "ok"
ESTADO_NO_ENCONTRADO = "no_encontrado"
ESTADO_ERROR = "error"
ESTADO_RATE_LIMITED = "rate_limited"


class ResultadoYahoo:
    """Resultado de una consulta de fundamentales. **No lanza**: el estado dice qué pasó.

    `rate_limited` es distinto de `error` a propósito: ante un 429 la ingesta corta la corrida
    entera (seguir sólo alarga el bloqueo), ante un error suelto sigue con el próximo símbolo.
    """
    __slots__ = ("estado", "datos", "error")

    def __init__(self, estado: str, datos=None, error: str | None = None):
        self.estado = estado
        self.datos = datos
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"ResultadoYahoo({self.estado!r}, error={self.error!r})"


def _es_rate_limit(exc: Exception) -> bool:
    nombre = type(exc).__name__.lower()
    texto = str(exc).lower()
    return "ratelimit" in nombre or "429" in texto or "too many requests" in texto or "rate limit" in texto


def _resultado_de_excepcion(simbolo: str, exc: Exception) -> "ResultadoYahoo":
    if _es_rate_limit(exc):
        logger.warning("yahoo: límite de tasa al pedir %s: %s", simbolo, exc)
        return ResultadoYahoo(ESTADO_RATE_LIMITED, error=str(exc)[:300])
    texto = str(exc).lower()
    if "404" in texto or "not found" in texto or "no data found" in texto:
        return ResultadoYahoo(ESTADO_NO_ENCONTRADO, error=str(exc)[:300])
    logger.warning("yahoo: fundamentales de %s fallaron: %s", simbolo, exc)
    return ResultadoYahoo(ESTADO_ERROR, error=str(exc)[:300])


def fetch_fundamentales(simbolo: str) -> ResultadoYahoo:
    """Clasificación y fundamentales de `simbolo` (símbolo de Yahoo) desde `get_info()`.

    `datos` es un dict con las claves de `CLAVES_TEXTO`/`CLAVES_NUMERO` que vinieron con valor
    (números finitos, textos no vacíos). Un símbolo sin `quoteType` ni nombre es
    `no_encontrado`: Yahoo responde un dict casi vacío en vez de un 404 para lo que no conoce.
    """
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        return ResultadoYahoo(ESTADO_ERROR, error="yfinance no instalado")

    try:
        info = yf.Ticker(simbolo).get_info() or {}
    except Exception as exc:
        return _resultado_de_excepcion(simbolo, exc)

    if not isinstance(info, dict):
        return ResultadoYahoo(ESTADO_ERROR, error="respuesta inesperada")

    datos: dict = {}
    for clave in CLAVES_TEXTO:
        valor = _texto(info.get(clave))
        if valor:
            datos[clave] = valor
    for clave in CLAVES_NUMERO:
        valor = _num(info.get(clave))
        if valor is not None:
            datos[clave] = valor

    if not datos.get("quoteType") and not (datos.get("longName") or datos.get("shortName")):
        return ResultadoYahoo(ESTADO_NO_ENCONTRADO)
    return ResultadoYahoo(ESTADO_OK, datos=datos)


def fetch_cierres_semanales(simbolo: str, semanas: int = 56) -> ResultadoYahoo:
    """Cierres semanales ajustados de las últimas `semanas`, en la moneda del símbolo.

    `datos` = `[{"fecha": "YYYY-MM-DD", "cierre": float}, ...]` ordenada. Alcanza para medir el
    rendimiento a 3, 6 y 12 meses contra los pares sin bajar la serie diaria de ~460 emisores
    (que además no tienen lugar en `serie_ohlcv`: esa tabla es de cartera y watchlist).
    """
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover
        return ResultadoYahoo(ESTADO_ERROR, error="yfinance no instalado")

    hasta = date.today()
    desde = hasta - timedelta(weeks=semanas)
    try:
        df = yf.Ticker(simbolo).history(
            start=desde.isoformat(),
            end=(hasta + timedelta(days=1)).isoformat(),
            interval="1wk",
            auto_adjust=True,
            actions=False,
            raise_errors=False,
            timeout=_YF_TIMEOUT,
        )
    except Exception as exc:
        return _resultado_de_excepcion(simbolo, exc)

    if df is None or getattr(df, "empty", True) or "Close" not in getattr(df, "columns", ()):
        return ResultadoYahoo(ESTADO_ERROR, error="serie semanal vacía")

    serie = []
    for idx, fila in df.iterrows():
        try:
            fecha = idx.date()
        except (AttributeError, ValueError):
            continue
        cierre = _num(fila.get("Close"))
        if cierre is None or cierre <= 0:
            continue
        serie.append({"fecha": fecha.isoformat(), "cierre": cierre})
    serie.sort(key=lambda p: p["fecha"])
    if not serie:
        return ResultadoYahoo(ESTADO_ERROR, error="serie semanal sin cierres válidos")
    return ResultadoYahoo(ESTADO_OK, datos=serie)
