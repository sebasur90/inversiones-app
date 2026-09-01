"""Servicio de patrimonio histórico y descomposición del crecimiento.

Reutiliza funciones privadas de inversiones_analytics para reconstruir al vuelo
la serie de valor + aportes + dividendos + comisiones, garantizando identidad:
  crecimiento = aportes + rendimiento + dividendos + otros_ajustes
"""
from datetime import date
from sqlalchemy.orm import Session

from .inversiones_analytics import (
    _movimientos_ordenados,
    _HoldingsTracker,
    _precios_por_ticker,
    _valuar_holdings,
    _valuar_holdings_ars,
    _valuar_holdings_ars_real,
    _fechas_por_granularidad,
    _fin_de_mes_range,
    _monto_usd,
    _monto_ars,
    _monto_ars_real,
    _comision_usd,
    _comision_ars,
    _cer_indice,
    TIPOS_INGRESO,
)
from .cache import cache_por_sync


@cache_por_sync
def get_patrimonio_history(
    cartera: str | None,
    db: Session,
    desde: date | None = None,
    max_puntos: int = 24,
) -> dict:
    """Serie histórica del patrimonio con descomposición en aportes/dividendos/comisiones.

    Recorre fechas muestreadas (misma granularidad que get_evolucion) y por cada una
    acumula en USD/ARS/ARS-real:
    - valor: vía _valuar_holdings* (valor de mercado)
    - aportes_acumulados: flujo neto compra(+)/venta(-)/amortizacion(-)
    - dividendos_acumulados: flujo neto de movimientos en TIPOS_INGRESO
    - otros_ajustes_acumulados: comisiones acumuladas (siempre negativas)
    - ganancia: valor - aportes_acumulados (excluye aportes, incluye rendimiento + cambios de moneda)

    Args:
        cartera: nombre de cartera o None para consolidado
        db: sesión SQLAlchemy
        desde: fecha inicio (None = desde primer movimiento, granular a meses)
        max_puntos: máx. puntos retornados (subsampling si excede)

    Returns:
        dict con "puntos": list[PatrimonioPunto]
    """
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return {"puntos": []}

    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()
    cer_hoy = _cer_indice(hoy, db, cer_cache)

    desde_efectivo = desde if desde is not None else movs[0].fecha
    if desde is not None:
        fechas = _fechas_por_granularidad(desde_efectivo, hoy)
    else:
        fechas = _fin_de_mes_range(desde_efectivo, hoy)

    if len(fechas) > max_puntos:
        paso = len(fechas) / max_puntos
        muestreadas = [fechas[int(i * paso)] for i in range(max_puntos - 1)]
        fechas = muestreadas + [fechas[-1]]

    tracker = _HoldingsTracker(movs)
    puntos = []
    idx_mov = 0

    aportes_usd = 0.0
    aportes_ars = 0.0
    aportes_ars_real = 0.0
    aportes_ars_real_valido = True

    dividendos_usd = 0.0
    dividendos_ars = 0.0
    dividendos_ars_real = 0.0
    dividendos_ars_real_valido = True

    otros_ajustes_usd = 0.0
    otros_ajustes_ars = 0.0
    otros_ajustes_ars_real = 0.0
    otros_ajustes_ars_real_valido = True

    for f in fechas:
        tracker.avanzar_a(f)
        snapshot = tracker.snapshot()
        costos = tracker.costo_snapshot()
        valor_usd, _, _ = _valuar_holdings(snapshot, f, precios_por_ticker, db, mep_cache, costos)
        valor_ars, _, _ = _valuar_holdings_ars(snapshot, f, precios_por_ticker, db, mep_cache, costos)
        valor_ars_real, _, _ = _valuar_holdings_ars_real(
            snapshot, f, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, costos
        )

        while idx_mov < len(movs) and movs[idx_mov].fecha <= f:
            mov = movs[idx_mov]
            idx_mov += 1

            comision_usd = _comision_usd(mov, db, mep_cache)
            if comision_usd is not None:
                otros_ajustes_usd -= comision_usd
            comision_ars = _comision_ars(mov, db, mep_cache)
            if comision_ars is not None:
                otros_ajustes_ars -= comision_ars
                if otros_ajustes_ars_real_valido:
                    cer_fecha = _cer_indice(mov.fecha, db, cer_cache)
                    if cer_hoy is not None and cer_fecha is not None:
                        otros_ajustes_ars_real -= comision_ars * (cer_hoy / cer_fecha)
                    else:
                        otros_ajustes_ars_real_valido = False

            if mov.tipo_movimiento == "compra":
                monto_usd = _monto_usd(mov, db, mep_cache)
                if monto_usd is not None:
                    aportes_usd += monto_usd
                monto_ars = _monto_ars(mov, db, mep_cache)
                if monto_ars is not None:
                    aportes_ars += monto_ars
                if aportes_ars_real_valido:
                    monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
                    if monto_ars_real is not None:
                        aportes_ars_real += monto_ars_real
                    else:
                        aportes_ars_real_valido = False

            elif mov.tipo_movimiento == "venta":
                monto_usd = _monto_usd(mov, db, mep_cache)
                if monto_usd is not None:
                    aportes_usd -= monto_usd
                monto_ars = _monto_ars(mov, db, mep_cache)
                if monto_ars is not None:
                    aportes_ars -= monto_ars
                if aportes_ars_real_valido:
                    monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
                    if monto_ars_real is not None:
                        aportes_ars_real -= monto_ars_real
                    else:
                        aportes_ars_real_valido = False

            elif mov.tipo_movimiento == "amortizacion":
                monto_usd = _monto_usd(mov, db, mep_cache)
                if monto_usd is not None:
                    aportes_usd -= monto_usd
                monto_ars = _monto_ars(mov, db, mep_cache)
                if monto_ars is not None:
                    aportes_ars -= monto_ars
                if aportes_ars_real_valido:
                    monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
                    if monto_ars_real is not None:
                        aportes_ars_real -= monto_ars_real
                    else:
                        aportes_ars_real_valido = False

            elif mov.tipo_movimiento in TIPOS_INGRESO:
                monto_usd = _monto_usd(mov, db, mep_cache)
                if monto_usd is not None:
                    dividendos_usd += monto_usd
                monto_ars = _monto_ars(mov, db, mep_cache)
                if monto_ars is not None:
                    dividendos_ars += monto_ars
                if dividendos_ars_real_valido:
                    monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
                    if monto_ars_real is not None:
                        dividendos_ars_real += monto_ars_real
                    else:
                        dividendos_ars_real_valido = False

        ganancia_usd = valor_usd - aportes_usd
        ganancia_ars = valor_ars - aportes_ars
        ganancia_ars_real = (valor_ars_real - aportes_ars_real) if (valor_ars_real is not None and aportes_ars_real_valido) else None

        puntos.append({
            "fecha": f,
            "valor_usd": round(valor_usd, 2),
            "valor_ars": round(valor_ars, 2),
            "valor_ars_real": round(valor_ars_real, 2) if valor_ars_real is not None else None,
            "aportes_acumulados_usd": round(aportes_usd, 2),
            "aportes_acumulados_ars": round(aportes_ars, 2),
            "aportes_acumulados_ars_real": round(aportes_ars_real, 2) if aportes_ars_real_valido else None,
            "dividendos_acumulados_usd": round(dividendos_usd, 2),
            "dividendos_acumulados_ars": round(dividendos_ars, 2),
            "dividendos_acumulados_ars_real": round(dividendos_ars_real, 2) if dividendos_ars_real_valido else None,
            "otros_ajustes_acumulados_usd": round(otros_ajustes_usd, 2),
            "otros_ajustes_acumulados_ars": round(otros_ajustes_ars, 2),
            "otros_ajustes_acumulados_ars_real": round(otros_ajustes_ars_real, 2) if otros_ajustes_ars_real_valido else None,
            "ganancia_usd": round(ganancia_usd, 2),
            "ganancia_ars": round(ganancia_ars, 2),
            "ganancia_ars_real": round(ganancia_ars_real, 2) if ganancia_ars_real is not None else None,
        })

    return {"puntos": puntos}


