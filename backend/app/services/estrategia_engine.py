"""Motor puro de estrategias técnicas: DSL declarativo, evaluación trivaluada y backtest.

Sin dependencias de `Session`/DB/red — recibe `Barra`s ya resueltas por `ohlcv_analytics` (o
por los tests) y un DSL en `dict`, y devuelve `dataclass`s planas. Reusa
`services.indicadores_engine` para los indicadores y `services.risk_engine.calcular_drawdown`
para el drawdown de la curva de equity.

**Lógica trivaluada estricta**: si cualquier operando de una hoja es `None` (warm-up de un
indicador), la hoja es `None`; si cualquier hijo de `y`/`o`/`no` es `None`, el nodo es `None`.
Una estrategia con MM200 simplemente no está definida antes de la barra 200 — la alternativa
(`o` cortocircuitando a `True` con un hijo `None`) daría señales antes de que la estrategia
exista. `compilar().primera_barra_evaluable` se calcula de forma empírica (primer índice sin
`None` en `entrada`/`salida` ya evaluadas), no a partir de una fórmula de warm-up: es exacto,
mientras que sumar warm-ups a mano sólo daría una cota superior.

**Backtest**: long-only, all-in, sin parciales — se evalúa la calidad de la señal, no el sizing.
Máquina de estados `fuera`↔`dentro`; estando dentro se ignora `entrada`. El `precio_ejecucion`
(`"cierre"` o `"apertura_siguiente"` + `demora_barras`) se respeta tanto para la entrada como
para la salida por regla; los stops (stop loss / take profit / trailing) siempre se chequean
intrabar contra `mínimo`/`máximo` (o el cierre, sin OHLC) de la barra en curso — no tiene sentido
demorarlos, es la primera barra en que se cruza el nivel. Si dos stops bajistas (stop loss y
trailing) están activos el mismo día, gana el nivel más alto (es el que el precio cruza primero
al caer); si la apertura gapeó más allá del nivel, se sale a la apertura (criterio conservador).
Comisión por lado, aplicada como resta lineal sobre el retorno (`neto = bruto - 2×comisión` al
cerrar, `bruto - comisión` si la posición queda abierta al final, sólo se pagó la entrada). La
curva de equity se marca a mercado barra a barra mientras hay posición (no sólo al cerrar), así
el drawdown es el real; el salto de la comisión se aplica de una sola vez en la barra de salida.
"""
from __future__ import annotations

import operator
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date

from . import indicadores_engine
from . import risk_engine
from .indicadores_engine import Barra

__all__ = [
    "Barra", "Compilado", "Senal", "Operacion", "ResultadoBacktest",
    "compilar", "backtest", "validar_estrategia", "barras_minimas",
    "PRESETS", "resolver_preset",
]


# ─── Tipos ────────────────────────────────────────────────────────────────────

@dataclass
class Compilado:
    entrada: list           # list[bool | None]
    salida: list             # list[bool | None]
    series: dict             # id -> {salida: list[float | None]}
    primera_barra_evaluable: int | None


@dataclass
class Senal:
    indice: int
    fecha: date
    tipo: str          # "compra" | "venta"
    precio: float
    motivo: str        # "entrada" | "regla_salida" | "stop_loss" | "take_profit" | "trailing_stop" | "max_barras"


@dataclass
class Operacion:
    indice_entrada: int
    indice_salida: int | None
    fecha_entrada: date
    fecha_salida: date | None
    precio_entrada: float
    precio_salida: float | None
    barras: int
    retorno_bruto_pct: float
    retorno_neto_pct: float
    motivo_salida: str | None
    abierta: bool


@dataclass
class ResultadoBacktest:
    senales: list           # list[Senal]
    operaciones: list        # list[Operacion]
    metricas: dict
    curva_equity: list        # list[tuple[date, float]] base 100
    curva_buy_hold: list       # list[tuple[date, float]] base 100
    advertencias: list = field(default_factory=list)


# ─── Operandos ────────────────────────────────────────────────────────────────

_CAMPO_GETTERS = {
    "cierre": lambda b: b.cierre,
    "apertura": lambda b: b.apertura,
    "maximo": lambda b: b.maximo,
    "minimo": lambda b: b.minimo,
    "volumen": lambda b: b.volumen,
}


def _resolver_operando(operando: dict, barras: list[Barra], series: dict) -> list:
    if "ref" in operando:
        serie_dict = series.get(operando["ref"])
        if serie_dict is None:
            raise ValueError(f"referencia desconocida: {operando['ref']!r}")
        salida = operando.get("salida", "valor")
        if salida not in serie_dict:
            raise ValueError(f"salida desconocida {salida!r} para {operando['ref']!r}")
        return serie_dict[salida]
    if "const" in operando:
        c = operando["const"]
        return [c] * len(barras)
    if "campo" in operando:
        getter = _CAMPO_GETTERS.get(operando["campo"])
        if getter is None:
            raise ValueError(f"campo desconocido: {operando['campo']!r}")
        return [getter(b) for b in barras]
    raise ValueError(f"operando inválido: {operando!r}")


# ─── Hojas trivaluadas ────────────────────────────────────────────────────────

