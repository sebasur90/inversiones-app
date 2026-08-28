"""Integración con APIs de mercado gratuitas para completar datos que hoy se cargan a mano.

Todo lo de este paquete es "best effort": cualquier falla de red (proxy, timeout, API caída)
se traga y se reporta como advertencia de calidad de datos, nunca interrumpe el sync. El Sheet
siempre tiene prioridad — estas funciones sólo se usan para completar huecos.

Activado por la variable de entorno USE_EXTERNAL_APIS (ver `use_external_apis()`).
"""
from .client import use_external_apis

__all__ = ["use_external_apis"]
