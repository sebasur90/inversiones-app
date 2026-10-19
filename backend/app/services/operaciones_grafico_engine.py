"""Motor puro de las operaciones propias sobre el gráfico técnico: ciclos de tenencia, ubicación
de un precio pagado sobre la vela de otra serie y costo promedio en términos del gráfico.

Sin DB ni red. Trabaja con objetos que tengan los atributos de `MovimientoInversion`
(`tipo_movimiento`, `cantidad`, `fecha`) y con `Barra` (`fecha`, `cierre`, `maximo`, `minimo`).
El adaptador con la base es `operaciones_grafico`.

Por qué "precio equivalente": un CEDEAR se compra en pesos al precio del CEDEAR, y el gráfico
muestra el subyacente en USD (ajustado por dividendos y splits). No hay serie de CCL ni ratio del
CEDEAR, así que el precio pagado no se puede convertir. Lo que sí se puede es ubicarlo *relativo a
la vela del CEDEAR de ese día* y trasladar esa posición a la vela del subyacente: pagar 1% arriba
del cierre local deja la marca 1% arriba del cierre en USD. El CCL y el ratio entran implícitos.
"""
from __future__ import annotations

from datetime import timedelta

EPS = 1e-9

TIPOS_APERTURA = ("compra",)
TIPOS_CIERRE = ("venta", "amortizacion")
TIPOS_INGRESO = ("dividendo", "cupon")

# Cuánto puede alejarse la barra usada de la fecha de la operación. Cubre fines de semana y los
# feriados que no coinciden entre BYMA y Nueva York.
TOLERANCIA_DIAS = 5

MOTIVO_SIN_VELA_LOCAL = "sin_vela_local"
MOTIVO_RECORTADO = "recortado_al_rango"
MOTIVO_FECHA_CERCANA = "fecha_cercana"
MOTIVO_SIN_TIPO_DE_CAMBIO = "sin_tipo_de_cambio"


def partir_en_ciclos(movs: list) -> list[list]:
    """Parte los movimientos (ya ordenados) en ciclos de tenencia: de 0 a volver a 0.

    Un ciclo abre con la primera compra y cierra cuando la tenencia vuelve a cero. Las ventas se
    topan con la tenencia, igual que en `_recorrer_movs_ticker`. Los ingresos (dividendos, cupones)
    entran al ciclo vigente; si llegan con la tenencia en cero van al último ciclo, y si todavía no
    hubo ninguno se descartan (no hay posición a la que atribuirlos).
    """
    ciclos: list[list] = []
    actual: list | None = None
    tenencia = 0.0

    for mov in movs:
        cantidad = float(mov.cantidad or 0)
        tipo = mov.tipo_movimiento
        if tipo in TIPOS_APERTURA:
            if actual is None:
                actual = []
                ciclos.append(actual)
            actual.append(mov)
            tenencia += cantidad
        elif tipo in TIPOS_CIERRE:
            destino = actual if actual is not None else (ciclos[-1] if ciclos else None)
            if destino is None:
                continue
            destino.append(mov)
            if actual is not None:
                tenencia -= min(cantidad, tenencia) if tenencia > EPS else 0.0
                if tenencia < EPS:
                    tenencia = 0.0
                    actual = None
        elif tipo in TIPOS_INGRESO:
            destino = actual if actual is not None else (ciclos[-1] if ciclos else None)
            if destino is not None:
                destino.append(mov)
    return ciclos


def barra_de_fecha(barras: list, fecha, tolerancia: int = TOLERANCIA_DIAS):
    """Barra de `fecha` o, si no hubo rueda ese día, la primera posterior dentro de la tolerancia.

    Devuelve `(barra, exacta)` o `None`. Una fecha anterior al inicio de la serie queda afuera: el
    gráfico no la muestra. Una operación posterior al último dato (se operó hoy y la serie llega
    a ayer) usa la última barra si está dentro de la tolerancia.
    """
    if not barras or fecha < barras[0].fecha:
        return None
    # Búsqueda binaria de la primera barra con fecha >= `fecha`.
    lo, hi = 0, len(barras)
    while lo < hi:
        medio = (lo + hi) // 2
        if barras[medio].fecha < fecha:
            lo = medio + 1
        else:
            hi = medio
    if lo < len(barras):
        barra = barras[lo]
        if barra.fecha == fecha:
            return barra, True
        if barra.fecha - fecha <= timedelta(days=tolerancia):
            return barra, False
        return None
    ultima = barras[-1]
    if fecha - ultima.fecha <= timedelta(days=tolerancia):
        return ultima, False
    return None


def precio_equivalente(precio_local: float, barra_local, barra_serie) -> tuple[float, bool, str | None]:
    """Ubica `precio_local` sobre `barra_serie` conservando su posición relativa a `barra_local`.

    Devuelve `(precio, aproximado, motivo)`. Sin vela local utilizable la marca va al cierre de la
    serie y queda aproximada. El resultado se recorta al rango de la vela cuando lo hay: la serie
    del subyacente viene ajustada y una marca fuera de [mínimo, máximo] no tendría sentido; si hubo
    que recortar, queda aproximada.
    """
    if barra_local is None or not barra_local.cierre or barra_local.cierre <= 0:
        return barra_serie.cierre, True, MOTIVO_SIN_VELA_LOCAL
    precio = precio_local / barra_local.cierre * barra_serie.cierre
    minimo, maximo = barra_serie.minimo, barra_serie.maximo
    if minimo is not None and maximo is not None:
        if precio < minimo:
            return minimo, True, MOTIVO_RECORTADO
        if precio > maximo:
            return maximo, True, MOTIVO_RECORTADO
    return precio, False, None


def costo_promedio_grafico(compras: list[tuple[float, float | None]]) -> float | None:
    """Promedio ponderado por cantidad de los precios del gráfico de las compras `(cantidad, precio)`.

    Con costo promedio y remoción proporcional al vender, el costo unitario de lo que queda en
    cartera es exactamente el promedio de todas las compras del ciclo. Las compras sin precio en
    el gráfico (anteriores a la serie) no entran.
    """
    total = peso = 0.0
    for cantidad, precio in compras:
        if precio is None or cantidad <= 0:
            continue
        total += cantidad * precio
        peso += cantidad
    return total / peso if peso > EPS else None


def porcentaje(resultado: float | None, base: float | None) -> float | None:
    """Resultado sobre base en puntos porcentuales (5.0 = +5%, como `retorno_neto_pct` del
    backtest), o None si no hay base positiva."""
    if resultado is None or base is None or base <= EPS:
        return None
    return resultado / base * 100.0
