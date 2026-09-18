"""Ritmo de aportes: arma la serie mensual desde los movimientos y delega en `aportes_engine`.

La pantalla es sólo USD a propósito: comparar meses en ARS nominal entre años mide inflación,
no ritmo de ahorro.
"""
from datetime import date

from sqlalchemy.orm import Session

from . import aportes_engine
from .cache import cache_por_sync
from .inversiones_analytics import _movimientos_ordenados, serie_mensual_aportes


@cache_por_sync
def get_ritmo_aportes(cartera: str | None, db: Session) -> dict:
    """`cartera=None` = consolidado. La clave del caché incluye la fecha de hoy (ver `cache.py`),
    así la proyección al ritmo diario se recalcula sola cada día."""
    movs = _movimientos_ordenados(db, cartera)
    serie, omitidos = serie_mensual_aportes(movs, db, {})
    resultado = aportes_engine.calcular_ritmo(serie, hoy=date.today())
    resultado["movimientos_omitidos_sin_mep"] = omitidos
    return resultado
