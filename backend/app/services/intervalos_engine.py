"""Motor puro de intervalos: agrega barras diarias en semanales o mensuales.

Sin DB ni red. Trabaja con `indicadores_engine.Barra`. La fecha de cada barra agregada es la
**última rueda** del período (no el lunes ni el día 1): es la misma fecha en la que cierra el
período y la que usa el resto de la app para ubicar un dato sobre el gráfico.
"""
from __future__ import annotations

from datetime import date

from .indicadores_engine import Barra

DIARIO, SEMANAL, MENSUAL = "D", "S", "M"
INTERVALOS = (DIARIO, SEMANAL, MENSUAL)
# Cuántas ruedas diarias entran, como máximo, en una barra del intervalo (para pedir historia).
FACTOR = {DIARIO: 1, SEMANAL: 5, MENSUAL: 21}


def clave_periodo(fecha: date, intervalo: str) -> tuple:
    """Identifica el período al que pertenece `fecha`: la semana ISO o el mes."""
    if intervalo == SEMANAL:
        iso = fecha.isocalendar()
        return (iso[0], iso[1])
    if intervalo == MENSUAL:
        return (fecha.year, fecha.month)
    return (fecha,)


def _unir(grupo: list[Barra]) -> Barra:
    """Apertura = primera, máximo = máx, mínimo = mín, cierre = último, volumen = suma.

    Si ninguna barra del grupo tiene OHLC (serie de sólo cierres), la agregada tampoco. Si la
    serie es mixta, la barra sin OHLC aporta su cierre como máximo y mínimo.
    """
    primera, ultima = grupo[0], grupo[-1]
    if any(b.maximo is not None and b.minimo is not None for b in grupo):
        maximo = max(b.maximo if b.maximo is not None else b.cierre for b in grupo)
        minimo = min(b.minimo if b.minimo is not None else b.cierre for b in grupo)
        apertura = primera.apertura if primera.apertura is not None else primera.cierre
    else:
        maximo = minimo = apertura = None
    volumenes = [b.volumen for b in grupo if b.volumen is not None]
    return Barra(
        fecha=ultima.fecha, cierre=ultima.cierre, apertura=apertura, maximo=maximo, minimo=minimo,
        volumen=sum(volumenes) if volumenes else None,
    )


def agregar(barras: list[Barra], intervalo: str) -> list[Barra]:
    """Barras agregadas al intervalo (`D` devuelve la misma lista)."""
    if intervalo == DIARIO or not barras:
        return list(barras)
    resultado: list[Barra] = []
    grupo: list[Barra] = []
    clave_actual = None
    for b in barras:
        clave = clave_periodo(b.fecha, intervalo)
        if grupo and clave != clave_actual:
            resultado.append(_unir(grupo))
            grupo = []
        clave_actual = clave
        grupo.append(b)
    resultado.append(_unir(grupo))
    return resultado


def agregar_serie(barras: list[Barra], intervalo: str, indice_desde: int) -> tuple[list[Barra], int]:
    """Agrega y traduce `indice_desde` (índice diario del primer día visible) al de la serie
    agregada: la primera barra visible es la del período que contiene ese día."""
    if intervalo == DIARIO or not barras:
        return list(barras), indice_desde
    agregadas = agregar(barras, intervalo)
    indice_desde = min(max(indice_desde, 0), len(barras) - 1)
    clave = clave_periodo(barras[indice_desde].fecha, intervalo)
    nuevo = next(
        (i for i, b in enumerate(agregadas) if clave_periodo(b.fecha, intervalo) == clave),
        len(agregadas) - 1,
    )
    return agregadas, nuevo
