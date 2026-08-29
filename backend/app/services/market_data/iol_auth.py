"""Autenticación OAuth de la API de InvertirOnline (IOL) y control del cupo mensual de llamadas.

IOL bonifica 25.000 llamadas por mes calendario; pasado eso cobra por bloque adicional (ver
DESARROLLO.md). Todo lo de este módulo respeta el mismo contrato que el resto de `market_data`:
nunca lanza, y cualquier fallo (credenciales ausentes, red caída, cupo agotado) se traduce en
`None` para que el llamador (`market_data/iol.py`) caiga al fallback público (data912/
analisistecnico).

Credenciales: archivo JSON `{"username": ..., "password": ...}` montado read-only — mismo patrón
que `sheets_client._credentials_path()` para la cuenta de servicio de Google. Nunca se aceptan
usuario/contraseña por variable de entorno: quedarían visibles en `docker inspect` y en el
entorno del proceso del contenedor.

El bearer token y el refresh token viven SOLO en memoria (un singleton a nivel de módulo): nunca
se persisten en disco ni en la base. Se pierden al reiniciar el contenedor — no pasa nada, sólo
cuesta una reautenticación (1 llamada) en el próximo sync.

El cupo mensual sí se persiste (tabla `EstadoApiIol`), porque tiene que sobrevivir al reinicio
del contenedor para seguir protegiendo contra el límite bonificado (requiere que `/app/data` esté
en un volumen — ver docker-compose.yml). Se lee/escribe con la MISMA sesión que pasa el llamador
(`db`, la del sync) y sin comitear acá: SQLite sólo admite un escritor a la vez, y el sync
mantiene una transacción larga sin commit hasta el final — una segunda conexión/sesión
independiente que intentara comitear en paralelo chocaría con "database is locked" (probado en
producción: ver commit que corrige esto). El conteo queda pendiente en la sesión del sync y se
vuelve durable recién con su commit final; si el sync falla antes de eso, las llamadas ya
hechas en esa corrida no quedan contadas — es el trade-off elegido frente al riesgo de romper el
sync entero por una segunda conexión SQLite compitiendo por el lock de escritura.

IMPORTANTE — higiene de secretos: ninguna función de este módulo loguea la contraseña, el
access_token ni el refresh_token, ni el body de una respuesta de error (podría ecoar el token
enviado). Los fallos de autenticación se reportan sólo con el código HTTP.
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ...database import EstadoApiIol
from .client import request_json

logger = logging.getLogger("market_data")

TOKEN_URL = "https://api.invertironline.com/token"
BASE_URL = "https://api.invertironline.com/api/v2"

# Margen de seguridad antes de que expire el bearer (IOL lo emite con ~15 min de vida) para no
# arrancar una request con un token que vence a mitad de viaje.
_MARGEN_EXPIRACION = timedelta(seconds=60)

_LIMITE_MENSUAL_DEFAULT = 22_000  # colchón (~12%) bajo el límite bonificado real de 25.000


def iol_enabled() -> bool:
    """Feature flag independiente de USE_EXTERNAL_APIS: permite apagar sólo IOL (p.ej. si se
    quiere ahorrar cupo antes de fin de mes) sin apagar data912/analisistecnico."""
    return os.getenv("IOL_ENABLED", "true").lower() in ("true", "1", "yes")


def _limite_mensual() -> int:
    try:
        return int(os.getenv("IOL_LIMITE_MENSUAL", str(_LIMITE_MENSUAL_DEFAULT)))
    except (TypeError, ValueError):
        return _LIMITE_MENSUAL_DEFAULT


def _credentials_path() -> str:
    return os.getenv(
        "IOL_CREDENTIALS_FILE",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "iol.json"),
    )


def _leer_credenciales() -> tuple[str, str] | None:
    """`(username, password)` desde el archivo montado, o `None` si falta o está mal formado.
    Nunca lanza ni loguea el contenido del archivo."""
    path = _credentials_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        username, password = data.get("username"), data.get("password")
        if not username or not password:
            return None
        return str(username), str(password)
    except Exception:
        logger.warning("market_data.iol: archivo de credenciales inválido en '%s'", path)
        return None


def _periodo_actual() -> str:
    """"YYYY-MM" en UTC — el mismo huso con el que está documentada la clave de `EstadoApiIol`.
    No `date.today()`: esa es la fecha local del contenedor y, con un TZ corrido, el corte de mes
    no coincidiría con el de IOL (que factura por mes calendario)."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def cupo_disponible(db: Session) -> bool:
    """True si todavía hay margen para llamar a IOL este mes calendario. Cualquier error de DB
    se trata como "sin cupo" — nunca "cupo libre" — para no arriesgarse a llamar a IOL sin poder
    contarlo. No comitea ni hace rollback: es una lectura sobre la sesión del llamador."""
    try:
        fila = db.get(EstadoApiIol, _periodo_actual())
        llamadas = fila.llamadas if fila is not None else 0
        return llamadas < _limite_mensual()
    except Exception as exc:
        logger.warning("market_data.iol: no se pudo leer el contador de cupo mensual: %s", exc)
        return False


