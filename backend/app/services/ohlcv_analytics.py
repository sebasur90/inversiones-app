"""Datos de análisis técnico (serie de barras OHLCV) sobre lo que YA existe en la DB.

DB-aware, a diferencia de `indicadores_engine`/`estrategia_engine` (puros): lee `serie_ohlcv` y
`precios_instrumento`, resuelve la fuente por fecha y arma la lista de `Barra` que consumen esos
motores. Cacheado con `cache_por_sync`: entre dos syncs la serie de un ticker no cambia.

Resolución de la serie, por fecha, en orden de prioridad:
  1. fila de `serie_ohlcv` (vela real si tiene o/h/l, o close-only si el backfill sólo pudo
     resolver el cierre);
  2. si no hay fila ahí, el precio de `precios_instrumento` de esa fecha (cualquier fuente,
     `'sheet'` incluida — es historia real) — close-only, marca la barra como `fuente_serie`
     `"mixta"`;
  3. si ninguna de las dos tiene esa fecha, no hay barra ese día: no se inventa con
     carry-forward ni relleno de ruedas faltantes.

Un ticker de watchlist recién agregado sólo tiene un punto en `precios_watchlist` (el precio del
día que se agregó, no una serie histórica) — por diseño `get_serie_barras` no lo sirve.

**Este módulo no convierte de moneda.** La variante `local` sirve el precio cotizado tal cual
(convertir por MEP metería la volatilidad del dólar dentro del RSI/las bandas de Bollinger). La
variante `subyacente` (`variante="subyacente"`) tampoco convierte: lee una serie distinta —la del
subyacente en EE.UU., p.ej. la acción del NASDAQ detrás de un CEDEAR— que **ya cotiza
nativamente en USD**, guardada bajo la clave derivada `TICKER@SUB` en `serie_ohlcv`. Son dos
instrumentos, no el mismo precio en dos monedas.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import (
    BarraOHLCV, EstadoMarketDataTicker, InstrumentoInversion, PrecioInstrumento, PrecioSubyacente,
    WatchlistItem,
)
from . import catalogo_instrumentos, splits_engine
from .cache import cache_por_sync
from .clasificacion_instrumentos import es_cedear
from .indicadores_engine import Barra

MAX_BARRAS_DEFAULT = 750
MIN_PUNTOS_SERIE = 2
# Proxy en días calendario de "hueco > 10 ruedas": no hay calendario de feriados acá, así que se
# aproxima con margen (fines de semana + feriados largos) en vez de contar ruedas hábiles.
_GAP_DIAS_ADVERTENCIA = 15

# `yahoo` sólo escribe filas bajo la clave `@SUB`, que ninguna otra fuente toca; su prioridad
# relativa a `api`/`iol` sólo importa como "> -1" para que `debe_reemplazar_barra` la deje ganar
# el upsert (una fuente desconocida ordena -1 y nunca pisaría).
_PRIORIDAD_FUENTE = {"api": 0, "iol": 1, "yahoo": 2}

# La serie del subyacente en USD se guarda bajo una clave derivada del ticker (no una columna
# discriminadora): el UNIQUE de `serie_ohlcv` es `(ticker, fecha)` y SQLite no permite alterarlo
# sin reconstruir la tabla. Además `MSFT@SUB` no existe en `precios_instrumento`, así que la
# contaminación ARS↔USD en el merge de `get_serie_barras` es imposible por construcción.
SUFIJO_SUBYACENTE = "@SUB"

# Series que existen de verdad. `"referencia"` NO es una serie: es el pedido de "la que corresponde
# a este ticker" y se resuelve con `resolver_variante` antes de leer nada. Por eso `clave_serie`
# rechaza todo lo que no sea una de estas dos: un `"referencia"` sin resolver que degradara en
# silencio a la serie local daría un resultado plausible y equivocado.
VARIANTES_SERIE = ("local", "subyacente")
VARIANTE_REFERENCIA = "referencia"

# Barras mínimas de la serie `@SUB` para que un CEDEAR la tome como referencia. El backfill del
# subyacente baja por tandas: con 3 barras la pantalla por defecto mostraría un gráfico de 3 puntos
# tapando años de serie local. ~3 meses de ruedas alcanza para indicadores de ventana corta.
MIN_BARRAS_REFERENCIA = 60


def clave_serie(ticker: str, variante: str = "local") -> str:
    """Clave de fila en `serie_ohlcv` para `(ticker, variante)`. `local` -> el ticker tal cual;
    `subyacente` -> `"MSFT@SUB"`. Cualquier otra variante es un error de quien llama."""
    if variante not in VARIANTES_SERIE:
        raise ValueError(f"variante de serie desconocida: {variante!r}")
    return f"{ticker}{SUFIJO_SUBYACENTE}" if variante == "subyacente" else ticker


def ticker_base(clave: str) -> str:
    """Inversa de `clave_serie`: quita el sufijo de variante si está presente."""
    return clave[: -len(SUFIJO_SUBYACENTE)] if clave.endswith(SUFIJO_SUBYACENTE) else clave


# Los índices de referencia para la fuerza relativa (SPY, QQQ, ^MERV) se guardan en la misma tabla
# bajo `SIMBOLO@BENCH`. No son del universo técnico (no se pueden graficar ni tienen movimientos):
# `variantes_de_ticker` los ignora y el sync no los purga. Ver `benchmarks`.
SUFIJO_BENCHMARK = "@BENCH"


def es_clave_benchmark(clave: str) -> bool:
    return clave.endswith(SUFIJO_BENCHMARK)


def variante_de_clave(clave: str) -> str:
    return "subyacente" if clave.endswith(SUFIJO_SUBYACENTE) else "local"


def debe_reemplazar_barra(existente: dict | None, nueva: dict) -> bool:
    """Precedencia de `serie_ohlcv` al hacer upsert: `iol` pisa a `api`, nunca al revés; a igual
    fuente, una barra con velas (`o/h/l`) pisa a una close-only, pero nunca al revés. Esto es lo
    que permite escribir la barra close-only del precio del día y que el backfill del día
    siguiente la promueva a vela real sin retroceder si el orden de escritura se invierte.

    `existente`/`nueva`: `{"fuente": "api"|"iol", "tiene_velas": bool}`. `existente=None` (no hay
    fila previa) siempre reemplaza."""
    if existente is None:
        return True
    p_existente = _PRIORIDAD_FUENTE.get(existente["fuente"], -1)
    p_nueva = _PRIORIDAD_FUENTE.get(nueva["fuente"], -1)
    if p_nueva != p_existente:
        return p_nueva > p_existente
    return nueva["tiene_velas"] and not existente["tiene_velas"]


def upsert_barras(db: Session, filas: list[dict]) -> None:
    """Upsert de `serie_ohlcv` con la precedencia de `debe_reemplazar_barra`. Hace `flush`, no
    `commit`.

    Lo usan el sync (todas las barras de la corrida juntas) y el alta de un CEDEAR en la watchlist
    (la serie del subyacente de un solo ticker), para que la precedencia viva en un solo lugar.
    """
    if not filas:
        return
    tickers = {b["ticker"] for b in filas}
    existentes = {
        (r.ticker, r.fecha): r
        for r in db.query(BarraOHLCV).filter(BarraOHLCV.ticker.in_(tickers)).all()
    }
    for fila in filas:
        clave = (fila["ticker"], fila["fecha"])
        existente = existentes.get(clave)
        tiene_velas_nueva = (
            fila["apertura"] is not None and fila["maximo"] is not None and fila["minimo"] is not None
        )
        existente_dict = (
            {"fuente": existente.fuente, "tiene_velas": existente.apertura is not None
             and existente.maximo is not None and existente.minimo is not None}
            if existente is not None else None
        )
        if not debe_reemplazar_barra(existente_dict, {"fuente": fila["fuente"], "tiene_velas": tiene_velas_nueva}):
            continue
        if existente is not None:
            existente.apertura = fila["apertura"]
            existente.maximo = fila["maximo"]
            existente.minimo = fila["minimo"]
            existente.cierre = fila["cierre"]
            existente.volumen = fila["volumen"]
            existente.moneda = fila["moneda"]
            existente.fuente = fila["fuente"]
        else:
            nueva = BarraOHLCV(
                ticker=fila["ticker"], fecha=fila["fecha"],
                apertura=fila["apertura"], maximo=fila["maximo"], minimo=fila["minimo"],
                cierre=fila["cierre"], volumen=fila["volumen"],
                moneda=fila["moneda"], fuente=fila["fuente"],
            )
            existentes[clave] = nueva
            db.add(nueva)
    db.flush()

def variantes_de_ticker(db: Session) -> dict[str, list[dict]]:
    """Por ticker base, las variantes de serie que tienen filas reales en `serie_ohlcv`.

    Cada entrada: `{variante, moneda, mercado, barras}`. `moneda` es la dominante de esa clave de
    serie y `barras` cuántas filas tiene en total (es lo que decide si alcanza para ser la
    referencia, ver `variante_referencia`);
    `mercado` sale de Instrumentos/Watchlist para `local` y de `EstadoMarketDataTicker` para
    `subyacente`. `local` va siempre primero. Un ticker sin ninguna fila en `serie_ohlcv` no
    aparece acá (lo completa `listar_tickers_tecnicos`).
    """
    conteo: dict[tuple[str, str], int] = {}
    for clave, moneda, n in (
        db.query(BarraOHLCV.ticker, BarraOHLCV.moneda, func.count(BarraOHLCV.id))
        .group_by(BarraOHLCV.ticker, BarraOHLCV.moneda)
    ):
        conteo[(clave, moneda)] = n

    moneda_dominante: dict[str, str] = {}
    for (clave, moneda), n in conteo.items():
        actual = moneda_dominante.get(clave)
        if actual is None or n > conteo.get((clave, actual), 0):
            moneda_dominante[clave] = moneda

    mercado_inst = dict(db.query(InstrumentoInversion.ticker, InstrumentoInversion.mercado))
    mercado_wl = dict(db.query(WatchlistItem.ticker, WatchlistItem.mercado))
    mercado_sub = dict(
        db.query(EstadoMarketDataTicker.ticker, EstadoMarketDataTicker.mercado_subyacente)
    )

    barras_por_clave: dict[str, int] = {}
    for (clave, _moneda), n in conteo.items():
        barras_por_clave[clave] = barras_por_clave.get(clave, 0) + n

    out: dict[str, list[dict]] = {}
    for clave, moneda in moneda_dominante.items():
        if es_clave_benchmark(clave):
            continue
        base = ticker_base(clave)
        variante = variante_de_clave(clave)
        if variante == "local":
            mercado = mercado_inst.get(base) or mercado_wl.get(base) or ""
        else:
            mercado = mercado_sub.get(base) or ""
        out.setdefault(base, []).append({
            "variante": variante, "moneda": moneda, "mercado": mercado,
            "barras": barras_por_clave.get(clave, 0),
        })
    for lst in out.values():
        lst.sort(key=lambda s: 0 if s["variante"] == "local" else 1)
    return out


def listar_tickers_tecnicos(db: Session) -> list[dict]:
    """Universo de tickers analizables: instrumentos de cartera ∪ watchlist.

    Cada ticker trae `series`: las variantes con datos reales (`variantes_de_ticker`), garantizando
    siempre una entrada `local` (sintetizada con la moneda/mercado del instrumento si todavía no
    hay velas cargadas). La UI muestra el toggle Local/Subyacente sólo si `len(series) > 1`.
    """
    instrumentos = {row.ticker: row for row in db.query(InstrumentoInversion).all()}
    watchlist = {row.ticker: row for row in db.query(WatchlistItem).all()}
    variantes = variantes_de_ticker(db)
    cedears_catalogo = catalogo_instrumentos.simbolos_cedear()

    resultado = []
    for ticker in sorted(set(instrumentos) | set(watchlist)):
        inst = instrumentos.get(ticker)
        wl = watchlist.get(ticker)
        origen = "ambos" if inst and wl else ("cartera" if inst else "watchlist")
        moneda = (inst.moneda if inst else None) or (wl.moneda if wl else "ARS")
        mercado = (inst.mercado if inst else None) or (wl.mercado if wl else "")

        series = list(variantes.get(ticker, []))
        if not any(s["variante"] == "local" for s in series):
            series.insert(0, {"variante": "local", "moneda": moneda, "mercado": mercado, "barras": 0})

        tipo = (inst.tipo_instrumento if inst else None) or (wl.tipo_instrumento if wl else "")
        # CEDEAR si lo dice cualquiera de las fuentes: el tipo de la cartera manda para mostrar,
        # pero un Sheet que dice "Acción" (o una watchlist vieja con otro tipo) no puede dejar en
        # pesos algo que IOL lista como CEDEAR.
        es_cedear_efectivo = (
            es_cedear(tipo)
            or (wl is not None and es_cedear(wl.tipo_instrumento or ""))
            or ticker.upper() in cedears_catalogo
        )
        resultado.append({
            "ticker": ticker,
            "nombre": (inst.nombre if inst else None) or (wl.nombre if wl else ticker),
            "moneda": moneda,
            "tipo_instrumento": tipo,
            "origen": origen,
            "series": series,
            "variante_referencia": variante_referencia("CEDEAR" if es_cedear_efectivo else tipo, series),
        })
    return resultado


def variante_referencia(tipo_instrumento: str, series: list[dict]) -> str:
    """La serie con la que hay que **decidir** sobre este ticker: `"subyacente"` o `"local"`.

    Para comprar MSFT por CEDEAR, el momento de compra se juzga por la acción en el Nasdaq en
    dólares, no por el CEDEAR: éste mezcla el movimiento de la empresa con el del dólar y el ratio,
    así que su RSI, sus bandas y sus extremos describen otra cosa. Hace falta, a la vez:

    - **ser un CEDEAR.** Una acción argentina con ADR (GGAL, YPF) tiene el ADR resuelto como
      subyacente, pero su mercado de referencia es BYMA en pesos: no se la lleva a dólares. Un
      bono o una ON tampoco tienen subyacente.
    - **tener la serie `@SUB` en USD y con barras suficientes** (`MIN_BARRAS_REFERENCIA`). Un CEDEAR
      recién agregado, o uno que yfinance no resolvió, sigue en `local`: apuntar a una serie vacía
      dejaría el gráfico en blanco.

    Pura: `series` es la lista que arma `variantes_de_ticker`. No convierte monedas; elige cuál de
    las dos series se mira.
    """
    if not es_cedear(tipo_instrumento):
        return "local"
    for serie in series:
        if (
            serie["variante"] == "subyacente"
            and (serie.get("moneda") or "").upper() == "USD"
            and serie.get("barras", 0) >= MIN_BARRAS_REFERENCIA
        ):
            return "subyacente"
    return "local"


@cache_por_sync
def mapa_referencias(db: Session) -> dict[str, str]:
    """`ticker -> variante de referencia` de todo el universo cartera ∪ watchlist, en una pasada."""
    return {t["ticker"]: t["variante_referencia"] for t in listar_tickers_tecnicos(db)}


def resolver_variante(pedida: str | None, referencia: str) -> str:
    """Traduce lo que pidió quien llama a una serie concreta (`local` | `subyacente`).

    `None` y `"referencia"` significan "la de referencia de este ticker". Es **el único lugar**
    donde se interpreta ese valor especial; `get_serie_barras` sólo acepta series reales para que
    la misma serie no ocupe dos entradas de caché (`None` y su equivalente resuelto).
    """
    if pedida is None or pedida == VARIANTE_REFERENCIA:
        return referencia
    if pedida in VARIANTES_SERIE:
        return pedida
    raise ValueError(f"variante desconocida: {pedida!r}")


def variante_para(db: Session, ticker: str, pedida: str | None) -> str:
    """`resolver_variante` buscando la referencia del ticker. Un ticker fuera del universo (sin
    cartera ni watchlist) no tiene serie del subyacente que preferir: cae en `local`."""
    if pedida in VARIANTES_SERIE:
        return pedida   # no hace falta saber la referencia para obedecer un pedido explícito
    return resolver_variante(pedida, mapa_referencias(db).get(ticker, "local"))


def variante_efectiva(db: Session, ticker: str, pedida: str | None) -> str:
    """La serie concreta (`local` | `subyacente`) sobre la que responde un endpoint de análisis
    técnico. Sin variante pedida rige la referencia del ticker, y una referencia que todavía no tiene
    barras degrada a la local (un pedido explícito se respeta tal cual)."""
    variante = variante_para(db, ticker, pedida)
    if variante == "subyacente" and pedida is None:
        if not get_serie_barras(ticker, date.min, date.today(), db, max_barras=1, variante=variante)["barras"]:
            return "local"
    return variante


def ultimo_precio_subyacente(db: Session, tickers: set[str]) -> dict[str, tuple[date, float, str]]:
    """Último precio en USD del subyacente de cada ticker: `ticker -> (fecha, precio, origen)`.

    Une las dos fuentes que lo tienen. `precios_subyacente` lo refresca el job liviano varias veces
    por rueda (`origen="intradia"`); la serie `TICKER@SUB` la completa el sync de la tarde
    (`origen="cierre"`). **Gana la más fresca por fecha**, y no una fuente fija: si el job dejó de
    correr hace días su precio es más viejo que el último cierre de la serie, y al revés durante la
    rueda. A igual fecha gana el intradía.

    Sólo USD, en las dos fuentes: comparar o mostrar como dólares un precio en otra moneda es peor
    que no tener precio. Es la fuente única de la Watchlist y de las alertas, para que la pantalla y
    el aviso de Telegram no puedan discrepar.
    """
    if not tickers:
        return {}

    mejor: dict[str, tuple[date, float, str]] = {}

    def _considerar(ticker: str, fecha: date, precio: float, origen: str) -> None:
        actual = mejor.get(ticker)
        if actual is None or fecha >= actual[0]:
            mejor[ticker] = (fecha, precio, origen)

    claves = {clave_serie(t, "subyacente"): t for t in tickers}
    for clave, fecha, cierre in (
        db.query(BarraOHLCV.ticker, BarraOHLCV.fecha, BarraOHLCV.cierre)
        .filter(BarraOHLCV.ticker.in_(claves), func.upper(BarraOHLCV.moneda) == "USD")
        .order_by(BarraOHLCV.fecha)
    ):
        _considerar(claves[clave], fecha, float(cierre), "cierre")

    for fila in db.query(PrecioSubyacente).filter(PrecioSubyacente.ticker.in_(tickers)):
        if (fila.moneda or "").upper() == "USD":
            _considerar(fila.ticker, fila.fecha, float(fila.precio), "intradia")

    return mejor


def _fila_a_barra(fecha, cierre, apertura=None, maximo=None, minimo=None, volumen=None) -> Barra:
    return Barra(
        fecha=fecha, cierre=float(cierre),
        apertura=float(apertura) if apertura is not None else None,
        maximo=float(maximo) if maximo is not None else None,
        minimo=float(minimo) if minimo is not None else None,
        volumen=float(volumen) if volumen is not None else None,
    )


def _serie_vacia(
    ticker: str, nombre: str, moneda: str, origen: str | None, motivo: str,
    variante: str = "local", mercado: str = "", motivos_extra: list[str] | None = None,
) -> dict:
    return {
        "ticker": ticker, "nombre": nombre, "moneda": moneda, "origen": origen,
        "variante": variante, "mercado": mercado,
        "fuente_serie": "sin_datos", "tiene_velas": False, "tiene_volumen": False,
        "indice_desde": 0, "barras": [], "advertencias": [motivo, *(motivos_extra or [])],
    }


def _motivos_sin_serie(db: Session, ticker: str, variante: str) -> list[str]:
    """Por qué la serie de este ticker está vacía, según lo que dejó anotado el pipeline de market
    data (`EstadoMarketDataTicker`).

    Sin esto la pantalla dice "todavía no hay datos históricos" y el usuario no puede distinguir
    "el cupo mensual de IOL se agotó" de "ninguna fuente tiene este símbolo" o de "la serie vino en
    otra unidad que el precio de la pantalla y se descartó" — tres situaciones con tres acciones
    distintas.
    """
    estado = (
        db.query(EstadoMarketDataTicker)
        .filter(EstadoMarketDataTicker.ticker == ticker).first()
    )
    if estado is None:
        return []

    motivos: list[str] = []
    if variante == "subyacente":
        if estado.resolucion_estado in ("sin_subyacente", "ticker_no_apto"):
            motivos.append(f"subyacente_{estado.resolucion_estado}")
        return motivos

    if estado.ohlcv_estado == "sin_serie_iol":
        motivos.append("sin_fuente_historica")
    if estado.yahoo_local_estado == "escala_desconocida":
        motivos.append("escala_desconocida")
    return motivos


@cache_por_sync
def get_serie_barras(
    ticker: str, desde: date, hasta: date, db: Session,
    barras_previas: int = 0, max_barras: int = MAX_BARRAS_DEFAULT,
    variante: str = "local",
) -> dict:
    """`variante="subyacente"` lee la serie `TICKER@SUB` (subyacente en USD) y **no** mergea
    `precios_instrumento` (son cierres ARS del CEDEAR; mezclarlos daría un salto de ~x50 entre
    barras contiguas). La moneda del dict sale de la serie en ese caso, no del instrumento."""
    es_sub = variante == "subyacente"
    clave = clave_serie(ticker, variante)

    inst = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    wl = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    origen = "ambos" if inst and wl else ("cartera" if inst else ("watchlist" if wl else None))
    nombre = (inst.nombre if inst else None) or (wl.nombre if wl else ticker)
    moneda_instrumento = (inst.moneda if inst else None) or (wl.moneda if wl else "ARS")
    # Para el subyacente la moneda la fija la serie (USD nativo), no el instrumento (declarado en
    # ARS para un CEDEAR). Se ajusta más abajo con la moneda real de las barras de la ventana.
    moneda_serie = "USD" if es_sub else moneda_instrumento
    mercado_serie = (inst.mercado if inst else None) or (wl.mercado if wl else "") or ""
    if es_sub:
        est_sub = (
            db.query(EstadoMarketDataTicker)
            .filter(EstadoMarketDataTicker.ticker == ticker).first()
        )
        mercado_serie = (est_sub.mercado_subyacente if est_sub and est_sub.mercado_subyacente else "")

    filas_precio = [] if es_sub else (
        db.query(PrecioInstrumento)
        .filter(PrecioInstrumento.ticker == ticker, PrecioInstrumento.fecha <= hasta)
        .order_by(PrecioInstrumento.fecha).all()
    )
    filas_ohlcv = (
        db.query(BarraOHLCV)
        .filter(BarraOHLCV.ticker == clave, BarraOHLCV.fecha <= hasta)
        .order_by(BarraOHLCV.fecha).all()
    )

    barras_por_fecha: dict[date, Barra] = {}
    origen_por_fecha: dict[date, str] = {}
    moneda_por_fecha: dict[date, str] = {}

    for fp in filas_precio:
        barras_por_fecha[fp.fecha] = _fila_a_barra(fp.fecha, fp.precio)
        origen_por_fecha[fp.fecha] = "mixta"
        moneda_por_fecha[fp.fecha] = fp.moneda

    for fo in filas_ohlcv:  # serie_ohlcv siempre pisa a precios_instrumento en la misma fecha
        es_vela = fo.apertura is not None and fo.maximo is not None and fo.minimo is not None
        barras_por_fecha[fo.fecha] = _fila_a_barra(fo.fecha, fo.cierre, fo.apertura, fo.maximo, fo.minimo, fo.volumen)
        origen_por_fecha[fo.fecha] = "velas" if es_vela else "mixta"
        moneda_por_fecha[fo.fecha] = fo.moneda

    fechas_ordenadas = sorted(barras_por_fecha.keys())
    if len(fechas_ordenadas) < MIN_PUNTOS_SERIE:
        motivo = "un_solo_punto" if fechas_ordenadas else "sin_serie"
        return _serie_vacia(
            ticker, nombre, moneda_serie, origen, motivo, variante, mercado_serie,
            _motivos_sin_serie(db, ticker, variante),
        )

    idx_desde = next((i for i, f in enumerate(fechas_ordenadas) if f >= desde), len(fechas_ordenadas))
    idx_inicio = max(0, idx_desde - barras_previas)
    fechas_ventana = fechas_ordenadas[idx_inicio:]
    if len(fechas_ventana) < MIN_PUNTOS_SERIE:
        return _serie_vacia(
            ticker, nombre, moneda_serie, origen, "sin_serie", variante, mercado_serie,
            _motivos_sin_serie(db, ticker, variante),
        )

    barras = [barras_por_fecha[f] for f in fechas_ventana]
    origenes = [origen_por_fecha[f] for f in fechas_ventana]
    monedas = [moneda_por_fecha[f] for f in fechas_ventana]
    indice_desde = idx_desde - idx_inicio

    if max_barras is not None and len(barras) > max_barras:
        recorte = len(barras) - max_barras
        barras = barras[recorte:]
        origenes = origenes[recorte:]
        monedas = monedas[recorte:]
        fechas_ventana = fechas_ventana[recorte:]
        indice_desde = max(0, indice_desde - recorte)

    advertencias: list[str] = []
    n_velas = sum(1 for o in origenes if o == "velas")
    tiene_velas = (n_velas / len(origenes)) >= 0.9
    tiene_volumen = any(b.volumen is not None for b in barras)
    fuente_serie = "velas" if n_velas == len(origenes) else "mixta"

    if any((fechas_ventana[i] - fechas_ventana[i - 1]).days > _GAP_DIAS_ADVERTENCIA for i in range(1, len(fechas_ventana))):
        advertencias.append("serie_con_huecos")
    if len(set(monedas)) > 1:
        advertencias.append("moneda_mixta")
    # Las series de IOL vienen sin ajustar, así que un split queda como un escalón que los
    # indicadores leen como un movimiento real. No se corrige la serie: se avisa. Ver
    # `splits_engine`. El chequeo es O(n) sobre las barras que ya están en memoria.
    if splits_engine.detectar_saltos(barras):
        advertencias.append("posible_split")

    # La moneda efectiva sale de las barras de la ventana (para el subyacente, USD nativo; para
    # la local, la del instrumento salvo que la serie diga otra cosa).
    moneda_final = monedas[-1] if monedas else moneda_serie

    return {
        "ticker": ticker, "nombre": nombre, "moneda": moneda_final if es_sub else moneda_instrumento,
        "variante": variante, "mercado": mercado_serie, "origen": origen,
        "fuente_serie": fuente_serie, "tiene_velas": tiene_velas, "tiene_volumen": tiene_volumen,
        "indice_desde": indice_desde, "barras": barras, "advertencias": advertencias,
    }
