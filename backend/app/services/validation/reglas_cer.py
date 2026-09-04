"""Saneamiento de la serie CER.

El CER es un índice de inflación acumulada: sólo se usa como cociente (`CER(hoy)/CER(fecha)`,
ver `_monto_ars_real` en inversiones_analytics.py), así que su base absoluta es irrelevante
**mientras toda la serie comparta una sola base**. El problema real aparece cuando se mezclan
bases: la app arma una única serie con dos orígenes (`fuente='sheet'` y `fuente='api'`) y el
Sheet gana por fecha, de modo que un puñado de filas del Sheet en otra base contamina los
cocientes de todas las fechas vecinas.

Este módulo detecta esas filas por continuidad, no por magnitud: el CER **nunca baja** (es
acumulado) y sube a un ritmo acotado. Un valor que rompe eso no es "un CER raro", es un CER de
otra base o un error de escala, y se descarta para que el lookup con carry-forward de
`_cer_indice` use el último valor bueno de la misma base.
"""
from datetime import date

from .types import ValidationIssue, Severity

# El CER es acumulado: nunca decrece. El epsilon absorbe redondeos de la fuente.
RATIO_MIN = 0.999
# Techo de crecimiento diario. El máximo real observado en la serie de la API (2016-2026, con
# la inflación de 2024 adentro) es 3,73% en un día: 5% deja margen sin dejar pasar un cambio
# de base (los observados van de 2,5x a 1000x).
TASA_DIARIA_MAX = 0.05


def _limite_superior(dias: int) -> float:
    return (1 + TASA_DIARIA_MAX) ** max(dias, 1)


def _es_continuo(v0: float, f0: date, v1: float, f1: date) -> bool:
    """¿`v1` puede seguir a `v0` dentro de la misma serie de CER?"""
    if v0 <= 0:
        return False
    ratio = v1 / v0
    return RATIO_MIN <= ratio <= _limite_superior((f1 - f0).days)


def _indice_ancla(serie: list[tuple[date, float]]) -> int:
    """Primer punto que empalma con el siguiente: ahí arranca la base de referencia.

    No se ancla ciegamente en `serie[0]`: si el valor más viejo fuera el erróneo, el recorrido
    descartaría la serie entera midiéndola contra una base equivocada. Dos puntos consecutivos
    que empalman ya no pueden ser ambos un outlier aislado.
    """
    for i in range(len(serie) - 1):
        if _es_continuo(serie[i][1], serie[i][0], serie[i + 1][1], serie[i + 1][0]):
            return i
    return 0


def detectar_cer_fuera_de_serie(
    serie: list[tuple[date, float]],
) -> tuple[set[date], list[ValidationIssue]]:
    """Fechas cuyo CER no pertenece a la base del resto de la serie.

    `serie` son pares (fecha, valor) ordenados por fecha. Devuelve las fechas a descartar y las
    advertencias para Calidad de Datos, para que el problema se vea y se pueda corregir en el
    Sheet en vez de quedar enterrado en un número raro.
    """
    if len(serie) < 3:
        return set(), []

    ancla_ini = _indice_ancla(serie)
    descartadas: set[date] = set()
    issues: list[ValidationIssue] = []

    def _descartar(i: int, referencia: tuple[date, float]) -> None:
        fecha, valor = serie[i]
        f_ref, v_ref = referencia
        descartadas.add(fecha)
        issues.append(ValidationIssue(
            tab="CER/MEP", regla="cer_fuera_de_serie",
            mensaje=(
                f"CER de {fecha.isoformat()} ({valor:g}) no sigue la serie: "
                f"el valor de {f_ref.isoformat()} es {v_ref:g}"
            ),
            impacto="Se descartó ese CER y se usa el último valor válido (carry-forward)",
            severidad=Severity.ADVERTENCIA,
        ))

    # Se recorre hacia adelante y hacia atrás desde el ancla. En ambos sentidos el ancla NO se
    # mueve cuando un punto se descarta: si se moviera, el outlier pasaría a ser la referencia y
    # arrastraría consigo a todo lo que sigue.
    ancla = serie[ancla_ini]
    for i in range(ancla_ini + 1, len(serie)):
        if _es_continuo(ancla[1], ancla[0], serie[i][1], serie[i][0]):
            ancla = serie[i]
        else:
            _descartar(i, ancla)

    ancla = serie[ancla_ini]
    for i in range(ancla_ini - 1, -1, -1):
        if _es_continuo(serie[i][1], serie[i][0], ancla[1], ancla[0]):
            ancla = serie[i]
        else:
            _descartar(i, ancla)

    return descartadas, issues
