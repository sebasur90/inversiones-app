"""Valuación, XIRR, TWR, exposición y benchmarks para la página de Inversiones."""
import bisect
import calendar
from datetime import date, timedelta
from sqlalchemy.orm import Session

from ..database import MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado, RebalanceoObjetivo
from .cotizaciones import get_rates_for_date

UMBRAL_APROXIMADO_DIAS = 45
EPS = 1e-9

TIPOS_QUE_CAMBIAN_TENENCIA = ("compra", "venta", "amortizacion")
TIPOS_INGRESO = ("dividendo", "cupon")


# ── Conversión de monedas / índices ──────────────────────────────────────────

def _mep_venta(fecha: date, db: Session, cache: dict) -> float | None:
    if fecha in cache:
        return cache[fecha]
    rates = get_rates_for_date(fecha, db)
    mep = rates.get("mep")
    valor = float(mep["venta"]) if mep and mep.get("venta") else None
    cache[fecha] = valor
    return valor


def _to_usd(monto: float, moneda: str, fecha: date, db: Session, mep_cache: dict) -> float | None:
    if moneda == "USD":
        return monto
    mep = _mep_sheet(fecha, db, mep_cache)
    if not mep:
        return None
    return monto / mep


def _convertir(monto: float, moneda_origen: str, moneda_destino: str, fecha: date, db: Session, mep_cache: dict) -> float | None:
    """Conversión genérica entre ARS y USD usando MEP del Sheet (con fallback)."""
    if moneda_origen == moneda_destino:
        return monto
    if moneda_origen == "ARS" and moneda_destino == "USD":
        return _to_usd(monto, "ARS", fecha, db, mep_cache)
    if moneda_origen == "USD" and moneda_destino == "ARS":
        mep = _mep_sheet(fecha, db, mep_cache)
        if not mep:
            return None
        return monto * mep
    return None


def _cer_indice(fecha: date, db: Session, cache: dict) -> float | None:
    """Lookup de CER con carry-forward: último valor con fecha ≤ fecha_buscada."""
    if fecha in cache:
        return cache[fecha]
    row = (
        db.query(IndiceMercado)
        .filter(IndiceMercado.cer.isnot(None), IndiceMercado.fecha <= fecha)
        .order_by(IndiceMercado.fecha.desc())
        .first()
    )
    valor = float(row.cer) if row else None
    cache[fecha] = valor
    return valor


def _mep_sheet(fecha: date, db: Session, cache: dict) -> float | None:
    """Lookup de MEP del Sheet con carry-forward; fallback a TipoCambio auto-fetched."""
    if fecha in cache:
        return cache[fecha]
    row = (
        db.query(IndiceMercado)
        .filter(IndiceMercado.mep.isnot(None), IndiceMercado.fecha <= fecha)
        .order_by(IndiceMercado.fecha.desc())
        .first()
    )
    if row:
        valor = float(row.mep)
    else:
        # Fallback a TipoCambio auto-fetched
        valor = _mep_venta(fecha, db, {})
    cache[fecha] = valor
    return valor


# ── Montos de movimientos ────────────────────────────────────────────────────

def _monto_bruto(mov: MovimientoInversion) -> float:
    if mov.tipo_movimiento in TIPOS_INGRESO:
        return float(mov.precio)
    return float(mov.precio) * float(mov.cantidad or 0)


def _monto_ajustado(mov: MovimientoInversion) -> float:
    """Monto en la moneda original del movimiento, con la comisión aplicada."""
    bruto = _monto_bruto(mov)
    comision = float(mov.comision or 0)
    return bruto + comision if mov.tipo_movimiento == "compra" else bruto - comision


def _comision_usd(mov: MovimientoInversion, db: Session, mep_cache: dict) -> float | None:
    comision = float(mov.comision or 0)
    if comision == 0:
        return 0.0
    return _to_usd(comision, mov.moneda, mov.fecha, db, mep_cache)


def _comision_ars(mov: MovimientoInversion, db: Session, mep_cache: dict) -> float | None:
    comision = float(mov.comision or 0)
    if comision == 0:
        return 0.0
    return _convertir(comision, mov.moneda, "ARS", mov.fecha, db, mep_cache)


def _monto_usd(mov: MovimientoInversion, db: Session, mep_cache: dict) -> float | None:
    return _to_usd(_monto_ajustado(mov), mov.moneda, mov.fecha, db, mep_cache)


def _monto_ars(mov: MovimientoInversion, db: Session, mep_cache: dict) -> float | None:
    """Monto en ARS nominal (sin ajuste por inflación)."""
    monto_ajustado = _monto_ajustado(mov)
    return _convertir(monto_ajustado, mov.moneda, "ARS", mov.fecha, db, mep_cache)


def _monto_ars_real(mov: MovimientoInversion, db: Session, cer_cache: dict, mep_cache: dict, cer_hoy: float | None) -> float | None:
    """Monto en ARS real (deflactado por CER). Devuelve None si falta CER para el período."""
    if cer_hoy is None:
        return None
    monto_ars = _monto_ars(mov, db, mep_cache)
    if monto_ars is None:
        return None
    cer_fecha = _cer_indice(mov.fecha, db, cer_cache)
    if cer_fecha is None:
        return None
    return monto_ars * (cer_hoy / cer_fecha)


# ── Tenencias y valuación ────────────────────────────────────────────────────

class _HoldingsTracker:
    """Avanza cronológicamente sobre movimientos (ordenados por fecha) acumulando tenencia por ticker."""

    def __init__(self, movimientos: list[MovimientoInversion]):
        self.movs = movimientos
        self.idx = 0
        self.tenencias: dict[str, float] = {}
        self.costo_promedio: dict[str, tuple[float, str]] = {}  # ticker -> (precio unitario promedio, moneda)

    def avanzar_a(self, fecha: date) -> None:
        while self.idx < len(self.movs) and self.movs[self.idx].fecha <= fecha:
            mov = self.movs[self.idx]
            cant = float(mov.cantidad or 0)
            if mov.tipo_movimiento == "compra":
                cant_actual = self.tenencias.get(mov.ticker, 0.0)
                precio_actual, _ = self.costo_promedio.get(mov.ticker, (0.0, mov.moneda))
                nueva_cant = cant_actual + cant
                if nueva_cant > EPS:
                    self.costo_promedio[mov.ticker] = (
                        (precio_actual * cant_actual + float(mov.precio) * cant) / nueva_cant,
                        mov.moneda,
                    )
                self.tenencias[mov.ticker] = nueva_cant
            elif mov.tipo_movimiento in ("venta", "amortizacion"):
                self.tenencias[mov.ticker] = self.tenencias.get(mov.ticker, 0.0) - cant
                # El costo promedio no se recalcula al vender: la posición remanente sigue al mismo costo.
            self.idx += 1

    def snapshot(self) -> dict[str, float]:
        return dict(self.tenencias)

    def costo_snapshot(self) -> dict[str, tuple[float, str]]:
        return dict(self.costo_promedio)


def _precios_por_ticker(db: Session) -> dict[str, list[tuple[date, float, str]]]:
    rows = db.query(PrecioInstrumento).order_by(PrecioInstrumento.ticker, PrecioInstrumento.fecha).all()
    result: dict[str, list[tuple[date, float, str]]] = {}
    for row in rows:
        result.setdefault(row.ticker, []).append((row.fecha, float(row.precio), row.moneda))
    return result


def _precio_conocido(precios_sorted: list[tuple[date, float, str]], fecha: date) -> tuple[date, float, str] | None:
    fechas = [p[0] for p in precios_sorted]
    idx = bisect.bisect_right(fechas, fecha) - 1
    if idx < 0:
        return None
    return precios_sorted[idx]


def _valuar_holdings(
    holdings: dict[str, float],
    fecha: date,
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    costos_por_ticker: dict[str, tuple[float, str]] | None = None,
) -> tuple[float, bool, bool]:
    """Devuelve (valor_usd, aproximado, tiene_precio_faltante).

    Si no hay cotización de mercado conocida para una fecha (p.ej. antes de que exista
    histórico de precios para el ticker), se usa el costo promedio de compra como valor
    de referencia (marcando `aproximado=True`) en lugar de descartar la posición.
    """
    total_usd = 0.0
    aproximado = False
    precio_faltante = False
    for ticker, cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, fecha) if precios_sorted else None
        if info is None:
            costo = costos_por_ticker.get(ticker) if costos_por_ticker else None
            if costo is None:
                precio_faltante = True
                continue
            precio, moneda = costo
            aproximado = True
        else:
            fecha_precio, precio, moneda = info
            if (fecha - fecha_precio).days > UMBRAL_APROXIMADO_DIAS:
                aproximado = True
        usd = _to_usd(precio * cantidad, moneda, fecha, db, mep_cache)
        if usd is None:
            precio_faltante = True
            continue
        total_usd += usd
    return total_usd, aproximado, precio_faltante


