"""Valuación, XIRR, TWR, exposición y benchmarks para la página de Inversiones."""
import bisect
import calendar
from datetime import date, timedelta
from sqlalchemy.orm import Session

from ..database import MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado
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

    def avanzar_a(self, fecha: date) -> None:
        while self.idx < len(self.movs) and self.movs[self.idx].fecha <= fecha:
            mov = self.movs[self.idx]
            cant = float(mov.cantidad or 0)
            if mov.tipo_movimiento == "compra":
                self.tenencias[mov.ticker] = self.tenencias.get(mov.ticker, 0.0) + cant
            elif mov.tipo_movimiento in ("venta", "amortizacion"):
                self.tenencias[mov.ticker] = self.tenencias.get(mov.ticker, 0.0) - cant
            self.idx += 1

    def snapshot(self) -> dict[str, float]:
        return dict(self.tenencias)


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
) -> tuple[float, bool, bool]:
    """Devuelve (valor_usd, aproximado, tiene_precio_faltante)."""
    total_usd = 0.0
    aproximado = False
    precio_faltante = False
    for ticker, cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, fecha) if precios_sorted else None
        if info is None:
            precio_faltante = True
            continue
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
) -> tuple[float, bool, bool]:
    """Devuelve (valor_ars, aproximado, tiene_precio_faltante)."""
    total_ars = 0.0
    aproximado = False
    precio_faltante = False
    for ticker, cantidad in holdings.items():
        if abs(cantidad) < EPS:
            continue
        precios_sorted = precios_por_ticker.get(ticker)
        info = _precio_conocido(precios_sorted, fecha) if precios_sorted else None
        if info is None:
            precio_faltante = True
            continue
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
) -> tuple[float | None, bool, bool]:
    """Devuelve (valor_ars_real, aproximado, tiene_precio_faltante). None si falta CER."""
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
            precio_faltante = True
            continue
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
        tracker.snapshot(), hoy, precios_por_ticker, db, mep_cache
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
    valor_actual_ars, _, _ = _valuar_holdings_ars(tracker.snapshot(), hoy, precios_por_ticker, db, mep_cache)

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
            tracker.snapshot(), hoy, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy
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
        valor, aprox, _ = _valuar_holdings(tracker.snapshot(), b, precios_por_ticker, db, mep_cache)
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
        valor, aprox, _ = _valuar_holdings_ars(tracker.snapshot(), b, precios_por_ticker, db, mep_cache)
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
        valor, aprox, _ = _valuar_holdings_ars_real(tracker.snapshot(), b, precios_por_ticker, db, mep_cache, cer_cache, cer_hoy)
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


def _bucket_vencimiento(fecha_venc: date, hoy: date) -> str:
    anios = (fecha_venc - hoy).days / 365
    if anios < 1:
        return "Corto (<1 año)"
    if anios <= 3:
        return "Mediano (1-3 años)"
    return "Largo (>3 años)"


def get_exposicion(cartera: str | None, db: Session) -> dict:
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


# ── Rendimiento por ticker ─────────────────────────────────────────────────────

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
        })

    return sorted(resultado, key=lambda x: -abs(x["valor_actual_usd"]))


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


def get_evolucion(cartera: str | None, db: Session, max_puntos: int = 24) -> dict:
    """Serie histórica (mensual) del valor de la cartera, para sparklines."""
    movs = _movimientos_ordenados(db, cartera)
    if not movs:
        return {"puntos": []}

    precios_por_ticker = _precios_por_ticker(db)
    mep_cache: dict = {}
    hoy = date.today()

    fechas = _fin_de_mes_range(movs[0].fecha, hoy)
    if len(fechas) > max_puntos:
        paso = len(fechas) / max_puntos
        muestreadas = [fechas[int(i * paso)] for i in range(max_puntos - 1)]
        fechas = muestreadas + [fechas[-1]]

    tracker = _HoldingsTracker(movs)
    puntos = []
    for f in fechas:
        tracker.avanzar_a(f)
        snapshot = tracker.snapshot()
        valor_usd, _, _ = _valuar_holdings(snapshot, f, precios_por_ticker, db, mep_cache)
        valor_ars, _, _ = _valuar_holdings_ars(snapshot, f, precios_por_ticker, db, mep_cache)
        puntos.append({"fecha": f, "valor_usd": round(valor_usd, 2), "valor_ars": round(valor_ars, 2)})

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
