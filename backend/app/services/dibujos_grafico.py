"""Dibujos manuales sobre el gráfico técnico: línea horizontal, línea de tendencia y Fibonacci.

Ver `database.DibujoGrafico` para el modelo. Acá viven la validación (en un solo lugar, con un
código de error por regla) y el CRUD. Lo que se dibuja y se toca es del frontend; el servidor
sólo guarda los anclajes `(fecha, precio)`.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from ..database import DibujoGrafico

TIPO_HORIZONTAL, TIPO_TENDENCIA, TIPO_FIBONACCI = "horizontal", "tendencia", "fibonacci"
TIPOS = (TIPO_HORIZONTAL, TIPO_TENDENCIA, TIPO_FIBONACCI)
VARIANTES = ("local", "subyacente")
#: Tipos que necesitan dos puntos.
DE_DOS_PUNTOS = (TIPO_TENDENCIA, TIPO_FIBONACCI)

COLOR_POR_TIPO = {TIPO_HORIZONTAL: "#fbbf24", TIPO_TENDENCIA: "#38bdf8", TIPO_FIBONACCI: "#c084fc"}
MAX_POR_TICKER = 50
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

MENSAJE_ERROR = {
    "tipo_invalido": "El tipo de dibujo tiene que ser 'horizontal', 'tendencia' o 'fibonacci'",
    "variante_invalida": "La variante tiene que ser 'local' o 'subyacente'",
    "precio_invalido": "Los precios tienen que ser mayores que cero",
    "falta_segundo_punto": "La línea de tendencia y el Fibonacci necesitan dos puntos",
    "segundo_punto_sobra": "La línea horizontal tiene un solo punto",
    "mismo_dia": "Los dos puntos tienen que ser de días distintos",
    "mismo_precio": "Los dos puntos del Fibonacci tienen que tener precios distintos",
    "color_invalido": "El color tiene que ser un hexadecimal '#rrggbb'",
    "demasiados": f"Máximo {MAX_POR_TICKER} dibujos por ticker: borrá alguno antes de agregar otro",
}


def validar(datos: dict) -> str | None:
    """Código de error de `MENSAJE_ERROR`, o None si el dibujo es válido."""
    tipo = datos.get("tipo")
    if tipo not in TIPOS:
        return "tipo_invalido"
    if datos.get("variante") not in VARIANTES:
        return "variante_invalida"
    color = datos.get("color")
    if color is not None and not _COLOR_RE.match(color):
        return "color_invalido"
    precio1, precio2 = datos.get("precio1"), datos.get("precio2")
    if precio1 is None or not precio1 > 0 or (precio2 is not None and not precio2 > 0):
        return "precio_invalido"
    tiene_segundo = datos.get("fecha2") is not None or precio2 is not None
    if tipo in DE_DOS_PUNTOS:
        if datos.get("fecha2") is None or precio2 is None:
            return "falta_segundo_punto"
        if datos["fecha2"] == datos["fecha1"]:
            return "mismo_dia"
        if tipo == TIPO_FIBONACCI and precio2 == precio1:
            return "mismo_precio"
    elif tiene_segundo:
        return "segundo_punto_sobra"
    return None


def listar(db: Session, ticker: str, variante: str | None = None) -> list[DibujoGrafico]:
    q = db.query(DibujoGrafico).filter(DibujoGrafico.ticker == ticker)
    if variante is not None:
        q = q.filter(DibujoGrafico.variante == variante)
    return q.order_by(DibujoGrafico.id).all()


def obtener(db: Session, ticker: str, dibujo_id: int) -> DibujoGrafico | None:
    return db.query(DibujoGrafico).filter(
        DibujoGrafico.id == dibujo_id, DibujoGrafico.ticker == ticker,
    ).first()


def _aplicar(fila: DibujoGrafico, datos: dict) -> None:
    fila.variante = datos["variante"]
    fila.tipo = datos["tipo"]
    fila.fecha1, fila.precio1 = datos["fecha1"], datos["precio1"]
    fila.fecha2, fila.precio2 = datos.get("fecha2"), datos.get("precio2")
    fila.color = datos.get("color") or COLOR_POR_TIPO[datos["tipo"]]


def crear(db: Session, ticker: str, datos: dict) -> tuple[DibujoGrafico | None, str | None]:
    """`(fila, None)` o `(None, codigo_de_error)`. Commitea."""
    error = validar(datos)
    if error is None and db.query(DibujoGrafico).filter(DibujoGrafico.ticker == ticker).count() >= MAX_POR_TICKER:
        error = "demasiados"
    if error:
        return None, error
    fila = DibujoGrafico(ticker=ticker, fecha_creacion=datetime.utcnow())
    _aplicar(fila, datos)
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila, None


def reemplazar(db: Session, fila: DibujoGrafico, datos: dict) -> str | None:
    """Reemplaza los puntos, el tipo y el color de un dibujo existente. Commitea."""
    error = validar(datos)
    if error:
        return error
    _aplicar(fila, datos)
    db.commit()
    db.refresh(fila)
    return None


def borrar(db: Session, fila: DibujoGrafico) -> None:
    db.delete(fila)
    db.commit()


def a_dict(fila: DibujoGrafico) -> dict:
    return {
        "id": fila.id, "ticker": fila.ticker, "variante": fila.variante, "tipo": fila.tipo,
        "fecha1": fila.fecha1, "precio1": float(fila.precio1),
        "fecha2": fila.fecha2, "precio2": float(fila.precio2) if fila.precio2 is not None else None,
        "color": fila.color,
    }
