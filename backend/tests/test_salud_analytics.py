"""Tests para el adaptador de Salud de cartera (backend/app/services/salud_analytics.py)."""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, MovimientoInversion, InstrumentoInversion, PrecioInstrumento, IndiceMercado
from app.services.salud_analytics import _inventario_posiciones, get_salud


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(IndiceMercado(fecha=date(2024, 1, 1), mep=1000.0))
    session.commit()
    yield session
    session.close()


def _inst(db, ticker, tipo="Bono", sector=None, pais=None, moneda="USD", fecha_vencimiento=None):
    db.add(InstrumentoInversion(
        ticker=ticker, nombre=ticker, tipo_instrumento=tipo, mercado="MERVAL",
        moneda=moneda, sector=sector, pais=pais, fecha_vencimiento=fecha_vencimiento,
    ))


def _compra(db, cartera, ticker, cantidad, precio, moneda="USD", fecha=date(2024, 1, 1)):
    db.add(MovimientoInversion(
        fecha=fecha, cartera=cartera, ticker=ticker, tipo_movimiento="compra",
        cantidad=cantidad, precio=precio, moneda=moneda, comision=0.0,
    ))


def _precio(db, ticker, precio, fecha, moneda="USD", fuente="sheet"):
    db.add(PrecioInstrumento(fecha=fecha, ticker=ticker, precio=precio, moneda=moneda, fuente=fuente))


class TestInventarioPosiciones:
    def test_detecta_posicion_sin_precio(self, db: Session):
        _inst(db, "SINPRECIO")
        db.commit()
        _compra(db, "test", "SINPRECIO", 10, 100.0)
        db.commit()

        inv = {it["ticker"]: it for it in _inventario_posiciones("test", db)}
        assert inv["SINPRECIO"]["sin_precio"] is True
        assert inv["SINPRECIO"]["valor_usd"] is None

    def test_detecta_precio_desactualizado(self, db: Session):
        _inst(db, "VIEJO")
        db.commit()
        _compra(db, "test", "VIEJO", 10, 100.0)
        _precio(db, "VIEJO", 100.0, date.today() - timedelta(days=60))
        db.commit()

        inv = {it["ticker"]: it for it in _inventario_posiciones("test", db)}
        assert inv["VIEJO"]["dias_precio"] == 60
        assert inv["VIEJO"]["sin_precio"] is False
        assert inv["VIEJO"]["fuente_precio"] == "sheet"

    def test_detecta_instrumento_sin_sector_ni_pais(self, db: Session):
        _inst(db, "AL30")  # sin sector ni país
        db.commit()
        _compra(db, "test", "AL30", 10, 100.0)
        _precio(db, "AL30", 100.0, date.today())
        db.commit()

        inv = {it["ticker"]: it for it in _inventario_posiciones("test", db)}
        assert inv["AL30"]["sector"] is None
        assert inv["AL30"]["pais"] is None
        assert inv["AL30"]["sin_ficha"] is False

    def test_ticker_sin_ficha_en_instrumentos(self, db: Session):
        _compra(db, "test", "FANTASMA", 10, 100.0)
        _precio(db, "FANTASMA", 100.0, date.today())
        db.commit()

        inv = {it["ticker"]: it for it in _inventario_posiciones("test", db)}
        assert inv["FANTASMA"]["sin_ficha"] is True
        assert inv["FANTASMA"]["valor_usd"] == pytest.approx(1000.0)

    def test_pesos_suman_cien(self, db: Session):
        _inst(db, "A")
        _inst(db, "B")
        db.commit()
        _compra(db, "test", "A", 10, 100.0)
        _compra(db, "test", "B", 10, 300.0)
        _precio(db, "A", 100.0, date.today())
        _precio(db, "B", 300.0, date.today())
        db.commit()

        inv = _inventario_posiciones("test", db)
        pesos = sum(it["peso_pct"] for it in inv)
        assert pesos == pytest.approx(100.0, abs=0.1)


class TestGetSalud:
    def _cartera_basica(self, db: Session, cartera="test"):
        _inst(db, "AL30", tipo="Bono", sector="Soberano", pais="AR", fecha_vencimiento=date(2030, 1, 1))
        db.commit()
        _compra(db, cartera, "AL30", 100, 50.0)
        _precio(db, "AL30", 55.0, date.today())
        db.commit()

    def test_devuelve_claves_esperadas(self, db: Session):
        self._cartera_basica(db)
        salud = get_salud("test", db)
        assert salud["cartera"] == "test"
        assert set(salud["resumen"].keys()) == {"n_revisar", "n_atencion", "n_normal", "n_sin_datos"}
        claves_dim = {d["clave"] for d in salud["dimensiones"]}
        assert claves_dim == {
            "riesgo", "concentracion", "diversificacion", "liquidez",
            "costos", "vencimientos", "balance_objetivo", "calidad_datos",
        }
        assert isinstance(salud["observaciones"], list)
        assert isinstance(salud["indicadores"], list)
        assert isinstance(salud["exposicion_moneda"], list)
        assert isinstance(salud["exposicion_tipo"], list)

    def test_consolidado_none_no_rompe(self, db: Session):
        self._cartera_basica(db)
        salud = get_salud(None, db)
        assert salud["cartera"] is None
        assert len(salud["dimensiones"]) == 8

    def test_concentracion_total_en_un_solo_bono_da_revisar(self, db: Session):
        self._cartera_basica(db)
        salud = get_salud("test", db)
        dim_conc = next(d for d in salud["dimensiones"] if d["clave"] == "concentracion")
        assert dim_conc["estado"] == "revisar"
        obs_ticker = [o for o in salud["observaciones"] if o["id"] == "peso_ticker:AL30"]
        assert obs_ticker
        assert obs_ticker[0]["pantalla"] == "/ticker/AL30"

    def test_liquidez_normal_con_vencimiento_corto(self, db: Session):
        _inst(db, "LECAP", tipo="Letra", fecha_vencimiento=date.today() + timedelta(days=60))
        db.commit()
        _compra(db, "test", "LECAP", 100, 10.0)
        _precio(db, "LECAP", 10.0, date.today())
        db.commit()

        salud = get_salud("test", db)
        dim_liq = next(d for d in salud["dimensiones"] if d["clave"] == "liquidez")
        assert dim_liq["estado"] == "normal"

    def test_cartera_sin_movimientos_no_rompe(self, db: Session):
        salud = get_salud("vacia", db)
        assert salud["cartera"] == "vacia"
        assert salud["resumen"]["n_sin_datos"] >= 1
