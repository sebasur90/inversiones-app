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


def _ultimo_dia(anio: int, mes: int) -> date:
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def _mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def _tiene_huecos(claves_con_tenencia: list[tuple[int, int]]) -> bool:
    """True si entre el primer y el último mes con tenencia hay algún mes sin ella."""
    if len(claves_con_tenencia) < 2:
        return False
    primero, ultimo = claves_con_tenencia[0], claves_con_tenencia[-1]
    meses_totales = (ultimo[0] - primero[0]) * 12 + (ultimo[1] - primero[1]) + 1
    return meses_totales != len(claves_con_tenencia)


def _variacion_mep_solo_con_tenencia(
    claves_con_tenencia: list[tuple[int, int]], db: Session, mep_cache: dict,
) -> float | None:
    """Variación compuesta del MEP sumando únicamente los meses en que había cartera.

    Si el período incluye meses sin tenencia, el índice de la cartera queda plano en esos meses
    pero el MEP sigue moviéndose: medir `MEP_fin / MEP_inicio` de punta a punta le atribuía a la
    cartera una suba del dólar que no vivió (por ejemplo, vendés todo en 2024 y recomprás en 2025).
    Devuelve `None` si falta el MEP de algún mes.
    """
    factor = 1.0
    for anio, mes in claves_con_tenencia:
        mep_fin_mes = _mep_sheet(_ultimo_dia(anio, mes), db, mep_cache)
        a_prev, m_prev = _mes_anterior(anio, mes)
        mep_ini_mes = _mep_sheet(_ultimo_dia(a_prev, m_prev), db, mep_cache)
        if mep_fin_mes is None or mep_ini_mes is None or mep_ini_mes <= 0:
            return None
        factor *= mep_fin_mes / mep_ini_mes
    return factor - 1.0




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

    # Meses del período en que había cartera (con retorno medido).
    claves_con_tenencia = sorted(
        k for k, v in twr_usd_filtrado.items() if v is not None and twr_ars_filtrado.get(k) is not None
    )
    advertencias: list[str] = []
    mep_para_motor = (mep_inicio, mep_fin)
    if _tiene_huecos(claves_con_tenencia):
        variacion = _variacion_mep_solo_con_tenencia(claves_con_tenencia, db, mep_cache)
        if variacion is not None:
            # El motor sólo usa el cociente: se le pasa la variación compuesta de los meses con cartera.
            mep_para_motor = (1.0, 1.0 + variacion)
            advertencias.append(
                "En este período hubo meses sin cartera (vendiste todo y volviste a comprar). El efecto del "
                "dólar cuenta sólo los meses en que tenías posiciones."
            )
        else:
            advertencias.append(
                "En este período hubo meses sin cartera y falta el MEP de alguno: el efecto del dólar "
                "incluye meses en que no tenías posiciones y puede estar sobrestimado."
            )

    # Llamar motor puro
    resultado = fx_decomposition_engine.descomponer_retorno_periodo(
        twr_ars=twr_ars_periodo,
        twr_usd=twr_usd_periodo,
        mep_inicio=mep_para_motor[0],
        mep_fin=mep_para_motor[1],
    )

    # Completar campos extras
    resultado["periodo_desde"] = periodo_desde
    resultado["periodo_hasta"] = periodo_hasta
    resultado["mep_aproximado"] = resultado["mep_aproximado"] or mep_aproximado
    # Los MEP que se muestran siguen siendo los de las puntas del período.
    if resultado["estado"] == "ok":
        resultado["mep_inicio"] = mep_inicio
        resultado["mep_fin"] = mep_fin
    resultado["advertencias"] = advertencias

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

    # MEP promedio de compra de la POSICIÓN ABIERTA de cada ticker, ponderado por USD. Cada venta o
    # amortización quita la fracción vendida del capital (igual que el costo remanente de
    # `_recorrer_movs_ticker`) y, al cerrarse la posición, el promedio se reinicia: antes se
    # promediaban todas las compras de la historia, incluidas las de lotes ya vendidos, y tras
    # cerrar y recomprar el efecto FX de la posición no correspondía a la tenencia actual.
    estado_por_ticker: dict[str, dict[str, float]] = {}
    for mov in movs:
        st = estado_por_ticker.setdefault(mov.ticker, {"cant": 0.0, "usd": 0.0, "mep_x_usd": 0.0})
        cant = float(mov.cantidad or 0)
        if mov.tipo_movimiento == "compra":
            st["cant"] += cant
            mep = _mep_sheet(mov.fecha, db, mep_cache)
            monto_usd = _monto_usd(mov, db, mep_cache)
            if mep is not None and monto_usd is not None:
                st["usd"] += monto_usd
                st["mep_x_usd"] += mep * monto_usd
        elif mov.tipo_movimiento in ("venta", "amortizacion"):
            if st["cant"] > 1e-9:
                resto = 1.0 - min(cant / st["cant"], 1.0)
                st["usd"] *= resto
                st["mep_x_usd"] *= resto
            st["cant"] = max(st["cant"] - cant, 0.0)

    mep_promedio_por_ticker: dict[str, float] = {
        ticker: st["mep_x_usd"] / st["usd"]
        for ticker, st in estado_por_ticker.items()
        if st["usd"] > 1e-9
    }

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
