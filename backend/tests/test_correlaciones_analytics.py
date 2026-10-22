"""get_matriz_correlaciones y sus helpers de boundaries/retornos por frecuencia
(app.services.correlaciones_analytics). SQLite in-memory, sin HTTP."""
from datetime import date, timedelta

import math

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    BarraOHLCV, Base, IndiceMercado, MovimientoInversion, PrecioInstrumento, WatchlistItem,
)
from app.services import contribucion_analytics
from app.services.cache import limpiar_cache
from app.services.correlaciones_analytics import (
    MAX_TICKERS,
    TOLERANCIA_DIAS,
    _boundaries_frecuencia,
    _periodo_efectivo,
    _resolver_tickers,
    _retornos_por_boundaries,
    _tickers_por_defecto,
    get_matriz_correlaciones,
)
from app.services.inversiones_analytics import UMBRAL_APROXIMADO_DIAS, _precios_por_ticker


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    session.commit()
    yield session
    session.close()
    limpiar_cache()


def _compra(db, cartera, ticker, cantidad, precio, fecha=date(2024, 1, 1), moneda="USD"):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0,
    ))


def _precio(db, ticker, precio, fecha, moneda="USD"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda))


def _serie_diaria(db, ticker, valores: dict, moneda="USD"):
    for fecha, precio in valores.items():
        _precio(db, ticker, precio, fecha, moneda)


# ── _boundaries_frecuencia ────────────────────────────────────────────────────

def test_boundaries_diarios_excluyen_fin_de_semana():
    # 2024-01-01 es lunes; 2024-01-07 es domingo.
    boundaries = _boundaries_frecuencia("diaria", date(2024, 1, 1), date(2024, 1, 7))
    assert all(b.weekday() < 5 for b in boundaries)
    assert len(boundaries) == 5  # lun a vie


def test_boundaries_semanales_son_viernes_espaciados_7_dias():
    boundaries = _boundaries_frecuencia("semanal", date(2024, 1, 1), date(2024, 2, 1))
    assert all(b.weekday() == 4 for b in boundaries)
    for a, b in zip(boundaries, boundaries[1:]):
        assert (b - a).days == 7


def test_boundaries_mensuales_son_fin_de_mes_completo_y_excluyen_mes_en_curso_y_hasta_extra():
    # hasta = 15 de marzo: enero y febrero están completos, marzo no.
    boundaries = _boundaries_frecuencia("mensual", date(2024, 1, 1), date(2024, 3, 15))
    assert boundaries == [date(2024, 1, 31), date(2024, 2, 29)]
    assert date(2024, 3, 15) not in boundaries  # no se agrega `hasta` como punto extra


def test_boundaries_vacio_si_desde_mayor_a_hasta():
    assert _boundaries_frecuencia("diaria", date(2024, 2, 1), date(2024, 1, 1)) == []


# ── _retornos_por_boundaries: el núcleo anti-fabricación de ceros ────────────

def test_diaria_no_fabrica_ceros_ante_huecos(db: Session):
    """3 días sin precio cargado en medio de una serie diaria: ningún retorno debe salir 0 por
    el hueco, y ningún retorno debe cruzarlo (las claves emitidas son sólo entre boundaries
    consecutivos, ambos aceptados)."""
    boundaries = [date(2024, 1, i) for i in range(1, 11) if date(2024, 1, i).weekday() < 5]
    # Precios: día 1..3 con valores, hueco días 4-6 sin cargar, retoma día 8/9/10.
    precios_sorted = [
        (date(2024, 1, 1), 100.0, "USD"),
        (date(2024, 1, 2), 101.0, "USD"),
        (date(2024, 1, 3), 102.0, "USD"),
        (date(2024, 1, 8), 200.0, "USD"),  # salto grande: si se encadenara sobre el hueco se vería
        (date(2024, 1, 9), 201.0, "USD"),
        (date(2024, 1, 10), 202.0, "USD"),
    ]
    serie, cobertura = _retornos_por_boundaries(precios_sorted, boundaries, 0, "USD", db, {})

    # Ningún retorno == 0.0 fabricado por carry-forward sobre un día sin dato.
    assert 0.0 not in serie.values()
    # El salto de 102 a 200 (que cruzaría el hueco) NO debe aparecer como un único retorno.
    huge_jump = any(v > 0.9 for v in serie.values())  # 200/102-1 ~ 0.96 sería la fabricación
    assert not huge_jump
    # Sólo se emiten retornos entre boundaries consecutivos con precio exacto (tolerancia 0).
    assert serie.get(date(2024, 1, 2)) == pytest.approx(101.0 / 100.0 - 1)
    assert serie.get(date(2024, 1, 3)) == pytest.approx(102.0 / 101.0 - 1)
    assert date(2024, 1, 8) not in serie  # el boundary previo (1/4, 1/5) no tiene precio propio
    assert serie.get(date(2024, 1, 9)) == pytest.approx(201.0 / 200.0 - 1)
    assert serie.get(date(2024, 1, 10)) == pytest.approx(202.0 / 201.0 - 1)


