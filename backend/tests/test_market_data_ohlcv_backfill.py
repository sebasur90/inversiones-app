"""Tests del backfill de OHLCV: aplicación del factor de escala, precedencia de `serie_ohlcv`,
backfill de velas de la watchlist y la "regla de primer llenado" del backfill de cartera."""
from datetime import date, timedelta

import pytest

from backend.app.services.market_data import analisistecnico, precios as mdp
from backend.app.services import ohlcv_analytics as oa

HOY = date(2026, 8, 28)


def _inst(ticker, tipo="Bono", moneda="ARS"):
    return {"ticker": ticker, "tipo_instrumento": tipo, "moneda": moneda}


def _px(ticker, precio, fecha=date(2026, 7, 27)):
    return {"ticker": ticker, "fecha": fecha, "precio": precio, "moneda": "ARS"}


def _wl(ticker, objetivo=None, moneda="ARS"):
    return {"ticker": ticker, "moneda": moneda, "objetivo": objetivo}


def _serie(*pares):
    return [analisistecnico.BarraCruda(fecha=f, cierre=px, apertura=px, maximo=px, minimo=px) for f, px in pares]


# ── _aplicar_factor_ohlcv: escala o/h/l/c, no el volumen ──────────────────────

def test_aplicar_factor_escala_ohlc_y_preserva_volumen():
    barra = analisistecnico.BarraCruda(
        fecha=date(2026, 1, 1), cierre=272.5, apertura=270.0, maximo=275.0, minimo=268.0, volumen=1000.0,
    )
    escalada = mdp._aplicar_factor_ohlcv(barra, 0.01)
    assert escalada.cierre == pytest.approx(2.725)
    assert escalada.apertura == pytest.approx(2.70)
    assert escalada.maximo == pytest.approx(2.75)
    assert escalada.minimo == pytest.approx(2.68)
    assert escalada.volumen == 1000.0  # nominal, nunca escalado


def test_aplicar_factor_preserva_invariante_minimo_cierre_maximo():
    barra = analisistecnico.BarraCruda(fecha=date(2026, 1, 1), cierre=100.0, apertura=98.0, maximo=105.0, minimo=95.0)
    escalada = mdp._aplicar_factor_ohlcv(barra, 0.01)
    assert escalada.minimo <= escalada.cierre <= escalada.maximo
    assert escalada.minimo <= escalada.apertura <= escalada.maximo


def test_aplicar_factor_con_ohlc_ausente_no_falla():
    barra = analisistecnico.BarraCruda(fecha=date(2026, 1, 1), cierre=100.0)
    escalada = mdp._aplicar_factor_ohlcv(barra, 0.01)
    assert escalada.apertura is None and escalada.maximo is None and escalada.minimo is None
    assert escalada.cierre == pytest.approx(1.0)


# ── debe_reemplazar_barra: los cuatro casos de precedencia ────────────────────

def test_precedencia_sin_existente_siempre_reemplaza():
    assert oa.debe_reemplazar_barra(None, {"fuente": "api", "tiene_velas": False}) is True


def test_precedencia_iol_pisa_a_api():
    existente = {"fuente": "api", "tiene_velas": True}
    nueva = {"fuente": "iol", "tiene_velas": False}
    assert oa.debe_reemplazar_barra(existente, nueva) is True


def test_precedencia_api_nunca_pisa_a_iol():
    existente = {"fuente": "iol", "tiene_velas": False}
    nueva = {"fuente": "api", "tiene_velas": True}
    assert oa.debe_reemplazar_barra(existente, nueva) is False


def test_precedencia_misma_fuente_velas_pisa_close_only():
    existente = {"fuente": "api", "tiene_velas": False}
    nueva = {"fuente": "api", "tiene_velas": True}
    assert oa.debe_reemplazar_barra(existente, nueva) is True


def test_precedencia_misma_fuente_close_only_nunca_pisa_velas():
    existente = {"fuente": "api", "tiene_velas": True}
    nueva = {"fuente": "api", "tiene_velas": False}
    assert oa.debe_reemplazar_barra(existente, nueva) is False


# ── fetch_backfill_ohlcv_watchlist ────────────────────────────────────────────

def test_watchlist_ohlcv_referencia_sintetica_del_objetivo(monkeypatch):
    serie = _serie((date(2026, 1, 1), 270.0), (date(2026, 1, 2), 271.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)

    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL", objetivo=2.70)], [], {}, object(), hoy=HOY,
    )
    assert issues == []
    assert len(filas) == 2
    assert all(f["fuente"] == "api" for f in filas)
    # factor ~0.01 (270 vs objetivo 2.70)
    assert round(filas[0]["cierre"], 4) == 2.70


