from sqlalchemy import create_engine, Column, Integer, String, Date, Numeric, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "data.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class TipoCambio(Base):
    __tablename__ = "tipos_cambio"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    tipo = Column(String, nullable=False)
    compra = Column(Numeric(18, 4), nullable=True)
    venta = Column(Numeric(18, 4), nullable=True)

    __table_args__ = (UniqueConstraint("fecha", "tipo", name="uq_tipo_cambio"),)


class InstrumentoInversion(Base):
    __tablename__ = "instrumentos_inversion"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, nullable=False)
    nombre = Column(String, nullable=False)
    tipo_instrumento = Column(String, nullable=False)
    mercado = Column(String, nullable=False)
    moneda = Column(String, nullable=False)
    pais = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    fecha_vencimiento = Column(Date, nullable=True)
    objetivo_modo = Column(String, nullable=True)
    objetivo_valor = Column(Numeric(18, 6), nullable=True)
    stop_loss_modo = Column(String, nullable=True)
    stop_loss_valor = Column(Numeric(18, 6), nullable=True)


class MovimientoInversion(Base):
    __tablename__ = "movimientos_inversion"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    cartera = Column(String, nullable=False)
    ticker = Column(String, ForeignKey("instrumentos_inversion.ticker"), nullable=False)
    tipo_movimiento = Column(String, nullable=False)  # compra, venta, dividendo, cupon, amortizacion
    cantidad = Column(Numeric(18, 6), nullable=True)
    precio = Column(Numeric(18, 6), nullable=False)
    moneda = Column(String, nullable=False)
    comision = Column(Numeric(18, 2), nullable=False, default=0)


class PrecioInstrumento(Base):
    __tablename__ = "precios_instrumento"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    ticker = Column(String, ForeignKey("instrumentos_inversion.ticker"), nullable=False)
    precio = Column(Numeric(18, 6), nullable=False)
    moneda = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("fecha", "ticker", name="uq_precio_instrumento"),)


class IndiceMercado(Base):
    __tablename__ = "indices_mercado"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False, unique=True)
    cer = Column(Numeric(18, 6), nullable=True)
    mep = Column(Numeric(18, 6), nullable=True)


class BenchmarkValor(Base):
    __tablename__ = "benchmarks_mercado"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    benchmark = Column(String, nullable=False)
    valor = Column(Numeric(18, 6), nullable=False)

    __table_args__ = (UniqueConstraint("fecha", "benchmark", name="uq_benchmark_valor"),)


class ObjetivoInversion(Base):
    __tablename__ = "objetivos_inversion"
    id = Column(Integer, primary_key=True, index=True)
    cartera = Column(String, nullable=False, index=True)
    nombre = Column(String, nullable=False)
    icono = Column(String, nullable=False, default="🎯")
    monto_usd = Column(Numeric(18, 2), nullable=False)
    fecha_limite = Column(Date, nullable=False)


class RebalanceoObjetivo(Base):
    __tablename__ = "rebalanceo_objetivos"
    id = Column(Integer, primary_key=True, index=True)
    cartera = Column(String, nullable=True, index=True)  # None = Consolidado
    eje = Column(String, nullable=False)  # "Cartera" | "Tipo" | "Sector" | "Ticker"
    categoria = Column(String, nullable=False)
    porcentaje_objetivo = Column(Numeric(6, 2), nullable=False)

    __table_args__ = (UniqueConstraint("cartera", "eje", "categoria", name="uq_rebalanceo_objetivo"),)


class ConfiguracionCartera(Base):
    __tablename__ = "configuracion_carteras"
    id = Column(Integer, primary_key=True, index=True)
    cartera = Column(String, nullable=True, unique=True, index=True)  # None = default/Consolidado
    benchmark = Column(String, nullable=True)
    rendimiento_objetivo = Column(Numeric(6, 2), nullable=True)
    peso_maximo = Column(Numeric(6, 2), nullable=True)
    peso_minimo = Column(Numeric(6, 2), nullable=True)
    tolerancia = Column(Numeric(6, 2), nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)

    # sqlite create_all no agrega columnas nuevas en tablas existentes.
    # aseguramos compatibilidad con DB antiguas que no tenían es_jubilacion.
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(objetivos_inversion)"))
        cols = [row[1] for row in result.fetchall()]
        if 'es_jubilacion' not in cols:
            conn.execute(text("ALTER TABLE objetivos_inversion ADD COLUMN es_jubilacion INTEGER NOT NULL DEFAULT 0"))
            conn.commit()

        # aseguramos compatibilidad con DB antiguas que no tenían objetivo/stop loss.
        result = conn.execute(text("PRAGMA table_info(instrumentos_inversion)"))
        cols = [row[1] for row in result.fetchall()]
        for columna, tipo in (
            ("objetivo_modo", "TEXT"),
            ("objetivo_valor", "NUMERIC"),
            ("stop_loss_modo", "TEXT"),
            ("stop_loss_valor", "NUMERIC"),
        ):
            if columna not in cols:
                conn.execute(text(f"ALTER TABLE instrumentos_inversion ADD COLUMN {columna} {tipo}"))
                conn.commit()
