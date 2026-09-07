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
    BarraOHLCV, EstadoMarketDataTicker, InstrumentoInversion, PrecioInstrumento, WatchlistItem,
)
from .cache import cache_por_sync
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


def clave_serie(ticker: str, variante: str = "local") -> str:
    """Clave de fila en `serie_ohlcv` para `(ticker, variante)`. `local` -> el ticker tal cual;
    `subyacente` -> `"MSFT@SUB"`."""
    return f"{ticker}{SUFIJO_SUBYACENTE}" if variante == "subyacente" else ticker


def ticker_base(clave: str) -> str:
    """Inversa de `clave_serie`: quita el sufijo de variante si está presente."""
    return clave[: -len(SUFIJO_SUBYACENTE)] if clave.endswith(SUFIJO_SUBYACENTE) else clave


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


def variantes_de_ticker(db: Session) -> dict[str, list[dict]]:
    """Por ticker base, las variantes de serie que tienen filas reales en `serie_ohlcv`.

    Cada entrada: `{variante, moneda, mercado}`. `moneda` es la dominante de esa clave de serie;
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

    out: dict[str, list[dict]] = {}
    for clave, moneda in moneda_dominante.items():
        base = ticker_base(clave)
        variante = variante_de_clave(clave)
        if variante == "local":
            mercado = mercado_inst.get(base) or mercado_wl.get(base) or ""
        else:
            mercado = mercado_sub.get(base) or ""
        out.setdefault(base, []).append({"variante": variante, "moneda": moneda, "mercado": mercado})
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

    resultado = []
    for ticker in sorted(set(instrumentos) | set(watchlist)):
        inst = instrumentos.get(ticker)
        wl = watchlist.get(ticker)
        origen = "ambos" if inst and wl else ("cartera" if inst else "watchlist")
        moneda = (inst.moneda if inst else None) or (wl.moneda if wl else "ARS")
        mercado = (inst.mercado if inst else None) or (wl.mercado if wl else "")

        series = list(variantes.get(ticker, []))
        if not any(s["variante"] == "local" for s in series):
            series.insert(0, {"variante": "local", "moneda": moneda, "mercado": mercado})

        resultado.append({
            "ticker": ticker,
            "nombre": (inst.nombre if inst else None) or (wl.nombre if wl else ticker),
            "moneda": moneda,
            "tipo_instrumento": (inst.tipo_instrumento if inst else None) or (wl.tipo_instrumento if wl else ""),
            "origen": origen,
            "series": series,
        })
    return resultado


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
    variante: str = "local", mercado: str = "",
) -> dict:
    return {
        "ticker": ticker, "nombre": nombre, "moneda": moneda, "origen": origen,
        "variante": variante, "mercado": mercado,
        "fuente_serie": "sin_datos", "tiene_velas": False, "tiene_volumen": False,
        "indice_desde": 0, "barras": [], "advertencias": [motivo],
    }


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
        return _serie_vacia(ticker, nombre, moneda_serie, origen, motivo, variante, mercado_serie)

    idx_desde = next((i for i, f in enumerate(fechas_ordenadas) if f >= desde), len(fechas_ordenadas))
    idx_inicio = max(0, idx_desde - barras_previas)
    fechas_ventana = fechas_ordenadas[idx_inicio:]
    if len(fechas_ventana) < MIN_PUNTOS_SERIE:
        return _serie_vacia(ticker, nombre, moneda_serie, origen, "sin_serie", variante, mercado_serie)

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

    # La moneda efectiva sale de las barras de la ventana (para el subyacente, USD nativo; para
    # la local, la del instrumento salvo que la serie diga otra cosa).
    moneda_final = monedas[-1] if monedas else moneda_serie

    return {
        "ticker": ticker, "nombre": nombre, "moneda": moneda_final if es_sub else moneda_instrumento,
        "variante": variante, "mercado": mercado_serie, "origen": origen,
        "fuente_serie": fuente_serie, "tiene_velas": tiene_velas, "tiene_volumen": tiene_volumen,
        "indice_desde": indice_desde, "barras": barras, "advertencias": advertencias,
    }