def registrar_llamada(db: Session) -> None:
    """Suma una llamada al contador del mes actual, sobre la MISMA sesión que pasa el llamador
    (ver nota del módulo sobre por qué no usa una sesión propia). Sólo hace `flush` — no
    `commit` — para no comitear a destiempo el resto de los cambios pendientes de esa sesión;
    la durabilidad del conteo queda atada al commit final del llamador."""
    periodo = _periodo_actual()
    try:
        fila = db.get(EstadoApiIol, periodo)
        if fila is None:
            fila = EstadoApiIol(periodo=periodo, llamadas=0)
            db.add(fila)
        fila.llamadas += 1
        db.flush()
    except Exception as exc:
        # No se hace rollback: haría perder el resto de los cambios pendientes de `db` (el sync
        # en curso), no sólo este contador.
        logger.warning("market_data.iol: no se pudo persistir el contador de cupo mensual: %s", exc)


class _TokenCache:
    """Singleton en memoria (nunca en disco) con el bearer/refresh token vigentes."""

    def __init__(self):
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.expira_en: datetime | None = None
        self.lock = threading.Lock()

    def vigente(self) -> bool:
        return (
            self.access_token is not None
            and self.expira_en is not None
            and datetime.now(timezone.utc) < self.expira_en - _MARGEN_EXPIRACION
        )


_cache = _TokenCache()


def _guardar_respuesta_token(body: dict) -> str | None:
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")
    expires_in = body.get("expires_in")
    if not access_token or not isinstance(expires_in, (int, float)):
        return None
    _cache.access_token = access_token
    _cache.refresh_token = refresh_token or _cache.refresh_token
    _cache.expira_en = datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))
    return access_token


def _autenticar(db: Session, username: str, password: str) -> str | None:
    registrar_llamada(db)
    status, body = request_json(
        "POST", TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"username": username, "password": password, "grant_type": "password"},
    )
    if status != 200 or not isinstance(body, dict):
        logger.warning("market_data.iol: fallo de autenticación (HTTP %s)", status)
        return None
    return _guardar_respuesta_token(body)


def _refrescar(db: Session, refresh_token: str) -> str | None:
    registrar_llamada(db)
    status, body = request_json(
        "POST", TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"refresh_token": refresh_token, "grant_type": "refresh_token"},
    )
    if status != 200 or not isinstance(body, dict):
        logger.warning("market_data.iol: fallo al refrescar el token (HTTP %s)", status)
        return None
    return _guardar_respuesta_token(body)


def invalidar_cache() -> None:
    """Fuerza una reautenticación en la próxima llamada (se usa tras un 401 inesperado a mitad
    de sesión: token revocado del lado de IOL antes de la expiración declarada)."""
    with _cache.lock:
        _cache.expira_en = None


def get_bearer(db: Session) -> str | None:
    """Token bearer vigente, listo para el header `Authorization`. `None` si IOL está
    deshabilitada, sin credenciales, sin cupo, o la autenticación falló — en cualquier caso el
    llamador cae al fallback público. Si el token cacheado sigue vigente, no consume cupo."""
    if not iol_enabled():
        return None
    with _cache.lock:
        if _cache.vigente():
            return _cache.access_token

        if not cupo_disponible(db):
            logger.warning("market_data.iol: cupo mensual agotado, no se llama a IOL")
            return None

        if _cache.refresh_token:
            token = _refrescar(db, _cache.refresh_token)
            if token:
                return token
            _cache.refresh_token = None  # el refresh token también puede haber vencido

        if not cupo_disponible(db):  # el intento de refresh pudo haber agotado el cupo
            return None
        credenciales = _leer_credenciales()
        if credenciales is None:
            return None
        username, password = credenciales
        return _autenticar(db, username, password)


def get_autenticado(db: Session, url: str) -> object | None:
    """GET a `url` con el bearer vigente. Chequea cupo y cuenta la llamada antes de pedirla;
    reintenta una vez si el token resulta revocado (401) a mitad de sesión. `None` ante cualquier
    fallo — deshabilitada, sin credenciales, sin cupo, error HTTP o de red. Nunca lanza."""
    for intento in range(2):
        token = get_bearer(db)
        if token is None:
            return None
        if not cupo_disponible(db):
            logger.warning("market_data.iol: cupo mensual agotado, no se llama a IOL")
            return None
        registrar_llamada(db)
        status, body = request_json("GET", url, headers={"Authorization": f"Bearer {token}"})
        if status == 401 and intento == 0:
            invalidar_cache()
            continue
        if status != 200:
            return None
        return body
    return None
