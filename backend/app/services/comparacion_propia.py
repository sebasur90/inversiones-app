"""Lo que hiciste vs. lo que habría hecho la estrategia vs. comprar y mantener, ciclo por ciclo.

Cruza los ciclos de tenencia del usuario (`operaciones_grafico`) con las curvas de un backtest sobre
la misma serie. Para cada ciclo que toca el período del backtest se mide el retorno de la curva de la
estrategia y el de la de comprar y mantener **entre las mismas dos fechas**: de la rueda en que el
usuario entró a la rueda en que salió (o a la última, si sigue adentro).

Aclaraciones que la pantalla repite: el resultado del usuario es real, en USD MEP y con comisiones,
sobre todo el ciclo; el de la estrategia es sobre el precio de la serie del backtest. Un ciclo que
empezó antes del período queda `recortado`: el del usuario cuenta todo el ciclo y las curvas sólo
desde que arranca el período. Si la estrategia no estaba posicionada en ese tramo, su retorno es 0.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..database import MovimientoInversion

# Cuántos días puede distar la última barra del backtest de hoy sin considerar que el período
# "terminó antes" de tu posición abierta (fin de semana largo + rezago de carga).
_TOLERANCIA_DIAS_FIN_SERIE = 5


def _indice_desde(fechas: list[date], fecha: date) -> int | None:
    """Primera barra con fecha >= `fecha`, o None si es posterior a la última."""
    for i, f in enumerate(fechas):
        if f >= fecha:
            return i
    return None


def _retorno(curva: list[float], i0: int, i1: int) -> float | None:
    base = curva[i0]
    return (curva[i1] / base - 1.0) * 100.0 if base else None


def comparar(
    ciclos: list[dict], fechas: list[date], indice_desde: int,
    curva_estrategia: list[float], curva_buy_hold: list[float],
) -> list[dict]:
    """Una fila por ciclo del usuario que toca el período del backtest
    (`fechas[indice_desde:]`). Las curvas están alineadas 1:1 con `fechas`."""
    if not fechas or indice_desde >= len(fechas) or len(curva_estrategia) != len(fechas):
        return []
    inicio, fin = fechas[indice_desde], fechas[-1]
    filas: list[dict] = []

    for c in ciclos:
        hasta = c["hasta"] or fin
        if c["desde"] > fin or hasta < inicio:
            continue
        recortado = c["desde"] < inicio
        # El otro extremo: un ciclo que sigue (o terminó) después de la última barra del backtest.
        # Tu resultado se mide hasta hoy / hasta tu venta y las curvas cortan en `fin`: sin avisarlo
        # se comparaban períodos distintos. Un día o dos de rezago de la serie respecto de hoy no
        # cuentan (la última rueda cargada suele ser la de ayer).
        if c["hasta"] is None:
            recortado_fin = (date.today() - fin).days > _TOLERANCIA_DIAS_FIN_SERIE
        else:
            recortado_fin = c["hasta"] > fin
        i0 = max(_indice_desde(fechas, c["desde"]) or 0, indice_desde)
        i1 = _indice_desde(fechas, hasta)
        i1 = len(fechas) - 1 if i1 is None else i1
        if i1 < i0:
            continue
        filas.append({
            "ciclo": c["ciclo"], "desde": c["desde"], "hasta": c["hasta"], "abierto": c["abierto"],
            "tramo_desde": fechas[i0], "tramo_hasta": fechas[i1], "recortado": recortado,
            "recortado_fin": recortado_fin,
            "tu_resultado_usd": c["resultado_usd"], "tu_resultado_pct": c["resultado_pct"],
            "estrategia_pct": _retorno(curva_estrategia, i0, i1),
            "buy_hold_pct": _retorno(curva_buy_hold, i0, i1),
        })
    return filas


def para_backtest(ticker: str, variante: str, resultado: dict, db: Session) -> list[dict] | None:
    """`mis_ciclos` de un resultado de `ejecutar_backtest`: `None` si el usuario nunca operó el
    ticker, y de lo contrario una fila por ciclo suyo que toca el período (puede ser vacía)."""
    from . import operaciones_grafico   # import tardío: operaciones_grafico no depende de este módulo

    opero = db.query(MovimientoInversion.id).filter(
        MovimientoInversion.ticker == ticker,
        MovimientoInversion.tipo_movimiento.in_(("compra", "venta", "amortizacion")),
    ).first() is not None
    if not opero:
        return None
    ciclos = operaciones_grafico.get_operaciones_grafico(ticker, variante, db)["ciclos"]
    return comparar(
        ciclos, [b["fecha"] for b in resultado["barras"]], resultado.get("indice_desde", 0),
        [p["valor"] for p in resultado["curva_equity"]], [p["valor"] for p in resultado["curva_buy_hold"]],
    )
