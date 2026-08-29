"""Cliente autenticado de la API de InvertirOnline (IOL) — fuente primaria de cotizaciones.

Requiere una cuenta IOL con el servicio de API habilitado (es opcional, con habilitación previa
desde la cuenta — ver DESARROLLO.md) y credenciales en el archivo que resuelve
`iol_auth._credentials_path()`. Todo acá es "best effort" igual que el resto de `market_data`:
cualquier fallo (sin credenciales, cupo agotado, red caída, panel desconocido) se traduce en
`None`, nunca se lanza, y el llamador (`precios.py`) cae a data912/analisistecnico.

Un panel (`/Cotizaciones/{instrumento}/{panel}/{pais}`) trae docenas de símbolos en una sola
llamada — es la pieza clave para no acercarse al cupo mensual bonificado (25.000 llamadas): un
sync típico gasta ~7 llamadas (1 token + paneles) en vez de una por ticker.

Los nombres de panel en `_PANELES` **no están confirmados contra la documentación oficial**
(`api.invertironline.com/Help` responde 403 a cualquier cliente que no sea un navegador logueado);
se fijaron con lo que expone código de terceros y hay que validarlos una vez, con una cuenta real,
con `backend/scripts/iol_probe.py`. Si un nombre no existe, ese panel simplemente no aporta
símbolos (degrada, no rompe): `fetch_precios_paneles` sólo devuelve `None` si NINGÚN panel
respondió, y `precios.py` completa con data912/analisistecnico lo que los paneles no cubran.
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from . import iol_auth

# (instrumento, panel, pais) -> una llamada, docenas de símbolos. Ajustar los nombres exactos
# según lo que devuelva `scripts/iol_probe.py` contra una cuenta real.
_PANELES = (
    ("acciones", "Panel General", "argentina"),
    ("acciones", "Merval", "argentina"),
    ("Acciones", "CEDEARs", "Argentina"),
    ("bonos", "Soberanos en dólares", "argentina"),
    ("bonos", "Soberanos en pesos", "argentina"),
    ("bonos", "Corporativos", "argentina"),
    ("letras", "Todas", "argentina"),
)

_MERCADO_DEFAULT = "bCBA"


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_panel(db: Session, instrumento: str, panel: str, pais: str) -> dict[str, tuple[float, str]] | None:
    url = f"{iol_auth.BASE_URL}/Cotizaciones/{instrumento}/{panel}/{pais}"
    data = iol_auth.get_autenticado(db, url)
    if not isinstance(data, dict):
        return None
    titulos = data.get("titulos")
    if not isinstance(titulos, list):
        return None
    out: dict[str, tuple[float, str]] = {}
    for fila in titulos:
        if not isinstance(fila, dict):
            continue
        simbolo = (fila.get("simbolo") or "").strip().upper()
        precio = _num(fila.get("ultimoPrecio"))
        moneda = (fila.get("moneda") or "").strip().upper() or "ARS"
        if simbolo and precio is not None and precio > 0:
            out[simbolo] = (precio, moneda)
    return out


def fetch_precios_paneles(db: Session) -> dict[str, tuple[float, str]] | None:
    """`simbolo -> (ultimoPrecio, moneda)`, uniendo todos los paneles de `_PANELES` (una llamada
    cada uno). Devuelve `None` sólo si NINGÚN panel respondió (mismo contrato que
    `data912._fetch_live`): así el llamador distingue "IOL está caída/sin cupo/deshabilitada" de
    "respondió pero sin ese ticker en particular"."""
    out: dict[str, tuple[float, str]] = {}
    alguno_respondio = False
    for instrumento, panel, pais in _PANELES:
        fila = _fetch_panel(db, instrumento, panel, pais)
        if fila is None:
            continue
        alguno_respondio = True
        for simbolo, valor in fila.items():
            out.setdefault(simbolo, valor)
    return out if alguno_respondio else None


def fetch_precios_fci(db: Session) -> dict[str, tuple[float, str]] | None:
    """`simbolo -> (valorCuotaparte, moneda)` para todos los FCI, en una sola llamada
    (`GET /Titulos/FCI`)."""
    url = f"{iol_auth.BASE_URL}/Titulos/FCI"
    data = iol_auth.get_autenticado(db, url)
    if not isinstance(data, list):
        return None
    out: dict[str, tuple[float, str]] = {}
    for fila in data:
        if not isinstance(fila, dict):
            continue
        simbolo = (fila.get("simbolo") or "").strip().upper()
        precio = _num(fila.get("ultimoPrecio") or fila.get("valorCuotaparte"))
        moneda = (fila.get("moneda") or "").strip().upper() or "ARS"
        if simbolo and precio is not None and precio > 0:
            out[simbolo] = (precio, moneda)
    return out


def fetch_precio_simbolo(db: Session, simbolo: str, mercado: str = _MERCADO_DEFAULT) -> tuple[float, str] | None:
    """Cotización de un símbolo suelto (1 llamada). Hoy `precios.py` NO la usa —lo que los paneles
    no cubren se completa con data912, que no gasta cupo—; queda para diagnóstico manual
    (`scripts/iol_probe.py`) y como pieza lista si algún día conviene cerrar el hueco con IOL. Si
    se cablea, la cota de cuántos símbolos se piden por sync la tiene que aplicar el llamador."""
    url = f"{iol_auth.BASE_URL}/{mercado}/Titulos/{simbolo}/Cotizacion"
    data = iol_auth.get_autenticado(db, url)
    if not isinstance(data, dict):
        return None
    precio = _num(data.get("ultimoPrecio"))
    if precio is None or precio <= 0:
        return None
    moneda = (data.get("moneda") or "").strip().upper() or "ARS"
    return precio, moneda


def fetch_historico(
    db: Session, ticker: str, desde: date, hasta: date, mercado: str = _MERCADO_DEFAULT,
) -> list[tuple[date, float]] | None:
    """Serie diaria `[(fecha, cierre), ...]` vía la serie histórica de IOL para `ticker` en
    `[desde, hasta]`, ordenada por fecha. `None` si la petición falló (sin cupo, red caída, HTTP
    de error); `[]` si el símbolo existe pero no vino ningún cierre usable. Nunca lanza."""
    f_desde, f_hasta = desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")
    url = (f"{iol_auth.BASE_URL}/{mercado}/Titulos/{ticker}/Cotizacion/seriehistorica/"
           f"{f_desde}/{f_hasta}/sinAjustar")
    data = iol_auth.get_autenticado(db, url)
    if not isinstance(data, list):
        return None
    out: list[tuple[date, float]] = []
    for fila in data:
        if not isinstance(fila, dict):
            continue
        precio = _num(fila.get("ultimoPrecio"))
        fecha_raw = fila.get("fechaHora")
        if precio is None or precio <= 0 or not fecha_raw:
            continue
        try:
            fecha = datetime.fromisoformat(str(fecha_raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        out.append((fecha, precio))
    out.sort(key=lambda t: t[0])
    return out
