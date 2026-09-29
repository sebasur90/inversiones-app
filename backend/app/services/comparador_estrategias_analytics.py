"""Orquestación del comparador de estrategias: mismo patrón que `screener_analytics.py` con el eje
invertido (1 ticker × N estrategias en vez de N tickers × N estrategias). Resuelve la serie **una
sola vez** con el warm-up máximo entre todas las estrategias, y corre `estrategia_engine.backtest`
una vez por estrategia sobre esas mismas `barras` y el mismo `indice_desde`: es lo que garantiza que
todas las curvas comparten el mismo eje de fechas.

No se toca `estrategia_engine`/`risk_engine`/`ohlcv_analytics`/`estrategias_analytics`: acá sólo se
conecta lo que ya existe con los cálculos nuevos de `comparador_estrategias_engine`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import comparador_estrategias_engine as cee
from . import estrategia_engine, estrategias_analytics, ohlcv_analytics, risk_engine
from .cache import cache_por_sync

# DSL centinela para leer `curva_buy_hold`: la condición nunca es verdadera (cierre > cierre es
# falso siempre), así que no abre ninguna operación y no hace falta ningún indicador. Buy & Hold no
# depende de la estrategia (`_curva_buy_hold` interna del motor sólo usa `barras`/`indice_inicio`),
# así que esto evita depender de una función privada de `estrategia_engine` para conseguirla sin
# correr un backtest de verdad.
_DSL_BUYHOLD = {
    "version": 1, "indicadores": [],
    "entrada": {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"campo": "cierre"}},
}


def _operaciones_ventana(operaciones, indice_desde: int, largo_ventana: int) -> list[tuple[int, int]]:
    """`(indice_entrada, indice_salida)` de cada operación, reindexados a la ventana (0 = primer
    índice pedido) y con la salida resuelta a un índice concreto (última barra si sigue abierta)."""
    out = []
    for o in operaciones:
        entrada = max(0, o.indice_entrada - indice_desde)
        salida = (o.indice_salida - indice_desde) if o.indice_salida is not None else (largo_ventana - 1)
        out.append((entrada, min(largo_ventana - 1, salida)))
    return out


def _riesgo_operaciones(metricas: dict) -> dict:
    return {
        "operaciones": metricas["operaciones"], "operaciones_cerradas": metricas["operaciones_cerradas"],
        "ganadoras": metricas["ganadoras"], "perdedoras": metricas["perdedoras"],
        "win_rate_pct": metricas["win_rate_pct"], "mejor_operacion_pct": metricas["mejor_operacion_pct"],
        "peor_operacion_pct": metricas["peor_operacion_pct"], "exposicion_pct": metricas["exposicion_pct"],
        "tiempo_fuera_mercado_pct": round(100 - metricas["exposicion_pct"], 2),
        "comisiones_pct_acum": metricas["comisiones_pct_acum"],
    }


def _riesgo_fila(metricas: dict, ventana_equity: list[tuple[date, float]]) -> dict:
    """Riesgo de una fila con backtest real: reusa el drawdown que ya calculó
    `estrategia_engine._calcular_metricas` (no se recalcula), y sólo agrega lo que el motor de
    backtest no da: volatilidad de la curva y duración del drawdown en días."""
    dur = cee.duracion_drawdown(ventana_equity, metricas["fecha_pico"], metricas["fecha_valle"])
    vol = cee.volatilidad_curva(ventana_equity)
    return {
        "max_drawdown_pct": metricas["max_drawdown_pct"],
        "fecha_pico": metricas["fecha_pico"], "fecha_valle": metricas["fecha_valle"],
        "duracion_caida_dias": dur["dias_caida"], "duracion_recuperacion_dias": dur["dias_recuperacion"],
        "recuperado": dur["recuperado"],
        "volatilidad_anualizada_pct": vol["anualizada_pct"], "volatilidad_estado": vol["estado"],
        **_riesgo_operaciones(metricas),
    }


def _riesgo_bh(ventana_bh: list[tuple[date, float]]) -> dict:
    """Riesgo de Comprar y mantener: drawdown de su propia curva, no el del backtest de la
    estrategia centinela (que no opera y por lo tanto no tiene drawdown propio). 1 operación, 100%
    expuesto, sin comisión — Buy & Hold bruto, como ya lo documenta el motor."""
    dd = risk_engine.calcular_drawdown(ventana_bh)
    dur = cee.duracion_drawdown(ventana_bh, dd["fecha_pico"], dd["fecha_valle"])
    vol = cee.volatilidad_curva(ventana_bh)
    return {
        "max_drawdown_pct": round(dd["maximo"] * 100, 4) if dd["maximo"] is not None else None,
        "fecha_pico": dd["fecha_pico"], "fecha_valle": dd["fecha_valle"],
        "duracion_caida_dias": dur["dias_caida"], "duracion_recuperacion_dias": dur["dias_recuperacion"],
        "recuperado": dur["recuperado"],
        "volatilidad_anualizada_pct": vol["anualizada_pct"], "volatilidad_estado": vol["estado"],
        "operaciones": 1, "operaciones_cerradas": 0, "ganadoras": 0, "perdedoras": 0,
        "win_rate_pct": None, "mejor_operacion_pct": None, "peor_operacion_pct": None,
        "exposicion_pct": 100.0, "tiempo_fuera_mercado_pct": 0.0, "comisiones_pct_acum": 0.0,
    }


def _fila_base(estrategia_id: int | None, nombre: str, es_referencia: bool) -> dict:
    return {
        "estrategia_id": estrategia_id, "nombre": nombre, "es_referencia": es_referencia,
        "estado": "definicion_invalida", "errores": [], "retorno_total_pct": None,
        "retorno_anualizado_pct": None, "capital_final": None, "ganancia": None,
        "diferencia_pp": None, "diferencia_monetaria": None, "diferencia_relativa_pct": None,
        "riesgo": None, "divergencias": [], "curva": [], "advertencias": [],
    }


@cache_por_sync
def comparar_estrategias(
    ticker: str, estrategia_ids: tuple[int, ...], db: Session,
    desde: date | None = None, hasta: date | None = None, variante: str = "local",
    capital_inicial: float = cee.CAPITAL_DEFAULT, referencia_id: int | None = None,
    sin_costos: bool = False,
) -> dict:
    hasta = hasta or date.today()
    advertencias: list[str] = []

    filas_db = {
        e.id: e for e in (estrategias_analytics.obtener_estrategia(i, db) for i in set(estrategia_ids))
        if e is not None
    }
    omitidas = [i for i in estrategia_ids if i not in filas_db]
    if omitidas:
        advertencias.append("estrategias_omitidas")

    # DSL + errores de validación por estrategia pedida, en el orden pedido (no el de `filas_db`,
    # que viene de un `set` sin orden estable).
    ids_ordenados = [i for i in estrategia_ids if i in filas_db]
    errores_por_id: dict[int, list[str]] = {}
    dsl_por_id: dict[int, dict] = {}
    for i in ids_ordenados:
        dsl = filas_db[i].definicion
        errores = estrategia_engine.validar_estrategia(dsl)
        errores_por_id[i] = errores
        if not errores:
            dsl_por_id[i] = cee.dsl_sin_costos(dsl) if sin_costos else dsl

    warm_up = 0
    for dsl in dsl_por_id.values():
        try:
            warm_up = max(warm_up, estrategia_engine.barras_minimas(dsl))
        except (TypeError, AttributeError):
            continue

    serie = ohlcv_analytics.get_serie_barras(
        ticker, desde or date(1900, 1, 1), hasta, db, barras_previas=warm_up, max_barras=3000, variante=variante,
    )
    barras = serie["barras"]
    advertencias.extend(serie["advertencias"])
    indice_desde = serie.get("indice_desde", 0)

    base = {
        "ticker": ticker, "variante": variante, "moneda": serie["moneda"], "capital_inicial": capital_inicial,
        "desde": desde, "hasta": hasta, "referencia_id": referencia_id,
        "estrategias_omitidas": omitidas, "fechas": [], "filas": [], "mejor": None,
        "advertencias": advertencias,
    }

    if len(barras) < 2:
        return {**base, "estado": "sin_serie"}

    largo_ventana = len(barras) - indice_desde
    if largo_ventana < cee.MIN_BARRAS_VENTANA:
        return {**base, "estado": "datos_insuficientes"}

    fechas = [b.fecha for b in barras[indice_desde:]]

    # Buy & Hold: no depende de ninguna estrategia (ver `_DSL_BUYHOLD`), se corre una sola vez.
    resultado_bh = estrategia_engine.backtest(_DSL_BUYHOLD, barras, indice_inicio=indice_desde)
    ventana_bh = resultado_bh.curva_buy_hold[indice_desde:]
    curva_bh = [v for _, v in ventana_bh]
    retorno_bh = resultado_bh.metricas["retorno_buy_hold_pct"]
    ops_bh = [(0, largo_ventana - 1)]

    fila_bh = _fila_base(None, "Comprar y mantener", referencia_id is None)
    fila_bh.update({
        "estado": "ok",
        "retorno_total_pct": retorno_bh, "retorno_anualizado_pct": None,
        **cee.dinero(retorno_bh, capital_inicial),
        "riesgo": _riesgo_bh(ventana_bh),
        "curva": curva_bh,
    })

    filas: list[dict] = [fila_bh]
    curvas: dict[int | None, list[float | None]] = {None: curva_bh}
    ops_por_id: dict[int, list[tuple[int, int]]] = {}
    retorno_por_id: dict[int | None, float | None] = {None: retorno_bh}

    for i in ids_ordenados:
        estrategia = filas_db[i]
        errores = errores_por_id[i]

        if errores:
            fila = _fila_base(i, estrategia.nombre, referencia_id == i)
            fila["errores"] = errores
            fila["curva"] = [None] * len(fechas)
            curvas[i] = fila["curva"]
            retorno_por_id[i] = None
            filas.append(fila)
            continue

        dsl = dsl_por_id[i]
        resultado = estrategia_engine.backtest(dsl, barras, indice_inicio=indice_desde)
        metricas = resultado.metricas
        ventana_equity = resultado.curva_equity[indice_desde:]
        curva = [v for _, v in ventana_equity]
        ops_por_id[i] = _operaciones_ventana(resultado.operaciones, indice_desde, largo_ventana)

        try:
            pbe = estrategia_engine.compilar(dsl, barras).primera_barra_evaluable
        except (ValueError, KeyError, TypeError):
            pbe = None

        if metricas["operaciones"] == 0:
            estado = "warm_up_insuficiente" if (pbe is None or pbe >= len(barras)) else "sin_senales"
        elif metricas["estado"] == "datos_insuficientes":
            estado = "datos_insuficientes"
        else:
            estado = "ok"

        advertencias_fila = cee.advertencias_dsl_serie(dsl, serie["tiene_velas"], serie["tiene_volumen"])
        if estrategia.ticker is not None and estrategia.ticker != ticker:
            advertencias_fila.append("ticker_distinto_al_de_la_estrategia")

        fila = _fila_base(i, estrategia.nombre, referencia_id == i)
        fila.update({
            "estado": estado,
            "retorno_total_pct": metricas["retorno_total_pct"],
            "retorno_anualizado_pct": metricas["retorno_anualizado_pct"],
            **cee.dinero(metricas["retorno_total_pct"], capital_inicial),
            "riesgo": _riesgo_fila(metricas, ventana_equity),
            "curva": curva, "advertencias": advertencias_fila,
        })
        curvas[i] = curva
        retorno_por_id[i] = metricas["retorno_total_pct"]
        filas.append(fila)

    # ── Referencia, diferencia y divergencias ───────────────────────────────────────────────
    retorno_ref = retorno_por_id.get(referencia_id) if referencia_id is not None else retorno_bh
    curva_ref = curvas.get(referencia_id) if referencia_id is not None else curva_bh
    ops_ref = ops_por_id.get(referencia_id, []) if referencia_id is not None else ops_bh
    if referencia_id is not None and retorno_ref is None:
        advertencias.append("referencia_sin_datos")

    for fila in filas:
        es_la_referencia = fila["estrategia_id"] == referencia_id
        if fila["estado"] == "definicion_invalida" or retorno_ref is None or curva_ref is None:
            continue
        d = cee.diferencia(fila["retorno_total_pct"], retorno_ref, capital_inicial)
        fila["diferencia_pp"], fila["diferencia_monetaria"], fila["diferencia_relativa_pct"] = (
            d["pp"], d["monetaria"], d["relativa_pct"],
        )
        if es_la_referencia:
            continue
        ops_fila = ops_bh if fila["estrategia_id"] is None else ops_por_id.get(fila["estrategia_id"], [])
        fila["divergencias"] = [
            {"desde": t["desde"], "hasta": t["hasta"], "delta_pp": t["delta_pp"],
             "invertida_pct": t["invertida_pct"], "invertida_referencia_pct": t["invertida_referencia_pct"]}
            for t in cee.divergencias(fechas, curvas[fila["estrategia_id"]], curva_ref, ops_fila, ops_ref)
        ]

    fechas_sub, curvas_sub = cee.submuestrear(fechas, {str(k): v for k, v in curvas.items()})
    for fila in filas:
        fila["curva"] = curvas_sub[str(fila["estrategia_id"])]

    # "Comprar y mantener" es la referencia, no una de las estrategias elegidas: no compite por
    # "mejor" aunque haya rendido más que todas.
    candidatas = [
        f for f in filas
        if f["estrategia_id"] is not None and f["estado"] == "ok" and f["retorno_total_pct"] is not None
    ]
    mejor = None
    if candidatas:
        top = max(candidatas, key=lambda f: f["retorno_total_pct"])
        mejor = {
            "estrategia_id": top["estrategia_id"], "nombre": top["nombre"],
            "retorno_total_pct": top["retorno_total_pct"], "diferencia_pp": top["diferencia_pp"],
            "disclaimer": cee.DISCLAIMER_MEJOR,
        }

    return {**base, "estado": "ok", "fechas": fechas_sub, "filas": filas, "mejor": mejor, "advertencias": advertencias}
