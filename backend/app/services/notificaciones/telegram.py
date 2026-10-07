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

_SUFIJO_RECORTE = "\n<i>…</i>"

# Lo que dice Telegram cuando el HTML del mensaje no le cierra. Se reconoce para poder
# reintentar en texto plano en vez de perder el aviso.
_PISTAS_FORMATO = ("parse entities", "unsupported start tag", "unclosed")

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


def _recortar(texto: str, parse_mode: str | None) -> tuple[str, str | None]:
    """Recorta a `_MAX_LARGO` sin partir un tag. Devuelve `(texto, parse_mode_efectivo)`.

    Con `parse_mode` un corte a mitad de `<cod` no pierde un pedazo del mensaje: Telegram
    responde 400 `can't parse entities` y se pierde **todo**. Por eso el corte cae en el último
    salto de línea (el texto se arma línea por línea en `alertas_engine`, y ahí cada tag abre y
    cierra dentro de su línea). Si no hay ningún salto de línea —caso patológico— se corta a lo
    bruto y se manda **sin** `parse_mode`: texto feo es mucho mejor que aviso perdido.
    """
    if len(texto) <= _MAX_LARGO:
        return texto, parse_mode
    if parse_mode:
        corte = texto.rfind("\n", 0, _MAX_LARGO - len(_SUFIJO_RECORTE))
        if corte > 0:
            return texto[:corte] + _SUFIJO_RECORTE, parse_mode
        return texto[: _MAX_LARGO - 1] + "…", None
    return texto[: _MAX_LARGO - 1] + "…", None


def _post(texto: str, token: str, chat: str, parse_mode: str | None):
    data = {"chat_id": chat, "text": texto, "disable_web_page_preview": "true"}
    if parse_mode:
        data["parse_mode"] = parse_mode
    return request_json("POST", f"{_API}/bot{token}/sendMessage", data=data, timeout=TIMEOUT)


def _es_error_de_formato(body) -> bool:
    detalle = str(body.get("description") or "").lower() if isinstance(body, dict) else ""
    return any(pista in detalle for pista in _PISTAS_FORMATO)


def enviar(texto: str, parse_mode: str | None = None) -> tuple[bool, str | None]:
    """Manda `texto` al chat configurado. Devuelve `(entregado, motivo_del_fallo)`.

    `parse_mode` (`"HTML"`) habilita negrita y monospace. Por defecto `None`, que deja el payload
    exactamente como era: un mensaje de texto plano no tiene por qué pasar por el parser de
    Telegram y arriesgarse a un 400 por un `&` perdido.

    Si el envío con formato falla **por el formato**, se reintenta una vez en texto plano. Un bug
    de escapado tiene que degradar el aviso, no hacerlo desaparecer.

    El motivo es para mostrarlo en la app y para el log; nunca incluye el token.
    """
    if not texto.strip():
        return False, "mensaje vacío"
    if not alertas_habilitadas():
        return False, "alertas deshabilitadas (ALERTAS_ENABLED)"
    token, chat = bot_token(), chat_id()
    if not token or not chat:
        return False, "falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID"

    recortado, modo = _recortar(texto, parse_mode)
    status, body = _post(recortado, token, chat, modo)

    if status == 400 and modo and _es_error_de_formato(body):
        logger.warning("telegram: el formato %s fue rechazado; reintento en texto plano", modo)
        status, body = _post(recortado, token, chat, None)

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
