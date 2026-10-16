"""Lectura del seed versionado de clasificación (`catalogos/clasificacion_seed.json`).

Mismo esquema de ubicación que `catalogo_instrumentos._catalogo_path`: override por entorno, y si
no, `catalogos/` montado read-only en el contenedor o en la raíz del repo. Un seed ausente o roto
equivale a uno vacío: la clasificación sigue funcionando con Yahoo, el Sheet y las correcciones
manuales.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, float], dict] = {}

_VACIO = {"variantes": {}, "simbolos_yahoo": {}, "exposicion": {}}


def _seed_path() -> str:
    override = os.getenv("CLASIFICACION_SEED_FILE")
    if override:
        return override
    base = os.path.dirname(__file__)
    candidatos = (
        os.path.join(base, "..", "..", "catalogos", "clasificacion_seed.json"),
        os.path.join(base, "..", "..", "..", "catalogos", "clasificacion_seed.json"),
    )
    for ruta in candidatos:
        if os.path.exists(ruta):
            return ruta
    return candidatos[-1]


def _sin_doc(d) -> dict:
    """Saca las claves `_doc` (comentarios del JSON) y pasa las claves a mayúsculas."""
    if not isinstance(d, dict):
        return {}
    return {str(k).upper(): v for k, v in d.items() if not str(k).startswith("_")}


def cargar_seed() -> dict:
    """`{"variantes": {...}, "simbolos_yahoo": {...}, "exposicion": {ticker: {campo: valor}}}`."""
    ruta = _seed_path()
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        return dict(_VACIO)
    clave = (ruta, mtime)
    if clave in _cache:
        return _cache[clave]
    try:
        with open(ruta, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("clasificacion_seed: no se pudo leer %s: %s", ruta, exc)
        return dict(_VACIO)

    seed = {
        "variantes": {k: str(v).upper() for k, v in _sin_doc(data.get("variantes")).items()},
        "simbolos_yahoo": {k: str(v).upper() for k, v in _sin_doc(data.get("simbolos_yahoo")).items()},
        "exposicion": {
            k: {c: v for c, v in campos.items() if not c.startswith("_")}
            for k, campos in _sin_doc(data.get("exposicion")).items()
            if isinstance(campos, dict)
        },
    }
    _cache.clear()
    _cache[clave] = seed
    return seed