def _valuar_holdings_ars(
    holdings: dict[str, float],
    fecha: date,
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    costos_por_ticker: dict[str, tuple[float, str]] | None = None,
) -> tuple[float, bool, bool]:
    """Devuelve (valor_ars, aproximado, tiene_precio_faltante). Ver `_valuar_holdings` para el fallback de costo."""
    total_ars = 0.0
    aproximado = False
    precio_faltante = False
    for ticker, cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, fecha) if precios_sorted else None
        if info is None:
            costo = costos_por_ticker.get(ticker) if costos_por_ticker else None
            if costo is None:
                precio_faltante = True
                continue
            precio, moneda = costo
            aproximado = True
        else:
            fecha_precio, precio, moneda = info
            if (fecha - fecha_precio).days > UMBRAL_APROXIMADO_DIAS:
                aproximado = True
        ars = _convertir(precio * cantidad, moneda, "ARS", fecha, db, mep_cache)
        if ars is None:
            precio_faltante = True
            continue
        total_ars += ars
    return total_ars, aproximado, precio_faltante


def _valuar_holdings_ars_real(
    holdings: dict[str, float],
    fecha: date,
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    cer_cache: dict,
    cer_hoy: float | None,
    costos_por_ticker: dict[str, tuple[float, str]] | None = None,
) -> tuple[float | None, bool, bool]:
    """Devuelve (valor_ars_real, aproximado, tiene_precio_faltante). None si falta CER.

    Ver `_valuar_holdings` para el fallback de costo cuando no hay cotización de mercado.
    """
    if cer_hoy is None:
        return None, False, False
    total_ars_real = 0.0
    aproximado = False
    precio_faltante = False
    for ticker, cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, fecha) if precios_sorted else None
        if info is None:
            costo = costos_por_ticker.get(ticker) if costos_por_ticker else None
            if costo is None:
                precio_faltante = True
                continue
            precio, moneda = costo
            aproximado = True
        else:
            fecha_precio, precio, moneda = info
            if (fecha - fecha_precio).days > UMBRAL_APROXIMADO_DIAS:
                aproximado = True
        ars = _convertir(precio * cantidad, moneda, "ARS", fecha, db, mep_cache)
        if ars is None:
            precio_faltante = True
            continue
        cer_fecha = _cer_indice(fecha, db, cer_cache)
        if cer_fecha is None:
            # Falta CER para este período, marcar como incalculable
            return None, aproximado, True
        ars_real = ars * (cer_hoy / cer_fecha)
        total_ars_real += ars_real
    return total_ars_real, aproximado, precio_faltante


def _movimientos_ordenados(db: Session, cartera: str | None) -> list[MovimientoInversion]:
    q = db.query(MovimientoInversion)
    if cartera is not None:
        q = q.filter(MovimientoInversion.cartera == cartera)
    return q.order_by(MovimientoInversion.fecha, MovimientoInversion.id).all()


# ── Carteras ──────────────────────────────────────────────────────────────

def get_carteras(db: Session) -> list[str]:
    rows = db.query(MovimientoInversion.cartera).distinct().order_by(MovimientoInversion.cartera).all()
    return [r[0] for r in rows]


# ── Resumen ───────────────────────────────────────────────────────────────

def get_resumen(cartera: str | None, db: Session) -> dict:
    movs = _movimientos_ordenados(db, cartera)
    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()

    # CER de hoy (para deflactación en modo real)
    cer_hoy = _cer_indice(hoy, db, cer_cache)

    # === USD ===
    tracker = _HoldingsTracker(movs)
    tracker.avanzar_a(hoy)
    valor_actual_usd, aproximado, _precio_faltante = _valuar_holdings(
        tracker.snapshot(), hoy, precios_por_ticker, db, mep_cache, tracker.costo_snapshot()
    )

    total_invertido_usd = 0.0
    ingresos_recibidos_usd = 0.0
    hubo_compra = False
    flujos_xirr_usd: list[tuple[date, float]] = []

    # === ARS nominal y real ===
    total_invertido_ars = 0.0
    ingresos_recibidos_ars = 0.0
    total_invertido_ars_real = 0.0
    ingresos_recibidos_ars_real = 0.0
    tiene_cer_faltante = False

    for mov in movs:
        monto_usd = _monto_usd(mov, db, mep_cache)
        if monto_usd is None:
            continue

        monto_ars = _monto_ars(mov, db, mep_cache)
        monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
        if monto_ars_real is None and (mov.tipo_movimiento in ("compra", "venta", "amortizacion") or mov.tipo_movimiento in TIPOS_INGRESO):
            tiene_cer_faltante = True

        if mov.tipo_movimiento == "compra":
            total_invertido_usd += monto_usd
            hubo_compra = True
            flujos_xirr_usd.append((mov.fecha, -monto_usd))
            if monto_ars is not None:
                total_invertido_ars += monto_ars
            if monto_ars_real is not None:
                total_invertido_ars_real += monto_ars_real
        elif mov.tipo_movimiento == "venta":
            total_invertido_usd -= monto_usd
            flujos_xirr_usd.append((mov.fecha, monto_usd))
            if monto_ars is not None:
                total_invertido_ars -= monto_ars
            if monto_ars_real is not None:
                total_invertido_ars_real -= monto_ars_real
        elif mov.tipo_movimiento in TIPOS_INGRESO:
            ingresos_recibidos_usd += monto_usd
            flujos_xirr_usd.append((mov.fecha, monto_usd))
            if monto_ars is not None:
                ingresos_recibidos_ars += monto_ars
            if monto_ars_real is not None:
                ingresos_recibidos_ars_real += monto_ars_real
        elif mov.tipo_movimiento == "amortizacion":
            flujos_xirr_usd.append((mov.fecha, monto_usd))
            if monto_ars is not None:
                pass  # No afecta invertido/ingresos en amortización

    # Cálculo de métricas USD
    rendimiento_simple_usd = (
        (valor_actual_usd + ingresos_recibidos_usd - total_invertido_usd) / total_invertido_usd
        if abs(total_invertido_usd) > EPS
        else None
    )

    xirr_usd = None
    if hubo_compra:
        flujos_xirr_usd.append((hoy, valor_actual_usd))
        xirr_usd = _calcular_xirr(flujos_xirr_usd)

    twr_usd = None
    twr_aproximado = False
    if hubo_compra:
        twr_usd, twr_aproximado = _calcular_twr(movs, precios_por_ticker, db, mep_cache, hoy)

    # === ARS nominal ===
    # Recalcular valor actual en ARS
    tracker = _HoldingsTracker(movs)
    tracker.avanzar_a(hoy)
    valor_actual_ars, _, _ = _valuar_holdings_ars(tracker.snapshot(), hoy, precios_por_ticker, db, mep_cache, tracker.costo_snapshot())

    rendimiento_simple_ars = (
        (valor_actual_ars + ingresos_recibidos_ars - total_invertido_ars) / total_invertido_ars
        if abs(total_invertido_ars) > EPS
        else None
    )

    xirr_ars = None
    if hubo_compra:
        flujos_xirr_ars: list[tuple[date, float]] = []
        for mov in movs:
            monto_ars = _monto_ars(mov, db, mep_cache)
            if monto_ars is None:
                continue
            if mov.tipo_movimiento == "compra":
                flujos_xirr_ars.append((mov.fecha, -monto_ars))
            elif mov.tipo_movimiento == "venta":
                flujos_xirr_ars.append((mov.fecha, monto_ars))
            elif mov.tipo_movimiento in TIPOS_INGRESO:
                flujos_xirr_ars.append((mov.fecha, monto_ars))
            elif mov.tipo_movimiento == "amortizacion":
                flujos_xirr_ars.append((mov.fecha, monto_ars))
        flujos_xirr_ars.append((hoy, valor_actual_ars))
        xirr_ars = _calcular_xirr(flujos_xirr_ars)

    twr_ars = None
    if hubo_compra:
        twr_ars, _ = _calcular_twr_ars(movs, precios_por_ticker, db, mep_cache, hoy)

    # === ARS real (deflactado por CER) ===
    rendimiento_simple_ars_real = None
    xirr_ars_real = None
    twr_ars_real = None

    if cer_hoy and not tiene_cer_faltante:
        # Valor actual en ARS real
        tracker = _HoldingsTracker(movs)
        tracker.avanzar_a(hoy)
        valor_actual_ars_real, _, _ = _valuar_holdings_ars_real(
            tracker.snapshot(), hoy, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, tracker.costo_snapshot()
        )

        if valor_actual_ars_real is not None:
            rendimiento_simple_ars_real = (
                (valor_actual_ars_real + ingresos_recibidos_ars_real - total_invertido_ars_real) / total_invertido_ars_real
                if abs(total_invertido_ars_real) > EPS
                else None
            )

            if hubo_compra:
                flujos_xirr_ars_real: list[tuple[date, float]] = []
                for mov in movs:
                    monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
                    if monto_ars_real is None:
                        tiene_cer_faltante = True
                        break
                    if mov.tipo_movimiento == "compra":
                        flujos_xirr_ars_real.append((mov.fecha, -monto_ars_real))
                    elif mov.tipo_movimiento == "venta":
                        flujos_xirr_ars_real.append((mov.fecha, monto_ars_real))
                    elif mov.tipo_movimiento in TIPOS_INGRESO:
                        flujos_xirr_ars_real.append((mov.fecha, monto_ars_real))
                    elif mov.tipo_movimiento == "amortizacion":
                        flujos_xirr_ars_real.append((mov.fecha, monto_ars_real))

                if not tiene_cer_faltante:
                    flujos_xirr_ars_real.append((hoy, valor_actual_ars_real))
                    xirr_ars_real = _calcular_xirr(flujos_xirr_ars_real)
                    twr_ars_real, _ = _calcular_twr_ars_real(movs, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, hoy)

    # Cálculo de valor_benchmark_usd_ars (Si comprabas USD)
    mep_hoy = _mep_sheet(hoy, db, mep_cache)
    valor_benchmark_usd_ars = (
        total_invertido_usd * mep_hoy if mep_hoy is not None else None
    )

    return {
        "valor_actual_usd": round(valor_actual_usd, 2),
        "valor_actual_ars": round(valor_actual_ars, 2),
        "total_invertido_usd": round(total_invertido_usd, 2),
        "total_invertido_ars": round(total_invertido_ars, 2),
        "total_invertido_ars_real": round(total_invertido_ars_real, 2) if total_invertido_ars_real is not None else None,
        "ingresos_recibidos_usd": round(ingresos_recibidos_usd, 2),
        "ingresos_recibidos_ars": round(ingresos_recibidos_ars, 2),
        "rendimiento_simple_usd": round(rendimiento_simple_usd, 4) if rendimiento_simple_usd is not None else None,
        "rendimiento_simple_ars": round(rendimiento_simple_ars, 4) if rendimiento_simple_ars is not None else None,
        "rendimiento_simple_ars_real": round(rendimiento_simple_ars_real, 4) if rendimiento_simple_ars_real is not None else None,
        "xirr_usd": round(xirr_usd, 4) if xirr_usd is not None else None,
        "xirr_ars": round(xirr_ars, 4) if xirr_ars is not None else None,
        "xirr_ars_real": round(xirr_ars_real, 4) if xirr_ars_real is not None else None,
        "twr_usd": round(twr_usd, 4) if twr_usd is not None else None,
        "twr_ars": round(twr_ars, 4) if twr_ars is not None else None,
        "twr_ars_real": round(twr_ars_real, 4) if twr_ars_real is not None else None,
        "valor_benchmark_usd_ars": round(valor_benchmark_usd_ars, 2) if valor_benchmark_usd_ars is not None else None,
        "tiene_precios_desactualizados": aproximado or twr_aproximado,
    }


