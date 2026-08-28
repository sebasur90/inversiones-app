"""Servicio para consultar calidad de datos / historial de sync."""
from sqlalchemy.orm import Session
from ..database import SyncRun, SyncIssue
from .validation.types import SEVERIDAD_RANK

# Cuántos SyncRun se conservan (ver inversiones_sync._prune_sync_runs); acota el historial.
_MAX_HISTORIAL = 20


def get_calidad_datos(db: Session) -> dict:
    """Último SyncRun con sus issues (agrupados por tab y severidad), más el historial de
    health score de los últimos syncs y las reglas que se repiten entre corridas."""
    runs = (
        db.query(SyncRun)
        .order_by(SyncRun.timestamp.desc())
        .limit(_MAX_HISTORIAL)
        .all()
    )

    if not runs:
        return {
            "ultimo_sync": None,
            "issues": [],
            "issues_por_tab": {},
            "historial": [],
            "reglas_recurrentes": [],
            "total_syncs": 0,
        }

    ultimo = runs[0]
    run_ids = [r.id for r in runs]

    issues_db = db.query(SyncIssue).filter(SyncIssue.sync_run_id == ultimo.id).all()

    issues_list = [
        {
            "tab": iss.tab,
            "fila": iss.fila,
            "campo": iss.campo,
            "regla": iss.regla,
            "severidad": iss.severidad,
            "mensaje": iss.mensaje,
            "impacto": iss.impacto,
        }
        for iss in issues_db
    ]

    issues_sorted = sorted(
        issues_list,
        key=lambda i: (SEVERIDAD_RANK.get(i["severidad"], 2), i.get("tab", ""), i.get("fila") or 999999),
    )

    issues_por_tab: dict[str, list] = {}
    for iss in issues_sorted:
        issues_por_tab.setdefault(iss["tab"], []).append(iss)

    # Historial de health score, del más viejo al más nuevo (para el sparkline).
    historial = [
        {
            "timestamp": r.timestamp,
            "health_score": r.health_score,
            "resultado": r.resultado,
            "filas_advertencia": r.filas_advertencia,
            "filas_error": r.filas_error,
        }
        for r in reversed(runs)
    ]

    # Reglas que aparecen en 2+ corridas distintas: problemas crónicos, no ruido de un sync.
    todos_issues = db.query(SyncIssue).filter(SyncIssue.sync_run_id.in_(run_ids)).all()
    por_regla: dict[str, dict] = {}
    for iss in todos_issues:
        d = por_regla.setdefault(
            iss.regla,
            {"run_ids": set(), "severidad": iss.severidad, "tab": iss.tab, "mensaje": iss.mensaje},
        )
        d["run_ids"].add(iss.sync_run_id)
        if SEVERIDAD_RANK.get(iss.severidad, 2) < SEVERIDAD_RANK.get(d["severidad"], 2):
            d["severidad"] = iss.severidad
        # El tab/mensaje de muestra sale del sync más reciente en que apareció la regla.
        if iss.sync_run_id == ultimo.id:
            d["tab"] = iss.tab
            d["mensaje"] = iss.mensaje

    reglas_recurrentes = sorted(
        (
            {
                "regla": regla,
                "tab": d["tab"],
                "severidad": d["severidad"],
                "mensaje_muestra": d["mensaje"],
                "apariciones": len(d["run_ids"]),
                "en_ultimo_sync": ultimo.id in d["run_ids"],
            }
            for regla, d in por_regla.items()
            if len(d["run_ids"]) >= 2
        ),
        key=lambda x: (-x["apariciones"], SEVERIDAD_RANK.get(x["severidad"], 2), x["regla"]),
    )

    return {
        "ultimo_sync": {
            "id": ultimo.id,
            "timestamp": ultimo.timestamp,
            "duration_ms": ultimo.duration_ms,
            "filas_procesadas": ultimo.filas_procesadas,
            "filas_validas": ultimo.filas_validas,
            "filas_advertencia": ultimo.filas_advertencia,
            "filas_error": ultimo.filas_error,
            "health_score": ultimo.health_score,
            "resultado": ultimo.resultado,
        },
        "issues": issues_sorted,
        "issues_por_tab": issues_por_tab,
        "historial": historial,
        "reglas_recurrentes": reglas_recurrentes,
        "total_syncs": len(runs),
    }