_COMPARADORES = {
    "mayor": operator.gt,
    "menor": operator.lt,
    "mayor_igual": operator.ge,
    "menor_igual": operator.le,
}


def _comparar(izq: list, der: list, cmp) -> list:
    return [cmp(a, b) if a is not None and b is not None else None for a, b in zip(izq, der)]


def _cruce_arriba(izq: list, der: list) -> list:
    n = len(izq)
    out: list = [None] * n
    for i in range(1, n):
        a0, b0, a1, b1 = izq[i - 1], der[i - 1], izq[i], der[i]
        if a0 is None or b0 is None or a1 is None or b1 is None:
            continue
        out[i] = a0 <= b0 and a1 > b1
    return out


def _cruce_abajo(izq: list, der: list) -> list:
    n = len(izq)
    out: list = [None] * n
    for i in range(1, n):
        a0, b0, a1, b1 = izq[i - 1], der[i - 1], izq[i], der[i]
        if a0 is None or b0 is None or a1 is None or b1 is None:
            continue
        out[i] = a0 >= b0 and a1 < b1
    return out


def _entre(valor: list, minimo: list, maximo: list) -> list:
    out = []
    for v, mn, mx in zip(valor, minimo, maximo):
        out.append(mn <= v <= mx if v is not None and mn is not None and mx is not None else None)
    return out


def _subiendo_bajando(operando: list, n_barras: int, cmp) -> list:
    n = len(operando)
    out: list = [None] * n
    for i in range(n_barras, n):
        a, b = operando[i], operando[i - n_barras]
        if a is None or b is None:
            continue
        out[i] = cmp(a, b)
    return out


def _evaluar_y(hijos: list[list]) -> list:
    n = len(hijos[0])
    out: list = [None] * n
    for i in range(n):
        valores = [h[i] for h in hijos]
        out[i] = None if any(v is None for v in valores) else all(valores)
    return out


def _evaluar_o(hijos: list[list]) -> list:
    n = len(hijos[0])
    out: list = [None] * n
    for i in range(n):
        valores = [h[i] for h in hijos]
        out[i] = None if any(v is None for v in valores) else any(valores)
    return out


def _evaluar_no(hijo: list) -> list:
    return [None if v is None else (not v) for v in hijo]


def _evaluar_condicion(cond: dict, barras: list[Barra], series: dict) -> list:
    op = cond["op"]
    if op == "y":
        return _evaluar_y([_evaluar_condicion(c, barras, series) for c in cond["condiciones"]])
    if op == "o":
        return _evaluar_o([_evaluar_condicion(c, barras, series) for c in cond["condiciones"]])
    if op == "no":
        return _evaluar_no(_evaluar_condicion(cond["condicion"], barras, series))
    if op in _COMPARADORES:
        izq = _resolver_operando(cond["izq"], barras, series)
        der = _resolver_operando(cond["der"], barras, series)
        return _comparar(izq, der, _COMPARADORES[op])
    if op == "cruce_arriba":
        return _cruce_arriba(_resolver_operando(cond["izq"], barras, series), _resolver_operando(cond["der"], barras, series))
    if op == "cruce_abajo":
        return _cruce_abajo(_resolver_operando(cond["izq"], barras, series), _resolver_operando(cond["der"], barras, series))
    if op == "entre":
        return _entre(
            _resolver_operando(cond["valor"], barras, series),
            _resolver_operando(cond["minimo"], barras, series),
            _resolver_operando(cond["maximo"], barras, series),
        )
    if op in ("subiendo", "bajando"):
        operando = _resolver_operando(cond["operando"], barras, series)
        n_barras = int(cond.get("barras", 1))
        cmp = operator.gt if op == "subiendo" else operator.lt
        return _subiendo_bajando(operando, n_barras, cmp)
    raise ValueError(f"operador desconocido: {op!r}")


def compilar(dsl: dict, barras: list[Barra]) -> Compilado:
    series: dict = {}
    for item in dsl.get("indicadores", []) or []:
        series[item["id"]] = indicadores_engine.calcular(item["tipo"], barras, item.get("params"))

    entrada = _evaluar_condicion(dsl["entrada"], barras, series)
    salida_dsl = dsl.get("salida")
    salida = _evaluar_condicion(salida_dsl, barras, series) if salida_dsl else [None] * len(barras)

    primera_entrada = next((i for i, v in enumerate(entrada) if v is not None), None)
    primera_salida = next((i for i, v in enumerate(salida) if v is not None), None) if salida_dsl else None
    if primera_entrada is None:
        primera_barra_evaluable = primera_salida
    elif primera_salida is None:
        primera_barra_evaluable = primera_entrada
    else:
        primera_barra_evaluable = max(primera_entrada, primera_salida)

    return Compilado(entrada=entrada, salida=salida, series=series, primera_barra_evaluable=primera_barra_evaluable)


# ─── Backtest ─────────────────────────────────────────────────────────────────

def _maximo_barra(barra: Barra) -> float:
    return barra.maximo if barra.maximo is not None else barra.cierre


