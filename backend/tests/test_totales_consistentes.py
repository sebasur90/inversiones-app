"""El valor total de la cartera es el mismo en todas las pantallas que lo muestran.

La pantalla principal (`get_resumen`) valúa al costo de compra lo que no tiene cotización, así
que Exposición, Descomposición, Rebalanceo y Posiciones tienen que hacer lo mismo: si alguna
descarta posiciones, su total —y los pesos que salen de él, con los que se decide un
rebalanceo— queda por debajo del patrimonio real sin que nada lo explique.
"""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, IndiceMercado, InstrumentoInversion, MovimientoInversion, PrecioInstrumento
from app.services.descomposicion_analytics import get_descomposicion
from app.services.inversiones_analytics import (
    get_exposicion,
    get_rebalanceo,
    get_rendimiento_por_ticker,
    get_resumen,
)

FECHA = date(2024, 1, 1)
MEP = 1000.0


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(IndiceMercado(fecha=FECHA, mep=MEP, cer=100.0))
    session.commit()
    yield session
    session.close()


def _inst(db: Session, ticker: str, **kwargs) -> None:
    db.add(InstrumentoInversion(
        ticker=ticker,
        nombre=f"{ticker} SA",
        tipo_instrumento=kwargs.get("tipo_instrumento", "Accion"),
        mercado=kwargs.get("mercado", "NYSE"),
        moneda=kwargs.get("moneda", "USD"),
        sector=kwargs.get("sector"),
        pais=kwargs.get("pais"),
        fecha_vencimiento=kwargs.get("fecha_vencimiento"),
    ))


def _compra(db: Session, ticker: str, cantidad: float, precio: float, cartera="test", moneda="USD") -> None:
    db.add(MovimientoInversion(
        fecha=FECHA, cartera=cartera, ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0,
    ))


def _precio(db: Session, ticker: str, precio: float, moneda="USD") -> None:
    db.add(PrecioInstrumento(fecha=FECHA, ticker=ticker, precio=precio, moneda=moneda))


@pytest.fixture
def cartera_con_casos_raros(db: Session) -> Session:
    """Cartera con los tres casos que antes rompían los totales:

    - CONPRECIO: ficha completa y cotización (el caso feliz).
    - SINPRECIO: ficha, pero nunca se le cargó un precio → se valúa al costo.
    - SINFICHA: cotización, pero no está en la hoja Instrumentos.
    - SINSECTOR: ficha sin sector ni país ni vencimiento (campos opcionales).
    """
    _inst(db, "CONPRECIO", sector="Tecnologia", pais="US")
    _inst(db, "SINPRECIO", tipo_instrumento="Bono", sector="Soberano", pais="AR")
    _inst(db, "SINSECTOR")
    db.commit()
    _compra(db, "CONPRECIO", 10, 100.0)   # 1000 a precio de mercado (110 → 1100)
    _compra(db, "SINPRECIO", 10, 50.0)    # 500 al costo
    _compra(db, "SINFICHA", 10, 20.0)     # 200 a precio de mercado
    _compra(db, "SINSECTOR", 10, 30.0)    # 300 a precio de mercado
    _precio(db, "CONPRECIO", 110.0)
    _precio(db, "SINFICHA", 20.0)
    _precio(db, "SINSECTOR", 30.0)
    db.commit()
    return db


def test_exposicion_suma_el_mismo_total_que_la_pantalla_principal(cartera_con_casos_raros: Session):
    db = cartera_con_casos_raros
    resumen = get_resumen("test", db)
    exposicion = get_exposicion("test", db)

    assert exposicion["ejes"], "la cartera tiene posiciones: tiene que haber ejes"
    for eje in exposicion["ejes"]:
        total_usd = sum(it["valor_usd"] for it in eje["items"])
        total_ars = sum(it["valor_ars"] for it in eje["items"])
        assert total_usd == pytest.approx(resumen["valor_actual_usd"], abs=0.02), eje["eje"]
        assert total_ars == pytest.approx(resumen["valor_actual_ars"], abs=0.02), eje["eje"]
        assert sum(it["porcentaje"] for it in eje["items"]) == pytest.approx(100.0, abs=0.05), eje["eje"]


def test_exposicion_no_esconde_lo_que_no_tiene_ficha_ni_sector(cartera_con_casos_raros: Session):
    db = cartera_con_casos_raros
    ejes = {e["eje"]: {it["etiqueta"]: it for it in e["items"]} for e in get_exposicion("test", db)["ejes"]}

    # Sin ficha en Instrumentos: no desaparece del eje, cae en el bucket residual.
    assert ejes["Mercado"]["Sin clasificar"]["valor_usd"] == pytest.approx(200.0, abs=0.01)
    # Campos opcionales vacíos: el eje sigue sumando el patrimonio completo.
    assert ejes["Sector"]["Sin sector"]["valor_usd"] == pytest.approx(500.0, abs=0.01)   # SINFICHA + SINSECTOR
    assert ejes["País"]["Sin país"]["valor_usd"] == pytest.approx(500.0, abs=0.01)
    # Ningún instrumento de esta cartera vence: el donut del eje sigue cerrando en el patrimonio.
    assert ejes["Vencimiento"]["Sin vencimiento"]["valor_usd"] == pytest.approx(2100.0, abs=0.01)
    # Y el eje Ticker tiene las cuatro posiciones, no sólo las clasificadas.
    assert set(ejes["Ticker"]) == {"CONPRECIO", "SINPRECIO", "SINFICHA", "SINSECTOR"}


