from sqlalchemy import create_engine, event, Column, Integer, String, Date, DateTime, Numeric, ForeignKey, UniqueConstraint, text, JSON
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "data.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# `timeout=30`: si otra conexión tiene el lock de escritura (el sync a mitad de camino), esta
# espera hasta 30 s en vez de fallar al toque con "database is locked".
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):
    """WAL + synchronous=NORMAL en cada conexión nueva.

    En rollback-journal (el default) los lectores se bloquean mientras el escritor tiene el
    commit tomado: es exactamente el síntoma "la web se cuelga durante el sync". Con WAL los
    lectores siguen leyendo la última versión consistente mientras el sync escribe.

    `foreign_keys` se deja en el default (OFF) a propósito: las FK de
    `MovimientoInversion.ticker` / `PrecioInstrumento.ticker` son decorativas hoy y el sync
    inserta con aislamiento por pestaña (puede quedar un movimiento de un ticker cuya pestaña
    Instrumentos quedó bloqueada). Activarlo hay que validarlo contra un sync real antes.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


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


class CotizacionDiaria(Base):
    """Lo que IOL informa del día de un ticker: cierre anterior y variación %.

    Tabla aparte de `precios_instrumento` a propósito: el sync reescribe esa tabla (borra las filas
    `fuente='sheet'` y reconcilia el resto), y este dato no tiene equivalente en el Sheet. Una fila
    por `(ticker, fecha)` de la cotización a la que corresponde. `variacion_pct` está en puntos
    porcentuales tal como lo manda IOL (1.26 = +1,26%); `cierre_anterior` ya viene en la escala del
    precio guardado (calibrada igual que `precios_instrumento.precio`). Ambos pueden ser NULL.
    """
    __tablename__ = "cotizacion_diaria"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    cierre_anterior = Column(Numeric(18, 6), nullable=True)
    variacion_pct = Column(Numeric(12, 6), nullable=True)
    fuente = Column(String, nullable=False, default="iol", server_default="iol")

    __table_args__ = (UniqueConstraint("ticker", "fecha", name="uq_cotizacion_diaria"),)


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


class ObjetivoAporteMensual(Base):
    """Cuánto se propone aportar el usuario por mes, en USD. **La gestiona el usuario desde la
    app** (pantalla "Ritmo de aportes"), no el Sheet: a diferencia de `ObjetivoInversion` —que es
    una meta de patrimonio y la pisa el sync en cada corrida— ésta es una meta de *hábito* y
    sobrevive a los syncs.

    Una fila por cartera; `cartera IS NULL` = Consolidado (mismo criterio que
    `RebalanceoObjetivo` y `ConfiguracionCartera`).

    `vigente_desde` ("YYYY-MM") es el mes desde el que se mide el cumplimiento: por defecto el mes
    en que se fijó el objetivo, porque dar por incumplido un mes en que la meta todavía no existía
    sería inventar historia. `retroactivo` (0/1) lo lleva hasta el primer mes con movimientos,
    pero sólo si el usuario lo pide explícitamente.
    """
    __tablename__ = "objetivo_aporte_mensual"
    id = Column(Integer, primary_key=True, index=True)
    cartera = Column(String, nullable=True, unique=True, index=True)  # None = Consolidado
    monto_usd = Column(Numeric(18, 2), nullable=False)
    vigente_desde = Column(String, nullable=False)  # "YYYY-MM"
    retroactivo = Column(Integer, nullable=False, default=0)
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)


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
      - `relleno_estado` / `relleno_intento`: relleno de huecos internos del historial (una vez por
        ticker, ver `precios.fetch_relleno_huecos_iol`). 'completo' = ya no tenía huecos o se
        rellenó; `relleno_intento` = último intento, para no reintentar antes de ~30 días.

    Serie del subyacente en USD (análisis técnico, fuente yfinance):
      - `simbolo_local`: el símbolo con el que se pide la serie local del ticker a
        analisistecnico (`"MSFT:CEDEAR"` para un CEDEAR, el ticker pelado para lo demás). Se
        persiste para detectar un cambio y purgar las velas viejas, que podrían estar en otra
        unidad.
      - `simbolo_subyacente`: ticker pelado en Yahoo del subyacente (`"MSFT"`), o NULL si el
        ticker no tiene subyacente apto.
      - `mercado_subyacente` / `moneda_subyacente`: `"NMS"`/`"NYQ"` y `"USD"` — la moneda es la
        que se escribe en `serie_ohlcv.moneda` de la variante subyacente.
      - `resolucion_estado`: None | 'ok' | 'sin_subyacente' (no se pudo resolver un subyacente
        USD) | 'ticker_no_apto' (renta fija u otro instrumento sin subyacente posible).
      - `resolucion_intento`: fecha del último probe (cooldown de 180 días para 'sin_subyacente').

    Serie **local** profunda vía yfinance (`TICKER.BA`, ver
    `precios.fetch_backfill_ohlcv_local_yahoo`):
      - `yahoo_local_estado`: None | 'completo' | 'sin_serie' (Yahoo no tiene el símbolo local) |
        'escala_desconocida' (la serie no concuerda con el precio observado, así que no se carga).
      - `yahoo_local_intento`: fecha del último intento (cooldown para no reintentar cada sync).
    """
    __tablename__ = "estado_market_data_ticker"
    ticker = Column(String, primary_key=True)
    factor_escala = Column(Numeric(10, 6), nullable=True)
    factor_fecha = Column(Date, nullable=True)
    backfill_estado = Column(String, nullable=True)
    backfill_intento = Column(Date, nullable=True)
    # Estado del backfill de velas (serie_ohlcv), independiente de `backfill_estado`: ese campo
    # tiene una interacción delicada ya documentada entre las dos funciones de backfill de
    # `precios.py`; un tercer consumidor ahí reabriría ese bug. Mismos valores posibles que
    # `backfill_estado` pero para el pipeline de OHLCV.
    ohlcv_estado = Column(String, nullable=True)
    ohlcv_intento = Column(Date, nullable=True)
    # Serie del subyacente en USD (yfinance) — ver docstring.
    simbolo_local = Column(String, nullable=True)
    simbolo_subyacente = Column(String, nullable=True)
    mercado_subyacente = Column(String, nullable=True)
    moneda_subyacente = Column(String, nullable=True)
    resolucion_estado = Column(String, nullable=True)
    resolucion_intento = Column(Date, nullable=True)
    # Serie local profunda vía yfinance (`TICKER.BA`) — ver docstring. Estado propio y no
    # `ohlcv_estado`: ese lo comparten los backfills de analisistecnico/IOL, y un tercer escritor
    # ahí haría que un 'completo' de una fuente frene a las otras.
    yahoo_local_estado = Column(String, nullable=True)
    yahoo_local_intento = Column(Date, nullable=True)
    relleno_estado = Column(String, nullable=True)
    relleno_intento = Column(Date, nullable=True)


