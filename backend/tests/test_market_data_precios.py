"""Tests de `market_data.precios` (renta fija y renta variable vía data912) — sin red: mockea
`data912`."""
from datetime import date, timedelta

import pytest

from backend.app.services.market_data import precios as mdp
from backend.app.services.market_data import analisistecnico, data912


@pytest.mark.parametrize("tipo, esperado", [
    ("Bono", True),
    ("bono", True),
    ("BONO SOBERANO", True),
    ("Boncer", True),
    ("Obligación Negociable", True),
    ("ON", True),
    ("on", True),
    ("Letra", True),
    ("LECAP", True),
    ("CEDEAR", False),
    ("Acción", False),  # "accion" no debe matchear por el token "on"
    ("Accion", False),
    ("FCI", False),
    ("", False),
    (None, False),
])
def test_es_renta_fija(tipo, esperado):
    assert mdp._es_renta_fija(tipo) is esperado


@pytest.mark.parametrize("tipo, esperado", [
    ("Acción", True),
    ("Accion", True),
    ("ACCIONES", True),
    ("CEDEAR", True),
    ("cedear", True),
    ("Cedears", True),
    ("Bono", False),
    ("ON", False),
    ("FCI", False),
    ("", False),
    (None, False),
])
def test_es_renta_variable(tipo, esperado):
    assert mdp._es_renta_variable(tipo) is esperado


def _inst(ticker, tipo="Bono", moneda="ARS"):
    return {"ticker": ticker, "tipo_instrumento": tipo, "moneda": moneda}


def _px(ticker, precio, fecha=date(2026, 7, 27)):
    return {"ticker": ticker, "fecha": fecha, "precio": precio, "moneda": "ARS"}


HOY = date(2026, 8, 28)


def test_escala_100_se_normaliza(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)], claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert len(filas) == 1
    assert filas[0]["ticker"] == "TZXD7"
    assert filas[0]["fecha"] == HOY
    assert filas[0]["fuente"] == "api"
    assert round(filas[0]["precio"], 4) == 2.7285  # 272.85 / 100


def test_escala_1_se_deja_igual(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"AL30": 85160.0})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("AL30")], [_px("AL30", 84000.0)], claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert filas[0]["precio"] == 85160.0


def test_sin_precio_previo_no_carga_y_reporta(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert len(issues) == 1
    assert issues[0].regla == "sin_precio_para_calibrar"
    assert issues[0].severidad.value == "info"


def test_ticker_no_encontrado_en_data912(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"OTRO": 100.0})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "ticker_no_mapeado"
    assert issues[0].severidad.value == "info"


def test_ratio_raro_no_carga_y_advierte(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 27.0})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert issues[0].severidad.value == "advertencia"


def test_api_caida_devuelve_none(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: None)
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY
    )
    assert filas is None
    assert len(issues) == 1
    assert issues[0].regla == "data912_no_disponible"


def test_fecha_ya_cubierta_por_el_sheet_se_saltea(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)],
        claves_excluir={("TZXD7", HOY)}, hoy=HOY,
    )
    assert filas == []
    assert issues == []


def test_sin_instrumentos_de_renta_fija_no_llama_api(monkeypatch):
    def _boom():
        raise AssertionError("no debería pegarle a data912 si no hay renta fija")

    monkeypatch.setattr(data912, "fetch_precios_renta_fija", _boom)
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("KO", tipo="CEDEAR")], [], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues == []


def test_usa_el_ultimo_precio_del_sheet_para_calibrar(monkeypatch):
    """Con varias filas del Sheet, calibra contra la más reciente."""
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    precios_sheet = [
        _px("TZXD7", 200.0, fecha=date(2026, 1, 1)),   # vieja y en otra escala: no debe ganar
        _px("TZXD7", 2.7135, fecha=date(2026, 7, 27)),
    ]
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], precios_sheet, claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert round(filas[0]["precio"], 4) == 2.7285


