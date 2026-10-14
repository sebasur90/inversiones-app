"""Watchlist: instrumentos a seguir y su distancia a la zona de compra.

La diferencia con las alertas de precio de `Posiciones` es la dirección: el `Objetivo` de un
instrumento en cartera es un precio de **venta** (se cruza hacia arriba), mientras que la zona de
compra de la watchlist se cruza hacia **abajo**.

El nivel ya no vive en esta tabla: desde que las zonas se dibujan sobre el gráfico, el precio de
compra es el **techo de la zona de compra** (`services/zonas_precio.py`, tabla `zonas_precio`), y
la columna `watchlist.objetivo` quedó vacía y sin lectores (ver la migración en `database.py`).
Los campos `precio_objetivo`/`pct_a_objetivo`/`en_zona` de la salida se mantienen con el mismo
nombre y el mismo criterio: son el contrato del badge de la pantalla, de `alertas_engine` y de
Oportunidades de compra del Resumen.

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
    ZonaPrecio,
)
from . import catalogo_instrumentos, cotizacion_diaria, zonas_precio
from .inversiones_analytics import (
    _holdings_por_cartera_ticker,
    _precio_conocido,
    _precios_por_ticker,
    _variacion_diaria,
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


def _cierres_barras(db: Session, tickers: list[str]) -> dict[str, list[tuple[date, float, str]]]:
    """Cierres diarios de `BarraOHLCV` con la forma de `_precios_por_ticker` (la moneda se pasa
    vacía: las velas no la guardan, así que la comparación de moneda se hace con la del precio)."""
    if not tickers:
        return {}
    filas = (
        db.query(BarraOHLCV.ticker, BarraOHLCV.fecha, BarraOHLCV.cierre)
        .filter(BarraOHLCV.ticker.in_(tickers))
        .order_by(BarraOHLCV.ticker, BarraOHLCV.fecha)
        .all()
    )
    out: dict[str, list[tuple[date, float, str]]] = {}
    for ticker, fecha, cierre in filas:
        out.setdefault(ticker, []).append((fecha, float(cierre), ""))
    return out


def get_watchlist(db: Session) -> list[dict]:
    """La watchlist con precio actual, distancia al objetivo y si está en zona de compra.

    El precio sale de la serie de `precios_instrumento` (con carry-forward) cuando el ticker
    también existe en `Instrumentos` -- ahí hay historia real --, y de `precios_watchlist` cuando
    es un ticker que sólo se está siguiendo.

    El nivel sale del techo de la zona de compra, y **sólo si la zona es de variante `local`**: una
    zona dibujada sobre la serie del subyacente está en USD del mercado de origen y compararla
    contra este precio (el CEDEAR en ARS) daría una distancia sin sentido. La zona viaja igual en
    la salida para dibujarla; quien la evalúa en su propia moneda es la corrida de alertas.

    Ordena por urgencia: primero lo que ya está en zona, después lo más cerca del borde, y al
    final lo que no tiene zona o no tiene precio.
    """
    items = db.query(WatchlistItem).order_by(WatchlistItem.ticker).all()
    if not items:
        return []

    hoy = date.today()
    tickers_instrumento = {row[0] for row in db.query(InstrumentoInversion.ticker).all()}
    en_cartera = _tickers_en_cartera(db, hoy)
    precios_wl = {row.ticker: row for row in db.query(PrecioWatchlist).all()}
    precios_inst = _precios_por_ticker(db) if tickers_instrumento else {}

    solo_seguidos = [i.ticker for i in items if i.ticker not in tickers_instrumento]
    cierres = _cierres_barras(db, solo_seguidos)
    cotizaciones_dia = cotizacion_diaria.cargar_por_clave(db, {i.ticker for i in items})
    zonas = zonas_precio.mapa_zonas(db)   # una sola consulta para toda la lista

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

        variacion_dia = variacion_dia_pct = None
        if precio_actual is not None and fecha_precio is not None:
            if item.ticker in tickers_instrumento:
                serie = precios_inst.get(item.ticker, [])
                variacion_dia, variacion_dia_pct = _variacion_diaria(
                    serie, fecha_precio, precio_actual, moneda_precio or "", cotizaciones_dia.get((item.ticker, fecha_precio)),
                )
            else:
                # Cierres de las velas: sin moneda guardada, así que se compara contra "".
                variacion_dia, variacion_dia_pct = _variacion_diaria(
                    cierres.get(item.ticker, []), fecha_precio, precio_actual, "", cotizaciones_dia.get((item.ticker, fecha_precio)),
                )

        del_ticker = zonas.get(item.ticker, zonas_precio.VACIO)
        zonas_dict = zonas_precio.a_dict(item.ticker, del_ticker)
        zona_compra = del_ticker.compra
        comparable = (
            zona_compra
            if zona_compra is not None and zona_compra.variante == zonas_precio.VARIANTE_LOCAL
            else None
        )
        precio_objetivo, pct_a_objetivo, en_zona = zonas_precio.estado_de_zona(
            comparable, precio_actual,
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
            "variacion_dia": round(variacion_dia, 6) if variacion_dia is not None else None,
            "variacion_dia_pct": round(variacion_dia_pct, 4) if variacion_dia_pct is not None else None,
            "precio_objetivo": precio_objetivo,
            "pct_a_objetivo": pct_a_objetivo,
            "en_zona": en_zona,
            "zona_compra": zonas_dict["compra"],
            "zona_venta": zonas_dict["venta"],
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

    Además del precio guarda el cierre anterior y la variación del día que informó IOL
    (`cotizacion_diaria`), sin llamadas extra.

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
    cotizaciones: dict = {}
    filas, issues = market_data_precios.fetch_precios_watchlist_catalogo(
        a_cotizar, db, paneles_fn=paneles_fn, fci_fn=fci_fn,
        solo_simbolo_suelto=solo_simbolo_suelto, cotizaciones_out=cotizaciones, **extra,
    )
    cotizacion_diaria.guardar(db, cotizacion_diaria.construir_cotizaciones_dia(filas, cotizaciones))
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

    `objetivo` (opcional, por compatibilidad del endpoint de alta) se guarda como el **techo** de
    la zona de compra, abierta hacia abajo: es exactamente lo que significaba cuando era un escalar.
    La zona se puede ajustar después arrastrándola en el gráfico.
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
        notas=(notas or "").strip() or None,
        agregado_en=date.today(),
    )
    db.add(item)
    db.flush()

    if objetivo is not None:
        _guardar_zona_compra(db, ticker, objetivo, entrada["moneda"])

    # Una sola llamada a IOL: el endpoint por símbolo, sin bajar los paneles enteros.
    _, issues = refrescar_precios(db, [ticker], max_simbolos_sueltos=1, solo_simbolo_suelto=True)
    return item, None, issues


def _guardar_zona_compra(db: Session, ticker: str, techo: float | None, moneda: str) -> None:
    """Traduce el escalar `objetivo` de la API de watchlist a la zona de compra: techo = objetivo,
    piso abierto. `None` borra la zona.

    Pasa por `zonas_precio.aplicar_cambios` y no escribe la tabla a mano para no duplicar la
    validación ni el re-armado de la alerta. Esa función commitea, igual que los endpoints de
    niveles: es el final de la operación en los dos llamadores (alta y edición).
    """
    cambios = {zonas_precio.TIPO_COMPRA: None} if techo is None else {
        zonas_precio.TIPO_COMPRA: {
            "variante": zonas_precio.VARIANTE_LOCAL, "moneda": moneda,
            "piso": None, "techo": techo, "activa": True,
        }
    }
    zonas_precio.aplicar_cambios(db, ticker, cambios)


def actualizar(db: Session, ticker: str, cambios: dict) -> WatchlistItem | None:
    """Edita los campos que el usuario controla. El resto (nombre, tipo, moneda, mercado) sale del
    catálogo y no se toca a mano: si estuviera mal, lo que corresponde es regenerar el catálogo.

    `cambios` trae **sólo las claves que el request mandó** (`exclude_unset`), así un PUT parcial
    con `{"objetivo": 1300}` no borra las notas. Mandar `null` explícito sí limpia el campo.

    `objetivo` escribe el **techo de la zona de compra**: la columna `watchlist.objetivo` ya no se
    lee. Se mantiene en la API porque es el camino simple ("comprar por debajo de X") y no todo el
    mundo quiere dibujar un rango; el editor del gráfico usa los endpoints de zonas.
    """
    item = db.get(WatchlistItem, ticker)
    if item is None:
        return None
    if "notas" in cambios:
        item.notas = (cambios["notas"] or "").strip() or None
    db.flush()
    if "objetivo" in cambios:
        _guardar_zona_compra(db, ticker, cambios["objetivo"], item.moneda)
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

    # Las zonas se van con el ticker **sólo** si no está en cartera: si lo está, siguen siendo las
    # de la posición (el gráfico las sigue dibujando desde análisis técnico).
    if db.query(InstrumentoInversion).filter(
        InstrumentoInversion.ticker == ticker
    ).first() is None:
        db.query(ZonaPrecio).filter(ZonaPrecio.ticker == ticker).delete(synchronize_session=False)

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
