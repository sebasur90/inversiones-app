"""Tests para la fórmula del Health Score."""
from backend.app.services.validation.types import ValidationIssue, Severity
from backend.app.services.validation.health_score import calcular_health_score


def test_health_score_sin_issues():
    """Score de 100 sin issues."""
    issues = []
    result = calcular_health_score(issues)
    assert result["score"] == 100
    assert result["resultado"] == "ok"
    assert result["n_criticos"] == 0
    assert result["n_advertencias"] == 0
    assert result["n_info"] == 0


def test_health_score_1_critico_100_advertencias():
    """Con 1 crítico + 100 advertencias, score queda capado en 59."""
    issues = [
        ValidationIssue("Test", "regla1", "msg", "impacto", Severity.CRITICO)
    ] + [
        ValidationIssue("Test", f"regla{i}", "msg", "impacto", Severity.ADVERTENCIA)
        for i in range(100)
    ]
    result = calcular_health_score(issues)
    assert result["score"] == 59, "Score con crítico debe quedar capado en 59 independientemente de advertencias"
    assert result["resultado"] == "con_errores"
    assert result["n_criticos"] == 1
    assert result["n_advertencias"] == 100


def test_health_score_100_advertencias_solas():
    """Con 100 advertencias solas, score nunca baja a <75."""
    issues = [
        ValidationIssue("Test", f"regla{i}", "msg", "impacto", Severity.ADVERTENCIA)
        for i in range(100)
    ]
    result = calcular_health_score(issues)
    assert result["score"] >= 75, "100 advertencias solas no deben bajar score por debajo de 75"
    assert result["resultado"] == "con_advertencias"
    assert result["n_criticos"] == 0


def test_health_score_1_critico():
    """1 crítico solo → score 85, capado a 59."""
    issues = [ValidationIssue("Test", "regla1", "msg", "impacto", Severity.CRITICO)]
    result = calcular_health_score(issues)
    assert result["score"] == 59
    assert result["resultado"] == "con_errores"


def test_health_score_1_advertencia():
    """1 advertencia → score 97."""
    issues = [ValidationIssue("Test", "regla1", "msg", "impacto", Severity.ADVERTENCIA)]
    result = calcular_health_score(issues)
    assert result["score"] == 97


def test_health_score_solo_info():
    """Solo issues info → score 100."""
    issues = [
        ValidationIssue("Test", f"regla{i}", "msg", "impacto", Severity.INFO)
        for i in range(10)
    ]
    result = calcular_health_score(issues)
    assert result["score"] == 100
    assert result["resultado"] == "ok"


def test_health_score_mezcla():
    """2 críticos + 5 advertencias + 3 info → score 100 - 30 - 15 = 55.

    El tope por críticos (59) es un techo, no un piso: 55 ya está por debajo, así que no aplica.
    """
    issues = [
        ValidationIssue("Test", f"critico{i}", "msg", "impacto", Severity.CRITICO)
        for i in range(2)
    ] + [
        ValidationIssue("Test", f"adv{i}", "msg", "impacto", Severity.ADVERTENCIA)
        for i in range(5)
    ] + [
        ValidationIssue("Test", f"info{i}", "msg", "impacto", Severity.INFO)
        for i in range(3)
    ]
    result = calcular_health_score(issues)
    # score = 100 - min(70, 2*15) - min(25, 5*3) = 100 - 30 - 15 = 55
    # el cap por críticos es min(score, 59) → 55 se mantiene
    assert result["score"] == 55
    assert result["n_criticos"] == 2
    assert result["n_advertencias"] == 5
    assert result["n_info"] == 3
