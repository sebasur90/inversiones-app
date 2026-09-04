"""Orquestación del sync desde Google Sheets con validación de calidad."""
import time
import logging
from datetime import datetime, UTC
from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from ..database import (
    InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado,
    ObjetivoInversion, RebalanceoObjetivo, BenchmarkValor, ConfiguracionCartera,
    SyncRun, SyncIssue, EstadoMarketDataTicker, WatchlistItem, PrecioWatchlist
)
from .sheets_client import fetch_sheet_data
from .inversiones_analytics import get_carteras
from .validation.types import ValidationIssue, Severity
from .validation.reglas_estructura import validar_estructura_tab
from .validation import reglas_instrumentos, reglas_movimientos, reglas_precios, reglas_objetivos, reglas_rebalanceo, reglas_benchmarks, reglas_configuracion, reglas_tipos_cambio, reglas_watchlist, reglas_cer
from .validation.health_score import calcular_health_score
from . import market_data
from .market_data import indices as market_data_indices
from .market_data import precios as market_data_precios

logger = logging.getLogger("calidad_datos")


def _tickers_conocidos_db(db: Session) -> set[str]:
    """Lee tickers válidos actuales de la DB para fallback."""
    return {row[0] for row in db.query(InstrumentoInversion.ticker).all()}


def _carteras_conocidas_db(db: Session) -> set[str]:
    """Lee carteras actuales de la DB para fallback."""
    return set(get_carteras(db))


def _tab_actualmente_no_vacia(db: Session, tabla_name: str) -> bool:
    """Verifica si una tabla espejo tiene filas actualmente en la DB."""
    tabla_map = {
        "Instrumentos": InstrumentoInversion,
        "Movimientos": MovimientoInversion,
        "Precios": PrecioInstrumento,
        "Objetivos": ObjetivoInversion,
        "Rebalanceo": RebalanceoObjetivo,
        "Benchmarks": BenchmarkValor,
        "Configuracion": ConfiguracionCartera,
        "Watchlist": WatchlistItem,
    }
    tabla = tabla_map.get(tabla_name)
    if not tabla:
        return False
    return db.query(tabla).first() is not None


def _prune_sync_runs(db: Session, keep: int = 20):
    """Elimina SyncRun antiguos, mantiene los últimos `keep`."""
    subq = db.query(SyncRun.id).order_by(SyncRun.timestamp.desc()).limit(keep).subquery()
    db.query(SyncIssue).filter(SyncIssue.sync_run_id.notin_(db.query(subq))).delete()
    db.query(SyncRun).filter(SyncRun.id.notin_(db.query(subq))).delete()


