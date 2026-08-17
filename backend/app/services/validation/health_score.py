"""Cálculo del Health Score de calidad de datos."""
from .types import ValidationIssue, Severity

PENALIZACION_POR_CRITICO = 15
TOPE_PENALIZACION_CRITICOS = 70
PENALIZACION_POR_ADVERTENCIA = 3
TOPE_PENALIZACION_ADVERTENCIAS = 25
TOPE_SCORE_CON_CRITICOS = 59


def calcular_health_score(issues: list[ValidationIssue]) -> dict:
    """Calcula el health score, resultado, y conteos por severidad.

    Fórmula:
      score = 100
      score -= min(TOPE_PENALIZACION_CRITICOS, n_criticos * PENALIZACION_POR_CRITICO)
      score -= min(TOPE_PENALIZACION_ADVERTENCIAS, n_advertencias * PENALIZACION_POR_ADVERTENCIA)
      score = max(0, score)
      if n_criticos > 0:
          score = min(score, TOPE_SCORE_CON_CRITICOS)

    Esto garantiza que un error crítico nunca queda oculto por advertencias menores.
    """
    n_criticos = sum(1 for i in issues if i.severidad == Severity.CRITICO)
    n_advertencias = sum(1 for i in issues if i.severidad == Severity.ADVERTENCIA)
    n_info = sum(1 for i in issues if i.severidad == Severity.INFO)

    score = 100
    score -= min(TOPE_PENALIZACION_CRITICOS, n_criticos * PENALIZACION_POR_CRITICO)
    score -= min(TOPE_PENALIZACION_ADVERTENCIAS, n_advertencias * PENALIZACION_POR_ADVERTENCIA)
    score = max(0, score)
    if n_criticos > 0:
        score = min(score, TOPE_SCORE_CON_CRITICOS)

    if n_criticos > 0:
        resultado = "con_errores"
    elif n_advertencias > 0:
        resultado = "con_advertencias"
    else:
        resultado = "ok"

    return {
        "score": score,
        "n_criticos": n_criticos,
        "n_advertencias": n_advertencias,
        "n_info": n_info,
        "resultado": resultado,
    }
