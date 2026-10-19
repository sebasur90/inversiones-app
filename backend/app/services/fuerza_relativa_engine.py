"""Motor puro de la fuerza relativa de un activo contra un índice de referencia.

Sin DB ni red. `ratio = cierre_activo / cierre_benchmark`, normalizado a 100 en la primera barra
visible en la que existen los dos: sube cuando el activo le gana al índice y baja cuando le
pierde, sin importar si los dos suben o bajan en términos absolutos.
"""
from __future__ import annotations

from datetime import timedelta

from . import indicadores_engine as ind
from . import intervalos_engine

# Máximo de días de calendario que se arrastra el último cierre del índice a una fecha en la que
# no operó (feriados que no coinciden entre BYMA y Nueva York).
TOLERANCIA_DIAS = 5
PERIODO_SMA = 50


def alinear_benchmark(
    barras: list[ind.Barra], barras_bench: list[ind.Barra], intervalo: str = intervalos_engine.DIARIO,
) -> list[float | None]:
    """Cierre del índice para cada barra de `barras` (misma longitud), o `None` si no hay dato.

    Diario: el cierre de la misma fecha o, si el índice no operó ese día, el último anterior
    (hasta `TOLERANCIA_DIAS`). Semanal o mensual: el cierre de la barra del índice del **mismo
    período**, y no el de la misma fecha: los feriados distintos desfasarían la última rueda de
    cada semana y compararían semanas distintas.
    """
    if not barras_bench:
        return [None] * len(barras)

    if intervalo != intervalos_engine.DIARIO:
        por_periodo = {
            intervalos_engine.clave_periodo(b.fecha, intervalo): b.cierre
            for b in intervalos_engine.agregar(barras_bench, intervalo)
        }
        return [por_periodo.get(intervalos_engine.clave_periodo(b.fecha, intervalo)) for b in barras]

    out: list[float | None] = []
    j = -1  # última barra del índice con fecha <= la de la barra actual
    for b in barras:
        while j + 1 < len(barras_bench) and barras_bench[j + 1].fecha <= b.fecha:
            j += 1
        if j >= 0 and b.fecha - barras_bench[j].fecha <= timedelta(days=TOLERANCIA_DIAS):
            out.append(barras_bench[j].cierre)
        else:
            out.append(None)
    return out


def fuerza_relativa(
    cierres: list[float], cierres_bench: list[float | None], indice_desde: int = 0,
    periodo_sma: int = PERIODO_SMA,
) -> dict[str, list[float | None]]:
    """`{"ratio", "sma"}` de la misma longitud que `cierres`, normalizados a 100 en la primera
    barra desde `indice_desde` en la que existen el activo y el índice. Las barras anteriores
    (el calentamiento de la media) quedan en la misma escala. Sin ninguna barra en común,
    todo `None`."""
    n = len(cierres)
    crudo: list[float | None] = [
        c / b if b is not None and b > 0 and c is not None else None
        for c, b in zip(cierres, cierres_bench)
    ]
    base = next((crudo[i] for i in range(max(0, indice_desde), n) if crudo[i] is not None), None)
    if base is None or base == 0:
        return {"ratio": [None] * n, "sma": [None] * n}
    ratio = [v / base * 100.0 if v is not None else None for v in crudo]
    return {"ratio": ratio, "sma": ind.sma(ratio, periodo_sma)}
