# -*- coding: utf-8 -*-
"""Análisis profundo por ticker individual (reutiliza el motor de analytics de cartera).

Patrón adaptador: sin lógica de cálculo propia, filtra movimientos por ticker y orquesta
las funciones ya existentes en inversiones_analytics.py / risk_engine.py / benchmarks_analytics.py.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from ..database import MovimientoInversion, InstrumentoInversion
from . import risk_engine
from .inversiones_analytics import (
    _movimientos_ordenados,
    _precios_por_ticker,
    _precio_conocido,
    _monto_usd,
    _monto_ars,
    _monto_ars_real,
    _valuar_holdings,
    _valuar_holdings_ars,
    _valuar_holdings_ars_real,
    _calcular_twr_mensual,
    _calcular_twr_mensual_ars_real,
    _cer_indice,
    _HoldingsTracker,
    _resumen_sobre_movs,
    get_pnl_realizado_no_realizado,
    get_comisiones,
    EPS,
    TIPOS_INGRESO,
    TIPOS_QUE_CAMBIAN_TENENCIA,
    _fin_de_mes_range,
    _nivel_precio,
    _mep_sheet,
)
from .riesgo_analytics import MONEDAS_VALIDAS
from .benchmarks_analytics import (
    _benchmark_retornos_mensuales,
    _filtrar_desde,
    _performance_relativa_sobre_movs,
)


def _movimientos_ticker(db: Session, cartera: Optional[str], ticker: str) -> List[MovimientoInversion]:
    """Filtra movimientos por ticker dentro de una cartera (o consolidado si cartera=None)."""
    return [m for m in _movimientos_ordenados(db, cartera) if m.ticker == ticker]


def get_ticker_position(ticker: str, cartera: Optional[str], db: Session) -> dict:
    """Bloque 'position': resumen financiero (XIRR/TWR/rendimiento) + metadata de posición.

    Reusa _resumen_sobre_movs (identidad de flujos, maneja tenencia cero correctamente)
    + _HoldingsTracker para cantidad/precio_promedio + precio actual + objetivo/stop-loss.
    """
    movs = _movimientos_ticker(db, cartera, ticker)
    if not movs:
        # Ticker sin movimientos en esta cartera: devolver respuesta "vacía" pero válida
        return {
            "ticker": ticker,
            "nombre": ticker,
            "tipo_instrumento": "—",
            "mercado": "—",
            "moneda": "—",
            "pais": None,
            "sector": None,
            "cantidad_actual": 0.0,
            "precio_promedio": 0.0,
            "precio_actual": None,
            "primera_fecha_movimiento": None,
            "ultima_fecha_movimiento": None,
            "posicion_cerrada": True,
            "objetivo_modo": None,
            "objetivo_valor": None,
            "precio_objetivo": None,
            "pct_a_objetivo": None,
            "objetivo_alcanzado": None,
            "stop_loss_modo": None,
            "stop_loss_valor": None,
            "precio_stop_loss": None,
            "pct_a_stop_loss": None,
            "stop_loss_disparado": None,
            # Herencia de InversionesResumen:
            "valor_actual_usd": 0.0,
            "valor_actual_ars": 0.0,
            "total_invertido_usd": 0.0,
            "total_invertido_ars": 0.0,
            "total_invertido_ars_real": None,
            "ingresos_recibidos_usd": 0.0,
            "ingresos_recibidos_ars": 0.0,
            "rendimiento_simple_usd": None,
            "rendimiento_simple_ars": None,
            "rendimiento_simple_ars_real": None,
            "xirr_usd": None,
            "xirr_ars": None,
            "xirr_ars_real": None,
            "twr_usd": None,
            "twr_ars": None,
            "twr_ars_real": None,
            "valor_benchmark_usd_ars": None,
            "tiene_precios_desactualizados": False,
        }

    # Resumen financiero (reutiliza la identidad XIRR/TWR, maneja tenencia 0)
    resumen = _resumen_sobre_movs(movs, db)

    # Metadata de posición (usando _HoldingsTracker, NO manual como get_rendimiento_por_ticker)
    hoy = date.today()
    tracker = _HoldingsTracker(movs)
    tracker.avanzar_a(hoy)
    cantidad_actual = tracker.snapshot().get(ticker, 0.0)
    precio_promedio, moneda_costo = tracker.costo_snapshot().get(ticker, (0.0, "USD"))

    # Instrumento y precio actual
    instrumento = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    precios_por_ticker = _precios_por_ticker(db)
    info = _precio_conocido(precios_por_ticker.get(ticker), hoy) if precios_por_ticker.get(ticker) else None
    precio_actual = info[1] if info else None  # Puede ser None sin descartar el bloque

    # Objetivo y stop-loss
    precio_objetivo, pct_a_objetivo, objetivo_alcanzado = _nivel_precio(
        instrumento.objetivo_modo if instrumento else None,
        instrumento.objetivo_valor if instrumento else None,
        precio_promedio,
        precio_actual if precio_actual is not None else precio_promedio,
        alcanzado_si_mayor=True,
    )
    precio_stop_loss, pct_a_stop_loss, stop_loss_disparado = _nivel_precio(
        instrumento.stop_loss_modo if instrumento else None,
        instrumento.stop_loss_valor if instrumento else None,
        precio_promedio,
        precio_actual if precio_actual is not None else precio_promedio,
        alcanzado_si_mayor=False,
    )

    return {
        **resumen,
        "ticker": ticker,
        "nombre": instrumento.nombre if instrumento else ticker,
        "tipo_instrumento": instrumento.tipo_instrumento if instrumento else "—",
        "mercado": instrumento.mercado if instrumento else "—",
        "moneda": instrumento.moneda if instrumento else moneda_costo,
        "pais": instrumento.pais if instrumento else None,
        "sector": instrumento.sector if instrumento else None,
        "cantidad_actual": round(cantidad_actual, 8),
        "precio_promedio": round(precio_promedio, 6),
        "precio_actual": round(precio_actual, 6) if precio_actual is not None else None,
        "primera_fecha_movimiento": movs[0].fecha if movs else None,
        "ultima_fecha_movimiento": movs[-1].fecha if movs else None,
        "posicion_cerrada": abs(cantidad_actual) < EPS,
        "objetivo_modo": instrumento.objetivo_modo if instrumento else None,
        "objetivo_valor": float(instrumento.objetivo_valor) if instrumento and instrumento.objetivo_valor is not None else None,
        "precio_objetivo": round(precio_objetivo, 6) if precio_objetivo is not None else None,
        "pct_a_objetivo": round(pct_a_objetivo, 4) if pct_a_objetivo is not None else None,
        "objetivo_alcanzado": objetivo_alcanzado,
        "stop_loss_modo": instrumento.stop_loss_modo if instrumento else None,
        "stop_loss_valor": float(instrumento.stop_loss_valor) if instrumento and instrumento.stop_loss_valor is not None else None,
        "precio_stop_loss": round(precio_stop_loss, 6) if precio_stop_loss is not None else None,
        "pct_a_stop_loss": round(pct_a_stop_loss, 4) if pct_a_stop_loss is not None else None,
        "stop_loss_disparado": stop_loss_disparado,
    }


def get_ticker_performance(ticker: str, cartera: Optional[str], db: Session) -> dict:
    """Bloque 'performance': descomposición PnL + comisiones.

    Filtra get_pnl_realizado_no_realizado y get_comisiones por ticker sin reimplementar.
    Las comisiones ya están neteadas en realizado/no_realizado via _monto_ajustado.
    """
    pnl = get_pnl_realizado_no_realizado(cartera, db)
    comisiones = get_comisiones(cartera, db)

    # Buscar entrada por ticker en PnL
    pnl_item = next((i for i in pnl["por_ticker"] if i["ticker"] == ticker), None)
    com_item = next((c for c in comisiones["por_ticker"] if c["ticker"] == ticker), None)

    if pnl_item is None:
        # Ticker sin PnL (posición 100% vendida o sin tenencia inicial):
        # get_pnl_realizado_no_realizado hace `continue` si no hay precio actual
        # devolver estado explícito
        pnl_item = {
            "ticker": ticker,
            "nombre": ticker,
            "realizado_usd": 0.0,
            "no_realizado_usd": None,
            "ingresos_usd": 0.0,
            "total_usd": 0.0,
            "realizado_ars": 0.0,
            "no_realizado_ars": None,
            "ingresos_ars": 0.0,
            "total_ars": None,
        }

    return {
        **pnl_item,
        "comisiones_usd": com_item["total_usd"] if com_item else 0.0,
        "comisiones_ars": com_item["total_ars"] if com_item else 0.0,
        "precio_actual_faltante": pnl_item.get("no_realizado_usd") is None,
    }


def get_ticker_riesgo(
    ticker: str, cartera: Optional[str], moneda: str, benchmark: Optional[str], db: Session
) -> dict:
    """Bloque 'risk': TWR mensual encadenado + risk_engine.

    Filtra movimientos por ticker y delega en risk_engine con el mismo patrón que
    riesgo_analytics.get_riesgo (pero con movs ya filtrados a un ticker).
    El benchmark se alinea "desde la primera compra" del ticker.
    """
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}")

    movs = _movimientos_ticker(db, cartera, ticker)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()

    # TWR mensual encadenado por moneda
    if moneda == "usd":
        retornos_por_mes = _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_usd, _valuar_holdings)
    elif moneda == "ars_nominal":
        retornos_por_mes = _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_ars, _valuar_holdings_ars)
    else:  # ars_real
        cer_hoy = _cer_indice(hoy, db, cer_cache)
        retornos_por_mes = _calcular_twr_mensual_ars_real(movs, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, hoy)

    retornos_validos = {k: v for k, v in retornos_por_mes.items() if v is not None}
    retornos_lista = [retornos_validos[k] for k in sorted(retornos_validos)]
    n_meses = len(retornos_validos)

    # Construir índice e índices de riesgo (drawdown, volatilidad, etc.)
    indice = risk_engine.construir_indice(retornos_por_mes)
    drawdown = risk_engine.calcular_drawdown(indice)
    drawdown["serie"] = risk_engine.serie_drawdown(indice) if drawdown["estado"] == "ok" else []
    volatilidad = risk_engine.calcular_volatilidad(retornos_lista)
    sortino = risk_engine.calcular_sortino(retornos_lista)
    retorno_anualizado = risk_engine.calcular_retorno_anualizado(indice)
    calmar = risk_engine.calcular_calmar(retorno_anualizado, drawdown.get("maximo"))
    mejores_peores = risk_engine.mejores_peores_periodos(retornos_validos)
    frecuencia = risk_engine.frecuencia_positivos_negativos(retornos_lista)

    # Sharpe vs benchmark (alineado desde la primera compra del ticker)
    benchmark_retorno_anualizado = None
    if benchmark and movs:
        desde_fecha = movs[0].fecha  # Primera compra del ticker
        retornos_benchmark = _benchmark_retornos_mensuales(benchmark, db, hoy)
        retornos_benchmark = _filtrar_desde(retornos_benchmark, desde_fecha)
        sharpe = risk_engine.calcular_sharpe_vs_benchmark(retornos_validos, retornos_benchmark, benchmark)
        if retornos_benchmark and sharpe["estado"] == "ok":
            indice_benchmark = risk_engine.construir_indice(retornos_benchmark)
            benchmark_retorno_anualizado = risk_engine.calcular_retorno_anualizado(indice_benchmark)
    else:
        sharpe = {"estado": "sin_benchmark", "valor": None, "benchmark": None, "n_obs": 0}

    return {
        "frecuencia": "mensual",
        "moneda": moneda,
        "benchmark_usado": benchmark if sharpe["estado"] == "ok" else None,
        "n_meses_historia": n_meses,
        "drawdown": drawdown,
        "volatilidad": volatilidad,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "benchmark_retorno_anualizado": round(benchmark_retorno_anualizado, 4) if benchmark_retorno_anualizado is not None else None,
        "mejores_periodos": mejores_peores["mejores"],
        "peores_periodos": mejores_peores["peores"],
        "frecuencia_positivos_negativos": frecuencia,
    }


def get_ticker_performance_relativa(
    ticker: str, cartera: Optional[str], moneda: str, benchmark: Optional[str], db: Session
) -> dict:
    """Bloque 'performance relativa': comparación contra benchmark.

    Delega en _performance_relativa_sobre_movs con movs ya filtrados por ticker,
    alineando desde la primera compra del ticker.
    """
    movs = _movimientos_ticker(db, cartera, ticker)
    desde = movs[0].fecha if movs else None
    return _performance_relativa_sobre_movs(movs, cartera, moneda, benchmark, desde, db)


def get_ticker_historico(ticker: str, cartera: Optional[str], desde: Optional[date], db: Session) -> dict:
    """Bloque 'histórico': serie de precio + valor de posición + rendimiento acumulado.

    Combina:
    - Precio nominal/USD/CER (como get_precios_historicos_ticker)
    - Valor de posición en cada fecha (via _HoldingsTracker + _valuar_holdings)
    - Rendimiento acumulado (walk de capital neto aportado, como get_evolucion)
    """
    from datetime import timedelta
    from ..database import PrecioInstrumento

    movs = _movimientos_ticker(db, cartera, ticker)
    hoy = date.today()

    # Fetch price history
    desde_fecha = desde if desde is not None else hoy - timedelta(days=3650)
    rows = db.query(PrecioInstrumento).filter(
        PrecioInstrumento.ticker == ticker,
        PrecioInstrumento.fecha >= desde_fecha,
    ).order_by(PrecioInstrumento.fecha).all()

    instrumento = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    moneda = instrumento.moneda if instrumento else "ARS"

    mep_cache: dict = {}
    cer_cache: dict = {}
    cer_hoy = _cer_indice(hoy, db, cer_cache)

    # Build holdings tracker and capital walk
    tracker = _HoldingsTracker(movs)
    capital_neto = 0.0
    capital_por_fecha: Dict[date, float] = {}

    for mov in movs:
        if mov.fecha > hoy:
            continue
        capital_neto += _monto_usd(mov, db, mep_cache) or 0.0  # Sumar todos los flujos
        capital_por_fecha[mov.fecha] = capital_neto

    precios_por_ticker = _precios_por_ticker(db)

    puntos = []
    for row in rows:
        precio_nominal = float(row.precio)
        precio_usd: float | None = None
        precio_cer: float | None = None

        if moneda == "ARS":
            mep = _mep_sheet(row.fecha, db, mep_cache)
            if mep and mep > 0:
                precio_usd = precio_nominal / mep
            if cer_hoy is not None:
                cer_fecha = _cer_indice(row.fecha, db, cer_cache)
                if cer_fecha is not None and cer_fecha > 0:
                    precio_cer = precio_nominal * (cer_hoy / cer_fecha)
        else:  # USD
            precio_usd = precio_nominal
            mep = _mep_sheet(row.fecha, db, mep_cache)
            if mep and mep > 0:
                precio_cer = precio_nominal * mep

        # Valor de posición en esa fecha (holdings + precio)
        tracker.avanzar_a(row.fecha)
        tenencia = tracker.snapshot().get(ticker, 0.0)
        valor_posicion_usd, _, _ = _valuar_holdings(
            {ticker: tenencia}, row.fecha, precios_por_ticker, db, mep_cache, tracker.costo_snapshot()
        ) if abs(tenencia) > EPS else (0.0, False, False)

        # Valor de posición en ARS (si aplica)
        valor_posicion_ars = None
        if valor_posicion_usd and valor_posicion_usd > 0:
            mep = _mep_sheet(row.fecha, db, mep_cache)
            if mep:
                valor_posicion_ars = valor_posicion_usd * mep

        # Rendimiento acumulado
        capital_hasta_fecha = capital_por_fecha.get(row.fecha, capital_neto)
        rendimiento_acumulado_pct = (valor_posicion_usd - capital_hasta_fecha) / capital_hasta_fecha if abs(capital_hasta_fecha) > EPS else None

        puntos.append({
            "fecha": row.fecha,
            "precio_nominal": round(precio_nominal, 4),
            "precio_usd": round(precio_usd, 4) if precio_usd is not None else None,
            "precio_cer": round(precio_cer, 4) if precio_cer is not None else None,
            "valor_posicion_usd": round(valor_posicion_usd, 2) if valor_posicion_usd > 0 else None,
            "valor_posicion_ars": round(valor_posicion_ars, 2) if valor_posicion_ars is not None else None,
            "rendimiento_acumulado_pct": round(rendimiento_acumulado_pct, 4) if rendimiento_acumulado_pct is not None else None,
        })

    return {"ticker": ticker, "moneda": moneda, "puntos": puntos}
