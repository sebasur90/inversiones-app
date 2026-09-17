"""Watchlist: instrumentos a seguir y su distancia a la zona de compra.

La diferencia con las alertas de precio de `Posiciones` es la dirección: el `Objetivo` de un
instrumento en cartera es un precio de **venta** (se cruza hacia arriba), mientras que el de la
watchlist es un precio de **compra** (se cruza hacia abajo). Por eso `_nivel_precio` se invoca acá
con `alcanzado_si_mayor=False`, igual que el stop-loss.

La detección de "cerca" (el umbral de proximidad) vive en el frontend, como la de posiciones: es
una preferencia del usuario guardada en localStorage y se aplica sobre `pct_a_objetivo` sin
necesidad de re-sincronizar.

Además del cálculo, este módulo tiene el alta/baja/edición: la watchlist la gestiona el usuario
desde la app y el ticker sale del catálogo de IOL (`catalogo_instrumentos`), no de la pestaña
`Watchlist` del Sheet, que ya no se lee.
"""
from datetime import date

from sqlalchemy.orm import Session

from ..database import (
    BarraOHLCV,
    EstadoMarketDataTicker,
    InstrumentoInversion,
    MovimientoInversion,
    PrecioWatchlist,
    WatchlistItem,
)
from . import catalogo_instrumentos
from .inversiones_analytics import (
    _holdings_por_cartera_ticker,
    _nivel_precio,
    _precio_conocido,
    _precios_por_ticker,
)
from . import market_data
from .market_data import precios as market_data_precios
from .validation.types import ValidationIssue


def _tickers_en_cartera(db: Session, hasta: date) -> set[str]:
    """Tickers con tenencia > 0 a `hasta`, sumando todas las carteras."""
    movs = db.query(MovimientoInversion).all()
    totales: dict[str, float] = {}
    for (_cartera, ticker), cantidad in _holdings_por_cartera_ticker(movs, hasta).items():
        totales[ticker] = totales.get(ticker, 0.0) + cantidad
    return {t for t, cant in totales.items() if cant > 0}


def get_watchlist(db: Session) -> list[dict]:
    """La watchlist con precio actual, distancia al objetivo y si está en zona de compra.

    El precio sale de la serie de `precios_instrumento` (con carry-forward) cuando el ticker
    también existe en `Instrumentos` -- ahí hay historia real --, y de `precios_watchlist` cuando
    es un ticker que sólo se está siguiendo.

    Ordena por urgencia: primero lo que ya está en zona, después lo más cerca del objetivo, y al
    final lo que no tiene objetivo o precio.
    """
    items = db.query(WatchlistItem).order_by(WatchlistItem.ticker).all()
    if not items:
        return []

    hoy = date.today()
    tickers_instrumento = {row[0] for row in db.query(InstrumentoInversion.ticker).all()}
    en_cartera = _tickers_en_cartera(db, hoy)
    precios_wl = {row.ticker: row for row in db.query(PrecioWatchlist).all()}
    precios_inst = _precios_por_ticker(db) if tickers_instrumento else {}

    resultado: list[dict] = []
    for item in items:
        precio_actual: float | None = None
        fecha_precio: date | None = None
        moneda_precio: str | None = None
        fuente_precio: str | None = None

        if item.ticker in tickers_instrumento:
            conocido = _precio_conocido(precios_inst.get(item.ticker, []), hoy)
            if conocido is not None:
                fecha_precio, precio_actual, moneda_precio = conocido
                fuente_precio = "cartera"
        else:
            fila = precios_wl.get(item.ticker)
            if fila is not None:
                fecha_precio = fila.fecha
                precio_actual = float(fila.precio)
                moneda_precio = fila.moneda
                fuente_precio = fila.fuente

        objetivo = float(item.objetivo) if item.objetivo is not None else None
        precio_objetivo, pct_a_objetivo, en_zona = _nivel_precio(
            "Fijo" if objetivo is not None else None,
            objetivo,
            0.0,  # sin precio promedio de compra: el modo "Fijo" no lo usa
            precio_actual if precio_actual is not None else 0.0,
            alcanzado_si_mayor=False,
        )

        resultado.append({
            "ticker": item.ticker,
            "nombre": item.nombre,
            "tipo_instrumento": item.tipo_instrumento,
            "mercado": item.mercado,
            "moneda": item.moneda,
            "pais": item.pais,
            "sector": item.sector,
            "precio_actual": precio_actual,
            "fecha_precio": fecha_precio,
            "moneda_precio": moneda_precio or item.moneda,
            "fuente_precio": fuente_precio,
            "precio_objetivo": precio_objetivo,
            "pct_a_objetivo": pct_a_objetivo,
            "en_zona": en_zona,
            "en_cartera": item.ticker in en_cartera,
            "notas": item.notas,
            "agregado_en": item.agregado_en,
        })

    def _orden(fila: dict) -> tuple[int, float]:
        if fila["en_zona"]:
            return (0, -abs(fila["pct_a_objetivo"] or 0.0))
        if fila["pct_a_objetivo"] is not None:
            return (1, abs(fila["pct_a_objetivo"]))
        return (2, 0.0)

    return sorted(resultado, key=_orden)


