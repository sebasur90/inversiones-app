"""Backfill de la serie **local** (ARS) desde yfinance con el sufijo `.BA`.

Para qué existe esta ruta: la serie local de un CEDEAR salía de analisistecnico o de IOL, que gasta
cupo mensual y sin cupo no devuelve nada, así que la variante `subyacente` podía mostrar cinco años
de historia y la `local` quedar vacía — el mismo instrumento visto desde otro mercado.

Sin red: se monkeypatchea `market_data.yahoo` (la autouse de conftest lo deja en None; cada test
pone su fake explícito).
"""
from datetime import date, timedelta

from backend.app.services.market_data import precios as mdp, yahoo

HOY = date(2026, 9, 1)


def _rv(ticker, tipo="CEDEAR", moneda="ARS"):
    return {"ticker": ticker, "nombre": ticker, "tipo_instrumento": tipo, "moneda": moneda}


def _ref(ticker, precio, fecha=None, moneda="ARS"):
    return {"ticker": ticker, "fecha": fecha or (HOY - timedelta(days=1)),
            "precio": precio, "moneda": moneda}


def _serie(desde, hasta, precio=1000.0):
    """Barras diarias (lun-vie) con cierre constante, para que el factor contra la referencia sea
    exactamente 1."""
    out = []
    d = desde
    while d <= hasta:
        if d.weekday() < 5:
            out.append(mdp.BarraCruda(fecha=d, cierre=precio, apertura=precio * 0.99,
                                      maximo=precio * 1.01, minimo=precio * 0.98, volumen=500.0))
        d += timedelta(days=1)
    return out


def _fake_serie(mapa):
    return lambda simbolo, desde, hasta: mapa.get(simbolo)


# ── camino feliz ─────────────────────────────────────────────────────────────

def test_carga_velas_del_simbolo_local_con_sufijo_ba(monkeypatch):
    piso = HOY - mdp._PISO_LOCAL_YAHOO
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fake_serie({
        "AAPL.BA": _serie(piso, HOY - timedelta(days=1), 1000.0),
    }))
    estado: dict = {}
    filas, issues = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker=estado, hoy=HOY,
    )

    assert filas, "tendría que haber bajado velas locales"
    assert {f["ticker"] for f in filas} == {"AAPL"}  # la clave local, no `AAPL@SUB`
    assert {f["fuente"] for f in filas} == {"yahoo"}
    assert {f["moneda"] for f in filas} == {"ARS"}
    # Velas completas, no close-only: es lo que distingue esta fuente del espejo del precio del día.
    assert all(f["apertura"] is not None and f["maximo"] is not None for f in filas)
    assert estado["AAPL"]["yahoo_local_estado"] == "completo"
    assert issues == []


def test_no_emite_barras_de_hoy(monkeypatch):
    """La rueda en curso no se persiste como vela: la cierra el espejo del precio del día."""
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fake_serie({
        "AAPL.BA": _serie(HOY - timedelta(days=30), HOY, 1000.0),
    }))
    filas, _ = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker={}, hoy=HOY,
    )
    assert filas and all(f["fecha"] < HOY for f in filas)


def test_pide_cinco_anios_hacia_atras(monkeypatch):
    """El piso es más profundo que el de analisistecnico/IOL (2 años): yfinance trae todo el rango
    en una sola llamada, así que la profundidad extra no cuesta nada."""
    pedidos: list[tuple] = []

    def fake(simbolo, desde, hasta):
        pedidos.append((simbolo, desde, hasta))
        return _serie(desde, hasta, 1000.0)

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", fake)
    mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker={}, hoy=HOY,
    )
    simbolo, desde, _ = pedidos[0]
    assert simbolo == "AAPL.BA"
    assert (HOY - desde).days >= 365 * 4  # ~5 años


# ── guardas ──────────────────────────────────────────────────────────────────

def test_descarta_la_serie_si_la_escala_no_concuerda(monkeypatch):
    """El `.BA` cotiza por unidad igual que IOL. Si el ratio contra el precio observado no es ~1,
    el símbolo no es el que se cree (serie en USD, otro instrumento) y no se carga nada: una serie
    en otra unidad que la pantalla es peor que no tener serie."""
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fake_serie({
        "AAPL.BA": _serie(HOY - timedelta(days=400), HOY - timedelta(days=1), 230.0),
    }))
    estado: dict = {}
    filas, issues = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 27000.0)], {}, estado_por_ticker=estado, hoy=HOY,
    )
    assert filas == []
    assert estado["AAPL"]["yahoo_local_estado"] == "escala_desconocida"
    assert any(i.regla == "escala_desconocida" for i in issues)


def test_no_reusa_ni_persiste_el_factor_de_la_ruta_live(monkeypatch):
    """El 1/100 de la lámina de renta fija no aplica acá, y el `factor_escala` calibrado contra
    IOL/data912 no se toca: pisarlo rompería la calibración de la ruta de cotización."""
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fake_serie({
        "AAPL.BA": _serie(HOY - timedelta(days=400), HOY - timedelta(days=1), 100000.0),
    }))
    estado = {"AAPL": {"factor_escala": 0.01, "factor_fecha": HOY - timedelta(days=10)}}
    filas, _ = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker=estado, hoy=HOY,
    )
    assert filas == []                                  # ratio 100 -> no es ~1, se descarta
    assert estado["AAPL"]["factor_escala"] == 0.01       # intacto


