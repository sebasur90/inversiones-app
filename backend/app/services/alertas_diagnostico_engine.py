"""Cuándo avisar de un cambio en el diagnóstico de una empresa. Puro: sin DB ni red.

Un aviso por cambio **confirmado** de estado en una dimensión (valuación, calidad, solidez), con las mismas
ideas de antirrebote que el resto de las alertas pero otra mecánica, porque acá no hay un precio que cruce un
nivel: el diagnóstico se mueve con cada snapshot de fundamentales y puede oscilar en el borde de una banda.

Reglas, en este orden:

1. **Silencio por dato poco confiable**: sin aviso (y sin tocar el estado guardado) si el estado no aplica o
   no tiene datos, si el snapshot es más viejo que `MAX_DIAS_DATO`, o si la confianza global es baja. Anclar
   el estado de referencia en un dato malo produciría un aviso falso el día que mejore.
2. **Primera vez** que se ve un emisor y dimensión: se **siembra** el estado, sin avisar (el usuario no
   necesita un aviso por cada estado de partida).
3. **Cambio de versión de las reglas**: se **re-siembra** sin avisar. Un cambio de reglas no es un cambio de
   la empresa, y avisarlo inundaría el celular cada vez que se afina un umbral.
4. **Mismo estado que el de referencia**: se cancela cualquier cambio pendiente (era ruido).
5. **Estado distinto**: queda **pendiente**; recién se avisa cuando el *mismo* estado nuevo se vuelve a ver en
   un snapshot con **otra `fecha_dato`**. Dos lecturas seguidas del mismo dato no confirman nada.

Al avisar, el estado nuevo pasa a ser el de referencia. Si el aviso está silenciado por configuración el estado
avanza igual (ver `alertas_analytics`): prender el interruptor después no dispara una andanada de cambios viejos.

Ningún texto dice qué hacer con la acción.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from . import alertas_engine as ae

DIMENSIONES_CON_AVISO = ("valuacion", "calidad", "solidez")
NOMBRE_DIMENSION = {"valuacion": "Valuación", "calidad": "Calidad", "solidez": "Solidez financiera"}
MAX_DIAS_DATO = 21                 # mismo criterio que `valuacion_engine.DIAS_DATO_VIEJO`
NIVELES_SIN_ESTADO = frozenset({"no_aplica", "sin_datos"})
CONFIANZAS_QUE_SILENCIAN = frozenset({"baja", "sin_datos"})


@dataclass(frozen=True)
class CandidatoDiagnostico:
    """El estado actual de una dimensión de un emisor, tal como lo dejó la última foto del historial."""
    ticker_base: str
    ticker: str                     # el ticker local que se muestra
    nombre: str
    dimension: str
    estado: str
    nivel: str
    razon: str
    regla: str
    fecha_dato: str                 # ISO
    version: int
    confianza: str
    precio: float | None = None
    moneda: str = ""
    contexto: ae.Contexto = ae.Contexto()

    @property
    def clave(self) -> tuple[str, str]:
        return (self.ticker_base, self.dimension)


@dataclass(frozen=True)
class EstadoAlerta:
    """Lo que se recuerda de una `(emisor, dimensión)` entre corridas."""
    estado_base: str | None = None
    pendiente: str | None = None
    pendiente_fecha_dato: str | None = None
    version: int | None = None


@dataclass
class DecisionDiagnostico:
    a_emitir: list[ae.Alerta] = field(default_factory=list)
    #: Estado a persistir por clave. Sólo las que cambian: lo que no aparece no se toca.
    nuevos: dict[tuple[str, str], EstadoAlerta] = field(default_factory=dict)
    silenciadas_por_dato: int = 0
    sembradas: int = 0
    pendientes: int = 0


def _dias(fecha_iso: str, hoy: date) -> int | None:
    try:
        return (hoy - date.fromisoformat(fecha_iso)).days
    except (TypeError, ValueError):
        return None


def evaluar_diagnosticos(
    candidatos: list[CandidatoDiagnostico],
    guardados: dict[tuple[str, str], EstadoAlerta],
    hoy: date,
    max_dias: int = MAX_DIAS_DATO,
) -> DecisionDiagnostico:
    """Qué avisar y qué estado guardar. Determinista: no depende del orden de `candidatos`."""
    decision = DecisionDiagnostico()
    for c in sorted(candidatos, key=lambda x: x.clave):
        if c.dimension not in DIMENSIONES_CON_AVISO:
            continue
        dias = _dias(c.fecha_dato, hoy)
        if (c.nivel in NIVELES_SIN_ESTADO or c.confianza in CONFIANZAS_QUE_SILENCIAN
                or dias is None or dias > max_dias or dias < 0):
            decision.silenciadas_por_dato += 1
            continue

        previo = guardados.get(c.clave)
        if previo is None or previo.estado_base is None or previo.version != c.version:
            # Primera vez, o las reglas cambiaron: se toma el estado actual como referencia, sin avisar.
            decision.nuevos[c.clave] = EstadoAlerta(c.estado, None, None, c.version)
            decision.sembradas += 1
            continue

        if c.estado == previo.estado_base:
            if previo.pendiente is not None:
                decision.nuevos[c.clave] = replace(previo, pendiente=None, pendiente_fecha_dato=None)
            continue

        if previo.pendiente != c.estado:
            decision.nuevos[c.clave] = replace(previo, pendiente=c.estado, pendiente_fecha_dato=c.fecha_dato)
            decision.pendientes += 1
            continue

        if previo.pendiente_fecha_dato == c.fecha_dato:
            continue                # la misma lectura del mismo snapshot: todavía no confirma nada

        decision.a_emitir.append(_alerta(c, previo.estado_base))
        decision.nuevos[c.clave] = EstadoAlerta(c.estado, None, None, c.version)
    return decision


def _alerta(c: CandidatoDiagnostico, estado_anterior: str) -> ae.Alerta:
    contexto = replace(
        c.contexto,
        diag_dimension=c.dimension,
        diag_nombre_dimension=NOMBRE_DIMENSION.get(c.dimension, c.dimension),
        diag_de=estado_anterior, diag_a=c.estado,
        diag_razon=c.razon or None, diag_regla=c.regla or None,
        diag_fecha_dato=c.fecha_dato, diag_version=c.version,
    )
    return ae.Alerta(
        ticker=c.ticker_base, nombre=c.nombre or c.ticker_base, tipo=ae.tipo_diagnostico(c.dimension),
        cartera=ae.SIN_CARTERA, nivel=None, precio=c.precio if c.precio is not None else 0.0,
        moneda=c.moneda, contexto=contexto,
    )
