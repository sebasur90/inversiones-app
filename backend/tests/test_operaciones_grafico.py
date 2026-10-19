"""Operaciones propias sobre el gráfico técnico: motor puro, adaptador con la base y endpoint."""
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
from app.services import inversiones_analytics as ia
from app.services import operaciones_grafico as og
from app.services import operaciones_grafico_engine as eng
from app.services.indicadores_engine import Barra


def _mov(tipo, cantidad=10.0, dias=0, precio=100.0):
    return MovimientoInversion(
        fecha=date(2026, 1, 1) + timedelta(days=dias), cartera="c", ticker="X",
        tipo_movimiento=tipo, cantidad=cantidad, precio=precio, moneda="ARS", comision=0.0,
    )


def _barra(dias, cierre, minimo=None, maximo=None):
    return Barra(fecha=date(2026, 1, 1) + timedelta(days=dias), cierre=cierre,
                 apertura=cierre, maximo=maximo, minimo=minimo, volumen=None)


# ── Motor puro ───────────────────────────────────────────────────────────────

def test_ciclos_abrir_cerrar_reabrir():
    movs = [_mov("compra", 10, 0), _mov("compra", 5, 1), _mov("venta", 15, 2), _mov("compra", 3, 3)]
    ciclos = eng.partir_en_ciclos(movs)
    assert [len(c) for c in ciclos] == [3, 1]


def test_ciclos_venta_parcial_no_cierra():
    movs = [_mov("compra", 10, 0), _mov("venta", 4, 1), _mov("venta", 6, 2), _mov("compra", 1, 3)]
    assert [len(c) for c in eng.partir_en_ciclos(movs)] == [3, 1]
    parcial = eng.partir_en_ciclos([_mov("compra", 10, 0), _mov("venta", 4, 1), _mov("compra", 1, 2)])
    assert len(parcial) == 1


def test_ciclos_dividendo_con_tenencia_cero_va_al_ultimo_ciclo():
    movs = [_mov("compra", 10, 0), _mov("venta", 10, 1), _mov("dividendo", None, 2)]
    ciclos = eng.partir_en_ciclos(movs)
    assert len(ciclos) == 1 and ciclos[0][-1].tipo_movimiento == "dividendo"


def test_ciclos_ingreso_o_venta_sin_ciclo_previo_se_descartan():
    assert eng.partir_en_ciclos([_mov("dividendo", None, 0), _mov("venta", 1, 1)]) == []


def test_precio_equivalente_proporcional():
    precio, aprox, motivo = eng.precio_equivalente(
        20200.0, _barra(0, 20000.0), _barra(0, 500.0, minimo=490.0, maximo=510.0))
    assert precio == pytest.approx(505.0)
    assert aprox is False and motivo is None


def test_precio_equivalente_recorta_al_rango():
    precio, aprox, motivo = eng.precio_equivalente(
        30000.0, _barra(0, 20000.0), _barra(0, 500.0, minimo=490.0, maximo=510.0))
    assert precio == 510.0 and aprox is True and motivo == eng.MOTIVO_RECORTADO


def test_precio_equivalente_sin_vela_local_usa_el_cierre():
    precio, aprox, motivo = eng.precio_equivalente(20000.0, None, _barra(0, 500.0))
    assert precio == 500.0 and aprox is True and motivo == eng.MOTIVO_SIN_VELA_LOCAL


def test_barra_de_fecha_exacta_cercana_y_fuera():
    barras = [_barra(0, 1), _barra(1, 1), _barra(4, 1)]  # hueco el 3 y el 4 de enero
    assert eng.barra_de_fecha(barras, date(2026, 1, 2)) == (barras[1], True)
    barra, exacta = eng.barra_de_fecha(barras, date(2026, 1, 3))
    assert barra is barras[2] and exacta is False
    assert eng.barra_de_fecha(barras, date(2025, 12, 31)) is None       # antes de la serie
    assert eng.barra_de_fecha(barras, date(2026, 1, 20)) is None        # lejos del último dato
    assert eng.barra_de_fecha(barras, date(2026, 1, 7))[0] is barras[2]  # operada "hoy"
    assert eng.barra_de_fecha([], date(2026, 1, 1)) is None