def _precio_ejecucion(barras: list[Barra], indice_senal: int, ejecucion: dict, advertencias: set) -> tuple[int, float] | None:
    demora = int(ejecucion.get("demora_barras", 0) or 0)
    idx = indice_senal + demora
    if idx >= len(barras):
        return None
    modo = ejecucion.get("precio_ejecucion", "cierre")
    barra = barras[idx]
    if modo == "apertura_siguiente":
        if barra.apertura is not None:
            return idx, barra.apertura
        advertencias.add("apertura_no_disponible_uso_cierre")
        return idx, barra.cierre
    return idx, barra.cierre


def _chequear_salida(
    barras: list[Barra], i: int, precio_entrada: float, maximo_desde_entrada: float,
    stop_loss_pct, take_profit_pct, trailing_stop_pct, max_barras, idx_entrada_ejec: int,
    salida_compilada: list, ejecucion: dict, advertencias: set,
):
    """`None` si no hay salida en la barra `i`, o `(motivo, precio, indice_ejecucion)`."""
    barra = barras[i]
    tiene_ohlc = barra.maximo is not None and barra.minimo is not None
    minimo_barra = barra.minimo if tiene_ohlc else barra.cierre
    maximo_barra = barra.maximo if tiene_ohlc else barra.cierre

    niveles_bajistas = []
    if stop_loss_pct is not None:
        niveles_bajistas.append(("stop_loss", precio_entrada * (1 - stop_loss_pct / 100)))
    if trailing_stop_pct is not None:
        niveles_bajistas.append(("trailing_stop", maximo_desde_entrada * (1 - trailing_stop_pct / 100)))
    if niveles_bajistas:
        motivo, nivel = max(niveles_bajistas, key=lambda t: t[1])
        if minimo_barra <= nivel:
            precio = barra.apertura if (barra.apertura is not None and barra.apertura < nivel) else nivel
            return motivo, precio, i

    if take_profit_pct is not None:
        nivel_tp = precio_entrada * (1 + take_profit_pct / 100)
        if maximo_barra >= nivel_tp:
            precio = barra.apertura if (barra.apertura is not None and barra.apertura > nivel_tp) else nivel_tp
            return "take_profit", precio, i

    if salida_compilada[i] is True:
        ejec = _precio_ejecucion(barras, i, ejecucion, advertencias)
        if ejec is not None:
            idx_ejec, precio = ejec
            return "regla_salida", precio, idx_ejec

    if max_barras is not None and (i - idx_entrada_ejec) >= int(max_barras):
        ejec = _precio_ejecucion(barras, i, ejecucion, advertencias)
        if ejec is not None:
            idx_ejec, precio = ejec
            return "max_barras", precio, idx_ejec
        return "max_barras", barra.cierre, i

    return None


def _curva_buy_hold(barras: list[Barra], indice_inicio: int = 0) -> list[tuple[date, float]]:
    """Base 100 en `barras[indice_inicio]`, no en `barras[0]`: si el caller pidió warm-up extra
    para los indicadores, el buy&hold tiene que arrancar donde arranca la ventana pedida, igual
    que la curva de equity (que ya empieza en 100 ahí porque no hay operaciones antes)."""
    base = barras[indice_inicio].cierre
    return [(b.fecha, (b.cierre / base) * 100.0) for b in barras]


def _construir_curva_equity(
    barras: list[Barra], operaciones: list[Operacion], comision_pct: float = 0.0,
) -> list[tuple[date, float]]:
    n = len(barras)
    curva: list[tuple[date, float]] = []
    equity_actual = 100.0
    equity_en_apertura = 100.0
    idx_op = 0
    op_actual: Operacion | None = None

    for i in range(n):
        if op_actual is None and idx_op < len(operaciones) and operaciones[idx_op].indice_entrada == i:
            op_actual = operaciones[idx_op]
            equity_en_apertura = equity_actual

        if op_actual is not None:
            idx_salida = op_actual.indice_salida if op_actual.indice_salida is not None else n - 1
            if i == idx_salida and not op_actual.abierta:
                equity_actual = equity_en_apertura * (1 + op_actual.retorno_neto_pct / 100)
                curva.append((barras[i].fecha, equity_actual))
                idx_op += 1
                op_actual = None
            else:
                retorno_pct = (barras[i].cierre / op_actual.precio_entrada - 1) * 100
                # En la última barra de una posición que queda abierta ya no habrá salida que
                # cargue la comisión: se descuenta acá (sólo la de entrada, como en
                # `retorno_neto_pct` de la `Operacion` abierta) para que el equity final coincida
                # con `retorno_abierta_pct`. Los días intermedios quedan a precio bruto a propósito
                # (ver docstring del módulo): el salto de comisión es de una sola vez.
                if i == n - 1 and op_actual.abierta:
                    retorno_pct -= comision_pct
                equity_actual = equity_en_apertura * (1 + retorno_pct / 100)
                curva.append((barras[i].fecha, equity_actual))
            continue

        curva.append((barras[i].fecha, equity_actual))
    return curva


