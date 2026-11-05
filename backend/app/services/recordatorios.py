"""Recordatorios con fecha: "el 10 de julio, revisar estas acciones". Los carga el usuario y el job los
manda por Telegram cuando llega el momento.

**Un aviso nunca se da por enviado si Telegram no confirmó la entrega.** A diferencia de
`diario_decisiones.avisar_revisiones`, acá no hay interruptor en Ajustes ni marca de "silenciado":
cada recordatorio ya es un pedido explícito, y marcarlo sin mandarlo lo perdería sin que se note. Si
Telegram o el servidor no están disponibles, el recordatorio espera y sale en la corrida siguiente.

"Hoy" sale de `ahora_local()`, nunca de `date.today()`: el contenedor no define `TZ`, y en UTC un
recordatorio de mañana a la mañana se vería vencido desde las 21:00 de hoy.
"""
from __future__ import annotations

import html
import logging
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..database import EventoMercado, Recordatorio
from . import alertas_engine, ohlcv_analytics, scheduler, sync_lock
from .notificaciones import telegram

logger = logging.getLogger("recordatorios")

ESTADO_PENDIENTE = "pendiente"
ESTADO_HECHO = "hecho"
#: Antes de la apertura: alcanza para mirar el recordatorio con el mercado todavía cerrado.
HORA_POR_DEFECTO = "09:00"
LOCK_ESCRITURA_TIMEOUT_SEG = 300

_TICKER = re.compile(r"^[A-Z0-9^][A-Z0-9._-]{0,19}$")   # `^` por los índices: ^MERV

MENSAJE_ERROR = {
    "titulo_vacio": "El recordatorio necesita un título.",
    "fecha_pasada": "Esa fecha ya pasó.",
    "hora_pasada": "Esa hora de hoy ya pasó.",
    "ticker_invalido": "Hay un ticker con caracteres que no corresponden.",
    "evento_inexistente": "El evento vinculado ya no existe.",
    "ya_hecho": "Este recordatorio ya está hecho: reabrilo para posponerlo.",
}


class RecordatorioNoEncontrado(Exception):
    pass


def ahora_local() -> datetime:
    """La hora de ahora en la zona del scheduler, sin offset: se compara contra `fecha` + `hora`."""
    zona = (os.getenv("SCHEDULER_TZ") or scheduler.ZONA_DEFAULT).strip()
    return datetime.now(ZoneInfo(zona)).replace(tzinfo=None)


def _vence_en(fecha: date, hora: str | None) -> datetime:
    return datetime.combine(fecha, time.fromisoformat(hora or HORA_POR_DEFECTO))


def _error_de_momento(fecha: date, hora: str | None, ahora: datetime) -> str | None:
    """Hoy sin hora se acepta aunque ya hayan pasado las 9: sale en la corrida siguiente."""
    if fecha < ahora.date():
        return "fecha_pasada"
    if hora and _vence_en(fecha, hora) <= ahora:
        return "hora_pasada"
    return None


def _normalizar_tickers(tickers: list[str]) -> tuple[list[str], str | None]:
    salida: list[str] = []
    for crudo in tickers:
        ticker = crudo.strip().upper()
        if not ticker:
            continue
        if not _TICKER.match(ticker):
            return [], "ticker_invalido"
        if ticker not in salida:
            salida.append(ticker)
    return salida, None


def _titulos_de_eventos(db: Session, recordatorios: list[Recordatorio]) -> dict[int, str]:
    ids = {r.evento_id for r in recordatorios if r.evento_id is not None}
    if not ids:
        return {}
    return dict(db.query(EventoMercado.id, EventoMercado.titulo).filter(EventoMercado.id.in_(ids)).all())


def _a_dict(r: Recordatorio, ahora: datetime, eventos: dict[int, str]) -> dict:
    vence = _vence_en(r.fecha, r.hora)
    return {
        "id": r.id, "titulo": r.titulo, "nota": r.nota, "fecha": r.fecha, "hora": r.hora,
        "tickers": r.tickers or [], "evento_id": r.evento_id, "evento_titulo": eventos.get(r.evento_id),
        "estado": r.estado, "vence_en": vence.isoformat(timespec="minutes"),
        "vencido": r.estado == ESTADO_PENDIENTE and vence <= ahora,
        "aviso_enviado_en": r.aviso_enviado_en, "hecho_en": r.hecho_en, "creado_en": r.creado_en,
    }


def obtener(db: Session, recordatorio_id: int) -> Recordatorio:
    r = db.query(Recordatorio).filter(Recordatorio.id == recordatorio_id).first()
    if r is None:
        raise RecordatorioNoEncontrado(recordatorio_id)
    return r