def test_watchlist_ohlcv_precio_manual_gana_sobre_el_objetivo(monkeypatch):
    serie = _serie((date(2026, 1, 1), 270.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)

    # Objetivo mal cargado (escala rota) pero hay un precio manual real y consistente.
    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL", objetivo=99999.0)],
        [_px("GGAL", 2.70, fecha=date(2025, 12, 1))],
        {}, object(), hoy=HOY,
    )
    assert issues == []
    assert round(filas[0]["cierre"], 4) == 2.70


def test_watchlist_ohlcv_escala_desconocida_advierte(monkeypatch):
    serie = _serie((date(2026, 1, 1), 270.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)

    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL", objetivo=7.0)], [], {}, object(), hoy=HOY,  # ratio ~38.6, fuera de ventana
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert issues[0].tab == "Watchlist (OHLCV)"


def test_watchlist_ohlcv_reusa_factor_persistido_sin_recalibrar(monkeypatch):
    """A1: con un factor ya persistido y una referencia manual más vieja que `factor_fecha`, se
    reusa el factor guardado y NO se re-persiste la calibración (la referencia sintética del
    Objetivo se fecha en `hoy`, así que recalibrar movería `factor_fecha` en cada sync)."""
    serie = _serie((date(2026, 1, 1), 270.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)
    estado = {"GGAL": {"factor_escala": 0.01, "factor_fecha": date(2020, 1, 1)}}

    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL")], [_px("GGAL", 2.70, fecha=date(2019, 6, 1))],
        {}, object(), hoy=HOY, estado_por_ticker=estado,
    )
    assert issues == []
    assert round(filas[0]["cierre"], 4) == 2.70
    assert estado["GGAL"]["factor_fecha"] == date(2020, 1, 1)   # intacta: no se recalibró


def test_watchlist_ohlcv_cota_de_cupo_iol(monkeypatch):
    """analisistecnico siempre falla (None): cada ticker consume una llamada a IOL, cotizada."""
    n = mdp._MAX_BACKFILL_OHLCV_POR_SYNC + 2
    watchlist = [_wl(f"W{i}", objetivo=2.70) for i in range(n)]
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: None)
    llamadas_iol = []

    def _fake_iol(db, t, d, h):
        llamadas_iol.append(t)
        return _serie((date(2026, 1, 1), 270.0))

    import backend.app.services.market_data.iol as iol_mod
    monkeypatch.setattr(iol_mod, "fetch_historico_ohlcv", _fake_iol)

    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(watchlist, [], {}, object(), hoy=HOY)
    assert len(llamadas_iol) == mdp._MAX_BACKFILL_OHLCV_POR_SYNC


def test_watchlist_ohlcv_sin_ninguna_fuente_marca_sin_serie_iol(monkeypatch):
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: None)
    import backend.app.services.market_data.iol as iol_mod
    monkeypatch.setattr(iol_mod, "fetch_historico_ohlcv", lambda db, t, d, h: None)

    estado: dict = {}
    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL", objetivo=2.70)], [], {}, object(), hoy=HOY, estado_por_ticker=estado,
    )
    assert filas == []
    assert issues[0].regla == "sin_historico_ohlcv"
    assert estado["GGAL"]["ohlcv_estado"] == "sin_serie_iol"
    assert estado["GGAL"]["ohlcv_intento"] == HOY


def test_watchlist_ohlcv_converge_no_vuelve_a_pedir(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("ya está backfilleado hasta el piso")

    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", _boom)
    piso = HOY - mdp._PISO_TECNICO
    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL", objetivo=2.70)], [], {"GGAL": piso + timedelta(days=5)}, object(), hoy=HOY,
    )
    assert filas == [] and issues == []


def test_watchlist_ohlcv_marca_completo_cuando_ya_no_baja_mas(monkeypatch):
    piso = HOY - mdp._PISO_TECNICO
    ya = piso + timedelta(days=100)   # hueco > tolerancia (40d): sí se pide la serie
    serie = _serie((ya, 270.0))       # pero la fuente no da más historia que la que ya había
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)

    estado: dict = {}
    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("GGAL", objetivo=2.70)], [], {"GGAL": ya}, object(),
        hoy=HOY, estado_por_ticker=estado,
    )
    assert filas
    assert estado["GGAL"]["ohlcv_estado"] == "completo"