def test_costo_promedio_grafico_ponderado_e_ignora_sin_precio():
    assert eng.costo_promedio_grafico([(10, 100.0), (30, 200.0)]) == pytest.approx(175.0)
    assert eng.costo_promedio_grafico([(10, None), (10, 50.0)]) == pytest.approx(50.0)
    assert eng.costo_promedio_grafico([(10, None)]) is None


def test_porcentaje():
    assert eng.porcentaje(5.0, 100.0) == pytest.approx(5.0)
    assert eng.porcentaje(5.0, 0.0) is None and eng.porcentaje(None, 10.0) is None


# ── Adaptador con la base ────────────────────────────────────────────────────

BASE = date.today() - timedelta(days=100)
D1, D2, D3, D4, D5 = (BASE + timedelta(days=n) for n in (10, 20, 30, 40, 60))
MEP = 1000.0


def _poblar(db):
    db.add(InstrumentoInversion(ticker="MSFT", nombre="Microsoft CEDEAR", tipo_instrumento="CEDEAR",
                                mercado="BCBA", moneda="ARS"))
    db.add(EstadoMarketDataTicker(ticker="MSFT", simbolo_subyacente="MSFT", mercado_subyacente="NMS",
                                  moneda_subyacente="USD", resolucion_estado="ok"))
    db.add(IndiceMercado(fecha=BASE - timedelta(days=30), mep=MEP, fuente="sheet"))
    movs = [
        (D1, "compra", 10, 20000.0), (D2, "compra", 10, 22000.0),
        (D3, "venta", 20, 26000.0), (D4, "compra", 5, 24000.0),
    ]
    for fecha, tipo, cantidad, precio in movs:
        db.add(MovimientoInversion(fecha=fecha, cartera="c", ticker="MSFT", tipo_movimiento=tipo,
                                   cantidad=cantidad, precio=precio, moneda="ARS", comision=0.0))
    cierre_local = {D1: 20000.0, D2: 22000.0, D3: 26000.0, D4: 24000.0, D5: 27000.0}
    for i in range(80):
        f = BASE + timedelta(days=i)
        c = cierre_local.get(f, 21000.0)
        db.add(BarraOHLCV(ticker="MSFT", fecha=f, apertura=c, maximo=c * 1.01, minimo=c * 0.99,
                          cierre=c, volumen=1e5, moneda="ARS", fuente="yahoo"))
        db.add(BarraOHLCV(ticker="MSFT@SUB", fecha=f, apertura=500.0, maximo=501.0, minimo=499.0,
                          cierre=500.0, volumen=1e7, moneda="USD", fuente="yahoo"))
    db.add(PrecioInstrumento(ticker="MSFT", fecha=D5, precio=27000.0, moneda="ARS", fuente="sheet"))
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
def db(fabrica):
    s = fabrica()
    yield s
    s.close()


def test_resultado_por_ciclo_y_por_venta(db):
    r = og.get_operaciones_grafico("MSFT", "subyacente", db)
    cerrado, abierto = r["ciclos"]

    assert cerrado["abierto"] is False and cerrado["hasta"] == D3
    assert cerrado["comprado_usd"] == pytest.approx(420.0)
    assert cerrado["realizado_usd"] == pytest.approx(100.0)
    assert cerrado["resultado_pct"] == pytest.approx(100.0 / 420.0 * 100)

    assert abierto["abierto"] is True and abierto["cantidad_abierta"] == 5
    assert abierto["no_realizado_usd"] == pytest.approx(15.0)       # 5 × 27000 / 1000 − 120
    assert abierto["no_realizado_pct"] == pytest.approx(12.5)
    assert abierto["resultado_usd"] == pytest.approx(15.0)

    venta = next(o for o in r["operaciones"] if o["tipo"] == "venta")
    assert venta["resultado_usd"] == pytest.approx(100.0)
    assert venta["resultado_pct"] == pytest.approx(100.0 / 420.0 * 100)
    assert venta["ciclo"] == 1


