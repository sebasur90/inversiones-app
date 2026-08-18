"""Motor puro para calcular el valor "sombra" de inversiones crecidas por un benchmark.

Sin dependencias de `Session`/DB: recibe series de niveles y flujos de caja, computa
el valor hipotético (shadow value) que esos flujos habrían alcanzado si hubieran sido
invertidos en la fuente (benchmark/índice) en lugar de en la cartera real.

Esto permite cuantificar el "costo de oportunidad" en dinero: valor_actual - valor_shadow.
"""
import bisect
from datetime import date


def valor_shadow(
    flujos: list[tuple[date, float]],
    serie_niveles: list[tuple[date, float]],
    hasta: date
) -> float | None:
    """Calcula el valor "sombra" de una serie de flujos de caja invertidos en un benchmark.

    Por cada flujo en su fecha, busca el nivel del benchmark en esa fecha y en `hasta`,
    crece el monto (con signo invertido: una compra `-monto` se trata como `+monto` invertido)
    por la razón de crecimiento (nivel_final / nivel_fecha), y suma todos los crecimientos.

    Args:
        flujos: lista de (fecha, monto) donde monto < 0 = compra (cash out), monto > 0 = venta/ingreso
        serie_niveles: lista de (fecha, valor_nivel) ordenada cronológicamente (e.g., precios históricos)
        hasta: fecha de valuación final (típicamente hoy)

    Returns:
        float: valor total sombra en la moneda de la serie; None si la serie no cubre todas las fechas
               de flujo (el flujo más antiguo es anterior al primer dato de la serie).

    Ejemplo:
        flujos = [(2026-01-15, -1000), (2026-02-20, +500)]  # Compré $1000, vendí $500
        serie = [(2026-01-10, 100), (2026-01-20, 110), (2026-02-25, 115)]
        hasta = 2026-02-28
        → -1000 * (115 / 110) + 500 * (115 / 115) = -1000 * 1.045 + 500 * 1.0 = ...
    """
    if not flujos or not serie_niveles:
        return 0.0

    fechas_serie = [f[0] for f in serie_niveles]
    nivel_final_idx = bisect.bisect_right(fechas_serie, hasta) - 1

    if nivel_final_idx < 0:
        return None  # `hasta` está antes de todos los datos de la serie

    nivel_final = serie_niveles[nivel_final_idx][1]
    if nivel_final == 0:
        return None

    valor_total = 0.0
    for flujo_fecha, monto in flujos:
        # Buscar el nivel en la fecha del flujo (carry-forward: último valor conocido <= fecha)
        nivel_flujo_idx = bisect.bisect_right(fechas_serie, flujo_fecha) - 1

        if nivel_flujo_idx < 0:
            # El flujo es anterior a todos los datos de la serie — no se puede valuar
            return None

        nivel_flujo = serie_niveles[nivel_flujo_idx][1]
        if nivel_flujo == 0:
            return None

        # Invertir el signo del monto: compra (-) se trata como inversión (+),
        # venta (+) se trata como retiro (negativo en el shadow crecido)
        monto_invertido = -monto
        crecimiento_ratio = nivel_final / nivel_flujo
        valor_total += monto_invertido * crecimiento_ratio

    return valor_total
