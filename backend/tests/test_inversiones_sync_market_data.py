"""Tests de integración de `market_data` (CER/MEP y Benchmarks automáticos) dentro del sync.

Todos mockean `fetch_sheet_data` (sin red hacia Sheets) y, cuando corresponde, las funciones de
`market_data` (sin red hacia las APIs externas) — igual que `test_inversiones_sync_isolation.py`.
"""
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.database import Base, IndiceMercado, BenchmarkValor, PrecioInstrumento
from backend.app.services.inversiones_sync import sync_from_sheet
from backend.app.services.sheets_client import TabRaw
import backend.app.services.inversiones_sync as sync_module

TABS_BASE = {
    "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[]),
    "Movimientos": TabRaw(presente=True, header=["Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Precio", "Moneda"], rows=[]),
    "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[]),
    "Objetivos": TabRaw(presente=False, header=[], rows=[]),
    "Rebalanceo": TabRaw(presente=False, header=[], rows=[]),
    "Benchmarks": TabRaw(presente=False, header=[], rows=[]),
    "Configuracion": TabRaw(presente=False, header=[], rows=[]),
    "Tipos de Cambio": TabRaw(presente=False, header=[], rows=[]),
}


def _make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _mock_fetch(overrides: dict):
    tabs = dict(TABS_BASE, **overrides)
    return lambda: tabs


def test_tipos_cambio_tab_alimenta_indices_mercado(monkeypatch):
    """La pestaña "Tipos de Cambio" (sin USE_EXTERNAL_APIS) puebla IndiceMercado con fuente='sheet'."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch({
        "Tipos de Cambio": TabRaw(presente=True, header=["Fecha", "Tipo", "Valor"], rows=[
            (2, {"Fecha": "2026-02-18", "Tipo": "CER", "Valor": "103.6"}),
            (3, {"Fecha": "2026-02-18", "Tipo": "MEP", "Valor": "818"}),
        ]),
    })
    # Explícito y no dependiente de la env var del contenedor (que en docker-compose.yml /
    # docker-compose.corporate.yml está en `true` por defecto): este test sólo quiere probar
    # la ruta del Sheet, sin pegarle a la red.
    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: False)
    try:
        result = sync_from_sheet(db)
        row = db.query(IndiceMercado).filter(IndiceMercado.fecha == date(2026, 2, 18)).first()
        assert row is not None
        assert float(row.cer) == 103.6
        assert float(row.mep) == 818.0
        assert row.fuente == "sheet"
        assert result["indices_mercado"] == 1
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_sin_use_external_apis_no_llama_market_data(monkeypatch):
    """Con USE_EXTERNAL_APIS apagado (default), no se toca la red ni se agregan filas 'api'."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch({})

    def _boom(*a, **kw):
        raise AssertionError("no debería llamarse a market_data con USE_EXTERNAL_APIS apagado")

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: False)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", _boom)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", _boom)
    monkeypatch.setattr(sync_module.market_data_precios, "fetch_precios_renta_fija_api", _boom)

    try:
        sync_from_sheet(db)
        assert db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").count() == 0
        assert db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "api").count() == 0
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").count() == 0
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_use_external_apis_completa_huecos_sin_pisar_sheet(monkeypatch):
    """Con USE_EXTERNAL_APIS prendido: la API llena fechas que el Sheet no cubre y no pisa las que sí."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch({
        "Tipos de Cambio": TabRaw(presente=True, header=["Fecha", "Tipo", "Valor"], rows=[
            (2, {"Fecha": "2026-02-18", "Tipo": "MEP", "Valor": "999"}),  # el Sheet manda para esta fecha
        ]),
    })

    def _fake_fetch_indices(fechas_excluir):
        # Simula lo que haría market_data_indices.fetch_indices_mercado_api de verdad: el
        # llamador (inversiones_sync) ya filtra por fechas_excluir, pero acá se replica ese
        # filtro para que el test no dependa de ese detalle de implementación.
        candidatas = [
            {"fecha": date(2026, 2, 18), "cer": None, "mep": 1.0, "fuente": "api"},  # el Sheet ya cubre esta fecha
            {"fecha": date(2026, 2, 19), "cer": 105.0, "mep": 820.0, "fuente": "api"},
        ]
        return [row for row in candidatas if row["fecha"] not in fechas_excluir], []

    def _fake_fetch_benchmarks():
        return [{"fecha": date(2026, 2, 19), "benchmark": "Inflación (INDEC)", "valor": 110.0, "fuente": "api"}], []

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", _fake_fetch_indices)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", _fake_fetch_benchmarks)

    try:
        result = sync_from_sheet(db)

        fila_sheet = db.query(IndiceMercado).filter(IndiceMercado.fecha == date(2026, 2, 18)).first()
        assert fila_sheet.fuente == "sheet"
        assert float(fila_sheet.mep) == 999.0  # el Sheet ganó, la API no pisó

        fila_api = db.query(IndiceMercado).filter(IndiceMercado.fecha == date(2026, 2, 19)).first()
        assert fila_api is not None
        assert fila_api.fuente == "api"
        assert float(fila_api.cer) == 105.0

        bench_api = db.query(BenchmarkValor).filter(BenchmarkValor.fuente == "api").first()
        assert bench_api is not None
        assert bench_api.benchmark == "Inflación (INDEC)"

        assert result["indices_mercado"] == 2
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_api_caida_preserva_filas_api_de_una_corrida_anterior(monkeypatch):
    """Si la API falla en una corrida, las filas 'api' de una corrida anterior no se borran."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch({})

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api",
                         lambda fechas_excluir: ([{"fecha": date(2026, 3, 1), "cer": 200.0, "mep": 900.0, "fuente": "api"}], []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))

    try:
        sync_from_sheet(db)
        assert db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").count() == 1

        # Segunda corrida: la API de índices ahora falla (None) → no debe borrar lo que ya había.
        monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api",
                             lambda fechas_excluir: (None, []))
        result = sync_from_sheet(db)

        assert db.query(IndiceMercado).filter(IndiceMercado.fuente == "api").count() == 1
        assert result["indices_mercado"] == 1
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def _tabs_con_bono():
    return {
        "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[
            (2, {"Ticker": "TZXD7", "Nombre": "Boncer 2027", "Tipo Instrumento": "Bono", "Mercado": "MERVAL", "Moneda": "ARS"}),
        ]),
        "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
            (2, {"Fecha": "2026-07-27", "Ticker": "TZXD7", "Precio": "2.7135", "Moneda": "ARS"}),
        ]),
    }


def test_precio_renta_fija_api_normaliza_escala_y_persiste(monkeypatch):
    """data912 cotiza por lámina de 100; se calibra contra el último precio del Sheet y se divide."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_bono())

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})

    try:
        result = sync_from_sheet(db)
        sheet_row = db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "sheet").one()
        assert float(sheet_row.precio) == 2.7135
        api_row = db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").one()
        assert api_row.ticker == "TZXD7"
        assert api_row.moneda == "ARS"
        assert round(float(api_row.precio), 4) == 2.7285  # 272.85 / 100
        assert result["precios"] == 2
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_precio_renta_fija_api_caida_preserva_corrida_anterior(monkeypatch):
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_bono())

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})

    try:
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").count() == 1

        # data912 se cae (None) → la fila 'api' de la corrida anterior no se borra.
        monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: None)
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").count() == 1
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()