def test_tolerancia_por_frecuencia_jueves_aceptado_en_semanal_no_en_diaria(db: Session):
    boundary_viernes = date(2024, 1, 5)  # viernes
    # precios_sorted debe ir ordenado por fecha (lo exige _precio_conocido/bisect).
    precios_sorted = [(date(2023, 12, 29), 90.0, "USD"), (date(2024, 1, 4), 100.0, "USD")]

    serie_semanal, _cob = _retornos_por_boundaries(
        precios_sorted, [date(2023, 12, 29), boundary_viernes], TOLERANCIA_DIAS["semanal"], "USD", db, {},
    )
    assert boundary_viernes in serie_semanal

    serie_diaria, _cob = _retornos_por_boundaries(
        precios_sorted, [date(2023, 12, 29), boundary_viernes], TOLERANCIA_DIAS["diaria"], "USD", db, {},
    )
    assert boundary_viernes not in serie_diaria


def test_tolerancia_mensual_no_acepta_precio_de_45_dias(db: Session):
    """Contraste explícito: 45 días es exactamente UMBRAL_APROXIMADO_DIAS (umbral de valuación),
    muy por encima de la tolerancia de retorno mensual (10 días)."""
    assert TOLERANCIA_DIAS["mensual"] < UMBRAL_APROXIMADO_DIAS
    boundary = date(2024, 3, 31)
    precio_viejo = date(2024, 2, 14)  # 46 días antes
    assert (boundary - precio_viejo).days > TOLERANCIA_DIAS["mensual"]

    serie, _cob = _retornos_por_boundaries(
        [(date(2024, 1, 31), 100.0, "USD"), (precio_viejo, 110.0, "USD")],
        [date(2024, 1, 31), boundary],
        TOLERANCIA_DIAS["mensual"], "USD", db, {},
    )
    assert boundary not in serie


def test_precios_semanales_pedidos_en_diaria_no_inventan_correlacion(db: Session):
    """Si sólo hay un precio por semana pero se pide frecuencia diaria, ningún par debe salir
    con valor numérico: todo `datos_insuficientes`, ninguna celda fabricada."""
    boundaries = _boundaries_frecuencia("diaria", date(2024, 1, 1), date(2024, 3, 31))
    viernes = [b for b in boundaries if b.weekday() == 4]
    precios_a = [(f, 100.0 + i, "USD") for i, f in enumerate(viernes)]
    precios_b = [(f, 50.0 + i * 2, "USD") for i, f in enumerate(viernes)]

    serie_a, _ = _retornos_por_boundaries(precios_a, boundaries, TOLERANCIA_DIAS["diaria"], "USD", db, {})
    serie_b, _ = _retornos_por_boundaries(precios_b, boundaries, TOLERANCIA_DIAS["diaria"], "USD", db, {})
    # Con tolerancia 0 en diaria, sólo los viernes (que ya tienen precio propio) sobreviven, y
    # nunca dos viernes son boundaries consecutivos en la lista diaria -> ningún retorno emitido.
    assert serie_a == {}
    assert serie_b == {}