def sync_from_sheet(db: Session) -> dict:
    """Sincroniza datos del Sheet con validación, per-tab isolation y persistencia de historial."""
    inicio = time.monotonic()
    # naive en UTC: la columna SyncRun.timestamp es DateTime sin timezone
    timestamp = datetime.now(UTC).replace(tzinfo=None)
    issues: list[ValidationIssue] = []

    # Leer datos del Sheet (raw)
    raw_data = fetch_sheet_data()

    # Fallback: conocidos actuales de DB
    tickers_fallback = _tickers_conocidos_db(db)
    carteras_fallback = _carteras_conocidas_db(db)
    tickers_conocidos = tickers_fallback.copy()
    carteras_conocidas = carteras_fallback.copy()

    # Estado de cada pestaña
    tabs_bloqueadas = set()
    instrumentos_validos = []
    movimientos_validos = []
    cer_mep_movimientos = []
    precios_validos = []
    cer_mep_precios = []
    objetivos_validos = []
    rebalanceo_validos = []
    benchmarks_validos = []
    configuracion_validos = []
    watchlist_validos = []

    # Validar Instrumentos (obligatoria)
    raw_inst = raw_data.get("Instrumentos")
    if raw_inst and raw_inst.error_lectura:
        issues.append(ValidationIssue(
            tab="Instrumentos", regla="lectura_fallo",
            mensaje=f"Error leyendo Instrumentos: {raw_inst.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.CRITICO
        ))
        tabs_bloqueadas.add("Instrumentos")
    elif not raw_inst or not raw_inst.presente:
        issues.append(ValidationIssue(
            tab="Instrumentos", regla="pestana_faltante",
            mensaje="Pestaña Instrumentos no encontrada",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.CRITICO
        ))
        tabs_bloqueadas.add("Instrumentos")
    else:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Instrumentos", raw_inst.header, raw_inst.rows,
            tab_requerida=True, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Instrumentos")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Instrumentos")
        else:
            instrumentos_validos, tickers_conocidos, issues_inst = reglas_instrumentos.validar_instrumentos(raw_inst.rows)
            issues.extend(issues_inst)

    # Validar Movimientos (obligatoria)
    raw_mov = raw_data.get("Movimientos")
    if raw_mov and raw_mov.error_lectura:
        issues.append(ValidationIssue(
            tab="Movimientos", regla="lectura_fallo",
            mensaje=f"Error leyendo Movimientos: {raw_mov.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.CRITICO
        ))
        tabs_bloqueadas.add("Movimientos")
    elif not raw_mov or not raw_mov.presente:
        issues.append(ValidationIssue(
            tab="Movimientos", regla="pestana_faltante",
            mensaje="Pestaña Movimientos no encontrada",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.CRITICO
        ))
        tabs_bloqueadas.add("Movimientos")
    else:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Movimientos", raw_mov.header, raw_mov.rows,
            tab_requerida=True, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Movimientos")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Movimientos")
        else:
            movimientos_validos, cer_mep_movimientos, issues_mov = reglas_movimientos.validar_movimientos(
                raw_mov.rows, tickers_conocidos
            )
            issues.extend(issues_mov)
            # Unión con el fallback de la DB, no reemplazo: si el único movimiento de una
            # cartera se rechaza por otro motivo, esa cartera seguiría existiendo en la DB y
            # reemplazar el set invalidaría (y borraría) sus objetivos y su fila de rebalanceo.
            carteras_conocidas = carteras_fallback | {m["cartera"] for m in movimientos_validos}

    # Validar Precios (obligatoria)
    raw_pre = raw_data.get("Precios")
    if raw_pre and raw_pre.error_lectura:
        issues.append(ValidationIssue(
            tab="Precios", regla="lectura_fallo",
            mensaje=f"Error leyendo Precios: {raw_pre.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.CRITICO
        ))
        tabs_bloqueadas.add("Precios")
    elif not raw_pre or not raw_pre.presente:
        issues.append(ValidationIssue(
            tab="Precios", regla="pestana_faltante",
            mensaje="Pestaña Precios no encontrada",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.CRITICO
        ))
        tabs_bloqueadas.add("Precios")
    else:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Precios", raw_pre.header, raw_pre.rows,
            tab_requerida=True, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Precios")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Precios")
        else:
            precios_validos, cer_mep_precios, issues_pre = reglas_precios.validar_precios(raw_pre.rows)
            issues.extend(issues_pre)
            issues.extend(reglas_precios.detectar_huecos(precios_validos))
            issues.extend(reglas_precios.detectar_saltos_extremos(precios_validos))

    # Cross-tab: detectar_sin_precio
    if "Instrumentos" not in tabs_bloqueadas and "Precios" not in tabs_bloqueadas:
        issues.extend(reglas_instrumentos.detectar_sin_precio(instrumentos_validos, precios_validos))

    # Consolidar CER/MEP
    indices_mercado, advertencias_cer = _consolidar_indices_mercado(cer_mep_movimientos, cer_mep_precios)
    issues.extend(advertencias_cer)

    # CER/MEP se arma con las columnas de Movimientos + Precios: si alguna de las dos está
    # bloqueada, reescribir la tabla perdería el histórico que aportaba esa pestaña (y con él
    # toda métrica ARS real). Se preserva lo que ya está en la DB, igual que el resto de tablas.
    fuentes_cer_mep_bloqueadas = sorted({"Movimientos", "Precios"} & tabs_bloqueadas)
    if fuentes_cer_mep_bloqueadas:
        issues.append(ValidationIssue(
            tab="CER/MEP", regla="fuente_bloqueada",
            mensaje=f"No se actualizó CER/MEP: {', '.join(fuentes_cer_mep_bloqueadas)} bloqueada(s)",
            impacto="Se preservó el histórico de CER/MEP anterior",
            severidad=Severity.ADVERTENCIA
        ))

    # Validar Objetivos (opcional)
    raw_obj = raw_data.get("Objetivos")
    if raw_obj and raw_obj.error_lectura:
        issues.append(ValidationIssue(
            tab="Objetivos", regla="lectura_fallo",
            mensaje=f"Error leyendo Objetivos: {raw_obj.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.ADVERTENCIA
        ))
        tabs_bloqueadas.add("Objetivos")
    elif raw_obj and raw_obj.presente:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Objetivos", raw_obj.header, raw_obj.rows,
            tab_requerida=False, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Objetivos")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Objetivos")
        else:
            objetivos_validos, issues_obj = reglas_objetivos.validar_objetivos(raw_obj.rows, carteras_conocidas)
            issues.extend(issues_obj)

    # Validar Rebalanceo (opcional)
    raw_reb = raw_data.get("Rebalanceo")
    if raw_reb and raw_reb.error_lectura:
        issues.append(ValidationIssue(
            tab="Rebalanceo", regla="lectura_fallo",
            mensaje=f"Error leyendo Rebalanceo: {raw_reb.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.ADVERTENCIA
        ))
        tabs_bloqueadas.add("Rebalanceo")
    elif raw_reb and raw_reb.presente:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Rebalanceo", raw_reb.header, raw_reb.rows,
            tab_requerida=False, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Rebalanceo")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Rebalanceo")
        else:
            rebalanceo_validos, issues_reb = reglas_rebalanceo.validar_rebalanceo(
                raw_reb.rows, tickers_conocidos, carteras_conocidas
            )
            issues.extend(issues_reb)

    # Validar Benchmarks (opcional)
    raw_ben = raw_data.get("Benchmarks")
    if raw_ben and raw_ben.error_lectura:
        issues.append(ValidationIssue(
            tab="Benchmarks", regla="lectura_fallo",
            mensaje=f"Error leyendo Benchmarks: {raw_ben.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.ADVERTENCIA
        ))
        tabs_bloqueadas.add("Benchmarks")
    elif raw_ben and raw_ben.presente:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Benchmarks", raw_ben.header, raw_ben.rows,
            tab_requerida=False, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Benchmarks")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Benchmarks")
        else:
            benchmarks_validos, issues_ben = reglas_benchmarks.validar_benchmarks(raw_ben.rows)
            issues.extend(issues_ben)

    # Validar Configuracion (opcional)
    raw_cfg = raw_data.get("Configuracion")
    if raw_cfg and raw_cfg.error_lectura:
        issues.append(ValidationIssue(
            tab="Configuracion", regla="lectura_fallo",
            mensaje=f"Error leyendo Configuracion: {raw_cfg.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.ADVERTENCIA
        ))
        tabs_bloqueadas.add("Configuracion")
    elif raw_cfg and raw_cfg.presente:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Configuracion", raw_cfg.header, raw_cfg.rows,
            tab_requerida=False, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Configuracion")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Configuracion")
        else:
            configuracion_validos, issues_cfg = reglas_configuracion.validar_configuracion(raw_cfg.rows)
            issues.extend(issues_cfg)

    # Validar Watchlist (opcional): instrumentos a seguir que todavía no están en cartera.
    raw_wl = raw_data.get("Watchlist")
    if raw_wl and raw_wl.error_lectura:
        issues.append(ValidationIssue(
            tab="Watchlist", regla="lectura_fallo",
            mensaje=f"Error leyendo Watchlist: {raw_wl.error_lectura}",
            impacto="Pestaña bloqueada, datos anteriores preservados",
            severidad=Severity.ADVERTENCIA
        ))
        tabs_bloqueadas.add("Watchlist")
    elif raw_wl and raw_wl.presente:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Watchlist", raw_wl.header, raw_wl.rows,
            tab_requerida=False, tab_actual_no_vacia=_tab_actualmente_no_vacia(db, "Watchlist")
        )
        issues.extend(issues_est)
        if bloqueada_est:
            tabs_bloqueadas.add("Watchlist")
        else:
            watchlist_validos, issues_wl = reglas_watchlist.validar_watchlist(raw_wl.rows)
            issues.extend(issues_wl)

    # Validar Tipos de Cambio (opcional): fuente dedicada de CER/MEP, tiene prioridad sobre las
    # columnas CER/MEP embebidas en Movimientos/Precios (que sólo traen valor en fechas con
    # operación o carga de precio).
    tipos_cambio_validos = []
    raw_tc = raw_data.get("Tipos de Cambio")
    if raw_tc and raw_tc.error_lectura:
        issues.append(ValidationIssue(
            tab="Tipos de Cambio", regla="lectura_fallo",
            mensaje=f"Error leyendo Tipos de Cambio: {raw_tc.error_lectura}",
            impacto="No se aplicó como fuente prioritaria de CER/MEP",
            severidad=Severity.ADVERTENCIA
        ))
    elif raw_tc and raw_tc.presente:
        bloqueada_est, issues_est = validar_estructura_tab(
            "Tipos de Cambio", raw_tc.header, raw_tc.rows,
            tab_requerida=False, tab_actual_no_vacia=False
        )
        issues.extend(issues_est)
        if not bloqueada_est:
            tipos_cambio_validos, issues_tc = reglas_tipos_cambio.validar_tipos_cambio(raw_tc.rows)
            issues.extend(issues_tc)

    if tipos_cambio_validos and not fuentes_cer_mep_bloqueadas:
        indices_mercado = _aplicar_tipos_cambio(indices_mercado, tipos_cambio_validos)

    # Persistencia selectiva: DELETE + INSERT solo para tablas NO bloqueadas
    if "Instrumentos" not in tabs_bloqueadas:
        db.query(InstrumentoInversion).delete()
        db.flush()
        for inst in instrumentos_validos:
            db.add(InstrumentoInversion(**inst))

    if "Movimientos" not in tabs_bloqueadas:
        db.query(MovimientoInversion).delete()
        db.flush()
        for mov in movimientos_validos:
            db.add(MovimientoInversion(
                fecha=mov["fecha"],
                cartera=mov["cartera"],
                ticker=mov["ticker"],
                tipo_movimiento=mov["tipo_movimiento"],
                cantidad=mov["cantidad"],
                precio=mov["precio"],
                moneda=mov["moneda"],
                comision=mov["comision"],
            ))

    # Estado persistente por ticker (A1: factor de escala ya calibrado; A3: backfill que no
    # converge) y memos de las llamadas a IOL. Viven a nivel de sync, no dentro del bloque de
    # Precios, porque los comparten las dos rutas de precios -- cartera y watchlist -- y los
    # paneles de IOL tienen que pedirse una sola vez por corrida (cupo mensual).
    usa_apis = market_data.use_external_apis()
    estado_por_ticker: dict = {}
    paneles_fn = None
    fci_fn = None
    if usa_apis:
        estado_por_ticker = {
            r.ticker: {
                "factor_escala": float(r.factor_escala) if r.factor_escala is not None else None,
                "factor_fecha": r.factor_fecha,
                "backfill_estado": r.backfill_estado,
                "backfill_intento": r.backfill_intento,
            }
            for r in db.query(EstadoMarketDataTicker).all()
        }
        paneles_fn = market_data_precios.memo_paneles(db)
        fci_fn = market_data_precios.memo_fci(db)

    precios_api_count = 0
    if "Precios" not in tabs_bloqueadas:
        for precio in precios_validos:
            precio.setdefault("fuente", "sheet")
        claves_sheet: set = {(p["ticker"], p["fecha"]) for p in precios_validos}
        manual_por_clave: dict = {(p["ticker"], p["fecha"]): float(p["precio"]) for p in precios_validos}

        # Precedencia por (ticker, fecha): iol > sheet > api. Se calcula ANTES de tocar la DB —
        # `fetch_precios_api`/`fetch_backfill_*` sólo necesitan el Sheet en memoria (igual que
        # antes) — para saber qué claves va a reclamar IOL y así no insertar la fila 'sheet' que
        # esa (ticker, fecha) va a perder.
        filas_iol: list[dict] = []
        filas_api: list[dict] = []
        if usa_apis:
            # `estado_por_ticker` lo mutan in place las cinco rutas (las cuatro de cartera y la de
            # watchlist); se persiste una sola vez, más abajo.

            # Precio del día: IOL primero (paneles, una llamada trae docenas de símbolos),
            # data912 como red de contención para lo que IOL no cotizó. Sin `claves_excluir`
            # (set()): IOL puede reclamar una fecha que el Sheet ya cubre —es la fuente primaria—,
            # la precedencia final se resuelve más abajo al escribir en la DB.
            precios_auto, issues_precios_auto = market_data_precios.fetch_precios_api(
                instrumentos_validos, precios_validos, set(), db,
                estado_por_ticker=estado_por_ticker, paneles_fn=paneles_fn, fci_fn=fci_fn,
            )
            issues.extend(issues_precios_auto)
            for p in precios_auto:
                (filas_iol if p["fuente"] == "iol" else filas_api).append(p)

            # Backfill histórico hacia atrás. Ninguno de los dos pisa fechas que el Sheet ya trae
            # (son para llenar huecos, no para reemplazar una carga manual pasada) — a diferencia
            # del precio del día, que sí puede desplazar al Sheet.
            primeras_fechas_mov: dict = {}
            for mov in movimientos_validos:
                t, f = mov["ticker"], mov["fecha"]
                if t not in primeras_fechas_mov or f < primeras_fechas_mov[t]:
                    primeras_fechas_mov[t] = f

            def _min_por_ticker(fuente: str) -> dict:
                out: dict = {}
                for t, f in db.query(PrecioInstrumento.ticker, PrecioInstrumento.fecha).filter(
                    PrecioInstrumento.fuente == fuente
                ):
                    if t not in out or f < out[t]:
                        out[t] = f
                return out

            # analisistecnico (renta fija soberana/letras, no ONs) — se auto-limita: sólo pide la
            # serie de tickers cuyas filas 'api' todavía no llegan al piso.
            backfill_api, issues_backfill_api = market_data_precios.fetch_backfill_renta_fija_api(
                instrumentos_validos, precios_validos, claves_sheet,
                primeras_fechas_mov, _min_por_ticker("api"), estado_por_ticker=estado_por_ticker,
            )
            issues.extend(issues_backfill_api)
            filas_api.extend(backfill_api)

            # IOL para lo que analisistecnico no cubre: ONs (backfill_estado 'sin_serie'/
            # 'sin_serie_iol') y renta variable (sin ninguna otra fuente de historia).
            backfill_iol, issues_backfill_iol = market_data_precios.fetch_backfill_iol(
                instrumentos_validos, precios_validos, claves_sheet,
                primeras_fechas_mov, _min_por_ticker("iol"), db, estado_por_ticker=estado_por_ticker,
            )
            issues.extend(issues_backfill_iol)
            filas_iol.extend(backfill_iol)

        claves_iol: set = {(p["ticker"], p["fecha"]) for p in filas_iol}

        # Válvula de seguridad: un precio manual del Sheet que IOL desplaza nunca es silencioso.
        for ticker, fecha in claves_iol & claves_sheet:
            px_manual = manual_por_clave[(ticker, fecha)]
            px_iol = next(p["precio"] for p in filas_iol if (p["ticker"], p["fecha"]) == (ticker, fecha))
            delta_pct = abs(px_iol - px_manual) / px_manual * 100 if px_manual else 0.0
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="precio_manual_reemplazado_por_iol",
                mensaje=(f"{ticker} ({fecha}): IOL reemplaza el precio manual del Sheet "
                         f"({px_manual:g} -> {px_iol:g}, {delta_pct:.1f}% de diferencia)"),
                impacto="Se usa el precio de IOL; revisar si el ticker o la escala están bien mapeados",
                severidad=Severity.ADVERTENCIA if delta_pct > 20 else Severity.INFO,
            ))

        # El Sheet se reescribe entero en cada sync, salvo las claves que IOL reclama esta corrida
        # (para esas, sólo queda la fila 'iol' — es la fuente primaria). Las filas 'iol'/'api' se
        # manejan aparte por (ticker, fecha) para no perder la serie que acumulan.
        db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "sheet").delete()
        db.flush()

        # A4: una fila 'iol'/'api' guardada para (ticker, fecha) que el Sheet está por (re)cubrir
        # no puede convivir con la fila 'sheet' que se inserta a continuación (chocan contra el
        # UNIQUE (fecha, ticker)) — hay que borrarla ANTES de insertar, no después. Corre siempre,
        # no sólo si alguna API respondió, así que de paso limpia filas ya duplicadas en la DB.
        claves_a_liberar = list(claves_sheet - claves_iol)
        for i in range(0, len(claves_a_liberar), 400):
            lote = claves_a_liberar[i:i + 400]
            db.query(PrecioInstrumento).filter(
                PrecioInstrumento.fuente.in_(("iol", "api")),
                tuple_(PrecioInstrumento.ticker, PrecioInstrumento.fecha).in_(lote),
            ).delete(synchronize_session=False)
        db.flush()

        for precio in precios_validos:
            if (precio["ticker"], precio["fecha"]) in claves_iol:
                continue
            db.add(PrecioInstrumento(**precio))
        db.flush()

        if usa_apis:
            # Purga las filas 'iol'/'api' de tickers que ya no son renta fija/variable/FCI del
            # Sheet (p.ej. un bono que venció y se sacó de Instrumentos): quedarían huérfanas.
            # Sólo si hay al menos un ticker automático: con el conjunto vacío (la pestaña
            # Instrumentos bloqueada por un error de lectura, p.ej.) el DELETE no llevaría filtro
            # de ticker y se llevaría puesta TODA la serie automática acumulada.
            tickers_auto = {
                i["ticker"] for i in instrumentos_validos
                if market_data_precios._es_renta_fija(i.get("tipo_instrumento", ""))
                or market_data_precios._es_renta_variable(i.get("tipo_instrumento", ""))
                or market_data_precios._es_fci(i.get("tipo_instrumento", ""))
            }
            if tickers_auto:
                db.query(PrecioInstrumento).filter(
                    PrecioInstrumento.fuente.in_(("iol", "api")),
                    PrecioInstrumento.ticker.notin_(tickers_auto),
                ).delete(synchronize_session=False)
                db.flush()

            # 'api' nunca pisa una fecha que el Sheet cubre ni una que IOL reclamó (precedencia
            # iol > sheet > api): se descartan acá, no en el fetch, para no tener que duplicar
            # `claves_excluir` contra tres precedencias distintas dentro de `fetch_precios_api`.
            filas_api = [
                p for p in filas_api
                if (p["ticker"], p["fecha"]) not in claves_sheet
                and (p["ticker"], p["fecha"]) not in claves_iol
            ]

            existentes = {
                (r.ticker, r.fecha): r
                for r in db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente.in_(("iol", "api"))).all()
            }
            for p in filas_iol + filas_api:
                fila = existentes.get((p["ticker"], p["fecha"]))
                if fila is not None:
                    fila.precio, fila.moneda, fila.fuente = p["precio"], p["moneda"], p["fuente"]
                else:
                    nueva = PrecioInstrumento(**p)
                    existentes[(p["ticker"], p["fecha"])] = nueva
                    db.add(nueva)
            db.flush()

            precios_api_count = db.query(PrecioInstrumento).filter(
                PrecioInstrumento.fuente.in_(("iol", "api"))
            ).count()

    # Precios de la watchlist. Mismo motor que los de cartera, pero contra `precios_watchlist`:
    # esos tickers no están en `instrumentos_inversion` y no deben entrar en la serie que leen
    # patrimonio/exposición/riesgo (ver la docstring de `PrecioWatchlist`).
    if usa_apis and watchlist_validos:
        # Los que también están en cartera ya los resolvió el pipeline de arriba, con serie
        # histórica completa: `watchlist_analytics` lee de ahí para ellos.
        tickers_en_cartera = {i["ticker"] for i in instrumentos_validos}
        wl_a_cotizar = [w for w in watchlist_validos if w["ticker"] not in tickers_en_cartera]
        filas_wl, issues_wl_api = market_data_precios.fetch_precios_watchlist(
            wl_a_cotizar, precios_validos, db,
            estado_por_ticker=estado_por_ticker, paneles_fn=paneles_fn, fci_fn=fci_fn,
        )
        issues.extend(issues_wl_api)
        for fila in filas_wl:
            existente = db.get(PrecioWatchlist, fila["ticker"])
            if existente is None:
                db.add(PrecioWatchlist(**fila))
            else:
                existente.fecha = fila["fecha"]
                existente.precio = fila["precio"]
                existente.moneda = fila["moneda"]
                existente.fuente = fila["fuente"]
        db.flush()

    # Precios huérfanos de tickers que salieron de la watchlist. Sólo con la pestaña sin bloquear:
    # bloqueada, `watchlist_validos` está vacía y el DELETE se llevaría todo.
    if "Watchlist" not in tabs_bloqueadas:
        tickers_wl = {w["ticker"] for w in watchlist_validos}
        query_huerfanos = db.query(PrecioWatchlist)
        if tickers_wl:
            query_huerfanos = query_huerfanos.filter(PrecioWatchlist.ticker.notin_(tickers_wl))
        query_huerfanos.delete(synchronize_session=False)
        db.flush()

    # A1/A3: persistir el factor de escala calibrado y el estado de backfill por ticker, una vez
    # que pasaron por acá todas las rutas que lo mutan.
    if usa_apis:
        for tk, est in estado_por_ticker.items():
            fila_est = db.get(EstadoMarketDataTicker, tk)
            if fila_est is None:
                fila_est = EstadoMarketDataTicker(ticker=tk)
                db.add(fila_est)
            fila_est.factor_escala = est.get("factor_escala")
            fila_est.factor_fecha = est.get("factor_fecha")
            fila_est.backfill_estado = est.get("backfill_estado")
            fila_est.backfill_intento = est.get("backfill_intento")
        db.flush()

    indices_mercado_api_count = 0
    if not fuentes_cer_mep_bloqueadas:
        # El Sheet se recalcula por completo en cada sync; las filas de la API (si las hay,
        # ver más abajo) se preservan aparte para no perderlas por una falla de red transitoria.
        db.query(IndiceMercado).filter(IndiceMercado.fuente == "sheet").delete()
        db.flush()
        fechas_sheet = {indice["fecha"] for indice in indices_mercado}

        # Una fila 'api' guardada para una fecha que el Sheet ahora sí cubre no puede convivir con
        # la fila 'sheet' que se inserta a continuación (IndiceMercado.fecha es unique) — hay que
        # borrarla ANTES de insertar. Su riesgo país se conserva mergeándolo en la fila del Sheet
        # (mismo criterio que A5 más abajo: el Sheet nunca aporta riesgo país), así no se pierde si
        # la API no responde en esta corrida.
        riesgo_pais_api = {}
        for fila_api in db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").all():
            if fila_api.fecha not in fechas_sheet:
                continue
            if fila_api.riesgo_pais is not None:
                riesgo_pais_api[fila_api.fecha] = fila_api.riesgo_pais
            db.delete(fila_api)
        db.flush()

        for indice in indices_mercado:
            indice.setdefault("fuente", "sheet")
            if indice.get("riesgo_pais") is None and indice["fecha"] in riesgo_pais_api:
                indice["riesgo_pais"] = riesgo_pais_api[indice["fecha"]]
            db.add(IndiceMercado(**indice))
        db.flush()

        if market_data.use_external_apis():
            api_indices, issues_api = market_data_indices.fetch_indices_mercado_api(fechas_sheet)
            issues.extend(issues_api)
            if api_indices is not None:
                db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").delete()
                db.flush()
                sheet_por_fecha = {
                    r.fecha: r
                    for r in db.query(IndiceMercado).filter(IndiceMercado.fuente == "sheet").all()
                }
                n_api = 0
                for indice in api_indices:
                    fila_sheet = sheet_por_fecha.get(indice["fecha"])
                    if fila_sheet is not None:
                        # A5: "el Sheet gana" es por campo, no por fila. El Sheet nunca aporta
                        # riesgo país y IndiceMercado.fecha es unique → el riesgo país de la API
                        # se mergea sobre la fila 'sheet' de esa fecha (CER/MEP del Sheet
                        # intactos). La fila sigue siendo fuente='sheet': el campo es de la API
                        # por construcción, ya documentado así en el modelo.
                        if indice.get("riesgo_pais") is not None:
                            fila_sheet.riesgo_pais = indice["riesgo_pais"]
                    else:
                        db.add(IndiceMercado(**indice))
                        n_api += 1
                db.flush()
                indices_mercado_api_count = n_api
            else:
                indices_mercado_api_count = db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").count()

        # Con las dos fuentes ya persistidas, la serie de CER queda en una sola base: se descarta
        # lo que venga en otra (ver reglas_cer). Va al final a propósito — es el único punto donde
        # se ve la serie completa, Sheet y API juntas, que es como la leen los analytics.
        issues.extend(_sanear_serie_cer(db))

    if "Objetivos" not in tabs_bloqueadas:
        db.query(ObjetivoInversion).delete()
        db.flush()
        for objetivo in objetivos_validos:
            db.add(ObjetivoInversion(**objetivo))

    if "Rebalanceo" not in tabs_bloqueadas:
        db.query(RebalanceoObjetivo).delete()
        db.flush()
        for rebalanceo in rebalanceo_validos:
            db.add(RebalanceoObjetivo(**rebalanceo))

    benchmarks_api_count = 0
    if "Benchmarks" not in tabs_bloqueadas:
        db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "sheet").delete()
        db.flush()

        # Mismo caso que en índices: las filas 'api' preservadas de corridas anteriores chocan
        # contra UNIQUE (fecha, benchmark) si el Sheet pasa a cubrir esa clave. El Sheet gana.
        claves_sheet_bench = {(b["fecha"], b["benchmark"]) for b in benchmarks_validos}
        for fila_api in db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "api").all():
            if (fila_api.fecha, fila_api.benchmark) in claves_sheet_bench:
                db.delete(fila_api)
        db.flush()

        for benchmark in benchmarks_validos:
            benchmark.setdefault("fuente", "sheet")
            db.add(BenchmarkValor(**benchmark))
        db.flush()

        if market_data.use_external_apis():
            api_benchmarks, issues_api_bench = market_data_indices.fetch_benchmarks_api()
            issues.extend(issues_api_bench)
            if api_benchmarks is not None:
                db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "api").delete()
                db.flush()
                # 'api' nunca pisa una clave que el Sheet cubre (precedencia sheet > api).
                api_benchmarks = [
                    b for b in api_benchmarks
                    if (b["fecha"], b["benchmark"]) not in claves_sheet_bench
                ]
                for benchmark in api_benchmarks:
                    db.add(BenchmarkValor(**benchmark))
                benchmarks_api_count = len(api_benchmarks)
            else:
                benchmarks_api_count = db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "api").count()

    if "Configuracion" not in tabs_bloqueadas:
        db.query(ConfiguracionCartera).delete()
        db.flush()
        for configuracion in configuracion_validos:
            db.add(ConfiguracionCartera(**configuracion))

    if "Watchlist" not in tabs_bloqueadas:
        db.query(WatchlistItem).delete()
        db.flush()
        for item in watchlist_validos:
            db.add(WatchlistItem(**item))
        db.flush()

    # Calcular health score
    score_result = calcular_health_score(issues)
    duracion_ms = int((time.monotonic() - inicio) * 1000)

    # Persistir SyncRun + SyncIssue
    sync_run = SyncRun(
        timestamp=timestamp,
        duration_ms=duracion_ms,
        filas_procesadas=sum(len(raw_data.get(t, {}).rows if hasattr(raw_data.get(t), 'rows') else []) for t in ["Instrumentos", "Movimientos", "Precios", "Objetivos", "Rebalanceo", "Benchmarks", "Configuracion"]),
        filas_validas=len(instrumentos_validos) + len(movimientos_validos) + len(precios_validos) + len(objetivos_validos) + len(rebalanceo_validos) + len(benchmarks_validos) + len(configuracion_validos),
        filas_advertencia=sum(1 for i in issues if i.severidad == Severity.ADVERTENCIA),
        filas_error=sum(1 for i in issues if i.severidad == Severity.CRITICO),
        health_score=score_result["score"],
        resultado=score_result["resultado"],
    )
    db.add(sync_run)
    db.flush()

    for issue in issues:
        db.add(SyncIssue(
            sync_run_id=sync_run.id,
            tab=issue.tab,
            fila=issue.fila,
            campo=issue.campo,
            regla=issue.regla,
            severidad=issue.severidad.value,
            mensaje=issue.mensaje,
            impacto=issue.impacto,
        ))

    _prune_sync_runs(db, keep=20)
    db.commit()

    logger.info(
        f"Sync completed: {score_result['resultado']}, score={score_result['score']}, "
        f"criticals={score_result['n_criticos']}, warnings={score_result['n_advertencias']}, "
        f"duration={duracion_ms}ms"
    )

    return {
        "movimientos": len(movimientos_validos),
        "instrumentos": len(instrumentos_validos),
        "precios": len(precios_validos) + precios_api_count,
        "objetivos": len(objetivos_validos),
        "rebalanceo": len(rebalanceo_validos),
        "indices_mercado": 0 if fuentes_cer_mep_bloqueadas else len(indices_mercado) + indices_mercado_api_count,
        "benchmarks": len(benchmarks_validos) + benchmarks_api_count,
        "configuracion": len(configuracion_validos),
        "health_score": score_result["score"],
        "resultado": score_result["resultado"],
        "duration_ms": duracion_ms,
        "timestamp": timestamp,
        "issues": [issue.to_dict() for issue in issues],
    }


