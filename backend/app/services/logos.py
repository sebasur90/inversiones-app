"""Logos de los emisores: el servidor los baja una vez y los guarda en el volumen de datos.

Por qué no un CDN desde el celular: depende de un tercero (algunos piden token), no funciona sin
internet y le cuenta a ese tercero qué empresas mirás. Acá los baja el backend (por el mismo proxy
que el resto), los valida y los sirve desde la propia app (`GET /api/inversiones/logos/{base}.png`).

De dónde sale cada logo, en orden:
1. el favicon grande del dominio de la empresa, desde un servicio público de favicons;
2. el `apple-touch-icon` de la home de la empresa.
El dominio sale del `website` que informa Yahoo (queda en `FundamentalesSnapshot.metricas`), así
que los logos aparecen a medida que la ingesta de fundamentales re-baja a cada emisor.

Qué se rechaza: lo que no es un PNG real (una página de error con status 200 es lo más común),
lo menor a `MIN_LADO` (un favicon de 16px se ve borroso en el mapa), lo mayor a `MAX_BYTES`, y el
**icono genérico** que el servicio de favicons devuelve para un dominio que no conoce: se lo
"aprende" pidiendo un dominio inexistente al comienzo de cada corrida, en vez de fijar un hash que
se rompe el día que cambie el dibujo.

Como el dominio lo informa un tercero y lo consulta el servidor, se valida con estrictez: sólo
nombres de host públicos con aspecto de dominio (nada de IPs, puertos ni `localhost`), sólo HTTPS,
pocas redirecciones y un tope de tamaño.

Se enganchan al job de fundamentales (`scheduler.correr_fundamentales`): ahí es donde aparecen
los `website` nuevos. Cada corrida baja a lo sumo `LOGOS_MAX_POR_CORRIDA` (default 40).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import ClasificacionAuto, DB_PATH, FundamentalesSnapshot, LogoEmpresa
from . import sync_lock
from .market_data.client import USER_AGENT, use_external_apis

logger = logging.getLogger("logos")

MAX_POR_CORRIDA_DEFAULT = 40
MAX_BYTES = 200 * 1024
MIN_LADO = 32
MAX_LADO = 1024
TIMEOUT_SEG = 10.0
MAX_REDIRECCIONES = 3
SIN_LOGO_REINTENTO_DIAS = 30
BACKOFF_TOPE_DIAS = 30
LOCK_ESCRITURA_TIMEOUT_SEG = 300

_PNG = b"\x89PNG\r\n\x1a\n"
_HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
# Un `ticker_base` es lo que se usa de nombre de archivo: nada de separadores ni `..`.
_BASE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")

_URL_FAVICON = "https://www.google.com/s2/favicons?domain={dominio}&sz=128"
_URL_APPLE = "https://{dominio}/apple-touch-icon.png"
_DOMINIO_INEXISTENTE = "dominio-que-no-existe-zzqx.com"

# Una sola corrida a la vez. No bloqueante.
_lock_logos = threading.Lock()


def directorio() -> str:
    return os.getenv("LOGOS_DIR") or os.path.join(os.path.dirname(DB_PATH), "logos")


def base_valida(ticker_base: str) -> bool:
    return bool(_BASE.fullmatch(ticker_base or ""))


def ruta(ticker_base: str) -> str | None:
    """Ruta del archivo del logo si existe, o `None`. Sólo para una base con forma válida."""
    if not base_valida(ticker_base):
        return None
    archivo = os.path.join(directorio(), f"{ticker_base}.png")
    return archivo if os.path.isfile(archivo) else None


def dominio_de(website: str | None) -> str | None:
    """El dominio público de una URL de Yahoo (`https://www.ko.com/x` → `ko.com`), o `None` si no
    parece un dominio que valga la pena consultar (IP, puerto, `localhost`, sin punto)."""
    if not website or not isinstance(website, str):
        return None
    texto = website.strip().lower()
    if "://" not in texto:
        texto = "https://" + texto
    try:
        partes = urlparse(texto)
        host = partes.hostname
        if partes.port is not None or partes.username or partes.password:
            return None
    except ValueError:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    # El TLD alfabético deja afuera las IPs (127.0.0.1) y `localhost` no tiene punto.
    return host if _HOST.fullmatch(host) else None


def _dimensiones_png(datos: bytes) -> tuple[int, int] | None:
    if len(datos) < 24 or not datos.startswith(_PNG) or datos[12:16] != b"IHDR":
        return None
    return int.from_bytes(datos[16:20], "big"), int.from_bytes(datos[20:24], "big")


def es_logo_valido(datos: bytes | None, genericos: set[str] | None = None) -> bool:
    """PNG real, de tamaño razonable y que no sea el icono genérico del servicio."""
    if not datos or len(datos) > MAX_BYTES:
        return False
    dim = _dimensiones_png(datos)
    if dim is None:
        return False
    ancho, alto = dim
    if min(ancho, alto) < MIN_LADO or max(ancho, alto) > MAX_LADO:
        return False
    return not genericos or hashlib.sha1(datos).hexdigest() not in genericos


def _get_bytes(url: str) -> bytes | None:
    """GET de una imagen: el cuerpo si fue 200 y entró en `MAX_BYTES`, si no `None`. Nunca lanza."""
    try:
        with httpx.Client(
            trust_env=True, timeout=TIMEOUT_SEG, headers={"User-Agent": USER_AGENT},
            follow_redirects=True, max_redirects=MAX_REDIRECCIONES,
        ) as cliente:
            with cliente.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                cuerpo = bytearray()
                for trozo in resp.iter_bytes():
                    cuerpo.extend(trozo)
                    if len(cuerpo) > MAX_BYTES:
                        return None
                return bytes(cuerpo)
    except Exception as exc:
        logger.debug("logos: falló GET %s: %s", url, exc)
        return None


def firmas_genericas() -> set[str]:
    """Huella del icono que el servicio de favicons devuelve para un dominio que no conoce."""
    datos = _get_bytes(_URL_FAVICON.format(dominio=_DOMINIO_INEXISTENTE))
    return {hashlib.sha1(datos).hexdigest()} if datos else set()


def buscar_logo(dominio: str, genericos: set[str]) -> bytes | None:
    for plantilla in (_URL_FAVICON, _URL_APPLE):
        datos = _get_bytes(plantilla.format(dominio=dominio))
        if es_logo_valido(datos, genericos):
            return datos
    return None


# ---------------------------------------------------------------------------------------------
# Qué dominios hay
# ---------------------------------------------------------------------------------------------

def dominios_por_emisor(db: Session) -> dict[str, str]:
    """`{ticker_base: dominio}` para los emisores con clasificación ok cuyo último snapshot trae
    `website`. Dos bases que comparten símbolo de Yahoo (`PETR3`/`PBR`) comparten dominio."""
    ultimos = (
        db.query(FundamentalesSnapshot.simbolo_yahoo, func.max(FundamentalesSnapshot.fecha).label("f"))
        .group_by(FundamentalesSnapshot.simbolo_yahoo)
        .subquery()
    )
    por_simbolo: dict[str, str] = {}
    for snap in db.query(FundamentalesSnapshot).join(
        ultimos,
        (FundamentalesSnapshot.simbolo_yahoo == ultimos.c.simbolo_yahoo)
        & (FundamentalesSnapshot.fecha == ultimos.c.f),
    ):
        dominio = dominio_de((snap.metricas or {}).get("website"))
        if dominio:
            por_simbolo[snap.simbolo_yahoo] = dominio

    out: dict[str, str] = {}
    for fila in db.query(ClasificacionAuto.ticker_base, ClasificacionAuto.simbolo_yahoo).filter(
        ClasificacionAuto.estado == "ok"
    ):
        dominio = por_simbolo.get(fila.simbolo_yahoo or "")
        if dominio and base_valida(fila.ticker_base):
            out[fila.ticker_base] = dominio
    return out


def con_logo(db: Session) -> set[str]:
    """Los `ticker_base` con logo disponible: estado ok **y** archivo presente."""
    return {
        f.ticker_base
        for f in db.query(LogoEmpresa.ticker_base).filter(LogoEmpresa.estado == "ok")
        if ruta(f.ticker_base)
    }


# ---------------------------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------------------------

def _pendientes(db: Session, dominios: dict[str, str], hoy: date) -> list[tuple[str, str]]:
    """Lo que toca intentar: lo que nunca se intentó, lo que cambió de dominio, y lo fallido o sin
    logo cuyo plazo de reintento ya pasó. Primero lo nuevo."""
    estado = {f.ticker_base: f for f in db.query(LogoEmpresa)}
    nuevos: list[tuple[str, str]] = []
    reintentos: list[tuple[str, str]] = []
    for base, dominio in sorted(dominios.items()):
        fila = estado.get(base)
        if fila is None:
            nuevos.append((base, dominio))
        elif fila.dominio != dominio:
            nuevos.append((base, dominio))
        elif fila.estado == "ok":
            if not ruta(base):  # el archivo se perdió (volumen nuevo): bajarlo de nuevo
                reintentos.append((base, dominio))
        elif fila.proximo_intento is None or fila.proximo_intento <= hoy:
            reintentos.append((base, dominio))
    return nuevos + reintentos


def _guardar_archivo(base: str, datos: bytes) -> None:
    os.makedirs(directorio(), exist_ok=True)
    destino = os.path.join(directorio(), f"{base}.png")
    temporal = f"{destino}.tmp"
    with open(temporal, "wb") as f:
        f.write(datos)
    os.replace(temporal, destino)  # atómico: nunca se sirve un archivo a medio escribir


def correr(db: Session, max_por_corrida: int | None = None) -> dict:
    """Una corrida: baja los logos pendientes (hasta el tope) y registra el resultado. Hace commit.
    Nunca lanza por red."""
    if not use_external_apis():
        return {"resultado": "sin_fuentes", "intentados": 0, "ok": 0}
    if not _lock_logos.acquire(blocking=False):
        return {"resultado": "en_curso", "intentados": 0, "ok": 0}
    try:
        return _correr(db, max_por_corrida)
    finally:
        _lock_logos.release()


def _correr(db: Session, max_por_corrida: int | None) -> dict:
    tope = max_por_corrida if max_por_corrida is not None else int(
        (os.getenv("LOGOS_MAX_POR_CORRIDA") or "").strip() or MAX_POR_CORRIDA_DEFAULT
    )
    hoy = date.today()

    # -- 1. Lectura (corta) --
    dominios = dominios_por_emisor(db)
    pendientes = _pendientes(db, dominios, hoy)[:tope]
    previos = {f.ticker_base: f.intentos for f in db.query(LogoEmpresa)}
    db.rollback()
    if not pendientes:
        return {"resultado": "ok", "intentados": 0, "ok": 0}

    # -- 2. Red (sin lock) --
    genericos = firmas_genericas()
    resultados: list[tuple[str, str, str]] = []  # (base, dominio, estado)
    for base, dominio in pendientes:
        datos = buscar_logo(dominio, genericos)
        if datos is not None:
            try:
                _guardar_archivo(base, datos)
                resultados.append((base, dominio, "ok"))
                continue
            except OSError as exc:
                logger.warning("logos: no se pudo guardar el logo de %s: %s", base, exc)
                resultados.append((base, dominio, "error"))
                continue
        resultados.append((base, dominio, "sin_logo"))

    # -- 3. Escritura (un solo commit, con el lock del sync) --
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("logos: el sync no soltó el lock en %ds; se descarta el registro", LOCK_ESCRITURA_TIMEOUT_SEG)
        return {"resultado": "lock_ocupado", "intentados": len(resultados), "ok": 0}
    try:
        ahora = datetime.utcnow()
        for base, dominio, estado in resultados:
            fila = db.get(LogoEmpresa, base)
            if fila is None:
                fila = LogoEmpresa(ticker_base=base)
                db.add(fila)
            fila.dominio = dominio
            fila.estado = estado
            fila.actualizado = ahora
            if estado == "ok":
                fila.intentos = 0
                fila.proximo_intento = None
            else:
                fila.intentos = previos.get(base, 0) + 1
                dias = SIN_LOGO_REINTENTO_DIAS if estado == "sin_logo" else min(2 ** fila.intentos, BACKOFF_TOPE_DIAS)
                fila.proximo_intento = hoy + timedelta(days=dias)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()

    ok = sum(1 for _, _, e in resultados if e == "ok")
    logger.info("logos: %d intentados, %d ok, %d sin logo", len(resultados), ok, len(resultados) - ok)
    return {"resultado": "ok", "intentados": len(resultados), "ok": ok}