def get_watchlist_item(db: Session, ticker: str) -> dict | None:
    """La fila de `get_watchlist` de un solo ticker, o None si no está en la watchlist.

    Recalcula la lista entera: son unas pocas decenas de ítems y así la respuesta de un alta o una
    edición sale por exactamente el mismo camino que la de la pantalla, sin una segunda versión del
    cálculo que se pueda desincronizar.
    """
    for fila in get_watchlist(db):
        if fila["ticker"] == ticker:
            return fila
    return None


def _item_a_dict(item: WatchlistItem) -> dict:
    """La forma que esperan las funciones de `market_data.precios` (las mismas claves que los dicts
    validados del Sheet que recibían antes)."""
    return {
        "ticker": item.ticker,
        "nombre": item.nombre,
        "tipo_instrumento": item.tipo_instrumento,
        "mercado": item.mercado,
        "moneda": item.moneda,
        "pais": item.pais,
        "sector": item.sector,
        "objetivo": float(item.objetivo) if item.objetivo is not None else None,
    }


def items_para_market_data(db: Session) -> list[dict]:
    """Los ítems de la watchlist en la forma que consume `market_data.precios`. Lo usa el sync."""
    return [_item_a_dict(i) for i in db.query(WatchlistItem).order_by(WatchlistItem.ticker).all()]


def refrescar_precios(
    db: Session, tickers: list[str] | None = None, paneles_fn=None, fci_fn=None,
    max_simbolos_sueltos: int | None = None, tickers_en_cartera: set[str] | None = None,
    solo_simbolo_suelto: bool = False,
) -> tuple[int, list[ValidationIssue]]:
    """Re-cotiza la watchlist (o sólo `tickers`) y hace upsert en `precios_watchlist`.

    Se saltea los que están en cartera: para esos `get_watchlist` lee la serie de
    `precios_instrumento`, que tiene historia real y la resuelve el pipeline de cartera.

    `solo_simbolo_suelto`: para un ticker solo (un alta, el botón "Precio"), pedir la tanda entera
    de paneles costaría ~9 llamadas del cupo para cotizar uno. Con esto va derecho al endpoint por
    símbolo: 1 llamada. El sync no lo usa, porque ahí los paneles ya están pedidos y memoizados.

    `tickers_en_cartera`: qué considerar "en cartera". El sync lo pasa explícito porque llama a esto
    **antes** de reescribir `instrumentos_inversion`, así que la tabla todavía tiene la foto de la
    corrida anterior; el endpoint lo omite y se lee de la DB, que ahí sí está al día.

    No hace commit: lo hace el llamador (el endpoint, o la transacción del sync).
    Devuelve (cuántos precios se actualizaron, issues).
    """
    # Vía el paquete (y no `from .client import`) para compartir el binding que usa el sync: es el
    # que se sustituye en los tests y el que respeta `USE_EXTERNAL_APIS`.
    if not market_data.use_external_apis():
        return 0, []

    query = db.query(WatchlistItem)
    if tickers is not None:
        if not tickers:
            return 0, []
        query = query.filter(WatchlistItem.ticker.in_(tickers))
    items = query.all()
    if not items:
        return 0, []

    if tickers_en_cartera is None:
        tickers_en_cartera = {row[0] for row in db.query(InstrumentoInversion.ticker).all()}
    a_cotizar = [_item_a_dict(i) for i in items if i.ticker not in tickers_en_cartera]
    if not a_cotizar:
        return 0, []

    extra = {} if max_simbolos_sueltos is None else {"max_simbolos_sueltos": max_simbolos_sueltos}
    filas, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        a_cotizar, db, paneles_fn=paneles_fn, fci_fn=fci_fn,
        solo_simbolo_suelto=solo_simbolo_suelto, **extra,
    )
    for fila in filas:
        existente = db.get(PrecioWatchlist, fila["ticker"])
        if existente is None:
            db.add(PrecioWatchlist(**fila))
        else:
            existente.fecha = fila["fecha"]
            existente.precio = fila["precio"]
            existente.moneda = fila["moneda"]
            existente.fuente = fila["fuente"]
    db.flush()
    return len(filas), issues


