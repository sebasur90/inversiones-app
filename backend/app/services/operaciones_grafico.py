"""Operaciones propias (compras y ventas) de un ticker, ubicadas sobre la serie del gráfico técnico.

El adaptador con la base del motor puro `operaciones_grafico_engine`. El resultado de cada venta y
de cada posición sale de la misma convención de costo promedio del resto de la app
(`inversiones_analytics._recorrer_movs_ticker`) y el no realizado de una posición abierta, de
`_valuar_tenencia`: lo que se ve en el gráfico coincide con el P&L realizado y no realizado.

Lo único que cambia respecto de esas cuentas es *dónde* se dibuja la marca (ver el docstring del
motor): el resultado es siempre el real, en USD MEP.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..database import MovimientoInversion
from . import intervalos_engine
from . import inversiones_analytics as ia
from . import ohlcv_analytics
from . import operaciones_grafico_engine as eng

MAX_BARRAS = 3000
TIPOS_MARCA = ("compra", "venta", "amortizacion")
# Cobros: no tienen precio unitario (`precio` es el monto total), así que se ubican sólo por fecha.
TIPOS_COBRO = eng.TIPOS_INGRESO


def _barras(db: Session, ticker: str, variante: str, hoy: date) -> tuple[list, str]:
    serie = ohlcv_analytics.get_serie_barras(
        ticker, date.min, hoy, db, max_barras=MAX_BARRAS, variante=variante,
    )
    return serie["barras"], serie["moneda"]


def _vacio(ticker: str, variante: str, moneda: str, advertencias: list[str]) -> dict:
    return {
        "ticker": ticker, "variante": variante, "moneda": moneda,
        "operaciones": [], "ciclos": [], "fuera_de_serie": 0, "advertencias": advertencias,
    }


def get_operaciones_grafico(
    ticker: str, variante: str, db: Session, intervalo: str = intervalos_engine.DIARIO,
) -> dict:
    """`variante` es una serie concreta (`local` | `subyacente`), nunca `referencia`.

    Todo se calcula sobre la serie diaria (ubicación, precio equivalente, contexto, resultado). Con
    `intervalo` semanal o mensual, al final cada marca pasa a la barra agregada que la contiene."""
    hoy = date.today()
    movs = (
        db.query(MovimientoInversion)
        .filter(MovimientoInversion.ticker == ticker)
        .order_by(MovimientoInversion.fecha, MovimientoInversion.id)
        .all()
    )
    barras, moneda_serie = _barras(db, ticker, variante, hoy)
    if not movs:
        return _vacio(ticker, variante, moneda_serie, [])

    advertencias: list[str] = []
    if not barras:
        advertencias.append("sin_serie")

    # La vela del instrumento local sirve de referencia para ubicar el precio pagado sobre otra
    # serie. Con la serie local misma no hace falta.
    if variante == "local":
        barras_local, moneda_local = barras, moneda_serie
    else:
        barras_local, moneda_local = _barras(db, ticker, "local", hoy)

    mep_cache: dict = {}
    series_ctx = eng.series_contexto(barras) if barras else None
    indice_de_fecha = {b.fecha: i for i, b in enumerate(barras)}
    ciclos = eng.partir_en_ciclos(movs)
    ciclo_de = {id(m): n for n, ciclo in enumerate(ciclos, start=1) for m in ciclo}

    # ── Resultado por ciclo y por venta, con la convención de costo promedio de la app ──
    resultado_venta: dict[int, tuple[float, float | None]] = {}
    ciclos_out: list[dict] = []
    precios_por_ticker = ia._precios_por_ticker(db)
    costo_incompleto = False

    for n, ciclo in enumerate(ciclos, start=1):
        def _al_realizar(mov, monto_usd, _monto_ars, costo_removido_usd, _costo_removido_ars):
            resultado = monto_usd - costo_removido_usd
            resultado_venta[id(mov)] = (resultado, eng.porcentaje(resultado, costo_removido_usd))

        est = ia._recorrer_movs_ticker(
            ciclo, db, mep_cache, {}, None, ars_real_valido_inicial=False, on_realizado=_al_realizar,
        )
        costo_incompleto = costo_incompleto or est.costo_incompleto

        compras = [m for m in ciclo if m.tipo_movimiento == "compra"]
        comprado_usd = 0.0
        for m in compras:
            monto = ia._monto_usd(m, db, mep_cache)
            if monto is not None:
                comprado_usd += monto

        abierto = est.cantidad_held > ia.EPS
        no_realizado_usd = None
        no_realizado_pct = None
        if abierto:
            valuacion = ia._valuar_tenencia(
                precios_por_ticker.get(ticker), est.cantidad_held, hoy, db, mep_cache,
            )
            if valuacion is not None and valuacion.valor_usd is not None:
                no_realizado_usd = valuacion.valor_usd - est.costo_usd
                no_realizado_pct = eng.porcentaje(no_realizado_usd, est.costo_usd)

        if abierto:
            resultado_usd = (
                est.realizado_usd + no_realizado_usd + est.ingresos_usd
                if no_realizado_usd is not None else None
            )
        else:
            resultado_usd = est.realizado_usd + est.ingresos_usd

        ciclos_out.append({
            "ciclo": n,
            "desde": ciclo[0].fecha,
            # La fecha de la última venta o amortización: un dividendo que llega después de salir
            # se atribuye al ciclo pero no lo extiende.
            "hasta": None if abierto else max(
                (m.fecha for m in ciclo if m.tipo_movimiento in eng.TIPOS_CIERRE), default=ciclo[-1].fecha,
            ),
            "abierto": abierto,
            "cantidad_abierta": est.cantidad_held if abierto else 0.0,
            "comprado_usd": round(comprado_usd, 2),
            "realizado_usd": round(est.realizado_usd, 2),
            "no_realizado_usd": round(no_realizado_usd, 2) if no_realizado_usd is not None else None,
            "no_realizado_pct": no_realizado_pct,
            "ingresos_usd": round(est.ingresos_usd, 2),
            "resultado_usd": round(resultado_usd, 2) if resultado_usd is not None else None,
            "resultado_pct": eng.porcentaje(resultado_usd, comprado_usd),
            "costo_promedio_grafico": None,
            "vwap": _vwap_del_ciclo(ciclo, abierto, barras),
            "precio_actual_grafico": barras[-1].cierre if (abierto and barras) else None,
        })

    # ── Marcas: dónde se dibuja cada operación ──
    operaciones: list[dict] = []
    fuera_de_serie = 0
    compras_por_ciclo: dict[int, list[tuple[float, float | None]]] = {}

    for mov in movs:
        if mov.tipo_movimiento not in TIPOS_MARCA + TIPOS_COBRO or id(mov) not in ciclo_de:
            continue
        n = ciclo_de[id(mov)]
        if mov.tipo_movimiento in TIPOS_COBRO:
            operaciones.append(_cobro(mov, n, barras, db, mep_cache))
            if operaciones[-1]["fecha_barra"] is None:
                fuera_de_serie += 1
            continue

        cantidad = float(mov.cantidad or 0)
        precio = float(mov.precio)
        ubicada = _ubicar(mov, precio, barras, barras_local, moneda_serie, moneda_local, variante, db, mep_cache)
        if ubicada is None:
            fuera_de_serie += 1
            fecha_barra = precio_grafico = None
            aproximado, motivo = False, None
        else:
            fecha_barra, precio_grafico, aproximado, motivo = ubicada

        monto_usd = ia._monto_usd(mov, db, mep_cache)
        precio_usd_mep = monto_usd / cantidad if (monto_usd is not None and cantidad > ia.EPS) else None
        resultado = resultado_venta.get(id(mov))

        if mov.tipo_movimiento == "compra":
            compras_por_ciclo.setdefault(n, []).append((cantidad, precio_grafico))

        # Contexto de mercado y qué pasó después: sólo si la operación cayó dentro de la serie.
        idx = indice_de_fecha.get(fecha_barra) if fecha_barra is not None else None
        contexto = (
            eng.contexto_en(barras, idx, series_ctx)
            if idx is not None and series_ctx is not None
            else {"rsi": None, "dist_sma200_pct": None, "rango_52s_pct": None}
        )
        posterior = {f"post_{d}_pct": None for d in eng.DIAS_POSTERIOR}
        if mov.tipo_movimiento == "venta" and idx is not None:
            posterior = {f"post_{d}_pct": _redondear(eng.variacion_posterior(barras, idx, d), 2)
                         for d in eng.DIAS_POSTERIOR}

        operaciones.append({
            "fecha": mov.fecha, "fecha_barra": fecha_barra, "tipo": mov.tipo_movimiento,
            "cartera": mov.cartera, "cantidad": cantidad, "precio": precio, "moneda": mov.moneda,
            "precio_usd_mep": round(precio_usd_mep, 4) if precio_usd_mep is not None else None,
            "precio_grafico": round(precio_grafico, 6) if precio_grafico is not None else None,
            "aproximado": aproximado, "motivo_aproximado": motivo, "ciclo": n,
            "resultado_usd": round(resultado[0], 2) if resultado else None,
            "resultado_pct": resultado[1] if resultado else None,
            "rsi": _redondear(contexto["rsi"], 1),
            "dist_sma200_pct": _redondear(contexto["dist_sma200_pct"], 2),
            "rango_52s_pct": _redondear(contexto["rango_52s_pct"], 1),
            **posterior,
        })

    for ciclo_out in ciclos_out:
        ciclo_out["costo_promedio_grafico"] = eng.costo_promedio_grafico(
            compras_por_ciclo.get(ciclo_out["ciclo"], []),
        )

    if costo_incompleto:
        advertencias.append("costo_incompleto")
    if intervalo != intervalos_engine.DIARIO:
        _reubicar_en_intervalo(operaciones, ciclos_out, barras, intervalo)
    return {
        "ticker": ticker, "variante": variante, "moneda": moneda_serie,
        "operaciones": operaciones, "ciclos": ciclos_out,
        "fuera_de_serie": fuera_de_serie, "advertencias": advertencias,
    }


def _reubicar_en_intervalo(operaciones: list[dict], ciclos: list[dict], barras: list, intervalo: str) -> None:
    """Pasa `fecha_barra` (y el VWAP) de la barra diaria a la barra agregada que la contiene, cuya
    fecha es la última rueda del período. El precio de cada marca no cambia: la vela diaria queda
    dentro del rango de la semanal o mensual, así que sigue cayendo sobre la vela."""
    ultima_rueda: dict[tuple, date] = {}
    for b in barras:  # ascendentes: la última de cada período pisa a las anteriores
        ultima_rueda[intervalos_engine.clave_periodo(b.fecha, intervalo)] = b.fecha

    def reubicar(fecha: date) -> date:
        return ultima_rueda.get(intervalos_engine.clave_periodo(fecha, intervalo), fecha)

    for op in operaciones:
        if op["fecha_barra"] is not None:
            op["fecha_barra"] = reubicar(op["fecha_barra"])
    for ciclo in ciclos:
        if ciclo["vwap"]:
            # Un punto por período: el valor de la última rueda, que es el VWAP al cierre de la barra.
            por_periodo = {reubicar(p["fecha"]): p["valor"] for p in ciclo["vwap"]}
            ciclo["vwap"] = [{"fecha": f, "valor": v} for f, v in por_periodo.items()]


def _ubicar(
    mov, precio: float, barras: list, barras_local: list, moneda_serie: str, moneda_local: str,
    variante: str, db: Session, mep_cache: dict,
) -> tuple[date, float, bool, str | None] | None:
    """`(fecha_barra, precio_en_el_gráfico, aproximado, motivo)` o None si queda fuera de la serie."""
    hallada = eng.barra_de_fecha(barras, mov.fecha)
    if hallada is None:
        return None
    barra, exacta = hallada
    aproximado = not exacta
    motivo = None if exacta else eng.MOTIVO_FECHA_CERCANA

    # El precio pagado se expresa en la moneda de la serie local (la del instrumento).
    precio_local = ia._convertir(precio, mov.moneda, moneda_local, mov.fecha, db, mep_cache)
    if precio_local is None:
        return barra.fecha, barra.cierre, True, eng.MOTIVO_SIN_TIPO_DE_CAMBIO

    if variante == "local":
        return barra.fecha, precio_local, aproximado, motivo

    local = eng.barra_de_fecha(barras_local, mov.fecha)
    barra_local = local[0] if local is not None else None
    precio_graf, aprox_precio, motivo_precio = eng.precio_equivalente(precio_local, barra_local, barra)
    if local is not None and not local[1]:
        aprox_precio = True
        motivo_precio = motivo_precio or eng.MOTIVO_FECHA_CERCANA
    return barra.fecha, precio_graf, aproximado or aprox_precio, motivo_precio or motivo


def _redondear(valor: float | None, decimales: int) -> float | None:
    return round(valor, decimales) if valor is not None else None


def _cobro(mov, ciclo: int, barras: list, db: Session, mep_cache: dict) -> dict:
    """Dividendo o cupón: sin precio en el gráfico, sólo la rueda en la que se cobró y el monto."""
    hallada = eng.barra_de_fecha(barras, mov.fecha)
    monto_usd = ia._monto_usd(mov, db, mep_cache)
    return {
        "fecha": mov.fecha, "fecha_barra": hallada[0].fecha if hallada else None,
        "tipo": mov.tipo_movimiento, "cartera": mov.cartera, "cantidad": float(mov.cantidad or 0),
        "precio": float(mov.precio), "moneda": mov.moneda, "precio_usd_mep": None,
        "precio_grafico": None, "aproximado": bool(hallada and not hallada[1]),
        "motivo_aproximado": eng.MOTIVO_FECHA_CERCANA if hallada and not hallada[1] else None,
        "ciclo": ciclo, "resultado_usd": None, "resultado_pct": None,
        "monto_usd": round(monto_usd, 2) if monto_usd is not None else None,
    }


def _vwap_del_ciclo(ciclo: list, abierto: bool, barras: list) -> list[dict] | None:
    """VWAP anclado a la primera compra del ciclo, hasta la venta final (o hasta hoy si sigue
    abierto). None si la compra es anterior a la serie o la serie no tiene volumen."""
    primera = eng.barra_de_fecha(barras, ciclo[0].fecha)
    if primera is None:
        return None
    desde = next(i for i, b in enumerate(barras) if b.fecha == primera[0].fecha)
    hasta = len(barras) - 1
    if not abierto:
        cierres = [m for m in ciclo if m.tipo_movimiento in eng.TIPOS_CIERRE]
        final = eng.barra_de_fecha(barras, cierres[-1].fecha) if cierres else None
        if final is not None:
            hasta = next(i for i, b in enumerate(barras) if b.fecha == final[0].fecha)
    valores = eng.vwap_anclado(barras[:hasta + 1], desde)
    if valores is None:
        return None
    return [
        {"fecha": barras[desde + k].fecha, "valor": round(v, 6)}
        for k, v in enumerate(valores) if v is not None
    ]