def test_descomposicion_y_rebalanceo_usan_el_mismo_total(cartera_con_casos_raros: Session):
    db = cartera_con_casos_raros
    esperado_usd = get_resumen("test", db)["valor_actual_usd"]

    descomp = get_descomposicion("test", db)
    assert descomp["total_usd"] == pytest.approx(esperado_usd, abs=0.02)

    for eje in get_rebalanceo("test", db)["ejes"]:
        assert eje["total_usd"] == pytest.approx(esperado_usd, abs=0.02), eje["eje"]


def test_posiciones_no_pierde_la_fila_sin_cotizacion(cartera_con_casos_raros: Session):
    db = cartera_con_casos_raros
    posiciones = {p["ticker"]: p for p in get_rendimiento_por_ticker("test", db)}

    assert set(posiciones) == {"CONPRECIO", "SINPRECIO", "SINFICHA", "SINSECTOR"}

    sin_cotizacion = posiciones["SINPRECIO"]
    assert sin_cotizacion["valuado_al_costo"] is True
    assert sin_cotizacion["fecha_precio"] is None
    assert sin_cotizacion["variacion_dia_pct"] is None
    # Valuada al costo, la posición no inventa ganancia ni pérdida.
    assert sin_cotizacion["valor_actual_usd"] == pytest.approx(500.0, abs=0.01)
    assert sin_cotizacion["rendimiento_simple_usd"] == pytest.approx(0.0, abs=1e-6)

    assert posiciones["CONPRECIO"]["valuado_al_costo"] is False

    total_posiciones = sum(p["valor_actual_usd"] for p in posiciones.values())
    assert total_posiciones == pytest.approx(get_resumen("test", db)["valor_actual_usd"], abs=0.02)


def test_avisos_dicen_que_quedo_aproximado_y_que_no_tiene_ficha(cartera_con_casos_raros: Session):
    avisos = get_exposicion("test", db=cartera_con_casos_raros)["avisos"]

    assert avisos["aproximadas"] == ["SINPRECIO"]
    assert avisos["sin_ficha"] == ["SINFICHA"]
    assert avisos["sin_valuar"] == []
    assert avisos["sin_valor_usd"] == []
    assert avisos["sin_valor_ars"] == []


def test_posicion_sigue_en_la_lista_sin_tipo_de_cambio_de_la_fecha_de_compra(db: Session):
    """Un movimiento en pesos anterior al primer MEP cargado no se puede expresar en USD.

    La tenencia no depende del tipo de cambio, así que la posición tiene que seguir apareciendo
    (la pantalla principal la cuenta): antes Posiciones perdía la fila entera, porque el
    recorrido de costos saltea ese movimiento y con él se iba la cuenta de unidades. Lo que no
    se puede calcular es el rendimiento, y eso queda en None en vez de salir inflado.
    """
    _inst(db, "BONOARS", moneda="ARS")
    db.commit()
    # Compra anterior a la única fila de IndiceMercado: no hay MEP para esa fecha.
    db.add(MovimientoInversion(
        fecha=date(2023, 6, 1), cartera="test", ticker="BONOARS", tipo_movimiento="compra",
        cantidad=1000, precio=50.0, moneda="ARS", comision=0.0,
    ))
    db.add(PrecioInstrumento(fecha=FECHA, ticker="BONOARS", precio=60.0, moneda="ARS"))
    db.commit()

    posiciones = get_rendimiento_por_ticker("test", db)
    assert [p["ticker"] for p in posiciones] == ["BONOARS"]
    fila = posiciones[0]
    assert fila["cantidad_actual"] == pytest.approx(1000.0)
    assert fila["costo_incompleto"] is True
    assert fila["rendimiento_simple_usd"] is None
    assert fila["rendimiento_simple_ars"] is None
    assert fila["valor_actual_usd"] == pytest.approx(60_000 / MEP, abs=0.01)
    assert fila["valor_actual_usd"] == pytest.approx(get_resumen("test", db)["valor_actual_usd"], abs=0.01)


def test_posicion_sin_precio_ni_costo_queda_fuera_del_total_pero_se_avisa(db: Session):
    """Una amortización/venta que deja tenencia sin ninguna compra previa no se puede valuar."""
    _inst(db, "RARO")
    db.commit()
    db.add(MovimientoInversion(
        fecha=FECHA, cartera="test", ticker="RARO", tipo_movimiento="venta",
        cantidad=-5.0, precio=10.0, moneda="USD", comision=0.0,
    ))
    db.commit()

    exposicion = get_exposicion("test", db)

    assert exposicion["avisos"]["sin_valuar"] == ["RARO"]
    assert all("RARO" not in {it["etiqueta"] for it in eje["items"]} for eje in exposicion["ejes"])
