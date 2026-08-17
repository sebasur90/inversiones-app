"""Servicio para consultar calidad de datos / historial de sync."""
from sqlalchemy.orm import Session
from ..database import SyncRun, SyncIssue
from .validation.types import SEVERIDAD_RANK


def get_calidad_datos(db: Session) -> dict:
    """Obtiene el último SyncRun con sus issues, agrupados por tab y ordenados por severidad."""
    ultimo = db.query(SyncRun).order_by(SyncRun.timestamp.desc()).first()

    if ultimo is None:
        return {
            "ultimo_sync": None,
            "issues": [],
            "issues_por_tab": {},
        }

    issues_db = db.query(SyncIssue).filter(SyncIssue.sync_run_id == ultimo.id).all()

    # Convertir a dicts y ordenar por severidad
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
        key=lambda i: (SEVERIDAD_RANK.get(i["severidad"], 2), i.get("tab", ""), i.get("fila") or 999999)
    )

    # Agrupar por tab
    issues_por_tab: dict[str, list] = {}
    for iss in issues_sorted:
        tab = iss["tab"]
        if tab not in issues_por_tab:
            issues_por_tab[tab] = []
        issues_por_tab[tab].append(iss)

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
    }
