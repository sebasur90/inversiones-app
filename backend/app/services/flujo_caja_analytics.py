"""Flujo de caja proyectado de renta fija: cupones y amortizaciones futuras.

No hay API gratuita de cronogramas de bonos argentinos. La periodicidad y el monto por unidad
de cada cobro se **infieren del historial** de movimientos `cupon` / `amortizacion` ya cargados
para cada ticker, y se proyectan hacia adelante hasta la fecha de vencimiento del instrumento.

Todo lo proyectado se marca en la respuesta (`confianza`, `notas`, `metodo_capital`) para que
la UI lo muestre siempre como estimación, nunca como dato firme. El tipo de cambio usado para
expresar los importes en USD/ARS es el MEP más reciente conocido (supuesto de FX constante).
"""
import calendar
import statistics
from datetime import date

from sqlalchemy.orm import Session

from ..database import InstrumentoInversion
from .inversiones_analytics import (
    EPS,
    _convertir,
    _holdings_por_cartera_ticker,
    _movimientos_ordenados,
    get_rendimiento_por_ticker,
)

HORIZONTE_MESES = 24

# (meses, etiqueta, umbral superior de gap mediano en días)
_PERIODICIDADES = [
    (1, "Mensual", 45),
    (2, "Bimestral", 75),
    (3, "Trimestral", 135),
    (6, "Semestral", 270),
    (12, "Anual", 10_000),
]


def _clasificar_periodicidad(gap_dias: float) -> tuple[int, str]:
    for meses, label, umbral in _PERIODICIDADES:
        if gap_dias <= umbral:
            return meses, label
    return 12, "Anual"


def _sumar_meses(d: date, meses: int) -> date:
    total = d.month - 1 + meses
    anio = d.year + total // 12
    mes = total % 12 + 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(d.day, ultimo_dia))


def _holdings_hasta(movs_ticker: list, fecha: date) -> float:
    """Tenencia acumulada del ticker (todas las carteras del scope) con fecha ≤ `fecha`."""
    cant = 0.0
    for m in movs_ticker:
        if m.fecha > fecha:
            break
        c = float(m.cantidad or 0)
        if m.tipo_movimiento == "compra":
            cant += c
        elif m.tipo_movimiento in ("venta", "amortizacion"):
            cant -= c
    return cant


def _rango_meses(desde: date, hasta: date) -> list[str]:
    """Claves 'YYYY-MM' desde el mes de `desde` hasta el mes de `hasta`, inclusive."""
    claves: list[str] = []
    y, m = desde.year, desde.month
    while (y, m) <= (hasta.year, hasta.month):
        claves.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return claves


