"""Objetivo de aporte mensual: CRUD de la meta de hábito que el usuario fija desde `/aportes`.

Sin `@cache_por_sync` a propósito: son lecturas de una fila y escrituras del usuario. El caché de
`aportes_analytics` cubre la parte cara (recorrer movimientos y resolver el MEP día a día), que no
depende del objetivo; así editar la meta se ve reflejado al instante sin depender de que el
invalidador por escritura de `cache.py` (que es local al proceso) alcance a todos los workers.
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..database import ObjetivoAporteMensual


def _mes_actual(hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    return f"{hoy.year:04d}-{hoy.month:02d}"


def _fila(cartera: str | None, db: Session) -> ObjetivoAporteMensual | None:
    """`cartera=None` = consolidado. SQLite no equipara `= NULL`, hace falta `IS NULL`."""
    q = db.query(ObjetivoAporteMensual)
    if cartera is None:
        q = q.filter(ObjetivoAporteMensual.cartera.is_(None))
    else:
        q = q.filter(ObjetivoAporteMensual.cartera == cartera)
    return q.first()


def get_objetivo(cartera: str | None, db: Session) -> dict | None:
    """Forma plana lista para el motor puro, o `None` si no hay objetivo configurado."""
    fila = _fila(cartera, db)
    if fila is None:
        return None
    return {
        "monto_usd": float(fila.monto_usd),
        "vigente_desde": fila.vigente_desde,
        "retroactivo": bool(fila.retroactivo),
        "fecha_actualizacion": fila.fecha_actualizacion,
    }


def guardar_objetivo(
    cartera: str | None,
    monto_usd: float,
    db: Session,
    retroactivo: bool = False,
    hoy: date | None = None,
) -> dict:
    """Upsert: una sola fila por cartera.

    La unicidad no puede delegarse al `UNIQUE` de la columna porque SQLite considera distintos
    entre sí a los `NULL`, así que dos consolidados pasarían la constraint. Se resuelve acá.

    `vigente_desde` se fija al mes en curso al crear y **no se mueve** al editar el monto: si ya
    venías midiendo desde marzo, cambiar la meta en septiembre no borra ese historial. `retroactivo`
    no lo toca: es un flag aparte que el motor interpreta como "medí desde el primer mes con
    movimientos", así que desmarcarlo recupera la fecha original en vez de perderla.
    """
    ahora = datetime.now()
    fila = _fila(cartera, db)
    if fila is None:
        fila = ObjetivoAporteMensual(
            cartera=cartera,
            monto_usd=monto_usd,
            vigente_desde=_mes_actual(hoy),
            retroactivo=1 if retroactivo else 0,
            fecha_creacion=ahora,
            fecha_actualizacion=ahora,
        )
        db.add(fila)
    else:
        fila.monto_usd = monto_usd
        fila.retroactivo = 1 if retroactivo else 0
        fila.fecha_actualizacion = ahora
    db.commit()
    db.refresh(fila)
    return get_objetivo(cartera, db)  # type: ignore[return-value]


def eliminar_objetivo(cartera: str | None, db: Session) -> bool:
    """`True` si había algo que borrar. Idempotente: borrar dos veces no es un error."""
    fila = _fila(cartera, db)
    if fila is None:
        return False
    db.delete(fila)
    db.commit()
    return True
