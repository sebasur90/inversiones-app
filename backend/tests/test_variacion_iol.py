"""Variación diaria de IOL: captura, guardado, uso en la variación mostrada y relleno de huecos.

Sin red: se mockea `get_autenticado` / `fetch_historico_ohlcv` y el contador de cupo de IOL.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, CotizacionDiaria
from app.services import cotizacion_diaria, refresco_precios
from app.services.inversiones_analytics import _variacion_diaria
from app.services.market_data import iol
from app.services.market_data import precios as mdp
from app.services.market_data.ohlcv_types import BarraCruda

_DB = object()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


# --- Captura en iol.py --------------------------------------------------------------------------

def _panel(monkeypatch, titulos):
    p0 = iol._PANELES[0]
    url0 = f"{iol.iol_auth.BASE_URL}/Cotizaciones/{p0[0]}/{p0[1]}/{p0[2]}"
    monkeypatch.setattr(iol.iol_auth, "get_autenticado",
                        lambda db, url: {"titulos": titulos} if url == url0 else None)


def test_panel_captura_variacion_y_cierre_anterior(monkeypatch):
    _panel(monkeypatch, [
        {"simbolo": "SPY", "ultimoPrecio": 20980.0, "moneda": "AR$", "variacion": 2.55, "ultimoCierre": 20458.0},
    ])
    out = iol.fetch_precios_paneles(_DB)
    assert out["SPY"] == (20980.0, "ARS")          # sigue siendo desempaquetable como (precio, moneda)
    assert out["SPY"].variacion_pct == 2.55
    assert out["SPY"].cierre_anterior == 20458.0


def test_panel_sin_campos_del_dia_los_deja_en_none(monkeypatch):
    _panel(monkeypatch, [{"simbolo": "KO", "ultimoPrecio": 27680.0, "moneda": "ARS"}])
    cot = iol.fetch_precios_paneles(_DB)["KO"]
    assert cot.variacion_pct is None and cot.cierre_anterior is None


def test_panel_descarta_variacion_absurda_y_cierre_no_positivo(monkeypatch):
    _panel(monkeypatch, [
        {"simbolo": "X", "ultimoPrecio": 10.0, "moneda": "ARS", "variacion": 99999, "ultimoCierre": 0},
    ])
    cot = iol.fetch_precios_paneles(_DB)["X"]
    assert cot.variacion_pct is None and cot.cierre_anterior is None


# --- construir_cotizaciones_dia -------------------------------------------------------------------

def _fila(ticker, precio, fuente="iol", fecha=date(2026, 10, 8)):
    return {"ticker": ticker, "fecha": fecha, "precio": precio, "moneda": "ARS", "fuente": fuente}


def test_construir_escala_el_cierre_anterior_con_el_mismo_factor():
    # IOL cotiza por lámina de 100: el precio guardado es 1/100 y el cierre anterior también.
    cot = iol.CotizacionIOL(272.85, "ARS", 270.0, 1.0556)
    out = cotizacion_diaria.construir_cotizaciones_dia([_fila("TZXD7", 2.7285)], {"TZXD7": cot})
    assert out == [{"ticker": "TZXD7", "fecha": date(2026, 10, 8), "cierre_anterior": 2.7,
                    "variacion_pct": 1.0556, "fuente": "iol"}]


def test_construir_deriva_la_variacion_si_solo_viene_el_cierre():
    cot = iol.CotizacionIOL(110.0, "ARS", 100.0, None)
    out = cotizacion_diaria.construir_cotizaciones_dia([_fila("A", 110.0)], {"A": cot})
    assert out[0]["variacion_pct"] == pytest.approx(10.0)


def test_construir_ignora_lo_que_no_viene_de_iol_o_no_trae_nada():
    cot_vacia = iol.CotizacionIOL(10.0, "ARS")
    plano = (10.0, "ARS")  # un `(precio, moneda)` pelado, como el de un test viejo
    filas = [_fila("A", 10.0, fuente="api"), _fila("B", 10.0), _fila("C", 10.0)]
    assert cotizacion_diaria.construir_cotizaciones_dia(filas, {"A": cot_vacia, "B": cot_vacia, "C": plano}) == []


def test_guardar_es_idempotente_y_cargar_devuelve_la_clave(db):
    fila = {"ticker": "SPY", "fecha": date(2026, 10, 8), "cierre_anterior": 100.0, "variacion_pct": 2.5, "fuente": "iol"}
    cotizacion_diaria.guardar(db, [fila])
    cotizacion_diaria.guardar(db, [{**fila, "variacion_pct": 3.0}])
    db.commit()
    assert db.query(CotizacionDiaria).count() == 1
    assert cotizacion_diaria.cargar_por_clave(db, {"SPY"}) == {("SPY", date(2026, 10, 8)): (100.0, 3.0)}


def test_purgar_antiguas(db):
    hoy = date(2026, 10, 8)
    cotizacion_diaria.guardar(db, [
        {"ticker": "A", "fecha": hoy - timedelta(days=500), "cierre_anterior": 1, "variacion_pct": 1, "fuente": "iol"},
        {"ticker": "A", "fecha": hoy, "cierre_anterior": 1, "variacion_pct": 1, "fuente": "iol"},
    ])
    cotizacion_diaria.purgar_antiguas(db, hoy)
    assert [r.fecha for r in db.query(CotizacionDiaria).all()] == [hoy]


# --- _variacion_diaria ---------------------------------------------------------------------------

def test_variacion_prefiere_lo_que_informa_iol():
    serie = [(date(2026, 8, 24), 20380.0, "ARS")]  # registro de hace seis semanas: no debe usarse
    abs_, ratio = _variacion_diaria(serie, date(2026, 10, 8), 20870.0, "ARS", (20350.0, 2.5307))
    assert ratio == pytest.approx(0.025307)
    assert abs_ == pytest.approx(520.0)


def test_variacion_con_solo_porcentaje_deriva_el_absoluto():
    abs_, ratio = _variacion_diaria([], date(2026, 10, 8), 110.0, "ARS", (None, 10.0))
    assert ratio == pytest.approx(0.10)
    assert abs_ == pytest.approx(10.0)


def test_variacion_usa_el_dia_habil_previo_sin_iol():
    serie = [(date(2026, 10, 2), 100.0, "ARS")]  # viernes -> lunes
    _, ratio = _variacion_diaria(serie, date(2026, 10, 5), 101.0, "ARS")
    assert ratio == pytest.approx(0.01)


def test_variacion_con_hueco_de_semanas_es_none():
    serie = [(date(2026, 8, 24), 20380.0, "ARS")]
    assert _variacion_diaria(serie, date(2026, 10, 8), 20870.0, "ARS") == (None, None)


def test_variacion_en_otra_moneda_es_none():
    serie = [(date(2026, 10, 7), 100.0, "USD")]
    assert _variacion_diaria(serie, date(2026, 10, 8), 100.0, "ARS") == (None, None)


# --- Huecos y relleno -----------------------------------------------------------------------------

def test_huecos_ignora_fines_de_semana_y_feriados_sueltos():
    lun = date(2026, 10, 5)
    # Falta el miércoles (feriado suelto) y hay fin de semana de por medio: ningún hueco.
    conocidas = {lun, lun + timedelta(days=1), lun + timedelta(days=3), lun + timedelta(days=4),
                 lun + timedelta(days=7)}
    assert mdp._huecos_dias_habiles(conocidas, lun, lun + timedelta(days=7)) == []


def test_huecos_detecta_tramo_de_cuatro_dias_habiles():
    conocidas = {date(2026, 8, 10), date(2026, 8, 17)}  # lun .. lun: faltan mar-vie
    assert mdp._huecos_dias_habiles(conocidas, date(2026, 8, 10), date(2026, 8, 17)) == [
        (date(2026, 8, 11), date(2026, 8, 14), 4)
    ]


HOY = date(2026, 10, 8)
INST = [{"ticker": "SPY", "tipo_instrumento": "CEDEAR", "moneda": "ARS"}]


def _dias_habiles(desde, hasta):
    d = desde
    while d <= hasta:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


@pytest.fixture
def iol_stub(monkeypatch):
    llamadas = []

    def historico(db, ticker, desde, hasta, mercado="bCBA"):
        llamadas.append((ticker, desde, hasta))
        return [BarraCruda(fecha=d, cierre=100.0, apertura=100.0, maximo=101.0, minimo=99.0)
                for d in _dias_habiles(desde, hasta)]

    monkeypatch.setattr(mdp.iol_client, "fetch_historico_ohlcv", historico)
    monkeypatch.setattr(mdp.iol_auth, "cupo_disponible", lambda db: True)
    monkeypatch.setattr(mdp.iol_auth, "llamadas_mes", lambda db: 0)
    monkeypatch.setattr(mdp.iol_auth, "limite_mensual", lambda: 22_000)
    return llamadas


def _relleno(conocidas, estado=None, instrumentos=INST, **kw):
    sheet = [{"ticker": "SPY", "fecha": max(conocidas), "precio": 100.0, "moneda": "ARS"}]
    barras: list = []
    filas, issues = mdp.fetch_relleno_huecos_iol(
        instrumentos, sheet, {("SPY", f) for f in conocidas},
        {"SPY": min(conocidas)}, {"SPY": set(conocidas)}, _DB, hoy=HOY,
        estado_por_ticker=estado if estado is not None else {}, barras_out=barras, **kw,
    )
    return filas, issues, barras


def test_relleno_completa_solo_las_fechas_que_faltan(iol_stub):
    conocidas = {date(2026, 8, 10), date(2026, 8, 17), date(2026, 8, 24)}
    estado: dict = {}
    filas, _, barras = _relleno(conocidas, estado)

    assert len(iol_stub) == 1                       # una sola llamada para todo el ticker
    fechas = {f["fecha"] for f in filas}
    assert not fechas & conocidas                   # nunca pisa lo que ya había (ni el Sheet)
    assert HOY not in fechas and date(2026, 10, 7) in fechas and date(2026, 8, 11) in fechas
    assert all(f["fuente"] == "iol" and f["precio"] == 100.0 for f in filas)
    assert estado["SPY"]["relleno_estado"] == "completo" and estado["SPY"]["relleno_intento"] == HOY
    assert barras and all(b["fecha"] < HOY for b in barras)


def test_sin_hueco_no_gasta_ninguna_llamada(iol_stub):
    conocidas = set(_dias_habiles(date(2026, 9, 1), date(2026, 10, 7)))
    filas, _, _ = _relleno(conocidas)
    assert filas == [] and iol_stub == []


def test_cooldown_tras_un_intento_no_vuelve_a_pedir(iol_stub):
    conocidas = {date(2026, 8, 10), date(2026, 8, 24)}
    estado = {"SPY": {"relleno_intento": HOY - timedelta(days=5)}}
    filas, _, _ = _relleno(conocidas, estado)
    assert filas == [] and iol_stub == []


def test_pasado_el_cooldown_vuelve_a_intentar(iol_stub):
    conocidas = {date(2026, 8, 10), date(2026, 8, 24)}
    estado = {"SPY": {"relleno_intento": HOY - timedelta(days=45)}}
    _relleno(conocidas, estado)
    assert len(iol_stub) == 1


def test_sin_cupo_no_llama(iol_stub, monkeypatch):
    monkeypatch.setattr(mdp.iol_auth, "cupo_disponible", lambda db: False)
    filas, _, _ = _relleno({date(2026, 8, 10), date(2026, 8, 24)})
    assert filas == [] and iol_stub == []


def test_con_el_cupo_mensual_muy_usado_se_omite(iol_stub, monkeypatch):
    monkeypatch.setattr(mdp.iol_auth, "llamadas_mes", lambda db: 16_000)  # > 70% de 22.000
    filas, issues, _ = _relleno({date(2026, 8, 10), date(2026, 8, 24)})
    assert filas == [] and iol_stub == []
    assert [i.regla for i in issues] == ["relleno_huecos_omitido_por_cupo"]


def test_tope_de_tickers_por_sync(iol_stub):
    tickers = [f"T{n}" for n in range(8)]
    instrumentos = [{"ticker": t, "tipo_instrumento": "CEDEAR", "moneda": "ARS"} for t in tickers]
    conocidas = {date(2026, 8, 10), date(2026, 8, 24)}
    sheet = [{"ticker": t, "fecha": date(2026, 8, 24), "precio": 100.0, "moneda": "ARS"} for t in tickers]
    mdp.fetch_relleno_huecos_iol(
        instrumentos, sheet, set(), {t: date(2026, 8, 10) for t in tickers},
        {t: set(conocidas) for t in tickers}, _DB, hoy=HOY, estado_por_ticker={},
    )
    assert len(iol_stub) == mdp._MAX_RELLENO_POR_SYNC


def test_sin_serie_en_iol_igual_queda_en_cooldown(iol_stub, monkeypatch):
    monkeypatch.setattr(mdp.iol_client, "fetch_historico_ohlcv", lambda *a, **k: None)
    estado: dict = {}
    filas, _, _ = _relleno({date(2026, 8, 10), date(2026, 8, 24)}, estado)
    assert filas == [] and estado["SPY"]["relleno_intento"] == HOY


# --- El refresco guarda la variación ---------------------------------------------------------------

def test_refresco_guarda_la_variacion_de_iol(db, monkeypatch):
    from app.database import InstrumentoInversion
    db.add(InstrumentoInversion(ticker="SPY", nombre="SPY", tipo_instrumento="CEDEAR", mercado="MERVAL", moneda="ARS"))
    db.commit()
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    monkeypatch.setattr(mdp, "memo_paneles", lambda db: (lambda: None))
    monkeypatch.setattr(mdp, "memo_fci", lambda db: (lambda: None))

    hoy = date.today()

    def falso(instrumentos, precios_sheet, claves_excluir, db, **kwargs):
        kwargs["cotizaciones_out"]["SPY"] = iol.CotizacionIOL(20980.0, "ARS", 20458.0, 2.55)
        return [{"ticker": "SPY", "fecha": hoy, "precio": 20980.0, "moneda": "ARS", "fuente": "iol"}], []

    monkeypatch.setattr(mdp, "fetch_precios_api", falso)
    refresco_precios.refrescar(db)

    assert cotizacion_diaria.cargar_por_clave(db) == {("SPY", hoy): (20458.0, 2.55)}
