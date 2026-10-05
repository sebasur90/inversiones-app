"""Adaptador DB → `alertas_engine` → canal de notificación.

Lee los niveles de precio de todas las carteras y de la watchlist, le pregunta al motor qué hay
que avisar, persiste el estado y manda un único mensaje.

Orden de las operaciones, a propósito: **primero se persiste el estado y se commitea, después se
manda el mensaje**. La llamada de red queda fuera de cualquier transacción de escritura abierta
(el lock de escritura de SQLite durante un POST con timeout es justo el problema que ya tuvo el
sync). Si el proceso muere entre el commit y el envío, las filas quedan `disparada` con
`entregada=0` y la corrida siguiente reintenta el envío sin volver a tratar el cruce como nuevo.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..database import AlertaPrecio
from . import alertas_engine, inversiones_analytics, watchlist_analytics
from .notificaciones import telegram

logger = logging.getLogger("alertas")


def _estados_guardados(db: Session) -> dict[tuple[str, str, str], str]:
    return {
        (fila.ticker, fila.tipo, fila.cartera or ""): fila.estado
        for fila in db.query(AlertaPrecio).all()
    }


def _candidatas(db: Session) -> list[alertas_engine.Candidata]:
    """Todos los niveles vigentes: stop-loss y objetivo por cartera, más la watchlist.

    Se recorre cartera por cartera (y no el consolidado) para que el aviso pueda decir de qué
    cartera es la posición, y porque el mismo ticker puede tener tenencia en más de una.
    """
    candidatas: list[alertas_engine.Candidata] = []
    for cartera in inversiones_analytics.get_carteras(db):
        rendimiento = inversiones_analytics.get_rendimiento_por_ticker(cartera, db)
        candidatas.extend(alertas_engine.candidatas_de_posiciones(rendimiento, cartera))
    candidatas.extend(alertas_engine.candidatas_de_watchlist(watchlist_analytics.get_watchlist(db)))
    return candidatas


def _fila(db: Session, clave: tuple[str, str, str]) -> AlertaPrecio | None:
    ticker, tipo, cartera = clave
    return (
        db.query(AlertaPrecio)
        .filter(
            AlertaPrecio.ticker == ticker,
            AlertaPrecio.tipo == tipo,
            AlertaPrecio.cartera == cartera,
        )
        .first()
    )


def _aplicar(db: Session, decision: alertas_engine.Decision) -> None:
    """Persiste el resultado del motor. No manda nada: el envío va después del commit."""
    ahora = datetime.utcnow()

    for alerta in decision.a_emitir:
        fila = _fila(db, alerta.clave)
        if fila is None:
            fila = AlertaPrecio(ticker=alerta.ticker, tipo=alerta.tipo, cartera=alerta.cartera)
            db.add(fila)
        fila.estado = alertas_engine.ESTADO_DISPARADA
        fila.nivel = alerta.nivel
        fila.precio_disparo = alerta.precio
        fila.moneda = alerta.moneda
        fila.emitida_en = ahora
        fila.entregada = 0
        fila.detalle = {"nombre": alerta.nombre}

    for clave in decision.a_rearmar:
        fila = _fila(db, clave)
        if fila is not None:
            fila.estado = alertas_engine.ESTADO_ARMADA

    for clave in decision.a_crear:
        ticker, tipo, cartera = clave
        db.add(AlertaPrecio(
            ticker=ticker, tipo=tipo, cartera=cartera,
            estado=alertas_engine.ESTADO_ARMADA, entregada=0,
        ))


def _pendientes_de_entrega(db: Session) -> list[alertas_engine.Alerta]:
    """Cruces ya decididos cuyo envío falló antes. Se reintentan sin re-disparar nada."""
    filas = (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.estado == alertas_engine.ESTADO_DISPARADA, AlertaPrecio.entregada == 0)
        .all()
    )
    salida = []
    for fila in filas:
        if fila.nivel is None or fila.precio_disparo is None:
            continue
        nombre = (fila.detalle or {}).get("nombre") or fila.ticker
        salida.append(alertas_engine.Alerta(
            ticker=fila.ticker, nombre=nombre, tipo=fila.tipo, cartera=fila.cartera or "",
            nivel=float(fila.nivel), precio=float(fila.precio_disparo), moneda=fila.moneda or "",
        ))
    return salida


def evaluar_y_notificar(db: Session, notificar: bool = True) -> dict:
    """Evalúa todos los niveles, persiste el estado y manda un mensaje con los cruces nuevos.

    `notificar=False` evalúa y persiste sin mandar nada: lo usan los tests y sirve para sembrar
    el estado inicial sin disparar una andanada de avisos la primera vez.
    """
    candidatas = _candidatas(db)
    decision = alertas_engine.evaluar(candidatas, _estados_guardados(db))

    _aplicar(db, decision)
    db.commit()  # antes del envío: la red no corre con una transacción de escritura abierta

    # Los cruces nuevos ya quedaron persistidos con `entregada=0`, así que salen de esta consulta
    # junto con los que no se pudieron entregar en corridas anteriores.
    a_enviar = _pendientes_de_entrega(db)

    resumen = {
        "niveles_vigilados": len(candidatas),
        "nuevas": len(decision.a_emitir),
        "rearmadas": len(decision.a_rearmar),
        "pendientes_de_entrega": len(a_enviar),
        "entregado": False,
        "motivo": None,
    }

    if not a_enviar:
        logger.info(
            "alertas: %d niveles vigilados, sin cruces nuevos (%d re-armadas)",
            len(candidatas), len(decision.a_rearmar),
        )
        return resumen

    if not notificar:
        resumen["motivo"] = "notificación desactivada en la llamada"
        return resumen

    entregado, motivo = telegram.enviar(alertas_engine.texto_notificacion(a_enviar))
    resumen["entregado"] = entregado
    resumen["motivo"] = motivo

    if entregado:
        ahora = datetime.utcnow()
        for alerta in a_enviar:
            fila = _fila(db, alerta.clave)
            if fila is not None:
                fila.entregada = 1
                fila.emitida_en = fila.emitida_en or ahora
        db.commit()
        logger.info("alertas: %d aviso(s) entregado(s)", len(a_enviar))
    else:
        logger.warning("alertas: %d aviso(s) sin entregar: %s", len(a_enviar), motivo)

    return resumen


def listar(db: Session, limite: int = 50) -> list[dict]:
    """Historial de cruces, el más reciente primero. Lo consume la app para mostrar el estado."""
    filas = (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.emitida_en.isnot(None))
        .order_by(AlertaPrecio.emitida_en.desc())
        .limit(limite)
        .all()
    )
    return [
        {
            "ticker": f.ticker,
            "nombre": (f.detalle or {}).get("nombre") or f.ticker,
            "tipo": f.tipo,
            "etiqueta": alertas_engine.ETIQUETA_TIPO.get(f.tipo, f.tipo),
            "cartera": f.cartera or None,
            "estado": f.estado,
            "nivel": float(f.nivel) if f.nivel is not None else None,
            "precio_disparo": float(f.precio_disparo) if f.precio_disparo is not None else None,
            "moneda": f.moneda or "",
            "emitida_en": f.emitida_en,
            "entregada": bool(f.entregada),
        }
        for f in filas
    ]


def estado_configuracion(db: Session) -> dict:
    """Si las alertas están prendidas y configuradas, y cuándo fue el último aviso."""
    ultima = (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.emitida_en.isnot(None))
        .order_by(AlertaPrecio.emitida_en.desc())
        .first()
    )
    return {
        "habilitadas": telegram.alertas_habilitadas(),
        "configurado": telegram.configurado(),
        "canal": "telegram",
        "niveles_vigilados": db.query(AlertaPrecio).count(),
        "ultimo_aviso": ultima.emitida_en if ultima is not None else None,
        "sin_entregar": (
            db.query(AlertaPrecio)
            .filter(AlertaPrecio.estado == alertas_engine.ESTADO_DISPARADA, AlertaPrecio.entregada == 0)
            .count()
        ),
    }
