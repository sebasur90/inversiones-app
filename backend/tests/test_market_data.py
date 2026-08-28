"""Tests de la orquestación de `market_data.indices` (sin red: mockea `argentina_datos`)."""
from datetime import date
from backend.app.services.market_data import indices as market_data_indices
from backend.app.services.market_data import argentina_datos


def test_fetch_indices_mercado_api_combina_uva_mep_y_riesgo_pais(monkeypatch):
    """Combina las tres series por fecha. CER/MEP se excluyen en las fechas del Sheet; el
    riesgo país igual viene en esas fechas (A5: el Sheet nunca lo aporta)."""
    monkeypatch.setattr(argentina_datos, "fetch_uva_serie", lambda: [
        (date(2026, 1, 1), 100.0),
        (date(2026, 1, 2), 101.0),
    ])
    monkeypatch.setattr(argentina_datos, "fetch_dolar_mep_historico", lambda: [
        (date(2026, 1, 1), 1000.0),
        (date(2026, 1, 3), 1010.0),
    ])
    monkeypatch.setattr(argentina_datos, "fetch_riesgo_pais", lambda: [
        (date(2026, 1, 1), 1500.0),
        (date(2026, 1, 2), 1490.0),
    ])

    filas, issues = market_data_indices.fetch_indices_mercado_api(fechas_excluir={date(2026, 1, 2)})

    assert issues == []
    por_fecha = {f["fecha"]: f for f in filas}
    assert por_fecha[date(2026, 1, 1)] == {
        "fecha": date(2026, 1, 1), "cer": 100.0, "mep": 1000.0, "riesgo_pais": 1500.0, "fuente": "api",
    }
    # 2026-01-02 la trae el Sheet: CER/MEP excluidos, pero el riesgo país igual viene para que
    # el sync lo mergee sobre la fila 'sheet' de esa fecha (A5).
    assert por_fecha[date(2026, 1, 2)] == {
        "fecha": date(2026, 1, 2), "cer": None, "mep": None, "riesgo_pais": 1490.0, "fuente": "api",
    }
    # 2026-01-03 sólo tiene MEP → cer y riesgo_pais quedan None.
    assert por_fecha[date(2026, 1, 3)]["cer"] is None
    assert por_fecha[date(2026, 1, 3)]["riesgo_pais"] is None
    assert por_fecha[date(2026, 1, 3)]["mep"] == 1010.0


def test_fetch_indices_mercado_api_todas_las_fuentes_caidas(monkeypatch):
    """Si ninguna fuente responde, devuelve None (no []) para que el llamador no borre nada."""
    monkeypatch.setattr(argentina_datos, "fetch_uva_serie", lambda: None)
    monkeypatch.setattr(argentina_datos, "fetch_dolar_mep_historico", lambda: None)
    monkeypatch.setattr(argentina_datos, "fetch_riesgo_pais", lambda: None)

    filas, issues = market_data_indices.fetch_indices_mercado_api(fechas_excluir=set())

    assert filas is None
    assert len(issues) == 3


def test_fetch_indices_mercado_api_una_fuente_caida(monkeypatch):
    """Si sólo una fuente falla, se sigue con las otras y se reporta advertencia."""
    monkeypatch.setattr(argentina_datos, "fetch_uva_serie", lambda: None)
    monkeypatch.setattr(argentina_datos, "fetch_dolar_mep_historico", lambda: [(date(2026, 1, 1), 1000.0)])
    monkeypatch.setattr(argentina_datos, "fetch_riesgo_pais", lambda: [(date(2026, 1, 1), 1500.0)])

    filas, issues = market_data_indices.fetch_indices_mercado_api(fechas_excluir=set())

    assert filas is not None
    assert len(filas) == 1
    assert filas[0]["mep"] == 1000.0
    assert filas[0]["cer"] is None
    assert filas[0]["riesgo_pais"] == 1500.0
    assert len(issues) == 1
    assert "uva" in issues[0].regla


def test_fetch_indices_mercado_api_solo_riesgo_pais(monkeypatch):
    """Con CER y MEP caídos pero riesgo país disponible, igual devuelve filas."""
    monkeypatch.setattr(argentina_datos, "fetch_uva_serie", lambda: None)
    monkeypatch.setattr(argentina_datos, "fetch_dolar_mep_historico", lambda: None)
    monkeypatch.setattr(argentina_datos, "fetch_riesgo_pais", lambda: [(date(2026, 1, 1), 1500.0)])

    filas, issues = market_data_indices.fetch_indices_mercado_api(fechas_excluir=set())

    assert filas is not None
    assert len(filas) == 1
    assert filas[0]["riesgo_pais"] == 1500.0
    assert len(issues) == 2  # uva + mep caídos


def test_fetch_benchmarks_api_construye_indice_compuesto(monkeypatch):
    """La inflación mensual (%) se compone en un índice base-100 creciente."""
    monkeypatch.setattr(argentina_datos, "fetch_inflacion_mensual", lambda: [
        (date(2026, 1, 31), 10.0),   # +10%
        (date(2026, 2, 28), 10.0),   # +10% sobre el nuevo nivel
    ])

    filas, issues = market_data_indices.fetch_benchmarks_api()

    assert issues == []
    assert len(filas) == 2
    assert filas[0]["benchmark"] == market_data_indices.BENCHMARK_INFLACION_INDEC
    assert round(filas[0]["valor"], 4) == 110.0
    assert round(filas[1]["valor"], 4) == 121.0
    assert all(f["fuente"] == "api" for f in filas)


def test_fetch_benchmarks_api_falla_devuelve_none(monkeypatch):
    monkeypatch.setattr(argentina_datos, "fetch_inflacion_mensual", lambda: None)

    filas, issues = market_data_indices.fetch_benchmarks_api()

    assert filas is None
    assert len(issues) == 1