def _consolidar_indices_mercado(cer_mep_movimientos: list[dict], cer_mep_precios: list[dict]) -> tuple[list[dict], list[ValidationIssue]]:
    """Consolida CER/MEP de Movimientos y Precios por fecha, resolviendo conflictos."""
    indices_por_fecha: dict = {}
    advertencias: list[ValidationIssue] = []

    for item in cer_mep_movimientos + cer_mep_precios:
        fecha = item["fecha"]
        cer = item.get("cer")
        mep = item.get("mep")

        if fecha not in indices_por_fecha:
            indices_por_fecha[fecha] = {"fecha": fecha, "cer": cer, "mep": mep}
        else:
            existente = indices_por_fecha[fecha]
            if cer is not None and existente["cer"] is not None and abs(cer - existente["cer"]) > 1e-6:
                advertencias.append(ValidationIssue(
                    tab="CER/MEP", regla="cer_inconsistente",
                    mensaje=f"CER inconsistente para {fecha.isoformat()}",
                    impacto="Se usó el último valor cargado",
                    severidad=Severity.ADVERTENCIA
                ))
            if cer is not None:
                existente["cer"] = cer

            if mep is not None and existente["mep"] is not None and abs(mep - existente["mep"]) > 1e-6:
                advertencias.append(ValidationIssue(
                    tab="CER/MEP", regla="mep_inconsistente",
                    mensaje=f"MEP inconsistente para {fecha.isoformat()}",
                    impacto="Se usó el último valor cargado",
                    severidad=Severity.ADVERTENCIA
                ))
            if mep is not None:
                existente["mep"] = mep

    return list(indices_por_fecha.values()), advertencias


