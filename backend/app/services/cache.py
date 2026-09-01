# -*- coding: utf-8 -*-
"""Caché en memoria para los analytics, invalidada por sincronización.

Los datos sólo cambian cuando corre el sync: entre dos syncs, `get_resumen(cartera)` devuelve
exactamente lo mismo aunque recorra todos los movimientos y recalcule XIRR/TWR. La clave
incluye la fecha de hoy y dos marcas de versión, así que la entrada muere sola cuando deja de
ser válida:

- un contador de escrituras, que sube ante cualquier flush/commit — mismo mecanismo que el
  caché de precios de `inversiones_analytics._invalidar_cache_precios`. Es lo que garantiza
  que agregar un precio y volver a valuar en la misma sesión no devuelva el valor viejo;
- el id del último `SyncRun`, que sí es compartido entre procesos: el contador es local, así
  que con más de un worker sería el único que vería el sync de otro;
- la fecha de hoy, porque varios cálculos dependen de `date.today()`.

No hay invalidación explícita que mantener: nadie tiene que acordarse de limpiar nada.
"""
from __future__ import annotations

import functools
import inspect
from collections import OrderedDict
from copy import deepcopy
from datetime import date
from threading import Lock
from typing import Any, Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from ..database import SyncRun

# Cota para que el proceso no crezca sin fin: una entrada por (función, cartera, params) y
# generación. Con ~10 funciones cacheadas y unas pocas carteras alcanza de sobra, y las
# generaciones viejas caen solas por LRU.
MAX_ENTRADAS = 256

_cache: "OrderedDict[tuple, Any]" = OrderedDict()
_lock = Lock()

# Sube ante cualquier escritura en la sesión: ver el listener de abajo.
_version_datos = 0

# Sólo para los tests: cuántas veces se evitó recalcular.
_hits = 0
_misses = 0


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_flush")
def _invalidar_por_escritura(session: Session, flush_context=None) -> None:
    """Cualquier escritura vuelve obsoleto todo lo cacheado.

    No borra el diccionario: sube la versión, y las entradas viejas caen por LRU. Borrarlo
    acá significaría vaciarlo una vez por flush durante un sync, que hace cientos.
    """
    global _version_datos
    _version_datos += 1


def _generacion(db: Session) -> int:
    """Id del último sync. 0 si todavía no corrió ninguno."""
    fila = db.query(SyncRun.id).order_by(SyncRun.id.desc()).first()
    return fila[0] if fila else 0


def _hashable(valor: Any) -> Any:
    """Los params de los analytics son escalares; cualquier otra cosa se cachea por su repr."""
    if isinstance(valor, (str, int, float, bool, type(None), date)):
        return valor
    if isinstance(valor, (list, tuple)):
        return tuple(_hashable(v) for v in valor)
    return repr(valor)


def cache_por_sync(func: Callable) -> Callable:
    """Cachea el resultado hasta el próximo sync (o el próximo día).

    La `Session` se usa para leer la generación pero no forma parte de la clave: dos requests
    distintos traen sesiones distintas y tienen que compartir la entrada.
    """
    firma = inspect.signature(func)
    nombre = f"{func.__module__}.{func.__qualname__}"

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ligados = firma.bind(*args, **kwargs)
        ligados.apply_defaults()

        db = next((v for v in ligados.arguments.values() if isinstance(v, Session)), None)
        if db is None:
            # Sin sesión no hay forma de saber en qué generación estamos: no cachear.
            return func(*args, **kwargs)

        clave = (
            nombre,
            # La conexión forma parte de la clave: en producción es siempre la misma, pero en
            # los tests conviven varias SQLite en memoria, todas sin sync (generación 0), que
            # si no se distinguen comparten entrada.
            id(db.get_bind()),
            _version_datos,
            _generacion(db),
            date.today(),
            tuple(
                (k, _hashable(v))
                for k, v in ligados.arguments.items()
                if not isinstance(v, Session)
            ),
        )

        global _hits, _misses
        with _lock:
            if clave in _cache:
                _cache.move_to_end(clave)
                _hits += 1
                # Copia: si el caller muta el resultado, la entrada cacheada no se corrompe.
                return deepcopy(_cache[clave])

        resultado = func(*args, **kwargs)

        with _lock:
            _misses += 1
            _cache[clave] = deepcopy(resultado)
            while len(_cache) > MAX_ENTRADAS:
                _cache.popitem(last=False)

        return resultado

    wrapper.__wrapped__ = func  # type: ignore[attr-defined]
    return wrapper


def limpiar_cache() -> None:
    """Vacía la caché. Sólo la usan los tests; en producción invalida el id de sync."""
    global _hits, _misses
    with _lock:
        _cache.clear()
        _hits = 0
        _misses = 0


def estadisticas() -> dict:
    with _lock:
        return {"entradas": len(_cache), "hits": _hits, "misses": _misses}
