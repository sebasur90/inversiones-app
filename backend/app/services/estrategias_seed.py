"""Siembra del catálogo de presets como estrategias guardadas.

Los presets de `estrategia_engine.PRESETS` viven en código y sólo se ofrecen como plantilla en el
editor: hasta que alguien las guarda, el screener y las señales de la watchlist no las ven (ambos
recorren `estrategias_tecnicas`). Este módulo las materializa en la tabla, con `ticker=None`
(reusables sobre todo el universo) y `tipo_preset` = slug del preset, que es lo que después enlaza
cada estrategia guardada con su ficha explicativa en el front.

**Dos modos, y la diferencia importa**:

- `forzar=False` (el del arranque, `database.init_db`): sólo agrega las que faltan por nombre.
  Un `docker compose up` no puede pisar los ajustes que el usuario le hizo a una estrategia
  sembrada — si le bajó el stop loss a "Cruce de medias 50/200", eso es suyo.
- `forzar=True` (el del endpoint "restaurar recomendadas"): reescribe la definición de las que ya
  existen, volviéndolas al preset de fábrica. Es una acción explícita del usuario.

En ambos casos la identidad es el **nombre normalizado** (`estrategias_analytics.normalizar_nombre`),
no el `tipo_preset`: si el usuario ya tenía una estrategia propia llamada "Cruce de MACD", la
siembra la reconoce como la misma en vez de dejar dos entradas con el mismo texto en el selector.
"""
from sqlalchemy.orm import Session

from ..database import EstrategiaTecnica
from . import estrategias_analytics
from .estrategia_engine import PRESETS


def _descripcion(espec) -> str:
    return f"Estrategia del catálogo ({espec.categoria})."


def sembrar_presets(db: Session, forzar: bool = False) -> dict:
    """Materializa `PRESETS` en `estrategias_tecnicas`. Devuelve el recuento por acción."""
    creadas = actualizadas = sin_cambios = 0

    for slug, espec in PRESETS.items():
        existente = estrategias_analytics.buscar_por_nombre(espec.etiqueta, db)
        if existente is not None and not forzar:
            sin_cambios += 1
            continue

        _, fue_creada = estrategias_analytics.guardar_por_nombre(
            nombre=espec.etiqueta,
            definicion=espec.definicion,
            db=db,
            descripcion=_descripcion(espec),
            ticker=None,
            tipo_preset=slug,
            variante="local",
        )
        if fue_creada:
            creadas += 1
        else:
            actualizadas += 1

    return {"creadas": creadas, "actualizadas": actualizadas, "sin_cambios": sin_cambios}


def deduplicar_por_nombre(db: Session) -> int:
    """Deja una sola fila por nombre normalizado (la de `id` más alto, la más reciente).

    Paso defensivo de arranque para las bases creadas antes de que el nombre identificara a la
    estrategia: sin esto, los duplicados viejos seguirían apareciendo dos veces en el selector y
    el screener los correría dos veces. Devuelve cuántas filas borró.
    """
    vistos: dict[str, EstrategiaTecnica] = {}
    a_borrar: list[EstrategiaTecnica] = []

    for e in db.query(EstrategiaTecnica).order_by(EstrategiaTecnica.id).all():
        clave = estrategias_analytics.normalizar_nombre(e.nombre)
        previa = vistos.get(clave)
        if previa is not None:
            a_borrar.append(previa)
        vistos[clave] = e

    for e in a_borrar:
        db.delete(e)
    if a_borrar:
        db.commit()
    return len(a_borrar)