# --- Renta variable (acciones/CEDEARs, Ola 4) — mismo motor, sin backfill ------------------

def test_rv_escala_1_se_deja_igual(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"GGAL": 5230.0})
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0)], claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert filas[0]["ticker"] == "GGAL"
    assert filas[0]["fuente"] == "api"
    assert filas[0]["precio"] == 5230.0


def test_rv_escala_100_se_normaliza(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"KO": 850.0})
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("KO", tipo="CEDEAR")], [_px("KO", 8.4)], claves_excluir=set(), hoy=HOY
    )
    assert issues == []
    assert round(filas[0]["precio"], 4) == 8.5  # 850 / 100


def test_rv_sin_precio_previo_no_carga_y_reporta(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"GGAL": 5230.0})
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("GGAL", tipo="Accion")], [], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "sin_precio_para_calibrar"
    assert issues[0].severidad.value == "info"


def test_rv_ticker_no_encontrado_en_data912(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"OTRO": 100.0})
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0)], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "ticker_no_mapeado"
    assert "arg_stocks/arg_cedears" in issues[0].mensaje
    assert issues[0].severidad.value == "info"


def test_rv_ratio_raro_no_carga_y_advierte(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"GGAL": 500.0})
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0)], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert issues[0].severidad.value == "advertencia"


def test_rv_api_caida_devuelve_none(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: None)
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0)], claves_excluir=set(), hoy=HOY
    )
    assert filas is None
    assert issues[0].regla == "data912_no_disponible"


def test_rv_fecha_ya_cubierta_por_el_sheet_se_saltea(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_variable", lambda: {"GGAL": 5230.0})
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("GGAL", tipo="Accion")], [_px("GGAL", 5100.0)],
        claves_excluir={("GGAL", HOY)}, hoy=HOY,
    )
    assert filas == []
    assert issues == []


def test_sin_instrumentos_de_renta_variable_no_llama_api(monkeypatch):
    def _boom():
        raise AssertionError("no debería pegarle a data912 si no hay renta variable")

    monkeypatch.setattr(data912, "fetch_precios_renta_variable", _boom)
    filas, issues = mdp.fetch_precios_renta_variable_api(
        [_inst("AL30", tipo="Bono")], [], claves_excluir=set(), hoy=HOY
    )
    assert filas == []
    assert issues == []


# --- Backfill histórico (analisistecnico) --------------------------------------------------

def _serie(*pares):
    return [(f, px) for f, px in pares]


def _backfill(monkeypatch, serie, *, instrumentos, precios_sheet, primeras, api_min=None,
              claves_excluir=None, hoy=HOY, estado=None):
    llamadas = []

    def _fake(ticker, desde, hasta):
        llamadas.append((ticker, desde, hasta))
        return serie(ticker) if callable(serie) else serie

    monkeypatch.setattr(analisistecnico, "fetch_historico_bono", _fake)
    filas, issues = mdp.fetch_backfill_renta_fija_api(
        instrumentos, precios_sheet, claves_excluir or set(),
        primeras, api_min or {}, hoy=hoy, estado_por_ticker=estado,
    )
    return filas, issues, llamadas


def test_backfill_normaliza_escala_100_y_marca_fuente(monkeypatch):
    serie = _serie((date(2025, 6, 2), 270.0), (date(2025, 6, 3), 272.5))
    filas, issues, llamadas = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 6, 1)},
    )
    assert issues == []
    assert len(llamadas) == 1 and llamadas[0][0] == "TZXD7"
    assert {f["fecha"] for f in filas} == {date(2025, 6, 2), date(2025, 6, 3)}
    assert all(f["fuente"] == "api" and f["moneda"] == "ARS" for f in filas)
    assert round(filas[0]["precio"], 4) == 2.70 and round(filas[1]["precio"], 4) == 2.725