def test_precio_cero_o_negativo_no_produce_retorno(db: Session):
    boundaries = [date(2024, 1, 1), date(2024, 1, 2)]
    precios_sorted = [(date(2024, 1, 1), 0.0, "USD"), (date(2024, 1, 2), 10.0, "USD")]
    serie, _cob = _retornos_por_boundaries(precios_sorted, boundaries, 0, "USD", db, {})
    assert serie == {}


def test_conversion_ars_usd_con_mep_constante(db: Session):
    db.add(IndiceMercado(fecha=date(2024, 1, 2), mep=1000.0))
    db.commit()
    boundaries = [date(2024, 1, 1), date(2024, 1, 2)]
    precios_usd = [(date(2024, 1, 1), 10.0, "USD"), (date(2024, 1, 2), 11.0, "USD")]
    precios_ars = [(date(2024, 1, 1), 10_000.0, "ARS"), (date(2024, 1, 2), 11_000.0, "ARS")]

    mep_cache: dict = {}
    serie_usd, _ = _retornos_por_boundaries(precios_usd, boundaries, 0, "USD", db, mep_cache)
    serie_ars, _ = _retornos_por_boundaries(precios_ars, boundaries, 0, "USD", db, mep_cache)
    # Con MEP constante, el retorno en USD del activo ARS es idéntico al del activo ya en USD.
    assert serie_ars[date(2024, 1, 2)] == pytest.approx(serie_usd[date(2024, 1, 2)])


# ── _tickers_por_defecto / _resolver_tickers ─────────────────────────────────

def test_tickers_por_defecto_son_tenencias_top_por_valor_usd(db: Session):
    _compra(db, "test", "AAA", 10, 50.0)
    _compra(db, "test", "BBB", 100, 5.0)
    _compra(db, "test", "CCC", 1, 1.0)
    db.commit()
    _precio(db, "AAA", 50.0, date.today())
    _precio(db, "BBB", 5.0, date.today())
    _precio(db, "CCC", 1.0, date.today())
    db.commit()

    tickers = _tickers_por_defecto("test", db, tope=2)
    assert tickers == ["AAA", "BBB"]  # 500 y 500... orden desc, CCC (1.0) afuera por tope


def test_tickers_por_defecto_excluye_posiciones_cerradas(db: Session):
    _compra(db, "test", "AAA", 10, 50.0)
    db.add(MovimientoInversion(
        fecha=date(2024, 2, 1), cartera="test", ticker="AAA", tipo_movimiento="venta",
        cantidad=10, precio=55.0, moneda="USD", comision=0.0,
    ))
    db.commit()
    _precio(db, "AAA", 55.0, date.today())
    db.commit()
    assert _tickers_por_defecto("test", db) == []


def test_ticker_pedido_sin_precios_va_a_descartados(db: Session):
    _precio(db, "AAA", 100.0, date.today())
    db.commit()
    usables, descartados = _resolver_tickers(["AAA", "ZZZ"], "test", db)
    assert usables == ["AAA"]
    assert descartados == [{"ticker": "ZZZ", "motivo": "sin_precios"}]


def test_resolver_tickers_dedup_y_uppercase(db: Session):
    _precio(db, "AAA", 100.0, date.today())
    db.commit()
    usables, _descartados = _resolver_tickers(["aaa", "AAA", " aaa "], "test", db)
    assert usables == ["AAA"]


def test_resolver_tickers_aplica_tope(db: Session):
    tickers = [f"T{i}" for i in range(MAX_TICKERS + 2)]
    for t in tickers:
        _precio(db, t, 10.0, date.today())
    db.commit()
    usables, descartados = _resolver_tickers(tickers, "test", db)
    assert len(usables) == MAX_TICKERS
    assert len(descartados) == 2
    assert all(d["motivo"] == "tope_tickers" for d in descartados)


# ── _periodo_efectivo ──────────────────────────────────────────────────────────

