"""Historial de calidad de datos: sparkline del health score + reglas que se repiten
entre corridas (Ola 5, ítem 7)."""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, SyncRun, SyncIssue
from app.services.calidad_datos import get_calidad_datos


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _run(db, *, dias_atras, score, resultado="ok", adv=0, err=0):
    r = SyncRun(
        timestamp=datetime(2026, 1, 20) - timedelta(days=dias_atras),
        duration_ms=1000,
        filas_procesadas=100,
        filas_validas=100 - adv - err,
        filas_advertencia=adv,
        filas_error=err,
        health_score=score,
        resultado=resultado,
    )
    db.add(r)
    db.commit()
    return r


def _issue(db, run, regla, tab="Movimientos", severidad="advertencia", mensaje="algo"):
    db.add(SyncIssue(
        sync_run_id=run.id, tab=tab, fila=1, campo="x", regla=regla,
        severidad=severidad, mensaje=mensaje, impacto="bajo",
    ))
    db.commit()


def test_sin_syncs_devuelve_estructura_vacia(db: Session):
    out = get_calidad_datos(db)
    assert out["ultimo_sync"] is None
    assert out["historial"] == []
    assert out["reglas_recurrentes"] == []
    assert out["total_syncs"] == 0


def test_historial_ordenado_del_mas_viejo_al_mas_nuevo(db: Session):
    _run(db, dias_atras=3, score=60)
    _run(db, dias_atras=2, score=75)
    _run(db, dias_atras=1, score=90)

    out = get_calidad_datos(db)
    assert [h["health_score"] for h in out["historial"]] == [60, 75, 90]
    assert out["total_syncs"] == 3
    assert out["ultimo_sync"]["health_score"] == 90


def test_historial_se_limita_a_20(db: Session):
    for i in range(25):
        _run(db, dias_atras=25 - i, score=50 + i)
    out = get_calidad_datos(db)
    assert len(out["historial"]) == 20
    assert out["total_syncs"] == 20
    # los 20 más recientes -> scores 55..74
    assert out["historial"][0]["health_score"] == 55
    assert out["historial"][-1]["health_score"] == 74


def test_reglas_recurrentes_solo_las_que_aparecen_en_2_o_mas_corridas(db: Session):
    r1 = _run(db, dias_atras=3, score=70, resultado="con_advertencias", adv=2)
    r2 = _run(db, dias_atras=2, score=72, resultado="con_advertencias", adv=1)
    r3 = _run(db, dias_atras=1, score=71, resultado="con_advertencias", adv=1)

    _issue(db, r1, "cer_faltante")
    _issue(db, r1, "precio_viejo")
    _issue(db, r2, "cer_faltante")
    _issue(db, r3, "cer_faltante")
    _issue(db, r3, "solo_una_vez")

    out = get_calidad_datos(db)
    recurrentes = {x["regla"]: x for x in out["reglas_recurrentes"]}
    assert set(recurrentes) == {"cer_faltante"}
    assert recurrentes["cer_faltante"]["apariciones"] == 3
    assert recurrentes["cer_faltante"]["en_ultimo_sync"] is True


def test_regla_recurrente_no_presente_en_el_ultimo_sync(db: Session):
    r1 = _run(db, dias_atras=3, score=70)
    r2 = _run(db, dias_atras=2, score=80)
    _run(db, dias_atras=1, score=95)  # último sync, limpio

    _issue(db, r1, "precio_viejo", severidad="critico")
    _issue(db, r2, "precio_viejo", severidad="advertencia")

    out = get_calidad_datos(db)
    assert len(out["reglas_recurrentes"]) == 1
    regla = out["reglas_recurrentes"][0]
    assert regla["regla"] == "precio_viejo"
    assert regla["apariciones"] == 2
    assert regla["en_ultimo_sync"] is False
    # se queda con la severidad más grave observada
    assert regla["severidad"] == "critico"
