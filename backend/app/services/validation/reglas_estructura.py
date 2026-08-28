"""Validación estructural de pestañas: columnas, encabezados, etc."""
from .types import ValidationIssue, Severity
from .parsers import _strip_accents

COLUMNAS_REQUERIDAS = {
    "Instrumentos": ["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"],
    "Movimientos": ["Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Precio", "Moneda"],
    "Precios": ["Fecha", "Ticker", "Precio", "Moneda"],
    "Objetivos": ["Cartera", "Nombre", "Monto USD", "Fecha Límite"],
    "Rebalanceo": ["Cartera", "Eje", "Categoría", "Porcentaje Objetivo"],
    "Benchmarks": ["Fecha", "Benchmark", "Valor"],
    "Configuracion": ["Cartera"],
    "Tipos de Cambio": ["Fecha", "Tipo", "Valor"],
}

COLUMNAS_CONOCIDAS = {
    "Instrumentos": [
        "Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda",
        "País", "Pais", "Sector", "Fecha Vencimiento",
        "Objetivo Modo", "Objetivo Valor", "Stop Loss Modo", "Stop Loss Valor"
    ],
    "Movimientos": [
        "Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Cantidad", "Precio", "Moneda",
        "Comisión", "Comision", "CER", "MEP"
    ],
    "Precios": ["Fecha", "Ticker", "Precio", "Moneda", "CER", "MEP"],
    "Objetivos": ["Cartera", "Nombre", "Fecha Límite", "Fecha Limite", "Monto USD", "Icono"],
    "Rebalanceo": ["Cartera", "Eje", "Categoría", "Categoria", "Porcentaje Objetivo"],
    "Benchmarks": ["Fecha", "Benchmark", "Valor"],
    "Configuracion": [
        "Cartera", "Benchmark", "Rendimiento Objetivo",
        "Peso Máximo", "Peso Mínimo", "Tolerancia"
    ],
    "Tipos de Cambio": ["Fecha", "Tipo", "Valor"],
}


def _normalizar_encabezados(headers: list[str]) -> list[str]:
    """Normaliza encabezados quitando acentos para comparación."""
    return [_strip_accents(h).strip() for h in headers]


def validar_estructura_tab(
    tab: str,
    headers: list[str],
    rows: list[tuple[int, dict]],
    tab_requerida: bool,
    tab_actual_no_vacia: bool,
) -> tuple[bool, list[ValidationIssue]]:
    """
    Valida estructura de una pestaña.

    Returns: (bloqueada, issues)
    - bloqueada=True si hay un problema que impide procesar esa pestaña
    - issues: lista de ValidationIssue encontrados
    """
    issues = []

    # Normalizar encabezados para comparación
    headers_norm = _normalizar_encabezados(headers)
    conocidas_norm = _normalizar_encabezados(COLUMNAS_CONOCIDAS.get(tab, []))
    requeridas = COLUMNAS_REQUERIDAS.get(tab, [])
    requeridas_norm = _normalizar_encabezados(requeridas)

    # Chequear columnas requeridas
    faltantes = [r for r in requeridas_norm if r not in headers_norm]
    if faltantes:
        severidad = Severity.CRITICO if tab_requerida else Severity.ADVERTENCIA
        issues.append(ValidationIssue(
            tab=tab,
            regla="columnas_requeridas_faltantes",
            mensaje=f"Columna(s) requerida(s) faltante(s): {', '.join(faltantes)}",
            impacto=f"No se pueden procesar filas de {tab}",
            severidad=severidad,
        ))
        return True, issues

    # Chequear encabezados duplicados
    if len(headers) != len(set(headers_norm)):
        severidad = Severity.CRITICO if tab_requerida else Severity.ADVERTENCIA
        issues.append(ValidationIssue(
            tab=tab,
            regla="encabezados_duplicados",
            mensaje=f"Hay encabezados duplicados en {tab}",
            impacto=f"No se pueden procesar filas de {tab}",
            severidad=severidad,
        ))
        return True, issues

    # Chequear columnas no reconocidas (info, no bloquea)
    no_reconocidas = [h for h in headers_norm if h not in conocidas_norm]
    if no_reconocidas:
        issues.append(ValidationIssue(
            tab=tab,
            regla="columna_no_reconocida",
            mensaje=f"Columna(s) no reconocida(s): {', '.join(no_reconocidas[:3])}",
            impacto="Se ignorarán esas columnas",
            severidad=Severity.INFO,
        ))

    # Vaciamiento sospechoso
    if len(rows) == 0 and tab_actual_no_vacia:
        issues.append(ValidationIssue(
            tab=tab,
            regla="vaciamiento_sospechoso",
            mensaje=f"La pestaña {tab} no tiene filas válidas pero la tabla en DB tiene datos",
            impacto="Se preservarán los datos existentes para evitar pérdida accidental",
            severidad=Severity.CRITICO,
        ))
        return True, issues

    return False, issues
