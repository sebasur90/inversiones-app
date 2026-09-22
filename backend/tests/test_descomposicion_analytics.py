"""get_descomposicion: adaptador Session/DB del árbol de composición de cartera."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado
from app.services.descomposicion_analytics import get_descomposicion
from app.services.inversiones_analytics import get_exposicion


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    # Sin MEP, `_clasificados_valorizados` descarta toda posición (no puede convertir a ARS).
    session.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    session.commit()
    yield session
    session.close()


def _inst(db, ticker, tipo="Accion", sector=None, pais=None, moneda="USD"):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="NYSE",
        moneda=moneda, sector=sector, pais=pais,
    ))


def _compra(db, cartera, ticker, cantidad, precio, moneda="USD"):
    db.add(MovimientoInversion(
        fecha=date(2024, 1, 1), cartera=cartera, ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0,
    ))


def _precio(db, ticker, precio, fecha=date(2024, 6, 1), moneda="USD"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda))


def test_pesos_reconcilian_con_exposicion(db: Session):
    _inst(db, "AAA", tipo="CEDEAR", sector="Tecnologia", pais="Estados Unidos")
    _inst(db, "BBB", tipo="Bono", sector="Soberano", pais="Argentina")
    db.commit()
    _compra(db, "test", "AAA", 10, 50.0)
    _compra(db, "test", "BBB", 10, 30.0)
    _precio(db, "AAA", 50.0)
    _precio(db, "BBB", 30.0)
    db.commit()

    descomp = get_descomposicion("test", db)
    exposicion = get_exposicion("test", db)

    total_exposicion = sum(i["valor_usd"] for i in exposicion["ejes"][0]["items"])
    assert descomp["total_usd"] == pytest.approx(total_exposicion, abs=0.01)

    # Familia Renta variable (AAA, 500) + Renta fija (BBB, 300) sobre el total real.
    familias = {n["etiqueta"]: n for n in descomp["raiz"]}
    assert familias["Renta variable"]["valor_usd"] == pytest.approx(500.0, abs=0.01)
    assert familias["Renta fija"]["valor_usd"] == pytest.approx(300.0, abs=0.01)
    assert familias["Renta variable"]["porcentaje"] + familias["Renta fija"]["porcentaje"] == pytest.approx(100.0, abs=0.01)


def test_instrumentos_cuenta_tickers_distintos(db: Session):
    _inst(db, "AAA", tipo="CEDEAR", sector="Tecnologia", pais="AR")
    _inst(db, "BBB", tipo="CEDEAR", sector="Tecnologia", pais="AR")
    db.commit()
    _compra(db, "test", "AAA", 10, 10.0)
    _compra(db, "test", "BBB", 10, 10.0)
    _precio(db, "AAA", 10.0)
    _precio(db, "BBB", 10.0)
    db.commit()

    descomp = get_descomposicion("test", db)
    assert descomp["instrumentos"] == 2
    assert descomp["raiz"][0]["instrumentos"] == 2


def test_ticker_en_dos_carteras_se_consolida_en_consolidado(db: Session):
    _inst(db, "AAA", tipo="CEDEAR", sector="Tecnologia", pais="AR")
    db.commit()
    _compra(db, "cartera1", "AAA", 10, 10.0)
    _compra(db, "cartera2", "AAA", 5, 10.0)
    _precio(db, "AAA", 10.0)
    db.commit()

    descomp = get_descomposicion(None, db)
    # Una sola hoja para AAA, sumando ambas carteras (150 = 15 * 10).
    assert descomp["instrumentos"] == 1
    assert descomp["total_usd"] == pytest.approx(150.0, abs=0.01)
    ticker = descomp["raiz"][0]["hijos"][0]["hijos"][0]["hijos"][0]
    assert ticker["etiqueta"] == "AAA"
    assert ticker["valor_usd"] == pytest.approx(150.0, abs=0.01)


def test_ticker_sin_ficha_cae_en_sin_clasificar_y_no_desaparece(db: Session):
    """A diferencia de `get_exposicion` (que omite los tickers sin ficha), acá tienen que
    aparecer bajo "Sin clasificar" en vez de desaparecer del denominador."""
    _inst(db, "AAA", tipo="CEDEAR", sector="Tecnologia", pais="AR")
    db.commit()
    _compra(db, "test", "AAA", 10, 10.0)
    _compra(db, "test", "ZZZ", 10, 10.0)  # sin ficha en Instrumentos
    _precio(db, "AAA", 10.0)
    _precio(db, "ZZZ", 10.0)
    db.commit()

    descomp = get_descomposicion("test", db)
    assert descomp["total_usd"] == pytest.approx(200.0, abs=0.01)
    familias = {n["etiqueta"]: n for n in descomp["raiz"]}
    assert "Sin clasificar" in familias
    assert familias["Sin clasificar"]["valor_usd"] == pytest.approx(100.0, abs=0.01)
    assert familias["Sin clasificar"]["porcentaje"] == pytest.approx(50.0, abs=0.01)


def test_posicion_sin_precio_no_entra_al_arbol_pero_se_reporta(db: Session):
    _inst(db, "AAA", tipo="CEDEAR", sector="Tecnologia", pais="AR")
    _inst(db, "SINPRECIO", tipo="Bono", sector="Soberano", pais="AR")
    db.commit()
    _compra(db, "test", "AAA", 10, 10.0)
    _compra(db, "test", "SINPRECIO", 10, 10.0)  # nunca se le cargó un precio
    _precio(db, "AAA", 10.0)
    db.commit()

    descomp = get_descomposicion("test", db)
    assert descomp["posiciones_sin_precio"] == ["SINPRECIO"]
    todos_los_tickers = {
        t["etiqueta"]
        for fam in descomp["raiz"]
        for pais in fam["hijos"]
        for sector in pais["hijos"]
        for t in sector["hijos"]
    }
    assert "SINPRECIO" not in todos_los_tickers
    assert "AAA" in todos_los_tickers


def test_sin_posiciones_arbol_vacio(db: Session):
    descomp = get_descomposicion("vacia", db)
    assert descomp["raiz"] == []
    assert descomp["total_usd"] == 0.0
    assert descomp["instrumentos"] == 0
