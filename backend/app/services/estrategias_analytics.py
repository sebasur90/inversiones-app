"""Orquestación de estrategias técnicas: CRUD (calco de `escenarios_analytics.py`) + backtest.

**Ojo**: `listar_estrategias(ticker=None)` devuelve **todas** las estrategias, no sólo las de
`ticker IS NULL` — semántica distinta del `cartera is None -> filter(is_(None))` de
`escenarios_analytics.listar_escenarios`. Ahí `None` significa "Consolidado", una cartera más;
acá una estrategia con `ticker IS NULL` es simplemente reusable en cualquier ticker, así que
"todas las estrategias" es la lista correcta para poblar un selector. Vale este comentario para
que no se copie el patrón de escenarios sin pensarlo.
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..database import EstrategiaTecnica
from . import estrategia_engine, ohlcv_analytics


def crear_estrategia(
    nombre: str, definicion: dict, db: Session,
    descripcion: str | None = None, ticker: str | None = None, tipo_preset: str | None = None,
    variante: str = "local",
) -> EstrategiaTecnica:
    ahora = datetime.utcnow()
    estrategia = EstrategiaTecnica(
        nombre=nombre, descripcion=descripcion, ticker=ticker, tipo_preset=tipo_preset,
        definicion=definicion, variante=variante or "local",
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    )
    db.add(estrategia)
    db.commit()
    db.refresh(estrategia)
    return estrategia


def listar_estrategias(ticker: str | None, db: Session) -> list[EstrategiaTecnica]:
    """Todas las estrategias guardadas, reusables en cualquier ticker o no. `ticker` no filtra
    hoy (no hay forma de saber, sin correr el DSL, si aplica a un ticker en particular) — queda
    como parámetro para el día que la definición declare afinidad por ticker."""
    return db.query(EstrategiaTecnica).order_by(EstrategiaTecnica.nombre).all()


def obtener_estrategia(estrategia_id: int, db: Session) -> EstrategiaTecnica | None:
    return db.query(EstrategiaTecnica).filter(EstrategiaTecnica.id == estrategia_id).first()


def actualizar_estrategia(
    estrategia_id: int, db: Session,
    nombre: str | None = None, descripcion: str | None = None,
    ticker: str | None = None, definicion: dict | None = None,
    variante: str | None = None,
) -> EstrategiaTecnica | None:
    estrategia = obtener_estrategia(estrategia_id, db)
    if estrategia is None:
        return None
    if nombre is not None:
        estrategia.nombre = nombre
    if descripcion is not None:
        estrategia.descripcion = descripcion
    if ticker is not None:
        estrategia.ticker = ticker
    if definicion is not None:
        estrategia.definicion = definicion
    if variante is not None:
        estrategia.variante = variante
    estrategia.fecha_actualizacion = datetime.utcnow()
    db.commit()
    db.refresh(estrategia)
    return estrategia


def duplicar_estrategia(estrategia_id: int, nuevo_nombre: str | None, db: Session) -> EstrategiaTecnica | None:
    original = obtener_estrategia(estrategia_id, db)
    if original is None:
        return None
    return crear_estrategia(
        nombre=nuevo_nombre or f"{original.nombre} (copia)",
        definicion=original.definicion, db=db,
        descripcion=original.descripcion, ticker=original.ticker, tipo_preset=original.tipo_preset,
        variante=getattr(original, "variante", None) or "local",
    )


def eliminar_estrategia(estrategia_id: int, db: Session) -> bool:
    estrategia = obtener_estrategia(estrategia_id, db)
    if estrategia is None:
        return False
    db.delete(estrategia)
    db.commit()
    return True


def ejecutar_backtest(
    ticker: str, definicion: dict, db: Session,
    desde: date | None = None, hasta: date | None = None,
    variante: str = "local",
) -> dict:
    """Corre el backtest de `definicion` sobre la serie de `ticker` (variante `local` o
    `subyacente` en USD).

    Pide `barras_minimas(definicion)` ruedas extra de warm-up antes de `desde` y las recorta
    después (vía `indice_desde`/`primera_barra_evaluable`), para que la primera barra visible ya
    tenga los indicadores calculados. Devuelve un dict listo para `BacktestOut`; `estado` en
    `advertencias` documenta si la serie no alcanzó para operar.
    """
    hasta = hasta or date.today()
    warm_up = estrategia_engine.barras_minimas(definicion)
    serie = ohlcv_analytics.get_serie_barras(
        ticker, desde or date(1900, 1, 1), hasta, db,
        barras_previas=warm_up, max_barras=3000, variante=variante,
    )
    barras = serie["barras"]
    advertencias = list(serie["advertencias"])
    moneda = serie["moneda"]
    indice_desde = serie.get("indice_desde", 0)

    if len(barras) < 2:
        return {
            "ticker": ticker, "variante": variante, "moneda": moneda,
            "senales": [], "operaciones": [],
            "metricas": {
                "estado": "datos_insuficientes", "retorno_total_pct": 0.0, "retorno_anualizado_pct": None,
                "retorno_buy_hold_pct": 0.0, "exceso_vs_buy_hold_pp": 0.0, "operaciones": 0,
                "operaciones_cerradas": 0, "retorno_abierta_pct": None, "ganadoras": 0,
                "perdedoras": 0, "win_rate_pct": None, "retorno_medio_operacion_pct": None,
                "mejor_operacion_pct": None, "peor_operacion_pct": None, "profit_factor": None,
                "max_drawdown_pct": None, "fecha_pico": None, "fecha_valle": None,
                "duracion_media_barras": None, "exposicion_pct": 0.0, "comisiones_pct_acum": 0.0,
            },
            "curva_equity": [], "curva_buy_hold": [], "primera_barra_evaluable": None,
            "barras": [], "indicadores": {}, "indice_desde": 0,
            "advertencias": advertencias + ["sin_serie"],
        }

    # `indice_desde` marca dónde arranca el período que pidió el usuario dentro de `barras` (que
    # trae warm-up extra antepuesto): sin pasarlo, el backtest podría abrir operaciones dentro del
    # warm-up y contaminar retorno total, buy&hold, drawdown y exposición con actividad anterior
    # al período pedido.
    resultado = estrategia_engine.backtest(definicion, barras, indice_inicio=indice_desde)
    advertencias.extend(resultado.advertencias)
    # `compilar` se vuelve a correr acá (el backtest lo hace internamente) para exponer las series
    # de indicadores ya calculadas y la primera barra evaluable, alineadas 1:1 con `barras`.
    compilado_primera = None
    series_indicadores: dict = {}
    try:
        compilado = estrategia_engine.compilar(definicion, barras)
        compilado_primera = compilado.primera_barra_evaluable
        series_indicadores = compilado.series
    except Exception:
        compilado_primera = None
        series_indicadores = {}

    return {
        "ticker": ticker,
        "variante": variante,
        "moneda": moneda,
        "senales": [
            {"indice": s.indice, "fecha": s.fecha, "tipo": s.tipo, "precio": s.precio, "motivo": s.motivo}
            for s in resultado.senales
        ],
        "operaciones": [
            {
                "indice_entrada": o.indice_entrada, "indice_salida": o.indice_salida,
                "fecha_entrada": o.fecha_entrada, "fecha_salida": o.fecha_salida,
                "precio_entrada": o.precio_entrada, "precio_salida": o.precio_salida,
                "barras": o.barras, "retorno_bruto_pct": o.retorno_bruto_pct,
                "retorno_neto_pct": o.retorno_neto_pct, "motivo_salida": o.motivo_salida,
                "abierta": o.abierta,
            }
            for o in resultado.operaciones
        ],
        "metricas": resultado.metricas,
        "curva_equity": [{"fecha": f, "valor": v} for f, v in resultado.curva_equity],
        "curva_buy_hold": [{"fecha": f, "valor": v} for f, v in resultado.curva_buy_hold],
        "primera_barra_evaluable": compilado_primera,
        "barras": [
            {
                "fecha": b.fecha, "cierre": b.cierre, "apertura": b.apertura,
                "maximo": b.maximo, "minimo": b.minimo, "volumen": b.volumen,
            }
            for b in barras
        ],
        "indicadores": series_indicadores,
        "indice_desde": indice_desde,
        "advertencias": advertencias,
    }


# Una señal deja de ser accionable rápido: si el cruce fue hace dos semanas, el precio ya se movió
# y mostrarla como "oportunidad" en la watchlist sería engañoso.
MAX_BARRAS_SENAL_RECIENTE = 5


def senales_recientes(db: Session, max_barras: int = MAX_BARRAS_SENAL_RECIENTE) -> list[dict]:
    """Última señal de cada estrategia guardada **con ticker asignado**, si disparó dentro de las
    últimas `max_barras` ruedas de la serie.

    Reusa `estrategia_engine.backtest` en vez de evaluar las condiciones sueltas: así la señal que
    se muestra es la que la máquina de estados realmente habría operado (una compra no se repite
    mientras la posición sigue abierta), no cada barra en la que la condición da verdadera.

    Las estrategias sin ticker (reusables) se omiten: no hay forma de saber sobre qué serie
    correrlas sin que el usuario lo elija.
    """
    hoy = date.today()
    resultado: list[dict] = []

    for estrategia in db.query(EstrategiaTecnica).filter(EstrategiaTecnica.ticker.isnot(None)).all():
        if estrategia_engine.validar_estrategia(estrategia.definicion):
            continue  # una definición inválida no debería frenar al resto de la lista

        variante = getattr(estrategia, "variante", None) or "local"
        try:
            # `barras_minimas` y `get_serie_barras` también van dentro del `try`: una estrategia
            # guardada antes de que `validar_estrategia` chequeara los params de sus indicadores
            # (o con params corruptos por otra vía) no debería tirar 500 y frenar la lista entera.
            warm_up = estrategia_engine.barras_minimas(estrategia.definicion)
            serie = ohlcv_analytics.get_serie_barras(
                estrategia.ticker, date(1900, 1, 1), hoy, db, barras_previas=warm_up, max_barras=3000,
                variante=variante,
            )
            barras = serie["barras"]
            if len(barras) < 2:
                continue
            backtest_out = estrategia_engine.backtest(estrategia.definicion, barras)
        except (ValueError, KeyError, TypeError):
            continue  # DSL válido para el validador pero roto para esta serie: se omite

        if not backtest_out.senales:
            continue
        ultima = backtest_out.senales[-1]
        barras_desde = (len(barras) - 1) - ultima.indice
        if barras_desde > max_barras:
            continue

        resultado.append({
            "ticker": estrategia.ticker,
            "estrategia_id": estrategia.id,
            "estrategia_nombre": estrategia.nombre,
            "tipo": ultima.tipo,
            "fecha": ultima.fecha,
            "precio": ultima.precio,
            "motivo": ultima.motivo,
            "barras_desde": barras_desde,
            "variante": variante,
            "moneda": serie["moneda"],
        })

    resultado.sort(key=lambda s: (s["barras_desde"], s["ticker"]))
    return resultado
