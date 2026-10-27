"""Proveedores intercambiables del Calendario de eventos. Ver `base.py` para la interfaz común.

`todos()` es el registro: el orquestador (`eventos_sync`) y el estado de fuentes recorren esta lista,
nunca nombran a un proveedor concreto. Agregar uno es escribir su módulo y sumarlo acá.
"""
from .base import ProveedorEventos


def todos() -> list[ProveedorEventos]:
    from .gdelt import Gdelt
    from .importacion import ImportacionArchivos
    from .marketaux import Marketaux
    from .yahoo_resultados import YahooResultados

    return [Marketaux(), YahooResultados(), Gdelt(), ImportacionArchivos()]


def por_nombre(nombre: str) -> ProveedorEventos | None:
    return next((p for p in todos() if p.nombre == nombre), None)
