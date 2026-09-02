"""Orquestación de descomposición FX: base de datos y sesión.

Reutiliza las funciones "privadas" de inversiones_analytics.py (mismo patrón que
contribucion_analytics.py/benchmarks_analytics.py) para evitar re-derivar valuaciones.
"""
from datetime import date
import calendar
from sqlalchemy.orm import Session

from ..database import IndiceMercado
from . import fx_decomposition_engine, risk_engine
from .inversiones_analytics import (
    _movimientos_ordenados,
    _precios_por_ticker,
    _calcular_twr_mensual,
    _monto_usd,
    _monto_ars,
    _valuar_holdings,
    _valuar_holdings_ars,
    _mep_sheet,
    UMBRAL_APROXIMADO_DIAS,
    get_rendimiento_por_ticker,
)


def _filtrar_desde(
    retornos_por_mes: dict[tuple[int, int], float | None],
    desde: date | None,
) -> dict[tuple[int, int], float | None]:
    """Filtra retornos mensuales para excluir meses anteriores a `desde`."""
    if desde is None:
        return retornos_por_mes
    return {(a, m): r for (a, m), r in retornos_por_mes.items() if (a, m) >= (desde.year, desde.month)}


def _dias_carry_forward(fecha_lookup: date, fecha_observada: date) -> int:
    """Devuelve cuántos días lleva el carry-forward (cuántos días atrás es la observación)."""
    return (fecha_lookup - fecha_observada).days




def get_descomposicion_fx(
    cartera: str | None,
    desde: date | None,
    db: Session,
) -> dict:
    """Descomposición FX a nivel cartera/consolidado.

    Calcula retornos mensuales en USD/ARS nominal, filtra por `desde`,
    compone con indice, y descompone via motor puro.
    """
    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    hoy = date.today()

    # Calcular TWR mensuales completos (USD y ARS nominal)
    twr_mensuales_usd = _calcular_twr_mensual(
        movs, precios_por_ticker, db, mep_cache, hoy, _monto_usd, _valuar_holdings
    )
    twr_mensuales_ars = _calcular_twr_mensual(
        movs, precios_por_ticker, db, mep_cache, hoy, _monto_ars, _valuar_holdings_ars
    )

    # Filtrar por `desde`
    twr_usd_filtrado = _filtrar_desde(twr_mensuales_usd, desde)
    twr_ars_filtrado = _filtrar_desde(twr_mensuales_ars, desde)

    # Componer en retornos de período
    twr_usd_periodo = None
    twr_ars_periodo = None

    if twr_usd_filtrado:
        indice_usd = risk_engine.construir_indice(twr_usd_filtrado, base=100.0)
        twr_usd_periodo = (indice_usd[-1][1] / 100.0) - 1 if indice_usd else None

    if twr_ars_filtrado:
        indice_ars = risk_engine.construir_indice(twr_ars_filtrado, base=100.0)
        twr_ars_periodo = (indice_ars[-1][1] / 100.0) - 1 if indice_ars else None

    # Resolver fechas de inicio/fin del período
    periodo_desde = None
    periodo_hasta = hoy
    if twr_usd_filtrado or twr_ars_filtrado:
        meses_claves = sorted(set(list(twr_usd_filtrado.keys()) + list(twr_ars_filtrado.keys())))
        if meses_claves:
            primer_mes = meses_claves[0]
            periodo_desde = date(primer_mes[0], primer_mes[1], 1)

    # Buscar MEP inicio/fin
    mep_inicio = None
    mep_inicio_fecha = None
    mep_fin = None
    mep_fin_fecha = None
    mep_aproximado = False

    if periodo_desde:
        # MEP inicio: último día del mes anterior
        if periodo_desde.month == 1:
            mes_anterior = date(periodo_desde.year - 1, 12, 1)
        else:
            mes_anterior = date(periodo_desde.year, periodo_desde.month - 1, 1)
        ultimo_dia_mes_anterior = date(
            mes_anterior.year,
            mes_anterior.month,
            calendar.monthrange(mes_anterior.year, mes_anterior.month)[1]
        )

        row_mep_inicio = (
            db.query(IndiceMercado)
            .filter(
                IndiceMercado.mep.isnot(None),
                IndiceMercado.fecha <= ultimo_dia_mes_anterior
            )
            .order_by(IndiceMercado.fecha.desc())
            .first()
        )
        if row_mep_inicio:
            mep_inicio = float(row_mep_inicio.mep)
            mep_inicio_fecha = row_mep_inicio.fecha
            dias_cf = _dias_carry_forward(ultimo_dia_mes_anterior, mep_inicio_fecha)
            if dias_cf > UMBRAL_APROXIMADO_DIAS:
                mep_aproximado = True

    # MEP fin: hoy
    row_mep_fin = (
        db.query(IndiceMercado)
        .filter(
            IndiceMercado.mep.isnot(None),
            IndiceMercado.fecha <= hoy
        )
        .order_by(IndiceMercado.fecha.desc())
        .first()
    )
    if row_mep_fin:
        mep_fin = float(row_mep_fin.mep)
        mep_fin_fecha = row_mep_fin.fecha
        dias_cf = _dias_carry_forward(hoy, mep_fin_fecha)
        if dias_cf > UMBRAL_APROXIMADO_DIAS:
            mep_aproximado = True

    # Llamar motor puro
    resultado = fx_decomposition_engine.descomponer_retorno_periodo(
        twr_ars=twr_ars_periodo,
        twr_usd=twr_usd_periodo,
        mep_inicio=mep_inicio,
        mep_fin=mep_fin,
    )

    # Completar campos extras
    resultado["periodo_desde"] = periodo_desde
    resultado["periodo_hasta"] = periodo_hasta
    resultado["mep_aproximado"] = resultado["mep_aproximado"] or mep_aproximado

    return resultado


