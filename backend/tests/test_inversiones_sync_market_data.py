"""Tests de integración de `market_data` (CER/MEP y Benchmarks automáticos) dentro del sync.

Todos mockean `fetch_sheet_data` (sin red hacia Sheets) y, cuando corresponde, las funciones de
`market_data` (sin red hacia las APIs externas) — igual que `test_inversiones_sync_isolation.py`.
"""
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.database import Base, IndiceMercado, BenchmarkValor, PrecioInstrumento, SyncIssue
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
    monkeypatch.setattr(sync_module.market_data_precios, "fetch_precios_renta_variable_api", _boom)

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


def test_a5_riesgo_pais_se_mergea_sobre_fila_sheet(monkeypatch):
    """A5: el Sheet cubre una fecha con CER/MEP; el riesgo país de la API se mergea sobre esa
    fila (fuente='sheet') sin pisar CER/MEP, en vez de descartarse por 'fecha excluida'."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch({
        "Tipos de Cambio": TabRaw(presente=True, header=["Fecha", "Tipo", "Valor"], rows=[
            (2, {"Fecha": "2026-02-18", "Tipo": "CER", "Valor": "103.6"}),
            (3, {"Fecha": "2026-02-18", "Tipo": "MEP", "Valor": "818"}),
        ]),
    })

    def _fake_fetch_indices(fechas_excluir):
        return [
            {"fecha": date(2026, 2, 18), "cer": None, "mep": None, "riesgo_pais": 1200.0, "fuente": "api"},
            {"fecha": date(2026, 2, 19), "cer": 105.0, "mep": 820.0, "riesgo_pais": 1180.0, "fuente": "api"},
        ], []

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", _fake_fetch_indices)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))

    try:
        sync_from_sheet(db)

        fila_sheet = db.query(IndiceMercado).filter(IndiceMercado.fecha == date(2026, 2, 18)).one()
        assert fila_sheet.fuente == "sheet"
        assert float(fila_sheet.cer) == 103.6          # CER/MEP del Sheet intactos
        assert float(fila_sheet.mep) == 818.0
        assert float(fila_sheet.riesgo_pais) == 1200.0  # riesgo país mergeado de la API

        fila_api = db.query(IndiceMercado).filter(IndiceMercado.fecha == date(2026, 2, 19)).one()
        assert fila_api.fuente == "api"
        assert float(fila_api.riesgo_pais) == 1180.0

        # Segunda corrida: el riesgo país de la API cambia → se re-mergea, sin duplicar filas.
        def _fake_2(fechas_excluir):
            return [{"fecha": date(2026, 2, 18), "cer": None, "mep": None,
                     "riesgo_pais": 1150.0, "fuente": "api"}], []
        monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", _fake_2)
        sync_from_sheet(db)

        fila_sheet = db.query(IndiceMercado).filter(IndiceMercado.fecha == date(2026, 2, 18)).one()
        assert fila_sheet.fuente == "sheet"
        assert float(fila_sheet.cer) == 103.6
        assert float(fila_sheet.riesgo_pais) == 1150.0
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


def _tabs_con_bono_y_movimiento():
    return {
        "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[
            (2, {"Ticker": "TZXD7", "Nombre": "Boncer 2027", "Tipo Instrumento": "Bono", "Mercado": "MERVAL", "Moneda": "ARS"}),
        ]),
        "Movimientos": TabRaw(presente=True, header=["Fecha", "Cartera", "Ticker", "Tipo Movimiento", "Cantidad", "Precio", "Moneda"], rows=[
            (2, {"Fecha": "2026-06-01", "Cartera": "P1", "Ticker": "TZXD7", "Tipo Movimiento": "Compra", "Cantidad": "1000", "Precio": "2.6", "Moneda": "ARS"}),
        ]),
        "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
            (2, {"Fecha": "2026-07-27", "Ticker": "TZXD7", "Precio": "2.7135", "Moneda": "ARS"}),
        ]),
    }


def test_backfill_historico_renta_fija_normaliza_escala_y_converge(monkeypatch):
    """analisistecnico puebla la serie hacia atrás (desde el 1er movimiento); no pisa el Sheet y
    en la corrida siguiente no vuelve a pedir la serie (ya llegó al piso)."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_bono_y_movimiento())

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {})

    serie = [(date(2026, 6, 2), 265.0), (date(2026, 7, 27), 271.0), (date(2026, 7, 28), 272.5)]
    llamadas = []

    def _fake_hist(ticker, desde, hasta):
        llamadas.append(ticker)
        return serie

    monkeypatch.setattr(sync_module.market_data_precios.analisistecnico, "fetch_historico_bono", _fake_hist)

    try:
        sync_from_sheet(db)
        assert llamadas == ["TZXD7"]
        api_rows = db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").all()
        por_fecha = {r.fecha: round(float(r.precio), 4) for r in api_rows}
        # 2026-07-27 lo trae el Sheet (fuente='sheet'): la API no lo pisa.
        assert date(2026, 7, 27) not in por_fecha
        assert por_fecha == {date(2026, 6, 2): 2.65, date(2026, 7, 28): 2.725}
        sheet_row = db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "sheet").one()
        assert float(sheet_row.precio) == 2.7135

        # Segunda corrida: ya está backfilleado hasta el piso → no se vuelve a pedir la serie.
        llamadas.clear()
        sync_from_sheet(db)
        assert llamadas == []
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").count() == 2
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