def _calcular_metricas(
    operaciones: list[Operacion], curva_equity, curva_buy_hold, comision_pct: float, indice_inicio: int = 0,
) -> dict:
    """`curva_equity`/`curva_buy_hold` llegan alineadas 1:1 con la serie completa (incluye el
    warm-up previo a `indice_inicio`, si lo hubo); acá se recortan a la ventana `[indice_inicio:]`
    para que retorno total, días, drawdown y exposición reflejen sólo el período pedido, no el
    warm-up. `operaciones` no necesita recorte: `backtest()` ya no abre posiciones antes de
    `indice_inicio`."""
    ventana_equity = curva_equity[indice_inicio:]
    ventana_buy_hold = curva_buy_hold[indice_inicio:]

    retorno_total_pct = ventana_equity[-1][1] - 100.0
    retorno_buy_hold_pct = ventana_buy_hold[-1][1] - 100.0
    dias = (ventana_equity[-1][0] - ventana_equity[0][0]).days
    retorno_anualizado_pct = None
    if dias > 0 and ventana_equity[-1][1] > 0:
        retorno_anualizado_pct = ((ventana_equity[-1][1] / 100.0) ** (365.0 / dias) - 1) * 100.0

    drawdown = risk_engine.calcular_drawdown(ventana_equity)
    max_drawdown_pct = drawdown["maximo"] * 100 if drawdown["maximo"] is not None else None

    cerradas = [o for o in operaciones if not o.abierta]
    n_ops = len(operaciones)
    n_cerradas = len(cerradas)

    op_abierta = next((o for o in operaciones if o.abierta), None)
    retorno_abierta_pct = round(op_abierta.retorno_neto_pct, 4) if op_abierta is not None else None

    # Con 0 operaciones cerradas no hay nada que promediar. Con 1 sí se calculan las métricas por
    # operación (el `estado` pasa a "ok"); `operaciones_cerradas` deja que el front avise que están
    # basadas en una sola muestra.
    if n_cerradas < 1:
        estado = "datos_insuficientes"
        win_rate_pct = profit_factor = retorno_medio_operacion_pct = None
        mejor_operacion_pct = peor_operacion_pct = duracion_media_barras = None
    else:
        estado = "ok"
        ganadoras_lista = [o for o in cerradas if o.retorno_neto_pct > 0]
        perdedoras_lista = [o for o in cerradas if o.retorno_neto_pct <= 0]
        win_rate_pct = len(ganadoras_lista) / n_cerradas * 100
        suma_ganancias = sum(o.retorno_neto_pct for o in ganadoras_lista)
        suma_perdidas = abs(sum(o.retorno_neto_pct for o in perdedoras_lista))
        profit_factor = (suma_ganancias / suma_perdidas) if suma_perdidas > 0 else None
        retorno_medio_operacion_pct = sum(o.retorno_neto_pct for o in cerradas) / n_cerradas
        mejor_operacion_pct = max(o.retorno_neto_pct for o in cerradas)
        peor_operacion_pct = min(o.retorno_neto_pct for o in cerradas)
        duracion_media_barras = sum(o.barras for o in cerradas) / n_cerradas

    ganadoras = sum(1 for o in cerradas if o.retorno_neto_pct > 0)
    perdedoras = sum(1 for o in cerradas if o.retorno_neto_pct <= 0)

    # `indice_salida`/`indice_entrada` son índices absolutos (dentro de la serie completa, con
    # warm-up incluido); el fallback de una posición abierta usa el último índice absoluto
    # (`len(curva_equity) - 1`, la serie completa). La exposición, en cambio, se normaliza contra
    # el largo de la ventana pedida (`ventana_equity`), no contra el warm-up.
    barras_en_mercado = sum(
        (o.indice_salida if o.indice_salida is not None else len(curva_equity) - 1) - o.indice_entrada + 1
        for o in operaciones
    )
    exposicion_pct = (barras_en_mercado / len(ventana_equity) * 100) if ventana_equity else 0.0
    comisiones_pct_acum = n_cerradas * 2 * comision_pct + sum(1 for o in operaciones if o.abierta) * comision_pct

    return {
        "estado": estado,
        "retorno_total_pct": round(retorno_total_pct, 4),
        "retorno_anualizado_pct": round(retorno_anualizado_pct, 4) if retorno_anualizado_pct is not None else None,
        "retorno_buy_hold_pct": round(retorno_buy_hold_pct, 4),
        "exceso_vs_buy_hold_pp": round(retorno_total_pct - retorno_buy_hold_pct, 4),
        "operaciones": n_ops,
        "operaciones_cerradas": n_cerradas,
        "retorno_abierta_pct": retorno_abierta_pct,
        "ganadoras": ganadoras,
        "perdedoras": perdedoras,
        "win_rate_pct": round(win_rate_pct, 2) if win_rate_pct is not None else None,
        "retorno_medio_operacion_pct": round(retorno_medio_operacion_pct, 4) if retorno_medio_operacion_pct is not None else None,
        "mejor_operacion_pct": round(mejor_operacion_pct, 4) if mejor_operacion_pct is not None else None,
        "peor_operacion_pct": round(peor_operacion_pct, 4) if peor_operacion_pct is not None else None,
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "max_drawdown_pct": round(max_drawdown_pct, 4) if max_drawdown_pct is not None else None,
        "fecha_pico": drawdown["fecha_pico"],
        "fecha_valle": drawdown["fecha_valle"],
        "duracion_media_barras": round(duracion_media_barras, 2) if duracion_media_barras is not None else None,
        "exposicion_pct": round(exposicion_pct, 2),
        "comisiones_pct_acum": round(comisiones_pct_acum, 4),
    }