def _sanear_serie_cer(db: Session) -> list[ValidationIssue]:
    """Anula los CER persistidos que no pertenecen a la base del resto de la serie.

    Se anula sólo el campo `cer`: el MEP y el riesgo país de esa fecha son independientes y
    siguen siendo válidos. Al quedar en NULL, el lookup de `_cer_indice` (que filtra por
    `cer IS NOT NULL` y toma la última fecha ≤ la buscada) arrastra el último valor bueno.
    """
    filas = (
        db.query(IndiceMercado)
        .filter(IndiceMercado.cer.isnot(None))
        .order_by(IndiceMercado.fecha)
        .all()
    )
    descartadas, issues = reglas_cer.detectar_cer_fuera_de_serie(
        [(f.fecha, float(f.cer)) for f in filas]
    )
    if not descartadas:
        return issues

    for fila in filas:
        if fila.fecha in descartadas:
            fila.cer = None
    db.flush()
    return issues


def _aplicar_tipos_cambio(indices_existentes: list[dict], tipos_cambio: list[dict]) -> list[dict]:
    """Sobrescribe/completa `indices_existentes` (de Movimientos/Precios) con los valores de la
    pestaña "Tipos de Cambio", que tiene prioridad por ser la fuente dedicada."""
    por_fecha = {row["fecha"]: dict(row) for row in indices_existentes}
    for item in tipos_cambio:
        fecha = item["fecha"]
        if fecha not in por_fecha:
            por_fecha[fecha] = {"fecha": fecha, "cer": None, "mep": None}
        por_fecha[fecha][item["campo"]] = item["valor"]
    return list(por_fecha.values())