def agregar(
    db: Session, simbolo: str, objetivo: float | None = None, notas: str | None = None,
) -> tuple[WatchlistItem | None, str | None, list[ValidationIssue]]:
    """Da de alta un instrumento del catálogo y le baja el precio en el acto.

    Devuelve `(item, error, issues)`, donde `error` es `"no_encontrado"` si el símbolo no está en el
    catálogo o `"duplicado"` si ya está en la watchlist.

    La cotización es **best effort**: si IOL no responde o no cotiza el símbolo, el ítem se crea
    igual (sin precio) y el motivo vuelve en `issues`. El alta no puede depender de que una API de
    terceros esté arriba.
    """
    entrada = catalogo_instrumentos.obtener(simbolo)
    if entrada is None:
        return None, "no_encontrado", []

    ticker = entrada["simbolo"]
    if db.get(WatchlistItem, ticker) is not None:
        return None, "duplicado", []

    item = WatchlistItem(
        ticker=ticker,
        nombre=entrada["descripcion"],
        tipo_instrumento=entrada["tipo"],
        mercado=entrada["mercado"],
        moneda=entrada["moneda"],
        pais="argentina",
        sector=None,
        objetivo=objetivo,
        notas=(notas or "").strip() or None,
        agregado_en=date.today(),
    )
    db.add(item)
    db.flush()

    # Una sola llamada a IOL: el endpoint por símbolo, sin bajar los paneles enteros.
    _, issues = refrescar_precios(db, [ticker], max_simbolos_sueltos=1, solo_simbolo_suelto=True)
    return item, None, issues


def actualizar(db: Session, ticker: str, cambios: dict) -> WatchlistItem | None:
    """Edita los campos que el usuario controla. El resto (nombre, tipo, moneda, mercado) sale del
    catálogo y no se toca a mano: si estuviera mal, lo que corresponde es regenerar el catálogo.

    `cambios` trae **sólo las claves que el request mandó** (`exclude_unset`), así un PUT parcial
    con `{"objetivo": 1300}` no borra las notas. Mandar `null` explícito sí limpia el campo.
    """
    item = db.get(WatchlistItem, ticker)
    if item is None:
        return None
    if "objetivo" in cambios:
        item.objetivo = cambios["objetivo"]
    if "notas" in cambios:
        item.notas = (cambios["notas"] or "").strip() or None
    db.flush()
    return item


def eliminar(db: Session, ticker: str) -> bool:
    """Saca el instrumento de la watchlist y limpia lo que quedaría huérfano.

    Las velas y el estado de market data sólo se borran si el ticker **no** está en cartera: si lo
    está, esa serie la usa el análisis técnico de la posición y no es de la watchlist.
    """
    item = db.get(WatchlistItem, ticker)
    if item is None:
        return False

    db.delete(item)
    precio = db.get(PrecioWatchlist, ticker)
    if precio is not None:
        db.delete(precio)

    # Por `ticker`, no con `db.get`: la PK de `InstrumentoInversion` es `id`.
    en_cartera = db.query(InstrumentoInversion).filter(
        InstrumentoInversion.ticker == ticker
    ).first() is not None
    if not en_cartera:
        # `TICKER@SUB` es la clave derivada de la serie del subyacente en USD (ver
        # `market_data.precios.fetch_backfill_ohlcv_subyacente`); se va con el ticker.
        db.query(BarraOHLCV).filter(
            BarraOHLCV.ticker.in_((ticker, f"{ticker}@SUB"))
        ).delete(synchronize_session=False)
        estado = db.get(EstadoMarketDataTicker, ticker)
        if estado is not None:
            db.delete(estado)

    db.flush()
    return True