def get_descomposicion_fx_por_posicion(
    cartera: str | None,
    db: Session,
) -> dict:
    """Descomposición FX a nivel posición (ticker).

    Reutiliza get_rendimiento_por_ticker, calcula MEP promedio ponderado de compras,
    y aplica descomposición simple (aproximada).
    """
    # Obtener datos base de rendimiento por ticker
    rendimientos_por_ticker = get_rendimiento_por_ticker(cartera, db)

    movs = _movimientos_ordenados(db, cartera)
    mep_cache: dict = {}

    # Construir un diccionario de MEP promedio por ticker
    mep_promedio_por_ticker: dict[str, float] = {}
    for mov in movs:
        if mov.tipo_movimiento != "compra":
            continue
        mep = _mep_sheet(mov.fecha, db, mep_cache)
        if mep is None:
            continue

        monto_usd = _monto_usd(mov, db, mep_cache)
        if monto_usd is None:
            continue

        ticker = mov.ticker
        if ticker not in mep_promedio_por_ticker:
            mep_promedio_por_ticker[ticker] = 0.0

        # Acumular valor ponderado
        mep_promedio_por_ticker[ticker] += mep * monto_usd

    # Normalizar pesos (calcular promedio)
    total_usd_por_ticker: dict[str, float] = {}
    for mov in movs:
        if mov.tipo_movimiento != "compra":
            continue
        monto_usd = _monto_usd(mov, db, mep_cache)
        if monto_usd is None:
            continue
        ticker = mov.ticker
        if ticker not in total_usd_por_ticker:
            total_usd_por_ticker[ticker] = 0.0
        total_usd_por_ticker[ticker] += monto_usd

    for ticker in mep_promedio_por_ticker:
        if total_usd_por_ticker.get(ticker, 0) > 0:
            mep_promedio_por_ticker[ticker] /= total_usd_por_ticker[ticker]

    # Resolver MEP actual
    hoy = date.today()
    mep_actual = _mep_sheet(hoy, db, mep_cache)

    # Procesar cada posición
    posiciones = []
    for item in rendimientos_por_ticker:
        ticker = item["ticker"]
        moneda = item["moneda"]
        rendimiento_simple_ars = item.get("rendimiento_simple_ars")
        rendimiento_simple_usd = item.get("rendimiento_simple_usd")
        mep_prom = mep_promedio_por_ticker.get(ticker)

        resultado_posicion = fx_decomposition_engine.descomponer_retorno_posicion(
            rendimiento_simple_ars=rendimiento_simple_ars,
            rendimiento_simple_usd=rendimiento_simple_usd,
            moneda=moneda,
            mep_promedio_compra=mep_prom,
            mep_actual=mep_actual,
        )

        posicion_dict = {
            "ticker": ticker,
            "moneda": moneda,
            **resultado_posicion,
        }
        posiciones.append(posicion_dict)

    return {
        "posiciones": posiciones,
    }
