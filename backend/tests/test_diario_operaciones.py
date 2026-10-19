"""Diario de operaciones y comparación con la estrategia (Etapa 6)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base, BarraOHLCV, EstadoMarketDataTicker, IndiceMercado, InstrumentoInversion,
    MovimientoInversion, PrecioInstrumento, get_db,
)
from app.main import app
from app.services import comparacion_propia as cp
from app.services import diario_operaciones as dop
from app.services import diario_operaciones_engine as eng

# ── Motor puro: resumen y frases ─────────────────────────────────────────────


def _op(tipo="compra", **campos):
    base = {"tipo": tipo, "rsi": None, "dist_sma200_pct": None, "rango_52s_pct": None,
            "post_30_pct": None, "post_90_pct": None, "post_180_pct": None}
    return {**base, **campos}


def _ciclo(pct, usd, abierto=False):
    return {"abierto": abierto, "resultado_pct": pct, "resultado_usd": usd}


def test_resumen_de_compras_y_ventas():
    ops = [
        _op(rsi=70, dist_sma200_pct=10, rango_52s_pct=90), _op(rsi=50, dist_sma200_pct=-5, rango_52s_pct=80),
        _op(rsi=60, dist_sma200_pct=3, rango_52s_pct=70), _op(rsi=None),
        _op("venta", post_90_pct=15), _op("venta", post_90_pct=2), _op("venta", post_90_pct=None),
        _op("amortizacion"),
    ]
    r = eng.resumir(ops, [_ciclo(10.0, 5.0), _ciclo(-4.0, -2.0), _ciclo(None, None), _ciclo(3.0, 1.0, abierto=True)])
    assert (r["n_compras"], r["n_ventas"]) == (4, 3)               # la amortización no es una venta
    assert r["rsi_medio_compras"] == pytest.approx(60.0) and r["n_rsi"] == 3
    assert r["pct_compras_sobre_sma200"] == pytest.approx(200 / 3)
    assert r["rango_52s_medio_compras"] == pytest.approx(80.0)
    assert (r["n_ventas_con_post90"], r["n_ventas_subieron"]) == (2, 1)
    assert (r["n_ciclos_cerrados"], r["n_ciclos_ganadores"]) == (2, 1)      # sin los abiertos ni sin resultado
    assert r["resultado_medio_ciclos_pct"] == pytest.approx(3.0)


def test_resumen_vacio_no_lanza():
    r = eng.resumir([], [])
    assert r["rsi_medio_compras"] is None and r["pct_compras_sobre_sma200"] is None
    assert eng.frases(r) == []


def test_frases_comprar_cerca_de_maximos_y_vender_antes_de_subas():
    ops = [_op(rsi=65, dist_sma200_pct=8, rango_52s_pct=r) for r in (85, 90, 95)]
    ops += [_op("venta", post_90_pct=p) for p in (20, 12, 3)]
    f = eng.frases(eng.resumir(ops, [_ciclo(5.0, 2.0), _ciclo(-2.0, -1.0), _ciclo(9.0, 4.0)]))
    assert any("cerca de máximos" in x and "90%" in x for x in f)
    assert any("a favor de la tendencia" in x and "3 de 3" in x for x in f)
    assert any("RSI alto" in x for x in f)
    assert any("en 2 de 3 ventas" in x for x in f)
    assert any("3 posiciones cerradas ganaste en 2" in x and "+4.0%" in x for x in f)


def test_frases_comprar_cerca_de_minimos_y_caidas():
    ops = [_op(rsi=30, dist_sma200_pct=-10, rango_52s_pct=r) for r in (5, 10, 15)]
    f = eng.frases(eng.resumir(ops, []))
    assert any("cerca de mínimos" in x for x in f)
    assert any("Comprás las caídas" in x for x in f)
    assert any("RSI bajo" in x for x in f)


def test_sin_muestra_suficiente_no_hay_frases():
    ops = [_op(rsi=90, dist_sma200_pct=20, rango_52s_pct=99) for _ in range(eng.MIN_MUESTRA - 1)]
    assert eng.frases(eng.resumir(ops, [])) == []


# ── Comparación con la estrategia ────────────────────────────────────────────

D0 = date(2026, 1, 5)
FECHAS = [D0 + timedelta(days=i) for i in range(20)]
ESTRATEGIA = [100.0] * 10 + [100.0 + 2 * (i - 9) for i in range(10, 20)]       # entra en la barra 10
BUYHOLD = [100.0 + i for i in range(20)]


def _c(desde, hasta, **extra):
    return {"ciclo": 1, "desde": FECHAS[desde], "hasta": FECHAS[hasta] if hasta is not None else None,
            "abierto": hasta is None, "resultado_usd": 12.0, "resultado_pct": 7.5, **extra}


def test_tramo_de_la_curva_entre_las_fechas_del_ciclo():
    [fila] = cp.comparar([_c(12, 16)], FECHAS, 0, ESTRATEGIA, BUYHOLD)
    assert fila["tramo_desde"] == FECHAS[12] and fila["tramo_hasta"] == FECHAS[16]
    assert fila["estrategia_pct"] == pytest.approx((ESTRATEGIA[16] / ESTRATEGIA[12] - 1) * 100)
    assert fila["buy_hold_pct"] == pytest.approx((116 / 112 - 1) * 100)
    assert fila["tu_resultado_pct"] == 7.5 and fila["recortado"] is False


def test_estrategia_fuera_del_mercado_en_ese_tramo_rinde_cero():
    [fila] = cp.comparar([_c(2, 6)], FECHAS, 0, ESTRATEGIA, BUYHOLD)
    assert fila["estrategia_pct"] == 0.0 and fila["buy_hold_pct"] > 0


def test_ciclo_abierto_llega_a_la_ultima_barra():
    [fila] = cp.comparar([_c(15, None)], FECHAS, 0, ESTRATEGIA, BUYHOLD)
    assert fila["tramo_hasta"] == FECHAS[-1] and fila["hasta"] is None and fila["abierto"]


def test_ciclo_anterior_al_periodo_queda_recortado_y_uno_fuera_se_omite():
    # El período del backtest arranca en la barra 8; un ciclo de las barras 2 a 12 se recorta a 8-12.
    filas = cp.comparar([_c(2, 12), _c(3, 5)], FECHAS, 8, ESTRATEGIA, BUYHOLD)
    assert len(filas) == 1
    assert filas[0]["recortado"] is True and filas[0]["tramo_desde"] == FECHAS[8]
    assert filas[0]["buy_hold_pct"] == pytest.approx((112 / 108 - 1) * 100)


def test_posterior_al_periodo_se_omite_y_sin_barras_no_lanza():
    assert cp.comparar([{**_c(1, 2), "desde": FECHAS[-1] + timedelta(days=5), "hasta": None}], FECHAS, 0, ESTRATEGIA, BUYHOLD) == []
    assert cp.comparar([_c(1, 2)], [], 0, [], []) == []


# ── Con la base ──────────────────────────────────────────────────────────────

HOY = date.today()
BASE = HOY - timedelta(days=100)
MEP = 1000.0


def _poblar(db):
    db.add(IndiceMercado(fecha=BASE - timedelta(days=30), mep=MEP, fuente="sheet"))
    for ticker, tipo in (("GGAL", "Accion"), ("YPFD", "Accion"), ("MSFT", "CEDEAR")):
        db.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="BCBA", moneda="ARS"))
    db.add(EstadoMarketDataTicker(ticker="MSFT", simbolo_subyacente="MSFT", mercado_subyacente="NMS",
                                  moneda_subyacente="USD", resolucion_estado="ok"))
    movs = [
        ("GGAL", 10, "compra", 10, 1100.0), ("GGAL", 30, "venta", 10, 1300.0),
        ("YPFD", 15, "compra", 5, 2015.0), ("YPFD", 40, "venta", 5, 1800.0),
        ("YPFD", 50, "compra", 5, 1900.0),
        ("MSFT", 20, "compra", 2, 20000.0), ("MSFT", 60, "dividendo", None, 2000.0),
    ]
    for ticker, dia, tipo, cant, precio in movs:
        db.add(MovimientoInversion(fecha=BASE + timedelta(days=dia), cartera="c", ticker=ticker, tipo_movimiento=tipo,
                                   cantidad=cant, precio=precio, moneda="ARS", comision=0.0))
    for i in range(90):
        f = BASE + timedelta(days=i)
        for ticker, c in (("GGAL", 1000.0 + 10 * i), ("YPFD", 2000.0 + i), ("MSFT", 20000.0)):
            db.add(BarraOHLCV(ticker=ticker, fecha=f, apertura=c, maximo=c * 1.01, minimo=c * 0.99, cierre=c,
                              volumen=1e5, moneda="ARS", fuente="yahoo"))
        db.add(BarraOHLCV(ticker="MSFT@SUB", fecha=f, apertura=500.0, maximo=501.0, minimo=499.0, cierre=500.0,
                          volumen=1e7, moneda="USD", fuente="yahoo"))
    db.add(PrecioInstrumento(ticker="YPFD", fecha=BASE + timedelta(days=89), precio=2089.0, moneda="ARS", fuente="sheet"))
    db.commit()


@pytest.fixture
def fabrica():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)
    db = sesion()
    _poblar(db)
    db.close()
    return sesion


@pytest.fixture
def client(fabrica):
    def override():
        s = fabrica()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_diario_reune_los_tickers_ordenado_y_usa_la_serie_de_referencia(fabrica):
    d = dop.get_diario(fabrica())
    ops = d["operaciones"]
    assert [(o["ticker"], o["tipo"]) for o in ops] == [
        ("YPFD", "compra"), ("YPFD", "venta"), ("GGAL", "venta"), ("MSFT", "compra"), ("YPFD", "compra"),
        ("GGAL", "compra"),
    ]
    assert [o["fecha"] for o in ops] == sorted((o["fecha"] for o in ops), reverse=True)
    assert {o["ticker"] for o in ops} == {"GGAL", "YPFD", "MSFT"}          # el dividendo no es del diario
    assert {o["tipo"] for o in ops} <= {"compra", "venta", "amortizacion"}
    assert next(o for o in ops if o["ticker"] == "MSFT")["variante"] == "subyacente"
    assert next(o for o in ops if o["ticker"] == "GGAL")["variante"] == "local"
    assert d["resumen"]["n_compras"] == 4 and d["resumen"]["n_ventas"] == 2


def test_diario_resultados_y_despues_de_vender(fabrica):
    ops = {(o["ticker"], o["tipo"], o["fecha"]): o for o in dop.get_diario(fabrica())["operaciones"]}
    venta_ggal = ops[("GGAL", "venta", BASE + timedelta(days=30))]
    assert venta_ggal["resultado_pct"] == pytest.approx(200 / 1100 * 100)    # vendió a 1300 lo que compró a 1100
    # GGAL sigue subiendo 10 por día: a 30 días el cierre era 1300 + 300 → +23 %.
    assert venta_ggal["post_30_pct"] == pytest.approx((1600 / 1300 - 1) * 100, abs=0.01)
    assert venta_ggal["rsi"] == 100.0                       # sólo subió: RSI al tope
    venta_ypf = ops[("YPFD", "venta", BASE + timedelta(days=40))]
    assert venta_ypf["resultado_usd"] == pytest.approx(5 * (1800 - 2015) / MEP, abs=0.01)


def test_diario_resumen_cuenta_ciclos_cerrados(fabrica):
    r = dop.get_diario(fabrica())["resumen"]
    assert r["n_ciclos_cerrados"] == 2 and r["n_ciclos_ganadores"] == 1    # GGAL ganó, YPFD perdió


def test_diario_sin_movimientos(fabrica):
    db = fabrica()
    db.query(MovimientoInversion).delete()
    db.commit()
    d = dop.get_diario(db)
    assert d["operaciones"] == [] and d["frases"] == [] and d["resumen"]["n_compras"] == 0


def test_endpoint_diario(client):
    r = client.get("/api/inversiones/operaciones/diario")
    assert r.status_code == 200
    d = r.json()
    assert len(d["operaciones"]) == 6 and d["resumen"]["n_ventas"] == 2
    assert {"ticker", "fecha", "tipo", "rsi", "post_90_pct", "resultado_usd"} <= set(d["operaciones"][0])
    assert isinstance(d["frases"], list) and d["tickers_sin_serie"] == []


# ── Backtest: tus ciclos contra la estrategia ────────────────────────────────

DEF_SIN_OPERAR = {
    "version": 1,
    "indicadores": [{"id": "mm", "tipo": "SMA", "params": {"periodo": 200}}],
    "entrada": {"op": "y", "condiciones": [{"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"ref": "mm"}}]},
    "salida": {"op": "y", "condiciones": [{"op": "cruce_abajo", "izq": {"campo": "cierre"}, "der": {"ref": "mm"}}]},
    "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
    "ejecucion": {"comision_pct": 0.0, "slippage_pct": 0.0, "capital_inicial": 100000.0},
}


def test_backtest_trae_mis_ciclos_contra_la_estrategia(client):
    r = client.post("/api/inversiones/tecnico/GGAL/backtest", json={"definicion": DEF_SIN_OPERAR, "variante": "local"})
    assert r.status_code == 200, r.text
    d = r.json()
    [ciclo] = d["mis_ciclos"]
    assert ciclo["abierto"] is False and ciclo["tramo_desde"] == str(BASE + timedelta(days=10))
    assert ciclo["tramo_hasta"] == str(BASE + timedelta(days=30))
    assert ciclo["estrategia_pct"] == pytest.approx(0.0)                    # la SMA(200) nunca llega a operar
    assert ciclo["buy_hold_pct"] == pytest.approx((1300 / 1100 - 1) * 100)
    assert ciclo["tu_resultado_pct"] == pytest.approx(200 / 1100 * 100)


def test_backtest_de_un_ticker_que_nunca_operaste_no_trae_mis_ciclos(client, fabrica):
    db = fabrica()
    db.add(InstrumentoInversion(ticker="NUEVO", nombre="NUEVO", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))
    for i in range(60):
        db.add(BarraOHLCV(ticker="NUEVO", fecha=BASE + timedelta(days=i), cierre=100.0 + i, apertura=100.0 + i,
                          maximo=101.0 + i, minimo=99.0 + i, volumen=1.0, moneda="ARS", fuente="yahoo"))
    db.commit()
    db.close()
    r = client.post("/api/inversiones/tecnico/NUEVO/backtest", json={"definicion": DEF_SIN_OPERAR, "variante": "local"})
    assert r.status_code == 200 and r.json()["mis_ciclos"] is None
