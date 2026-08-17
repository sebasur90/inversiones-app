"""Validación de la pestaña Movimientos."""
from .types import ValidationIssue, Severity
from .parsers import _parse_fecha, _parse_numero, _normalize_tipo_movimiento, MONEDAS_VALIDAS, TIPOS_MOVIMIENTO


def validar_movimientos(
    rows: list[tuple[int, dict]],
    tickers_conocidos: set[str],
) -> tuple[list[dict], list[dict], list[ValidationIssue]]:
    """Valida filas de Movimientos. Devuelve (validos, cer_mep_datos, issues)."""
    parsed = []
    cer_mep_datos = []
    issues = []

    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Fecha", regla="fecha_invalida",
                mensaje=f"Fecha inválida: {fecha_raw}",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        cartera = (row.get("Cartera") or "").strip()
        if not cartera:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Cartera", regla="cartera_vacia",
                mensaje="Cartera vacía",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Ticker", regla="ticker_vacio",
                mensaje="Ticker vacío",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        tipo_raw = (row.get("Tipo Movimiento") or "").strip()
        tipo = _normalize_tipo_movimiento(tipo_raw)
        if tipo is None:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Tipo Movimiento", regla="tipo_movimiento_invalido",
                mensaje=f"Tipo Movimiento inválido: {tipo_raw}",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        cantidad_raw = (row.get("Cantidad") or "").strip()
        cantidad = None
        if cantidad_raw:
            cantidad = _parse_numero(cantidad_raw)
            if cantidad is None:
                issues.append(ValidationIssue(
                    tab="Movimientos", fila=row_num, campo="Cantidad", regla="cantidad_invalida",
                    mensaje=f"Cantidad inválida: {cantidad_raw}",
                    impacto="No se puede procesar este movimiento",
                    severidad=Severity.CRITICO
                ))
                continue
        elif tipo in ("compra", "venta", "amortizacion"):
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Cantidad", regla="cantidad_requerida",
                mensaje=f"Cantidad requerida para {tipo}",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        precio_raw = (row.get("Precio") or "").strip()
        precio = _parse_numero(precio_raw)
        if precio is None:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Precio", regla="precio_invalido",
                mensaje=f"Precio inválido: {precio_raw}",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Precio negativo → crítico
        if precio < 0:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Precio", regla="precio_negativo",
                mensaje=f"Precio negativo: {precio}",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Precio == 0 → advertencia/keep
        if precio == 0:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Precio", regla="precio_cero",
                mensaje="Precio es cero",
                impacto="Se registra con precio 0 (revisar si es intencional)",
                severidad=Severity.ADVERTENCIA
            ))

        moneda = (row.get("Moneda") or "").strip().upper()
        if moneda not in MONEDAS_VALIDAS:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Moneda", regla="moneda_invalida",
                mensaje=f"Moneda inválida: {moneda}",
                impacto="No se puede procesar este movimiento",
                severidad=Severity.CRITICO
            ))
            continue

        comision_raw = (row.get("Comisión") or row.get("Comision") or "").strip()
        comision = 0.0
        if comision_raw:
            parsed_comision = _parse_numero(comision_raw)
            if parsed_comision is None:
                issues.append(ValidationIssue(
                    tab="Movimientos", fila=row_num, campo="Comisión", regla="comision_invalida",
                    mensaje=f"Comisión inválida: {comision_raw}",
                    impacto="No se puede procesar este movimiento",
                    severidad=Severity.CRITICO
                ))
                continue
            # NUEVO: Comisión negativa → crítico
            if parsed_comision < 0:
                issues.append(ValidationIssue(
                    tab="Movimientos", fila=row_num, campo="Comisión", regla="comision_negativa",
                    mensaje=f"Comisión negativa: {parsed_comision}",
                    impacto="No se puede procesar este movimiento",
                    severidad=Severity.CRITICO
                ))
                continue
            comision = parsed_comision

        # NUEVO: Detectar duplicados potenciales (misma fecha+cartera+ticker+tipo+cantidad+precio)
        # Solo advertencia, se guardan ambos
        # (esto se detectaría en un segundo pass, por ahora solo registramos el movimiento)

        # CER/MEP opcionales
        cer_raw = (row.get("CER") or "").strip()
        cer = None
        if cer_raw:
            cer = _parse_numero(cer_raw, es_indice=True)

        mep_raw = (row.get("MEP") or "").strip()
        mep = None
        if mep_raw:
            mep = _parse_numero(mep_raw, es_indice=True)

        if cer or mep:
            cer_mep_datos.append({"fecha": fecha, "cer": cer, "mep": mep})

        # Advertencia si ticker desconocido (sin cambios)
        if ticker not in tickers_conocidos:
            issues.append(ValidationIssue(
                tab="Movimientos", fila=row_num, campo="Ticker", regla="ticker_desconocido",
                mensaje=f"Ticker '{ticker}' sin ficha en Instrumentos",
                impacto="Se registra igual pero queda sin clasificar",
                severidad=Severity.ADVERTENCIA
            ))

        parsed.append({
            "row_num": row_num,
            "fecha": fecha,
            "cartera": cartera,
            "ticker": ticker,
            "tipo_movimiento": tipo,
            "cantidad": cantidad,
            "precio": precio,
            "moneda": moneda,
            "comision": comision,
        })

    # Validar tenencia no negativa procesando en orden cronológico por (cartera, ticker)
    parsed.sort(key=lambda m: (m["fecha"], m["row_num"]))
    tenencias: dict[tuple[str, str], float] = {}
    validos = []
    for mov in parsed:
        key = (mov["cartera"], mov["ticker"])
        actual = tenencias.get(key, 0.0)
        if mov["tipo_movimiento"] == "compra":
            actual += mov["cantidad"] or 0.0
        elif mov["tipo_movimiento"] in ("venta", "amortizacion"):
            cant = mov["cantidad"] or 0.0
            if cant - actual > 1e-6:
                issues.append(ValidationIssue(
                    tab="Movimientos", fila=mov["row_num"], regla="tenencia_insuficiente",
                    mensaje=(
                        f"Tenencia insuficiente para {mov['tipo_movimiento']} de {mov['ticker']} "
                        f"en '{mov['cartera']}' ({cant} > {actual})"
                    ),
                    impacto="No se puede procesar este movimiento",
                    severidad=Severity.CRITICO
                ))
                continue
            actual -= cant
        tenencias[key] = actual
        validos.append(mov)

    return validos, cer_mep_datos, issues
