"""Tasas de interés del Tesoro de EE.UU.: nivel, cambios en puntos porcentuales y pendiente de la curva. Puro.

Una tasa es un **nivel en % anual**, no un precio: no se calcula «rendimiento» sobre ella (de 0,1 % a 0,2 % no se
«duplicó» nada que importe) sino su **diferencia en puntos porcentuales (pp)**. Tampoco se descartan los ceros: una tasa
puede valer 0. Como en el resto del módulo, un dato que falta se dice, no se completa.

La pendiente de la curva es la tasa larga menos la corta **en la misma fecha**. Cuando es negativa (curva invertida) las
tasas cortas superan a las largas; es un hecho de los datos, no un pronóstico.
"""
from __future__ import annotations

from datetime import date

from . import ciclos_engine as eng

HORIZONTES = {"1M": 1, "3M": 3, "6M": 6, "1A": 12}
#: Tolerancia (días) para tomar el dato de una fecha: igual que los rendimientos del resto del módulo.
TOLERANCIA_DIAS = eng.TOLERANCIA_DIAS
#: Tolerancia para alinear dos tasas en la misma semana (viernes).
TOLERANCIA_SEMANAL = 3
DIAS_DESACTUALIZADA = eng.DIAS_DESACTUALIZADO


def nivel_actual(serie: eng.Serie, hoy: date) -> dict:
    """Último nivel, su fecha y si está desactualizado (más de `DIAS_DESACTUALIZADA` días antes de `hoy`)."""
    if not serie:
        return {"nivel": None, "fecha": None, "desactualizada": False}
    fecha, nivel = serie[-1]
    return {"nivel": nivel, "fecha": fecha, "desactualizada": (hoy - fecha).days > DIAS_DESACTUALIZADA}


def cambio_pp(serie: eng.Serie, desde: date, hasta: date) -> tuple[float | None, str | None]:
    """`(cambio en pp, motivo)` entre dos fechas objetivo. `None` si la serie empieza después o no hay dato cerca."""
    if not serie:
        return None, "sin datos"
    fechas = [f for f, _ in serie]
    cierres = [v for _, v in serie]
    if fechas[0] > desde:
        return None, "sin datos suficientes"
    c0 = eng.cierre_en(fechas, cierres, desde, TOLERANCIA_DIAS)
    c1 = eng.cierre_en(fechas, cierres, hasta, TOLERANCIA_DIAS)
    if c0 is None or c1 is None:
        return None, "sin dato cerca de la fecha"
    return c1 - c0, None


def cambios(serie: eng.Serie, hasta: date, horizontes: dict[str, int] | None = None) -> dict[str, dict]:
    out = {}
    for nombre, meses in (horizontes or HORIZONTES).items():
        desde = eng.restar_meses(hasta, meses)
        valor, motivo = cambio_pp(serie, desde, hasta)
        out[nombre] = {"pp": valor, "desde": desde, "hasta": hasta, "motivo": motivo}
    return out


def valor_en(serie: eng.Serie, fecha: date, tolerancia: int = TOLERANCIA_SEMANAL) -> float | None:
    if not serie:
        return None
    return eng.cierre_en([f for f, _ in serie], [v for _, v in serie], fecha, tolerancia)


def pendiente(larga: eng.Serie, corta: eng.Serie, desde: date, hasta: date) -> eng.Serie:
    """`larga − corta` (pp) en cada viernes en que las dos tienen dato. Un viernes en que falta alguna no aparece."""
    out = []
    for viernes in eng.grilla_semanal(desde, hasta):
        a, b = valor_en(larga, viernes), valor_en(corta, viernes)
        if a is not None and b is not None:
            out.append((viernes, a - b))
    return out


def filas_semanales(series: dict[str, eng.Serie], desde: date, hasta: date) -> list[dict]:
    """Una fila por viernes con el nivel de cada serie (`None` donde no hay dato cerca)."""
    filas = []
    for viernes in eng.grilla_semanal(desde, hasta):
        fila: dict = {"fecha": viernes}
        for k, serie in series.items():
            fila[k] = valor_en(serie, viernes)
        if any(fila[k] is not None for k in series):
            filas.append(fila)
    return filas


def resumen_pendiente(serie_pendiente: eng.Serie, hoy: date) -> dict:
    """Valor actual de la pendiente, si está invertida y cuántas de las últimas 52 semanas lo estuvo."""
    if not serie_pendiente:
        return {"valor_pp": None, "fecha": None, "invertida": None, "desactualizada": False, "semanas_invertida_52": None, "semanas_52": 0}
    fecha, valor = serie_pendiente[-1]
    ultimas = [v for f, v in serie_pendiente if (fecha - f).days < 364]
    return {
        "valor_pp": valor, "fecha": fecha, "invertida": valor < 0,
        "desactualizada": (hoy - fecha).days > DIAS_DESACTUALIZADA,
        "semanas_invertida_52": sum(1 for v in ultimas if v < 0), "semanas_52": len(ultimas),
    }
