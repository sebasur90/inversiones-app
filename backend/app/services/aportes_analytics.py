"""Ritmo de aportes: arma la serie mensual desde los movimientos y delega en `aportes_engine`.

La pantalla es sólo USD a propósito: comparar meses en ARS nominal entre años mide inflación,
no ritmo de ahorro.

El caché cubre sólo `get_serie_aportes` (recorrer todos los movimientos y resolver el MEP día a
día), que es la parte cara y depende únicamente de los datos sincronizados. El objetivo mensual lo
edita el usuario fuera del sync, así que se lee sin caché y el motor puro —microsegundos sobre unos
cientos de meses— se recalcula en cada request. Así editar la meta se ve al instante sin depender
de que el invalidador por escritura de `cache.py`, que es local al proceso, alcance a todos los
workers.
"""
from datetime import date

from sqlalchemy.orm import Session

from . import aportes_engine, objetivo_aporte_analytics
from .cache import cache_por_sync
from .inversiones_analytics import _movimientos_ordenados, serie_mensual_aportes


@cache_por_sync
def get_serie_aportes(cartera: str | None, db: Session) -> dict:
    """Lo caro y estable entre syncs: `{"serie", "omitidos"}`. `cartera=None` = consolidado."""
    movs = _movimientos_ordenados(db, cartera)
    serie, omitidos = serie_mensual_aportes(movs, db, {})
    return {"serie": serie, "omitidos": omitidos}


def get_ritmo_aportes(cartera: str | None, db: Session) -> dict:
    """`cartera=None` = consolidado. Sin caché a propósito: ver el docstring del módulo."""
    base = get_serie_aportes(cartera, db)
    objetivo = objetivo_aporte_analytics.get_objetivo(cartera, db)
    resultado = aportes_engine.calcular_ritmo(base["serie"], hoy=date.today(), objetivo=objetivo)
    resultado["movimientos_omitidos_sin_mep"] = base["omitidos"]
    return resultado
