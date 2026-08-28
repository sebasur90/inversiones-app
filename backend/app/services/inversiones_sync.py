"""Orquestación del sync desde Google Sheets con validación de calidad."""
import time
import logging
from datetime import datetime, UTC
from sqlalchemy.orm import Session

from ..database import (
    InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado,
    ObjetivoInversion, RebalanceoObjetivo, BenchmarkValor, ConfiguracionCartera,
    SyncRun, SyncIssue
)
from .sheets_client import fetch_sheet_data, fetch_objetivos_tab, fetch_rebalanceo_tab, fetch_benchmarks_tab, fetch_configuracion_tab
from .inversiones_analytics import get_carteras
from .validation.types import ValidationIssue, Severity
from .validation.reglas_estructura import validar_estructura_tab
from .validation import reglas_instrumentos, reglas_movimientos, reglas_precios, reglas_objetivos, reglas_rebalanceo, reglas_benchmarks, reglas_configuracion, reglas_tipos_cambio
from .validation.health_score import calcular_health_score
from . import market_data
from .market_data import indices as market_data_indices

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

    if "Precios" not in tabs_bloqueadas:
        db.query(PrecioInstrumento).delete()
        db.flush()
        for precio in precios_validos:
            db.add(PrecioInstrumento(**precio))

    indices_mercado_api_count = 0
    if not fuentes_cer_mep_bloqueadas:
        # El Sheet se recalcula por completo en cada sync; las filas de la API (si las hay,
        # ver más abajo) se preservan aparte para no perderlas por una falla de red transitoria.
        db.query(IndiceMercado).filter(IndiceMercado.fuente == "sheet").delete()
        db.flush()
        fechas_sheet = set()
        for indice in indices_mercado:
            indice.setdefault("fuente", "sheet")
            fechas_sheet.add(indice["fecha"])
            db.add(IndiceMercado(**indice))

        if market_data.use_external_apis():
            api_indices, issues_api = market_data_indices.fetch_indices_mercado_api(fechas_sheet)
            issues.extend(issues_api)
            if api_indices is not None:
                db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").delete()
                db.flush()
                for indice in api_indices:
                    db.add(IndiceMercado(**indice))
                indices_mercado_api_count = len(api_indices)
            else:
                indices_mercado_api_count = db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").count()

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
        for benchmark in benchmarks_validos:
            benchmark.setdefault("fuente", "sheet")
            db.add(BenchmarkValor(**benchmark))

        if market_data.use_external_apis():
            api_benchmarks, issues_api_bench = market_data_indices.fetch_benchmarks_api()
            issues.extend(issues_api_bench)
            if api_benchmarks is not None:
                db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "api").delete()
                db.flush()
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
        "precios": len(precios_validos),
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