def detalle(db: Session, r: Recordatorio, ahora: datetime | None = None) -> dict:
    return _a_dict(r, ahora or ahora_local(), _titulos_de_eventos(db, [r]))


def estado_canal() -> tuple[bool, str | None]:
    """Si un recordatorio va a llegar al celular y, si no, por qué. Lo muestra la pantalla: enterarse
    recién el día del recordatorio de que el aviso nunca iba a salir es el peor momento."""
    if not scheduler.habilitado():
        return False, "el job programado está apagado en el servidor (SCHEDULER_ENABLED)"
    if not telegram.alertas_habilitadas():
        return False, "las alertas están apagadas en el servidor (ALERTAS_ENABLED)"
    if not telegram.configurado():
        return False, "falta configurar Telegram en el servidor (TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID)"
    return True, None


def listar(db: Session, ahora: datetime | None = None) -> dict:
    """Pendientes del más próximo (o más vencido) al más lejano; después los hechos, el último primero."""
    ahora = ahora or ahora_local()
    filas = db.query(Recordatorio).all()
    eventos = _titulos_de_eventos(db, filas)
    pendientes = sorted(
        (r for r in filas if r.estado == ESTADO_PENDIENTE), key=lambda r: (_vence_en(r.fecha, r.hora), r.id),
    )
    hechos = sorted(
        (r for r in filas if r.estado != ESTADO_PENDIENTE), key=lambda r: (r.hecho_en or r.creado_en, r.id), reverse=True,
    )
    activos, motivo = estado_canal()
    return {
        "items": [_a_dict(r, ahora, eventos) for r in pendientes + hechos],
        "avisos_activos": activos, "motivo_inactivo": motivo,
    }


