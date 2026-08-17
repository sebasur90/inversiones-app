"""Validación de la pestaña Objetivos."""
from datetime import date
from .types import ValidationIssue, Severity
from .parsers import _parse_fecha, _parse_numero


def validar_objetivos(
    rows: list[tuple[int, dict]],
    carteras_conocidas: set[str],
) -> tuple[list[dict], list[ValidationIssue]]:
    """Valida filas de Objetivos. Devuelve (validos, issues)."""
    validos = []
    carteras_vistas: set[str] = set()
    issues = []

    for row_num, row in rows:
        cartera = (row.get("Cartera") or "").strip()
        if not cartera:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Cartera", regla="cartera_vacia",
                mensaje="Cartera vacía",
                impacto="No se puede registrar este objetivo",
                severidad=Severity.CRITICO
            ))
            continue

        # Duplicado por cartera → advertencia/drop (antes crítico)
        if cartera in carteras_vistas:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, regla="objetivo_duplicado",
                mensaje=f"Objetivo duplicado para cartera: {cartera}",
                impacto="Se descarta este duplicado",
                severidad=Severity.ADVERTENCIA
            ))
            continue

        nombre = (row.get("Nombre") or "").strip()
        if not nombre:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Nombre", regla="nombre_vacio",
                mensaje="Nombre vacío",
                impacto="No se puede registrar este objetivo",
                severidad=Severity.CRITICO
            ))
            continue

        fecha_raw = (row.get("Fecha Límite") or row.get("Fecha Limite") or "").strip()
        fecha_limite = _parse_fecha(fecha_raw)
        if fecha_limite is None:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Fecha Límite", regla="fecha_limite_invalida",
                mensaje=f"Fecha Límite inválida: {fecha_raw}",
                impacto="No se puede registrar este objetivo",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Fecha Límite en el pasado → advertencia/keep
        if fecha_limite < date.today():
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Fecha Límite", regla="fecha_limite_pasado",
                mensaje=f"Fecha Límite en el pasado: {fecha_limite.isoformat()}",
                impacto="Se registra igual, pero el objetivo ya venció",
                severidad=Severity.ADVERTENCIA
            ))

        monto_raw = (row.get("Monto USD") or "").strip()
        monto_usd = _parse_numero(monto_raw)
        if monto_usd is None:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Monto USD", regla="monto_usd_invalido",
                mensaje=f"Monto USD inválido: {monto_raw}",
                impacto="No se puede registrar este objetivo",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Monto USD <= 0 → crítico
        if monto_usd <= 0:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Monto USD", regla="monto_usd_no_positivo",
                mensaje=f"Monto USD no positivo: {monto_usd}",
                impacto="No se puede registrar este objetivo",
                severidad=Severity.CRITICO
            ))
            continue

        # NUEVO: Cartera inexistente → advertencia/keep
        if cartera not in carteras_conocidas:
            issues.append(ValidationIssue(
                tab="Objetivos", fila=row_num, campo="Cartera", regla="cartera_inexistente",
                mensaje=f"Cartera '{cartera}' no aparece en Movimientos",
                impacto="Se registra igual, pero no hay movimientos asociados",
                severidad=Severity.ADVERTENCIA
            ))

        icono = (row.get("Icono") or "").strip() or "🎯"

        validos.append({
            "cartera": cartera,
            "nombre": nombre,
            "icono": icono,
            "monto_usd": monto_usd,
            "fecha_limite": fecha_limite,
        })
        carteras_vistas.add(cartera)

    return validos, issues