def test_backfill_escala_1_se_deja_igual(monkeypatch):
    serie = _serie((date(2025, 6, 2), 84000.0))
    filas, issues, _ = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("AL30")],
        precios_sheet=[_px("AL30", 83000.0, fecha=date(2026, 7, 27))],
        primeras={"AL30": date(2025, 6, 1)},
    )
    assert issues == []
    assert filas[0]["precio"] == 84000.0


def test_backfill_excluye_fechas_del_sheet_y_la_de_hoy(monkeypatch):
    serie = _serie(
        (date(2025, 6, 2), 270.0),
        (date(2026, 7, 27), 271.0),   # ya está en el Sheet
        (HOY, 272.0),                  # hoy lo cubre la ruta 'live'
    )
    filas, issues, _ = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 6, 1)},
        claves_excluir={("TZXD7", date(2026, 7, 27))},
    )
    assert issues == []
    assert {f["fecha"] for f in filas} == {date(2025, 6, 2)}


def test_backfill_converge_no_vuelve_a_pedir_si_ya_llego_al_piso(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("no debería pedir la serie: ya está backfilleado hasta el piso")

    monkeypatch.setattr(analisistecnico, "fetch_historico_bono", _boom)
    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)], set(),
        {"TZXD7": date(2025, 6, 1)},
        {"TZXD7": date(2025, 6, 10)},   # la serie 'api' ya arranca a 9 días del piso (< 40)
        hoy=HOY,
    )
    assert filas == [] and issues == []


def test_backfill_pide_si_el_hueco_supera_la_tolerancia(monkeypatch):
    serie = _serie((date(2025, 6, 2), 270.0))
    filas, issues, llamadas = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 6, 1)},
        api_min={"TZXD7": date(2026, 8, 1)},   # la serie 'api' sólo llega ~forward: hay hueco
    )
    assert len(llamadas) == 1 and filas


def test_backfill_sin_movimientos_no_pide(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("sin movimientos no hay posición que valuar")

    monkeypatch.setattr(analisistecnico, "fetch_historico_bono", _boom)
    filas, issues = mdp.fetch_backfill_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)], set(), {}, {}, hoy=HOY,
    )
    assert filas == [] and issues == []


def test_backfill_ticker_no_cubierto_reporta_info(monkeypatch):
    filas, issues, _ = _backfill(
        monkeypatch, None,   # analisistecnico -> None (ON u otro no listado)
        instrumentos=[_inst("MGCJO", tipo="ON")],
        precios_sheet=[_px("MGCJO", 105000.0, fecha=date(2026, 7, 27))],
        primeras={"MGCJO": date(2025, 6, 1)},
    )
    assert filas == []
    assert len(issues) == 1
    assert issues[0].regla == "sin_historico_backfill"
    assert issues[0].severidad.value == "info"


def test_backfill_sin_precio_para_calibrar_reporta_info(monkeypatch):
    serie = _serie((date(2025, 6, 2), 270.0))
    filas, issues, _ = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[],
        primeras={"TZXD7": date(2025, 6, 1)},
    )
    assert filas == []
    assert issues[0].regla == "sin_precio_para_calibrar"
    assert issues[0].severidad.value == "info"


def test_backfill_escala_rara_advierte(monkeypatch):
    serie = _serie((date(2025, 6, 2), 27.0))
    filas, issues, _ = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 6, 1)},
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert issues[0].severidad.value == "advertencia"


def test_backfill_respeta_tope_de_5_anios(monkeypatch):
    serie = _serie((date(2025, 6, 2), 270.0))
    _, _, llamadas = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2010, 1, 1)},   # mucho más viejo que el tope
    )
    _, desde, hasta = llamadas[0]
    assert desde == HOY - timedelta(days=366 * 5)
    assert hasta == HOY - timedelta(days=1)