class WatchlistItem(Base):
    """Instrumentos a seguir que no están en cartera. **La gestiona el usuario desde la app**, no
    el Sheet: se da de alta eligiendo un símbolo del catálogo de IOL
    (`services/catalogo_instrumentos.py`) y el sync sólo le refresca el precio.

    Que el ticker salga del catálogo y no de texto libre es lo que permite cotizarlo sin calibrar
    la escala: el símbolo es el de IOL por construcción (ver
    `market_data/precios.fetch_precios_watchlist_catalogo`).

    `objetivo` es el precio al que el usuario quiere comprar. La alerta se dispara "hacia abajo"
    (precio de mercado acercándose al objetivo), a diferencia del `objetivo_valor` de
    `InstrumentoInversion`, que es un precio de venta y se cruza hacia arriba.
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
    notas = Column(String, nullable=True)
    agregado_en = Column(Date, nullable=True)


class PrecioWatchlist(Base):
    """Último precio de mercado observado para un ticker de la watchlist.

    No va a `precios_instrumento` por dos razones: esos tickers no están en
    `instrumentos_inversion` (la FK del ticker), y la serie de precios la leen patrimonio,
    exposición y riesgo -- meter ahí instrumentos que no se poseen falsearía esos números.

    Tabla aparte de `watchlist` (y no columnas de esa tabla) para que el precio sobreviva a una
    caída transitoria de la API, igual que `EstadoMarketDataTicker`. Sólo se guarda el último
    precio: la watchlist no necesita serie histórica.

    Además es la **referencia de escala** del backfill de velas de la watchlist (ver
    `market_data/precios.fetch_backfill_ohlcv_watchlist`): un precio observado en la unidad de IOL.
    """
    __tablename__ = "precios_watchlist"
    ticker = Column(String, primary_key=True)
    fecha = Column(Date, nullable=False)
    precio = Column(Numeric(18, 6), nullable=False)
    moneda = Column(String, nullable=False)
    fuente = Column(String, nullable=False)  # "iol" | "api"


class PrecioSubyacente(Base):
    """Último precio conocido del **subyacente en USD** de un ticker (la acción en EE.UU. detrás de
    un CEDEAR o de un ADR). Una sola fila por ticker, como `PrecioWatchlist`.

    Para qué existe: una zona de precio puede estar medida sobre la serie del subyacente
    (`ZonaPrecio.variante == "subyacente"`), y entonces la alerta tiene que comparar contra el
    precio de **esa** serie, no contra el del CEDEAR en pesos. Pero la serie `TICKER@SUB` de
    `serie_ohlcv` sólo se refresca en el sync de la tarde, así que una zona cruzada al mediodía
    avisaría a la noche o al día siguiente. Esto lo refresca el job liviano de precios, que corre
    varias veces durante la rueda.

    **No se escribe en `serie_ohlcv` a propósito**, por dos razones: esa serie alimenta los
    indicadores y los backtests (es la guarda G4 del diseño del subyacente, ver
    `market_data.precios`), y además `debe_reemplazar_barra` no dejaría que un precio close-only
    pise la vela que yfinance ya trajo del día en curso.

    `moneda` se guarda y no se asume: el consumidor exige USD antes de comparar. Un precio en otra
    moneda contra una zona en dólares es un aviso falso.
    """
    __tablename__ = "precios_subyacente"
    ticker = Column(String, primary_key=True)   # el ticker **local**, no el símbolo de Yahoo
    fecha = Column(Date, nullable=False)
    precio = Column(Numeric(18, 6), nullable=False)
    moneda = Column(String, nullable=False)
    fuente = Column(String, nullable=False)     # "yahoo"


class RefrescoPrecios(Base):
    """Última corrida del job liviano de precios (`services/refresco_precios.py`). Una sola fila.

    **No es un `SyncRun` a propósito.** El refresco liviano no lee el Sheet ni valida pestañas, así
    que no tiene nada que decir sobre la calidad de los datos: si escribiera un `SyncRun`, su
    `health_score` perfecto inflaría el sparkline de Calidad de datos y, con varias corridas por
    día, consumiría en pocas jornadas el historial de 20 que sirve para detectar problemas del
    Sheet (ver `_prune_sync_runs`).

    Por eso el chip de frescura de la app sigue mostrando el último sync **completo**: los
    movimientos y los niveles de stop-loss vienen del Sheet, y esa es la fecha que importa para
    ellos. El timestamp de acá es la frescura de las **cotizaciones**, que es otra cosa.
    """
    __tablename__ = "refresco_precios"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    precios_actualizados = Column(Integer, nullable=False, default=0)
    precios_watchlist = Column(Integer, nullable=False, default=0)
    precios_subyacente = Column(Integer, nullable=False, default=0, server_default="0")
    iol_llamadas = Column(Integer, nullable=False, default=0)
    resultado = Column(String, nullable=False, default="ok")  # "ok" | "sin_fuentes" | "error"
    detalle = Column(JSON, nullable=True)


class AlertaPrecio(Base):
    """Estado de cada nivel de precio vigilado, y bitácora de los avisos emitidos.

    Una fila por `(ticker, tipo, cartera)`: el stop-loss y el objetivo de una posición, y el
    precio de compra de un ticker de la watchlist. `estado` es lo que hace que la alerta avise
    **una vez por cruce** en vez de una vez por corrida -- el antirrebote vive en
    `services/alertas_engine.py`, que explica por qué hace falta.

    La gestiona la app, no el Sheet: **el sync no la toca** (igual que `watchlist`,
    `estrategias_tecnicas` y `escenarios_simulacion`). Si se borrara en cada sync, todos los
    niveles cruzados volverían a avisar en la corrida siguiente.

    `cartera` guarda `""` y no `NULL` para la watchlist: el UNIQUE incluye la columna y en SQLite
    dos NULL no colisionan, así que con `NULL` se acumularían filas duplicadas del mismo nivel.

    `entregada` distingue "se decidió avisar" de "el aviso salió": si el POST al canal falla, la
    fila queda `disparada` pero sin entregar, y el envío se reintenta en la corrida siguiente sin
    volver a tratar el cruce como nuevo. También marca los avisos **silenciados** por la
    configuración (`ajustes_avisos`): se guardan `entregada=1` y `emitida_en=NULL`, así el estado
    avanza igual y volver a prender el interruptor no dispara una andanada de cruces viejos.

    La tabla guarda además las **señales de estrategia técnica**, con `tipo = "estrategia:<id>"` y
    `cartera = ""`. El id de la estrategia va dentro de `tipo` y no en una columna propia porque
    tiene que entrar en la clave de unicidad, y SQLite no sabe alterar un UniqueConstraint sin
    reconstruir la tabla. La cartera queda vacía a propósito: una señal es sobre la serie del
    ticker, no sobre una tenencia. Esas filas no usan la histéresis del nivel (no hay nivel):
    deduplican por la barra de la señal, guardada en `detalle`. Ver `alertas_engine`.

    `detalle` es el contexto completo del aviso serializado (`alertas_engine.contexto_a_detalle`),
    no un campo libre: el reintento de envío reconstruye el mensaje **sólo** desde las columnas
    más este JSON, así que lo que no viaje acá hace que el reintento mande un texto distinto.
    """
    __tablename__ = "alertas_precio"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False)
    # "stop_loss" | "objetivo" | "compra_zona" | "estrategia:<id>" (señal técnica)
    tipo = Column(String, nullable=False)
    cartera = Column(String, nullable=False, default="")  # "" = watchlist
    estado = Column(String, nullable=False, default="armada")  # "armada" | "disparada"
    nivel = Column(Numeric(18, 6), nullable=True)
    precio_disparo = Column(Numeric(18, 6), nullable=True)
    moneda = Column(String, nullable=True)
    emitida_en = Column(DateTime, nullable=True)
    entregada = Column(Integer, nullable=False, default=0)
    detalle = Column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint("ticker", "tipo", "cartera", name="uq_alerta_precio"),)


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


class BarraOHLCV(Base):
    """Serie histórica de velas (OHLCV) para análisis técnico — cartera y watchlist.

    Sin FK a `instrumentos_inversion` a propósito: sirve tanto tickers de cartera como de
    watchlist (que no tienen fila ahí), y no debe poder ensuciar patrimonio/exposición/riesgo,
    que leen `precios_instrumento`. Se acepta duplicar el cierre respecto de esa tabla para los
    tickers de cartera (~75k filas, irrelevante en SQLite).

    **El cierre de acá NO siempre coincide con `precios_instrumento.precio` de la misma fecha**,
    aunque las dos filas salgan del mismo backfill y el mismo factor. Las dos tablas se pueblan
    por caminos con reglas distintas y eso es deliberado:
      - el precio del día lo escribe la ruta 'live' (último precio de un panel de cotizaciones),
        mientras que la vela de esa misma rueda la trae después la serie histórica (cierre de la
        rueda): son dos números distintos para el mismo día, y cada uno es el correcto para lo
        suyo (valuar la tenencia de ese día / dibujar la vela);
      - el backfill no pisa en `precios_instrumento` las fechas que el Sheet cubre
        (`claves_excluir`), pero sí las emite acá — el Sheet no tiene OHLC, así que la vela es
        información nueva, no un reemplazo de una carga manual.
    Al comparar las dos tablas hay que esperar diferencias en las fechas donde conviven las dos
    rutas; no son un síntoma de que el factor de escala esté mal aplicado.

    Unique `(ticker, fecha)` **en ese orden**, al revés que `uq_precio_instrumento`: la consulta
    dominante acá es "toda la serie de UN ticker en un rango", así el índice único es covering.
    """
    __tablename__ = "serie_ohlcv"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    apertura = Column(Numeric(18, 6), nullable=True)
    maximo = Column(Numeric(18, 6), nullable=True)
    minimo = Column(Numeric(18, 6), nullable=True)
    cierre = Column(Numeric(18, 6), nullable=False)
    volumen = Column(Numeric(20, 2), nullable=True)  # nominal — nunca escalado por factor
    moneda = Column(String, nullable=False)
    fuente = Column(String, nullable=False)  # "iol" | "api" (no hay "sheet": el Sheet no tiene OHLC)

    __table_args__ = (UniqueConstraint("ticker", "fecha", name="uq_serie_ohlcv"),)


class EstrategiaTecnica(Base):
    """Estrategia de análisis técnico guardada por el usuario (reglas + riesgo + ejecución).

    Sin `cartera`: una estrategia es sobre indicadores, no sobre una cartera. `ticker` nullable
    (None = reusable en cualquier ticker); el ticker efectivo sobre el que se backtestea siempre
    lo pone el path del endpoint de backtest, no la estrategia guardada.
    """
    __tablename__ = "estrategias_tecnicas"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    ticker = Column(String, nullable=True, index=True)
    tipo_preset = Column(String, nullable=True)  # nombre del preset de origen, si se partió de uno
    definicion = Column(JSON, nullable=False)
    # 'local' (serie del ticker tal cual cotiza, default) | 'subyacente' (serie del subyacente en
    # USD vía yfinance). `senales_recientes` corre las estrategias guardadas sin que nadie elija
    # variante en la UI, así que la elección tiene que viajar en la estrategia.
    variante = Column(String, nullable=False, default="local", server_default="local")
    # Avisos por Telegram de las señales de esta estrategia, por lado. Dos columnas y no una
    # porque confiar en las entradas de una estrategia no implica confiar en sus salidas (ni al
    # revés). Apagadas por default: los 16 presets se siembran solos y prenderlos todos sería
    # decenas de avisos por día, que es peor que no avisar nada. Ver `alertas_analytics`.
    notificar_compra = Column(Integer, nullable=False, default=0, server_default="0")
    notificar_venta = Column(Integer, nullable=False, default=0, server_default="0")
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)


class AjustesAvisos(Base):
    """Qué tipos de aviso de nivel salen por Telegram. Fila única (`id = 1`).

    Vive en la DB y no en las preferencias del navegador porque quien manda los avisos es el job
    del servidor, que no ve el `localStorage` de la app.

    Los tres arrancan en 1 = el comportamiento previo a que existiera esta tabla: si pusiste un
    stop-loss o un objetivo, avisa. Apagar uno **no deja de seguir el estado** de esos niveles
    (ver el docstring de `AlertaPrecio`), sólo deja de mandarlos.

    Los avisos de señales de estrategia no se configuran acá, sino estrategia por estrategia en
    `EstrategiaTecnica.notificar_compra` / `notificar_venta`.
    """
    __tablename__ = "ajustes_avisos"
    id = Column(Integer, primary_key=True)
    avisar_stop_loss = Column(Integer, nullable=False, default=1, server_default="1")
    avisar_objetivo = Column(Integer, nullable=False, default=1, server_default="1")
    avisar_compra_zona = Column(Integer, nullable=False, default=1, server_default="1")
    avisar_venta_zona = Column(Integer, nullable=False, default=1, server_default="1")
    # Cambios de estado del diagnóstico de una empresa (valuación, calidad, solidez): ver
    # `alertas_diagnostico_engine`. Arranca prendido: sólo avisa de un cambio confirmado y la
    # primera corrida siembra el estado sin mandar nada.
    avisar_diagnostico = Column(Integer, nullable=False, default=1, server_default="1")
    fecha_actualizacion = Column(DateTime, nullable=False)


class NivelPrecioOverride(Base):
    """Stop-loss y objetivo fijados **desde la app**, que pisan los del Sheet.

    Vive fuera de `instrumentos_inversion` porque esa tabla es un espejo del Sheet: el sync le
    hace DELETE + INSERT completo en cada corrida (`inversiones_sync`), así que un nivel escrito
    ahí duraría hasta el sync de las 18:30 del mismo día. Mismo criterio que `watchlist`,
    `alertas_precio` y `objetivos_aporte_mensual`: lo que escribe el usuario no comparte tabla
    con lo que escribe el Sheet.

    **Una fila por `(ticker, tipo)`**, y la fila existe sólo si hay override: su presencia *es* el
    override. Con una sola fila de cuatro columnas, un `objetivo_modo IS NULL` sería ambiguo
    ("no hay override" vs. "override que anula el nivel del Sheet") y borrar un nivel dejaría
    media fila viva. Además la clave queda igual a la de `alertas_precio` (`ticker`, `tipo`), que
    es lo que permite re-armar la alerta exacta cuando se cambia un nivel.

    El nivel sigue siendo **por ticker y global**, no por cartera: es una decisión sobre el
    instrumento, igual que la del Sheet.

    `modo`/`valor` son nullable aunque hoy la API los exija juntos: dejan lugar a un futuro
    "override = sin nivel" (fila presente con los dos en NULL = ignorar el nivel del Sheet) sin
    reconstruir la tabla, que es lo que costaría en SQLite sacar un NOT NULL.

    Sin FK a `instrumentos_inversion.ticker` a propósito: el sync vacía esa tabla, y un ticker
    que desaparece del Sheet un día no tiene que perder el nivel que el usuario eligió.
    """
    __tablename__ = "niveles_precio_override"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False)
    tipo = Column(String, nullable=False)  # "stop_loss" | "objetivo"
    modo = Column(String, nullable=True)  # "Porcentaje" | "Fijo"
    # Misma escala que las columnas del Sheet, así `_nivel_precio` recibe exactamente lo mismo:
    # % sobre el precio promedio de compra (modo "Porcentaje") o precio absoluto (modo "Fijo").
    valor = Column(Numeric(18, 6), nullable=True)
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("ticker", "tipo", name="uq_nivel_precio_override"),)


class ZonaPrecio(Base):
    """Zona de compra y zona de venta de un ticker: el rango de precios en el que el usuario
    quiere entrar o salir, dibujado y arrastrado sobre el gráfico de análisis técnico.

    Reemplaza al escalar `WatchlistItem.objetivo`, que era un único precio de compra. Un rango dice
    algo que un número no: "entre 1150 y 1250 compro", y se lee de un vistazo como banda sobre las
    velas. La migración de `objetivo` está más abajo, en el bloque de compatibilidad.

    **Una fila por `(ticker, tipo)`**, con `variante` como atributo y no como parte de la clave:
    una sola zona de compra por ticker, en la serie que el usuario elija. Si la variante entrara en
    la clave, un ticker podría tener una zona de compra en ARS y otra en USD y avisaría dos veces
    del mismo motivo.

    `variante` es sobre **qué serie** se mide: `"local"` el precio tal como cotiza acá, o
    `"subyacente"` la serie del instrumento en EE.UU. en USD nativo (la clave `TICKER@SUB` de
    `serie_ohlcv`, ver `ohlcv_analytics`). No hay conversión de moneda en ningún caso: son dos
    instrumentos, y una zona se compara siempre contra el precio de su propia serie. `moneda` es la
    de esa serie al momento de guardar, para poder mostrarla y escribirla en el aviso.

    Bordes: **cualquiera de los dos puede ser NULL** (zona abierta de un lado). El que dispara es
    el `techo` para una zona de compra (el precio baja y entra) y el `piso` para una de venta (el
    precio sube y entra); el borde opuesto es informativo y, cuando está, define cuándo la alerta
    vuelve a armarse. Que los dos sean NULL no es una zona: lo rechaza `services/zonas_precio.py`.

    Vale para cualquier ticker del universo técnico (cartera ∪ watchlist), no sólo para la
    watchlist: planear la salida de algo que ya se tiene es tan válido como planear la entrada. No
    reemplaza al stop-loss/objetivo de una posición (`NivelPrecioOverride`), que son porcentajes
    sobre el precio promedio de compra y vienen del Sheet: son dos cosas distintas y conviven.

    Sin FK al ticker, igual que `NivelPrecioOverride`: el sync vacía `instrumentos_inversion` y un
    ticker que desaparece del Sheet un día no tiene que perder la zona que el usuario dibujó.
    """
    __tablename__ = "zonas_precio"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False)
    tipo = Column(String, nullable=False)  # "compra" | "venta"
    variante = Column(String, nullable=False, default="local")  # "local" | "subyacente"
    moneda = Column(String, nullable=False, default="")
    piso = Column(Numeric(18, 6), nullable=True)
    techo = Column(Numeric(18, 6), nullable=True)
    # Apagar una zona sin perder los números: el gráfico la deja de dibujar y las alertas de
    # evaluarla, pero volver a prenderla no obliga a re-dibujarla.
    activa = Column(Integer, nullable=False, default=1, server_default="1")
    # La apagó una migración, no el usuario: era una zona en pesos sobre un CEDEAR que ahora se
    # analiza por su precio en dólares (ver `migrar_zonas_locales_de_cedears`). Distinguirla de una
    # zona apagada a mano permite explicar en pantalla por qué desapareció la distancia y pedir que
    # se vuelva a dibujar. Cualquier guardado del usuario la limpia.
    vencida = Column(Integer, nullable=False, default=0, server_default="0")
    notas = Column(String, nullable=True)
    fecha_creacion = Column(DateTime, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("ticker", "tipo", name="uq_zona_precio_ticker_tipo"),)


class ClasificacionAuto(Base):
    """Clasificación de un emisor derivada de Yahoo, y estado de su ingesta.

    **Una fila por `ticker_base`**: el símbolo de IOL sin la variante de moneda (`AAPL`, no
    `AAPLD`; ver `clasificacion_engine.mapa_variantes`). Es la clave con la que el usuario corrige
    y con la que se buscan pares. `simbolo_yahoo` es con qué se le preguntó a Yahoo; dos tickers
    base pueden compartirlo (`PETR3` y `PBR` → `PBR`), y entonces comparten fundamentales.

    Guarda el dato crudo de Yahoo (`*_raw`) además del normalizado: si cambia el vocabulario de
    `clasificacion_engine`, se re-normaliza sin volver a pedir nada.

    `estado`: 'ok' | 'no_encontrado' (Yahoo no conoce el símbolo) | 'error' | 'no_apto' (renta
    fija, FCI: sin clasificación automática). `proximo_intento` es el backoff ante fallos.

    Sin FK a `instrumentos_inversion`: el sync vacía esa tabla, y la mayoría de estos emisores ni
    siquiera están en cartera (el universo es el catálogo de IOL).
    """
    __tablename__ = "clasificacion_auto"
    ticker_base = Column(String, primary_key=True)
    tipo_catalogo = Column(String, nullable=True)   # "CEDEAR" | "Acción" | ...
    simbolo_yahoo = Column(String, nullable=True, index=True)
    metodo_mapeo = Column(String, nullable=True)    # ver clasificacion_engine.METODO_*
    nombre = Column(String, nullable=True)
    quote_type = Column(String, nullable=True)
    sector_raw = Column(String, nullable=True)
    industria_raw = Column(String, nullable=True)
    pais_raw = Column(String, nullable=True)
    categoria_etf_raw = Column(String, nullable=True)
    fund_family = Column(String, nullable=True)
    tipo = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    industria = Column(String, nullable=True)
    pais = Column(String, nullable=True)
    region = Column(String, nullable=True)
    clase_msci = Column(String, nullable=True)
    estado = Column(String, nullable=True)
    fecha_clasificacion = Column(Date, nullable=True)
    fecha_fundamentales = Column(Date, nullable=True)
    intentos_fallidos = Column(Integer, nullable=False, default=0)
    proximo_intento = Column(Date, nullable=True)
    ultimo_error = Column(String, nullable=True)


class FundamentalesSnapshot(Base):
    """Foto de los fundamentales de un símbolo de Yahoo en una fecha.

    `metricas` es el dict de `yahoo.fetch_fundamentales` (lista blanca de `get_info()`), crudo: la
    limpieza (P/E negativo, topes, moneda) es de `valuacion_engine` y puede cambiar sin re-pedir
    datos. `serie_semanal` son ~56 cierres semanales en la moneda del símbolo (`moneda`), para el
    rendimiento relativo contra los pares.

    `market_cap_usd` va en columna propia (no sólo dentro del JSON) porque es por lo que se
    ordenan los pares por tamaño. `ratios_precio_confiables` = 0 cuando el balance está en otra
    moneda que la cotización (típico de `.BA` y de algunos ADR): ahí P/E y compañía de Yahoo
    mezclan monedas.

    Se guardan los últimos `fundamentales_ingesta.SNAPSHOTS_RETENIDOS` por símbolo.
    """
    __tablename__ = "fundamentales_snapshot"
    id = Column(Integer, primary_key=True, index=True)
    simbolo_yahoo = Column(String, nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    fuente = Column(String, nullable=False, default="yahoo")
    moneda = Column(String, nullable=True)
    market_cap_usd = Column(Numeric(24, 2), nullable=True)
    metricas = Column(JSON, nullable=False)
    serie_semanal = Column(JSON, nullable=True)
    ratios_precio_confiables = Column(Integer, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("simbolo_yahoo", "fecha", name="uq_fundamentales_simbolo_fecha"),)


class VariacionMercado(Base):
    """Variación reciente del precio de un emisor del catálogo, para el mapa de mercado.

    **Una fila por `simbolo_yahoo`, reescrita en cada corrida**: es una foto, no una serie. No se
    escribe en `serie_ohlcv` a propósito (esa tabla alimenta indicadores y backtests y es de
    cartera/watchlist, mismo criterio que `PrecioSubyacente`).

    Las variaciones son razones (0.012 = +1,2%), en la moneda de `moneda`: USD para el subyacente
    en EE.UU. y para lo local convertido por el MEP de cada fecha; 'ARS' sólo cuando no había MEP
    para convertir (y el mapa lo avisa). Cualquiera puede ser NULL si la historia no alcanza.
    """
    __tablename__ = "variacion_mercado"
    simbolo_yahoo = Column(String, primary_key=True)
    fecha_cierre = Column(Date, nullable=False)
    cierre = Column(Numeric(18, 6), nullable=False)
    moneda = Column(String, nullable=False, default="USD", server_default="USD")
    var_1d = Column(Numeric(12, 6), nullable=True)
    var_1s = Column(Numeric(12, 6), nullable=True)
    var_1m = Column(Numeric(12, 6), nullable=True)
    var_1a = Column(Numeric(12, 6), nullable=True)
    actualizado = Column(DateTime, nullable=False)


class ClasificacionOverride(Base):
    """Corrección manual de un campo de la clasificación, hecha desde la app.

    **Una fila por `(ticker_base, campo)`** y la fila existe sólo si hay corrección (mismo criterio
    que `NivelPrecioOverride`): su presencia *es* el override. `campo` ∈ tipo, sector, industria,
    pais, region, simbolo_yahoo. Gana sobre el seed, Yahoo y el Sheet
    (`clasificacion_engine.resolver`).
    """
    __tablename__ = "clasificacion_override"
    id = Column(Integer, primary_key=True, index=True)
    ticker_base = Column(String, nullable=False)
    campo = Column(String, nullable=False)
    valor = Column(String, nullable=False)
    nota = Column(String, nullable=True)
    fecha_actualizacion = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("ticker_base", "campo", name="uq_clasificacion_override"),)


class ParOverride(Base):
    """Par agregado o quitado a mano al grupo de comparables de un emisor.

    El grupo final es `(automáticos − quitados) ∪ agregados` (`pares_engine`). Un `agregar` de un
    símbolo que no está en el catálogo dispara su ingesta como extra.
    """
    __tablename__ = "pares_override"
    id = Column(Integer, primary_key=True, index=True)
    ticker_base = Column(String, nullable=False)
    par = Column(String, nullable=False)
    accion = Column(String, nullable=False)  # "agregar" | "quitar"
    fecha = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("ticker_base", "par", name="uq_par_override"),)


class ValorSupuestos(Base):
    """Supuestos del usuario para el valor razonable de un emisor (`valor_razonable_engine`).

    Una fila por `ticker_base`; `supuestos` es un JSON `{ajuste_pct, excluir[], multiplos{método: x}}` que
    se valida con `valor_razonable_engine.normalizar_supuestos` antes de guardarse. Sin fila, rige el
    cálculo por defecto (mediana de los pares). La gestiona la app: el sync no la toca.
    """
    __tablename__ = "valor_supuestos"
    id = Column(Integer, primary_key=True, index=True)
    ticker_base = Column(String, nullable=False, unique=True)
    supuestos = Column(JSON, nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=False)


class DiagnosticoHistorial(Base):
    """Foto del diagnóstico de un emisor cada vez que algo cambia (`services/historial_diagnosticos.py`).

    **Point-in-time**: cada fila guarda lo que la app *decía* ese día, con la versión de las reglas que
    lo dijo, y no se recalcula nunca. Es lo único que permite medir más adelante si las lecturas
    sirvieron: reconstruir el pasado con las reglas de hoy y los datos de hoy sería mirar el futuro.

    Sólo se agrega una fila si cambió algo respecto de la anterior (`huella`: versiones, fecha del dato,
    estados por dimensión, lectura y pares), así que la tabla crece con los cambios y no con los días.
    `estados`, `metricas`, `pares`, `comparador` y `valor_razonable` son JSON con fechas en ISO. No hay FK
    a nada que el sync vacíe. La gestiona la app.
    """
    __tablename__ = "diagnostico_historial"
    id = Column(Integer, primary_key=True, index=True)
    ticker_base = Column(String, nullable=False, index=True)
    fecha = Column(Date, nullable=False)              # día en que se registró
    fecha_dato = Column(Date, nullable=True)          # fecha del snapshot de fundamentales que se usó
    version_diagnostico = Column(Integer, nullable=False)
    version_comparador = Column(Integer, nullable=True)
    version_valor = Column(Integer, nullable=True)
    estados = Column(JSON, nullable=False)
    lectura = Column(String, nullable=True)
    confianza = Column(String, nullable=True)
    metricas = Column(JSON, nullable=True)
    pares = Column(JSON, nullable=True)
    comparador = Column(JSON, nullable=True)
    valor_razonable = Column(JSON, nullable=True)
    precio = Column(Numeric(18, 6), nullable=True)
    moneda = Column(String, nullable=True)
    huella = Column(String, nullable=False)


class DiagnosticoAlertaEstado(Base):
    """Estado del antirrebote de las alertas de cambio de diagnóstico, por `(emisor, dimensión)`.

    `estado_base` es el último estado avisado (o sembrado); `pendiente` el estado nuevo que se vio una vez y
    espera confirmación en un snapshot con otra `fecha_dato`. Aparte de `alertas_precio`, que guarda el aviso
    emitido (entrega, reintento, historial), porque ese registro se pisa con cada aviso y este estado tiene
    que avanzar también cuando el aviso está silenciado.
    """
    __tablename__ = "diagnostico_alerta_estado"
    id = Column(Integer, primary_key=True, index=True)
    ticker_base = Column(String, nullable=False)
    dimension = Column(String, nullable=False)
    estado_base = Column(String, nullable=True)
    pendiente = Column(String, nullable=True)
    pendiente_fecha_dato = Column(String, nullable=True)    # ISO
    version = Column(Integer, nullable=True)
    fecha_actualizacion = Column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("ticker_base", "dimension", name="uq_diagnostico_alerta_estado"),)


class IngestaFundamentales(Base):
    """Última corrida del job de fundamentales (`services/fundamentales_ingesta.py`). Una sola
    fila, como `RefrescoPrecios`, y por la misma razón no es un `SyncRun`."""
    __tablename__ = "ingesta_fundamentales"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    procesados = Column(Integer, nullable=False, default=0)
    ok = Column(Integer, nullable=False, default=0)
    fallidos = Column(Integer, nullable=False, default=0)
    rate_limited = Column(Integer, nullable=False, default=0)
    pendientes = Column(Integer, nullable=False, default=0)
    resultado = Column(String, nullable=False, default="ok")
    detalle = Column(JSON, nullable=True)


class MigracionAplicada(Base):
    """Marca de las migraciones de **datos** que no pueden correr en cada arranque.

    Las migraciones de esquema se reconocen por la columna que falta; éstas no: reescriben filas
    que el usuario puede volver a cambiar a propósito (una estrategia fijada en `local`, una zona
    local sobre un CEDEAR), y sin una marca el próximo arranque se las desharía.
    """
    __tablename__ = "migraciones_aplicadas"
    nombre = Column(String, primary_key=True)
    fecha = Column(DateTime, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrar_objetivo_watchlist_a_zonas(conn) -> None:
    """El `Objetivo` escalar de la watchlist (un único precio de compra) pasa a ser el **techo** de
    una zona de compra, que es lo que se dibuja y se arrastra en el gráfico (ver `ZonaPrecio`).

    Después de migrar se **vacía la columna**: dejarla con valor haría que borrar una zona a
    propósito la resucite en el próximo arranque. La columna no se borra (sacarla en SQLite obliga
    a reconstruir la tabla, y el endpoint de alta todavía acepta `objetivo` como atajo), queda sin
    lectores y sin datos.

    Idempotente: no pisa una zona de compra que ya exista, y una segunda corrida no encuentra nada
    que migrar. Función aparte de `init_db` para poder ejercitarla en un test sin tocar la DB real.
    """
    conn.execute(text("""
        INSERT INTO zonas_precio
            (ticker, tipo, variante, moneda, piso, techo, activa,
             fecha_creacion, fecha_actualizacion)
        SELECT w.ticker, 'compra', 'local', COALESCE(w.moneda, ''), NULL, w.objetivo, 1,
               datetime('now'), datetime('now')
          FROM watchlist w
         WHERE w.objetivo IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM zonas_precio z
                WHERE z.ticker = w.ticker AND z.tipo = 'compra'
           )
    """))
    conn.execute(text("UPDATE watchlist SET objetivo = NULL WHERE objetivo IS NOT NULL"))
    conn.commit()


def _migracion_aplicada(conn, nombre: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM migraciones_aplicadas WHERE nombre = :n"), {"n": nombre},
    ).first() is not None


def _marcar_migracion(conn, nombre: str) -> None:
    conn.execute(
        text("INSERT INTO migraciones_aplicadas (nombre, fecha) VALUES (:n, datetime('now'))"),
        {"n": nombre},
    )


def migrar_estrategias_a_referencia(conn) -> None:
    """Las estrategias guardadas con `variante='local'` pasan a `'referencia'`: la serie que
    corresponde a cada ticker (USD para un CEDEAR con serie del subyacente, local para el resto).

    Las que están en `'subyacente'` no se tocan: ahí el usuario eligió explícitamente. Para un
    ticker que no es CEDEAR `referencia` equivale a `local`, así que no cambia nada de lo que ya
    funcionaba. No se borra el estado de los avisos de señal: las de tickers locales siguen
    deduplicadas, y las de un CEDEAR que ahora se mide en USD son señales nuevas de verdad.

    Corre **una sola vez** (marca en `migraciones_aplicadas`): si no, fijar una estrategia en
    `local` a propósito se desharía en el próximo arranque.
    """
    nombre = "estrategias_variante_referencia"
    if _migracion_aplicada(conn, nombre):
        return
    conn.execute(text("UPDATE estrategias_tecnicas SET variante = 'referencia' WHERE variante = 'local'"))
    _marcar_migracion(conn, nombre)
    conn.commit()


def migrar_zonas_locales_de_cedears(conn, min_barras: int = 60) -> None:
    """Una zona en pesos sobre un CEDEAR mide contra el precio equivocado para decidir el momento
    de compra, y no se puede convertir a dólares (no hay histórico de CCL ni el ratio del CEDEAR).
    Se apaga y se marca `vencida`, conservando los números, para que la pantalla pida dibujarla de
    nuevo sobre el gráfico en USD.

    Alcanza a las zonas `local` activas de tickers que cumplen la regla de
    `ohlcv_analytics.variante_referencia` en SQL: son CEDEAR y tienen serie `TICKER@SUB` con
    `min_barras` o más y moneda dominante USD (`min_barras` replica
    `ohlcv_analytics.MIN_BARRAS_REFERENCIA`; un test los mantiene iguales). Un bono, una acción
    argentina o un CEDEAR sin serie del subyacente quedan como estaban.

    También borra el estado de las alertas de esas zonas: si no, al volver a dibujarla en dólares
    el primer cruce quedaría silenciado por el "ya disparada" de la zona vieja.

    Corre **una sola vez** (marca en `migraciones_aplicadas`): sin ella, una zona local que el
    usuario dibuje a propósito sobre un CEDEAR se volvería a apagar en cada arranque.
    """
    nombre = "zonas_locales_de_cedears_vencidas"
    if _migracion_aplicada(conn, nombre):
        return
    filas = conn.execute(text("""
        SELECT z.id, z.ticker
          FROM zonas_precio z
         WHERE z.variante = 'local' AND z.activa = 1
           AND z.ticker IN (
               SELECT ticker FROM watchlist
                WHERE lower(COALESCE(tipo_instrumento, '')) LIKE '%cedear%'
               UNION
               SELECT ticker FROM instrumentos_inversion
                WHERE lower(COALESCE(tipo_instrumento, '')) LIKE '%cedear%'
           )
           AND z.ticker || '@SUB' IN (
               SELECT ticker FROM serie_ohlcv
                GROUP BY ticker
               HAVING COUNT(*) >= :min_barras
                  AND 2 * SUM(CASE WHEN upper(moneda) = 'USD' THEN 1 ELSE 0 END) > COUNT(*)
           )
    """), {"min_barras": min_barras}).fetchall()
    for zona_id, ticker in filas:
        conn.execute(
            text("UPDATE zonas_precio SET activa = 0, vencida = 1, fecha_actualizacion = datetime('now') WHERE id = :i"),
            {"i": zona_id},
        )
        conn.execute(
            text("DELETE FROM alertas_precio WHERE ticker = :t AND tipo IN ('compra_zona', 'venta_zona')"),
            {"t": ticker},
        )
    _marcar_migracion(conn, nombre)
    conn.commit()


def init_db():
    Base.metadata.create_all(bind=engine)

    # `niveles_precio_override` no necesita migración: es una tabla nueva que crea `create_all` y
    # una DB vieja arranca con cero filas, que es exactamente el comportamiento previo (el nivel
    # del Sheet manda mientras no haya override). No la busques más abajo.

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

        # aseguramos compatibilidad con DB antiguas que no tenían el estado de backfill OHLCV
        # ni la resolución de la serie del subyacente en USD.
        result = conn.execute(text("PRAGMA table_info(estado_market_data_ticker)"))
        cols = [row[1] for row in result.fetchall()]
        for columna, tipo in (
            ("ohlcv_estado", "TEXT"),
            ("ohlcv_intento", "DATE"),
            ("simbolo_local", "TEXT"),
            ("simbolo_subyacente", "TEXT"),
            ("mercado_subyacente", "TEXT"),
            ("moneda_subyacente", "TEXT"),
            ("resolucion_estado", "TEXT"),
            ("resolucion_intento", "DATE"),
            ("yahoo_local_estado", "TEXT"),
            ("yahoo_local_intento", "DATE"),
            ("relleno_estado", "TEXT"),
            ("relleno_intento", "DATE"),
        ):
            if columna not in cols:
                conn.execute(text(f"ALTER TABLE estado_market_data_ticker ADD COLUMN {columna} {tipo}"))
                conn.commit()

        # aseguramos compatibilidad con DB antiguas de estrategias_tecnicas sin `variante`.
        result = conn.execute(text("PRAGMA table_info(estrategias_tecnicas)"))
        cols = [row[1] for row in result.fetchall()]
        if 'variante' not in cols:
            conn.execute(text("ALTER TABLE estrategias_tecnicas ADD COLUMN variante TEXT NOT NULL DEFAULT 'local'"))
            conn.commit()
        # Avisos por Telegram de las señales, por lado. Default 0: una DB que ya existía no
        # empieza a mandar avisos de estrategia sola.
        for columna in ("notificar_compra", "notificar_venta"):
            if columna not in cols:
                conn.execute(text(
                    f"ALTER TABLE estrategias_tecnicas ADD COLUMN {columna} INTEGER NOT NULL DEFAULT 0"
                ))
                conn.commit()

        # La watchlist dejó de ser espejo de la pestaña `Watchlist` del Sheet y pasó a gestionarse
        # desde la app (alta eligiendo del catálogo de IOL). La ausencia de `agregado_en` identifica
        # una DB anterior a ese cambio: sus filas las escribió el sync a partir del Sheet y sus
        # tickers son texto libre, no símbolos del catálogo, así que se descartan una única vez en
        # vez de quedar como ítems que no se pueden cotizar ni re-resolver. El Sheet conserva las
        # filas; se vuelven a cargar desde la pantalla.
        result = conn.execute(text("PRAGMA table_info(watchlist)"))
        cols = [row[1] for row in result.fetchall()]
        if 'agregado_en' not in cols:
            conn.execute(text("ALTER TABLE watchlist ADD COLUMN notas TEXT"))
            conn.execute(text("ALTER TABLE watchlist ADD COLUMN agregado_en DATE"))
            conn.execute(text("DELETE FROM watchlist"))
            conn.execute(text("DELETE FROM precios_watchlist"))
            conn.commit()

        migrar_objetivo_watchlist_a_zonas(conn)

        # Marca de zonas vencidas por la migración a la serie de referencia.
        result = conn.execute(text("PRAGMA table_info(zonas_precio)"))
        cols = [row[1] for row in result.fetchall()]
        if 'vencida' not in cols:
            conn.execute(text("ALTER TABLE zonas_precio ADD COLUMN vencida INTEGER NOT NULL DEFAULT 0"))
            conn.commit()

        # Migraciones de datos de la serie de referencia. Van acá y no antes: necesitan que ya
        # existan `estrategias_tecnicas.variante` y `zonas_precio.vencida`.
        migrar_estrategias_a_referencia(conn)
        migrar_zonas_locales_de_cedears(conn)

        # Interruptor de la zona de venta. Default 1 como los otros tres: dibujar la zona ya es la
        # decisión de querer el aviso. **Un tipo de nivel sin su interruptor queda silenciado**
        # (`avisos_config.tipos_habilitados` lo deriva de `CAMPO_POR_TIPO`), así que agregar un
        # tipo a `alertas_engine.TIPOS` obliga a agregar su columna acá.
        # Conteo de precios del subyacente refrescados por el job liviano.
        result = conn.execute(text("PRAGMA table_info(refresco_precios)"))
        cols = [row[1] for row in result.fetchall()]
        if 'precios_subyacente' not in cols:
            conn.execute(text(
                "ALTER TABLE refresco_precios ADD COLUMN precios_subyacente INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(ajustes_avisos)"))
        cols = [row[1] for row in result.fetchall()]
        if 'avisar_venta_zona' not in cols:
            conn.execute(text(
                "ALTER TABLE ajustes_avisos ADD COLUMN avisar_venta_zona INTEGER NOT NULL DEFAULT 1"
            ))
            conn.commit()
        if 'avisar_diagnostico' not in cols:
            conn.execute(text(
                "ALTER TABLE ajustes_avisos ADD COLUMN avisar_diagnostico INTEGER NOT NULL DEFAULT 1"
            ))
            conn.commit()

    # El nombre identifica a una estrategia (ver `estrategias_analytics.normalizar_nombre`): las
    # DB creadas antes de esa regla pueden tener homónimas duplicadas, que el selector muestra dos
    # veces y el screener corre dos veces. Después, sembramos el catálogo de presets **sin pisar**
    # lo existente: un arranque no puede deshacer los ajustes del usuario.
    # Import local: `services` importa `database`, y a nivel de módulo esto sería circular.
    from .services import estrategias_seed

    db = SessionLocal()
    try:
        estrategias_seed.deduplicar_por_nombre(db)
        estrategias_seed.sembrar_presets(db, forzar=False)
    except Exception:
        # Un catálogo no sembrado no puede impedir que la app levante: las plantillas siguen
        # disponibles en el editor y el usuario puede sembrar a mano desde la UI.
        db.rollback()
    finally:
        db.close()