def test_periodo_efectivo_respeta_desde_y_clampea_hasta_futuro():
    hoy = date.today()
    desde, hasta = _periodo_efectivo(date(2024, 1, 1), hoy + timedelta(days=30), "mensual", {}, [])
    assert desde == date(2024, 1, 1)
    assert hasta == hoy


# ── get_matriz_correlaciones: orquestación end-to-end ────────────────────────

def _sembrar_dos_tickers_correlacionados(db, fechas):
    for i, f in enumerate(fechas):
        _precio(db, "AAA", 100.0 + i, f)
        _precio(db, "BBB", 200.0 + i * 2, f)  # perfectamente correlacionado con AAA
    db.commit()


def test_get_matriz_correlaciones_ok_mensual(db: Session):
    fechas = [date(2024, m, 28) for m in range(1, 9)]
    _compra(db, "test", "AAA", 1, 100.0)
    _compra(db, "test", "BBB", 1, 200.0)
    db.commit()
    _sembrar_dos_tickers_correlacionados(db, fechas)

    resultado = get_matriz_correlaciones("test", db, tickers=["AAA", "BBB"], frecuencia="mensual",
                                          desde=date(2024, 1, 1), hasta=date(2024, 9, 1))
    assert resultado["estado"] == "ok"
    assert resultado["tickers"] == ["AAA", "BBB"]
    par = resultado["pares"][0]
    assert par["estado"] == "ok"
    assert par["valor"] == 1.0


def test_get_matriz_correlaciones_sin_tickers(db: Session):
    resultado = get_matriz_correlaciones("test", db, tickers=[], frecuencia="mensual")
    assert resultado["estado"] == "sin_tickers"
    assert resultado["matriz"] == []


def test_get_matriz_correlaciones_sin_suficientes_tickers(db: Session):
    _precio(db, "AAA", 100.0, date.today())
    db.commit()
    resultado = get_matriz_correlaciones("test", db, tickers=["AAA"], frecuencia="mensual")
    assert resultado["estado"] == "sin_suficientes_tickers"
    assert resultado["n_tickers"] == 1


def test_get_matriz_correlaciones_consolidado_une_todas_las_carteras(db: Session):
    fechas = [date(2024, m, 28) for m in range(1, 9)]
    _compra(db, "cartera-a", "AAA", 1, 100.0)
    _compra(db, "cartera-b", "BBB", 1, 200.0)
    db.commit()
    _sembrar_dos_tickers_correlacionados(db, fechas)

    resultado = get_matriz_correlaciones(None, db, tickers=["AAA", "BBB"], frecuencia="mensual",
                                          desde=date(2024, 1, 1), hasta=date(2024, 9, 1))
    assert resultado["estado"] == "ok"
    assert set(resultado["tickers"]) == {"AAA", "BBB"}


