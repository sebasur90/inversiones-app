"""Flujo de caja proyectado de renta fija: cupones y amortizaciones futuras.

No hay API gratuita de cronogramas de bonos argentinos. La periodicidad y el monto por unidad
de cada cobro se **infieren del historial** de movimientos `cupon` / `amortizacion` ya cargados
para cada ticker, y se proyectan hacia adelante hasta la fecha de vencimiento del instrumento.

Todo lo proyectado se marca en la respuesta (`confianza`, `notas`, `metodo_capital`) para que
la UI lo muestre siempre como estimación, nunca como dato firme. El tipo de cambio usado para
expresar los importes en USD/ARS es el MEP más reciente conocido (supuesto de FX constante).

Sobre esa misma inferencia se calculan las métricas de bono de la pantalla Vencimientos (TIR al
vencimiento, duration, paridad): ver `get_vencimientos_completo`. Al depender de un cronograma
inferido, heredan su incertidumbre y también van marcadas como estimadas.
"""
import calendar
import statistics
from datetime import date

from sqlalchemy.orm import Session

from ..database import InstrumentoInversion
from .inversiones_analytics import (
    EPS,
    _calcular_xirr,
    _convertir,
    _holdings_por_cartera_ticker,
    _movimientos_ordenados,
    get_rendimiento_por_ticker,
    get_resumen,
    get_vencimientos,
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


def _grilla_hacia_atras(venc: date, hoy: date, horizonte_fin: date, paso_meses: int) -> list[date]:
    """Fechas de cobro ancladas al vencimiento y retrocediendo de a `paso_meses`.

    Los cupones de un bono caen en fechas fijas que terminan el día del vencimiento, así que
    anclar ahí es más fiel que encadenar desde el último cupón cobrado (que puede estar
    desalineado). Sólo se devuelven fechas futuras (> hoy) y dentro de `horizonte_fin`.
    """
    fechas: list[date] = []
    for k in range(400):
        f = _sumar_meses(venc, -paso_meses * k)
        if f <= hoy:
            break
        if f <= horizonte_fin:
            fechas.append(f)
    return sorted(fechas)


def _proyectar_cobros_ticker(
    ticker: str,
    cantidad: float,
    inst: InstrumentoInversion,
    mt: list,
    valuacion: dict,
    hoy: date,
    horizonte_fin: date,
) -> dict:
    """Infiere el cronograma futuro de un bono desde su historial de cupones/amortizaciones.

    Devuelve un dict con los cobros en moneda nativa
    (`cobros`: ``[{"fecha", "tipo", "monto_nativo"}]``) más los metadatos de la inferencia, o
    ``{"sin_proyeccion": {...}}`` si no hay historial del cual inferir.

    `horizonte_fin` recorta la grilla de cobros: pasar la fecha de vencimiento del bono para
    obtener el flujo de toda su vida (TIR / duration), o el fin del horizonte de la pantalla
    para la grilla mensual de flujo de caja.
    """
    venc = inst.fecha_vencimiento
    moneda = inst.moneda
    nombre = inst.nombre
    notas: list[str] = []

    # ── cupones ────────────────────────────────────────────────────────────────
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

    # ── amortizaciones ────────────────────────────────────────────────────────
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

    # ── proyección de cobros dentro del horizonte ─────────────────────────────
    cobros: list[dict] = []  # {"fecha", "tipo", "monto_nativo"}
    amort_futuras = 0

    if cupon_por_unidad is not None and periodicidad_meses:
        monto_cupon = cupon_por_unidad * cantidad
        for f in _grilla_hacia_atras(venc, hoy, horizonte_fin, periodicidad_meses):
            cobros.append({"fecha": f, "tipo": "cupon", "monto_nativo": monto_cupon})

    metodo_capital: str
    if amort_por_unidad is not None and amort_periodicidad_meses:
        metodo_capital = "amortizacion_inferida"
        monto_amort = amort_por_unidad * cantidad
        grilla_amort = _grilla_hacia_atras(venc, hoy, horizonte_fin, amort_periodicidad_meses)
        amort_futuras = len(grilla_amort)
        for f in grilla_amort:
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
        return {
            "sin_proyeccion": {
                "ticker": ticker,
                "nombre": nombre,
                "fecha_vencimiento": venc,
                "motivo": (
                    "Sin cupones cobrados todavía: no hay historial del cual inferir el "
                    "cronograma."
                ),
            }
        }

    return {
        "cobros": cobros,
        "moneda": moneda,
        "nombre": nombre,
        "periodicidad_meses": periodicidad_meses,
        "periodicidad_label": periodicidad_label,
        "cupon_por_unidad": cupon_por_unidad,
        "confianza": confianza,
        "metodo_capital": metodo_capital,
        "amort_historicas": len(fechas_amort),
        "amort_futuras": amort_futuras,
        "amort_por_unidad": amort_por_unidad,
        "notas": notas,
    }


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
        proj = _proyectar_cobros_ticker(
            ticker, cantidad, inst, mt, valuacion, hoy, horizonte_fin
        )
        if "sin_proyeccion" in proj:
            sin_proyeccion.append(proj["sin_proyeccion"])
            continue

        moneda = proj["moneda"]
        nombre = proj["nombre"]
        cobros = proj["cobros"]

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

        cupon_por_unidad = proj["cupon_por_unidad"]
        instrumentos_out.append(
            {
                "ticker": ticker,
                "nombre": nombre,
                "moneda": moneda,
                "cantidad_actual": round(cantidad, 8),
                "fecha_vencimiento": venc,
                "periodicidad_meses": proj["periodicidad_meses"],
                "periodicidad_label": proj["periodicidad_label"],
                "cupon_por_unidad": round(cupon_por_unidad, 6) if cupon_por_unidad is not None else None,
                "confianza": proj["confianza"],
                "metodo_capital": proj["metodo_capital"],
                "cobros_proyectados": len(cobros),
                "proximo_cobro": proximo_cobro,
                "total_proyectado_usd": round(total_inst_usd, 2),
                "total_proyectado_ars": round(total_inst_ars, 2),
                "notas": proj["notas"],
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


# ── Métricas de bono para la pantalla Vencimientos ───────────────────────────

def _flujo_por_ticker_hasta_vencimiento(
    cartera: str | None, db: Session, rendimientos: list[dict] | None = None
) -> dict[str, dict]:
    """Cobros proyectados de **toda la vida** de cada bono (hasta su vencimiento), sin recortar
    al horizonte de la pantalla de flujo de caja. Clave = ticker, valor = salida de
    `_proyectar_cobros_ticker`. Reutiliza la misma inferencia; sirve para TIR y duration.
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

    if rendimientos is None:
        rendimientos = get_rendimiento_por_ticker(cartera, db)
    valuacion = {r["ticker"]: r for r in rendimientos}

    out: dict[str, dict] = {}
    for ticker, cantidad in cantidad_por_ticker.items():
        if cantidad <= EPS:
            continue
        inst = instrumentos.get(ticker)
        if inst is None or inst.fecha_vencimiento is None or inst.fecha_vencimiento <= hoy:
            continue
        mt = movs_por_ticker.get(ticker, [])
        out[ticker] = _proyectar_cobros_ticker(
            ticker, cantidad, inst, mt, valuacion, hoy, inst.fecha_vencimiento
        )
    return out


def _metricas_renta_fija(
    proj: dict | None, val: dict | None, venc: date, hoy: date
) -> dict:
    """TIR al vencimiento, duration y paridad de un bono, a partir del flujo inferido.

    Todo estimado: el cronograma no es oficial (`proj` viene de `_proyectar_cobros_ticker`) y
    la paridad asume valor nominal residual = par (1 por unidad), aproximando la fracción
    amortizada por el conteo de cuotas inferidas.
    """
    vacio = {
        "tir_vencimiento": None,
        "duration_macaulay": None,
        "duration_modificada": None,
        "paridad": None,
        "valor_tecnico": None,
        "interes_corrido": None,
        "valor_residual": None,
        "moneda_metricas": None,
        "metricas_estimadas": False,
        "metricas_nota": None,
    }
    if proj is None or "sin_proyeccion" in proj:
        return {**vacio, "metricas_nota": "Sin historial de cupones para inferir el cronograma."}

    moneda = proj["moneda"]
    cobros = sorted(proj["cobros"], key=lambda c: c["fecha"])
    metodo = proj["metodo_capital"]
    precio_actual = float(val["precio_actual"]) if val and val.get("precio_actual") else None
    cantidad = float(val["cantidad_actual"]) if val and val.get("cantidad_actual") else None

    out = {**vacio, "moneda_metricas": moneda, "metricas_estimadas": True}
    notas: list[str] = []

    # ── TIR al vencimiento + duration (sobre el valor de mercado de la posición) ──
    if precio_actual is not None and cantidad is not None and cobros:
        valor_mercado = precio_actual * cantidad
        flujos = [(hoy, -valor_mercado)] + [(c["fecha"], c["monto_nativo"]) for c in cobros]
        tir = _calcular_xirr(flujos)
        out["tir_vencimiento"] = round(tir, 4) if tir is not None else None

        if tir is not None and tir > -1:
            pv_total = 0.0
            pv_pond = 0.0
            for c in cobros:
                t = (c["fecha"] - hoy).days / 365
                if t <= 0:
                    continue
                pv = c["monto_nativo"] / ((1 + tir) ** t)
                pv_total += pv
                pv_pond += t * pv
            if pv_total > EPS:
                macaulay = pv_pond / pv_total
                out["duration_macaulay"] = round(macaulay, 3)
                out["duration_modificada"] = round(macaulay / (1 + tir), 3)
        if metodo == "bullet":
            notas.append(
                "Capital al vencimiento estimado con el precio de mercado: la TIR tiende a la "
                "TIR corriente."
            )
    elif metodo == "sin_estimacion":
        notas.append("Sin precio cargado: no se puede calcular TIR ni duration.")
    elif not cobros:
        notas.append("Sin cobros dentro de la vida restante del bono.")

    # ── paridad = precio / valor técnico (valor residual + interés corrido) ──
    cupon_unit = proj.get("cupon_por_unidad")
    periodicidad = proj.get("periodicidad_meses")
    if precio_actual is not None and cupon_unit is not None and periodicidad:
        # fracción del período de cupón ya transcurrida
        prox = next((c["fecha"] for c in cobros if c["tipo"] == "cupon"), None)
        if prox is None:
            prox = venc
        anterior = _sumar_meses(prox, -periodicidad)
        largo = (prox - anterior).days
        transcurrido = (hoy - anterior).days
        frac = min(max(transcurrido / largo, 0.0), 1.0) if largo > 0 else 0.0
        interes_corrido = cupon_unit * frac

        # valor residual por unidad, en términos de par = 1
        if metodo == "amortizacion_inferida":
            n_hist = proj.get("amort_historicas", 0)
            n_fut = proj.get("amort_futuras", 0)
            residual = n_fut / (n_hist + n_fut) if (n_hist + n_fut) > 0 else 1.0
            notas.append(
                "Valor residual estimado por el conteo de cuotas de amortización inferidas."
            )
        else:
            residual = 1.0

        valor_tecnico = residual + interes_corrido
        out["interes_corrido"] = round(interes_corrido, 6)
        out["valor_residual"] = round(residual, 6)
        out["valor_tecnico"] = round(valor_tecnico, 6)
        if valor_tecnico > EPS:
            out["paridad"] = round(precio_actual / valor_tecnico, 4)
    elif precio_actual is not None:
        notas.append("Sin cupones inferidos: no se estima el valor técnico ni la paridad.")

    out["metricas_nota"] = " ".join(notas) if notas else None
    return out


def get_vencimientos_completo(cartera: str | None, db: Session) -> dict:
    """Pantalla Vencimientos enriquecida: cada instrumento con paridad, TIR al vencimiento y
    duration modificada (estimadas sobre el flujo inferido), más el resumen de qué porción de
    la cartera vence por año.
    """
    hoy = date.today()
    rendimientos = get_rendimiento_por_ticker(cartera, db)
    valuacion = {r["ticker"]: r for r in rendimientos}
    items = get_vencimientos(cartera, db, rendimientos=rendimientos)
    flujos = _flujo_por_ticker_hasta_vencimiento(cartera, db, rendimientos=rendimientos)

    for item in items:
        venc = item["fecha_vencimiento"]
        if item.get("vencido"):
            item.update(
                {
                    "tir_vencimiento": None,
                    "duration_macaulay": None,
                    "duration_modificada": None,
                    "paridad": None,
                    "valor_tecnico": None,
                    "interes_corrido": None,
                    "valor_residual": None,
                    "moneda_metricas": None,
                    "metricas_estimadas": False,
                    "metricas_nota": "Instrumento vencido.",
                }
            )
            continue
        metr = _metricas_renta_fija(flujos.get(item["ticker"]), valuacion.get(item["ticker"]), venc, hoy)
        item.update(metr)

    # ── resumen: valor que vence por año y su peso en la cartera ──
    resumen = get_resumen(cartera, db)
    total_usd = resumen.get("valor_actual_usd") or 0.0
    total_ars = resumen.get("valor_actual_ars") or 0.0

    por_anio_map: dict[int, dict] = {}
    for item in items:
        if item.get("vencido"):
            continue  # B16: el resumen "% que vence por año" es una proyección; los vencidos
                      # (años ya pasados) siguen en `items` pero no acá.
        anio = item["fecha_vencimiento"].year
        bucket = por_anio_map.setdefault(
            anio,
            {"anio": anio, "valor_usd": 0.0, "valor_ars": 0.0, "tickers": [], "sin_valuar": 0},
        )
        bucket["tickers"].append(item["ticker"])
        v_usd = item.get("valor_actual_usd")
        v_ars = item.get("valor_actual_ars")
        if v_usd is None and v_ars is None:
            bucket["sin_valuar"] += 1
        bucket["valor_usd"] += v_usd or 0.0
        bucket["valor_ars"] += v_ars or 0.0

    por_anio = []
    for anio in sorted(por_anio_map):
        b = por_anio_map[anio]
        por_anio.append(
            {
                "anio": anio,
                "valor_usd": round(b["valor_usd"], 2),
                "valor_ars": round(b["valor_ars"], 2),
                "pct_cartera_usd": round(b["valor_usd"] / total_usd, 4) if total_usd > EPS else None,
                "pct_cartera_ars": round(b["valor_ars"] / total_ars, 4) if total_ars > EPS else None,
                "cantidad_instrumentos": len(b["tickers"]),
                "instrumentos_sin_valuar": b["sin_valuar"],
                "tickers": b["tickers"],
            }
        )

    return {
        "generado": hoy,
        "items": items,
        "por_anio": por_anio,
        "cartera_valor_usd": round(total_usd, 2),
        "cartera_valor_ars": round(total_ars, 2),
    }