def test_backfill_atiende_primero_los_huecos_mas_grandes(monkeypatch):
    tope = mdp._MAX_BACKFILL_POR_SYNC
    n = tope + 2
    piso = date(2025, 1, 1)
    instrumentos = [_inst(f"B{i}") for i in range(n)]
    precios_sheet = [_px(f"B{i}", 100.0, fecha=date(2026, 7, 27)) for i in range(n)]
    primeras = {f"B{i}": piso for i in range(n)}
    # B0 sin api (hueco infinito); B1..B(n-1) con hueco creciente, todos > la tolerancia de 40d.
    api_min = {f"B{i}": piso + timedelta(days=50 + i) for i in range(1, n)}
    llamados = []
    monkeypatch.setattr(analisistecnico, "fetch_historico_bono",
                        lambda t, d, h: llamados.append(t) or _serie((date(2025, 6, 2), 100.0)))
    mdp.fetch_backfill_renta_fija_api(instrumentos, precios_sheet, set(), primeras, api_min, hoy=HOY)
    assert len(llamados) == tope
    assert "B0" in llamados        # hueco infinito, primero
    assert "B1" not in llamados    # hueco más chico, queda afuera este sync
    assert "B2" not in llamados


# --- A2: la moneda de la fila 'api' sale de la serie calibrada, no de Instrumentos -----------

def test_a2_moneda_sale_de_la_serie_no_de_instrumentos(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7", moneda="USD")], [_px("TZXD7", 2.7135)], claves_excluir=set(), hoy=HOY
    )
    assert len(filas) == 1 and filas[0]["moneda"] == "ARS"  # la de la serie de Precios, no USD
    assert [i.regla for i in issues] == ["moneda_sheet_difiere_instrumento"]
    assert issues[0].severidad.value == "info"


def test_a2_backfill_moneda_sale_de_la_serie(monkeypatch):
    serie = _serie((date(2025, 6, 2), 270.0))
    filas, issues, _ = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7", moneda="USD")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 6, 1)},
    )
    assert filas and all(f["moneda"] == "ARS" for f in filas)
    assert [i.regla for i in issues] == ["moneda_sheet_difiere_instrumento"]


def test_a2_moneda_coincide_no_emite_issue(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7", moneda="ARS")], [_px("TZXD7", 2.7135)], claves_excluir=set(), hoy=HOY
    )
    assert filas[0]["moneda"] == "ARS" and issues == []


# --- A1: el factor de escala se persiste en vez de recalibrarse contra una referencia vieja --

def test_a1_factor_guardado_se_reusa_con_precio_manual_viejo(monkeypatch):
    # Hoy data912 cotiza 400 vs último manual 100 → ratio 4 (zona muerta: _factor_escala=None).
    # Pero hay factor 1.0 guardado y el manual no es más nuevo que factor_fecha → se reusa.
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"AL30": 400.0})
    estado = {"AL30": {"factor_escala": 1.0, "factor_fecha": date(2026, 7, 27),
                       "backfill_estado": None, "backfill_intento": None}}
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("AL30")], [_px("AL30", 100.0, fecha=date(2026, 1, 1))],
        claves_excluir=set(), hoy=HOY, estado_por_ticker=estado,
    )
    assert issues == []
    assert filas[0]["precio"] == 400.0


def test_a1_precio_manual_nuevo_dispara_recalibracion(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    estado = {"TZXD7": {"factor_escala": 1.0, "factor_fecha": date(2026, 1, 1),
                        "backfill_estado": None, "backfill_intento": None}}
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        claves_excluir=set(), hoy=HOY, estado_por_ticker=estado,
    )
    assert issues == []
    assert round(filas[0]["precio"], 4) == 2.7285  # recalibró: ratio ~100 → factor 0.01
    assert estado["TZXD7"]["factor_escala"] == 0.01
    assert estado["TZXD7"]["factor_fecha"] == date(2026, 7, 27)


