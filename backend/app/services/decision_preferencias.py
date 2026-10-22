"""Preferencias de análisis del Centro de Decisiones: horizonte, objetivo, enfoque, tolerancia, moneda,
universo, exclusiones y pesos de las dimensiones.

Una fila única (`DecisionPreferencias`, `id = 1`) con un JSON que se valida acá. Sin fila rigen los
`DEFAULTS`, que son un **punto de partida documentado, no una suposición sobre el usuario**: la tolerancia
al riesgo arranca en `None` ("sin definir") porque la app no tiene ningún dato del que inferirla.

Cada pedido de análisis puede pasar overrides (`combinar`) sin guardarlos: probar "¿y a largo plazo?" no
tiene por qué cambiar la configuración.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..database import DecisionPreferencias
from . import evaluacion_engine as ev

HORIZONTES = ("corto", "mediano", "largo")
OBJETIVOS = ("crecimiento", "valor", "ingresos", "diversificacion")
ENFOQUES = ev.ENFOQUES
TOLERANCIAS = ("baja", "media", "alta")
MONEDAS = ("USD", "ARS")
UNIVERSOS = ("cartera", "watchlist", "catalogo")
CLAVES_EXCLUIR = ("tipos", "sectores", "paises", "tickers")
MAX_EXCLUSIONES = 50

DEFAULTS: dict = {
    "horizonte": "largo",
    "objetivo": "crecimiento",
    "enfoque": "combinado",
    "tolerancia": None,
    "moneda": "USD",
    "universo": "catalogo",
    "excluir": {k: [] for k in CLAVES_EXCLUIR},
    "pesos": None,          # None = los de la tabla `evaluacion_engine.PESOS` para enfoque × horizonte
}

_FILA = 1


def _elegir(valor, opciones: tuple, campo: str, admite_none: bool = False):
    if valor is None and admite_none:
        return None
    if valor not in opciones:
        raise ValueError(f"{campo} debe ser uno de: {', '.join(opciones)}")
    return valor


def _lista_texto(valores, campo: str) -> list[str]:
    if valores is None:
        return []
    if not isinstance(valores, (list, tuple)):
        raise ValueError(f"excluir.{campo} debe ser una lista")
    salida = []
    for v in valores:
        if not isinstance(v, str) or not v.strip() or len(v) > 80:
            raise ValueError(f"excluir.{campo} tiene un valor inválido")
        t = v.strip().upper() if campo == "tickers" else v.strip()
        if t not in salida:
            salida.append(t)
    if len(salida) > MAX_EXCLUSIONES:
        raise ValueError(f"excluir.{campo} admite hasta {MAX_EXCLUSIONES} valores")
    return salida


def normalizar(crudo: dict | None) -> dict:
    """Valida y completa con los defaults. `ValueError` con un mensaje para el usuario si algo no vale."""
    crudo = crudo or {}
    if not isinstance(crudo, dict):
        raise ValueError("las preferencias deben ser un objeto")
    p = {**DEFAULTS, **{k: v for k, v in crudo.items() if k in DEFAULTS}}
    excluir = p.get("excluir") or {}
    if not isinstance(excluir, dict):
        raise ValueError("excluir debe ser un objeto")
    return {
        "horizonte": _elegir(p["horizonte"], HORIZONTES, "horizonte"),
        "objetivo": _elegir(p["objetivo"], OBJETIVOS, "objetivo"),
        "enfoque": _elegir(p["enfoque"], ENFOQUES, "enfoque"),
        "tolerancia": _elegir(p["tolerancia"], TOLERANCIAS, "tolerancia", admite_none=True),
        "moneda": _elegir(p["moneda"], MONEDAS, "moneda"),
        "universo": _elegir(p["universo"], UNIVERSOS, "universo"),
        "excluir": {k: _lista_texto(excluir.get(k), k) for k in CLAVES_EXCLUIR},
        "pesos": ev.normalizar_pesos(p["pesos"]) if p["pesos"] is not None else None,
    }


def leer(db: Session) -> dict:
    fila = db.query(DecisionPreferencias).filter(DecisionPreferencias.id == _FILA).first()
    try:
        return normalizar(fila.preferencias if fila else None)
    except ValueError:   # una fila vieja que ya no valida: rigen los defaults
        return normalizar(None)


def guardar(db: Session, crudo: dict) -> dict:
    prefs = normalizar(crudo)
    fila = db.query(DecisionPreferencias).filter(DecisionPreferencias.id == _FILA).first()
    if fila is None:
        db.add(DecisionPreferencias(id=_FILA, preferencias=prefs, fecha_actualizacion=datetime.utcnow()))
    else:
        fila.preferencias = prefs
        fila.fecha_actualizacion = datetime.utcnow()
    db.commit()
    return prefs


def combinar(db: Session, overrides: dict | None) -> dict:
    """Las guardadas con los overrides del pedido encima (sin guardar)."""
    base = leer(db)
    if not overrides:
        return base
    limpios = {k: v for k, v in overrides.items() if v is not None and k in DEFAULTS}
    return normalizar({**base, **limpios})
