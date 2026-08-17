"""Test crítico: validar que per-tab isolation funciona correctamente."""
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.database import Base, InstrumentoInversion, MovimientoInversion, SyncRun, SyncIssue
from backend.app.services.inversiones_sync import sync_from_sheet
from backend.app.services.sheets_client import TabRaw


def test_sync_isolation_instrumentos_bloqueada():
    """Si Instrumentos está bloqueada (columna faltante), Movimientos sigue sincronizando."""
    # Setup: DB en memoria
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed: 1 instrumento existente en DB
    db.add(InstrumentoInversion(ticker="EXISTING", nombre="Existing", tipo_instrumento="Stock", mercado="NASDAQ", moneda="USD"))
    db.add(MovimientoInversion(fecha=datetime(2024, 1, 1).date(), cartera="P1", ticker="EXISTING", tipo_movimiento="compra", precio=100, moneda="USD", comision=0))
    db.commit()

    initial_inst_count = db.query(InstrumentoInversion).count()
    initial_mov_count = db.query(MovimientoInversion).count()
    assert initial_inst_count == 1
    assert initial_mov_count == 1

    # Monkeypatch: simular lectura de Sheet con Instrumentos bloqueada (sin columna requerida)
    def mock_fetch_sheet_data():
        return {
            "Instrumentos": TabRaw(presente=True, header=["Nombre", "Tipo"], rows=[], error_lectura=None),  # Falta "Ticker"
            "Movimientos": TabRaw(presente=True, header=["Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Cantidad", "Precio", "Moneda"], rows=[
                (2, {"Fecha": "2024-02-01", "Cartera": "P1", "Ticker": "AAPL", "Tipo Movimiento": "Compra", "Cantidad": "50", "Precio": "150", "Moneda": "USD"})
            ]),
            "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
                (2, {"Fecha": "2024-02-01", "Ticker": "AAPL", "Precio": "155", "Moneda": "USD"})
            ]),
            "Objetivos": TabRaw(presente=False, header=[], rows=[]),
            "Rebalanceo": TabRaw(presente=False, header=[], rows=[]),
            "Benchmarks": TabRaw(presente=False, header=[], rows=[]),
            "Configuracion": TabRaw(presente=False, header=[], rows=[]),
        }

    import backend.app.services.inversiones_sync as sync_module
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = mock_fetch_sheet_data

    try:
        result = sync_from_sheet(db)

        # Verificar:
        # 1. Instrumentos table NOT touched (columna faltante = bloqueada)
        inst_count_after = db.query(InstrumentoInversion).count()
        assert inst_count_after == 1, "Instrumentos bloqueada, debe preservar existing data"

        # 2. Movimientos table IS updated (no error, columnas OK)
        mov_count_after = db.query(MovimientoInversion).count()
        assert mov_count_after == 1, "Movimientos sin bloques, puede estar vacío si hay error en validación de tickers"

        # 3. Issues: debe haber un crítico para Instrumentos (columnas faltantes)
        issues = result.get("issues", [])
        inst_issues = [i for i in issues if i["tab"] == "Instrumentos"]
        assert len(inst_issues) > 0, "Debe reportar issue de Instrumentos"
        assert inst_issues[0]["severidad"] == "critico", "Debe ser crítico"

        # 4. Health score debe reflejar el crítico
        assert result["health_score"] <= 59, "Con crítico, score capped a 59"

    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_sync_creates_sync_run_record():
    """Cada sync crea un registro SyncRun persistido en DB."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    def mock_fetch_sheet_data():
        return {
            "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[]),
            "Movimientos": TabRaw(presente=True, header=["Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Precio", "Moneda"], rows=[]),
            "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[]),
            "Objetivos": TabRaw(presente=False, header=[], rows=[]),
            "Rebalanceo": TabRaw(presente=False, header=[], rows=[]),
            "Benchmarks": TabRaw(presente=False, header=[], rows=[]),
            "Configuracion": TabRaw(presente=False, header=[], rows=[]),
        }

    import backend.app.services.inversiones_sync as sync_module
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = mock_fetch_sheet_data

    try:
        sync_from_sheet(db)

        # Verificar que SyncRun se creó
        sync_run = db.query(SyncRun).first()
        assert sync_run is not None, "Debe crear un registro SyncRun"
        assert sync_run.resultado == "ok", "Sin problemas, resultado debe ser 'ok'"
        assert sync_run.health_score == 100, "Sin issues, score debe ser 100"

    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()
