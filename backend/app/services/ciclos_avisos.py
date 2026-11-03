"""Adaptador DB → `ciclos_avisos_engine` → Telegram: avisa los cambios de estado confirmados de Ciclos de mercado
**en los grupos donde hay posición**.

Orden de las operaciones, a propósito (mismo criterio que `alertas_analytics`): primero se registra qué cambios se
trataron y se commitea, después se manda el mensaje. La red no corre con una transacción de escritura abierta, y si
el envío falla las filas quedan `entregado = 0` y la corrida siguiente reintenta sin tratar el cambio como nuevo.

- **Dedup:** `ciclos_avisos_emitidos` guarda cada cambio una vez (ver `CiclosAvisoEmitido`).
- **Interruptor apagado** (`avisar_ciclos`): los cambios se registran igual como `silenciado`; prenderlo después no
  manda de golpe lo que pasó mientras estaba apagado.
- **Sin posición:** se decide al momento del envío con el mismo cálculo que la ficha («tus posiciones en el grupo»),
  así que un grupo que vendiste entre la detección y el envío no genera aviso.
- **Sin recomendaciones:** el mensaje dice qué cambió y cuánto pesa en la cartera, nada más.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..database import CiclosAvisoEmitido
from . import avisos_config, ciclos_analytics as ca, ciclos_avisos_engine as ae, ciclos_catalogo as cc
from . import ciclos_cartera, ciclos_historial, ciclos_senales_engine, sync_lock

logger = logging.getLogger("ciclos_avisos")

LOCK_ESCRITURA_TIMEOUT_SEG = 300
EPS = 1e-9

MOTIVO_NUEVO = "nuevo"
MOTIVO_SILENCIADO = "silenciado"
MOTIVO_SIN_POSICION = "sin_posicion"

ETIQUETA_TIPO_GRUPO = {
    "sector": "sector", "industria": "industria", "commodity": "commodity", "region": "región",
    "pais": "país", "activo": "activo", "tema": "tema",
}


def _detectar(db: Session, cat: cc.Catalogo) -> list[ae.Cambio]:
    """Los cambios confirmados de todos los grupos activos, desde el historial semanal."""
    cambios: list[ae.Cambio] = []
    for g in cat.activos():
        b = ca._benchmark_efectivo(cat, g)
        if b is None:
            continue
        historial = ciclos_historial.historial_de(db, g.id, b.id)
        if historial:
            cambios.extend(ae.desde_senales(g.id, b.id, ciclos_senales_engine.detectar(historial)))
    return cambios


def _registrados(db: Session) -> set[tuple]:
    return {(f.grupo_id, f.benchmark_id, f.tipo, f.desde) for f in db.query(CiclosAvisoEmitido)}


def _fila(c: ae.Cambio, motivo: str, entregado: int, ahora: datetime) -> CiclosAvisoEmitido:
    return CiclosAvisoEmitido(
        grupo_id=c.grupo_id, benchmark_id=c.benchmark_id, tipo=c.tipo, desde=c.desde, de=c.de, a=c.a, semanas=c.semanas,
        motivo=motivo, entregado=entregado, emitido_en=None, registrado_en=ahora,
    )


def _commit(db: Session) -> bool:
    """Commit bajo `sync_lock` (el sync también escribe). `False` si el lock no se liberó a tiempo."""
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("ciclos: el sync no soltó el lock; no se registran los avisos en esta corrida")
        db.rollback()
        return False
    try:
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()


def _avisos_de_pendientes(
    db: Session, cat: cc.Catalogo, pendientes: list[CiclosAvisoEmitido], hoy: date,
) -> tuple[list[ae.AvisoGrupo], list[CiclosAvisoEmitido], list[CiclosAvisoEmitido], list[CiclosAvisoEmitido]]:
    """`(avisos, filas_a_enviar, filas_sin_posicion, filas_viejas)` a partir de las filas sin entregar."""
    por_cambio: dict[tuple, list[CiclosAvisoEmitido]] = {}
    for f in pendientes:
        por_cambio.setdefault((f.grupo_id, f.benchmark_id, f.desde), []).append(f)

    avisos, a_enviar, sin_posicion, viejas = [], [], [], []
    for (grupo_id, bench_id, desde), filas in sorted(por_cambio.items(), key=lambda kv: (kv[0][2], kv[0][0])):
        if (hoy - desde).days > ae.MAX_DIAS_CAMBIO:
            viejas.extend(filas)
            continue
        g, b = cat.grupos.get(grupo_id), cat.grupos.get(bench_id)
        if g is None or b is None:
            sin_posicion.extend(filas)       # el grupo salió del catálogo: no hay nada que mostrar
            continue
        try:
            detalle = ciclos_cartera.instrumentos_de_grupo(None, db, grupo_id, hoy=hoy)
        except Exception:
            logger.exception("ciclos: no se pudo medir la posición en %s; se reintenta en la próxima corrida", grupo_id)
            continue
        if detalle["exposicion_usd"] <= EPS or not detalle["instrumentos"]:
            sin_posicion.extend(filas)
            continue
        avisos.append(ae.AvisoGrupo(
            nombre=g.nombre, tipo_grupo=ETIQUETA_TIPO_GRUPO.get(g.tipo, g.tipo), benchmark=b.nombre,
            de=filas[0].de, a=filas[0].a, desde=desde, semanas=max(f.semanas for f in filas),
            tipos=tuple(sorted(f.tipo for f in filas)), peso_pct=float(detalle["exposicion_pct"]),
            tickers=tuple(i["emisor"] for i in detalle["instrumentos"]),
        ))
        a_enviar.extend(filas)
    return avisos, a_enviar, sin_posicion, viejas


def evaluar_y_notificar(db: Session, notificar: bool = True, hoy: date | None = None) -> dict:
    """Registra los cambios confirmados nuevos y avisa los de grupos con posición. Hace commit.

    `notificar=False` registra sin mandar nada y sin dejar nada encolado (siembra).
    """
    from .notificaciones import telegram

    hoy = hoy or date.today()
    cat = cc.cargar()
    cambios = _detectar(db, cat)
    ajustes = avisos_config.obtener(db)
    primera_vez = ajustes.ciclos_semilla_en is None
    reparto = ae.clasificar(cambios, _registrados(db), hoy, primera_vez=primera_vez)
    habilitado = avisos_config.ciclos_habilitado(db) and notificar
    ahora = datetime.utcnow()
    if primera_vez:
        ajustes.ciclos_semilla_en = ahora

    for c in reparto[ae.SEMBRADO]:
        db.add(_fila(c, ae.SEMBRADO, 1, ahora))
    for c in reparto[ae.VIEJO]:
        db.add(_fila(c, ae.VIEJO, 1, ahora))
    for c in reparto[ae.NUEVO]:
        db.add(_fila(c, MOTIVO_NUEVO if habilitado else MOTIVO_SILENCIADO, 0 if habilitado else 1, ahora))

    resumen = {
        "cambios_confirmados": len(cambios), "sembrados": len(reparto[ae.SEMBRADO]), "viejos": len(reparto[ae.VIEJO]),
        "nuevos": len(reparto[ae.NUEVO]), "silenciados": 0 if habilitado else len(reparto[ae.NUEVO]),
        "sin_posicion": 0, "avisados": 0, "entregado": False, "motivo": None,
    }
    if not _commit(db):
        return {**resumen, "motivo": "lock_ocupado"}
    if not habilitado:
        return resumen

    pendientes = db.query(CiclosAvisoEmitido).filter(
        CiclosAvisoEmitido.entregado == 0, CiclosAvisoEmitido.motivo == MOTIVO_NUEVO).all()
    if not pendientes:
        return resumen

    avisos, a_enviar, sin_posicion, viejas = _avisos_de_pendientes(db, cat, pendientes, hoy)
    for f in sin_posicion:
        f.entregado, f.motivo = 1, MOTIVO_SIN_POSICION
    for f in viejas:
        f.entregado, f.motivo = 1, ae.VIEJO
    resumen["sin_posicion"] = len(sin_posicion)
    if not avisos:
        _commit(db)
        return resumen

    # Se commitea lo descartado antes de la red, pero lo que se va a mandar queda `entregado = 0` hasta saber si salió.
    if not _commit(db):
        return {**resumen, "motivo": "lock_ocupado"}
    entregado, motivo = telegram.enviar(ae.texto_notificacion(avisos), parse_mode="HTML")
    resumen.update(avisados=len(avisos), entregado=entregado, motivo=motivo)
    if not entregado:
        logger.warning("ciclos: %d aviso(s) sin entregar: %s", len(avisos), motivo)
        return resumen
    ahora = datetime.utcnow()
    for f in a_enviar:
        f.entregado, f.emitido_en = 1, ahora
    _commit(db)
    logger.info("ciclos: %d cambio(s) avisado(s)", len(avisos))
    return resumen


def correr(db: Session) -> dict:
    """`evaluar_y_notificar` para los jobs: nunca lanza. Un fallo acá no puede deshacer la descarga que lo precede."""
    try:
        return evaluar_y_notificar(db)
    except Exception as exc:
        logger.exception("ciclos: la evaluación de avisos falló: %s", exc)
        db.rollback()
        return {"resultado": "error", "error": str(exc)}
