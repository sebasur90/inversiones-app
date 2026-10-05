"""Refresco liviano de cotizaciones: sólo el precio del día, sin tocar el Sheet.

Para qué existe: las alertas de precio sirven en la medida en que los precios sean frescos, y el
sync completo es demasiado caro para correrlo cada dos horas. Un `sync_from_sheet` lee el Google
Sheet entero, valida ocho pestañas, hace ~20 bloques de delete/insert y escribe un `SyncRun`. Todo
eso para enterarse de que un bono cotiza dos pesos más.

Qué hace este job, entonces:

1. lee de la **DB** qué instrumentos y qué precios manuales hay (no del Sheet);
2. pide el precio del día a IOL (paneles) con data912 de respaldo, por la misma vía que el sync
   (`market_data.precios.fetch_precios_api`): la precedencia `iol > sheet > api`, la calibración de
   escala y el conteo del cupo mensual son exactamente los del sync, no una copia;
3. hace upsert de esas filas en `precios_instrumento` y su espejo close-only en `serie_ohlcv`;
4. re-cotiza la watchlist (`watchlist_analytics.refrescar_precios`);
5. deja registro en `refresco_precios` (una fila, no un `SyncRun` -- ver el modelo).

Qué **no** hace, y por eso es liviano: no lee el Sheet, no valida pestañas, no hace backfill
histórico, no toca CER/MEP/benchmarks, no purga huérfanos y no escribe en el historial de calidad
de datos.

Cupo de IOL: una corrida gasta ~10 llamadas (1 token + ~9 paneles, memoizados), más las sueltas de
la watchlist que los paneles no cubran. Cuatro corridas por día hábil son ~840-2.700 llamadas al
mes contra el tope de 22.000.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..database import (
    BarraOHLCV, InstrumentoInversion, PrecioInstrumento, RefrescoPrecios,
)
from . import estado_market_data, ohlcv_analytics, watchlist_analytics
from .market_data import precios as market_data_precios
from .market_data import iol_auth
from .market_data.client import use_external_apis

logger = logging.getLogger("refresco_precios")


def _instrumentos_desde_db(db: Session) -> list[dict]:
    """Los instrumentos como los espera `fetch_precios_api`, leídos de la DB y no del Sheet."""
    return [
        {
            "ticker": fila.ticker,
            "nombre": fila.nombre,
            "tipo_instrumento": fila.tipo_instrumento or "",
            "mercado": fila.mercado or "",
            "moneda": fila.moneda or "",
        }
        for fila in db.query(InstrumentoInversion).all()
    ]


def _precios_manuales_desde_db(db: Session) -> list[dict]:
    """Las filas `fuente='sheet'` ya persistidas, que es lo que el sync pasa como `precios_sheet`.

    Sirven para dos cosas dentro de `fetch_precios_api`: calibrar el factor de escala de un ticker
    cuya API cotiza en otra unidad, y detectar que la moneda de la fuente difiere de la declarada.
    """
    return [
        {
            "ticker": fila.ticker,
            "fecha": fila.fecha,
            "precio": float(fila.precio),
            "moneda": fila.moneda,
            "fuente": "sheet",
        }
        for fila in db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "sheet").all()
    ]


def _upsert_precios(db: Session, filas: list[dict], claves_sheet: set[tuple[str, date]]) -> int:
    """Guarda las filas nuevas respetando la precedencia `iol > sheet > api`.

    - una fila `iol` puede desplazar al precio manual de esa `(ticker, fecha)`: es la fuente
      primaria, igual que en el sync. Como el UNIQUE es `(fecha, ticker)`, la fila `sheet` se borra
      antes de insertar la de IOL (no pueden convivir);
    - una fila `api` (data912) nunca pisa una fecha que el Sheet cubre.
    """
    filas_iol = [p for p in filas if p["fuente"] == "iol"]
    claves_iol = {(p["ticker"], p["fecha"]) for p in filas_iol}
    filas_api = [
        p for p in filas
        if p["fuente"] != "iol"
        and (p["ticker"], p["fecha"]) not in claves_sheet
        and (p["ticker"], p["fecha"]) not in claves_iol
    ]

    # Las claves que IOL reclama y el Sheet también tiene: se libera la fila manual.
    a_liberar = claves_iol & claves_sheet
    for ticker, fecha in a_liberar:
        db.query(PrecioInstrumento).filter(
            PrecioInstrumento.ticker == ticker,
            PrecioInstrumento.fecha == fecha,
            PrecioInstrumento.fuente == "sheet",
        ).delete(synchronize_session=False)
    if a_liberar:
        db.flush()
        logger.info(
            "refresco: %d precio(s) manual(es) desplazado(s) por IOL (se reponen en el próximo sync)",
            len(a_liberar),
        )

    a_guardar = filas_iol + filas_api
    if not a_guardar:
        return 0

    tickers = {p["ticker"] for p in a_guardar}
    existentes = {
        (r.ticker, r.fecha): r
        for r in db.query(PrecioInstrumento).filter(PrecioInstrumento.ticker.in_(tickers)).all()
    }
    for p in a_guardar:
        fila = existentes.get((p["ticker"], p["fecha"]))
        if fila is not None:
            fila.precio, fila.moneda, fila.fuente = p["precio"], p["moneda"], p["fuente"]
        else:
            nueva = PrecioInstrumento(**p)
            existentes[(p["ticker"], p["fecha"])] = nueva
            db.add(nueva)
    db.flush()
    return len(a_guardar)


def _espejo_ohlcv(db: Session, filas: list[dict]) -> None:
    """Espejo close-only del precio del día en `serie_ohlcv`.

    Lo mismo que hace el sync: así el backfill de mañana encuentra la fecha y la promueve a vela
    real en vez de partir de cero. Respeta `debe_reemplazar_barra`, para no degradar una vela
    completa que ya exista a un close-only.
    """
    if not filas:
        return
    tickers = {p["ticker"] for p in filas}
    existentes = {
        (r.ticker, r.fecha): r
        for r in db.query(BarraOHLCV).filter(BarraOHLCV.ticker.in_(tickers)).all()
    }
    for p in filas:
        clave = (p["ticker"], p["fecha"])
        existente = existentes.get(clave)
        existente_dict = (
            {
                "fuente": existente.fuente,
                "tiene_velas": existente.apertura is not None
                and existente.maximo is not None
                and existente.minimo is not None,
            }
            if existente is not None else None
        )
        if not ohlcv_analytics.debe_reemplazar_barra(
            existente_dict, {"fuente": p["fuente"], "tiene_velas": False}
        ):
            continue
        if existente is not None:
            existente.cierre = p["precio"]
            existente.moneda = p["moneda"]
            existente.fuente = p["fuente"]
        else:
            nueva = BarraOHLCV(
                ticker=p["ticker"], fecha=p["fecha"],
                apertura=None, maximo=None, minimo=None, cierre=p["precio"],
                volumen=None, moneda=p["moneda"], fuente=p["fuente"],
            )
            existentes[clave] = nueva
            db.add(nueva)
    db.flush()


def _registrar(db: Session, **campos) -> None:
    """Deja la marca de la corrida en la fila única de `refresco_precios`."""
    fila = db.get(RefrescoPrecios, 1)
    if fila is None:
        fila = RefrescoPrecios(id=1)
        db.add(fila)
    fila.timestamp = datetime.utcnow()
    for nombre, valor in campos.items():
        setattr(fila, nombre, valor)


def refrescar(db: Session) -> dict:
    """Refresca el precio del día de cartera y watchlist. Hace commit. Nunca lanza por red.

    Devuelve un resumen para el log y para la UI.
    """
    inicio = time.monotonic()

    if not use_external_apis():
        logger.info("refresco: USE_EXTERNAL_APIS está apagado, no se pide nada")
        _registrar(db, duration_ms=0, precios_actualizados=0, precios_watchlist=0,
                   iol_llamadas=0, resultado="sin_fuentes", detalle=None)
        db.commit()
        return {"resultado": "sin_fuentes", "precios_actualizados": 0, "precios_watchlist": 0,
                "iol_llamadas": 0, "issues": 0}

    iol_auth.iniciar_corrida()
    instrumentos = _instrumentos_desde_db(db)
    precios_manuales = _precios_manuales_desde_db(db)
    claves_sheet = {(p["ticker"], p["fecha"]) for p in precios_manuales}
    estado_por_ticker = estado_market_data.cargar(db)

    paneles_fn = market_data_precios.memo_paneles(db)
    fci_fn = market_data_precios.memo_fci(db)

    # `claves_excluir=set()`: IOL puede reclamar una fecha que el Sheet ya cubre (es la fuente
    # primaria); la precedencia se resuelve al escribir, igual que en el sync.
    filas, issues = market_data_precios.fetch_precios_api(
        instrumentos, precios_manuales, set(), db,
        estado_por_ticker=estado_por_ticker, paneles_fn=paneles_fn, fci_fn=fci_fn,
    )

    guardados = _upsert_precios(db, filas, claves_sheet)
    _espejo_ohlcv(db, filas)

    # Watchlist. Los que también están en cartera ya quedaron resueltos arriba: para esos
    # `get_watchlist` lee la serie de `precios_instrumento`.
    tickers_en_cartera = {i["ticker"] for i in instrumentos}
    wl_items = watchlist_analytics.items_para_market_data(db)
    wl_count = 0
    if wl_items:
        a_cotizar = [w["ticker"] for w in wl_items if w["ticker"] not in tickers_en_cartera]
        if a_cotizar:
            wl_count, issues_wl = watchlist_analytics.refrescar_precios(
                db, a_cotizar, paneles_fn=paneles_fn, fci_fn=fci_fn,
                tickers_en_cartera=tickers_en_cartera,
            )
            issues.extend(issues_wl)

    estado_market_data.persistir(db, estado_por_ticker)

    llamadas = iol_auth.finalizar_corrida()
    duracion = int((time.monotonic() - inicio) * 1000)

    # Los issues no van al historial de calidad de datos (eso es del sync, que sí mira el Sheet):
    # se cuentan por regla y quedan en el log y en `detalle`.
    por_regla: dict[str, int] = {}
    for issue in issues:
        por_regla[issue.regla] = por_regla.get(issue.regla, 0) + 1

    _registrar(
        db, duration_ms=duracion, precios_actualizados=guardados, precios_watchlist=wl_count,
        iol_llamadas=llamadas, resultado="ok", detalle={"issues": por_regla} if por_regla else None,
    )
    db.commit()

    logger.info(
        "refresco: %d precio(s) de cartera, %d de watchlist, %d llamada(s) a IOL, %d ms%s",
        guardados, wl_count, llamadas, duracion,
        f", issues: {por_regla}" if por_regla else "",
    )
    return {
        "resultado": "ok",
        "precios_actualizados": guardados,
        "precios_watchlist": wl_count,
        "iol_llamadas": llamadas,
        "issues": len(issues),
    }


def ultimo(db: Session) -> dict | None:
    """La última corrida registrada, o `None` si el job nunca corrió."""
    fila = db.get(RefrescoPrecios, 1)
    if fila is None:
        return None
    return {
        "timestamp": fila.timestamp,
        "duration_ms": fila.duration_ms,
        "precios_actualizados": fila.precios_actualizados,
        "precios_watchlist": fila.precios_watchlist,
        "iol_llamadas": fila.iol_llamadas,
        "resultado": fila.resultado,
    }
