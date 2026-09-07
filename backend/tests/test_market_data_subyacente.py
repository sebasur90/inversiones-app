"""Resolución del subyacente (yfinance) y backfill de la serie `TICKER@SUB` en USD.

Sin red: se monkeypatchea `market_data.yahoo` (la autouse de conftest lo deja stubeado en None;
cada test lo reemplaza por un fake explícito)."""
from datetime import date, timedelta

from backend.app.services.market_data import precios as mdp, yahoo

HOY = date(2026, 9, 1)


def _rv(ticker, nombre, tipo="CEDEAR", moneda="ARS"):
    return {"ticker": ticker, "nombre": nombre, "tipo_instrumento": tipo, "moneda": moneda}


def _info(mapa):
    return lambda t: mapa.get(t)


def _bc(f, c):
    return mdp.BarraCruda(fecha=f, cierre=c, apertura=c * 0.99, maximo=c * 1.01, minimo=c * 0.98,
                          volumen=1000.0)


# ── resolver_subyacente ──────────────────────────────────────────────────────

def test_resuelve_cedear_con_moneda_usd(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "MSFT": {"moneda": "USD", "mercado": "NMS", "nombre": "Microsoft Corporation"},
    }))
    estado: dict = {}
    issues = mdp.resolver_subyacente([_rv("MSFT", "Microsoft")], estado, hoy=HOY)
    assert estado["MSFT"]["resolucion_estado"] == "ok"
    assert estado["MSFT"]["simbolo_subyacente"] == "MSFT"
    assert estado["MSFT"]["moneda_subyacente"] == "USD"
    assert estado["MSFT"]["mercado_subyacente"] == "NMS"
    assert issues == []


def test_g1_rechaza_subyacente_no_usd(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "GGAL": {"moneda": "ARS", "mercado": "BUE", "nombre": "Grupo Financiero Galicia"},
    }))
    estado: dict = {}
    issues = mdp.resolver_subyacente([_rv("GGAL", "Grupo Galicia", tipo="Accion")], estado, hoy=HOY)
    assert estado["GGAL"]["resolucion_estado"] == "sin_subyacente"
    assert any(i.regla == "subyacente_no_usd" for i in issues)


def test_accion_local_sin_match_de_nombre_no_se_acepta(monkeypatch):
    """El ticker pelado de una acción local puede resolver a otra empresa en Yahoo."""
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "TXAR": {"moneda": "USD", "mercado": "NMS", "nombre": "Texas Roadhouse Inc"},
    }))
    estado: dict = {}
    issues = mdp.resolver_subyacente(
        [{"ticker": "TXAR", "nombre": "Ternium Argentina", "tipo_instrumento": "Accion", "moneda": "ARS"}],
        estado, hoy=HOY,
    )
    assert estado["TXAR"]["resolucion_estado"] == "sin_subyacente"
    assert any(i.regla == "subyacente_nombre_no_matchea" for i in issues)


def test_accion_local_con_match_de_nombre_se_acepta(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "YPF": {"moneda": "USD", "mercado": "NYQ", "nombre": "YPF Sociedad Anonima"},
    }))
    estado: dict = {}
    mdp.resolver_subyacente(
        [{"ticker": "YPF", "nombre": "YPF S.A.", "tipo_instrumento": "Accion", "moneda": "USD"}],
        estado, hoy=HOY,
    )
    assert estado["YPF"]["resolucion_estado"] == "ok"
    assert estado["YPF"]["simbolo_subyacente"] == "YPF"


def test_no_re_resuelve_si_ya_esta_ok(monkeypatch):
    def _boom(_t):
        raise AssertionError("no debería re-resolver un ticker ya 'ok'")

    monkeypatch.setattr(yahoo, "fetch_info", _boom)
    estado = {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT",
                       "moneda_subyacente": "USD"}}
    assert mdp.resolver_subyacente([_rv("MSFT", "Microsoft")], estado, hoy=HOY) == []


def test_sin_subyacente_respeta_cooldown_180d(monkeypatch):
    def _boom(_t):
        raise AssertionError("dentro del cooldown no debería reintentar")

    monkeypatch.setattr(yahoo, "fetch_info", _boom)
    estado = {"MSFT": {"resolucion_estado": "sin_subyacente",
                       "resolucion_intento": HOY - timedelta(days=90)}}
    mdp.resolver_subyacente([_rv("MSFT", "Microsoft")], estado, hoy=HOY)  # no explota