def _calcular_xirr(flujos: list[tuple[date, float]]) -> float | None:
    if len(flujos) < 2:
        return None
    base_date = min(f for f, _ in flujos)

    def npv(r: float) -> float:
        total = 0.0
        for fecha, monto in flujos:
            dias = (fecha - base_date).days
            total += monto / ((1 + r) ** (dias / 365))
        return total

    lo, hi = -0.999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        hi = 100.0
        f_hi = npv(hi)
        if f_lo * f_hi > 0:
            return None

    mid = (lo + hi) / 2
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return mid


def _calcular_twr(
    movs: list[MovimientoInversion],
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    hoy: date,
) -> tuple[float | None, bool]:
    fechas_borde = sorted({m.fecha for m in movs if m.tipo_movimiento in TIPOS_QUE_CAMBIAN_TENENCIA})
    if not fechas_borde:
        return None, False

    boundaries = list(fechas_borde)
    if boundaries[-1] < hoy:
        boundaries.append(hoy)
    if len(boundaries) < 1:
        return None, False

    # Si solo hay un boundary (una sola compra/venta), agregar hoy como segundo punto
    if len(boundaries) == 1:
        boundaries.append(hoy)

    cf_por_fecha: dict[date, float] = {}
    for mov in movs:
        if mov.tipo_movimiento not in TIPOS_QUE_CAMBIAN_TENENCIA:
            continue
        monto = _monto_usd(mov, db, mep_cache)
        if monto is None:
            continue
        signo = 1 if mov.tipo_movimiento == "compra" else -1
        cf_por_fecha[mov.fecha] = cf_por_fecha.get(mov.fecha, 0.0) + signo * monto

    tracker = _HoldingsTracker(movs)
    valores: dict[date, float] = {}
    aproximado = False
    for b in boundaries:
        tracker.avanzar_a(b)
        valor, aprox, _ = _valuar_holdings(tracker.snapshot(), b, precios_por_ticker, db, mep_cache, tracker.costo_snapshot())
        valores[b] = valor
        aproximado = aproximado or aprox

    twr_total = 1.0
    for i in range(1, len(boundaries)):
        d0, d1 = boundaries[i - 1], boundaries[i]
        v0, v1 = valores[d0], valores[d1]
        if v0 <= EPS:
            continue
        flujo = cf_por_fecha.get(d1, 0.0)
        r = (v1 - flujo) / v0 - 1
        twr_total *= (1 + r)

    return twr_total - 1, aproximado


def _calcular_twr_ars(
    movs: list[MovimientoInversion],
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    hoy: date,
) -> tuple[float | None, bool]:
    """TWR en ARS nominal."""
    fechas_borde = sorted({m.fecha for m in movs if m.tipo_movimiento in TIPOS_QUE_CAMBIAN_TENENCIA})
    if not fechas_borde:
        return None, False

    boundaries = list(fechas_borde)
    if boundaries[-1] < hoy:
        boundaries.append(hoy)
    if len(boundaries) < 1:
        return None, False

    # Si solo hay un boundary (una sola compra/venta), agregar hoy como segundo punto
    if len(boundaries) == 1:
        boundaries.append(hoy)

    cf_por_fecha: dict[date, float] = {}
    for mov in movs:
        if mov.tipo_movimiento not in TIPOS_QUE_CAMBIAN_TENENCIA:
            continue
        monto = _monto_ars(mov, db, mep_cache)
        if monto is None:
            continue
        signo = 1 if mov.tipo_movimiento == "compra" else -1
        cf_por_fecha[mov.fecha] = cf_por_fecha.get(mov.fecha, 0.0) + signo * monto

    tracker = _HoldingsTracker(movs)
    valores: dict[date, float] = {}
    aproximado = False
    for b in boundaries:
        tracker.avanzar_a(b)
        valor, aprox, _ = _valuar_holdings_ars(tracker.snapshot(), b, precios_por_ticker, db, mep_cache, tracker.costo_snapshot())
        valores[b] = valor
        aproximado = aproximado or aprox

    twr_total = 1.0
    for i in range(1, len(boundaries)):
        d0, d1 = boundaries[i - 1], boundaries[i]
        v0, v1 = valores[d0], valores[d1]
        if v0 <= EPS:
            continue
        flujo = cf_por_fecha.get(d1, 0.0)
        r = (v1 - flujo) / v0 - 1
        twr_total *= (1 + r)

    return twr_total - 1, aproximado


def _calcular_twr_ars_real(
    movs: list[MovimientoInversion],
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    cer_cache: dict,
    cer_hoy: float,
    hoy: date,
) -> tuple[float | None, bool]:
    """TWR en ARS real (deflactado por CER)."""
    fechas_borde = sorted({m.fecha for m in movs if m.tipo_movimiento in TIPOS_QUE_CAMBIAN_TENENCIA})
    if not fechas_borde:
        return None, False

    boundaries = list(fechas_borde)
    if boundaries[-1] < hoy:
        boundaries.append(hoy)
    if len(boundaries) < 1:
        return None, False

    # Si solo hay un boundary (una sola compra/venta), agregar hoy como segundo punto
    if len(boundaries) == 1:
        boundaries.append(hoy)

    cf_por_fecha: dict[date, float] = {}
    for mov in movs:
        if mov.tipo_movimiento not in TIPOS_QUE_CAMBIAN_TENENCIA:
            continue
        monto = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
        if monto is None:
            return None, False
        signo = 1 if mov.tipo_movimiento == "compra" else -1
        cf_por_fecha[mov.fecha] = cf_por_fecha.get(mov.fecha, 0.0) + signo * monto

    tracker = _HoldingsTracker(movs)
    valores: dict[date, float] = {}
    aproximado = False
    for b in boundaries:
        tracker.avanzar_a(b)
        valor, aprox, _ = _valuar_holdings_ars_real(tracker.snapshot(), b, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, tracker.costo_snapshot())
        if valor is None:
            return None, False
        valores[b] = valor
        aproximado = aproximado or aprox

    twr_total = 1.0
    for i in range(1, len(boundaries)):
        d0, d1 = boundaries[i - 1], boundaries[i]
        v0, v1 = valores[d0], valores[d1]
        if v0 <= EPS:
            continue
        flujo = cf_por_fecha.get(d1, 0.0)
        r = (v1 - flujo) / v0 - 1
        twr_total *= (1 + r)

    return twr_total - 1, aproximado