def test_identidad_con_el_pnl_realizado(db):
    """Σ de los ciclos = P&L del ticker: lo que se ve en el gráfico es el número de la app."""
    r = og.get_operaciones_grafico("MSFT", "subyacente", db)
    fila = next(t for t in ia.get_pnl_realizado_no_realizado(None, db)["por_ticker"] if t["ticker"] == "MSFT")
    assert sum(c["realizado_usd"] for c in r["ciclos"]) == pytest.approx(fila["realizado_usd"])
    assert sum(c["no_realizado_usd"] or 0 for c in r["ciclos"]) == pytest.approx(fila["no_realizado_usd"])
    assert sum(c["ingresos_usd"] for c in r["ciclos"]) == pytest.approx(fila["ingresos_usd"])


def test_serie_local_en_la_misma_moneda_deja_el_precio_exacto(db):
    r = og.get_operaciones_grafico("MSFT", "local", db)
    assert r["moneda"] == "ARS"
    precios = [o["precio_grafico"] for o in r["operaciones"]]
    assert precios == [20000.0, 22000.0, 26000.0, 24000.0]
    assert not any(o["aproximado"] for o in r["operaciones"])


def test_subyacente_ubica_el_precio_relativo_a_la_vela_local(db):
    r = og.get_operaciones_grafico("MSFT", "subyacente", db)
    assert r["moneda"] == "USD"
    # Pagó al cierre local de cada día → la marca cae en el cierre del subyacente (500).
    assert [o["precio_grafico"] for o in r["operaciones"]] == [500.0] * 4
    assert [o["fecha_barra"] for o in r["operaciones"]] == [D1, D2, D3, D4]
    # Costo promedio de la posición abierta = su única compra.
    assert r["ciclos"][1]["costo_promedio_grafico"] == pytest.approx(500.0)
    assert r["ciclos"][0]["costo_promedio_grafico"] == pytest.approx(500.0)
    # Precio unitario real en USD MEP para la ficha.
    assert r["operaciones"][0]["precio_usd_mep"] == pytest.approx(20.0)


def test_operacion_anterior_a_la_serie_cuenta_como_fuera(db):
    db.add(MovimientoInversion(fecha=BASE - timedelta(days=10), cartera="c", ticker="MSFT",
                               tipo_movimiento="compra", cantidad=1, precio=18000.0, moneda="ARS", comision=0.0))
    db.commit()
    r = og.get_operaciones_grafico("MSFT", "subyacente", db)
    assert r["fuera_de_serie"] == 1
    fuera = next(o for o in r["operaciones"] if o["fecha"] == BASE - timedelta(days=10))
    assert fuera["precio_grafico"] is None and fuera["fecha_barra"] is None


def test_ticker_sin_movimientos_devuelve_vacio(db):
    r = og.get_operaciones_grafico("OTRO", "local", db)
    assert r["operaciones"] == [] and r["ciclos"] == []


def test_sin_precio_actual_el_no_realizado_queda_en_none(db):
    db.query(PrecioInstrumento).delete()
    db.commit()
    abierto = og.get_operaciones_grafico("MSFT", "subyacente", db)["ciclos"][1]
    assert abierto["no_realizado_usd"] is None and abierto["resultado_usd"] is None


# ── Endpoint ─────────────────────────────────────────────────────────────────

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


def test_endpoint_usa_la_serie_de_referencia_sin_variante(client):
    r = client.get("/api/inversiones/tecnico/MSFT/operaciones")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["variante"] == "subyacente" and cuerpo["moneda"] == "USD"
    assert len(cuerpo["operaciones"]) == 4 and len(cuerpo["ciclos"]) == 2


def test_endpoint_variante_local_explicita(client):
    cuerpo = client.get("/api/inversiones/tecnico/MSFT/operaciones?variante=local").json()
    assert cuerpo["variante"] == "local" and cuerpo["moneda"] == "ARS"


def test_endpoint_rechaza_variante_invalida_y_ticker_desconocido(client):
    assert client.get("/api/inversiones/tecnico/MSFT/operaciones?variante=referencia").status_code == 422
    assert client.get("/api/inversiones/tecnico/NOEXISTE/operaciones").status_code == 404