def _tabs_con_accion():
    return {
        "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[
            (2, {"Ticker": "GGAL", "Nombre": "Grupo Galicia", "Tipo Instrumento": "Accion", "Mercado": "MERVAL", "Moneda": "ARS"}),
        ]),
        "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
            (2, {"Fecha": "2026-07-27", "Ticker": "GGAL", "Precio": "5100", "Moneda": "ARS"}),
        ]),
    }


def test_precio_renta_variable_api_persiste_sin_backfill(monkeypatch):
    """Ola 4: data912 arg_stocks/arg_cedears agrega el precio del día para acciones/CEDEARs."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_accion())

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {"GGAL": 5230.0})

    try:
        result = sync_from_sheet(db)
        sheet_row = db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "sheet").one()
        assert float(sheet_row.precio) == 5100.0
        api_row = db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").one()
        assert api_row.ticker == "GGAL"
        assert float(api_row.precio) == 5230.0  # ratio ~1: no se normaliza
        assert result["precios"] == 2
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_precio_renta_variable_api_caida_preserva_corrida_anterior(monkeypatch):
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_accion())

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {"GGAL": 5230.0})

    try:
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").count() == 1

        monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: None)
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").count() == 1
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_a4_fila_api_que_el_sheet_ahora_cubre_se_borra(monkeypatch):
    """Una fila 'api' para (ticker, fecha) que el Sheet empieza a cubrir no debe quedar
    conviviendo con la fila 'sheet'. La purga corre aunque USE_EXTERNAL_APIS esté apagado."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_bono())  # Sheet trae TZXD7 @ 2026-07-27
    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: False)

    try:
        db.add(PrecioInstrumento(fecha=date(2026, 7, 27), ticker="TZXD7", precio=999.0,
                                 moneda="ARS", fuente="api"))   # colisiona con el Sheet
        db.add(PrecioInstrumento(fecha=date(2026, 6, 1), ticker="TZXD7", precio=2.5,
                                 moneda="ARS", fuente="api"))    # fecha que el Sheet no cubre
        db.commit()

        sync_from_sheet(db)

        colision = db.query(PrecioInstrumento).filter(
            PrecioInstrumento.ticker == "TZXD7", PrecioInstrumento.fecha == date(2026, 7, 27)
        ).all()
        assert len(colision) == 1 and colision[0].fuente == "sheet"
        assert float(colision[0].precio) == 2.7135

        # La fila 'api' de una fecha que el Sheet no cubre sigue intacta.
        libre = db.query(PrecioInstrumento).filter(
            PrecioInstrumento.ticker == "TZXD7", PrecioInstrumento.fecha == date(2026, 6, 1)
        ).one()
        assert libre.fuente == "api"
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_purga_no_borra_filas_api_de_renta_variable_al_purgar_renta_fija(monkeypatch):
    """La purga de filas 'api' huérfanas debe considerar renta fija Y variable, no sólo una."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    tabs = _tabs_con_accion()
    tabs["Instrumentos"].rows.append(
        (3, {"Ticker": "TZXD7", "Nombre": "Boncer 2027", "Tipo Instrumento": "Bono", "Mercado": "MERVAL", "Moneda": "ARS"})
    )
    tabs["Precios"].rows.append(
        (3, {"Fecha": "2026-07-27", "Ticker": "TZXD7", "Precio": "2.7135", "Moneda": "ARS"})
    )
    sync_module.fetch_sheet_data = _mock_fetch(tabs)

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {"GGAL": 5230.0})
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})

    try:
        sync_from_sheet(db)
        api_rows = {r.ticker for r in db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "api").all()}
        assert api_rows == {"GGAL", "TZXD7"}
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


# --- IOL como fuente primaria: precedencia iol > sheet > api dentro del sync -------------------

def test_iol_desplaza_precio_manual_del_sheet_y_reporta(monkeypatch):
    """IOL cotiza la misma fecha que ya trae el Sheet: gana IOL, el Sheet queda desplazado y se
    reporta con un ValidationIssue (nunca es silencioso). El precio del día lo calcula
    `fetch_precios_api` contra `date.today()` (el sync no fija una fecha), así que la carga
    manual del Sheet tiene que ser justamente la de hoy para que colisionen."""
    hoy = date.today()
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch({
        "Instrumentos": TabRaw(presente=True, header=["Ticker", "Nombre", "Tipo Instrumento", "Mercado", "Moneda"], rows=[
            (2, {"Ticker": "TZXD7", "Nombre": "Boncer 2027", "Tipo Instrumento": "Bono", "Mercado": "MERVAL", "Moneda": "ARS"}),
        ]),
        "Precios": TabRaw(presente=True, header=["Fecha", "Ticker", "Precio", "Moneda"], rows=[
            (2, {"Fecha": hoy.isoformat(), "Ticker": "TZXD7", "Precio": "2.7135", "Moneda": "ARS"}),
        ]),
    })

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.iol_client, "fetch_precios_paneles",
                         lambda db: {"TZXD7": (2.72, "ARS")})
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {})

    try:
        result = sync_from_sheet(db)

        filas = db.query(PrecioInstrumento).filter(
            PrecioInstrumento.ticker == "TZXD7", PrecioInstrumento.fecha == hoy
        ).all()
        assert len(filas) == 1  # nunca conviven 'sheet' e 'iol' para la misma clave
        assert filas[0].fuente == "iol"
        assert float(filas[0].precio) == 2.72

        issue = db.query(SyncIssue).filter(SyncIssue.regla == "precio_manual_reemplazado_por_iol").one()
        assert "TZXD7" in issue.mensaje
        assert result["precios"] >= 1
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_iol_no_reclama_la_fecha_el_sheet_conserva(monkeypatch):
    """Si IOL no cotiza ese ticker (caído o sin ese símbolo), el Sheet sigue ganando -- ninguna
    fila 'api' de data912 puede pisar una fecha que el Sheet ya cubre."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_bono())

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.iol_client, "fetch_precios_paneles", lambda db: None)
    # data912 "cotiza" la misma fecha que ya trae el Sheet (con otro valor): no debe pisarla.
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija",
                         lambda: {"TZXD7": 999999.0})
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {})

    try:
        sync_from_sheet(db)
        filas = db.query(PrecioInstrumento).filter(
            PrecioInstrumento.ticker == "TZXD7", PrecioInstrumento.fecha == date(2026, 7, 27)
        ).all()
        assert len(filas) == 1
        assert filas[0].fuente == "sheet"
        assert float(filas[0].precio) == 2.7135

        sin_reemplazo = db.query(SyncIssue).filter(
            SyncIssue.regla == "precio_manual_reemplazado_por_iol"
        ).count()
        assert sin_reemplazo == 0
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_iol_caida_preserva_fila_iol_de_una_corrida_anterior(monkeypatch):
    """Si IOL falla en una corrida, las filas 'iol' de la corrida anterior no se pierden."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_accion())  # Sheet: GGAL @ 2026-07-27

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {})
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(sync_module.market_data_precios.iol_client, "fetch_precios_paneles",
                         lambda db: {"GGAL": (5230.0, "ARS")})

    try:
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "iol").count() == 1

        # IOL se cae (None) en la corrida siguiente -> la fila 'iol' previa no se borra, y como
        # el Sheet ya no está desplazado (claves_iol queda vacío), no reaparece una fila 'sheet'
        # duplicada: la purga de huérfanos tampoco la toca (GGAL sigue siendo Acción del Sheet).
        monkeypatch.setattr(sync_module.market_data_precios.iol_client, "fetch_precios_paneles", lambda db: None)
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.fuente == "iol").count() == 1
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()


def test_purga_orfanos_incluye_fuente_iol(monkeypatch):
    """Un ticker que ya no es renta fija/variable/FCI del Sheet no debe dejar una fila 'iol'
    huérfana para siempre. El Sheet trae otro instrumento (GGAL) con precio válido -- una pestaña
    Precios vacía dispararía el guard de "vaciamiento sospechoso" y bloquearía todo el tab."""
    db = _make_db()
    original_fetch = sync_module.fetch_sheet_data
    sync_module.fetch_sheet_data = _mock_fetch(_tabs_con_accion())  # Sheet: sólo GGAL

    monkeypatch.setattr(sync_module.market_data, "use_external_apis", lambda: True)
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_indices_mercado_api", lambda fechas_excluir: (None, []))
    monkeypatch.setattr(sync_module.market_data_indices, "fetch_benchmarks_api", lambda: (None, []))
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_fija", lambda: {})
    monkeypatch.setattr(sync_module.market_data_precios.data912, "fetch_precios_renta_variable", lambda: {})
    monkeypatch.setattr(sync_module.market_data_precios.iol_client, "fetch_precios_paneles", lambda db: None)

    try:
        db.add(PrecioInstrumento(fecha=date(2026, 6, 1), ticker="VENCIDO", precio=1.0,
                                  moneda="ARS", fuente="iol"))
        db.commit()
        sync_from_sheet(db)
        assert db.query(PrecioInstrumento).filter(PrecioInstrumento.ticker == "VENCIDO").count() == 0
    finally:
        sync_module.fetch_sheet_data = original_fetch
        db.close()
