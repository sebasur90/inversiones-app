from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Numeric, ForeignKey, UniqueConstraint, text, JSON
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
    # "iol" (API autenticada de InvertirOnline) | "sheet" (pestaña Precios, cargada a mano) |
    # "api" (fuentes públicas de fallback: data912 para el precio del día + analisistecnico para
    # el backfill histórico). Precedencia por (ticker, fecha): iol > sheet > api — IOL es la
    # fuente primaria de cotizaciones y el Sheet cubre lo que IOL no cotiza (ver
    # services/market_data/precios.py).
    fuente = Column(String, nullable=False, default="sheet", server_default="sheet")

    __table_args__ = (UniqueConstraint("fecha", "ticker", name="uq_precio_instrumento"),)


class IndiceMercado(Base):
    __tablename__ = "indices_mercado"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False, unique=True)
    cer = Column(Numeric(18, 6), nullable=True)
    mep = Column(Numeric(18, 6), nullable=True)
    riesgo_pais = Column(Numeric(18, 6), nullable=True)  # puntos básicos (EMBI+), sólo fuente='api'
    # "sheet" (Movimientos/Precios/Tipos de Cambio) | "api" (completado automáticamente, ver
    # services/market_data). El Sheet siempre gana; "api" sólo llena fechas que el Sheet no cubre.
    fuente = Column(String, nullable=False, default="sheet", server_default="sheet")


class BenchmarkValor(Base):
    __tablename__ = "benchmarks_mercado"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    benchmark = Column(String, nullable=False)
    valor = Column(Numeric(18, 6), nullable=False)
    fuente = Column(String, nullable=False, default="sheet", server_default="sheet")

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


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    duration_ms = Column(Integer, nullable=False)
    # filas_advertencia / filas_error cuentan ValidationIssue emitidos, no filas únicas
    # (una fila puede generar más de un issue).
    filas_procesadas = Column(Integer, nullable=False, default=0)
    filas_validas = Column(Integer, nullable=False, default=0)
    filas_advertencia = Column(Integer, nullable=False, default=0)
    filas_error = Column(Integer, nullable=False, default=0)
    health_score = Column(Integer, nullable=False)
    resultado = Column(String, nullable=False)  # "ok" | "con_advertencias" | "con_errores"


