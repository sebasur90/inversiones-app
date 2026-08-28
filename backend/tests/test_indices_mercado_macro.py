"""get_indices_mercado: riesgo país en la serie + inflación mensual derivada del
benchmark automático de INDEC (Ola 5, ítem 10)."""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, IndiceMercado, BenchmarkValor
from app.services.inversiones_analytics import get_indices_mercado


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def test_riesgo_pais_va_en_los_puntos(db: Session):
    hoy = date.today()
    db.add_all([
        IndiceMercado(fecha=hoy - timedelta(days=2), cer=100.0, mep=1000.0, riesgo_pais=1500.0),
        IndiceMercado(fecha=hoy - timedelta(days=1), cer=101.0, mep=1010.0, riesgo_pais=1400.0),
    ])
    db.commit()

    out = get_indices_mercado(3650, db)
    assert [p["riesgo_pais"] for p in out["puntos"]] == [1500.0, 1400.0]
    # variación riesgo país = 1400/1500 - 1 = -6.67%
    assert out["variacion_riesgo_pais_pct"] == pytest.approx(-6.67, abs=0.01)


def test_riesgo_pais_ausente_queda_none(db: Session):
    hoy = date.today()
    db.add(IndiceMercado(fecha=hoy - timedelta(days=1), cer=100.0, mep=1000.0))
    db.commit()

    out = get_indices_mercado(3650, db)
    assert out["puntos"][0]["riesgo_pais"] is None
    assert out["variacion_riesgo_pais_pct"] is None


def test_inflacion_mensual_derivada_del_benchmark_indec(db: Session):
    # El benchmark se guarda como nivel compuesto: 110 -> 121 -> 127.05
    # => inflación mensual 10%, 5%.
    db.add_all([
        BenchmarkValor(fecha=date(2026, 1, 31), benchmark="Inflación (INDEC)", valor=110.0, fuente="api"),
        BenchmarkValor(fecha=date(2026, 2, 28), benchmark="Inflación (INDEC)", valor=121.0, fuente="api"),
        BenchmarkValor(fecha=date(2026, 3, 31), benchmark="Inflación (INDEC)", valor=127.05, fuente="api"),
    ])
    db.commit()

    out = get_indices_mercado(3650, db)
    infl = out["inflacion_mensual"]
    assert [p["valor_pct"] for p in infl] == [pytest.approx(10.0), pytest.approx(5.0)]
    assert infl[0]["fecha"] == date(2026, 2, 28)


def test_inflacion_mensual_vacia_sin_benchmark(db: Session):
    db.add(IndiceMercado(fecha=date.today(), cer=100.0))
    db.commit()
    out = get_indices_mercado(3650, db)
    assert out["inflacion_mensual"] == []


def test_b15_inflacion_mensual_ignora_filas_manuales(db: Session):
    # Una fila manual (fuente='sheet') con el mismo nombre no debe intercalar niveles.
    db.add_all([
        BenchmarkValor(fecha=date(2026, 1, 31), benchmark="Inflación (INDEC)", valor=100.0, fuente="api"),
        BenchmarkValor(fecha=date(2026, 2, 10), benchmark="Inflación (INDEC)", valor=999.0, fuente="sheet"),
        BenchmarkValor(fecha=date(2026, 2, 28), benchmark="Inflación (INDEC)", valor=105.0, fuente="api"),
    ])
    db.commit()
    out = get_indices_mercado(3650, db)
    assert [p["valor_pct"] for p in out["inflacion_mensual"]] == [pytest.approx(5.0)]


def test_b15_inflacion_mensual_saltea_meses_faltantes(db: Session):
    # Falta marzo: la variación ene->feb es mensual (se muestra); feb->abr es de dos meses
    # (no se muestra como si fuera de uno).
    db.add_all([
        BenchmarkValor(fecha=date(2026, 1, 31), benchmark="Inflación (INDEC)", valor=100.0, fuente="api"),
        BenchmarkValor(fecha=date(2026, 2, 28), benchmark="Inflación (INDEC)", valor=104.0, fuente="api"),
        BenchmarkValor(fecha=date(2026, 4, 30), benchmark="Inflación (INDEC)", valor=115.0, fuente="api"),
    ])
    db.commit()
    out = get_indices_mercado(3650, db)
    infl = out["inflacion_mensual"]
    assert [p["fecha"] for p in infl] == [date(2026, 2, 28)]
    assert infl[0]["valor_pct"] == pytest.approx(4.0)


def test_b15_inflacion_primer_mes_de_la_ventana_no_se_pierde(db: Session):
    # Con un mes extra hacia atrás, el primer mes dentro de la ventana conserva su variación.
    hoy = date.today()
    m0 = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)     # mes pasado
    m_prev = (m0 - timedelta(days=1)).replace(day=1)                  # dos meses atrás
    db.add_all([
        BenchmarkValor(fecha=m_prev, benchmark="Inflación (INDEC)", valor=100.0, fuente="api"),
        BenchmarkValor(fecha=m0, benchmark="Inflación (INDEC)", valor=103.0, fuente="api"),
    ])
    db.commit()
    # ventana que arranca justo en m0: sin el mes extra, m0 no tendría nivel previo.
    dias = (hoy - m0).days + 1
    out = get_indices_mercado(dias, db)
    assert [p["fecha"] for p in out["inflacion_mensual"]] == [m0]
    assert out["inflacion_mensual"][0]["valor_pct"] == pytest.approx(3.0)
