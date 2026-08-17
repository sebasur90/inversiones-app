"""Validación de la pestaña Precios."""
from datetime import date
from .types import ValidationIssue, Severity
from .parsers import _parse_fecha, _parse_numero, MONEDAS_VALIDAS


def validar_precios(rows: list[tuple[int, dict]]) -> tuple[list[dict], list[dict], list[ValidationIssue]]:
    """Valida filas de Precios. Devuelve (validos, cer_mep_datos, issues)."""
    validos = []
    vistos: set[tuple[date, str]] = set()
    cer_mep_datos = []
    issues = []

    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            issues.append(ValidationIssue(
                tab="Precios", fila=row_num, campo="Fecha", regla="fecha_invalida",
                mensaje=f"Fecha inválida: {fecha_raw}",
                impacto="No se puede procesar este precio",
                severidad=Severity.CRITICO
            ))
            continue

        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            issues.append(ValidationIssue(
                tab="Precios", fila=row_num, campo="Ticker", regla="ticker_vacio",
                mensaje="Ticker vacío",
                impacto="No se puede procesar este precio",
                severidad=Severity.CRITICO
            ))
            continue

        precio_raw = (row.get("Precio") or "").strip()
        precio = _parse_numero(precio_raw)
        if precio is None:
            issues.append(ValidationIssue(
                tab="Precios", fila=row_num, campo="Precio", regla="precio_invalido",
                mensaje=f"Precio inválido: {precio_raw}",
                impacto="No se puede procesar este precio",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Precio <= 0 → crítico
        if precio <= 0:
            issues.append(ValidationIssue(
                tab="Precios", fila=row_num, campo="Precio", regla="precio_no_positivo",
                mensaje=f"Precio no positivo: {precio}",
                impacto="No se puede procesar este precio",
                severidad=Severity.CRITICO
            ))
            continue

        moneda = (row.get("Moneda") or "").strip().upper()
        if moneda not in MONEDAS_VALIDAS:
            issues.append(ValidationIssue(
                tab="Precios", fila=row_num, campo="Moneda", regla="moneda_invalida",
                mensaje=f"Moneda inválida: {moneda}",
                impacto="No se puede procesar este precio",
                severidad=Severity.CRITICO
            ))
            continue

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

        # Duplicado fecha+ticker → advertencia/drop (antes crítico, primero gana)
        key = (fecha, ticker)
        if key in vistos:
            issues.append(ValidationIssue(
                tab="Precios", fila=row_num, regla="precio_duplicado",
                mensaje=f"Precio duplicado para {ticker} en {fecha.isoformat()}",
                impacto="Se descarta este duplicado (se mantiene el primero)",
                severidad=Severity.ADVERTENCIA
            ))
            continue
        vistos.add(key)

        validos.append({"fecha": fecha, "ticker": ticker, "precio": precio, "moneda": moneda})

    return validos, cer_mep_datos, issues


def detectar_huecos(precios_validos: list[dict], umbral_dias: int = 10) -> list[ValidationIssue]:
    """Detecta huecos excesivos entre fechas para cada ticker. NUEVO."""
    issues = []
    por_ticker: dict[str, list[date]] = {}

    for p in precios_validos:
        ticker = p["ticker"]
        if ticker not in por_ticker:
            por_ticker[ticker] = []
        por_ticker[ticker].append(p["fecha"])

    for ticker, fechas in por_ticker.items():
        fechas_sorted = sorted(fechas)
        gaps = []
        for i in range(1, len(fechas_sorted)):
            delta_days = (fechas_sorted[i] - fechas_sorted[i - 1]).days
            if delta_days > umbral_dias:
                gaps.append(f"{fechas_sorted[i-1].isoformat()} → {fechas_sorted[i].isoformat()} ({delta_days} días)")

        if gaps:
            issues.append(ValidationIssue(
                tab="Precios", regla="hueco_excesivo",
                mensaje=f"Ticker {ticker}: {len(gaps)} hueco(s) mayor(es) a {umbral_dias} días",
                impacto="Análisis histórico incompleto para este instrumento",
                severidad=Severity.ADVERTENCIA
            ))

    return issues


def detectar_saltos_extremos(precios_validos: list[dict], umbral_pct: float = 0.50) -> list[ValidationIssue]:
    """Detecta saltos extremos de precio (>50%) entre fechas consecutivas. NUEVO, no bloquea."""
    issues = []
    por_ticker: dict[str, list[dict]] = {}

    for p in precios_validos:
        ticker = p["ticker"]
        if ticker not in por_ticker:
            por_ticker[ticker] = []
        por_ticker[ticker].append(p)

    for ticker, precios_ticker in por_ticker.items():
        precios_sorted = sorted(precios_ticker, key=lambda p: p["fecha"])
        saltos = []
        for i in range(1, len(precios_sorted)):
            precio_prev = precios_sorted[i - 1]["precio"]
            precio_curr = precios_sorted[i]["precio"]
            if precio_prev > 0:
                cambio_pct = abs(precio_curr - precio_prev) / precio_prev
                if cambio_pct > umbral_pct:
                    saltos.append(
                        f"{precios_sorted[i-1]['fecha'].isoformat()}: {precio_prev} → "
                        f"{precio_curr} ({cambio_pct*100:.1f}%)"
                    )

        if saltos:
            issues.append(ValidationIssue(
                tab="Precios", regla="salto_extremo",
                mensaje=f"Ticker {ticker}: {len(saltos)} salto(s) de precio >50%",
                impacto="Revisar si hay split o error de entrada",
                severidad=Severity.ADVERTENCIA
            ))

    return issues
