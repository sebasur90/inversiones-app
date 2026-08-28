"""Cliente HTTP compartido para las APIs de mercado.

`trust_env=True` hace que httpx tome HTTP_PROXY/HTTPS_PROXY/NO_PROXY del entorno (así llega al
mismo proxy corporativo que usa el resto de la app, vía .env.corporate). El User-Agent es
necesario: ArgentinaDatos y DolarAPI devuelven 403 al User-Agent por defecto de las librerías
HTTP de Python, tratándolo como bot.
"""
import os
import logging
import httpx

logger = logging.getLogger("market_data")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) inversiones-app/1.0 (+https://github.com/)"

DEFAULT_TIMEOUT = 20.0


def use_external_apis() -> bool:
    """Analogo a USE_LOCAL_SHEET: si está apagado, este paquete no hace ninguna llamada de red."""
    return os.getenv("USE_EXTERNAL_APIS", "false").lower() in ("true", "1", "yes")


def get_json(url: str, timeout: float = DEFAULT_TIMEOUT):
    """GET con manejo no-fatal de errores. Devuelve el JSON parseado, o None si falló cualquier cosa
    (timeout, proxy caído, HTTP error, JSON inválido). Nunca lanza."""
    try:
        with httpx.Client(trust_env=True, timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("market_data: fallo GET %s: %s", url, exc)
        return None