class SyncIssue(Base):
    __tablename__ = "sync_issues"
    id = Column(Integer, primary_key=True, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id"), nullable=False, index=True)
    tab = Column(String, nullable=False)
    fila = Column(Integer, nullable=True)
    campo = Column(String, nullable=True)
    regla = Column(String, nullable=False)
    severidad = Column(String, nullable=False)  # "critico" | "advertencia" | "info"
    mensaje = Column(String, nullable=False)
    impacto = Column(String, nullable=False)


class EstadoMarketDataTicker(Base):
    """Estado persistente por ticker de la integración automática de precios (market_data).

    Evita recalibrar/reintentar contra referencias que envejecen:
      - `factor_escala`: 1.0 | 0.01, la escala ya determinada contra el último precio manual.
        Se reusa tal cual mientras no aparezca un precio manual más nuevo que `factor_fecha`.
      - `backfill_estado`: None | 'sin_serie' (analisistecnico no cubre el ticker) |
        'sin_serie_iol' (tampoco lo cubre IOL, la última fuente) | 'completo' (la serie histórica
        ya no baja más). Ninguno de los tres vuelve a consumir cupo de backfill.
      - `backfill_intento`: fecha del último intento (para reintentar 'sin_serie' cada ~90 días).
    """
    __tablename__ = "estado_market_data_ticker"
    ticker = Column(String, primary_key=True)
    factor_escala = Column(Numeric(10, 6), nullable=True)
    factor_fecha = Column(Date, nullable=True)
    backfill_estado = Column(String, nullable=True)
    backfill_intento = Column(Date, nullable=True)


class WatchlistItem(Base):
    """Espejo de la pestaña `Watchlist` del Sheet: instrumentos a seguir que no están en cartera.

    `objetivo` es el precio al que el usuario quiere comprar. La alerta se dispara "hacia abajo"
    (precio de mercado acercándose al objetivo), a diferencia del `objetivo_valor` de
    `InstrumentoInversion`, que es un precio de venta y se cruza hacia arriba.

    Se reescribe entera en cada sync, como todas las pestañas -- por eso el precio observado vive
    aparte, en `PrecioWatchlist`.
    """
    __tablename__ = "watchlist"
    ticker = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    tipo_instrumento = Column(String, nullable=False, default="")
    mercado = Column(String, nullable=False, default="")
    moneda = Column(String, nullable=False, default="ARS")
    pais = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    objetivo = Column(Numeric(18, 6), nullable=True)


class PrecioWatchlist(Base):
    """Último precio de mercado observado para un ticker de la watchlist.

    No va a `precios_instrumento` por dos razones: esos tickers no están en
    `instrumentos_inversion` (la FK del ticker), y la serie de precios la leen patrimonio,
    exposición y riesgo -- meter ahí instrumentos que no se poseen falsearía esos números.

    Tabla aparte de `watchlist` (y no columnas de esa tabla) para que el precio sobreviva al
    DELETE+INSERT de cada sync y a una caída transitoria de la API, igual que
    `EstadoMarketDataTicker`. Sólo se guarda el último precio: la watchlist no necesita serie
    histórica.
    """
    __tablename__ = "precios_watchlist"
    ticker = Column(String, primary_key=True)
    fecha = Column(Date, nullable=False)
    precio = Column(Numeric(18, 6), nullable=False)
    moneda = Column(String, nullable=False)
    fuente = Column(String, nullable=False)  # "iol" | "api"


class EstadoApiIol(Base):
    """Contador mensual de llamadas a la API de IOL, para no pasarse del cupo bonificado.

    IOL bonifica 25.000 llamadas por mes calendario; a partir de ahí cobra por bloque adicional.
    Se cuenta *toda* petición HTTP a api.invertironline.com, incluida la del token. El tope
    efectivo (`IOL_LIMITE_MENSUAL`, default 22.000) deja colchón sobre el límite real: al
    alcanzarlo la integración deja de llamar a IOL por lo que queda del mes y cae a data912.

    Vive en la DB (y no en memoria) para sobrevivir al reinicio del contenedor — requiere que
    /app/data esté en un volumen, ver docker-compose.yml.
    """
    __tablename__ = "estado_api_iol"
    periodo = Column(String, primary_key=True)  # "YYYY-MM" (UTC)
    llamadas = Column(Integer, nullable=False, default=0)


class EscenarioSimulacion(Base):
    __tablename__ = "escenarios_simulacion"
    id = Column(Integer, primary_key=True, index=True)
    cartera = Column(String, nullable=True, index=True)  # None = Consolidado
    nombre = Column(String, nullable=False)
    tipo_preset = Column(String, nullable=False)  # "alcista" | "bajista" | "crisis" | "personalizado"
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)
    parametros = Column(JSON, nullable=False)  # Payload completo de EscenarioParamsIn


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

        # aseguramos compatibilidad con DB antiguas que no tenían fuente (sheet vs api).
        for tabla in ("indices_mercado", "benchmarks_mercado", "precios_instrumento"):
            result = conn.execute(text(f"PRAGMA table_info({tabla})"))
            cols = [row[1] for row in result.fetchall()]
            if 'fuente' not in cols:
                conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN fuente TEXT NOT NULL DEFAULT 'sheet'"))
                conn.commit()

        # aseguramos compatibilidad con DB antiguas que no tenían riesgo_pais en indices_mercado.
        result = conn.execute(text("PRAGMA table_info(indices_mercado)"))
        cols = [row[1] for row in result.fetchall()]
        if 'riesgo_pais' not in cols:
            conn.execute(text("ALTER TABLE indices_mercado ADD COLUMN riesgo_pais NUMERIC"))
            conn.commit()
