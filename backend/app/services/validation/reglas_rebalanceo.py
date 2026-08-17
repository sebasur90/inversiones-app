"""Validación de la pestaña Rebalanceo."""
from .types import ValidationIssue, Severity
from .parsers import _strip_accents, _parse_numero, EJES_REBALANCEO


def validar_rebalanceo(
    rows: list[tuple[int, dict]],
    tickers_conocidos: set[str],
    carteras_conocidas: set[str],
) -> tuple[list[dict], list[ValidationIssue]]:
    """Valida filas de Rebalanceo. Devuelve (validos, issues)."""
    validos = []
    seen: set[tuple[str | None, str, str]] = set()
    sumas: dict[tuple[str | None, str], float] = {}
    issues = []

    for row_num, row in rows:
        cartera_raw = (row.get("Cartera") or "").strip()
        cartera = None if not cartera_raw or _strip_accents(cartera_raw).lower() == "consolidado" else cartera_raw

        eje_raw = (row.get("Eje") or "").strip()
        eje = EJES_REBALANCEO.get(_strip_accents(eje_raw).lower())
        if eje is None:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, campo="Eje", regla="eje_desconocido",
                mensaje=f"Eje desconocido: {eje_raw}",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        if eje == "Cartera" and cartera is not None:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, regla="eje_cartera_conflicto",
                mensaje="El eje 'Cartera' solo aplica a nivel Consolidado",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        categoria = (row.get("Categoría") or row.get("Categoria") or "").strip()
        if not categoria:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, campo="Categoría", regla="categoria_vacia",
                mensaje="Categoría vacía",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        if eje == "Ticker" and categoria not in tickers_conocidos:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, campo="Categoría", regla="ticker_desconocido",
                mensaje=f"Ticker desconocido en Rebalanceo: {categoria}",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Cartera inexistente (eje ≠ Cartera) → advertencia/keep
        if eje != "Cartera" and cartera is not None and cartera not in carteras_conocidas:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, campo="Cartera", regla="cartera_inexistente",
                mensaje=f"Cartera '{cartera}' no aparece en Movimientos",
                impacto="Se registra igual, pero no hay movimientos asociados",
                severidad=Severity.ADVERTENCIA
            ))

        porcentaje_raw = (row.get("Porcentaje Objetivo") or "").strip()
        porcentaje = _parse_numero(porcentaje_raw)
        if porcentaje is None or porcentaje < 0 or porcentaje > 100:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, campo="Porcentaje Objetivo",
                regla="porcentaje_objetivo_invalido",
                mensaje=f"Porcentaje Objetivo inválido: {porcentaje_raw}",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        # Duplicado (cartera, eje, categoría) → advertencia/drop (antes crítico)
        key = (cartera, eje, categoria)
        if key in seen:
            issues.append(ValidationIssue(
                tab="Rebalanceo", fila=row_num, regla="objetivo_rebalanceo_duplicado",
                mensaje=f"Objetivo de rebalanceo duplicado para {cartera or 'Consolidado'} / {eje} / {categoria}",
                impacto="Se descarta este duplicado",
                severidad=Severity.ADVERTENCIA
            ))
            continue
        seen.add(key)

        grupo = (cartera, eje)
        sumas[grupo] = sumas.get(grupo, 0.0) + porcentaje

        validos.append({
            "cartera": cartera,
            "eje": eje,
            "categoria": categoria,
            "porcentaje_objetivo": porcentaje,
        })

    # Suma >100.5% por grupo → advertencia/keep, a nivel de tab
    for (cartera, eje), suma in sumas.items():
        if suma > 100.5:
            issues.append(ValidationIssue(
                tab="Rebalanceo",
                regla="suma_porcentajes_excedida",
                mensaje=f"Objetivos de Rebalanceo para {cartera or 'Consolidado'} / {eje} suman {suma:.1f}% (>100%)",
                impacto="La suma de pesos no será 100%, revisar si es intencional",
                severidad=Severity.ADVERTENCIA
            ))

    return validos, issues
