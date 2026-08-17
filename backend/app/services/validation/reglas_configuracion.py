"""Validación de la pestaña Configuracion."""
from .types import ValidationIssue, Severity
from .parsers import _strip_accents, _parse_numero


def validar_configuracion(rows: list[tuple[int, dict]]) -> tuple[list[dict], list[ValidationIssue]]:
    """Valida filas de Configuracion (campos opcionales, solo Cartera obligatoria).

    Devuelve (validos, issues).
    """
    validos = []
    carteras_vistas: set[str | None] = set()
    issues = []

    for row_num, row in rows:
        cartera_raw = (row.get("Cartera") or "").strip()
        cartera = None if not cartera_raw or _strip_accents(cartera_raw).lower() == "consolidado" else cartera_raw

        # Duplicado por cartera → advertencia/drop (antes crítico)
        if cartera in carteras_vistas:
            issues.append(ValidationIssue(
                tab="Configuracion", fila=row_num, regla="cartera_duplicada",
                mensaje=f"Configuración duplicada para cartera: {cartera or 'Consolidado'}",
                impacto="Se descarta este duplicado",
                severidad=Severity.ADVERTENCIA
            ))
            continue

        benchmark = (row.get("Benchmark") or "").strip() or None

        def _campo_opcional(nombre_col: str, nombre_error: str) -> tuple[float | None, bool]:
            """Parsea un campo numérico opcional. Devuelve (valor, ok)."""
            raw = (row.get(nombre_col) or "").strip()
            if not raw:
                return None, True
            valor = _parse_numero(raw)
            if valor is None:
                issues.append(ValidationIssue(
                    tab="Configuracion", fila=row_num, campo=nombre_col,
                    regla=f"{nombre_col.lower()}_invalido",
                    mensaje=f"{nombre_error} inválido: {raw}",
                    impacto=f"Se descarta este campo, la configuración se guarda sin él",
                    severidad=Severity.ADVERTENCIA
                ))
                return None, True  # salvage: solo anula este campo
            return valor, True

        rendimiento_objetivo, ok1 = _campo_opcional("Rendimiento Objetivo", "Rendimiento Objetivo")
        peso_maximo, ok2 = _campo_opcional("Peso Máximo", "Peso Máximo")
        peso_minimo, ok3 = _campo_opcional("Peso Mínimo", "Peso Mínimo")
        tolerancia, ok4 = _campo_opcional("Tolerancia", "Tolerancia")

        # Validar rangos
        if peso_maximo is not None and not (0 <= peso_maximo <= 100):
            issues.append(ValidationIssue(
                tab="Configuracion", fila=row_num, campo="Peso Máximo",
                regla="peso_maximo_fuera_rango",
                mensaje=f"Peso Máximo fuera de rango [0,100]: {peso_maximo}",
                impacto="Se anula este campo",
                severidad=Severity.ADVERTENCIA
            ))
            peso_maximo = None

        if peso_minimo is not None and not (0 <= peso_minimo <= 100):
            issues.append(ValidationIssue(
                tab="Configuracion", fila=row_num, campo="Peso Mínimo",
                regla="peso_minimo_fuera_rango",
                mensaje=f"Peso Mínimo fuera de rango [0,100]: {peso_minimo}",
                impacto="Se anula este campo",
                severidad=Severity.ADVERTENCIA
            ))
            peso_minimo = None

        if peso_maximo is not None and peso_minimo is not None and peso_minimo > peso_maximo:
            issues.append(ValidationIssue(
                tab="Configuracion", fila=row_num,
                regla="peso_minimo_mayor_maximo",
                mensaje=f"Peso Mínimo ({peso_minimo}) mayor que Peso Máximo ({peso_maximo})",
                impacto="Se anulan ambos campos",
                severidad=Severity.ADVERTENCIA
            ))
            peso_maximo, peso_minimo = None, None

        if tolerancia is not None and tolerancia < 0:
            issues.append(ValidationIssue(
                tab="Configuracion", fila=row_num, campo="Tolerancia",
                regla="tolerancia_negativa",
                mensaje=f"Tolerancia negativa: {tolerancia}",
                impacto="Se anula este campo",
                severidad=Severity.ADVERTENCIA
            ))
            tolerancia = None

        validos.append({
            "cartera": cartera,
            "benchmark": benchmark,
            "rendimiento_objetivo": rendimiento_objetivo,
            "peso_maximo": peso_maximo,
            "peso_minimo": peso_minimo,
            "tolerancia": tolerancia,
        })
        carteras_vistas.add(cartera)

    return validos, issues