def crear(db: Session, datos: dict, ahora: datetime | None = None) -> tuple[Recordatorio | None, str | None]:
    ahora = ahora or ahora_local()
    titulo = datos["titulo"].strip()
    if not titulo:
        return None, "titulo_vacio"
    error = _error_de_momento(datos["fecha"], datos.get("hora"), ahora)
    if error:
        return None, error
    tickers, error = _normalizar_tickers(datos.get("tickers") or [])
    if error:
        return None, error
    evento_id = datos.get("evento_id")
    if evento_id is not None and db.query(EventoMercado.id).filter(EventoMercado.id == evento_id).first() is None:
        return None, "evento_inexistente"

    marca = datetime.utcnow()
    r = Recordatorio(
        titulo=titulo, nota=(datos.get("nota") or "").strip() or None, fecha=datos["fecha"], hora=datos.get("hora"),
        tickers=tickers, evento_id=evento_id, estado=ESTADO_PENDIENTE, creado_en=marca, actualizado_en=marca,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r, None


def editar(db: Session, r: Recordatorio, datos: dict, ahora: datetime | None = None) -> str | None:
    """Aplica los campos presentes en `datos`. Devuelve un código de error sin haber tocado nada."""
    ahora = ahora or ahora_local()
    titulo = datos["titulo"].strip() if datos.get("titulo") is not None else r.titulo
    if not titulo:
        return "titulo_vacio"
    fecha = datos.get("fecha") or r.fecha
    hora = datos["hora"] if "hora" in datos else r.hora
    cambia_momento = fecha != r.fecha or hora != r.hora
    if cambia_momento:
        error = _error_de_momento(fecha, hora, ahora)
        if error:
            return error
    tickers = r.tickers
    if datos.get("tickers") is not None:
        tickers, error = _normalizar_tickers(datos["tickers"])
        if error:
            return error

    r.titulo, r.fecha, r.hora, r.tickers = titulo, fecha, hora, tickers
    if "nota" in datos:
        r.nota = (datos["nota"] or "").strip() or None
    if cambia_momento:
        r.aviso_enviado_en = None
    if datos.get("estado") == ESTADO_HECHO and r.estado != ESTADO_HECHO:
        r.estado, r.hecho_en = ESTADO_HECHO, datetime.utcnow()
    elif datos.get("estado") == ESTADO_PENDIENTE:
        r.estado, r.hecho_en = ESTADO_PENDIENTE, None
    r.actualizado_en = datetime.utcnow()
    db.commit()
    return None


def posponer(db: Session, r: Recordatorio, dias: int, ahora: datetime | None = None) -> str | None:
    """Corre el aviso `dias` días y lo rearma, conservando la hora. Cuenta desde hoy si ya venció y desde
    su fecha si todavía no llegó: posponer uno de dentro de un mes nunca puede adelantarlo."""
    if r.estado != ESTADO_PENDIENTE:
        return "ya_hecho"
    ahora = ahora or ahora_local()
    r.fecha = max(ahora.date(), r.fecha) + timedelta(days=dias)
    r.aviso_enviado_en = None
    r.actualizado_en = datetime.utcnow()
    db.commit()
    return None


def borrar(db: Session, r: Recordatorio) -> None:
    db.delete(r)
    db.commit()


def _precios(db: Session, tickers: set[str], hoy: date) -> dict[str, tuple[float, str, date]]:
    """Último precio guardado de cada ticker: `ticker -> (precio, moneda, fecha)`. Sólo lee la base.

    Primero el subyacente en USD, que es la referencia de un CEDEAR en el resto de la app. Un ticker
    sin precio queda afuera: el mensaje lo dice, y nada de esto puede frenar el aviso.
    """
    salida: dict[str, tuple[float, str, date]] = {}
    if not tickers:
        return salida
    try:
        for ticker, (fecha, precio, _origen) in ohlcv_analytics.ultimo_precio_subyacente(db, tickers).items():
            salida[ticker] = (precio, "USD", fecha)
        for ticker in tickers - salida.keys():
            serie = ohlcv_analytics.get_serie_barras(ticker, date.min, hoy, db, max_barras=1)
            if serie["barras"]:
                barra = serie["barras"][-1]
                salida[ticker] = (barra.cierre, serie["moneda"], barra.fecha)
    except Exception:
        logger.exception("recordatorios: no se pudieron leer los precios; el aviso sale sin ellos")
        db.rollback()
    return salida


def texto_aviso(r: Recordatorio, precios: dict[str, tuple[float, str, date]], evento: str | None = None) -> str:
    momento = r.fecha.strftime("%d/%m/%Y") + (f" {r.hora}" if r.hora else "")
    lineas = ["⏰ <b>RECORDATORIO</b>", f"<b>{html.escape(r.titulo)}</b>", momento]
    if r.nota:
        lineas.append(html.escape(r.nota))
    for ticker in r.tickers or []:
        if ticker in precios:
            precio, moneda, fecha = precios[ticker]
            prefijo = f"{html.escape(moneda)} " if moneda else ""
            lineas.append(f"• {html.escape(ticker)}: {prefijo}{alertas_engine._fmt_precio(precio)} ({fecha.strftime('%d/%m')})")
        else:
            lineas.append(f"• {html.escape(ticker)}: sin precio")
    if evento:
        lineas.append(f"Evento: {html.escape(evento)}")
    lineas.append("Abrí Recordatorios para marcarlo hecho o posponerlo.")
    return "\n".join(lineas)


def _marcar_enviado(db: Session, r: Recordatorio) -> bool:
    """Commit bajo `sync_lock` (el sync también escribe). `False` si el lock no se liberó a tiempo."""
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("recordatorios: el sync no soltó el lock; el aviso %s no quedó registrado", r.id)
        db.rollback()
        return False
    try:
        r.aviso_enviado_en = datetime.utcnow()
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()


def avisar_vencidos(db: Session, ahora: datetime | None = None) -> dict:
    """Manda por Telegram los recordatorios vencidos sin avisar, uno por mensaje. Hace commit.

    Con un sync en curso se saltea la corrida antes de tocar la red: mandar sin poder registrar el envío
    repetiría el mensaje hasta que el sync terminara. El job vuelve a pasar a los pocos minutos.
    """
    ahora = ahora or ahora_local()
    candidatos = db.query(Recordatorio).filter(
        Recordatorio.estado == ESTADO_PENDIENTE, Recordatorio.aviso_enviado_en.is_(None), Recordatorio.fecha <= ahora.date(),
    ).all()
    vencidos = sorted((r for r in candidatos if _vence_en(r.fecha, r.hora) <= ahora), key=lambda r: (_vence_en(r.fecha, r.hora), r.id))
    resumen = {"vencidos": len(vencidos), "entregados": 0, "motivo": None}
    if not vencidos:
        return resumen
    if not telegram.alertas_habilitadas() or not telegram.configurado():
        return {**resumen, "motivo": "telegram_inactivo"}
    if sync_lock.lock.locked():
        return {**resumen, "motivo": "lock_ocupado"}

    precios = _precios(db, {t for r in vencidos for t in (r.tickers or [])}, ahora.date())
    eventos = _titulos_de_eventos(db, vencidos)
    for r in vencidos:
        entregado, motivo = telegram.enviar(texto_aviso(r, precios, eventos.get(r.evento_id)), parse_mode="HTML")
        if not entregado:
            logger.warning("recordatorios: el aviso %s no se entregó: %s", r.id, motivo)
            resumen["motivo"] = motivo
            continue
        if not _marcar_enviado(db, r):
            return {**resumen, "motivo": "lock_ocupado"}
        resumen["entregados"] += 1
    return resumen
