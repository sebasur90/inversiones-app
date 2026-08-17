"""Validación de la pestaña Instrumentos."""
from .types import ValidationIssue, Severity
from .parsers import _parse_fecha, _parse_numero, _parse_nivel_precio

MONEDAS_VALIDAS = ("ARS", "USD")


def validar_instrumentos(rows: list[tuple[int, dict]]) -> tuple[list[dict], set[str], list[ValidationIssue]]:
    """Valida filas de Instrumentos. Devuelve (validos, tickers_conocidos, issues)."""
    validos = []
    tickers = set()
    issues = []

    for row_num, row in rows:
        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, regla="ticker_vacio",
                mensaje="Ticker vacío", impacto="No se puede registrar el instrumento",
                severidad=Severity.CRITICO
            ))
            continue

        if ticker in tickers:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, regla="ticker_duplicado",
                mensaje=f"Ticker duplicado: {ticker}", impacto="Se descarta este duplicado",
                severidad=Severity.CRITICO
            ))
            continue

        moneda = (row.get("Moneda") or "").strip().upper()
        if moneda not in MONEDAS_VALIDAS:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, campo="Moneda", regla="moneda_invalida",
                mensaje=f"Moneda inválida: {moneda}", impacto="No se puede registrar el instrumento",
                severidad=Severity.CRITICO
            ))
            continue

        # Fecha Vencimiento — antes crítico, ahora advertencia/salvage
        fecha_venc = None
        fecha_venc_raw = (row.get("Fecha Vencimiento") or "").strip()
        if fecha_venc_raw and fecha_venc_raw.lower() != "nan":
            fecha_venc = _parse_fecha(fecha_venc_raw)
            if fecha_venc is None:
                issues.append(ValidationIssue(
                    tab="Instrumentos", fila=row_num, campo="Fecha Vencimiento",
                    regla="fecha_vencimiento_invalida",
                    mensaje=f"Fecha Vencimiento inválida: {fecha_venc_raw}",
                    impacto="Se descarta este campo, el instrumento se guarda sin vencimiento",
                    severidad=Severity.ADVERTENCIA
                ))
                # No continue, salvage el instrumento sin la fecha

        # Objetivo/Stop Loss — antes crítico si ambos lados inválido, ahora advertencia/salvage
        objetivo_modo, objetivo_valor, error_objetivo = _parse_nivel_precio(
            row.get("Objetivo Modo"), row.get("Objetivo Valor")
        )
        if error_objetivo:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, campo="Objetivo Modo/Valor",
                regla="objetivo_invalido",
                mensaje=f"Objetivo inválido: {error_objetivo}",
                impacto="Se descarta este campo, el instrumento se guarda sin objetivo",
                severidad=Severity.ADVERTENCIA
            ))
            objetivo_modo, objetivo_valor = None, None

        stop_loss_modo, stop_loss_valor, error_stop = _parse_nivel_precio(
            row.get("Stop Loss Modo"), row.get("Stop Loss Valor")
        )
        if error_stop:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, campo="Stop Loss Modo/Valor",
                regla="stop_loss_invalido",
                mensaje=f"Stop Loss inválido: {error_stop}",
                impacto="Se descarta este campo, el instrumento se guarda sin stop loss",
                severidad=Severity.ADVERTENCIA
            ))
            stop_loss_modo, stop_loss_valor = None, None

        # Tipo Instrumento vacío — advertencia/salvage
        tipo_inst = (row.get("Tipo Instrumento") or "").strip()
        if not tipo_inst:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, campo="Tipo Instrumento",
                regla="tipo_instrumento_vacio",
                mensaje="Tipo Instrumento vacío",
                impacto="Se registra con tipo vacío",
                severidad=Severity.ADVERTENCIA
            ))

        # Mercado vacío — advertencia/salvage
        mercado = (row.get("Mercado") or "").strip()
        if not mercado:
            issues.append(ValidationIssue(
                tab="Instrumentos", fila=row_num, campo="Mercado",
                regla="mercado_vacio",
                mensaje="Mercado vacío",
                impacto="Se registra con mercado vacío",
                severidad=Severity.ADVERTENCIA
            ))

        # Sector vacío — info/salvage (ya es nullable)
        sector = row.get("Sector") or None

        # Pais vacío — info/salvage
        pais = row.get("País") or row.get("Pais") or None

        validos.append({
            "ticker": ticker,
            "nombre": row.get("Nombre") or ticker,
            "tipo_instrumento": tipo_inst,
            "mercado": mercado,
            "moneda": moneda,
            "pais": pais,
            "sector": sector,
            "fecha_vencimiento": fecha_venc,
            "objetivo_modo": objetivo_modo,
            "objetivo_valor": objetivo_valor,
            "stop_loss_modo": stop_loss_modo,
            "stop_loss_valor": stop_loss_valor,
        })
        tickers.add(ticker)

    return validos, tickers, issues


def detectar_sin_precio(instrumentos_validos: list[dict], precios_validos: list[dict]) -> list[ValidationIssue]:
    """Detecta instrumentos sin precio disponible. Cross-tab, solo si ambas pestañas están presentes."""
    issues = []
    tickers_con_precio = {p["ticker"] for p in precios_validos}
    tickers_sin_precio = [i["ticker"] for i in instrumentos_validos if i["ticker"] not in tickers_con_precio]

    if tickers_sin_precio:
        issues.append(ValidationIssue(
            tab="Instrumentos",
            regla="instrumento_sin_precio",
            mensaje=f"Hay {len(tickers_sin_precio)} instrumento(s) sin precio en la pestaña Precios",
            impacto="No se podrá calcular el valor actual de estas posiciones",
            severidad=Severity.ADVERTENCIA
        ))

    return issues
