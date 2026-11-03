"""Ingesta de las series de «Ciclos de mercado»: cierres diarios ajustados de Yahoo en lote.

Baja lo que pide el catálogo (`ciclos_catalogo`): proxies, índices locales y tipos de cambio. Las
barras se guardan en `serie_ohlcv` bajo `SIMBOLO@BENCH` (ver `benchmarks.py`): esa clave ya está
protegida de la purga del sync y no pertenece al universo técnico. No se crea otra tabla de precios.

Decisiones:
- **Primera vez = historia entera** (desde `INICIO_HISTORIA`); después incremental con un solape de
  `SOLAPE_DIAS`. La serie empieza cuando empieza en Yahoo: nunca se extrapola hacia atrás.
- **Detección de reajuste.** Los cierres son ajustados por dividendos y splits, así que un
  dividendo o un split reescribe la historia entera. Si los cierres que Yahoo devuelve para el
  solape difieren de los guardados más que `TOLERANCIA_REAJUSTE`, se vuelve a bajar el símbolo
  completo y se reemplaza: mezclar escalas rompería todo cociente entre series.
- **Sólo ruedas cerradas** (`fecha < hoy`): el valor intradía de hoy no se persiste.
- Cierres, sin velas: alcanza para rendimientos, relaciones y correlaciones.
- **La red va fuera de `sync_lock`** y la escritura es un solo commit al final. Ante un límite de
  tasa se corta (seguir pidiendo sólo alarga el bloqueo) y se guarda lo ya obtenido.
- No toca IOL. Respeta `USE_EXTERNAL_APIS`.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import BarraOHLCV, CiclosProxyEstado
from . import benchmarks, ciclos_catalogo, ohlcv_analytics, sync_lock
from .market_data import yahoo
from .market_data.client import use_external_apis

logger = logging.getLogger("ciclos_ingesta")

INICIO_HISTORIA = date(2005, 1, 1)
SOLAPE_DIAS = 7
# Diferencia relativa a partir de la cual los cierres del solape se consideran reescritos por Yahoo.
TOLERANCIA_REAJUSTE = 2e-4
TAMANO_TANDA = 25
PAUSA_ENTRE_TANDAS_SEG = 1.0
LOCK_ESCRITURA_TIMEOUT_SEG = 300
# Sin dato más reciente que esto (días de calendario hacia atrás desde la última rueda cerrada), el
# símbolo se marca como desactualizado en vez de presentarse como vigente.
DIAS_DESACTUALIZADO = 7

ESTADO_OK = "ok"
ESTADO_NO_ENCONTRADO = "no_encontrado"
ESTADO_ERROR = "error"
ESTADO_SIN_INTENTAR = "sin_intentar"

_lock_ingesta = threading.Lock()

Serie = list[tuple[date, float]]


# ---------------------------------------------------------------------------------------------
# Puro
# ---------------------------------------------------------------------------------------------

def detectar_reajuste(
    guardado: dict[date, float], nuevo: Serie, tolerancia: float = TOLERANCIA_REAJUSTE,
) -> bool:
    """`True` si algún cierre de `nuevo` que ya teníamos guardado difiere en más de `tolerancia` (relativo)."""
    for fecha, cierre in nuevo:
        previo = guardado.get(fecha)
        if previo and abs(cierre / previo - 1.0) > tolerancia:
            return True
    return False


def filas_barras(simbolo: str, moneda: str, serie: Serie, hoy: date, desde: date | None = None) -> list[dict]:
    """Filas para `upsert_barras`: sólo ruedas cerradas, sin duplicar fechas, sólo cierre."""
    por_fecha: dict[date, float] = {}
    for fecha, cierre in serie:
        if fecha < hoy and (desde is None or fecha >= desde) and cierre and cierre > 0:
            por_fecha[fecha] = cierre
    return [
        {"ticker": benchmarks.clave(simbolo), "fecha": f, "apertura": None, "maximo": None, "minimo": None,
         "cierre": c, "volumen": None, "moneda": moneda, "fuente": "yahoo"}
        for f, c in sorted(por_fecha.items())
    ]


def ultima_rueda_cerrada(hoy: date) -> date:
    return benchmarks._ultima_rueda_cerrada(hoy)


# ---------------------------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------------------------

def _ultimas_fechas(db: Session) -> dict[str, date]:
    """`{símbolo: última fecha guardada}` de todas las series `@BENCH`."""
    sufijo = ohlcv_analytics.SUFIJO_BENCHMARK
    filas = (
        db.query(BarraOHLCV.ticker, func.max(BarraOHLCV.fecha))
        .filter(BarraOHLCV.ticker.like(f"%{sufijo}")).group_by(BarraOHLCV.ticker).all()
    )
    return {t[: -len(sufijo)]: f for t, f in filas}


def _cierres_guardados(db: Session, simbolo: str, desde: date) -> dict[date, float]:
    filas = db.query(BarraOHLCV.fecha, BarraOHLCV.cierre).filter(
        BarraOHLCV.ticker == benchmarks.clave(simbolo), BarraOHLCV.fecha >= desde,
    )
    return {f: float(c) for f, c in filas if c is not None}


def planificar(
    simbolos: list[str], estados: dict[str, CiclosProxyEstado], ultimas: dict[str, date], hoy: date,
) -> tuple[list[str], dict[str, date]]:
    """`(completos, incrementales)`: a qué símbolos hay que bajarles toda la historia y a cuáles sólo
    lo que falta (`{símbolo: desde}`). Los que ya están al día no entran en ninguno."""
    cerrada = ultima_rueda_cerrada(hoy)
    completos: list[str] = []
    incrementales: dict[str, date] = {}
    for s in simbolos:
        est = estados.get(s)
        ultima = ultimas.get(s)
        if est is None or not est.historia_completa or ultima is None:
            completos.append(s)
        elif ultima < cerrada:
            incrementales[s] = ultima - timedelta(days=SOLAPE_DIAS)
    return completos, incrementales


# ---------------------------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------------------------

def correr(db: Session, tanda: int = TAMANO_TANDA, pausa_seg: float | None = None) -> dict:
    """Una corrida completa. Hace commit. Nunca lanza por red."""
    if not use_external_apis():
        return {"resultado": "sin_fuentes", "simbolos": 0}
    if not _lock_ingesta.acquire(blocking=False):
        return {"resultado": "en_curso", "simbolos": 0}
    try:
        resultado = _correr(db, tanda, PAUSA_ENTRE_TANDAS_SEG if pausa_seg is None else pausa_seg)
        if resultado.get("resultado") in ("ok", "rate_limited"):
            resultado["historial"] = _registrar_historial(db)
        return resultado
    finally:
        _lock_ingesta.release()


def _registrar_historial(db: Session) -> dict:
    """Foto semanal del estado de rotación con lo recién bajado. Un fallo acá no deshace la descarga."""
    try:
        from . import ciclos_historial
        return ciclos_historial.registrar(db)
    except Exception as exc:  # pragma: no cover - defensivo: la descarga ya se guardó
        logger.exception("ciclos: no se pudo registrar el historial semanal: %s", exc)
        db.rollback()
        return {"resultado": "error", "error": str(exc)}


def _bajar(simbolos: list[str], desde: date, hoy: date, tanda: int, pausa: float) -> tuple[dict[str, Serie], bool]:
    """Baja `simbolos` en tandas. `(series, rate_limited)`; ante un límite de tasa devuelve lo obtenido."""
    out: dict[str, Serie] = {}
    for i in range(0, len(simbolos), tanda):
        if i and pausa:
            time.sleep(pausa)
        lote, limitado = yahoo.fetch_cierres_lote(simbolos[i:i + tanda], desde, hoy)
        out.update(lote)
        if limitado:
            return out, True
    return out, False


def _correr(db: Session, tanda: int, pausa: float) -> dict:
    inicio = time.monotonic()
    hoy = date.today()
    catalogo = ciclos_catalogo.cargar()
    info = catalogo.simbolos()
    simbolos = sorted(info)
    if not simbolos:
        return {"resultado": "catalogo_vacio", "simbolos": 0, "errores": catalogo.errores}

    # -- 1. Lectura (corta) --
    estados = {e.simbolo: e for e in db.query(CiclosProxyEstado).all()}
    ultimas = _ultimas_fechas(db)
    completos, incrementales = planificar(simbolos, estados, ultimas, hoy)
    guardados = {s: _cierres_guardados(db, s, d) for s, d in incrementales.items()}
    db.rollback()  # la parte de red puede tardar minutos

    # -- 2. Red (sin lock) --
    limitado = False
    series_completas, lim = _bajar(completos, INICIO_HISTORIA, hoy, tanda, pausa)
    limitado = limitado or lim
    series_incrementales: dict[str, Serie] = {}
    if incrementales and not limitado:
        orden = sorted(incrementales, key=lambda s: incrementales[s])
        for i in range(0, len(orden), tanda):
            lote = orden[i:i + tanda]
            if i and pausa:
                time.sleep(pausa)
            datos, lim = yahoo.fetch_cierres_lote(lote, min(incrementales[s] for s in lote), hoy)
            series_incrementales.update(datos)
            if lim:
                limitado = True
                break

    reajustados = [
        s for s, nuevo in series_incrementales.items()
        if detectar_reajuste(guardados.get(s, {}), nuevo)
    ]
    if reajustados:
        logger.info("ciclos: Yahoo reajustó la historia de %s; se re-baja entera", ", ".join(reajustados))
        if not limitado:
            rebajadas, lim = _bajar(reajustados, INICIO_HISTORIA, hoy, tanda, pausa)
            limitado = limitado or lim
        else:
            rebajadas = {}
        # Sin la serie entera no se puede reemplazar: se deja lo guardado, sin sumar barras en otra escala.
        for s in reajustados:
            if s in rebajadas:
                series_completas[s] = rebajadas[s]
            series_incrementales.pop(s, None)

    # -- 3. Escritura (un solo commit, con el lock del sync) --
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("ciclos: el sync no soltó el lock en %ds; se descarta la corrida", LOCK_ESCRITURA_TIMEOUT_SEG)
        return {"resultado": "lock_ocupado", "simbolos": len(simbolos)}
    try:
        ahora = datetime.utcnow()
        estados = {e.simbolo: e for e in db.query(CiclosProxyEstado).all()}
        sin_datos: list[str] = []

        for s, serie in series_completas.items():
            # Una descarga entera reemplaza lo guardado: una sola escala para toda la serie.
            filas = filas_barras(s, info[s].moneda, serie, hoy)
            if not filas:
                continue
            db.query(BarraOHLCV).filter(BarraOHLCV.ticker == benchmarks.clave(s)).delete(synchronize_session=False)
            ohlcv_analytics.upsert_barras(db, filas)
        for s, serie in series_incrementales.items():
            ohlcv_analytics.upsert_barras(db, filas_barras(s, info[s].moneda, serie, hoy, desde=incrementales[s]))

        for s in simbolos:
            est = estados.get(s)
            if est is None:
                est = CiclosProxyEstado(simbolo=s, estado=ESTADO_SIN_INTENTAR, n_barras=0, historia_completa=0, reajustes=0)
                db.add(est)
                estados[s] = est
            if s in completos or s in reajustados:
                est.ultimo_intento = ahora
                if s in series_completas and series_completas[s]:
                    est.estado, est.error = ESTADO_OK, None
                    est.historia_completa = 1
                    est.ultimo_ok = ahora
                    if s in reajustados:
                        est.reajustes = (est.reajustes or 0) + 1
                elif s in reajustados:
                    est.error = "reajuste detectado pero no se pudo volver a bajar la serie"
                elif limitado:
                    est.error = "límite de tasa de Yahoo"
                    if est.estado == ESTADO_SIN_INTENTAR:
                        est.estado = ESTADO_ERROR
                    sin_datos.append(s)
                else:
                    est.estado, est.error = ESTADO_NO_ENCONTRADO, "Yahoo no devolvió datos"
                    sin_datos.append(s)
            elif s in incrementales:
                est.ultimo_intento = ahora
                if s in series_incrementales:
                    est.ultimo_ok = ahora
                    est.error = None
                elif limitado:
                    est.error = "límite de tasa de Yahoo"

        db.flush()
        _refrescar_cobertura(db, estados)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()

    duracion = int((time.monotonic() - inicio) * 1000)
    resultado = "rate_limited" if limitado else "ok"
    logger.info(
        "ciclos: %d símbolos (%d completos, %d incrementales, %d reajustados)%s, %d sin datos, %d ms",
        len(simbolos), len(completos), len(incrementales), len(reajustados),
        ", cortado por límite de tasa" if limitado else "", len(sin_datos), duracion,
    )
    return {
        "resultado": resultado, "simbolos": len(simbolos), "completos": len(completos),
        "incrementales": len(incrementales), "reajustados": len(reajustados), "sin_datos": sin_datos,
        "duration_ms": duracion,
    }


def _refrescar_cobertura(db: Session, estados: dict[str, CiclosProxyEstado]) -> None:
    """Primera/última fecha y cantidad de barras de cada símbolo, leídas de lo que quedó en `serie_ohlcv`."""
    sufijo = ohlcv_analytics.SUFIJO_BENCHMARK
    filas = (
        db.query(BarraOHLCV.ticker, func.min(BarraOHLCV.fecha), func.max(BarraOHLCV.fecha), func.count(BarraOHLCV.id))
        .filter(BarraOHLCV.ticker.like(f"%{sufijo}")).group_by(BarraOHLCV.ticker).all()
    )
    por_simbolo = {t[: -len(sufijo)]: (d, h, n) for t, d, h, n in filas}
    for s, est in estados.items():
        d, h, n = por_simbolo.get(s, (None, None, 0))
        est.primera_fecha, est.ultima_fecha, est.n_barras = d, h, n


# ---------------------------------------------------------------------------------------------
# Estado (para la API y el script de verificación)
# ---------------------------------------------------------------------------------------------

def estado(db: Session, hoy: date | None = None) -> list[dict]:
    """Cobertura de cada símbolo del catálogo (activos). `desactualizado` si la última fecha quedó
    más de `DIAS_DESACTUALIZADO` días atrás de la última rueda cerrada."""
    hoy = hoy or date.today()
    cerrada = ultima_rueda_cerrada(hoy)
    catalogo = ciclos_catalogo.cargar()
    estados = {e.simbolo: e for e in db.query(CiclosProxyEstado).all()}
    usados: dict[str, list[str]] = {}
    for g in catalogo.activos():
        for s in (g.proxy, (g.indice_local or {}).get("simbolo"), (g.fx or {}).get("simbolo")):
            if s:
                usados.setdefault(s, []).append(g.id)
    out = []
    for s, info in sorted(catalogo.simbolos().items()):
        est = estados.get(s)
        ultima = est.ultima_fecha if est else None
        out.append({
            "simbolo": s, "rol": info.rol, "moneda": info.moneda, "grupos": usados.get(s, []),
            "estado": est.estado if est else ESTADO_SIN_INTENTAR,
            "primera_fecha": est.primera_fecha if est else None,
            "ultima_fecha": ultima,
            "n_barras": est.n_barras if est else 0,
            "reajustes": est.reajustes if est else 0,
            "ultimo_ok": est.ultimo_ok if est else None,
            "error": est.error if est else None,
            "desactualizado": bool(ultima is not None and (cerrada - ultima).days > DIAS_DESACTUALIZADO),
        })
    return out