def backtest(dsl: dict, barras: list[Barra], indice_inicio: int = 0) -> ResultadoBacktest:
    """`indice_inicio`: primer índice desde el que se permite abrir posición (default 0 = toda la
    serie). El caller típico (`estrategias_analytics.ejecutar_backtest`) le pide a `barras` unas
    ruedas extra de warm-up antes del período pedido por el usuario para que los indicadores ya
    estén calculados en la primera barra visible; sin este corte esas ruedas de warm-up quedarían
    operables y contaminarían retorno total, buy&hold, drawdown y exposición con actividad de
    fuera del período pedido. Los indicadores sí se calculan sobre la serie completa (`compilar`
    no cambia): sólo se restringe cuándo puede *abrir* una operación."""
    n = len(barras)
    indice_inicio = max(0, min(indice_inicio, n))
    compilado = compilar(dsl, barras)
    riesgo = dsl.get("riesgo") or {}
    ejecucion = dsl.get("ejecucion") or {}
    comision_pct = float(ejecucion.get("comision_pct", 0.0) or 0.0)
    stop_loss_pct = riesgo.get("stop_loss_pct")
    take_profit_pct = riesgo.get("take_profit_pct")
    trailing_stop_pct = riesgo.get("trailing_stop_pct")
    max_barras = riesgo.get("max_barras")

    advertencias: set[str] = set()
    senales: list[Senal] = []
    operaciones: list[Operacion] = []

    estado = "fuera"
    precio_entrada = None
    idx_entrada_ejec = None
    maximo_desde_entrada = None

    i = 0
    while i < n:
        if estado == "fuera":
            if i >= indice_inicio and compilado.entrada[i] is True:
                ejec = _precio_ejecucion(barras, i, ejecucion, advertencias)
                if ejec is not None:
                    idx_ejec, precio = ejec
                    estado = "dentro"
                    precio_entrada = precio
                    idx_entrada_ejec = idx_ejec
                    # Sembrado con el precio de entrada, no con el máximo de la barra: ese máximo
                    # puede haber ocurrido antes de entrar (p.ej. si se entra al cierre), y un
                    # trailing stop sembrado más arriba del precio de entrada generaría una salida
                    # con ganancia que nunca existió. Sólo las barras *posteriores* a la entrada
                    # mueven el trailing hacia arriba (más abajo en el loop).
                    maximo_desde_entrada = precio_entrada
                    senales.append(Senal(idx_ejec, barras[idx_ejec].fecha, "compra", precio, "entrada"))
                    i = idx_ejec
            i += 1
            continue

        if i <= idx_entrada_ejec:
            i += 1
            continue

        maximo_desde_entrada = max(maximo_desde_entrada, _maximo_barra(barras[i]))
        resultado_salida = _chequear_salida(
            barras, i, precio_entrada, maximo_desde_entrada,
            stop_loss_pct, take_profit_pct, trailing_stop_pct, max_barras, idx_entrada_ejec,
            compilado.salida, ejecucion, advertencias,
        )
        if resultado_salida is not None:
            motivo, precio_salida, idx_salida_ejec = resultado_salida
            retorno_bruto = (precio_salida / precio_entrada - 1) * 100
            retorno_neto = retorno_bruto - 2 * comision_pct
            senales.append(Senal(idx_salida_ejec, barras[idx_salida_ejec].fecha, "venta", precio_salida, motivo))
            operaciones.append(Operacion(
                indice_entrada=idx_entrada_ejec, indice_salida=idx_salida_ejec,
                fecha_entrada=barras[idx_entrada_ejec].fecha, fecha_salida=barras[idx_salida_ejec].fecha,
                precio_entrada=precio_entrada, precio_salida=precio_salida,
                barras=idx_salida_ejec - idx_entrada_ejec,
                retorno_bruto_pct=retorno_bruto, retorno_neto_pct=retorno_neto,
                motivo_salida=motivo, abierta=False,
            ))
            estado = "fuera"
            i = idx_salida_ejec
            precio_entrada = None
            idx_entrada_ejec = None
            maximo_desde_entrada = None
        i += 1

    if estado == "dentro":
        precio_final = barras[-1].cierre
        retorno_bruto = (precio_final / precio_entrada - 1) * 100
        retorno_neto = retorno_bruto - comision_pct
        operaciones.append(Operacion(
            indice_entrada=idx_entrada_ejec, indice_salida=None,
            fecha_entrada=barras[idx_entrada_ejec].fecha, fecha_salida=None,
            precio_entrada=precio_entrada, precio_salida=None,
            barras=(n - 1) - idx_entrada_ejec,
            retorno_bruto_pct=retorno_bruto, retorno_neto_pct=retorno_neto,
            motivo_salida=None, abierta=True,
        ))
        advertencias.add("posicion_abierta_al_final")

    curva_equity = _construir_curva_equity(barras, operaciones, comision_pct)
    curva_buy_hold = _curva_buy_hold(barras, indice_inicio)
    metricas = _calcular_metricas(operaciones, curva_equity, curva_buy_hold, comision_pct, indice_inicio)

    return ResultadoBacktest(
        senales=senales, operaciones=operaciones, metricas=metricas,
        curva_equity=curva_equity, curva_buy_hold=curva_buy_hold, advertencias=sorted(advertencias),
    )