def _calcular_twr_mensual(
    movs: list[MovimientoInversion],
    precios_por_ticker: dict[str, list[tuple[date, float, str]]],
    db: Session,
    mep_cache: dict,
    hoy: date,
    monto_fn,
    valuar_fn,
) -> dict[tuple[int, int], float | None]:
    """TWR encadenado y agrupado por mes calendario. Devuelve {(anio, mes): twr_mensual},
    sin entrada para meses sin tenencia (en vez de 0.0).

    Reutiliza el mismo encadenamiento que `_calcular_twr`/`_calcular_twr_ars`, pero agrega los
    fines de mes (`_fin_de_mes_range`) como bordes adicionales entre las fechas de cashflow. Por
    identidad telescópica esto no altera el producto total del período (v_dm/v0 * (v1-flujo)/v_dm
    = (v1-flujo)/v0), y permite atribuir cada sub-retorno al mes calendario exacto en que ocurre,
    ya que ningún sub-período puede cruzar un fin de mes.
    """
    fechas_borde = sorted({m.fecha for m in movs if m.tipo_movimiento in TIPOS_QUE_CAMBIAN_TENENCIA})
    if not fechas_borde:
        return {}

    primera_fecha = fechas_borde[0]
    boundaries = sorted(set(fechas_borde) | set(_fin_de_mes_range(primera_fecha, hoy)))

    cf_por_fecha: dict[date, float] = {}
    for mov in movs:
        if mov.tipo_movimiento not in TIPOS_QUE_CAMBIAN_TENENCIA:
            continue
        monto = monto_fn(mov, db, mep_cache)
        if monto is None:
            continue
        signo = 1 if mov.tipo_movimiento == "compra" else -1
        cf_por_fecha[mov.fecha] = cf_por_fecha.get(mov.fecha, 0.0) + signo * monto

    tracker = _HoldingsTracker(movs)
    valores: dict[date, float] = {}
    for b in boundaries:
        tracker.avanzar_a(b)
        valor, _aprox, _falt = valuar_fn(tracker.snapshot(), b, precios_por_ticker, db, mep_cache, tracker.costo_snapshot())
        valores[b] = valor

    factores_por_mes: dict[tuple[int, int], list[float]] = {}
    tuvo_tenencia: dict[tuple[int, int], bool] = {}

    for i in range(1, len(boundaries)):
        d0, d1 = boundaries[i - 1], boundaries[i]
        v0, v1 = valores[d0], valores[d1]
        key = (d1.year, d1.month)
        if v0 > EPS or v1 > EPS:
            tuvo_tenencia[key] = True
        else:
            tuvo_tenencia.setdefault(key, False)
        if v0 <= EPS:
            continue
        flujo = cf_por_fecha.get(d1, 0.0)
        r = (v1 - flujo) / v0 - 1
        factores_por_mes.setdefault(key, []).append(1 + r)

    resultado: dict[tuple[int, int], float | None] = {}
    for key, tuvo in tuvo_tenencia.items():
        factores = factores_por_mes.get(key)
        if not tuvo or not factores:
            resultado[key] = None
            continue
        total = 1.0
        for f in factores:
            total *= f
        resultado[key] = total - 1
    return resultado


def get_rendimiento_mensual(cartera: str | None, db: Session) -> dict:
    """Rendimiento (TWR) por mes calendario y por año, en ARS nominal y USD."""
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return {"meses": [], "anios": []}

    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    hoy = date.today()

    resultado_usd = _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_usd, _valuar_holdings)
    resultado_ars = _calcular_twr_mensual(movs, precios_por_ticker, db, mep_cache, hoy, _monto_ars, _valuar_holdings_ars)
    if not resultado_usd and not resultado_ars:
        return {"meses": [], "anios": []}

    es_mes_cerrado = hoy.day == calendar.monthrange(hoy.year, hoy.month)[1]
    claves = sorted(set(resultado_usd) | set(resultado_ars))

    def _compuesto(vals: list[float]) -> float | None:
        if not vals:
            return None
        total = 1.0
        for v in vals:
            total *= (1 + v)
        return total - 1

    meses: list[dict] = []
    por_anio_usd: dict[int, list[float]] = {}
    por_anio_ars: dict[int, list[float]] = {}
    anios_en_curso: set[int] = set()

    for anio, mes in claves:
        r_usd = resultado_usd.get((anio, mes))
        r_ars = resultado_ars.get((anio, mes))
        en_curso = (anio, mes) == (hoy.year, hoy.month) and not es_mes_cerrado
        if en_curso:
            anios_en_curso.add(anio)
        if r_usd is not None:
            por_anio_usd.setdefault(anio, []).append(r_usd)
        if r_ars is not None:
            por_anio_ars.setdefault(anio, []).append(r_ars)
        meses.append({
            "anio": anio,
            "mes": mes,
            "twr_ars": round(r_ars, 4) if r_ars is not None else None,
            "twr_usd": round(r_usd, 4) if r_usd is not None else None,
            "en_curso": en_curso,
        })

    anios_todos = sorted(set(por_anio_usd) | set(por_anio_ars) | anios_en_curso)
    anios = []
    for anio in anios_todos:
        c_ars = _compuesto(por_anio_ars.get(anio, []))
        c_usd = _compuesto(por_anio_usd.get(anio, []))
        anios.append({
            "anio": anio,
            "twr_ars": round(c_ars, 4) if c_ars is not None else None,
            "twr_usd": round(c_usd, 4) if c_usd is not None else None,
            "en_curso": anio in anios_en_curso,
        })

    return {"meses": meses, "anios": anios}


# ── Evolución + benchmarks ───────────────────────────────────────────────────

# ── Exposición ────────────────────────────────────────────────────────────

def _holdings_por_cartera_ticker(movs: list[MovimientoInversion], hasta: date) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    for mov in movs:
        if mov.fecha > hasta:
            continue
        key = (mov.cartera, mov.ticker)
        cant = float(mov.cantidad or 0)
        if mov.tipo_movimiento == "compra":
            result[key] = result.get(key, 0.0) + cant
        elif mov.tipo_movimiento in ("venta", "amortizacion"):
            result[key] = result.get(key, 0.0) - cant
    return result


def _agrupar(entries: list[tuple[str, float, float]]) -> list[dict]:
    """Agrupa entradas (etiqueta, valor_usd, valor_ars) y calcula porcentajes."""
    grupos_usd: dict[str, float] = {}
    grupos_ars: dict[str, float] = {}
    for etiqueta, valor_usd, valor_ars in entries:
        if etiqueta is None:
            continue
        grupos_usd[etiqueta] = grupos_usd.get(etiqueta, 0.0) + valor_usd
        grupos_ars[etiqueta] = grupos_ars.get(etiqueta, 0.0) + valor_ars
    total = sum(grupos_usd.values())
    if total <= EPS:
        return []
    items = sorted(grupos_usd.items(), key=lambda kv: -kv[1])
    return [
        {
            "etiqueta": k,
            "valor_usd": round(v, 2),
            "valor_ars": round(grupos_ars[k], 2),
            "porcentaje": round(v / total * 100, 2)
        }
        for k, v in items
    ]


def _agrupar_sobre_total(entries: list[tuple[str, float, float]], total_usd: float, total_ars: float) -> list[dict]:
    """Igual que _agrupar, pero el % se calcula sobre un total dado (no sobre la suma de las entradas).

    Se usa para ejes donde algunas entradas no tienen etiqueta (ej. Sector es opcional) y el
    porcentaje debe reflejar el peso sobre el total real de la cartera, no sobre el subtotal
    de lo que sí tiene etiqueta.
    """
    grupos_usd: dict[str, float] = {}
    grupos_ars: dict[str, float] = {}
    for etiqueta, valor_usd, valor_ars in entries:
        if etiqueta is None:
            continue
        grupos_usd[etiqueta] = grupos_usd.get(etiqueta, 0.0) + valor_usd
        grupos_ars[etiqueta] = grupos_ars.get(etiqueta, 0.0) + valor_ars
    if total_usd <= EPS:
        return []
    items = sorted(grupos_usd.items(), key=lambda kv: -kv[1])
    return [
        {
            "etiqueta": k,
            "valor_usd": round(v, 2),
            "valor_ars": round(grupos_ars[k], 2),
            "porcentaje": round(v / total_usd * 100, 2),
        }
        for k, v in items
    ]


def _bucket_vencimiento(fecha_venc: date, hoy: date) -> str:
    anios = (fecha_venc - hoy).days / 365
    if anios < 1:
        return "Corto (<1 año)"
    if anios <= 3:
        return "Mediano (1-3 años)"
    return "Largo (>3 años)"


def _clasificados_valorizados(cartera: str | None, db: Session) -> tuple[list[tuple], list[tuple], dict]:
    """Holdings valorizados hoy, en el alcance pedido (una cartera o todas si cartera=None).

    Devuelve (valores, clasificados, instrumentos):
    - valores: [(cartera, ticker, valor_usd, valor_ars)] para todo holding con precio conocido.
    - clasificados: igual, restringido a tickers con ficha en Instrumentos.
    - instrumentos: {ticker: InstrumentoInversion}.
    """
    movs = _movimientos_ordenados(db, None)  # necesitamos todas las carteras para el eje "por cartera"
    precios_por_ticker = _precios_por_ticker(db)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}
    mep_cache: dict = {}
    hoy = date.today()

    holdings = _holdings_por_cartera_ticker(movs, hoy)

    valores: list[tuple[str, str, float, float]] = []  # (cartera, ticker, valor_usd, valor_ars)
    for (cart, ticker), cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        if cartera is not None and cart != cartera:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, hoy) if precios_sorted else None
        if info is None:
            continue
        _fecha_precio, precio, moneda = info
        usd = _to_usd(precio * cantidad, moneda, hoy, db, mep_cache)
        if usd is None:
            continue
        ars = _convertir(precio * cantidad, moneda, "ARS", hoy, db, mep_cache)
        if ars is None:
            ars = 0.0
        valores.append((cart, ticker, usd, ars))

    clasificados = [(cart, ticker, valor_usd, valor_ars) for cart, ticker, valor_usd, valor_ars in valores if ticker in instrumentos]

    return valores, clasificados, instrumentos


