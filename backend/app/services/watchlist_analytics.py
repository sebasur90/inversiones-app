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

**Serie de referencia.** Para un CEDEAR (MSFT) el precio que importa para decidir es el de la
acción en el Nasdaq en dólares, no el del CEDEAR en pesos (ver
`ohlcv_analytics.variante_referencia`). Cada fila trae por eso `precio_referencia` y compañía: el
precio de esa serie, con su moneda, su fecha y su variación del día. `precio_actual` sigue siendo
el precio cotizado acá, porque es el contrato de otros consumidores (Resumen, Oportunidades de
compra, alertas) y cambiarlo movería cálculos que no son de esta pantalla. La proximidad a la zona
ya **no** supone que el precio y la zona están en la misma moneda: cada zona se compara contra el
precio de **su propia serie**, igual que en las alertas (`base_comparacion` dice cuál).

La detección de "cerca" (el umbral de proximidad) vive en el frontend, como la de posiciones: es
una preferencia del usuario guardada en localStorage y se aplica sobre `pct_a_objetivo` sin
necesidad de re-sincronizar.

Además del cálculo, este módulo tiene el alta/baja/edición: la watchlist la gestiona el usuario
desde la app y el ticker sale del catálogo de IOL (`catalogo_instrumentos`), no de la pestaña
`Watchlist` del Sheet, que ya no se lee.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import (
    BarraOHLCV,
    EstadoMarketDataTicker,
    InstrumentoInversion,
    MovimientoInversion,
    PrecioWatchlist,
    WatchlistItem,
    ZonaPrecio, DibujoGrafico,
)
from . import (
    catalogo_instrumentos, clasificacion_analytics, cotizacion_diaria, estado_market_data,
    ohlcv_analytics, zonas_precio,
)
from .clasificacion_instrumentos import es_cedear
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


def _cierres_barras(
    db: Session, tickers: list[str], variante: str = "local", moneda: str = "",
) -> dict[str, list[tuple[date, float, str]]]:
    """Cierres diarios de `BarraOHLCV` con la forma de `_precios_por_ticker`, por ticker base.

    `moneda` es la que se pone en cada tupla. Para la serie local queda vacía (las velas no la
    guardan, así que la comparación de moneda se hace con la del precio); para la del subyacente es
    `"USD"`, porque `_variacion_diaria` exige la misma moneda entre el precio y el registro previo y
    con `""` contra `"USD"` nunca daría un número.
    """
    if not tickers:
        return {}
    claves = {ohlcv_analytics.clave_serie(t, variante): t for t in tickers}
    filas = (
        db.query(BarraOHLCV.ticker, BarraOHLCV.fecha, BarraOHLCV.cierre)
        .filter(BarraOHLCV.ticker.in_(claves))
        .order_by(BarraOHLCV.ticker, BarraOHLCV.fecha)
        .all()
    )
    out: dict[str, list[tuple[date, float, str]]] = {}
    for clave, fecha, cierre in filas:
        out.setdefault(claves[clave], []).append((fecha, float(cierre), moneda))
    return out


