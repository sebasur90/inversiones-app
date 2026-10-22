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
    """Una acción local sin subyacente casi siempre es un no definitivo: se espera medio año."""
    def _boom(_t):
        raise AssertionError("dentro del cooldown no debería reintentar")

    monkeypatch.setattr(yahoo, "fetch_info", _boom)
    estado = {"TXAR": {"resolucion_estado": "sin_subyacente",
                       "resolucion_intento": HOY - timedelta(days=90)}}
    mdp.resolver_subyacente([_rv("TXAR", "Ternium Argentina", tipo="Accion")], estado, hoy=HOY)


def test_sin_subyacente_reintenta_pasados_180d(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "YPF": {"moneda": "USD", "mercado": "NYQ", "nombre": "YPF Sociedad Anonima"},
    }))
    estado = {"YPF": {"resolucion_estado": "sin_subyacente",
                      "resolucion_intento": HOY - timedelta(days=200)}}
    mdp.resolver_subyacente([_rv("YPF", "YPF S.A.", tipo="Accion")], estado, hoy=HOY)
    assert estado["YPF"]["resolucion_estado"] == "ok"


def test_cedear_sin_subyacente_se_reintenta_a_los_pocos_dias(monkeypatch):
    """Para un CEDEAR un `fetch_info` vacío es un fallo pasajero de Yahoo (el ticker *es* el del
    subyacente): no puede dejarlo en pesos medio año."""
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "XLP": {"moneda": "USD", "mercado": "PCX", "nombre": "Consumer Staples Select Sector SPDR"},
    }))
    estado = {"XLP": {"resolucion_estado": "sin_subyacente",
                      "resolucion_intento": HOY - timedelta(days=mdp._REINTENTO_RESOLUCION_CEDEAR_DIAS)}}
    mdp.resolver_subyacente([_rv("XLP", "Cedear Consumer Staples")], estado, hoy=HOY)
    assert estado["XLP"]["resolucion_estado"] == "ok"


def test_cedear_sin_subyacente_respeta_su_cooldown_corto(monkeypatch):
    def _boom(_t):
        raise AssertionError("dentro del cooldown no debería reintentar")

    monkeypatch.setattr(yahoo, "fetch_info", _boom)
    estado = {"XLP": {"resolucion_estado": "sin_subyacente", "resolucion_intento": HOY}}
    mdp.resolver_subyacente([_rv("XLP", "Cedear Consumer Staples")], estado, hoy=HOY)


def test_cedear_sin_respuesta_avisa_el_plazo_corto(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_info", _info({}))
    estado: dict = {}
    issues = mdp.resolver_subyacente([_rv("SMH", "Cedear Van Eck Vectors")], estado, hoy=HOY)
    assert estado["SMH"]["resolucion_estado"] == "sin_subyacente"
    (issue,) = [i for i in issues if i.regla == "subyacente_no_resuelto"]
    assert f"~{mdp._REINTENTO_RESOLUCION_CEDEAR_DIAS} días" in issue.impacto


def test_tipo_etf_se_resuelve_como_cedear(monkeypatch):
    """Un tipo "ETF" (de un Sheet o una watchlist vieja) es renta variable y se acepta sin match de
    nombre: en BYMA un ETF del exterior sólo se opera como CEDEAR."""
    monkeypatch.setattr(yahoo, "fetch_info", _info({
        "SMH": {"moneda": "USD", "mercado": "NMS", "nombre": "VanEck Semiconductor ETF"},
    }))
    estado: dict = {}
    mdp.resolver_subyacente([_rv("SMH", "Van Eck Vectors Etf Tru", tipo="ETF")], estado, hoy=HOY)
    assert estado["SMH"]["resolucion_estado"] == "ok"


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


def _estado_msft():
    return {"MSFT": {"resolucion_estado": "ok", "simbolo_subyacente": "MSFT", "moneda_subyacente": "USD"}}


def test_backfill_cola_a_un_dia_de_la_ultima_rueda_se_refresca_y_pide_solo_la_cola(monkeypatch):
    # Hoy jueves 22: la última rueda es el miércoles 21 y la serie llega al martes 20. Antes se
    # consideraba "fresca" (tolerancia de 3 días) y la vela del 21 no entraba nunca.
    hoy = date(2026, 10, 22)
    pedidos = []

    def _fetch(sym, desde, hasta):
        pedidos.append((desde, hasta))
        return [_bc(date(2026, 10, 19), 300.0), _bc(date(2026, 10, 20), 301.0), _bc(date(2026, 10, 21), 302.0)]

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fetch)
    piso = hoy - mdp._PISO_SUBYACENTE
    filas, _ = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {"MSFT@SUB": piso + timedelta(days=5)},
        {"MSFT@SUB": date(2026, 10, 20)}, _estado_msft(), hoy=hoy,
    )
    assert pedidos == [(date(2026, 10, 15), date(2026, 10, 21))]    # no los 5 años
    assert date(2026, 10, 21) in {f["fecha"] for f in filas}


def test_backfill_lunes_con_viernes_guardado_no_vuelve_a_pedir(monkeypatch):
    # Lunes 26: "ayer" es domingo, pero la última rueda es el viernes 23, que ya está guardado.
    def _boom(*a, **k):
        raise AssertionError("la serie ya llega a la última rueda hábil")

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _boom)
    hoy = date(2026, 10, 26)
    piso = hoy - mdp._PISO_SUBYACENTE
    filas, issues = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {"MSFT@SUB": piso + timedelta(days=5)},
        {"MSFT@SUB": date(2026, 10, 23)}, _estado_msft(), hoy=hoy,
    )
    assert filas == [] and issues == []


def test_backfill_cola_con_una_sola_barra_nueva_se_acepta(monkeypatch):
    hoy = date(2026, 10, 22)
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", lambda *a, **k: [_bc(date(2026, 10, 21), 302.0)])
    piso = hoy - mdp._PISO_SUBYACENTE
    filas, _ = mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {"MSFT@SUB": piso + timedelta(days=5)},
        {"MSFT@SUB": date(2026, 10, 20)}, _estado_msft(), hoy=hoy,
    )
    assert [f["fecha"] for f in filas] == [date(2026, 10, 21)]


def test_backfill_solo_falta_historia_pide_hasta_la_barra_mas_vieja(monkeypatch):
    hoy = date(2026, 10, 22)
    pedidos = []
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv",
                        lambda sym, d, h: pedidos.append((d, h)) or [_bc(d, 100.0), _bc(h, 101.0)])
    piso = hoy - mdp._PISO_SUBYACENTE
    mdp.fetch_backfill_ohlcv_subyacente(
        [_rv("MSFT", "Microsoft")], {"MSFT@SUB": date(2024, 1, 2)},
        {"MSFT@SUB": date(2026, 10, 21)}, _estado_msft(), hoy=hoy,
    )
    assert pedidos == [(piso, date(2024, 1, 2))]


def test_backfill_sin_datos_pide_la_historia_completa(monkeypatch):
    hoy = date(2026, 10, 22)
    pedidos = []
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv",
                        lambda sym, d, h: pedidos.append((d, h)) or [_bc(d, 100.0), _bc(h, 101.0)])
    mdp.fetch_backfill_ohlcv_subyacente([_rv("MSFT", "Microsoft")], {}, {}, _estado_msft(), hoy=hoy)
    assert pedidos == [(hoy - mdp._PISO_SUBYACENTE, date(2026, 10, 21))]
