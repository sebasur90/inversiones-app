"""Validación de la pestaña opcional "Tipos de Cambio" (Fecha, Tipo, Valor).

Formato largo: una fila por (fecha, tipo), con Tipo ∈ {CER, MEP}. Es la fuente dedicada de
CER/MEP — tiene prioridad sobre las columnas CER/MEP embebidas en Movimientos y Precios, que
sólo traen valor en las fechas donde hubo una operación o una carga de precio.
"""
from datetime import date
from .types import ValidationIssue, Severity
from .parsers import _parse_fecha, _parse_numero, _strip_accents

TIPOS_VALIDOS = {"cer": "cer", "mep": "mep"}


def validar_tipos_cambio(rows: list[tuple[int, dict]]) -> tuple[list[dict], list[ValidationIssue]]:
    """Valida filas de Tipos de Cambio. Devuelve (validos, issues).

    `validos`: [{"fecha": date, "campo": "cer"|"mep", "valor": float}]
    """
    validos = []
    vistos: set[tuple[date, str]] = set()
    issues = []

    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            issues.append(ValidationIssue(
                tab="Tipos de Cambio", fila=row_num, campo="Fecha", regla="fecha_invalida",
                mensaje=f"Fecha inválida: {fecha_raw}",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        tipo_raw = (row.get("Tipo") or "").strip()
        campo = TIPOS_VALIDOS.get(_strip_accents(tipo_raw).strip().lower())
        if campo is None:
            issues.append(ValidationIssue(
                tab="Tipos de Cambio", fila=row_num, campo="Tipo", regla="tipo_no_reconocido",
                mensaje=f"Tipo no reconocido: '{tipo_raw}' (se esperaba CER o MEP)",
                impacto="No se puede procesar esta fila",
                severidad=Severity.ADVERTENCIA
            ))
            continue

        valor_raw = (row.get("Valor") or "").strip()
        valor = _parse_numero(valor_raw, es_indice=True)
        if valor is None:
            issues.append(ValidationIssue(
                tab="Tipos de Cambio", fila=row_num, campo="Valor", regla="valor_invalido",
                mensaje=f"Valor inválido: {valor_raw}",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        if valor <= 0:
            issues.append(ValidationIssue(
                tab="Tipos de Cambio", fila=row_num, campo="Valor", regla="valor_no_positivo",
                mensaje=f"Valor no positivo: {valor}",
                impacto="No se puede procesar esta fila",
                severidad=Severity.CRITICO
            ))
            continue

        key = (fecha, campo)
        if key in vistos:
            issues.append(ValidationIssue(
                tab="Tipos de Cambio", fila=row_num, regla="valor_duplicado",
                mensaje=f"Valor duplicado de {campo.upper()} para {fecha.isoformat()}",
                impacto="Se descarta este duplicado",
                severidad=Severity.ADVERTENCIA
            ))
            continue
        vistos.add(key)

        validos.append({"fecha": fecha, "campo": campo, "valor": valor})

    return validos, issues