# ── Regla de primer llenado (fetch_backfill_renta_fija_api con barras_out) ────

def test_regla_de_primer_llenado_repide_ticker_ya_completo_sin_ohlcv(monkeypatch):
    serie = _serie((date(2025, 6, 2), 270.0), (date(2025, 6, 3), 272.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)

    # backfill_estado ya convergió antes de que existiera la feature OHLCV: sin esto, jamás se
    # pedirían velas para este ticker.
    estado = {"TZXD7": {"factor_escala": None, "factor_fecha": None, "backfill_estado": "completo"}}
    barras_out: list[dict] = []
    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        set(), {"TZXD7": date(2025, 6, 1)}, {"TZXD7": date(2025, 6, 1)},
        hoy=HOY, estado_por_ticker=estado,
        ohlcv_existentes={}, barras_out=barras_out,
    )
    assert len(barras_out) == 2
    assert estado["TZXD7"]["ohlcv_intento"] == HOY
    # backfill_estado (valuación) no se toca por la regla de primer llenado
    assert estado["TZXD7"]["backfill_estado"] == "completo"


def test_regla_de_primer_llenado_no_repide_si_ya_tiene_ohlcv(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("ya tiene barras OHLCV, no debería volver a pedir la serie")

    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", _boom)
    estado = {"TZXD7": {"factor_escala": None, "factor_fecha": None, "backfill_estado": "completo"}}
    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        set(), {"TZXD7": date(2025, 6, 1)}, {"TZXD7": date(2025, 6, 1)},
        hoy=HOY, estado_por_ticker=estado,
        ohlcv_existentes={"TZXD7": date(2025, 6, 1)}, barras_out=[],
    )
    assert filas == []


def test_regla_de_primer_llenado_gateada_por_ohlcv_intento(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("no debería reintentar antes de los 90 días")

    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", _boom)
    estado = {"TZXD7": {"factor_escala": None, "factor_fecha": None, "backfill_estado": "completo",
                        "ohlcv_intento": HOY - timedelta(days=5)}}
    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        set(), {"TZXD7": date(2025, 6, 1)}, {"TZXD7": date(2025, 6, 1)},
        hoy=HOY, estado_por_ticker=estado,
        ohlcv_existentes={}, barras_out=[],
    )
    assert filas == []


def test_sin_barras_out_comportamiento_identico_al_original(monkeypatch):
    """`barras_out=None` (default) preserva el comportamiento anterior a OHLCV bit a bit."""
    serie = _serie((date(2025, 6, 2), 270.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)

    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        set(), {"TZXD7": date(2025, 6, 1)}, {}, hoy=HOY,
    )
    assert issues == []
    assert len(filas) == 1
    assert filas[0]["fecha"] == date(2025, 6, 2)


def test_watchlist_ohlcv_factor_persistido_no_se_aplica_a_una_serie_en_otra_unidad(monkeypatch):
    """Caso real (AMZN): IOL cotiza el CEDEAR en ARS (~2857) y persiste factor 1.0, pero
    analisistecnico resuelve el mismo símbolo a la acción en USD (~258). Reusar el factor
    persistido a ciegas cargaría velas ~11x más chicas que el precio de la tarjeta: se rechaza."""
    serie = _serie((date(2026, 1, 1), 258.51))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)
    estado = {"AMZN": {"factor_escala": 1.0, "factor_fecha": HOY}}

    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("AMZN", objetivo=2900.0)], [], {}, object(), hoy=HOY, estado_por_ticker=estado,
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert issues[0].tab == "Watchlist (OHLCV)"


def test_watchlist_ohlcv_factor_persistido_se_aplica_si_la_serie_concuerda(monkeypatch):
    """Contracara del test anterior: si la fuente de velas está en la misma escala que la
    cotización live, el factor persistido se reusa (no se recalibra contra una referencia nueva)."""
    serie = _serie((date(2026, 1, 1), 2850.0))
    monkeypatch.setattr(analisistecnico, "fetch_historico_ohlcv", lambda t, d, h: serie)
    estado = {"AMZN": {"factor_escala": 1.0, "factor_fecha": HOY}}

    filas, issues = mdp.fetch_backfill_ohlcv_watchlist(
        [_wl("AMZN", objetivo=2900.0)], [], {}, object(), hoy=HOY, estado_por_ticker=estado,
    )
    assert issues == []
    assert round(filas[0]["cierre"], 2) == 2850.0
