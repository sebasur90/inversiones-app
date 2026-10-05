"""Jobs programados: traer datos y evaluar las alertas sin que nadie abra la app.

Hasta ahora el sync era **pull desde el cliente**: lo disparaba el botón del header o
`useAutoSync` al abrir la PWA. Eso significa que si nadie abre la app, no entra ningún dato -- y
una alerta de precio que sólo se evalúa cuando el usuario mira la app no sirve de nada.

Son **dos jobs distintos**, y la diferencia es deliberada:

| Job | Cuándo | Qué hace |
|---|---|---|
| `sync_y_alertas` | lun-vie 18:30 (tras el cierre) | sync completo del Sheet + evaluar alertas |
| `refresco_y_alertas` | lun-vie 11, 13, 15, 17 (rueda) | sólo cotizaciones + evaluar alertas |

El sync completo no se puede correr cada dos horas: lee el Sheet entero, valida ocho pestañas,
escribe ~20 bloques de delete/insert y deja un `SyncRun`. Con varias corridas por día consumiría en
pocas jornadas el historial de 20 que sirve para ver problemas del Sheet, y su `health_score`
perfecto (no mira el Sheet) ensuciaría el sparkline de Calidad de datos. De ahí el job liviano:
`services/refresco_precios.py`.

Decisiones comunes a los dos:

- **APScheduler dentro del contenedor**, no un cron del host: viaja con la imagen, así que el
  despliegue no depende de que alguien instale una unit de systemd aparte.
- **Apagado por default** (`SCHEDULER_ENABLED`): en la máquina de desarrollo no tiene que pegarle
  a IOL ni gastar cupo.
- Respetan `sync_lock`: si el usuario está sincronizando desde la app, la corrida se saltea en vez
  de encolarse (ver `services/sync_lock.py`). Eso también evita que el refresco y el sync escriban
  a la vez.
- Sesión propia: un job no tiene request, así que no puede usar `Depends(get_db)`.
- Una excepción en el job no puede matar al worker: se loguea y la corrida siguiente reintenta.

Costo de cupo IOL: tanto un sync en régimen como un refresco gastan ~10 llamadas (1 token + ~9
paneles). Un sync diario más cuatro refrescos por día hábil son ~1.050 llamadas al mes contra el
tope de 22.000 de `IOL_LIMITE_MENSUAL` -- menos del 5%.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("scheduler")

# Default: después del cierre del mercado argentino (17:00 ART), con margen para que los precios
# del día ya estén publicados.
HORA_DEFAULT = 18
MINUTO_DEFAULT = 30
ZONA_DEFAULT = "America/Argentina/Buenos_Aires"

# Horas del refresco liviano: la rueda de contado va de 11 a 17, así que cada dos horas cubre la
# apertura, el medio y el cierre. El minuto 5 es para no pegarle al segundo exacto de la hora.
HORAS_REFRESCO_DEFAULT = "11,13,15,17"
MINUTO_REFRESCO_DEFAULT = 5

_scheduler = None


def habilitado() -> bool:
    return (os.getenv("SCHEDULER_ENABLED") or "false").lower() in ("true", "1", "yes")


def _entero_env(nombre: str, default: int, minimo: int, maximo: int) -> int:
    crudo = (os.getenv(nombre) or "").strip()
    if not crudo:
        return default
    try:
        valor = int(crudo)
    except ValueError:
        logger.warning("scheduler: %s=%r no es un entero; se usa %d", nombre, crudo, default)
        return default
    if not minimo <= valor <= maximo:
        logger.warning("scheduler: %s=%d fuera de rango; se usa %d", nombre, valor, default)
        return default
    return valor


def _evaluar_alertas() -> None:
    """Evalúa los niveles y manda el aviso. Nunca lanza.

    Corre **aunque la traída de datos haya fallado o se haya salteado**: los niveles se comparan
    contra los últimos precios que haya en la base, y un sync fallido no es razón para dejar de
    avisar de un cruce que ya ocurrió.
    """
    from ..database import SessionLocal
    from . import alertas_analytics

    db = SessionLocal()
    try:
        resumen = alertas_analytics.evaluar_y_notificar(db)
        logger.info("scheduler: alertas %s", resumen)
    except Exception as exc:
        logger.exception("scheduler: la evaluación de alertas falló: %s", exc)
        db.rollback()
    finally:
        db.close()


def _horas_refresco() -> str:
    """Las horas del refresco como las espera `CronTrigger` (`"11,13,15,17"`), validadas.

    Vacío (`REFRESCO_HORAS=`) desactiva el job liviano sin tocar el de cierre. Una hora inválida
    descarta la lista entera en vez de programar algo a medias: es mejor no tener refresco y verlo
    en el log que descubrir meses después que corría sólo a una hora.
    """
    crudo = os.getenv("REFRESCO_HORAS")
    if crudo is None:
        crudo = HORAS_REFRESCO_DEFAULT
    crudo = crudo.strip()
    if not crudo:
        return ""

    horas: list[int] = []
    for parte in crudo.split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            hora = int(parte)
        except ValueError:
            logger.warning(
                "scheduler: REFRESCO_HORAS=%r tiene un valor no numérico (%r); se usa %r",
                crudo, parte, HORAS_REFRESCO_DEFAULT,
            )
            return HORAS_REFRESCO_DEFAULT
        if not 0 <= hora <= 23:
            logger.warning(
                "scheduler: REFRESCO_HORAS=%r tiene una hora fuera de rango (%d); se usa %r",
                crudo, hora, HORAS_REFRESCO_DEFAULT,
            )
            return HORAS_REFRESCO_DEFAULT
        horas.append(hora)

    if not horas:
        return ""
    return ",".join(str(h) for h in sorted(set(horas)))


def correr_sync_y_alertas() -> None:
    """Job de cierre: sync completo del Sheet + alertas. Nunca lanza."""
    # Imports locales: este módulo se importa desde `main`, y a nivel de módulo arrastraría toda
    # la cadena de servicios antes de que `init_db` haya corrido.
    from ..database import SessionLocal
    from . import sync_lock
    from .inversiones_sync import sync_from_sheet

    if sync_lock.lock.acquire(blocking=False):
        db = SessionLocal()
        try:
            resultado = sync_from_sheet(db)
            logger.info(
                "scheduler: sync ok (health_score=%s, issues=%s)",
                getattr(resultado, "health_score", None), len(getattr(resultado, "issues", []) or []),
            )
        except Exception as exc:
            logger.exception("scheduler: el sync falló: %s", exc)
            db.rollback()
        finally:
            db.close()
            sync_lock.lock.release()
    else:
        logger.info("scheduler: ya hay un sync en curso, se saltea esta corrida")

    _evaluar_alertas()


def correr_refresco_y_alertas() -> None:
    """Job de rueda: sólo cotizaciones + alertas. Nunca lanza.

    Toma el mismo lock que el sync: el refresco también escribe en `precios_instrumento`, y dos
    escritores a la vez sobre SQLite es exactamente lo que el lock evita. Si el sync está corriendo
    se saltea el refresco (los precios los va a traer el sync igual) pero **las alertas se evalúan
    de todos modos**.
    """
    from ..database import SessionLocal
    from . import refresco_precios, sync_lock

    if sync_lock.lock.acquire(blocking=False):
        db = SessionLocal()
        try:
            resumen = refresco_precios.refrescar(db)
            logger.info("scheduler: refresco %s", resumen)
        except Exception as exc:
            logger.exception("scheduler: el refresco de precios falló: %s", exc)
            db.rollback()
        finally:
            db.close()
            sync_lock.lock.release()
    else:
        logger.info("scheduler: hay un sync en curso, se saltea el refresco de precios")

    _evaluar_alertas()


def iniciar() -> None:
    """Arranca el scheduler si está habilitado. Tolera que APScheduler no esté instalado."""
    global _scheduler
    if not habilitado():
        logger.info("scheduler: deshabilitado (SCHEDULER_ENABLED)")
        return
    if _scheduler is not None:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("scheduler: apscheduler no está instalado; no se programa nada")
        return

    hora = _entero_env("SCHEDULER_HORA", HORA_DEFAULT, 0, 23)
    minuto = _entero_env("SCHEDULER_MINUTO", MINUTO_DEFAULT, 0, 59)
    zona = (os.getenv("SCHEDULER_TZ") or ZONA_DEFAULT).strip()
    horas_refresco = _horas_refresco()
    minuto_refresco = _entero_env("REFRESCO_MINUTO", MINUTO_REFRESCO_DEFAULT, 0, 59)

    try:
        scheduler = BackgroundScheduler(timezone=zona)
        scheduler.add_job(
            correr_sync_y_alertas,
            CronTrigger(day_of_week="mon-fri", hour=hora, minute=minuto, timezone=zona),
            id="sync_y_alertas",
            # Si el contenedor estuvo caído a la hora del job, correrlo al volver sólo tiene
            # sentido dentro de una ventana razonable; y nunca dos veces solapadas.
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        if horas_refresco:
            scheduler.add_job(
                correr_refresco_y_alertas,
                CronTrigger(
                    day_of_week="mon-fri", hour=horas_refresco, minute=minuto_refresco, timezone=zona,
                ),
                id="refresco_y_alertas",
                # Margen corto: un refresco de hace dos horas ya no sirve de nada, lo cubre el
                # siguiente de la rueda.
                misfire_grace_time=900,
                coalesce=True,
                max_instances=1,
            )
        scheduler.start()
    except Exception as exc:
        logger.exception("scheduler: no se pudo iniciar: %s", exc)
        return

    _scheduler = scheduler
    logger.info("scheduler: sync lun-vie %02d:%02d (%s)", hora, minuto, zona)
    if horas_refresco:
        logger.info(
            "scheduler: refresco de precios lun-vie a las %s (minuto %02d)",
            horas_refresco, minuto_refresco,
        )
    else:
        logger.info("scheduler: refresco de precios desactivado (REFRESCO_HORAS vacío)")


def detener() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover
            logger.warning("scheduler: fallo al detener", exc_info=True)
        _scheduler = None
