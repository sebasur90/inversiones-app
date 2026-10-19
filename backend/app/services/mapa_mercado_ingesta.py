"""Ingesta de las variaciones del mapa de mercado: una descarga en lote desde Yahoo.

Baja ~13 meses de cierres de todos los emisores aptos del catálogo (acciones locales, CEDEARs y
ETFs) y guarda **una foto por símbolo** (`VariacionMercado`): último cierre y variación a 1 día,
1 semana, 1 mes y 1 año.

Decisiones:
- **Todo en USD.** Los CEDEARs se miden por el subyacente en EE.UU., que es lo que dice si "la
  empresa subió o bajó" (el precio en pesos mezcla el movimiento del dólar CCL). Las acciones
  locales (`.BA`) cotizan en pesos: se convierten por el MEP de cada fecha. Si falta MEP la
  variación queda en pesos y la fila lo dice (`moneda='ARS'`).
- **La red va fuera de `sync_lock`** y la escritura es un solo commit al final, igual que la
  ingesta de fundamentales.
- **Tandas de `TAMANO_TANDA` símbolos**, con pausa entre tandas y corte ante un límite de tasa:
  seguir pidiendo sólo alarga el bloqueo. Lo ya obtenido se guarda igual.
- No toca IOL. Respeta `USE_EXTERNAL_APIS`.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..database import IndiceMercado, VariacionMercado
from . import clasificacion_engine as ce
from . import mapa_mercado_engine as eng
from . import sync_lock
from .fundamentales_ingesta import construir_universo
from .market_data import yahoo
from .market_data.client import use_external_apis

logger = logging.getLogger("mapa_mercado_ingesta")

TAMANO_TANDA = 100
PAUSA_ENTRE_TANDAS_SEG = 1.0
# 13 meses: el año completo más margen para que haya un cierre en o antes de hace 365 días.
DIAS_HISTORIA = 400
LOCK_ESCRITURA_TIMEOUT_SEG = 300
SUFIJO_LOCAL = ".BA"

# Una sola corrida a la vez (el job y el botón de la app). No bloqueante.
_lock_ingesta = threading.Lock()


def simbolos_aptos(db: Session) -> list[str]:
    """Símbolos de Yahoo de los emisores de renta variable del universo, sin repetir y ordenados."""
    universo = construir_universo(db)
    return sorted({
        em.simbolo_yahoo for em in universo.values()
        if em.simbolo_yahoo and em.metodo != ce.METODO_NO_APTO
    })


def _mep_por_fecha(db: Session, desde: date) -> dict[date, float]:
    return {
        f.fecha: float(f.mep)
        for f in db.query(IndiceMercado.fecha, IndiceMercado.mep)
        .filter(IndiceMercado.fecha >= desde, IndiceMercado.mep.isnot(None))
    }


def calcular(
    cierres: dict[str, list[tuple[date, float]]], mep: dict[date, float], hoy: date,
) -> dict[str, tuple[eng.Variaciones, str]]:
    """`{simbolo: (variaciones, moneda)}` a partir de los cierres crudos. Puro y testeable."""
    out: dict[str, tuple[eng.Variaciones, str]] = {}
    for simbolo, serie in cierres.items():
        moneda = "USD"
        if simbolo.upper().endswith(SUFIJO_LOCAL):
            convertida = eng.a_usd(serie, mep)
            if convertida is not None:
                serie = convertida
            else:
                moneda = "ARS"
        v = eng.variaciones(serie, hoy=hoy)
        if v is not None:
            out[simbolo] = (v, moneda)
    return out


def correr(db: Session, tanda: int = TAMANO_TANDA, pausa_seg: float | None = None) -> dict:
    """Una corrida completa. Hace commit. Nunca lanza por red."""
    if not use_external_apis():
        return {"resultado": "sin_fuentes", "simbolos": 0, "con_datos": 0}
    if not _lock_ingesta.acquire(blocking=False):
        return {"resultado": "en_curso", "simbolos": 0, "con_datos": 0}
    try:
        return _correr(db, tanda, PAUSA_ENTRE_TANDAS_SEG if pausa_seg is None else pausa_seg)
    finally:
        _lock_ingesta.release()


def _correr(db: Session, tanda: int, pausa: float) -> dict:
    inicio = time.monotonic()
    hoy = date.today()
    desde = hoy - timedelta(days=DIAS_HISTORIA)

    # -- 1. Lectura (corta) --
    simbolos = simbolos_aptos(db)
    mep = _mep_por_fecha(db, desde)
    db.rollback()  # la parte de red puede tardar minutos

    # -- 2. Red (sin lock) --
    cierres: dict[str, list[tuple[date, float]]] = {}
    rate_limited = False
    for i in range(0, len(simbolos), tanda):
        if i and pausa:
            time.sleep(pausa)
        lote, limitado = yahoo.fetch_cierres_lote(simbolos[i:i + tanda], desde, hoy)
        cierres.update(lote)
        if limitado:
            rate_limited = True
            break

    calculado = calcular(cierres, mep, hoy)

    # -- 3. Escritura (un solo commit, con el lock del sync) --
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("mapa de mercado: el sync no soltó el lock en %ds; se descarta la corrida",
                       LOCK_ESCRITURA_TIMEOUT_SEG)
        return {"resultado": "lock_ocupado", "simbolos": len(simbolos), "con_datos": 0}
    try:
        existentes = {f.simbolo_yahoo: f for f in db.query(VariacionMercado)}
        ahora = datetime.utcnow()
        for simbolo, (v, moneda) in calculado.items():
            fila = existentes.get(simbolo)
            if fila is None:
                fila = VariacionMercado(simbolo_yahoo=simbolo)
                db.add(fila)
            fila.fecha_cierre = v.fecha_cierre
            fila.cierre = v.cierre
            fila.moneda = moneda
            fila.var_1d, fila.var_1s, fila.var_1m, fila.var_1a = v.var_1d, v.var_1s, v.var_1m, v.var_1a
            fila.actualizado = ahora
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()

    duracion = int((time.monotonic() - inicio) * 1000)
    resultado = "rate_limited" if rate_limited else "ok"
    logger.info(
        "mapa de mercado: %d símbolos pedidos, %d con datos%s, %d ms",
        len(simbolos), len(calculado), ", cortado por límite de tasa" if rate_limited else "", duracion,
    )
    return {"resultado": resultado, "simbolos": len(simbolos), "con_datos": len(calculado),
            "duration_ms": duracion}
