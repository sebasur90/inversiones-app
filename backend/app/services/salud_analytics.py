"""Adaptador entre datos reales (Session/DB) y el motor puro `salud_engine`.

Orquesta los analytics existentes (patrimonio, riesgo, concentración, exposición, rebalanceo,
vencimientos, comisiones, calidad de datos) y les agrega un inventario de posiciones que sí
incluye lo que `get_exposicion` descarta en silencio (sin precio, sin ficha) — porque eso es
justamente lo que esta pantalla tiene que señalar. Mismo patrón que `diagnostico_analytics.py`.
"""
from datetime import date
from sqlalchemy.orm import Session

from ..database import InstrumentoInversion, PrecioInstrumento
from . import salud_engine
from .cache import cache_por_sync
from .calidad_datos import get_calidad_datos
from .contribucion_analytics import get_concentracion
from .diagnostico_engine import calcular_ratio_comisiones
from .riesgo_analytics import get_riesgo
from .inversiones_analytics import (
    EPS,
    _holdings_por_cartera_ticker,
    _movimientos_ordenados,
    _precio_conocido,
    _precios_por_ticker,
    _to_usd,
    get_comisiones,
    get_configuracion_cartera,
    get_exposicion,
    get_rebalanceo,
    get_resumen,
    get_vencimientos,
)


def _ultimo_precio_por_ticker(db: Session) -> dict[str, str]:
    """Fuente (`"sheet"|"iol"|"api"`) del último precio cargado por ticker.

    Consulta puntual en vez de extender `_precios_por_ticker`: ese caché vive en `db.info` y lo
    usan ocho analytics distintos por request — no conviene ensancharlo sólo para el dato de
    procedencia que necesita esta pantalla.
    """
    rows = db.query(PrecioInstrumento).order_by(PrecioInstrumento.ticker, PrecioInstrumento.fecha).all()
    fuentes: dict[str, str] = {}
    for row in rows:
        fuentes[row.ticker] = row.fuente  # el último de la iteración ordenada por fecha gana
    return fuentes


def _inventario_posiciones(cartera: str | None, db: Session) -> list[dict]:
    """Tenencias de hoy con su clasificación (tipo/sector/país/moneda/vencimiento) y estado de
    precio. A diferencia de `get_exposicion`/`_clasificados_valorizados`, **no descarta** las
    posiciones sin precio conocido o sin ficha en `Instrumentos`: son justamente las que hay que
    mostrar en "Calidad de datos" y en las observaciones.
    """
    hoy = date.today()
    movs = _movimientos_ordenados(db, cartera)
    holdings = _holdings_por_cartera_ticker(movs, hoy)
    precios_por_ticker = _precios_por_ticker(db)
    fuentes = _ultimo_precio_por_ticker(db)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}
    mep_cache: dict = {}

    cantidad_por_ticker: dict[str, float] = {}
    for (_cart, ticker), cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        cantidad_por_ticker[ticker] = cantidad_por_ticker.get(ticker, 0.0) + cantidad

    items = []
    total_usd = 0.0
    for ticker in sorted(cantidad_por_ticker):
        cantidad = cantidad_por_ticker[ticker]
        inst = instrumentos.get(ticker)
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, hoy) if precios_sorted else None

        valor_usd = None
        fecha_precio = None
        dias_precio = None
        if info is not None:
            fecha_precio, precio, moneda = info
            dias_precio = (hoy - fecha_precio).days
            valor_usd = _to_usd(precio * cantidad, moneda, hoy, db, mep_cache)

        items.append({
            "ticker": ticker,
            "nombre": inst.nombre if inst else ticker,
            "tipo_instrumento": inst.tipo_instrumento if inst else None,
            "sector": inst.sector if inst else None,
            "pais": inst.pais if inst else None,
            "moneda": inst.moneda if inst else None,
            "fecha_vencimiento": inst.fecha_vencimiento if inst else None,
            "cantidad": cantidad,
            "valor_usd": valor_usd,
            "fecha_precio": fecha_precio,
            "dias_precio": dias_precio,
            "fuente_precio": fuentes.get(ticker),
            "sin_precio": valor_usd is None,
            "sin_ficha": inst is None,
        })
        if valor_usd is not None:
            total_usd += valor_usd

    for item in items:
        item["peso_pct"] = (
            round(item["valor_usd"] / total_usd * 100, 2)
            if item["valor_usd"] is not None and total_usd > EPS
            else None
        )

    return items


