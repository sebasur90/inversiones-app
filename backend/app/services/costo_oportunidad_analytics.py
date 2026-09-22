"""Adaptador para comparar históricamente una cartera contra una referencia (benchmark),
en la misma moneda, en porcentaje y en dinero.

A diferencia de `benchmarks_analytics.get_performance_relativa` (no toca la moneda de la
referencia) y de `opportunity_cost_analytics.get_opportunity_cost` (sólo da el valor final,
no la serie), este módulo:

1. Normaliza la serie de niveles de la referencia a la moneda elegida
   (`costo_oportunidad_engine.normalizar_serie`), para que "Dólar (MEP)" valuado en USD dé
   0% en vez de reflejar la suba del dólar en pesos.
2. Calcula la evolución del valor "si los mismos flujos se hubieran invertido en la
   referencia" punto a punto (`costo_oportunidad_engine.serie_valor_shadow`), ancladas ambas
   series (cartera y referencia) al mismo capital inicial y a los mismos aportes/retiros.
3. Arma las advertencias de homogeneidad que la pantalla muestra explícitamente.

No se modifica `benchmarks_analytics._resolver_fuente` ni los endpoints existentes:
`/performance-relativa`, `/benchmarks-comparacion` y `/opportunity-cost` siguen devolviendo
exactamente lo mismo que antes.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import BenchmarkValor, InstrumentoInversion
from . import risk_engine, costo_oportunidad_engine
from .benchmarks_analytics import (
    MONEDAS_VALIDAS,
    BENCHMARK_DOLAR,
    BENCHMARK_INFLACION,
    BENCHMARK_MONEDA_NATIVA,
    _twr_mensual_por_moneda,
    _filtrar_desde,
)
from .cache import cache_por_sync
from .inversiones_analytics import (
    EPS,
    _movimientos_ordenados,
    _precios_por_ticker,
    _flujos_cashflow,
    _fechas_por_granularidad,
    _fin_de_mes_range,
    _HoldingsTracker,
    _monto_usd,
    _monto_ars,
    _monto_ars_real,
    _valuar_holdings,
    _valuar_holdings_ars,
    _valuar_holdings_ars_real,
    _cer_indice,
    get_configuracion_cartera,
)
from .opportunity_cost_analytics import _mep_indice_serie, _cer_indice_serie


def _serie_nativa_referencia(nombre: str, db: Session) -> tuple[list[tuple[date, float, str]], str]:
    """(serie con moneda por punto, moneda nativa declarada: "ARS" | "USD" | "mixta").

    Mismo despacho que `benchmarks_analytics._resolver_fuente` (que no se toca), pero
    devolviendo niveles en vez de retornos mensuales, y conservando la moneda de cada punto.
    """
    if nombre == BENCHMARK_DOLAR:
        return [(f, v, "ARS") for f, v in _mep_indice_serie(db)], "ARS"
    if nombre == BENCHMARK_INFLACION:
        return [(f, v, "ARS") for f, v in _cer_indice_serie(db)], "ARS"

    es_ticker = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == nombre).first() is not None
    if es_ticker:
        serie = _precios_por_ticker(db).get(nombre, [])
        monedas = {m.upper() for _, _, m in serie}
        if len(monedas) == 1:
            moneda_declarada = next(iter(monedas))
        elif monedas:
            moneda_declarada = "mixta"
        else:
            moneda_declarada = "ARS"
        return [(f, v, m.upper()) for f, v, m in serie], moneda_declarada

    rows = (
        db.query(BenchmarkValor)
        .filter(BenchmarkValor.benchmark == nombre)
        .order_by(BenchmarkValor.fecha)
        .all()
    )
    moneda_nativa = BENCHMARK_MONEDA_NATIVA.get(nombre, "ars").upper()
    return [(r.fecha, float(r.valor), moneda_nativa) for r in rows], moneda_nativa


def _monto_fn_para_moneda(moneda: str, db: Session, mep_cache: dict, cer_cache: dict, cer_hoy: float | None):
    if moneda == "usd":
        return lambda m: _monto_usd(m, db, mep_cache)
    if moneda == "ars_nominal":
        return lambda m: _monto_ars(m, db, mep_cache)
    return lambda m: _monto_ars_real(m, db, cer_cache, mep_cache, cer_hoy)


def _valuar_fn_para_moneda(
    moneda: str,
    precios_por_ticker: dict,
    db: Session,
    mep_cache: dict,
    cer_cache: dict,
    cer_hoy: float | None,
):
    """Uniforma la firma de `_valuar_holdings*` a `(holdings, fecha, costos) -> (valor, aprox, faltante)`."""
    if moneda == "usd":
        return lambda holdings, fecha, costos: _valuar_holdings(holdings, fecha, precios_por_ticker, db, mep_cache, costos)
    if moneda == "ars_nominal":
        return lambda holdings, fecha, costos: _valuar_holdings_ars(holdings, fecha, precios_por_ticker, db, mep_cache, costos)
    return lambda holdings, fecha, costos: _valuar_holdings_ars_real(
        holdings, fecha, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, costos
    )


def _dict_vacio(estado: str, moneda: str, referencia: str | None = None, moneda_nativa_referencia: str | None = None) -> dict:
    return {
        "estado": estado,
        "moneda": moneda,
        "referencia": referencia,
        "moneda_nativa_referencia": moneda_nativa_referencia,
        "periodo_pedido_desde": None,
        "periodo_desde": None,
        "periodo_hasta": None,
        "n_meses": 0,
        "resultado_cartera_pct": None,
        "resultado_referencia_pct": None,
        "diferencia_pp": None,
        "valor_inicial": None,
        "aportes_netos_periodo": None,
        "valor_final_cartera": None,
        "valor_final_referencia": None,
        "diferencia_monetaria": None,
        "serie_indices": [],
        "serie_valores": [],
        "advertencias": [],
    }


@cache_por_sync
def get_costo_oportunidad(cartera: str | None, moneda: str, benchmark: str | None, desde: date | None, db: Session) -> dict:
    """Compara históricamente la cartera contra una referencia, en `moneda`, desde `desde`.

    Devuelve un dict con estados `"ok" | "sin_benchmark" | "sin_movimientos" | "datos_insuficientes"`,
    nunca lanza salvo `moneda` inválida (validado también en el router con 422).
    """
    if moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {moneda}")

    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return _dict_vacio("sin_movimientos", moneda)

    referencia = benchmark
    if referencia is None:
        config = get_configuracion_cartera(cartera, db)
        referencia = config.get("benchmark") if config else None
    if referencia is None:
        return _dict_vacio("sin_benchmark", moneda)

    hoy = date.today()
    mep_cache: dict = {}
    cer_cache: dict = {}
    cer_hoy = _cer_indice(hoy, db, cer_cache)

    serie_nativa, moneda_nativa_declarada = _serie_nativa_referencia(referencia, db)
    if not serie_nativa:
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)

    serie_mep = _mep_indice_serie(db)
    serie_cer = _cer_indice_serie(db)
    serie_norm, descartados_fx = costo_oportunidad_engine.normalizar_serie(
        serie_nativa, moneda, serie_mep, serie_cer, cer_hoy
    )
    if not serie_norm:
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)

    precios_por_ticker = _precios_por_ticker(db)

    # ── Lado % (índices base 100, igual criterio que get_performance_relativa) ──────────
    ret_cartera = _filtrar_desde(
        _twr_mensual_por_moneda(moneda, movs, precios_por_ticker, db, mep_cache, cer_cache, hoy),
        desde,
    )
    if not ret_cartera:
        # Incluye el caso de `_calcular_twr_mensual_ars_real` devolviendo `{}` cuando falta CER.
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)

    boundaries_ref = _fin_de_mes_range(serie_norm[0][0], hoy)
    ret_ref = _filtrar_desde(
        risk_engine.serie_retornos_mensuales_desde_niveles(serie_norm, boundaries_ref), desde
    )

    claves_comunes = sorted(set(ret_cartera) & set(ret_ref))
    if not claves_comunes:
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)

    ret_cartera_comunes = {k: ret_cartera[k] for k in claves_comunes}
    ret_ref_comunes = {k: ret_ref[k] for k in claves_comunes}

    indice_cartera = risk_engine.construir_indice(ret_cartera_comunes, base=100.0)
    indice_ref = risk_engine.construir_indice(ret_ref_comunes, base=100.0)

    resultado_cartera_pct = (indice_cartera[-1][1] / 100.0) - 1 if indice_cartera else None
    resultado_ref_pct = (indice_ref[-1][1] / 100.0) - 1 if indice_ref else None
    diferencia_pp = (
        (resultado_cartera_pct - resultado_ref_pct) * 100
        if resultado_cartera_pct is not None and resultado_ref_pct is not None
        else None
    )
    meses_sin_tenencia = sum(1 for k in claves_comunes if ret_cartera_comunes[k] is None)

    # ── Ancla: cierre del mes anterior al primer mes común (ver §3 del plan) ────────────
    # Sin clampear contra `movs[0].fecha`/`serie_norm[0][0]`: en el caso normal, `ancla`
    # precede a la primera compra a propósito (para que esa compra entre como flujo, no como
    # parte del valor inicial). Forzar `ancla >= movs[0].fecha` rompía justo ese caso.
    primer_anio, primer_mes = claves_comunes[0]
    anio_prev, mes_prev = (primer_anio, primer_mes - 1) if primer_mes > 1 else (primer_anio - 1, 12)
    ancla = risk_engine._ultimo_dia_mes(anio_prev, mes_prev)

    monto_fn = _monto_fn_para_moneda(moneda, db, mep_cache, cer_cache, cer_hoy)
    valuar_fn = _valuar_fn_para_moneda(moneda, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy)

    # ── Lado $: mismo capital inicial y mismos flujos posteriores para ambos lados ──────
    tracker = _HoldingsTracker(movs)
    tracker.avanzar_a(ancla)
    v0, aprox0, falt0 = valuar_fn(tracker.snapshot(), ancla, tracker.costo_snapshot())
    if v0 is None:
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)

    flujos_todos = _flujos_cashflow(movs, monto_fn)
    # Un flujo de exactamente $0 en el ancla (nada que valuar todavía) no debe exigir que la
    # referencia tenga datos justo en esa fecha: `serie_valor_shadow` trataría cualquier
    # flujo sin nivel conocido como "dañado", aunque no aporte nada al cálculo.
    flujo_inicial = [(ancla, -v0)] if abs(v0) > EPS else []
    flujos = flujo_inicial + [(f, m) for f, m in flujos_todos if f > ancla]
    aportes_netos_periodo = -sum(m for f, m in flujos if f > ancla)

    if abs(v0) < EPS and abs(aportes_netos_periodo) < EPS:
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)

    fechas_valuacion = _fechas_por_granularidad(ancla, hoy)

    valores_cartera: list[float | None] = []
    aproximado, precio_faltante = aprox0, falt0
    for f in fechas_valuacion:
        tracker.avanzar_a(f)
        valor, aprox, falt = valuar_fn(tracker.snapshot(), f, tracker.costo_snapshot())
        aproximado = aproximado or aprox
        precio_faltante = precio_faltante or falt
        valores_cartera.append(valor)

    valores_ref = costo_oportunidad_engine.serie_valor_shadow(flujos, serie_norm, fechas_valuacion)

    valor_final_cartera = valores_cartera[-1] if valores_cartera else None
    valor_final_referencia = valores_ref[-1] if valores_ref else None
    if valor_final_referencia is None:
        # Algún flujo cae antes del primer dato de la referencia: no hay con qué valuarlo.
        return _dict_vacio("datos_insuficientes", moneda, referencia, moneda_nativa_declarada)
    diferencia_monetaria = (
        valor_final_cartera - valor_final_referencia
        if valor_final_cartera is not None and valor_final_referencia is not None
        else None
    )

    periodo_desde = ancla
    periodo_hasta = min(risk_engine._ultimo_dia_mes(*claves_comunes[-1]), hoy)

    n_puntos_ref_periodo = sum(1 for f, _, _ in serie_nativa if periodo_desde <= f <= periodo_hasta)
    if n_puntos_ref_periodo == 0:
        n_puntos_ref_periodo = len(serie_nativa)
    dias_entre_puntos = (
        (periodo_hasta - periodo_desde).days / (n_puntos_ref_periodo - 1)
        if n_puntos_ref_periodo > 1 else None
    )

    ctx = costo_oportunidad_engine.ContextoComparacion(
        moneda_destino=moneda,
        moneda_nativa_referencia=moneda_nativa_declarada,
        referencia=referencia,
        periodo_pedido_desde=desde,
        periodo_efectivo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        n_meses=len(claves_comunes),
        n_puntos_referencia=n_puntos_ref_periodo,
        dias_entre_puntos_referencia=dias_entre_puntos,
        puntos_fx_descartados=descartados_fx,
        meses_sin_tenencia=meses_sin_tenencia,
        valuacion_aproximada=aproximado,
        precio_faltante=precio_faltante,
    )
    advertencias = costo_oportunidad_engine.advertencias_homogeneidad(ctx)

    serie_indices = []
    for (fc, ic), (fr, ir) in zip(indice_cartera, indice_ref):
        if fc == fr:
            serie_indices.append({
                "fecha": min(fc, hoy),
                "indice_cartera": round(ic, 2),
                "indice_referencia": round(ir, 2),
            })

    serie_valores = []
    for i, f in enumerate(fechas_valuacion):
        vc, vr = valores_cartera[i], valores_ref[i]
        dif = vc - vr if vc is not None and vr is not None else None
        serie_valores.append({
            "fecha": f,
            "valor_cartera": round(vc, 2) if vc is not None else None,
            "valor_referencia": round(vr, 2) if vr is not None else None,
            "diferencia": round(dif, 2) if dif is not None else None,
        })

    return {
        "estado": "ok",
        "moneda": moneda,
        "referencia": referencia,
        "moneda_nativa_referencia": moneda_nativa_declarada,
        "periodo_pedido_desde": desde,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "n_meses": len(claves_comunes),
        "resultado_cartera_pct": round(resultado_cartera_pct, 4) if resultado_cartera_pct is not None else None,
        "resultado_referencia_pct": round(resultado_ref_pct, 4) if resultado_ref_pct is not None else None,
        "diferencia_pp": round(diferencia_pp, 2) if diferencia_pp is not None else None,
        "valor_inicial": round(v0, 2),
        "aportes_netos_periodo": round(aportes_netos_periodo, 2),
        "valor_final_cartera": round(valor_final_cartera, 2) if valor_final_cartera is not None else None,
        "valor_final_referencia": round(valor_final_referencia, 2) if valor_final_referencia is not None else None,
        "diferencia_monetaria": round(diferencia_monetaria, 2) if diferencia_monetaria is not None else None,
        "serie_indices": serie_indices,
        "serie_valores": serie_valores,
        "advertencias": advertencias,
    }