def test_sin_precio_observado_no_carga(monkeypatch):
    """Sin referencia no hay con qué validar la unidad de la serie."""
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fake_serie({
        "AAPL.BA": _serie(HOY - timedelta(days=400), HOY - timedelta(days=1), 1000.0),
    }))
    filas, issues = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [], {}, estado_por_ticker={}, hoy=HOY,
    )
    assert filas == []
    assert not any(i.severidad.name == "ADVERTENCIA" for i in issues)


def test_solo_renta_variable(monkeypatch):
    """Para la renta fija local la correspondencia de símbolos en Yahoo no es confiable, y
    analisistecnico ya la cubre."""
    llamadas: list[str] = []

    def fake(simbolo, desde, hasta):
        llamadas.append(simbolo)
        return _serie(desde, hasta, 1000.0)

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", fake)
    filas, _ = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AL30", tipo="Bono"), _rv("YMCHO", tipo="ON")],
        [_ref("AL30", 1000.0), _ref("YMCHO", 1000.0)], {}, estado_por_ticker={}, hoy=HOY,
    )
    assert llamadas == []
    assert filas == []


def test_sin_serie_en_yahoo_avisa_una_vez_y_respeta_el_cooldown(monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", lambda *a, **k: None)
    estado: dict = {}

    filas, issues = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("NOEXISTE")], [_ref("NOEXISTE", 100.0)], {}, estado_por_ticker=estado, hoy=HOY,
    )
    assert filas == []
    assert estado["NOEXISTE"]["yahoo_local_estado"] == "sin_serie"
    assert [i.regla for i in issues] == ["sin_historico_local_yahoo"]

    # Al día siguiente no se vuelve a pedir ni se repite el aviso.
    llamadas: list[str] = []
    monkeypatch.setattr(
        yahoo, "fetch_historico_ohlcv",
        lambda s, d, h: llamadas.append(s) or None,
    )
    _, issues2 = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("NOEXISTE")], [_ref("NOEXISTE", 100.0)], {}, estado_por_ticker=estado,
        hoy=HOY + timedelta(days=1),
    )
    assert llamadas == []
    assert issues2 == []


def test_reintenta_pasado_el_cooldown(monkeypatch):
    estado = {"AAPL": {"yahoo_local_estado": "sin_serie",
                       "yahoo_local_intento": HOY - timedelta(days=mdp._REINTENTO_YAHOO_LOCAL_DIAS + 1)}}
    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", _fake_serie({
        "AAPL.BA": _serie(HOY - timedelta(days=400), HOY - timedelta(days=1), 1000.0),
    }))
    filas, _ = mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker=estado, hoy=HOY,
    )
    assert filas
    assert estado["AAPL"]["yahoo_local_estado"] != "sin_serie"


def test_completo_no_vuelve_a_pedir(monkeypatch):
    llamadas: list[str] = []
    monkeypatch.setattr(
        yahoo, "fetch_historico_ohlcv", lambda s, d, h: llamadas.append(s) or None,
    )
    estado = {"AAPL": {"yahoo_local_estado": "completo"}}
    mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker=estado, hoy=HOY,
    )
    assert llamadas == []


def test_salta_el_ticker_cuya_serie_ya_cubre_el_piso(monkeypatch):
    llamadas: list[str] = []
    monkeypatch.setattr(
        yahoo, "fetch_historico_ohlcv", lambda s, d, h: llamadas.append(s) or None,
    )
    ya_cubierto = {"AAPL": HOY - mdp._PISO_LOCAL_YAHOO}
    mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL")], [_ref("AAPL", 1000.0)], ya_cubierto, estado_por_ticker={}, hoy=HOY,
    )
    assert llamadas == []


def test_un_ticker_en_cartera_y_en_watchlist_se_pide_una_sola_vez(monkeypatch):
    llamadas: list[str] = []

    def fake(simbolo, desde, hasta):
        llamadas.append(simbolo)
        return _serie(desde, hasta, 1000.0)

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", fake)
    mdp.fetch_backfill_ohlcv_local_yahoo(
        [_rv("AAPL"), _rv("AAPL")], [_ref("AAPL", 1000.0)], {}, estado_por_ticker={}, hoy=HOY,
    )
    assert llamadas == ["AAPL.BA"]


def test_cota_de_llamadas_por_corrida(monkeypatch):
    llamadas: list[str] = []

    def fake(simbolo, desde, hasta):
        llamadas.append(simbolo)
        return _serie(desde, hasta, 1000.0)

    monkeypatch.setattr(yahoo, "fetch_historico_ohlcv", fake)
    n = mdp._MAX_BACKFILL_LOCAL_YAHOO_POR_SYNC + 5
    activos = [_rv(f"T{i}") for i in range(n)]
    refs = [_ref(f"T{i}", 1000.0) for i in range(n)]
    mdp.fetch_backfill_ohlcv_local_yahoo(activos, refs, {}, estado_por_ticker={}, hoy=HOY)
    assert len(llamadas) == mdp._MAX_BACKFILL_LOCAL_YAHOO_POR_SYNC