def get_patrimonio_summary(
    cartera: str | None,
    db: Session,
    desde: date | None = None,
) -> dict:
    """Resumen de patrimonio: máximo histórico, drawdown nominal, descomposición del período.

    Calcula dos series:
    1. Sin `desde` (all-time) para obtener máximo y drawdown real.
    2. Con `desde` (período seleccionado) para descomposición.

    Drawdown aquí es sobre el **valor nominal**, no sobre retornos TWR.
    Es distinto del drawdown de Riesgo.tsx (que es sobre índice de retornos mensuales).

    Returns:
        dict con "maximo" (PatrimonioMaximoOut) y "descomposicion" (PatrimonioDescomposicionOut)
    """
    historia_completa = get_patrimonio_history(cartera, db, desde=None, max_puntos=500)
    puntos_completos = historia_completa["puntos"]

    if not puntos_completos:
        return {
            "maximo": {
                "valor_usd": None,
                "valor_ars": None,
                "valor_ars_real": None,
                "fecha": None,
                "fecha_ars": None,
                "fecha_ars_real": None,
                "valor_actual_usd": None,
                "valor_actual_ars": None,
                "valor_actual_ars_real": None,
                "drawdown_usd": None,
                "drawdown_ars": None,
                "drawdown_ars_real": None,
            },
            "descomposicion": {
                "aportes_usd": 0.0,
                "aportes_ars": 0.0,
                "aportes_ars_real": None,
                "rendimiento_usd": 0.0,
                "rendimiento_ars": 0.0,
                "rendimiento_ars_real": None,
                "dividendos_usd": 0.0,
                "dividendos_ars": 0.0,
                "dividendos_ars_real": None,
                "otros_ajustes_usd": 0.0,
                "otros_ajustes_ars": 0.0,
                "otros_ajustes_ars_real": None,
            },
        }

    maximo_usd = max((p["valor_usd"] for p in puntos_completos), default=None)
    maximo_ars = max((p["valor_ars"] for p in puntos_completos), default=None)
    maximo_ars_real = max(
        (p["valor_ars_real"] for p in puntos_completos if p["valor_ars_real"] is not None),
        default=None,
    )

    fecha_maximo_usd = None
    fecha_maximo_ars = None
    fecha_maximo_ars_real = None
    for p in puntos_completos:
        if p["valor_usd"] == maximo_usd and fecha_maximo_usd is None:
            fecha_maximo_usd = p["fecha"]
        if p["valor_ars"] == maximo_ars and fecha_maximo_ars is None:
            fecha_maximo_ars = p["fecha"]
        if maximo_ars_real and p["valor_ars_real"] == maximo_ars_real and fecha_maximo_ars_real is None:
            fecha_maximo_ars_real = p["fecha"]

    punto_actual = puntos_completos[-1] if puntos_completos else None

    drawdown_usd = None
    if maximo_usd is not None and maximo_usd > 0 and punto_actual:
        drawdown_usd = max(0, (maximo_usd - punto_actual["valor_usd"]) / maximo_usd)

    drawdown_ars = None
    if maximo_ars is not None and maximo_ars > 0 and punto_actual:
        drawdown_ars = max(0, (maximo_ars - punto_actual["valor_ars"]) / maximo_ars)

    drawdown_ars_real = None
    if maximo_ars_real is not None and maximo_ars_real > 0 and punto_actual and punto_actual["valor_ars_real"] is not None:
        drawdown_ars_real = max(0, (maximo_ars_real - punto_actual["valor_ars_real"]) / maximo_ars_real)

    historia_periodo = get_patrimonio_history(cartera, db, desde=desde, max_puntos=500)
    puntos_periodo = historia_periodo["puntos"]

    if len(puntos_periodo) >= 2:
        primer_punto = puntos_periodo[0]
        ultimo_punto = puntos_periodo[-1]

        aportes_usd = ultimo_punto["aportes_acumulados_usd"] - primer_punto["aportes_acumulados_usd"]
        aportes_ars = ultimo_punto["aportes_acumulados_ars"] - primer_punto["aportes_acumulados_ars"]
        aportes_ars_real = None
        if (
            primer_punto["aportes_acumulados_ars_real"] is not None
            and ultimo_punto["aportes_acumulados_ars_real"] is not None
        ):
            aportes_ars_real = (
                ultimo_punto["aportes_acumulados_ars_real"] - primer_punto["aportes_acumulados_ars_real"]
            )

        dividendos_usd = ultimo_punto["dividendos_acumulados_usd"] - primer_punto["dividendos_acumulados_usd"]
        dividendos_ars = ultimo_punto["dividendos_acumulados_ars"] - primer_punto["dividendos_acumulados_ars"]
        dividendos_ars_real = None
        if (
            primer_punto["dividendos_acumulados_ars_real"] is not None
            and ultimo_punto["dividendos_acumulados_ars_real"] is not None
        ):
            dividendos_ars_real = (
                ultimo_punto["dividendos_acumulados_ars_real"] - primer_punto["dividendos_acumulados_ars_real"]
            )

        otros_ajustes_usd = (
            ultimo_punto["otros_ajustes_acumulados_usd"] - primer_punto["otros_ajustes_acumulados_usd"]
        )
        otros_ajustes_ars = (
            ultimo_punto["otros_ajustes_acumulados_ars"] - primer_punto["otros_ajustes_acumulados_ars"]
        )
        otros_ajustes_ars_real = None
        if (
            primer_punto["otros_ajustes_acumulados_ars_real"] is not None
            and ultimo_punto["otros_ajustes_acumulados_ars_real"] is not None
        ):
            otros_ajustes_ars_real = (
                ultimo_punto["otros_ajustes_acumulados_ars_real"] - primer_punto["otros_ajustes_acumulados_ars_real"]
            )

        delta_valor_usd = ultimo_punto["valor_usd"] - primer_punto["valor_usd"]
        delta_valor_ars = ultimo_punto["valor_ars"] - primer_punto["valor_ars"]
        delta_valor_ars_real = None
        if primer_punto["valor_ars_real"] is not None and ultimo_punto["valor_ars_real"] is not None:
            delta_valor_ars_real = ultimo_punto["valor_ars_real"] - primer_punto["valor_ars_real"]

        rendimiento_usd = delta_valor_usd - aportes_usd - dividendos_usd - otros_ajustes_usd
        rendimiento_ars = delta_valor_ars - aportes_ars - dividendos_ars - otros_ajustes_ars
        rendimiento_ars_real = None
        if delta_valor_ars_real is not None and aportes_ars_real is not None:
            rendimiento_ars_real = delta_valor_ars_real - aportes_ars_real - dividendos_ars_real - otros_ajustes_ars_real if dividendos_ars_real is not None and otros_ajustes_ars_real is not None else None

    else:
        aportes_usd = aportes_ars = aportes_ars_real = 0.0
        rendimiento_usd = rendimiento_ars = rendimiento_ars_real = 0.0
        dividendos_usd = dividendos_ars = dividendos_ars_real = 0.0
        otros_ajustes_usd = otros_ajustes_ars = otros_ajustes_ars_real = 0.0

    return {
        "maximo": {
            "valor_usd": round(maximo_usd, 2) if maximo_usd is not None else None,
            "valor_ars": round(maximo_ars, 2) if maximo_ars is not None else None,
            "valor_ars_real": round(maximo_ars_real, 2) if maximo_ars_real is not None else None,
            "fecha": fecha_maximo_usd,
            "fecha_ars": fecha_maximo_ars,
            "fecha_ars_real": fecha_maximo_ars_real,
            "valor_actual_usd": round(punto_actual["valor_usd"], 2) if punto_actual else None,
            "valor_actual_ars": round(punto_actual["valor_ars"], 2) if punto_actual else None,
            "valor_actual_ars_real": round(punto_actual["valor_ars_real"], 2) if (punto_actual and punto_actual["valor_ars_real"] is not None) else None,
            "drawdown_usd": round(drawdown_usd, 4) if drawdown_usd is not None else None,
            "drawdown_ars": round(drawdown_ars, 4) if drawdown_ars is not None else None,
            "drawdown_ars_real": round(drawdown_ars_real, 4) if drawdown_ars_real is not None else None,
        },
        "descomposicion": {
            "aportes_usd": round(aportes_usd, 2),
            "aportes_ars": round(aportes_ars, 2),
            "aportes_ars_real": round(aportes_ars_real, 2) if aportes_ars_real is not None else None,
            "rendimiento_usd": round(rendimiento_usd, 2),
            "rendimiento_ars": round(rendimiento_ars, 2),
            "rendimiento_ars_real": round(rendimiento_ars_real, 2) if rendimiento_ars_real is not None else None,
            "dividendos_usd": round(dividendos_usd, 2),
            "dividendos_ars": round(dividendos_ars, 2),
            "dividendos_ars_real": round(dividendos_ars_real, 2) if dividendos_ars_real is not None else None,
            "otros_ajustes_usd": round(otros_ajustes_usd, 2),
            "otros_ajustes_ars": round(otros_ajustes_ars, 2),
            "otros_ajustes_ars_real": round(otros_ajustes_ars_real, 2) if otros_ajustes_ars_real is not None else None,
        },
    }