def test_a1_zona_muerta_sin_factor_previo_sigue_rechazando(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 27.0})
    estado: dict = {}
    filas, issues = mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7)], claves_excluir=set(), hoy=HOY,
        estado_por_ticker=estado,
    )
    assert filas == []
    assert issues[0].regla == "escala_desconocida"
    assert estado == {}  # nada que persistir


def test_a1_factor_calibrado_se_persiste(monkeypatch):
    monkeypatch.setattr(data912, "fetch_precios_renta_fija", lambda: {"TZXD7": 272.85})
    estado: dict = {}
    mdp.fetch_precios_renta_fija_api(
        [_inst("TZXD7")], [_px("TZXD7", 2.7135)], claves_excluir=set(), hoy=HOY,
        estado_por_ticker=estado,
    )
    assert estado["TZXD7"]["factor_escala"] == 0.01
    assert estado["TZXD7"]["factor_fecha"] == date(2026, 7, 27)


# --- A3: el backfill converge para tickers sin serie / cuya serie no baja más ----------------

def test_a3_sin_serie_no_se_repite_y_libera_cupo(monkeypatch):
    estado: dict = {}
    args = ([_inst("MGCJO", tipo="ON")], [_px("MGCJO", 105000.0, fecha=date(2026, 7, 27))],
            set(), {"MGCJO": date(2025, 6, 1)}, {})

    filas1, issues1, llamadas1 = _backfill(
        monkeypatch, None, instrumentos=args[0], precios_sheet=args[1],
        primeras=args[3], estado=estado,
    )
    assert filas1 == [] and issues1[0].regla == "sin_historico_backfill"
    assert estado["MGCJO"]["backfill_estado"] == "sin_serie"
    assert estado["MGCJO"]["backfill_intento"] == HOY

    filas2, issues2, llamadas2 = _backfill(
        monkeypatch, None, instrumentos=args[0], precios_sheet=args[1],
        primeras=args[3], estado=estado,
    )
    assert filas2 == [] and issues2 == []   # no se re-emite el issue
    assert llamadas2 == []                   # no se vuelve a pedir la serie → cupo libre


def test_a3_sin_serie_se_reintenta_tras_90_dias(monkeypatch):
    estado = {"X1": {"factor_escala": None, "factor_fecha": None,
                     "backfill_estado": "sin_serie",
                     "backfill_intento": HOY - timedelta(days=91)}}
    filas, issues, llamadas = _backfill(
        monkeypatch, None,
        instrumentos=[_inst("X1", tipo="ON")],
        precios_sheet=[_px("X1", 100.0, fecha=date(2026, 7, 27))],
        primeras={"X1": date(2025, 6, 1)}, estado=estado,
    )
    assert [c[0] for c in llamadas] == ["X1"]      # pasaron >90 días → se reintenta
    assert estado["X1"]["backfill_intento"] == HOY


def test_a3_serie_que_no_baja_mas_se_marca_completo(monkeypatch):
    # La serie arranca muy por encima del piso y ya hay filas 'api' desde esa misma fecha:
    # la fecha más vieja no mejoró respecto de la corrida anterior → completo.
    serie = _serie((date(2025, 9, 1), 270.0), (date(2025, 9, 2), 271.0))
    estado: dict = {}
    filas, issues, llamadas = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 1, 1)},
        api_min={"TZXD7": date(2025, 9, 1)},
        estado=estado,
    )
    assert filas and issues == []
    assert estado["TZXD7"]["backfill_estado"] == "completo"

    # Segunda corrida: marcado completo → no se vuelve a pedir la serie.
    filas2, _, llamadas2 = _backfill(
        monkeypatch, serie,
        instrumentos=[_inst("TZXD7")],
        precios_sheet=[_px("TZXD7", 2.7135, fecha=date(2026, 7, 27))],
        primeras={"TZXD7": date(2025, 1, 1)},
        api_min={"TZXD7": date(2025, 9, 1)},
        estado=estado,
    )
    assert filas2 == [] and llamadas2 == []