@cache_por_sync
def get_salud(cartera: str | None, db: Session) -> dict:
    """Orquesta y agrega "Salud de cartera": estados por dimensión + observaciones.

    `cartera=None` = Consolidado. Todas las llamadas delegan en analytics existentes; no se
    recalcula ninguna métrica financiera acá, sólo se interpretan sus resultados.
    """
    resumen = get_resumen(cartera, db)
    config = get_configuracion_cartera(cartera, db)
    benchmark = config.get("benchmark")

    riesgo = get_riesgo(cartera, "usd", benchmark, db)
    concentracion = get_concentracion(cartera, db)
    exposicion = get_exposicion(cartera, db)
    rebalanceo = get_rebalanceo(cartera, db)
    vencimientos = get_vencimientos(cartera, db)
    comisiones = get_comisiones(cartera, db)
    calidad = get_calidad_datos(db)
    inventario = _inventario_posiciones(cartera, db)

    ejes = {eje["eje"]: eje["items"] for eje in exposicion.get("ejes", [])}
    exposicion_ticker = ejes.get("Ticker", [])
    exposicion_moneda = ejes.get("Moneda", [])
    exposicion_tipo = ejes.get("Tipo de instrumento", [])
    exposicion_pais = ejes.get("País", [])

    ratio_comisiones = calcular_ratio_comisiones(comisiones, resumen.get("valor_actual_usd", 0))

    dim_riesgo = salud_engine.evaluar_riesgo(riesgo.get("drawdown", {}), riesgo.get("volatilidad", {}))
    dim_concentracion = salud_engine.evaluar_concentracion(concentracion, exposicion_ticker, config.get("peso_maximo"))
    dim_diversificacion = salud_engine.evaluar_diversificacion(concentracion)
    dim_liquidez = salud_engine.evaluar_liquidez(inventario)
    dim_costos = salud_engine.evaluar_costos(ratio_comisiones)
    dim_vencimientos = salud_engine.evaluar_vencimientos(vencimientos)
    dim_balance = salud_engine.evaluar_balance_objetivo(rebalanceo.get("ejes", []), config.get("tolerancia", 2.0))
    dim_calidad = salud_engine.evaluar_calidad_datos(calidad, inventario, resumen.get("tiene_precios_desactualizados", False))

    dimensiones = [
        dim_riesgo, dim_concentracion, dim_diversificacion, dim_liquidez,
        dim_costos, dim_vencimientos, dim_balance, dim_calidad,
    ]

    observaciones = salud_engine.generar_observaciones(
        exposicion_ticker=exposicion_ticker,
        peso_maximo=config.get("peso_maximo"),
        rebalanceo_ejes=rebalanceo.get("ejes", []),
        tolerancia_pp=config.get("tolerancia", 2.0),
        inventario=inventario,
        vencimientos=vencimientos,
        ratio_comisiones=ratio_comisiones,
        calidad=calidad,
        dim_liquidez=dim_liquidez,
        dim_diversificacion=dim_diversificacion,
        dim_riesgo=dim_riesgo,
        concentracion=concentracion,
        exposicion_pais=exposicion_pais,
    )

    indicadores = salud_engine.construir_indicadores(
        resumen=resumen,
        riesgo=riesgo,
        concentracion=concentracion,
        exposicion_ticker=exposicion_ticker,
        inventario=inventario,
        ratio_comisiones=ratio_comisiones,
        calidad=calidad,
    )

    return salud_engine.armar_salud(
        cartera=cartera,
        dimensiones=dimensiones,
        observaciones=observaciones,
        indicadores=indicadores,
        exposicion_moneda=exposicion_moneda,
        exposicion_tipo=exposicion_tipo,
    )
