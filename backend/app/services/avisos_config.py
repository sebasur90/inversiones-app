"""Qué avisos salen por Telegram: los tres interruptores de nivel y el estado por estrategia.

Separado de `alertas_analytics` (que decide y manda) porque es configuración, no evaluación: la
app la lee y la escribe desde Ajustes, y el job sólo la consulta.

Un tipo de nivel apagado **no deja de seguirse**: `alertas_analytics` guarda igual el cruce y lo
marca como entregado sin mandarlo. Prender el interruptor después no tiene que disparar una
andanada de cruces que ya pasaron.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..database import AjustesAvisos, EstrategiaTecnica
from . import alertas_engine

#: Interruptor de `AjustesAvisos` que gobierna cada tipo de nivel.
CAMPO_POR_TIPO = {
    alertas_engine.TIPO_STOP_LOSS: "avisar_stop_loss",
    alertas_engine.TIPO_OBJETIVO: "avisar_objetivo",
    alertas_engine.TIPO_COMPRA_ZONA: "avisar_compra_zona",
}

_FILA = 1


def obtener(db: Session) -> AjustesAvisos:
    """La fila de ajustes, creándola con los defaults si todavía no existe.

    Se crea al leer y no en una migración de datos para que una DB vieja (o un test con una DB en
    memoria recién hecha) no necesite ningún paso previo.
    """
    fila = db.query(AjustesAvisos).filter(AjustesAvisos.id == _FILA).first()
    if fila is None:
        fila = AjustesAvisos(id=_FILA, fecha_actualizacion=datetime.utcnow())
        db.add(fila)
        db.commit()
        db.refresh(fila)
    return fila


def actualizar(
    db: Session,
    avisar_stop_loss: bool | None = None,
    avisar_objetivo: bool | None = None,
    avisar_compra_zona: bool | None = None,
) -> AjustesAvisos:
    """Cambia los interruptores pasados; `None` es "no tocar"."""
    fila = obtener(db)
    for campo, valor in (
        ("avisar_stop_loss", avisar_stop_loss),
        ("avisar_objetivo", avisar_objetivo),
        ("avisar_compra_zona", avisar_compra_zona),
    ):
        if valor is not None:
            setattr(fila, campo, 1 if valor else 0)
    fila.fecha_actualizacion = datetime.utcnow()
    db.commit()
    db.refresh(fila)
    return fila


def tipos_habilitados(db: Session) -> set[str]:
    """Tipos de nivel que hoy se mandan. Los demás se siguen pero se silencian."""
    fila = obtener(db)
    return {tipo for tipo, campo in CAMPO_POR_TIPO.items() if bool(getattr(fila, campo))}


def lados_por_estrategia(db: Session) -> dict[int, set[str]]:
    """`{estrategia_id: {"compra", "venta"}}` sólo de las estrategias con algo prendido.

    Vacío = ninguna estrategia avisa, y entonces `alertas_analytics` ni calcula señales: correr
    los backtests de todo el universo para después descartarlos sería el costo más caro del job
    a cambio de nada.
    """
    salida: dict[int, set[str]] = {}
    filas = (
        db.query(EstrategiaTecnica)
        .filter(
            (EstrategiaTecnica.notificar_compra == 1)
            | (EstrategiaTecnica.notificar_venta == 1)
        )
        .all()
    )
    for fila in filas:
        lados = set()
        if fila.notificar_compra:
            lados.add(alertas_engine.SENAL_COMPRA)
        if fila.notificar_venta:
            lados.add(alertas_engine.SENAL_VENTA)
        if lados:
            salida[fila.id] = lados
    return salida


def estado(db: Session) -> dict:
    """Lo que consume la pantalla de Ajustes: los tres interruptores y el detalle por estrategia."""
    fila = obtener(db)
    estrategias = (
        db.query(EstrategiaTecnica).order_by(EstrategiaTecnica.nombre).all()
    )
    return {
        "avisar_stop_loss": bool(fila.avisar_stop_loss),
        "avisar_objetivo": bool(fila.avisar_objetivo),
        "avisar_compra_zona": bool(fila.avisar_compra_zona),
        "estrategias": [
            {
                "id": e.id,
                "nombre": e.nombre,
                "ticker": e.ticker,
                "notificar_compra": bool(e.notificar_compra),
                "notificar_venta": bool(e.notificar_venta),
            }
            for e in estrategias
        ],
    }