# ─── Validador ────────────────────────────────────────────────────────────────

VERSION_SOPORTADA = 1
_OPERADORES_HOJA = {"mayor", "menor", "mayor_igual", "menor_igual", "cruce_arriba", "cruce_abajo", "entre", "subiendo", "bajando"}
_CAMPOS_VALIDOS = set(_CAMPO_GETTERS.keys())
_PROFUNDIDAD_MAXIMA = 4
_NODOS_MAXIMOS = 20
_PERIODO_MIN, _PERIODO_MAX = 1, 500
_COMISION_MIN, _COMISION_MAX = 0.0, 5.0
_PARAM_FLOAT_MIN, _PARAM_FLOAT_MAX = 0.1, 10.0  # p.ej. `desvios` de Bollinger: multiplicador, siempre positivo
_RIESGO_PCT_MIN, _RIESGO_PCT_MAX = 0.1, 90.0
_MAX_BARRAS_MIN = 1
_DEMORA_MAX = 20


def validar_estrategia(dsl) -> list[str]:
    """Lista de mensajes de error en castellano, listos para mostrar. `[]` == válido."""
    errores: list[str] = []
    if not isinstance(dsl, dict):
        return ["la definición debe ser un objeto"]

    if dsl.get("version") != VERSION_SOPORTADA:
        errores.append(f"version no soportada: {dsl.get('version')!r} (esperado {VERSION_SOPORTADA})")

    ids_declarados: set[str] = set()
    tipo_por_id: dict[str, str] = {}
    for item in dsl.get("indicadores", []) or []:
        if not isinstance(item, dict):
            errores.append("cada indicador debe ser un objeto")
            continue
        id_, tipo, params = item.get("id"), item.get("tipo"), item.get("params") or {}
        if not id_:
            errores.append("indicador sin 'id'")
        elif id_ in ids_declarados:
            errores.append(f"id de indicador duplicado: {id_!r}")
        else:
            ids_declarados.add(id_)
            tipo_por_id[id_] = tipo
        if tipo not in indicadores_engine.INDICADORES:
            errores.append(f"tipo de indicador desconocido: {tipo!r}")
            continue
        espec_ind = indicadores_engine.INDICADORES[tipo]
        params_default = espec_ind.params_default
        for clave_p, valor_p in params.items():
            if clave_p not in params_default:
                errores.append(f"{tipo}: parámetro desconocido {clave_p!r}")
                continue
            # `bool` es subclase de `int` en Python: sin este chequeo `True`/`False` colarían
            # como "numérico" válido.
            if not isinstance(valor_p, (int, float)) or isinstance(valor_p, bool):
                errores.append(f"{tipo}.{clave_p} debe ser numérico")
                continue
            # Rango declarativo del indicador (p.ej. `ventana` de EXTREMOS: 0..500) antes de la
            # heurística por tipo. Sin lista blanca de excepciones ni tipo aparte.
            rango = espec_ind.rangos.get(clave_p)
            if rango is not None:
                lo, hi = rango
                if not (lo <= valor_p <= hi):
                    errores.append(f"{tipo}.{clave_p} debe estar entre {lo} y {hi}")
            elif isinstance(params_default[clave_p], float):
                if not (_PARAM_FLOAT_MIN <= valor_p <= _PARAM_FLOAT_MAX):
                    errores.append(f"{tipo}.{clave_p} debe estar entre {_PARAM_FLOAT_MIN} y {_PARAM_FLOAT_MAX}")
            elif not (_PERIODO_MIN <= valor_p <= _PERIODO_MAX):
                errores.append(f"{tipo}.{clave_p} debe estar entre {_PERIODO_MIN} y {_PERIODO_MAX}")

    contador_nodos = [0]

    def _validar_operando(operando, contexto: str) -> None:
        if not isinstance(operando, dict):
            errores.append(f"{contexto}: operando inválido: {operando!r}")
            return
        claves = [k for k in ("ref", "const", "campo") if k in operando]
        if len(claves) != 1:
            errores.append(f"{contexto}: operando debe tener exactamente una clave (ref/const/campo)")
            return
        if "ref" in operando:
            ref = operando["ref"]
            if ref not in ids_declarados:
                errores.append(f"{contexto}: referencia no declarada: {ref!r}")
            else:
                salida = operando.get("salida", "valor")
                tipo_ref = tipo_por_id.get(ref)
                espec = indicadores_engine.INDICADORES.get(tipo_ref)
                if espec is not None and salida not in espec.salidas:
                    errores.append(f"{contexto}: salida {salida!r} inválida para {tipo_ref}")
        if "campo" in operando and operando["campo"] not in _CAMPOS_VALIDOS:
            errores.append(f"{contexto}: campo inválido: {operando['campo']!r}")

    def _validar_hoja(op: str, cond: dict) -> None:
        contexto = f"condición {op!r}"
        if op in _COMPARADORES or op in ("cruce_arriba", "cruce_abajo"):
            if "izq" not in cond or "der" not in cond:
                errores.append(f"{contexto} requiere 'izq' y 'der'")
                return
            _validar_operando(cond["izq"], contexto)
            _validar_operando(cond["der"], contexto)
        elif op == "entre":
            faltantes = [c for c in ("valor", "minimo", "maximo") if c not in cond]
            if faltantes:
                errores.append(f"{contexto} requiere 'valor', 'minimo' y 'maximo'")
                return
            for c in ("valor", "minimo", "maximo"):
                _validar_operando(cond[c], contexto)
        elif op in ("subiendo", "bajando"):
            if "operando" not in cond:
                errores.append(f"{contexto} requiere 'operando'")
                return
            _validar_operando(cond["operando"], contexto)
            n_barras = cond.get("barras", 1)
            if not isinstance(n_barras, int) or n_barras < 1:
                errores.append(f"{contexto}: 'barras' debe ser un entero >= 1")

    def _validar_condicion(cond, profundidad: int) -> None:
        contador_nodos[0] += 1
        if contador_nodos[0] > _NODOS_MAXIMOS:
            errores.append(f"la estrategia supera el máximo de {_NODOS_MAXIMOS} nodos")
            return
        if profundidad > _PROFUNDIDAD_MAXIMA:
            errores.append(f"la estrategia supera la profundidad máxima de {_PROFUNDIDAD_MAXIMA}")
            return
        if not isinstance(cond, dict) or "op" not in cond:
            errores.append(f"condición inválida: {cond!r}")
            return
        op = cond["op"]
        if op in ("y", "o"):
            hijos = cond.get("condiciones")
            if not isinstance(hijos, list) or not hijos:
                errores.append(f"'{op}' requiere 'condiciones' (lista no vacía)")
                return
            for h in hijos:
                _validar_condicion(h, profundidad + 1)
        elif op == "no":
            if cond.get("condicion") is None:
                errores.append("'no' requiere 'condicion'")
                return
            _validar_condicion(cond["condicion"], profundidad + 1)
        elif op in _OPERADORES_HOJA:
            _validar_hoja(op, cond)
        else:
            errores.append(f"operador desconocido: {op!r}")

    entrada = dsl.get("entrada")
    if entrada is None:
        errores.append("falta 'entrada' (al menos una condición de compra)")
    else:
        _validar_condicion(entrada, 1)

    salida = dsl.get("salida")
    if salida is not None:
        _validar_condicion(salida, 1)

    riesgo = dsl.get("riesgo") or {}
    if not isinstance(riesgo, dict):
        errores.append("riesgo debe ser un objeto")
    else:
        for campo_r in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"):
            valor_r = riesgo.get(campo_r)
            if valor_r is None:
                continue
            if not isinstance(valor_r, (int, float)) or isinstance(valor_r, bool) or not (_RIESGO_PCT_MIN <= valor_r <= _RIESGO_PCT_MAX):
                errores.append(f"riesgo.{campo_r} debe ser un número entre {_RIESGO_PCT_MIN} y {_RIESGO_PCT_MAX}")
        max_barras_r = riesgo.get("max_barras")
        if max_barras_r is not None:
            if not isinstance(max_barras_r, int) or isinstance(max_barras_r, bool) or max_barras_r < _MAX_BARRAS_MIN:
                errores.append(f"riesgo.max_barras debe ser un entero >= {_MAX_BARRAS_MIN}")

    ejecucion = dsl.get("ejecucion") or {}
    comision_pct = ejecucion.get("comision_pct", 0.0)
    if not isinstance(comision_pct, (int, float)) or isinstance(comision_pct, bool) or not (_COMISION_MIN <= comision_pct <= _COMISION_MAX):
        errores.append(f"comision_pct debe estar entre {_COMISION_MIN} y {_COMISION_MAX}")
    precio_ejecucion = ejecucion.get("precio_ejecucion", "cierre")
    if precio_ejecucion not in ("cierre", "apertura_siguiente"):
        errores.append(f"precio_ejecucion inválido: {precio_ejecucion!r}")
    lado = ejecucion.get("lado", "long")
    if lado != "long":
        errores.append(f"lado {lado!r} no soportado todavía: sólo 'long'")

    demora_barras = ejecucion.get("demora_barras", 0)
    if not isinstance(demora_barras, int) or isinstance(demora_barras, bool):
        errores.append("demora_barras debe ser un entero")
    elif not (0 <= demora_barras <= _DEMORA_MAX):
        errores.append(f"demora_barras debe estar entre 0 y {_DEMORA_MAX}")
    elif precio_ejecucion == "apertura_siguiente" and demora_barras < 1:
        # Con demora 0, la señal calculada con el cierre de la barra `i` ejecutaría en la apertura
        # de esa misma barra `i` — anterior al cierre que la generó. Es lookahead: la estrategia
        # "sabría" el resultado del día antes de que termine.
        errores.append(
            "con precio_ejecucion='apertura_siguiente', demora_barras debe ser >= 1 "
            "(si no, ejecuta en la apertura de la misma barra de la señal, antes de que exista)"
        )

    return errores


