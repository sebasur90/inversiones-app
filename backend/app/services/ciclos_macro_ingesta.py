"""Ingesta de las series macroeconómicas del régimen: CSV público de FRED, sin API key.

- **Cada descarga reemplaza la serie entera.** Los datos macro se revisan (el PIB, el empleo y el IPC cambian después de
  publicarse) y FRED entrega la versión vigente; mezclar versiones sería peor que reemplazar.
- **No se pisa lo bueno con lo malo:** una respuesta que no es un CSV de FRED, vacía o sin suficientes observaciones deja
  la serie como estaba y se registra el error.
- **La red va fuera de `sync_lock`** y la escritura es corta, con el lock (mismo criterio que `ciclos_ingesta`).
- Una serie ya bajada hace menos de `MIN_HORAS_ENTRE_DESCARGAS` no se vuelve a pedir (salvo `forzar`): estos datos cambian
  una vez por mes o por semana. Tras `MAX_FALLOS_DE_RED_SEGUIDOS` fallos sin respuesta se corta la corrida.
- Respeta `USE_EXTERNAL_APIS` y no toca IOL.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..database import CiclosMacroEstado, CiclosMacroObs
from . import ciclos_macro_catalogo as mc
from . import sync_lock
from .market_data.client import get_text, use_external_apis

logger = logging.getLogger("ciclos_macro_ingesta")

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
INICIO_HISTORIA = date(2000, 1, 1)
TIMEOUT_SEG = 30.0
PAUSA_ENTRE_SERIES_SEG = 0.3
MIN_HORAS_ENTRE_DESCARGAS = 20
MIN_OBSERVACIONES = 12
MAX_FALLOS_DE_RED_SEGUIDOS = 3
LOCK_ESCRITURA_TIMEOUT_SEG = 300

_lock_ingesta = threading.Lock()


def parsear_csv(texto: str | None, serie_id: str) -> list[tuple[date, float]]:
    """`[(fecha, valor)]` ordenado y sin repetidos, o `[]` si el texto no es el CSV de esa serie.

    Un valor vacío o «.» es un dato faltante de FRED: se omite, no se completa."""
    if not texto:
        return []
    filas = list(csv.reader(io.StringIO(texto.strip())))
    if len(filas) < 2 or len(filas[0]) != 2 or filas[0][1].strip() != serie_id:
        return []
    por_fecha: dict[date, float] = {}
    for fila in filas[1:]:
        if len(fila) != 2:
            continue
        try:
            fecha, valor = date.fromisoformat(fila[0].strip()), float(fila[1])
        except ValueError:
            continue
        if math.isfinite(valor):
            por_fecha[fecha] = valor
    return sorted(por_fecha.items())


def pendientes(cat: mc.CatalogoMacro, estados: dict[str, CiclosMacroEstado], ahora: datetime, forzar: bool = False) -> list[str]:
    """Series a bajar: las que nunca se bajaron bien, o cuya última descarga buena es más vieja que el mínimo."""
    if forzar:
        return list(cat.series)
    limite = ahora - timedelta(hours=MIN_HORAS_ENTRE_DESCARGAS)
    out = []
    for sid in cat.series:
        est = estados.get(sid)
        if est is None or est.estado != "ok" or est.ultimo_ok is None or est.ultimo_ok < limite:
            out.append(sid)
    return out


def correr(db: Session, *, forzar: bool = False, pausa_seg: float | None = None) -> dict:
    """Una corrida completa. Hace commit. Nunca lanza por red."""
    if not use_external_apis():
        return {"resultado": "sin_fuentes", "series": 0}
    if not _lock_ingesta.acquire(blocking=False):
        return {"resultado": "en_curso", "series": 0}
    try:
        return _correr(db, forzar, PAUSA_ENTRE_SERIES_SEG if pausa_seg is None else pausa_seg)
    finally:
        _lock_ingesta.release()


def _correr(db: Session, forzar: bool, pausa: float) -> dict:
    inicio = time.monotonic()
    cat = mc.cargar()
    if not cat.series:
        return {"resultado": "catalogo_vacio", "series": 0, "errores": cat.errores}
    ahora = datetime.utcnow()
    estados = {e.serie_id: e for e in db.query(CiclosMacroEstado).all()}
    a_bajar = pendientes(cat, estados, ahora, forzar)
    db.rollback()                                           # la parte de red puede tardar: sin transacción abierta
    if not a_bajar:
        return {"resultado": "al_dia", "series": len(cat.series), "bajadas": 0}

    # -- Red (sin lock) --
    bajadas: dict[str, list[tuple[date, float]]] = {}
    errores: dict[str, str] = {}
    fallos_seguidos = 0
    for i, sid in enumerate(a_bajar):
        if i and pausa:
            time.sleep(pausa)
        status, texto = get_text(URL, params={"id": sid, "cosd": INICIO_HISTORIA.isoformat()}, timeout=TIMEOUT_SEG)
        if status is None:
            errores[sid] = "no hubo respuesta de FRED (timeout, proxy o DNS)"
            fallos_seguidos += 1
            if fallos_seguidos >= MAX_FALLOS_DE_RED_SEGUIDOS:
                for resto in a_bajar[i + 1:]:
                    errores[resto] = "se cortó la corrida: FRED no responde"
                break
            continue
        fallos_seguidos = 0
        if status != 200:
            errores[sid] = f"FRED respondió {status}"
            continue
        serie = parsear_csv(texto, sid)
        if len(serie) < MIN_OBSERVACIONES:
            errores[sid] = "la respuesta de FRED no trae una serie válida"
            continue
        bajadas[sid] = serie

    # -- Escritura (corta, con el lock del sync) --
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("ciclos macro: el sync no soltó el lock en %ds; se descarta la corrida", LOCK_ESCRITURA_TIMEOUT_SEG)
        return {"resultado": "lock_ocupado", "series": len(cat.series)}
    try:
        estados = {e.serie_id: e for e in db.query(CiclosMacroEstado).all()}
        for sid in a_bajar:
            est = estados.get(sid)
            if est is None:
                est = CiclosMacroEstado(serie_id=sid, estado="sin_intentar", n_obs=0)
                db.add(est)
                estados[sid] = est
            est.ultimo_intento = ahora
            if sid in bajadas:
                serie = bajadas[sid]
                db.query(CiclosMacroObs).filter(CiclosMacroObs.serie_id == sid).delete(synchronize_session=False)
                db.bulk_insert_mappings(CiclosMacroObs, [{"serie_id": sid, "fecha": f, "valor": v} for f, v in serie])
                est.estado, est.error, est.ultimo_ok = "ok", None, ahora
                est.n_obs, est.primera_fecha, est.ultima_fecha = len(serie), serie[0][0], serie[-1][0]
            else:
                est.error = errores.get(sid, "sin respuesta")
                if est.estado == "sin_intentar":
                    est.estado = "error"
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()

    duracion = int((time.monotonic() - inicio) * 1000)
    logger.info("ciclos macro: %d de %d series bajadas, %d con error, %d ms", len(bajadas), len(a_bajar), len(errores), duracion)
    return {"resultado": "ok" if not errores else ("parcial" if bajadas else "error"), "series": len(cat.series),
            "bajadas": len(bajadas), "errores": errores, "duration_ms": duracion}


def correr_seguro(db: Session, *, forzar: bool = False) -> dict:
    """`correr` para los jobs: nunca lanza. Un fallo acá no puede deshacer lo que la descarga de mercado ya guardó."""
    try:
        return correr(db, forzar=forzar)
    except Exception as exc:
        logger.exception("ciclos macro: la descarga falló: %s", exc)
        db.rollback()
        return {"resultado": "error", "error": str(exc)}