def get_exposicion(cartera: str | None, db: Session) -> dict:
    valores, clasificados, instrumentos = _clasificados_valorizados(cartera, db)
    hoy = date.today()

    ejes = []

    mercado = _agrupar([(instrumentos[t].mercado, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    if mercado:
        ejes.append({"eje": "Mercado", "items": mercado})

    moneda = _agrupar([(instrumentos[t].moneda, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    if moneda:
        ejes.append({"eje": "Moneda", "items": moneda})

    tipo = _agrupar([(instrumentos[t].tipo_instrumento, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    if tipo:
        ejes.append({"eje": "Tipo de instrumento", "items": tipo})

    ticker_eje = _agrupar([(t, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    if ticker_eje:
        ejes.append({"eje": "Ticker", "items": ticker_eje})

    sector = _agrupar([(instrumentos[t].sector, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados if instrumentos[t].sector])
    if sector:
        ejes.append({"eje": "Sector", "items": sector})

    pais = _agrupar([(instrumentos[t].pais, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados if instrumentos[t].pais])
    if pais:
        ejes.append({"eje": "País", "items": pais})

    vencimiento = _agrupar([
        (_bucket_vencimiento(instrumentos[t].fecha_vencimiento, hoy), v_usd, v_ars)
        for _, t, v_usd, v_ars in clasificados
        if instrumentos[t].fecha_vencimiento
    ])
    if vencimiento:
        ejes.append({"eje": "Vencimiento", "items": vencimiento})

    if cartera is None:
        por_cartera = _agrupar([(cart, v_usd, v_ars) for cart, _, v_usd, v_ars in valores])
        if por_cartera:
            ejes.append({"eje": "Cartera", "items": por_cartera})

    return {"ejes": ejes}


def _construir_eje_rebalanceo(
    nombre_eje: str,
    actual_items: list[dict],
    targets: dict[str, float],
    total_usd: float,
    total_ars: float,
) -> dict | None:
    """Combina el % actual (salida de _agrupar/_agrupar_sobre_total) con los objetivos cargados.

    Las categorías con objetivo pero sin holding actual también aparecen (en 0%), para que se
    vea claramente qué falta comprar. Las categorías con holding pero sin objetivo cargado van
    aparte, en "sin_objetivo".
    """
    actuales_por_etiqueta = {it["etiqueta"]: it for it in actual_items}

    items = []
    for categoria, porcentaje_objetivo in targets.items():
        actual = actuales_por_etiqueta.get(categoria)
        valor_actual_usd = actual["valor_usd"] if actual else 0.0
        valor_actual_ars = actual["valor_ars"] if actual else 0.0
        porcentaje_actual = actual["porcentaje"] if actual else 0.0
        valor_objetivo_usd = round(total_usd * porcentaje_objetivo / 100, 2)
        valor_objetivo_ars = round(total_ars * porcentaje_objetivo / 100, 2)
        items.append({
            "etiqueta": categoria,
            "porcentaje_actual": porcentaje_actual,
            "porcentaje_objetivo": porcentaje_objetivo,
            "valor_actual_usd": valor_actual_usd,
            "valor_actual_ars": valor_actual_ars,
            "valor_objetivo_usd": valor_objetivo_usd,
            "valor_objetivo_ars": valor_objetivo_ars,
            "delta_pp": round(porcentaje_actual - porcentaje_objetivo, 2),
            "delta_valor_usd": round(valor_actual_usd - valor_objetivo_usd, 2),
            "delta_valor_ars": round(valor_actual_ars - valor_objetivo_ars, 2),
        })
    items.sort(key=lambda it: -it["porcentaje_objetivo"])

    sin_objetivo = [it for it in actual_items if it["etiqueta"] not in targets]

    if not items and not sin_objetivo:
        return None

    return {
        "eje": nombre_eje,
        "total_usd": round(total_usd, 2),
        "total_ars": round(total_ars, 2),
        "items": items,
        "sin_objetivo": sin_objetivo,
    }


def get_rebalanceo(cartera: str | None, db: Session) -> dict:
    valores, clasificados, instrumentos = _clasificados_valorizados(cartera, db)

    total_usd = sum(v_usd for _, _, v_usd, _ in clasificados)
    total_ars = sum(v_ars for _, _, _, v_ars in clasificados)

    objetivos = db.query(RebalanceoObjetivo).all()

    def _targets(eje: str) -> dict[str, float]:
        # Filtrado en Python (no SQL) para que None == None matchee de forma directa.
        return {
            o.categoria: float(o.porcentaje_objetivo)
            for o in objetivos
            if o.eje == eje and o.cartera == cartera
        }

    ejes = []

    if cartera is None:
        total_usd_global = sum(v_usd for _, _, v_usd, _ in valores)
        total_ars_global = sum(v_ars for _, _, _, v_ars in valores)
        por_cartera = _agrupar([(cart, v_usd, v_ars) for cart, _, v_usd, v_ars in valores])
        eje_cartera = _construir_eje_rebalanceo("Cartera", por_cartera, _targets("Cartera"), total_usd_global, total_ars_global)
        if eje_cartera:
            ejes.append(eje_cartera)

    tipo = _agrupar([(instrumentos[t].tipo_instrumento, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados])
    eje_tipo = _construir_eje_rebalanceo("Tipo", tipo, _targets("Tipo"), total_usd, total_ars)
    if eje_tipo:
        ejes.append(eje_tipo)

    sector = _agrupar_sobre_total(
        [(instrumentos[t].sector, v_usd, v_ars) for _, t, v_usd, v_ars in clasificados],
        total_usd, total_ars,
    )
    eje_sector = _construir_eje_rebalanceo("Sector", sector, _targets("Sector"), total_usd, total_ars)
    if eje_sector:
        ejes.append(eje_sector)

    return {"ejes": ejes}


# ── Rendimiento por ticker ─────────────────────────────────────────────────────

def _nivel_precio(
    modo: str | None,
    valor,
    precio_promedio_compra: float,
    precio_actual: float,
    alcanzado_si_mayor: bool,
) -> tuple[float | None, float | None, bool | None]:
    """Calcula el precio absoluto de un nivel (objetivo/stop loss), la distancia % al
    precio actual y si ya fue alcanzado/disparado. `valor` puede ser % sobre el precio
    promedio de compra (modo="Porcentaje") o un precio absoluto (modo="Fijo")."""
    if not modo or valor is None:
        return None, None, None

    valor = float(valor)
    if modo == "Porcentaje":
        precio_nivel = precio_promedio_compra * (1 + valor / 100)
    elif modo == "Fijo":
        precio_nivel = valor
    else:
        return None, None, None

    if abs(precio_actual) < EPS:
        return round(precio_nivel, 6), None, None

    pct_restante = (precio_nivel - precio_actual) / precio_actual
    alcanzado = precio_actual >= precio_nivel if alcanzado_si_mayor else precio_actual <= precio_nivel
    return precio_nivel, pct_restante, alcanzado


def get_rendimiento_por_ticker(cartera: str | None, db: Session) -> list[dict]:
    """Rendimiento individual por ticker con análisis por moneda."""
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return []

    precios_por_ticker = _precios_por_ticker(db)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()
    cer_hoy = _cer_indice(hoy, db, cer_cache)

    # Agrupar movimientos por ticker
    movimientos_por_ticker: dict[str, list[MovimientoInversion]] = {}
    for mov in movs:
        movimientos_por_ticker.setdefault(mov.ticker, []).append(mov)

    resultado = []

    for ticker, movs_ticker in movimientos_por_ticker.items():
        # Calcular tenencia actual
        tenencia = 0.0
        inversion_total_usd = 0.0
        inversion_total_ars = 0.0
        precio_promedio_compra = 0.0
        precio_promedio_compra_cantidad = 0.0
        primera_compra_fecha = None

        for mov in movs_ticker:
            if mov.tipo_movimiento == "compra":
                cant = float(mov.cantidad or 0)
                precio = float(mov.precio)
                tenencia += cant
                precio_promedio_compra_cantidad += cant
                precio_promedio_compra += cant * precio
                if primera_compra_fecha is None:
                    primera_compra_fecha = mov.fecha

                monto_usd = _monto_usd(mov, db, mep_cache)
                if monto_usd is not None:
                    inversion_total_usd += monto_usd
                monto_ars = _monto_ars(mov, db, mep_cache)
                if monto_ars is not None:
                    inversion_total_ars += monto_ars
            elif mov.tipo_movimiento == "venta":
                tenencia -= float(mov.cantidad or 0)
            elif mov.tipo_movimiento == "amortizacion":
                tenencia -= float(mov.cantidad or 0)

        if abs(tenencia) < EPS:
            continue

        if precio_promedio_compra_cantidad > 0:
            precio_promedio_compra /= precio_promedio_compra_cantidad
        else:
            precio_promedio_compra = 0.0

        # Obtener precio actual
        precios_sorted = precios_por_ticker.get(ticker)
        precio_info = _precio_conocido(precios_sorted, hoy) if precios_sorted else None
        if precio_info is None:
            continue

        _fecha_precio, precio_actual, moneda = precio_info

        # Calcular valor actual
        valor_actual_usd = _to_usd(precio_actual * tenencia, moneda, hoy, db, mep_cache) or 0.0
        valor_actual_ars = _convertir(precio_actual * tenencia, moneda, "ARS", hoy, db, mep_cache) or 0.0

        # Calcular rendimiento simple
        rendimiento_simple_usd = None
        if abs(inversion_total_usd) > EPS:
            rendimiento_simple_usd = (valor_actual_usd - inversion_total_usd) / inversion_total_usd

        rendimiento_simple_ars = None
        if abs(inversion_total_ars) > EPS:
            rendimiento_simple_ars = (valor_actual_ars - inversion_total_ars) / inversion_total_ars

        # Rendimiento en ARS real (ajustado por CER) - solo si es en ARS
        rendimiento_simple_ars_real = None
        precio_promedio_ars_ajustado_cer = None
        precio_actual_ars_ajustado_cer = None

        if moneda == "ARS" and cer_hoy is not None and primera_compra_fecha is not None:
            cer_compra = _cer_indice(primera_compra_fecha, db, cer_cache)
            if cer_compra is not None:
                # Precio promedio de compra ajustado por inflación
                precio_promedio_ars_ajustado_cer = precio_promedio_compra * (cer_hoy / cer_compra)
                # Precio actual no se ajusta (es el precio de hoy)
                precio_actual_ars_ajustado_cer = precio_actual

                if abs(precio_promedio_ars_ajustado_cer) > EPS:
                    rendimiento_simple_ars_real = (precio_actual_ars_ajustado_cer - precio_promedio_ars_ajustado_cer) / precio_promedio_ars_ajustado_cer

        instrumento = instrumentos.get(ticker, None)
        nombre = instrumento.nombre if instrumento else ticker

        precio_objetivo, pct_a_objetivo, objetivo_alcanzado = _nivel_precio(
            instrumento.objetivo_modo if instrumento else None,
            instrumento.objetivo_valor if instrumento else None,
            precio_promedio_compra,
            precio_actual,
            alcanzado_si_mayor=True,
        )
        precio_stop_loss, pct_a_stop_loss, stop_loss_disparado = _nivel_precio(
            instrumento.stop_loss_modo if instrumento else None,
            instrumento.stop_loss_valor if instrumento else None,
            precio_promedio_compra,
            precio_actual,
            alcanzado_si_mayor=False,
        )

        resultado.append({
            "ticker": ticker,
            "nombre": nombre,
            "tipo_instrumento": instrumento.tipo_instrumento if instrumento else "—",
            "mercado": instrumento.mercado if instrumento else "—",
            "moneda": instrumento.moneda if instrumento else moneda,
            "pais": instrumento.pais if instrumento else None,
            "sector": instrumento.sector if instrumento else None,
            "cantidad_actual": round(tenencia, 8),
            "precio_promedio": round(precio_promedio_compra, 6),
            "precio_actual": round(precio_actual, 6),
            "valor_invertido_usd": round(inversion_total_usd, 2),
            "valor_actual_usd": round(valor_actual_usd, 2),
            "valor_invertido_ars": round(inversion_total_ars, 2),
            "valor_actual_ars": round(valor_actual_ars, 2),
            "rendimiento_simple_usd": round(rendimiento_simple_usd, 4) if rendimiento_simple_usd is not None else None,
            "rendimiento_simple_ars": round(rendimiento_simple_ars, 4) if rendimiento_simple_ars is not None else None,
            "rendimiento_simple_ars_real": round(rendimiento_simple_ars_real, 4) if rendimiento_simple_ars_real is not None else None,
            "precio_promedio_ars_ajustado_cer": round(precio_promedio_ars_ajustado_cer, 6) if precio_promedio_ars_ajustado_cer is not None else None,
            "precio_actual_ars_ajustado_cer": round(precio_actual_ars_ajustado_cer, 6) if precio_actual_ars_ajustado_cer is not None else None,
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
        })

    return sorted(resultado, key=lambda x: -abs(x["valor_actual_usd"]))


# ── P&L Realizado vs No Realizado ────────────────────────────────────────────

def get_pnl_realizado_no_realizado(cartera: str | None, db: Session) -> dict:
    """P&L separado en realizado (ventas ya concretadas, costo promedio), no realizado
    (tenencia actual a valor de mercado menos su costo remanente) e ingresos (dividendos/cupones).

    Identidad algebraica con get_resumen: realizado + no_realizado + ingresos, sumado en USD,
    coincide con (valor_actual_usd + ingresos_recibidos_usd - total_invertido_usd).
    """
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return {
            "consolidado": {
                "realizado_usd": 0.0, "no_realizado_usd": 0.0, "ingresos_usd": 0.0, "total_usd": 0.0,
                "realizado_ars": 0.0, "no_realizado_ars": 0.0, "ingresos_ars": 0.0, "total_ars": 0.0,
                "realizado_ars_real": None, "no_realizado_ars_real": None, "ingresos_ars_real": None, "total_ars_real": None,
            },
            "por_ticker": [],
        }

    precios_por_ticker = _precios_por_ticker(db)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}
    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()
    cer_hoy = _cer_indice(hoy, db, cer_cache)
    cer_incompleto = cer_hoy is None

    movimientos_por_ticker: dict[str, list[MovimientoInversion]] = {}
    for mov in movs:
        movimientos_por_ticker.setdefault(mov.ticker, []).append(mov)

    por_ticker_resultado = []
    tot = {k: 0.0 for k in (
        "realizado_usd", "no_realizado_usd", "ingresos_usd",
        "realizado_ars", "no_realizado_ars", "ingresos_ars",
        "realizado_ars_real", "no_realizado_ars_real", "ingresos_ars_real",
    )}

    for ticker, movs_ticker in movimientos_por_ticker.items():
        cantidad_held = 0.0
        costo_usd = costo_ars = costo_ars_real = 0.0
        realizado_usd = realizado_ars = realizado_ars_real = 0.0
        ingresos_usd = ingresos_ars = ingresos_ars_real = 0.0
        ars_real_valido = not cer_incompleto

        for mov in movs_ticker:
            monto_usd = _monto_usd(mov, db, mep_cache)
            if monto_usd is None:
                continue  # mismo criterio que get_resumen: sin conversión a USD no se puede ubicar el flujo
            monto_ars = _monto_ars(mov, db, mep_cache)
            monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy) if not cer_incompleto else None
            if monto_ars_real is None:
                ars_real_valido = False

            cant = float(mov.cantidad or 0)

            if mov.tipo_movimiento == "compra":
                costo_usd += monto_usd
                if monto_ars is not None:
                    costo_ars += monto_ars
                if ars_real_valido and monto_ars_real is not None:
                    costo_ars_real += monto_ars_real
                cantidad_held += cant
            elif mov.tipo_movimiento in ("venta", "amortizacion"):
                cantidad_vendida = min(cant, cantidad_held) if cantidad_held > EPS else 0.0
                frac = cantidad_vendida / cantidad_held if cantidad_held > EPS else 0.0
                costo_removido_usd = costo_usd * frac
                costo_removido_ars = costo_ars * frac
                costo_removido_ars_real = costo_ars_real * frac if ars_real_valido else 0.0

                realizado_usd += monto_usd - costo_removido_usd
                if monto_ars is not None:
                    realizado_ars += monto_ars - costo_removido_ars
                if ars_real_valido and monto_ars_real is not None:
                    realizado_ars_real += monto_ars_real - costo_removido_ars_real

                costo_usd -= costo_removido_usd
                costo_ars -= costo_removido_ars
                costo_ars_real -= costo_removido_ars_real
                cantidad_held -= cantidad_vendida
            elif mov.tipo_movimiento in TIPOS_INGRESO:
                ingresos_usd += monto_usd
                if monto_ars is not None:
                    ingresos_ars += monto_ars
                if ars_real_valido and monto_ars_real is not None:
                    ingresos_ars_real += monto_ars_real

        if abs(cantidad_held) < EPS:
            no_realizado_usd, no_realizado_ars = 0.0, 0.0
            no_realizado_ars_real = 0.0 if ars_real_valido else None
        else:
            precios_sorted = precios_por_ticker.get(ticker)
            info = _precio_conocido(precios_sorted, hoy) if precios_sorted else None
            if info is None:
                continue  # sin precio actual no se puede valuar la tenencia remanente
            _fecha_precio, precio_actual, moneda_precio = info
            valor_usd = _to_usd(precio_actual * cantidad_held, moneda_precio, hoy, db, mep_cache)
            valor_ars = _convertir(precio_actual * cantidad_held, moneda_precio, "ARS", hoy, db, mep_cache)
            if valor_usd is None:
                continue
            no_realizado_usd = valor_usd - costo_usd
            no_realizado_ars = (valor_ars - costo_ars) if valor_ars is not None else None
            no_realizado_ars_real = (valor_ars - costo_ars_real) if (ars_real_valido and valor_ars is not None) else None

        if not ars_real_valido:
            cer_incompleto = True

        tot["realizado_usd"] += realizado_usd
        tot["no_realizado_usd"] += no_realizado_usd
        tot["ingresos_usd"] += ingresos_usd
        tot["realizado_ars"] += realizado_ars
        if no_realizado_ars is not None:
            tot["no_realizado_ars"] += no_realizado_ars
        tot["ingresos_ars"] += ingresos_ars
        if ars_real_valido:
            tot["realizado_ars_real"] += realizado_ars_real
            if no_realizado_ars_real is not None:
                tot["no_realizado_ars_real"] += no_realizado_ars_real
            tot["ingresos_ars_real"] += ingresos_ars_real

        instrumento = instrumentos.get(ticker)
        por_ticker_resultado.append({
            "ticker": ticker,
            "nombre": instrumento.nombre if instrumento else ticker,
            "realizado_usd": round(realizado_usd, 2),
            "no_realizado_usd": round(no_realizado_usd, 2),
            "ingresos_usd": round(ingresos_usd, 2),
            "total_usd": round(realizado_usd + no_realizado_usd + ingresos_usd, 2),
            "realizado_ars": round(realizado_ars, 2),
            "no_realizado_ars": round(no_realizado_ars, 2) if no_realizado_ars is not None else None,
            "ingresos_ars": round(ingresos_ars, 2),
            "total_ars": (
                round(realizado_ars + no_realizado_ars + ingresos_ars, 2) if no_realizado_ars is not None else None
            ),
        })

    por_ticker_resultado.sort(key=lambda x: -abs(x["total_usd"]))

    consolidado = {
        "realizado_usd": round(tot["realizado_usd"], 2),
        "no_realizado_usd": round(tot["no_realizado_usd"], 2),
        "ingresos_usd": round(tot["ingresos_usd"], 2),
        "total_usd": round(tot["realizado_usd"] + tot["no_realizado_usd"] + tot["ingresos_usd"], 2),
        "realizado_ars": round(tot["realizado_ars"], 2),
        "no_realizado_ars": round(tot["no_realizado_ars"], 2),
        "ingresos_ars": round(tot["ingresos_ars"], 2),
        "total_ars": round(tot["realizado_ars"] + tot["no_realizado_ars"] + tot["ingresos_ars"], 2),
        "realizado_ars_real": round(tot["realizado_ars_real"], 2) if not cer_incompleto else None,
        "no_realizado_ars_real": round(tot["no_realizado_ars_real"], 2) if not cer_incompleto else None,
        "ingresos_ars_real": round(tot["ingresos_ars_real"], 2) if not cer_incompleto else None,
        "total_ars_real": (
            round(tot["realizado_ars_real"] + tot["no_realizado_ars_real"] + tot["ingresos_ars_real"], 2)
            if not cer_incompleto else None
        ),
    }

    return {"consolidado": consolidado, "por_ticker": por_ticker_resultado}


# ── Evolución histórica (sparklines) ─────────────────────────────────────────

def _fin_de_mes_range(desde: date, hasta: date) -> list[date]:
    """Último día de cada mes entre `desde` y `hasta`, con `hasta` siempre como último punto."""
    fechas: list[date] = []
    cursor = date(desde.year, desde.month, 1)
    while cursor <= hasta:
        ultimo_dia = calendar.monthrange(cursor.year, cursor.month)[1]
        fin_mes = min(date(cursor.year, cursor.month, ultimo_dia), hasta)
        fechas.append(fin_mes)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    if not fechas or fechas[-1] != hasta:
        fechas.append(hasta)
    return fechas


def _fechas_por_granularidad(desde: date, hasta: date) -> list[date]:
    """Elige granularidad según el rango: diaria (≤40d), semanal (≤400d) o fin de mes (resto)."""
    rango_dias = (hasta - desde).days
    if rango_dias <= 40:
        return [desde + timedelta(days=i) for i in range(rango_dias + 1)]
    if rango_dias <= 400:
        fechas = []
        cursor = desde
        while cursor < hasta:
            fechas.append(cursor)
            cursor += timedelta(days=7)
        fechas.append(hasta)
        return fechas
    return _fin_de_mes_range(desde, hasta)


def get_evolucion(cartera: str | None, db: Session, desde: date | None = None, max_puntos: int = 24) -> dict:
    """Serie histórica del valor de la cartera (nominal USD/ARS y ARS real vía CER).

    Sin `desde`, arranca en el primer movimiento con granularidad mensual (uso original: sparklines).
    Con `desde`, ajusta la granularidad al rango solicitado (diaria/semanal/mensual).
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
    idx_capital = 0
    capital_usd = 0.0
    capital_ars = 0.0
    capital_ars_real = 0.0
    capital_ars_real_valido = True
    for f in fechas:
        tracker.avanzar_a(f)
        snapshot = tracker.snapshot()
        costos = tracker.costo_snapshot()
        valor_usd, _, _ = _valuar_holdings(snapshot, f, precios_por_ticker, db, mep_cache, costos)
        valor_ars, _, _ = _valuar_holdings_ars(snapshot, f, precios_por_ticker, db, mep_cache, costos)
        valor_ars_real, _, _ = _valuar_holdings_ars_real(snapshot, f, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy, costos)

        while idx_capital < len(movs) and movs[idx_capital].fecha <= f:
            mov = movs[idx_capital]
            idx_capital += 1
            if mov.tipo_movimiento == "compra":
                signo = 1
            elif mov.tipo_movimiento in ("venta", "amortizacion"):
                signo = -1
            elif mov.tipo_movimiento in TIPOS_INGRESO:
                signo = 1
            else:
                continue

            monto_usd = _monto_usd(mov, db, mep_cache)
            if monto_usd is not None:
                capital_usd += signo * monto_usd
            monto_ars = _monto_ars(mov, db, mep_cache)
            if monto_ars is not None:
                capital_ars += signo * monto_ars
            if capital_ars_real_valido:
                monto_ars_real = _monto_ars_real(mov, db, cer_cache, mep_cache, cer_hoy)
                if monto_ars_real is not None:
                    capital_ars_real += signo * monto_ars_real
                else:
                    capital_ars_real_valido = False

        puntos.append({
            "fecha": f,
            "valor_usd": round(valor_usd, 2),
            "valor_ars": round(valor_ars, 2),
            "valor_ars_real": round(valor_ars_real, 2) if valor_ars_real is not None else None,
            "capital_aportado_usd": round(capital_usd, 2),
            "capital_aportado_ars": round(capital_ars, 2),
            "capital_aportado_ars_real": round(capital_ars_real, 2) if capital_ars_real_valido else None,
        })

    return {"puntos": puntos}


def get_precios_ticker(ticker: str, dias: int, db: Session) -> dict:
    """Serie histórica de precio de un ticker (directo de PrecioInstrumento), para sparklines."""
    desde = date.today() - timedelta(days=dias)
    rows = (
        db.query(PrecioInstrumento)
        .filter(PrecioInstrumento.ticker == ticker, PrecioInstrumento.fecha >= desde)
        .order_by(PrecioInstrumento.fecha)
        .all()
    )
    return {
        "ticker": ticker,
        "puntos": [
            {"fecha": r.fecha, "precio": float(r.precio), "moneda": r.moneda}
            for r in rows
        ],
    }


# ── Precios históricos con ajustes ──────────────────────────────────────────

def get_tickers_con_precios(db: Session) -> list[dict]:
    """Lista de tickers que tienen al menos un precio cargado en PrecioInstrumento."""
    tickers_rows = db.query(PrecioInstrumento.ticker).distinct().all()
    tickers = [r[0] for r in tickers_rows]
    instrumentos = {
        i.ticker: i
        for i in db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker.in_(tickers)).all()
    }
    return [
        {
            "ticker": t,
            "nombre": instrumentos[t].nombre if t in instrumentos else t,
            "moneda": instrumentos[t].moneda if t in instrumentos else "—",
        }
        for t in sorted(tickers)
    ]


def get_precios_historicos_ticker(ticker: str, dias: int, db: Session) -> dict:
    """Serie de precios de un ticker con ajuste por MEP (USD) y CER para el frontend."""
    desde = date.today() - timedelta(days=dias)
    rows = (
        db.query(PrecioInstrumento)
        .filter(PrecioInstrumento.ticker == ticker, PrecioInstrumento.fecha >= desde)
        .order_by(PrecioInstrumento.fecha)
        .all()
    )

    instrumento = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    moneda = instrumento.moneda if instrumento else "ARS"

    mep_cache: dict = {}
    cer_cache: dict = {}
    hoy = date.today()
    cer_hoy = _cer_indice(hoy, db, cer_cache)

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
                precio_cer = precio_nominal * mep  # equivalente en ARS al tipo de cambio de cada fecha

        puntos.append({
            "fecha": row.fecha,
            "precio_nominal": round(precio_nominal, 4),
            "precio_usd": round(precio_usd, 4) if precio_usd is not None else None,
            "precio_cer": round(precio_cer, 4) if precio_cer is not None else None,
        })

    return {"ticker": ticker, "moneda": moneda, "puntos": puntos}


# ── Indicadores macro (CER/MEP) ──────────────────────────────────────────────

def get_indices_mercado(dias: int, db: Session) -> dict:
    """Serie histórica de CER y MEP, para verlos como indicadores propios."""
    desde = date.today() - timedelta(days=dias)
    rows = (
        db.query(IndiceMercado)
        .filter(IndiceMercado.fecha >= desde)
        .order_by(IndiceMercado.fecha)
        .all()
    )
    puntos = [
        {
            "fecha": r.fecha,
            "cer": float(r.cer) if r.cer is not None else None,
            "mep": float(r.mep) if r.mep is not None else None,
        }
        for r in rows
    ]

    def variacion(campo: str) -> float | None:
        valores = [p[campo] for p in puntos if p[campo] is not None]
        if len(valores) < 2 or valores[0] <= 0:
            return None
        return round((valores[-1] / valores[0] - 1) * 100, 2)

    return {
        "puntos": puntos,
        "variacion_cer_pct": variacion("cer"),
        "variacion_mep_pct": variacion("mep"),
    }


# ── Vencimientos ─────────────────────────────────────────────────────────────

def get_vencimientos(cartera: str | None, db: Session) -> list[dict]:
    """Instrumentos con tenencia activa y fecha de vencimiento, ordenados por proximidad."""
    rendimientos = get_rendimiento_por_ticker(cartera, db)
    instrumentos = {
        i.ticker: i
        for i in db.query(InstrumentoInversion).filter(InstrumentoInversion.fecha_vencimiento.isnot(None)).all()
    }
    hoy = date.today()

    resultado = []
    for item in rendimientos:
        instrumento = instrumentos.get(item["ticker"])
        if not instrumento:
            continue
        dias_restantes = (instrumento.fecha_vencimiento - hoy).days
        resultado.append({
            "ticker": item["ticker"],
            "nombre": item["nombre"],
            "fecha_vencimiento": instrumento.fecha_vencimiento,
            "dias_restantes": dias_restantes,
            "vencido": dias_restantes < 0,
            "cantidad_actual": item["cantidad_actual"],
            "valor_actual_usd": item["valor_actual_usd"],
            "valor_actual_ars": item["valor_actual_ars"],
            "moneda": item["moneda"],
        })

    return sorted(resultado, key=lambda x: x["dias_restantes"])


# ── Comisiones ────────────────────────────────────────────────────────────────

def get_comisiones(cartera: str | None, db: Session) -> dict:
    """Total y desglose de comisiones pagadas, por cartera/ticker/mes/año."""
    movs = _movimientos_ordenados(db, cartera)
    mep_cache: dict = {}
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}

    total_usd = 0.0
    total_ars = 0.0
    por_cartera: dict[str, float] = {}
    por_cartera_ars: dict[str, float] = {}
    por_ticker: dict[str, float] = {}
    por_ticker_ars: dict[str, float] = {}
    por_mes: dict[str, float] = {}
    por_anio: dict[str, float] = {}
    movimientos_con_comision = 0

    for mov in movs:
        comision = float(mov.comision or 0)
        if comision <= 0:
            continue
        movimientos_con_comision += 1

        c_usd = _comision_usd(mov, db, mep_cache)
        if c_usd is None:
            continue
        c_ars = _comision_ars(mov, db, mep_cache) or 0.0

        total_usd += c_usd
        total_ars += c_ars
        por_cartera[mov.cartera] = por_cartera.get(mov.cartera, 0.0) + c_usd
        por_cartera_ars[mov.cartera] = por_cartera_ars.get(mov.cartera, 0.0) + c_ars
        por_ticker[mov.ticker] = por_ticker.get(mov.ticker, 0.0) + c_usd
        por_ticker_ars[mov.ticker] = por_ticker_ars.get(mov.ticker, 0.0) + c_ars
        mes_key = mov.fecha.strftime("%Y-%m")
        anio_key = mov.fecha.strftime("%Y")
        por_mes[mes_key] = por_mes.get(mes_key, 0.0) + c_usd
        por_anio[anio_key] = por_anio.get(anio_key, 0.0) + c_usd

    por_cartera_items = sorted(
        [
            {"etiqueta": k, "total_usd": round(v, 2), "total_ars": round(por_cartera_ars[k], 2)}
            for k, v in por_cartera.items()
        ],
        key=lambda x: -x["total_usd"],
    ) if cartera is None else []

    por_ticker_items = sorted(
        [
            {
                "ticker": k,
                "nombre": instrumentos[k].nombre if k in instrumentos else k,
                "total_usd": round(v, 2),
                "total_ars": round(por_ticker_ars[k], 2),
            }
            for k, v in por_ticker.items()
        ],
        key=lambda x: -x["total_usd"],
    )

    return {
        "total_usd": round(total_usd, 2),
        "total_ars": round(total_ars, 2),
        "movimientos_con_comision": movimientos_con_comision,
        "por_cartera": por_cartera_items,
        "por_ticker": por_ticker_items,
        "por_mes": [{"periodo": k, "total_usd": round(v, 2)} for k, v in sorted(por_mes.items())],
        "por_anio": [{"periodo": k, "total_usd": round(v, 2)} for k, v in sorted(por_anio.items())],
    }


# ── Objetivos de inversión ──────────────────────────────────────────────────

def get_aportes_historicos(cartera: str, db: Session) -> dict:
    """Histórico de aportes netos acumulados mes a mes, con valor actual de mercado hoy."""
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        # Sin movimientos, devolver estructura vacía pero con valor_actual_usd
        resumen = get_resumen(cartera, db)
        return {
            "curva": [],
            "valor_actual_usd": resumen["valor_actual_usd"],
        }

    mep_cache: dict = {}
    aportes_por_mes: dict[str, float] = {}

    for mov in movs:
        monto_usd = _monto_usd(mov, db, mep_cache)
        if monto_usd is None:
            continue

        mes_key = mov.fecha.strftime("%Y-%m")
        aporte_neto = 0.0
        if mov.tipo_movimiento == "compra":
            aporte_neto = monto_usd
        elif mov.tipo_movimiento == "venta":
            aporte_neto = -monto_usd
        elif mov.tipo_movimiento in TIPOS_INGRESO:
            aporte_neto = monto_usd
        elif mov.tipo_movimiento == "amortizacion":
            aporte_neto = -monto_usd

        aportes_por_mes[mes_key] = aportes_por_mes.get(mes_key, 0.0) + aporte_neto

    # Construir curva acumulada mes a mes, manteniendo acumulado plano en meses sin movimiento
    if not aportes_por_mes:
        resumen = get_resumen(cartera, db)
        return {
            "curva": [],
            "valor_actual_usd": resumen["valor_actual_usd"],
        }

    meses_ordenados = sorted(aportes_por_mes.keys())
    curva = []
    acumulado = 0.0
    mes_anterior = None

    for mes in meses_ordenados:
        acumulado += aportes_por_mes[mes]
        curva.append({
            "mes": mes,
            "aportes_netos_acumulados": round(acumulado, 2),
        })
        mes_anterior = mes

    # Obtener valor actual de mercado de hoy
    resumen = get_resumen(cartera, db)
    valor_actual_usd = resumen["valor_actual_usd"]

    return {
        "curva": curva,
        "valor_actual_usd": valor_actual_usd,
    }


def get_progreso_objetivo(cartera: str, objetivo_id: int, db: Session) -> dict | None:
    """Calcula progreso del objetivo: proyección, aporte promedio, déficit, etc."""
    from ..database import ObjetivoInversion

    objetivo = db.query(ObjetivoInversion).filter(ObjetivoInversion.id == objetivo_id).first()
    if not objetivo:
        return None

    # Obtener aportes históricos
    aportes_hist = get_aportes_historicos(cartera, db)
    curva = aportes_hist["curva"]
    valor_actual_usd = aportes_hist["valor_actual_usd"]

    # Calcular promedio de aporte mensual (últimos 12 meses o todo si menos)
    hoy = date.today()
    hace_12_meses = date(hoy.year - 1, hoy.month, 1)

    aportes_ultimos_12 = [punto for punto in curva if punto["mes"] >= hace_12_meses.strftime("%Y-%m")]
    if not aportes_ultimos_12:
        aportes_ultimos_12 = curva

    aporte_mensual_promedio = 0.0
    if len(aportes_ultimos_12) > 0:
        meses_considerados = len(aportes_ultimos_12)
        if meses_considerados == 1:
            aporte_mensual_promedio = aportes_ultimos_12[0]["aportes_netos_acumulados"]
        else:
            # Diferencia entre el último y el anterior al primero (que es el acumulado antes)
            acumulado_final = aportes_ultimos_12[-1]["aportes_netos_acumulados"]
            acumulado_anterior = 0.0
            # Si hay puntos antes del período de 12 meses, restar el acumulado
            if len(curva) > len(aportes_ultimos_12):
                idx_first = curva.index(aportes_ultimos_12[0])
                if idx_first > 0:
                    acumulado_anterior = curva[idx_first - 1]["aportes_netos_acumulados"]
            aporte_total_12 = acumulado_final - acumulado_anterior
            aporte_mensual_promedio = aporte_total_12 / meses_considerados

    # Calcular meses restantes
    monto_objetivo = float(objetivo.monto_usd)
    fecha_limite = objetivo.fecha_limite
    dias_restantes = (fecha_limite - hoy).days
    meses_restantes_float = dias_restantes / 30.44  # Aproximado 30.44 días/mes
    meses_restantes = max(0, int(round(meses_restantes_float)))

    # Proyección
    if meses_restantes_float > 0:
        proyeccion_usd = valor_actual_usd + aporte_mensual_promedio * meses_restantes_float
        aporte_mensual_necesario = max(0, (monto_objetivo - valor_actual_usd) / meses_restantes_float) if meses_restantes_float > 0 else None
    else:
        proyeccion_usd = valor_actual_usd
        aporte_mensual_necesario = None

    alcanzable = proyeccion_usd >= monto_objetivo
    deficit_usd = max(0, monto_objetivo - proyeccion_usd)

    return {
        "valor_actual_usd": round(valor_actual_usd, 2),
        "aporte_mensual_promedio_usd": round(aporte_mensual_promedio, 2),
        "aporte_mensual_necesario_usd": round(aporte_mensual_necesario, 2) if aporte_mensual_necesario is not None else None,
        "meses_restantes": meses_restantes,
        "proyeccion_usd": round(proyeccion_usd, 2),
        "alcanzable": alcanzable,
        "deficit_usd": round(deficit_usd, 2),
    }