def barras_minimas(dsl: dict) -> int:
    """Máximo warm-up entre los indicadores declarados — ruedas extra a pedir antes de `desde`."""
    maximo = 0
    for item in dsl.get("indicadores", []) or []:
        tipo = item.get("tipo")
        if tipo in indicadores_engine.INDICADORES:
            maximo = max(maximo, indicadores_engine.warm_up_barras(tipo, item.get("params")))
    return maximo


# ─── Presets ──────────────────────────────────────────────────────────────────

_EJECUCION_DEFAULT = {"lado": "long", "comision_pct": 0.6, "precio_ejecucion": "cierre", "demora_barras": 0}
_RIESGO_DEFAULT = {"stop_loss_pct": 8.0, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None}

PRESETS: dict[str, dict] = {
    "cruce_medias": {
        "version": 1,
        "indicadores": [
            {"id": "mm_rapida", "tipo": "SMA", "params": {"periodo": 50}},
            {"id": "mm_lenta", "tipo": "SMA", "params": {"periodo": 200}},
        ],
        "entrada": {"op": "y", "condiciones": [
            {"op": "cruce_arriba", "izq": {"ref": "mm_rapida"}, "der": {"ref": "mm_lenta"}},
        ]},
        "salida": {"op": "y", "condiciones": [
            {"op": "cruce_abajo", "izq": {"ref": "mm_rapida"}, "der": {"ref": "mm_lenta"}},
        ]},
        "riesgo": dict(_RIESGO_DEFAULT),
        "ejecucion": dict(_EJECUCION_DEFAULT),
    },
    "rsi_sobreventa": {
        "version": 1,
        "indicadores": [{"id": "rsi14", "tipo": "RSI", "params": {"periodo": 14}}],
        "entrada": {"op": "y", "condiciones": [
            {"op": "menor", "izq": {"ref": "rsi14"}, "der": {"const": 30}},
        ]},
        "salida": {"op": "y", "condiciones": [
            {"op": "mayor", "izq": {"ref": "rsi14"}, "der": {"const": 60}},
        ]},
        "riesgo": {**_RIESGO_DEFAULT, "stop_loss_pct": 10.0},
        "ejecucion": dict(_EJECUCION_DEFAULT),
    },
    "macd_cruce": {
        "version": 1,
        "indicadores": [{"id": "macd_std", "tipo": "MACD", "params": {"rapida": 12, "lenta": 26, "senal": 9}}],
        "entrada": {"op": "y", "condiciones": [
            {"op": "cruce_arriba", "izq": {"ref": "macd_std", "salida": "macd"}, "der": {"ref": "macd_std", "salida": "senal"}},
        ]},
        "salida": {"op": "y", "condiciones": [
            {"op": "cruce_abajo", "izq": {"ref": "macd_std", "salida": "macd"}, "der": {"ref": "macd_std", "salida": "senal"}},
        ]},
        "riesgo": dict(_RIESGO_DEFAULT),
        "ejecucion": dict(_EJECUCION_DEFAULT),
    },
    "bollinger_reversion": {
        "version": 1,
        "indicadores": [{"id": "bb20", "tipo": "BOLLINGER", "params": {"periodo": 20, "desvios": 2.0}}],
        "entrada": {"op": "y", "condiciones": [
            {"op": "menor", "izq": {"campo": "cierre"}, "der": {"ref": "bb20", "salida": "inferior"}},
        ]},
        "salida": {"op": "y", "condiciones": [
            {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"ref": "bb20", "salida": "media"}},
        ]},
        "riesgo": {**_RIESGO_DEFAULT, "stop_loss_pct": 10.0},
        "ejecucion": dict(_EJECUCION_DEFAULT),
    },
    "extremos_historicos": {
        "version": 1,
        "indicadores": [{"id": "ext", "tipo": "EXTREMOS", "params": {"ventana": 0}}],
        "entrada": {"op": "y", "condiciones": [
            {"op": "menor_igual", "izq": {"ref": "ext", "salida": "dist_min_pct"}, "der": {"const": 1}},
        ]},
        "salida": {"op": "y", "condiciones": [
            {"op": "mayor_igual", "izq": {"ref": "ext", "salida": "dist_max_pct"}, "der": {"const": -1}},
        ]},
        "riesgo": {**_RIESGO_DEFAULT, "stop_loss_pct": 20.0},
        "ejecucion": dict(_EJECUCION_DEFAULT),
    },
}


def resolver_preset(nombre: str) -> dict:
    """Espejo de `escenario_engine.resolver_preset`: devuelve una copia profunda del preset."""
    if nombre not in PRESETS:
        raise ValueError(f"preset desconocido: {nombre!r}")
    return deepcopy(PRESETS[nombre])