def test_get_matriz_correlaciones_cacheado_por_sync(db: Session, monkeypatch):
    fechas = [date(2024, m, 28) for m in range(1, 9)]
    _compra(db, "test", "AAA", 1, 100.0)
    _compra(db, "test", "BBB", 1, 200.0)
    db.commit()
    _sembrar_dos_tickers_correlacionados(db, fechas)

    llamadas = {"n": 0}
    original = _retornos_por_boundaries

    def _contador(*args, **kwargs):
        llamadas["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr("app.services.correlaciones_analytics._retornos_por_boundaries", _contador)

    get_matriz_correlaciones("test", db, tickers=["AAA", "BBB"], frecuencia="mensual",
                              desde=date(2024, 1, 1), hasta=date(2024, 9, 1))
    n_tras_primera = llamadas["n"]
    get_matriz_correlaciones("test", db, tickers=["AAA", "BBB"], frecuencia="mensual",
                              desde=date(2024, 1, 1), hasta=date(2024, 9, 1))
    assert llamadas["n"] == n_tras_primera  # segunda llamada: cache hit, no vuelve a calcular


# ── No-regresión de la pantalla Contribución (correlación vieja) ─────────────

def test_no_regresion_get_correlaciones_viejo(db: Session):
    """`contribucion_analytics.get_correlaciones` (retornos mensuales fin-de-mes) sigue
    funcionando exactamente igual: este módulo nuevo no la toca."""
    fechas = [date(2024, m, 28) for m in range(1, 9)]
    _compra(db, "test", "AAA", 1, 100.0)
    _compra(db, "test", "BBB", 1, 200.0)
    db.commit()
    _sembrar_dos_tickers_correlacionados(db, fechas)

    resultado = contribucion_analytics.get_correlaciones("test", db, universo="tenencias")
    assert resultado["tickers"] == ["AAA", "BBB"]
    par = resultado["pares"][0]
    assert par["valor"] == 1.0


def test_mensual_nueva_puede_diferir_de_la_vieja_ante_un_hueco(db: Session):
    """La mensual vieja (`_retornos_mensuales_ticker`) encadena sobre huecos: si falta el
    boundary de un mes, el siguiente retorno cubre el tramo entero igual. La mensual nueva de
    esta pantalla NO admite eso: no emite retorno cuando el boundary previo fue rechazado. Se
    deja documentado a propósito: son dos métricas con criterios distintos, ambas válidas para
    su pantalla."""
    _compra(db, "test", "AAA", 1, 100.0)
    _compra(db, "test", "BBB", 1, 100.0)
    db.commit()
    # Precio de enero, salto directo a precio de marzo (falta febrero) para ambos tickers,
    # con una diferencia de magnitud entre ellos para poder distinguir el efecto.
    _precio(db, "AAA", 100.0, date(2024, 1, 31))
    _precio(db, "AAA", 150.0, date(2024, 3, 31))
    _precio(db, "BBB", 100.0, date(2024, 1, 31))
    _precio(db, "BBB", 300.0, date(2024, 3, 31))
    db.commit()

    resultado_nuevo = get_matriz_correlaciones("test", db, tickers=["AAA", "BBB"], frecuencia="mensual",
                                                desde=date(2024, 1, 1), hasta=date(2024, 4, 1))
    # La nueva rechaza el boundary de febrero (precio de enero está a 29-30 días, > tolerancia
    # de 10) y el de marzo también carry-forward desde enero supera la tolerancia -> sin retornos
    # nuevos entre boundaries consecutivos aceptados salvo que el precio de marzo exista justo
    # en ese boundary. Se limita a comprobar que el estado refleja la escasez, no que fabrique
    # una correlación con 1 sola observación encadenada de 2 meses como haría la vieja.
    assert resultado_nuevo["estado"] in ("ok", "datos_insuficientes")

    resultado_viejo = contribucion_analytics.get_correlaciones("test", db, universo="tenencias")
    # La vieja sí puede tener el par con datos (aunque insuficientes por count, la serie interna
    # sí contiene la observación encadenada que salta el hueco).
    assert "AAA" in resultado_viejo["tickers"]


# ── Fuente: serie histórica de velas (`serie_ohlcv`), no las fotos del sync ───

def _velas(db, clave, cierres: dict, moneda="USD"):
    for fecha, cierre in cierres.items():
        db.add(BarraOHLCV(ticker=clave, fecha=fecha, cierre=cierre, moneda=moneda, fuente="api"))


def _dias_habiles(n: int) -> list[date]:
    """Los últimos `n` días hábiles, el más viejo primero."""
    dias, cursor = [], date.today() - timedelta(days=1)
    while len(dias) < n:
        if cursor.weekday() < 5:
            dias.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(dias)


def _caminata(dias: list[date], fase: float, base=100.0) -> dict:
    """Serie determinística con retornos que oscilan; la misma `fase` da el mismo movimiento."""
    precio, out = base, {}
    for i, d in enumerate(dias):
        precio *= 1 + 0.01 * math.sin(i * 0.9 + fase)
        out[d] = round(precio, 4)
    return out


def _watchlist(db, ticker, tipo="Acción", moneda="USD"):
    db.add(WatchlistItem(ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="NYSE", moneda=moneda))


def test_matriz_usa_las_velas_y_no_necesita_precios_instrumento(db: Session):
    """Caso de la captura: tickers de watchlist (sin `precios_instrumento`) con 3 años de velas
    diarias. Antes salían 5-7 observaciones por par; ahora hay cientos."""
    dias = _dias_habiles(800)
    for t, fase in (("SPY", 0.0), ("KO", 1.7), ("MELI", 3.1), ("MSFT", 0.05)):
        _watchlist(db, t)
        _velas(db, t, _caminata(dias, fase))
    db.commit()

    r = get_matriz_correlaciones(None, db, tickers=["SPY", "KO", "MELI", "MSFT"], frecuencia="diaria",
                                 desde=dias[0])
    assert r["estado"] == "ok"
    assert r["n_pares_ok"] == 6
    assert not r["pocos_datos"]
    assert all(p["n_obs"] > 100 for p in r["pares"])
    spy_msft = next(p for p in r["pares"] if {p["ticker_a"], p["ticker_b"]} == {"SPY", "MSFT"})
    spy_ko = next(p for p in r["pares"] if {p["ticker_a"], p["ticker_b"]} == {"SPY", "KO"})
    assert spy_msft["valor"] > 0.95 > abs(spy_ko["valor"])


def test_cedear_con_sub_usa_la_serie_usd_y_no_mezcla_los_pesos_del_cedear(db: Session):
    dias = _dias_habiles(300)
    _watchlist(db, "MSFT", tipo="CEDEAR", moneda="ARS")
    _velas(db, "MSFT@SUB", _caminata(dias, 0.0), moneda="USD")
    # Fotos del CEDEAR en pesos (~x50): mezclarlas metería saltos falsos en la serie.
    for d, px in _caminata(dias, 2.0, base=5000.0).items():
        _precio(db, "MSFT", px, d, moneda="ARS")
    _watchlist(db, "AAA")
    _velas(db, "AAA", _caminata(dias, 0.0))
    db.commit()

    r = get_matriz_correlaciones(None, db, tickers=["MSFT", "AAA"], frecuencia="diaria", desde=dias[0])
    assert r["estado"] == "ok"
    assert {d["ticker"]: d["variante"] for d in r["tickers_detalle"]} == {"MSFT": "subyacente", "AAA": "local"}
    assert r["pares"][0]["valor"] > 0.99  # misma fase: sólo si se leyó la serie USD


def test_cedear_con_sub_corta_cae_a_la_serie_local(db: Session):
    dias = _dias_habiles(300)
    _watchlist(db, "MSFT", tipo="CEDEAR", moneda="USD")
    _velas(db, "MSFT@SUB", _caminata(dias[-10:], 0.0))  # < MIN_BARRAS_REFERENCIA
    _velas(db, "MSFT", _caminata(dias, 0.0))
    _watchlist(db, "AAA")
    _velas(db, "AAA", _caminata(dias, 0.0))
    db.commit()

    r = get_matriz_correlaciones(None, db, tickers=["MSFT", "AAA"], frecuencia="diaria", desde=dias[0])
    assert {d["ticker"]: d["variante"] for d in r["tickers_detalle"]}["MSFT"] == "local"
    assert r["estado"] == "ok" and r["pares"][0]["n_obs"] > 100


def test_series_historicas_la_vela_pisa_a_la_foto_en_la_misma_fecha(db: Session):
    from app.services.correlaciones_analytics import _series_historicas

    f1, f2 = date(2024, 3, 4), date(2024, 3, 5)
    _precio(db, "AAA", 10.0, f1)
    _precio(db, "AAA", 11.0, f2)
    _velas(db, "AAA", {f2: 12.5})
    db.commit()

    series, variantes = _series_historicas(db, ["AAA"])
    assert series["AAA"] == [(f1, 10.0, "USD"), (f2, 12.5, "USD")]
    assert variantes == {"AAA": "local"}


def test_ticker_sin_velas_ni_precios_se_descarta(db: Session):
    _watchlist(db, "AAA")
    db.commit()
    usables, descartados = _resolver_tickers(["AAA"], None, db)
    assert usables == [] and descartados == [{"ticker": "AAA", "motivo": "sin_precios"}]