def get_flujo_caja_proyectado(
    cartera: str | None, db: Session, horizonte_meses: int = HORIZONTE_MESES
) -> dict:
    """Proyección mes a mes de cupones y amortizaciones a cobrar por los bonos en cartera.

    Para cada instrumento con tenencia activa y `fecha_vencimiento` futura:
    - **Cupón**: se infiere periodicidad (gap mediano entre cupones cobrados) y monto por unidad
      (mediana de `precio / tenencia` de cada cupón histórico); se proyecta desde el último
      cupón hasta el vencimiento, valuando con la tenencia actual.
    - **Capital**: si hay historial de `amortizacion`, se proyecta esa serie inferida; si no,
      se asume *bullet* y se estima el capital al vencimiento con el valor de mercado actual
      del bono (marcado como estimación).
    """
    hoy = date.today()
    movs = _movimientos_ordenados(db, cartera)
    instrumentos = {i.ticker: i for i in db.query(InstrumentoInversion).all()}

    holdings = _holdings_por_cartera_ticker(movs, hoy)
    cantidad_por_ticker: dict[str, float] = {}
    for (_cart, ticker), qty in holdings.items():
        cantidad_por_ticker[ticker] = cantidad_por_ticker.get(ticker, 0.0) + qty

    movs_por_ticker: dict[str, list] = {}
    for m in movs:
        movs_por_ticker.setdefault(m.ticker, []).append(m)

    valuacion = {r["ticker"]: r for r in get_rendimiento_por_ticker(cartera, db)}

    horizonte_fin = _sumar_meses(hoy, horizonte_meses)
    conv_cache: dict = {}

    # eventos: dict[periodo -> lista de detalle]
    eventos_por_mes: dict[str, list[dict]] = {}
    instrumentos_out: list[dict] = []
    sin_proyeccion: list[dict] = []

    def _a_monedas(monto_nativo: float, moneda: str) -> tuple[float, float]:
        usd = _convertir(monto_nativo, moneda, "USD", hoy, db, conv_cache)
        ars = _convertir(monto_nativo, moneda, "ARS", hoy, db, conv_cache)
        return (usd or 0.0), (ars or 0.0)

    for ticker, cantidad in sorted(cantidad_por_ticker.items()):
        if cantidad <= EPS:
            continue
        inst = instrumentos.get(ticker)
        if inst is None or inst.fecha_vencimiento is None:
            continue
        venc = inst.fecha_vencimiento
        if venc <= hoy:
            continue  # ya vencido: lo cubre la pantalla Vencimientos

        mt = movs_por_ticker.get(ticker, [])
        moneda = inst.moneda
        nombre = inst.nombre
        notas: list[str] = []

        # ── cupones ────────────────────────────────────────────────────────────
        fechas_cupon: list[date] = []
        cupon_unit_vals: list[float] = []
        for m in mt:
            if m.tipo_movimiento != "cupon":
                continue
            tenencia = _holdings_hasta(mt, m.fecha)
            if tenencia <= EPS:
                continue
            fechas_cupon.append(m.fecha)
            cupon_unit_vals.append(float(m.precio) / tenencia)

        periodicidad_meses: int | None = None
        periodicidad_label: str | None = None
        cupon_por_unidad: float | None = None
        confianza: str | None = None

        if len(fechas_cupon) >= 2:
            gaps = [
                (fechas_cupon[i] - fechas_cupon[i - 1]).days
                for i in range(1, len(fechas_cupon))
            ]
            gap_med = statistics.median(gaps)
            periodicidad_meses, periodicidad_label = _clasificar_periodicidad(gap_med)
            cupon_por_unidad = statistics.median(cupon_unit_vals)
            if len(gaps) >= 2 and gap_med > 0:
                dispersion = statistics.pstdev(gaps) / gap_med
                confianza = "alta" if dispersion < 0.15 else "media"
            else:
                confianza = "media"
        elif len(fechas_cupon) == 1:
            periodicidad_meses, periodicidad_label = 6, "Semestral"
            cupon_por_unidad = cupon_unit_vals[0]
            confianza = "baja"
            notas.append("Un solo cupón histórico: se asume periodicidad semestral.")

        # ── amortizaciones ────────────────────────────────────────────────────
        fechas_amort: list[date] = []
        amort_unit_vals: list[float] = []
        for m in mt:
            if m.tipo_movimiento != "amortizacion":
                continue
            fechas_amort.append(m.fecha)
            amort_unit_vals.append(float(m.precio))

        amort_por_unidad: float | None = None
        amort_periodicidad_meses: int | None = None
        if len(fechas_amort) >= 2:
            gaps = [
                (fechas_amort[i] - fechas_amort[i - 1]).days
                for i in range(1, len(fechas_amort))
            ]
            amort_periodicidad_meses, _lbl = _clasificar_periodicidad(statistics.median(gaps))
            amort_por_unidad = statistics.median(amort_unit_vals)
        elif len(fechas_amort) == 1:
            amort_por_unidad = amort_unit_vals[0]
            amort_periodicidad_meses = periodicidad_meses or 6

        # ── proyección de cobros dentro del horizonte ─────────────────────────
        # Se ancla la grilla a la fecha de vencimiento y se retrocede: los cupones de un bono
        # caen en fechas fijas que terminan el día del vencimiento, así que anclar ahí es más
        # fiel que encadenar desde el último cupón cobrado (que puede estar desalineado).
        cobros: list[dict] = []  # {"fecha", "tipo", "monto_nativo"}

        def _grilla_hacia_atras(paso_meses: int) -> list[date]:
            fechas: list[date] = []
            for k in range(400):
                f = _sumar_meses(venc, -paso_meses * k)
                if f <= hoy:
                    break
                if f <= horizonte_fin:
                    fechas.append(f)
            return sorted(fechas)

        if cupon_por_unidad is not None and periodicidad_meses:
            monto_cupon = cupon_por_unidad * cantidad
            for f in _grilla_hacia_atras(periodicidad_meses):
                cobros.append({"fecha": f, "tipo": "cupon", "monto_nativo": monto_cupon})

        metodo_capital: str
        if amort_por_unidad is not None and amort_periodicidad_meses:
            metodo_capital = "amortizacion_inferida"
            monto_amort = amort_por_unidad * cantidad
            for f in _grilla_hacia_atras(amort_periodicidad_meses):
                cobros.append({"fecha": f, "tipo": "amortizacion", "monto_nativo": monto_amort})
            notas.append(
                "Amortización inferida del historial: el cupón proyectado no ajusta por la "
                "caída de capital residual."
            )
        else:
            # bullet: capital devuelto de una sola vez al vencimiento
            val = valuacion.get(ticker)
            capital_nativo = None
            if val and val.get("precio_actual") and val.get("cantidad_actual"):
                capital_nativo = float(val["precio_actual"]) * float(val["cantidad_actual"])
            if capital_nativo is not None:
                metodo_capital = "bullet"
                notas.append(
                    "Capital al vencimiento estimado con el precio de mercado actual del bono."
                )
                if hoy < venc <= horizonte_fin:
                    cobros.append(
                        {"fecha": venc, "tipo": "amortizacion", "monto_nativo": capital_nativo}
                    )
            else:
                metodo_capital = "sin_estimacion"
                notas.append("Sin precio cargado: no se estima el capital al vencimiento.")

        if not cobros and cupon_por_unidad is None:
            sin_proyeccion.append(
                {
                    "ticker": ticker,
                    "nombre": nombre,
                    "fecha_vencimiento": venc,
                    "motivo": (
                        "Sin cupones cobrados todavía: no hay historial del cual inferir el "
                        "cronograma."
                    ),
                }
            )
            continue

        # ── volcar cobros a la grilla mensual + resumen del instrumento ───────
        total_inst_usd = 0.0
        total_inst_ars = 0.0
        proximo_cobro: dict | None = None
        for c in sorted(cobros, key=lambda x: x["fecha"]):
            usd, ars = _a_monedas(c["monto_nativo"], moneda)
            total_inst_usd += usd
            total_inst_ars += ars
            periodo = c["fecha"].strftime("%Y-%m")
            eventos_por_mes.setdefault(periodo, []).append(
                {
                    "ticker": ticker,
                    "nombre": nombre,
                    "tipo": c["tipo"],
                    "fecha": c["fecha"],
                    "moneda": moneda,
                    "monto_nativo": round(c["monto_nativo"], 4),
                    "monto_usd": round(usd, 2),
                    "monto_ars": round(ars, 2),
                }
            )
            if proximo_cobro is None:
                proximo_cobro = {
                    "fecha": c["fecha"],
                    "tipo": c["tipo"],
                    "monto_usd": round(usd, 2),
                    "monto_ars": round(ars, 2),
                }

        instrumentos_out.append(
            {
                "ticker": ticker,
                "nombre": nombre,
                "moneda": moneda,
                "cantidad_actual": round(cantidad, 8),
                "fecha_vencimiento": venc,
                "periodicidad_meses": periodicidad_meses,
                "periodicidad_label": periodicidad_label,
                "cupon_por_unidad": round(cupon_por_unidad, 6) if cupon_por_unidad is not None else None,
                "confianza": confianza,
                "metodo_capital": metodo_capital,
                "cobros_proyectados": len(cobros),
                "proximo_cobro": proximo_cobro,
                "total_proyectado_usd": round(total_inst_usd, 2),
                "total_proyectado_ars": round(total_inst_ars, 2),
                "notas": notas,
            }
        )

    # ── grilla mensual continua ──────────────────────────────────────────────
    meses_out: list[dict] = []
    total_cupones_usd = total_cupones_ars = 0.0
    total_amort_usd = total_amort_ars = 0.0
    for periodo in _rango_meses(hoy, horizonte_fin):
        detalle = sorted(
            eventos_por_mes.get(periodo, []),
            key=lambda x: (-x["monto_usd"], x["ticker"]),
        )
        cup_usd = sum(d["monto_usd"] for d in detalle if d["tipo"] == "cupon")
        cup_ars = sum(d["monto_ars"] for d in detalle if d["tipo"] == "cupon")
        amo_usd = sum(d["monto_usd"] for d in detalle if d["tipo"] == "amortizacion")
        amo_ars = sum(d["monto_ars"] for d in detalle if d["tipo"] == "amortizacion")
        total_cupones_usd += cup_usd
        total_cupones_ars += cup_ars
        total_amort_usd += amo_usd
        total_amort_ars += amo_ars
        meses_out.append(
            {
                "periodo": periodo,
                "cupones_usd": round(cup_usd, 2),
                "cupones_ars": round(cup_ars, 2),
                "amortizaciones_usd": round(amo_usd, 2),
                "amortizaciones_ars": round(amo_ars, 2),
                "total_usd": round(cup_usd + amo_usd, 2),
                "total_ars": round(cup_ars + amo_ars, 2),
                "detalle": [
                    {
                        "ticker": d["ticker"],
                        "nombre": d["nombre"],
                        "tipo": d["tipo"],
                        "moneda": d["moneda"],
                        "monto_nativo": d["monto_nativo"],
                        "monto_usd": d["monto_usd"],
                        "monto_ars": d["monto_ars"],
                    }
                    for d in detalle
                ],
            }
        )

    instrumentos_out.sort(key=lambda x: -x["total_proyectado_usd"])

    return {
        "horizonte_meses": horizonte_meses,
        "generado": hoy,
        "total_cupones_usd": round(total_cupones_usd, 2),
        "total_cupones_ars": round(total_cupones_ars, 2),
        "total_amortizaciones_usd": round(total_amort_usd, 2),
        "total_amortizaciones_ars": round(total_amort_ars, 2),
        "total_usd": round(total_cupones_usd + total_amort_usd, 2),
        "total_ars": round(total_cupones_ars + total_amort_ars, 2),
        "meses": meses_out,
        "instrumentos": instrumentos_out,
        "sin_proyeccion": sin_proyeccion,
    }