def get_watchlist(db: Session) -> list[dict]:
    """La watchlist con precio actual, distancia al objetivo y si está en zona de compra.

    El precio sale de la serie de `precios_instrumento` (con carry-forward) cuando el ticker
    también existe en `Instrumentos` -- ahí hay historia real --, y de `precios_watchlist` cuando
    es un ticker que sólo se está siguiendo.

    El nivel sale del techo de la zona de compra, comparado contra el precio **de la serie de esa
    zona**: una zona `local` contra el precio cotizado acá, una `subyacente` contra el último
    precio del instrumento en EE.UU. en USD. Nunca se cruzan (una distancia entre 170 dólares y
    26.000 pesos no significa nada): `base_comparacion` dice contra cuál se midió y
    `moneda_objetivo` en qué moneda está el nivel. Es el mismo criterio de las alertas.

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
    clasif = clasificacion_analytics.clasificaciones(db)

    solo_seguidos = [i.ticker for i in items if i.ticker not in tickers_instrumento]
    cierres = _cierres_barras(db, solo_seguidos)
    cotizaciones_dia = cotizacion_diaria.cargar_por_clave(db, {i.ticker for i in items})
    zonas = zonas_precio.mapa_zonas(db)   # una sola consulta para toda la lista

    # Serie de referencia de cada ticker y, para los que se miran en dólares (o tienen una zona
    # dibujada sobre el subyacente), su último precio y sus cierres. Todo en bloque, nunca por ítem:
    # `get_watchlist_item` recalcula la lista entera en cada alta o edición.
    referencias = ohlcv_analytics.mapa_referencias(db)
    tickers_sub = {i.ticker for i in items if referencias.get(i.ticker) == "subyacente"}
    for item in items:
        zc = zonas.get(item.ticker, zonas_precio.VACIO).compra
        if zc is not None and zc.activa and zc.variante == zonas_precio.VARIANTE_SUBYACENTE:
            tickers_sub.add(item.ticker)
    precios_sub = ohlcv_analytics.ultimo_precio_subyacente(db, tickers_sub)
    cierres_sub = _cierres_barras(db, sorted(tickers_sub), "subyacente", "USD")

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

        # Serie de referencia: lo que hay que mirar para decidir. Si es el subyacente se usa su
        # precio en USD con la variación del día calculada sobre sus propias velas (no la de IOL,
        # que es la del CEDEAR en pesos); si por algún motivo no hay precio, se cae a la local en
        # vez de dejar la fila en blanco.
        variante_ref = referencias.get(item.ticker, "local")
        sub = precios_sub.get(item.ticker)
        if variante_ref == "subyacente" and sub is not None:
            fecha_ref, precio_ref, fuente_ref = sub
            moneda_ref = "USD"
            var_ref, var_ref_pct = _variacion_diaria(
                cierres_sub.get(item.ticker, []), fecha_ref, precio_ref, "USD", None,
            )
        else:
            variante_ref = "local"
            fecha_ref, precio_ref, fuente_ref = fecha_precio, precio_actual, fuente_precio
            moneda_ref = moneda_precio or item.moneda
            var_ref, var_ref_pct = variacion_dia, variacion_dia_pct

        # La zona de compra se mide contra el precio de su propia serie, sin convertir monedas.
        del_ticker = zonas.get(item.ticker, zonas_precio.VACIO)
        zonas_dict = zonas_precio.a_dict(item.ticker, del_ticker)
        zona_compra = del_ticker.compra
        base_comparacion = moneda_objetivo = None
        precio_comparado: float | None = None
        if zona_compra is not None and zona_compra.activa:
            if zona_compra.variante == zonas_precio.VARIANTE_SUBYACENTE:
                if sub is not None:
                    precio_comparado, moneda_objetivo = sub[1], "USD"
            else:
                precio_comparado, moneda_objetivo = precio_actual, moneda_precio or item.moneda
            if precio_comparado is not None:
                base_comparacion = zona_compra.variante
        precio_objetivo, pct_a_objetivo, en_zona = zonas_precio.estado_de_zona(
            zona_compra, precio_comparado,
        )

        resultado.append({
            "ticker": item.ticker,
            "nombre": item.nombre,
            "tipo_instrumento": item.tipo_instrumento,
            "mercado": item.mercado,
            "moneda": item.moneda,
            "pais": clasificacion_analytics.atributo(clasif, item.ticker, "pais"),
            "sector": clasificacion_analytics.atributo(clasif, item.ticker, "sector"),
            "precio_actual": precio_actual,
            "fecha_precio": fecha_precio,
            "moneda_precio": moneda_precio or item.moneda,
            "fuente_precio": fuente_precio,
            "variacion_dia": round(variacion_dia, 6) if variacion_dia is not None else None,
            "variacion_dia_pct": round(variacion_dia_pct, 4) if variacion_dia_pct is not None else None,
            "variante_referencia": variante_ref,
            "precio_referencia": precio_ref,
            "moneda_referencia": moneda_ref,
            "fecha_precio_referencia": fecha_ref,
            "fuente_precio_referencia": fuente_ref,
            "variacion_dia_referencia": round(var_ref, 6) if var_ref is not None else None,
            "variacion_dia_referencia_pct": round(var_ref_pct, 4) if var_ref_pct is not None else None,
            "precio_objetivo": precio_objetivo,
            "pct_a_objetivo": pct_a_objetivo,
            "en_zona": en_zona,
            "base_comparacion": base_comparacion,
            "moneda_objetivo": moneda_objetivo,
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
    """Los ítems de la watchlist en la forma que consume `market_data.precios`. Lo usa el sync.

    Un ítem que el catálogo lista como CEDEAR viaja con `tipo_instrumento="CEDEAR"` aunque el
    guardado diga otra cosa (watchlist vieja, del Sheet): si no, `resolver_subyacente` no le busca
    la serie en USD y queda en pesos.
    """
    cedears = catalogo_instrumentos.simbolos_cedear()
    salida = []
    for item in db.query(WatchlistItem).order_by(WatchlistItem.ticker).all():
        fila = _item_a_dict(item)
        if item.ticker.upper() in cedears and not es_cedear(fila["tipo_instrumento"] or ""):
            fila["tipo_instrumento"] = "CEDEAR"
        salida.append(fila)
    return salida


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

    # Una sola llamada a IOL: el endpoint por símbolo, sin bajar los paneles enteros.
    _, issues = refrescar_precios(db, [ticker], max_simbolos_sueltos=1, solo_simbolo_suelto=True)
    issues.extend(asegurar_serie_subyacente(db, ticker))

    # Después de la serie en USD: la zona se escribe en la serie de referencia del ticker, y un
    # CEDEAR sólo la tiene en dólares una vez que esa serie existe.
    if objetivo is not None:
        _guardar_zona_compra(db, ticker, objetivo, entrada["moneda"])
    return item, None, issues


def asegurar_serie_subyacente(db: Session, ticker: str) -> list[ValidationIssue]:
    """Para un CEDEAR de la watchlist: resuelve su subyacente y baja la serie `TICKER@SUB` en USD
    ya mismo, en vez de esperar al próximo sync.

    Sin esto un CEDEAR recién agregado se veía en pesos hasta el sync de la tarde (o varios, porque
    el sync resuelve y baja unos pocos por corrida). Son a lo sumo dos llamadas a yfinance y
    ninguna a IOL. Reusa las mismas funciones del sync (`resolver_subyacente`,
    `fetch_backfill_ohlcv_subyacente`), así que respeta su cooldown y su precedencia de barras.

    Best effort, como el precio del alta: si Yahoo no responde, el ítem queda como estaba y el
    sync lo completa. No commitea: lo hace el endpoint.
    """
    if not market_data.use_external_apis():
        return []
    activo = next((a for a in items_para_market_data(db) if a["ticker"] == ticker), None)
    if activo is None or not es_cedear(activo["tipo_instrumento"] or ""):
        return []

    estado = estado_market_data.cargar(db)
    issues = market_data_precios.resolver_subyacente([activo], estado, max_resoluciones=1)

    clave = ohlcv_analytics.clave_serie(ticker, "subyacente")
    desde, hasta = db.query(func.min(BarraOHLCV.fecha), func.max(BarraOHLCV.fecha)).filter(
        BarraOHLCV.ticker == clave,
    ).one()
    filas, issues_serie = market_data_precios.fetch_backfill_ohlcv_subyacente(
        [activo],
        {clave: desde} if desde is not None else {},
        {clave: hasta} if hasta is not None else {},
        estado, max_llamadas=1,
    )
    issues.extend(issues_serie)

    estado_market_data.persistir(db, {ticker: estado[ticker]} if ticker in estado else {})
    ohlcv_analytics.upsert_barras(db, filas)
    return issues


def descargar_series(db: Session, ticker: str, con_subyacente: bool = True) -> list[ValidationIssue]:
    """Baja ya mismo las velas de un ítem de la watchlist, en vez de esperar al próximo sync.

    El alta sólo trae el precio (y, para un CEDEAR, la serie del subyacente en USD): la serie local
    la llena el sync de la tarde con los mismos tres backfills que corre acá —analisistecnico/IOL,
    Yahoo `.BA` y el subyacente—, así que un ticker recién agregado quedaba sin gráfico hasta
    entonces. Las funciones son las del sync, con su misma calibración de escala y sus mismos
    cooldowns: acá no hay lógica de series nueva, sólo se las corre para un único ticker.

    Los que están en cartera no entran: esa serie la mantiene el sync con el historial completo.
    `con_subyacente=False` cuando el ítem se acaba de dar de alta: `agregar` ya bajó esa serie.

    Best effort, como el alta: una fuente que no responde deja un issue y el sync lo completa.
    No commitea: lo hace el llamador.
    """
    if not market_data.use_external_apis():
        return []
    activo = next((a for a in items_para_market_data(db) if a["ticker"] == ticker), None)
    if activo is None or db.query(InstrumentoInversion.id).filter(
        InstrumentoInversion.ticker == ticker,
    ).first() is not None:
        return []

    issues: list[ValidationIssue] = []
    if db.get(PrecioWatchlist, ticker) is None:
        # Sin precio observado no hay referencia de escala y los backfills descartan las velas.
        _, issues_precio = refrescar_precios(db, [ticker], max_simbolos_sueltos=1, solo_simbolo_suelto=True)
        issues.extend(issues_precio)
    precio = db.get(PrecioWatchlist, ticker)
    referencia = [] if precio is None else [
        {"ticker": ticker, "fecha": precio.fecha, "precio": float(precio.precio), "moneda": precio.moneda},
    ]

    existentes = {
        tk: f_min for tk, f_min in db.query(BarraOHLCV.ticker, func.min(BarraOHLCV.fecha)).filter(
            BarraOHLCV.ticker == ticker,
        ).group_by(BarraOHLCV.ticker)
    }
    estado = estado_market_data.cargar(db)
    barras, issues_wl = market_data_precios.fetch_backfill_ohlcv_watchlist(
        [activo], referencia, existentes, db, estado_por_ticker=estado,
    )
    filas_yahoo, issues_yahoo = market_data_precios.fetch_backfill_ohlcv_local_yahoo(
        [activo], referencia, existentes, estado_por_ticker=estado,
    )
    barras.extend(filas_yahoo)
    issues.extend(issues_wl + issues_yahoo)

    estado_market_data.persistir(db, {ticker: estado[ticker]} if ticker in estado else {})
    ohlcv_analytics.upsert_barras(db, barras)
    db.flush()
    if con_subyacente:
        # Último, porque carga su propio estado y persiste el suyo: el CEDEAR queda además con su serie en USD.
        issues.extend(asegurar_serie_subyacente(db, ticker))
    return issues


def _guardar_zona_compra(db: Session, ticker: str, techo: float | None, moneda: str) -> None:
    """Traduce el escalar `objetivo` de la API de watchlist a la zona de compra: techo = objetivo,
    piso abierto, en la serie de referencia del ticker. `None` borra la zona.

    Pasa por `zonas_precio.aplicar_cambios` y no escribe la tabla a mano para no duplicar la
    validación ni el re-armado de la alerta. Esa función commitea, igual que los endpoints de
    niveles: es el final de la operación en los dos llamadores (alta y edición).
    """
    # El atajo escribe en la serie de referencia del ticker: para un CEDEAR con serie del
    # subyacente, "comprar por debajo de 470" son 470 dólares del Nasdaq, no pesos del CEDEAR.
    variante = ohlcv_analytics.variante_para(db, ticker, None)
    if variante == zonas_precio.VARIANTE_SUBYACENTE:
        moneda = "USD"
    cambios = {zonas_precio.TIPO_COMPRA: None} if techo is None else {
        zonas_precio.TIPO_COMPRA: {
            "variante": variante, "moneda": moneda,
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
        db.query(DibujoGrafico).filter(DibujoGrafico.ticker == ticker).delete(synchronize_session=False)

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