def test_sin_subyacente_reintenta_pasados_180d(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "MSFT": {"moneda": "USD", "mercado": "NMS", "nombre": "Microsoft Corporation"},
    }))
    estado = {"MSFT": {"resolucion_estado": "sin_subyacente",
                       "resolucion_intento": HOY - timedelta(days=200)}}
    mdp.resolver_subyacente([_rv("MSFT", "Microsoft")], estado, hoy=HOY)
    assert estado["MSFT"]["resolucion_estado"] == "ok"


def test_renta_fija_no_se_toca(monkeypatch):
    def _boom(_t):
        raise AssertionError("resolver_subyacente sólo mira renta variable")

    monkeypatch.setattr(yahoo, "fetch_info", _boom)
    estado: dict = {}
    mdp.resolver_subyacente([_rv("AL30", "Bono", tipo="Bono")], estado, hoy=HOY)
    assert "AL30" not in estado or estado["AL30"].get("resolucion_estado") is None


def test_cota_de_resoluciones_por_corrida(monkeypatch):
    llamadas = []
    monkeypatch.setattr(yahoo, "fetch_info", lambda t: (llamadas.append(t) or
                                                        {"moneda": "USD", "mercado": "NMS", "nombre": t}))
    activos = [_rv(f"T{i}", f"T{i}") for i in range(15)]
    mdp.resolver_subyacente(activos, {}, hoy=HOY, max_resoluciones=10)
    assert len(llamadas) == 10


# ── fetch_backfill_ohlcv_subyacente ──────────────────────────────────────────

def test_backfill_emite_sub_en_usd_con_precios_verbatim(monkeypatch):
    serie = [_bc(date(2026, 8, 28), 499.70), _bc(date(2026, 8, 29), 505.0)]
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv",
                        lambda sym, d, h: serie if sym == "MSFT" else None)
    # Aunque haya un factor_escala persistido, NO se aplica al subyacente.
    estado = {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT",
                       "moneda_subyacente": "USD", "factor_escala": 0.01, "factor_fecha": HOY}}

    filas, issues = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {}, {}, estado, hoy=HOY,
    )
    assert {f["ticker"] for f in filas} == {"MSFT@SUB"}
    assert all(f["moneda"] == "USD" and f["fuente"] == "yahoo" for f in filas)
    assert filas[0]["cierre"] == 499.70          # verbatim, sin factor 0.01
    assert filas[0]["apertura"] is not None      # o/h/l pasan tal cual de yfinance


def test_backfill_ignora_tickers_no_resueltos(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("no se baja serie de un ticker sin resolver")

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _boom)
    filas, issues = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {}, {},
        {"MSFT": {"resolucion_estado": "sin_subyacente"}}, hoy=HOY,
    )
    assert filas == []


def test_backfill_serie_none_emite_issue(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", lambda *a, **k: None)
    estado = {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT",
                       "moneda_subyacente": "USD"}}
    filas, issues = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {}, {}, estado, hoy=HOY,
    )
    assert filas == []
    assert issues[0].regla == "subyacente_sin_serie"


def test_backfill_serie_de_una_barra_no_emite(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", lambda *a, **k: [_bc(date(2026, 8, 28), 499.7)])
    estado = {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT",
                       "moneda_subyacente": "USD"}}
    filas, issues = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {}, {}, estado, hoy=HOY,
    )
    assert filas == []


def test_backfill_convergido_y_fresco_no_vuelve_a_pedir(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("ya está backfilleado hasta el piso y con la cola fresca")

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _boom)
    estado = {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT",
                       "moneda_subyacente": "USD"}}
    piso = HOY - mdp._PISO_SUBYACENTE
    ohlcv_existentes = {"MSFT@SUB": piso + timedelta(days=5)}
    ohlcv_maximos = {"MSFT@SUB": HOY - timedelta(days=1)}
    filas, issues = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], ohlcv_existentes, ohlcv_maximos, estado, hoy=HOY,
    )
    assert filas == [] and issues == []


def test_backfill_cola_stale_se_refresca(monkeypatch):
    serie = [_bc(HOY - timedelta(days=2), 500.0), _bc(HOY - timedelta(days=1), 501.0)]
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", lambda *a, **k: serie)
    estado = {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT",
                       "moneda_subyacente": "USD"}}
    piso = HOY - mdp._PISO_SUBYACENTE
    ohlcv_existentes = {"MSFT@SUB": piso + timedelta(days=5)}
    ohlcv_maximos = {"MSFT@SUB": HOY - timedelta(days=30)}   # cola vieja
    filas, _ = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], ohlcv_existentes, ohlcv_maximos, estado, hoy=HOY,
    )
    assert [f["fecha"] for f in filas] == [HOY - timedelta(days=2), HOY - timedelta(days=1)]
