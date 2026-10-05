"""Envío de notificaciones por Telegram.

Por qué Telegram y no Web Push: la app se sirve por HTTP en la LAN
(`http://smoa7001lx:8087`), y los navegadores no permiten Notification/Push -- ni registran
service workers -- en orígenes que no son seguros. Web Push obligaría a montar HTTPS primero.
Acá el backend hace un POST saliente y el aviso llega al celular bloqueado, sin tocar nada de eso.

Mismo contrato que el resto de las integraciones de red del proyecto: **esta función nunca lanza**.
Que no se pueda avisar no puede tirar abajo el sync ni el job que la llama.

Nunca se loguea el token: va en la URL de la API de Telegram, así que tampoco se loguea la URL
(mismo cuidado que `market_data/iol_auth` con el bearer).
"""
from __future__ import annotations

import logging
import os

from ..market_data.client import request_json

logger = logging.getLogger("notificaciones")

_API = "https://api.telegram.org"

# Telegram corta los mensajes en 4096 caracteres.
_MAX_LARGO = 4000

TIMEOUT = 15.0


def bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def chat_id() -> str:
    return (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


def alertas_habilitadas() -> bool:
    """Interruptor general, análogo a `USE_EXTERNAL_APIS`. Apagado = no se manda nada."""
    return (os.getenv("ALERTAS_ENABLED") or "false").lower() in ("true", "1", "yes")


def configurado() -> bool:
    """`True` si hay token y chat id. Lo usa la UI para decir si falta configurar algo."""
    return bool(bot_token() and chat_id())


def enviar(texto: str) -> tuple[bool, str | None]:
    """Manda `texto` al chat configurado. Devuelve `(entregado, motivo_del_fallo)`.

    El motivo es para mostrarlo en la app y para el log; nunca incluye el token.
    """
    if not texto.strip():
        return False, "mensaje vacío"
    if not alertas_habilitadas():
        return False, "alertas deshabilitadas (ALERTAS_ENABLED)"
    token, chat = bot_token(), chat_id()
    if not token or not chat:
        return False, "falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID"

    recortado = texto if len(texto) <= _MAX_LARGO else texto[: _MAX_LARGO - 1] + "…"
    status, body = request_json(
        "POST",
        f"{_API}/bot{token}/sendMessage",
        data={"chat_id": chat, "text": recortado, "disable_web_page_preview": "true"},
        timeout=TIMEOUT,
    )

    if status is None:
        logger.warning("telegram: no hubo respuesta (timeout, proxy o DNS)")
        return False, "no hubo respuesta de Telegram"
    if status != 200:
        # El body de un error de Telegram trae `description` y no incluye el token.
        detalle = ""
        if isinstance(body, dict):
            detalle = str(body.get("description") or "")
        logger.warning("telegram: respondió %s %s", status, detalle)
        return False, f"Telegram respondió {status}{': ' + detalle if detalle else ''}"

    logger.info("telegram: mensaje entregado (%d caracteres)", len(recortado))
    return True, None
