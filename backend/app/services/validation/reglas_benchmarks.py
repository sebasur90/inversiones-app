"""Validación de la pestaña Benchmarks."""
from datetime import date
from .types import ValidationIssue, Severity
from .parsers import _parse_fecha, _parse_numero


def validar_benchmarks(rows: list[tuple[int, dict]]) -> tuple[list[dict], list[ValidationIssue]]:
    """Valida filas de Benchmarks. Devuelve (validos, issues)."""
    validos = []
    vistos: set[tuple[date, str]] = set()
    issues = []

    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            issues.append(ValidationIssue(
                tab="Benchmarks", fila=row_num, campo="Fecha", regla="fecha_invalida",
                mensaje=f"Fecha inválida: {fecha_raw}",
                impacto="No se puede procesar este benchmark",
                severidad=Severity.CRITICO
            ))
            continue

        benchmark = (row.get("Benchmark") or "").strip()
        if not benchmark:
            issues.append(ValidationIssue(
                tab="Benchmarks", fila=row_num, campo="Benchmark", regla="benchmark_vacio",
                mensaje="Benchmark vacío",
                impacto="No se puede procesar este benchmark",
                severidad=Severity.CRITICO
            ))
            continue

        valor_raw = (row.get("Valor") or "").strip()
        valor = _parse_numero(valor_raw)
        if valor is None:
            issues.append(ValidationIssue(
                tab="Benchmarks", fila=row_num, campo="Valor", regla="valor_invalido",
                mensaje=f"Valor inválido: {valor_raw}",
                impacto="No se puede procesar este benchmark",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Valor <= 0 → crítico
        if valor <= 0:
            issues.append(ValidationIssue(
                tab="Benchmarks", fila=row_num, campo="Valor", regla="valor_no_positivo",
                mensaje=f"Valor no positivo: {valor}",
                impacto="No se puede procesar este benchmark",
                severidad=Severity.CRITICO
            ))
            continue

        # Duplicado fecha+benchmark → advertencia/drop (antes crítico)
        key = (fecha, benchmark)
        if key in vistos:
            issues.append(ValidationIssue(
                tab="Benchmarks", fila=row_num, regla="valor_duplicado",
                mensaje=f"Valor duplicado para {benchmark} en {fecha.isoformat()}",
                impacto="Se descarta este duplicado",
                severidad=Severity.ADVERTENCIA
            ))
            continue
        vistos.add(key)

        validos.append({"fecha": fecha, "benchmark": benchmark, "valor": valor})

    return validos, issues
