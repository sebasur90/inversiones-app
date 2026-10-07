"""Adaptador DB → `alertas_engine` → canal de notificación.

Lee los niveles de precio de todas las carteras y de la watchlist, pide las señales de las
estrategias que el usuario habilitó, le pregunta al motor qué hay que avisar, persiste el estado
y manda un único mensaje.

Orden de las operaciones, a propósito: **primero se persiste el estado y se commitea, después se
manda el mensaje**. La llamada de red queda fuera de cualquier transacción de escritura abierta
(el lock de escritura de SQLite durante un POST con timeout es justo el problema que ya tuvo el
sync). Si el proceso muere entre el commit y el envío, las filas quedan `disparada` con
`entregada=0` y la corrida siguiente reintenta el envío sin volver a tratar el cruce como nuevo.

Los avisos silenciados por configuración (`avisos_config`) **se siguen igual**: se guardan con
`entregada=1` y `emitida_en=NULL`. Si en cambio no se guardaran, prender el interruptor meses
después mandaría de golpe todos los cruces que pasaron mientras estaba apagado.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..database import AlertaPrecio
from . import (
    alertas_engine, avisos_config, estrategias_analytics, inversiones_analytics,
    watchlist_analytics,
)
from .notificaciones import telegram

logger = logging.getLogger("alertas")

#: Antigüedad máxima, en ruedas, de una señal para que valga un aviso. Más corta que la de la
#: pantalla (`MAX_BARRAS_SENAL_RECIENTE = 5`): mostrar una señal de hace una semana como
#: "oportunidad" en una lista es discutible, mandarla al celular como aviso es un error. El 2 deja
#: margen para un día en que la serie no se actualizó.
MAX_BARRAS_SENAL_AVISO = 2


@dataclass
class _Universo:
    """Lo que se leyó de la DB en esta corrida, para no volver a consultar nada.

    `posiciones_por_ticker` existe para las señales: su clave no lleva cartera, pero el aviso sí
    tiene que decir de qué cartera es la tenencia y cuánto hay.
    """
    candidatas: list[alertas_engine.Candidata] = field(default_factory=list)
    posiciones_por_ticker: dict[str, list[tuple[str, dict]]] = field(default_factory=dict)
    watchlist_por_ticker: dict[str, dict] = field(default_factory=dict)


def _universo(db: Session) -> _Universo:
    """Todos los niveles vigentes: stop-loss y objetivo por cartera, más la watchlist.

    Se recorre cartera por cartera (y no el consolidado) para que el aviso pueda decir de qué
    cartera es la posición, y porque el mismo ticker puede tener tenencia en más de una.
    """
    universo = _Universo()
    for cartera in inversiones_analytics.get_carteras(db):
        rendimiento = inversiones_analytics.get_rendimiento_por_ticker(cartera, db)
        universo.candidatas.extend(
            alertas_engine.candidatas_de_posiciones(rendimiento, cartera)
        )
        for fila in rendimiento:
            universo.posiciones_por_ticker.setdefault(fila.get("ticker", ""), []).append(
                (cartera, fila)
            )

    watchlist = watchlist_analytics.get_watchlist(db)
    universo.candidatas.extend(alertas_engine.candidatas_de_watchlist(watchlist))
    universo.watchlist_por_ticker = {item.get("ticker", ""): item for item in watchlist}
    return universo


# ─── Estado guardado ─────────────────────────────────────────────────────────

def _estado_guardado(db: Session) -> tuple[
    dict[tuple[str, str, str], str],
    dict[tuple[str, str, str], tuple[str | None, str | None]],
]:
    """`(estados de nivel, última señal avisada por par)`, de una sola pasada por la tabla."""
    estados: dict[tuple[str, str, str], str] = {}
    avisadas: dict[tuple[str, str, str], tuple[str | None, str | None]] = {}
    for fila in db.query(AlertaPrecio).all():
        clave = (fila.ticker, fila.tipo, fila.cartera or "")
        if alertas_engine.es_tipo_senal(fila.tipo):
            detalle = fila.detalle or {}
            avisadas[clave] = (detalle.get("senal_fecha"), detalle.get("senal_tipo"))
        else:
            estados[clave] = fila.estado
    return estados, avisadas


def _fila(db: Session, clave: tuple[str, str, str]) -> AlertaPrecio | None:
    ticker, tipo, cartera = clave
    return (
        db.query(AlertaPrecio)
        .filter(
            AlertaPrecio.ticker == ticker,
            AlertaPrecio.tipo == tipo,
            AlertaPrecio.cartera == cartera,
        )
        .first()
    )


# ─── Señales de estrategia ───────────────────────────────────────────────────

def _contexto_de_senal(senal: dict, universo: _Universo) -> alertas_engine.Contexto:
    """Enriquece la señal con la tenencia, si el ticker está en alguna cartera.

    Con tenencia en varias carteras se usan los números de la más grande y se cuentan las otras:
    poner las cinco en el mensaje lo haría ilegible, y el aviso es sobre la serie del ticker, que
    es una sola.
    """
    ticker = senal.get("ticker", "")
    posiciones = universo.posiciones_por_ticker.get(ticker) or []
    if posiciones:
        cartera, fila = max(
            posiciones, key=lambda par: abs(par[1].get("valor_actual_usd") or 0.0)
        )
        moneda = fila.get("moneda") or ""
        resultado = (
            fila.get("rendimiento_simple_ars") if moneda == "ARS"
            else fila.get("rendimiento_simple_usd")
        )
        return alertas_engine.Contexto(
            origen=alertas_engine.ORIGEN_CARTERA,
            cartera_nombre=cartera,
            carteras_extra=len(posiciones) - 1,
            cantidad=fila.get("cantidad_actual"),
            precio_promedio=fila.get("precio_promedio"),
            resultado_pct=alertas_engine.pct_desde_fraccion(resultado),
        )

    item = universo.watchlist_por_ticker.get(ticker)
    if item is not None:
        return alertas_engine.Contexto(
            origen=alertas_engine.ORIGEN_WATCHLIST, en_cartera=item.get("en_cartera"),
        )
    return alertas_engine.Contexto()


def _nombre_de_senal(senal: dict, universo: _Universo) -> str:
    """`senales_recientes` no devuelve el nombre del instrumento; se busca donde ya está."""
    ticker = senal.get("ticker", "")
    posiciones = universo.posiciones_por_ticker.get(ticker) or []
    if posiciones:
        return posiciones[0][1].get("nombre") or ticker
    item = universo.watchlist_por_ticker.get(ticker)
    if item is not None:
        return item.get("nombre") or ticker
    return ticker


def _senales_candidatas(
    db: Session, universo: _Universo, lados: dict[int, set[str]],
) -> list[alertas_engine.SenalCandidata]:
    """Señales frescas de las estrategias habilitadas, ya filtradas por lado.

    Si no hay ninguna estrategia habilitada no se llama a `senales_recientes`: correr los
    backtests de todo el universo para después descartarlos es el gasto más caro del job.
    """
    if not lados:
        return []

    crudas = estrategias_analytics.senales_recientes(
        db,
        max_antiguedad_barras=MAX_BARRAS_SENAL_AVISO,
        estrategia_ids=tuple(sorted(lados)),
    )

    salida: list[alertas_engine.SenalCandidata] = []
    for senal in crudas:
        estrategia_id = senal.get("estrategia_id")
        if senal.get("tipo") not in lados.get(estrategia_id, set()):
            continue
        fecha = senal.get("fecha")
        salida.append(alertas_engine.SenalCandidata(
            ticker=senal.get("ticker", ""),
            nombre=_nombre_de_senal(senal, universo),
            estrategia_id=estrategia_id,
            estrategia_nombre=senal.get("estrategia_nombre") or "",
            tipo=senal.get("tipo", ""),
            # ISO y no `date`: el contexto viaja a una columna JSON y `json.dumps` no sabe
            # serializar fechas.
            fecha=fecha.isoformat() if isinstance(fecha, date) else str(fecha or ""),
            precio=float(senal.get("precio") or 0.0),
            moneda=senal.get("moneda") or "",
            motivo=senal.get("motivo") or "",
            variante=senal.get("variante") or "local",
            barras_desde=int(senal.get("barras_desde") or 0),
            contexto=_contexto_de_senal(senal, universo),
        ))
    return salida


# ─── Persistencia ────────────────────────────────────────────────────────────

def _guardar_aviso(
    db: Session, alerta: alertas_engine.Alerta, ahora: datetime, silenciado: bool,
) -> None:
    """Guarda (o actualiza) la fila del aviso.

    Cada fila lleva dos cosas a la vez: el **estado** del nivel y el **registro del último aviso
    emitido** (`nivel`, `precio_disparo`, `detalle`, `emitida_en`, que es lo que lee `listar`).
    Un cruce silenciado por configuración sólo avanza el estado y **no pisa ese registro**: un
    aviso que no se mandó no tiene por qué borrar del historial el que sí se mandó.
    """
    fila = _fila(db, alerta.clave)
    nueva = fila is None
    if nueva:
        fila = AlertaPrecio(ticker=alerta.ticker, tipo=alerta.tipo, cartera=alerta.cartera)
        db.add(fila)
    fila.estado = alertas_engine.ESTADO_DISPARADA

    if silenciado:
        # `entregada=1` lo saca de la cola de pendientes; `emitida_en` queda como estaba (o en
        # `NULL` si la fila es nueva), así que no aparece en el historial.
        fila.entregada = 1
        if not nueva:
            return
        fila.emitida_en = None
    else:
        fila.entregada = 0
        fila.emitida_en = ahora

    fila.nivel = alerta.nivel
    fila.precio_disparo = alerta.precio
    fila.moneda = alerta.moneda
    fila.detalle = alertas_engine.contexto_a_detalle(alerta.nombre, alerta.contexto)


def _purgar_senales_huerfanas(db: Session, ids_habilitados: set[int]) -> int:
    """Borra las filas de señal de estrategias borradas o deshabilitadas.

    Nadie las volvería a tocar y ensucian el historial y el conteo de lo vigilado. Se respetan las
    que están sin entregar: un aviso pendiente no se tira.
    """
    borradas = 0
    for fila in db.query(AlertaPrecio).all():
        if not alertas_engine.es_tipo_senal(fila.tipo) or not fila.entregada:
            continue
        if alertas_engine.estrategia_de_tipo(fila.tipo) not in ids_habilitados:
            db.delete(fila)
            borradas += 1
    return borradas


def _aplicar(
    db: Session,
    decision: alertas_engine.Decision,
    alertas_senal: list[alertas_engine.Alerta],
    tipos_habilitados: set[str],
    ids_habilitados: set[int],
) -> None:
    """Persiste el resultado del motor. No manda nada: el envío va después del commit."""
    ahora = datetime.utcnow()

    for alerta in decision.a_emitir:
        _guardar_aviso(db, alerta, ahora, silenciado=alerta.tipo not in tipos_habilitados)

    # Las señales ya vienen filtradas por `_senales_candidatas`: si llegaron hasta acá, su
    # estrategia y su lado están habilitados.
    for alerta in alertas_senal:
        _guardar_aviso(db, alerta, ahora, silenciado=False)

    for clave in decision.a_rearmar:
        fila = _fila(db, clave)
        if fila is not None:
            fila.estado = alertas_engine.ESTADO_ARMADA

    for clave in decision.a_crear:
        ticker, tipo, cartera = clave
        db.add(AlertaPrecio(
            ticker=ticker, tipo=tipo, cartera=cartera,
            estado=alertas_engine.ESTADO_ARMADA, entregada=0,
        ))

    _purgar_senales_huerfanas(db, ids_habilitados)


def _pendientes_de_entrega(db: Session) -> list[alertas_engine.Alerta]:
    """Avisos ya decididos cuyo envío falló antes. Se reintentan sin re-disparar nada.

    El aviso se reconstruye desde `detalle`, así que el texto del reintento es idéntico al del
    envío original. Las filas viejas, con un `detalle` que sólo tiene el nombre, renderizan en
    modo degradado en vez de explotar.
    """
    filas = (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.estado == alertas_engine.ESTADO_DISPARADA, AlertaPrecio.entregada == 0)
        .all()
    )
    salida = []
    for fila in filas:
        detalle = fila.detalle or {}
        if fila.precio_disparo is None:
            continue
        if alertas_engine.es_tipo_senal(fila.tipo):
            # Una señal no tiene nivel; lo que no puede faltar es la barra que la identifica.
            if not detalle.get("senal_fecha"):
                continue
        elif fila.nivel is None:
            continue
        salida.append(alertas_engine.Alerta(
            ticker=fila.ticker,
            nombre=alertas_engine.nombre_de_detalle(detalle, fila.ticker),
            tipo=fila.tipo, cartera=fila.cartera or "",
            nivel=float(fila.nivel) if fila.nivel is not None else None,
            precio=float(fila.precio_disparo), moneda=fila.moneda or "",
            contexto=alertas_engine.detalle_a_contexto(detalle),
        ))
    return salida


def _marcar_entregados(
    db: Session, alertas: list[alertas_engine.Alerta], ahora: datetime, historial: bool = True,
) -> None:
    """Saca los avisos de la cola de pendientes.

    `historial=False` es la siembra (`notificar=False`): nada se mandó, así que la fila no puede
    quedar fechada ni aparecer en el historial de avisos de la app.
    """
    for alerta in alertas:
        fila = _fila(db, alerta.clave)
        if fila is None:
            continue
        fila.entregada = 1
        fila.emitida_en = (fila.emitida_en or ahora) if historial else None
    db.commit()


def evaluar_y_notificar(db: Session, notificar: bool = True) -> dict:
    """Evalúa niveles y señales, persiste el estado y manda un mensaje con lo nuevo.

    `notificar=False` evalúa y persiste **sin mandar nada y sin dejar nada encolado**: es la forma
    de sembrar el estado inicial sin una andanada de avisos la primera vez. Antes dejaba las filas
    `entregada=0` y la corrida siguiente mandaba la andanada igual, así que la receta documentada
    no servía para nada.
    """
    universo = _universo(db)
    estados, avisadas = _estado_guardado(db)
    decision = alertas_engine.evaluar(universo.candidatas, estados)

    lados = avisos_config.lados_por_estrategia(db)
    senales = _senales_candidatas(db, universo, lados)
    alertas_senal = alertas_engine.evaluar_senales(senales, avisadas)

    tipos_habilitados = avisos_config.tipos_habilitados(db)
    silenciadas = [a for a in decision.a_emitir if a.tipo not in tipos_habilitados]

    _aplicar(db, decision, alertas_senal, tipos_habilitados, set(lados))
    db.commit()  # antes del envío: la red no corre con una transacción de escritura abierta

    # Los avisos nuevos ya quedaron persistidos con `entregada=0`, así que salen de esta consulta
    # junto con los que no se pudieron entregar en corridas anteriores.
    a_enviar = _pendientes_de_entrega(db)

    resumen = {
        "niveles_vigilados": len(universo.candidatas),
        "senales_vigiladas": len(senales),
        "nuevas": len(decision.a_emitir),
        "senales_nuevas": len(alertas_senal),
        "silenciadas": len(silenciadas),
        "rearmadas": len(decision.a_rearmar),
        "pendientes_de_entrega": len(a_enviar),
        "entregado": False,
        "motivo": None,
    }

    if not a_enviar:
        logger.info(
            "alertas: %d niveles y %d señales vigiladas, sin avisos nuevos "
            "(%d re-armadas, %d silenciadas)",
            len(universo.candidatas), len(senales), len(decision.a_rearmar), len(silenciadas),
        )
        return resumen

    if not notificar:
        # Se marcan entregados aunque no se mandó nada: el objetivo de esta rama es justamente
        # que la corrida siguiente no los mande.
        _marcar_entregados(db, a_enviar, datetime.utcnow(), historial=False)
        resumen["motivo"] = "notificación desactivada en la llamada (estado sembrado)"
        return resumen

    entregado, motivo = telegram.enviar(
        alertas_engine.texto_notificacion(a_enviar), parse_mode="HTML",
    )
    resumen["entregado"] = entregado
    resumen["motivo"] = motivo

    if entregado:
        _marcar_entregados(db, a_enviar, datetime.utcnow())
        logger.info("alertas: %d aviso(s) entregado(s)", len(a_enviar))
    else:
        logger.warning("alertas: %d aviso(s) sin entregar: %s", len(a_enviar), motivo)

    return resumen


# ─── Lecturas para la app ────────────────────────────────────────────────────

def listar(db: Session, limite: int = 50) -> list[dict]:
    """Historial de avisos, el más reciente primero.

    Sale de la misma fila que generó el mensaje de Telegram, para que la app y el celular no
    puedan contar cosas distintas.
    """
    filas = (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.emitida_en.isnot(None))
        .order_by(AlertaPrecio.emitida_en.desc())
        .limit(limite)
        .all()
    )
    salida = []
    for f in filas:
        detalle = f.detalle or {}
        contexto = alertas_engine.detalle_a_contexto(detalle)
        alerta = alertas_engine.Alerta(
            ticker=f.ticker, nombre=alertas_engine.nombre_de_detalle(detalle, f.ticker),
            tipo=f.tipo, cartera=f.cartera or "",
            nivel=float(f.nivel) if f.nivel is not None else None,
            precio=float(f.precio_disparo) if f.precio_disparo is not None else 0.0,
            moneda=f.moneda or "", contexto=contexto,
        )
        salida.append({
            "ticker": f.ticker,
            "nombre": alerta.nombre,
            "tipo": f.tipo,
            "etiqueta": alertas_engine.etiqueta_de(f.tipo, contexto),
            "accion": alertas_engine.accion_de(f.tipo, contexto),
            "encabezado": alertas_engine.encabezado_texto(alertas_engine.bloque_de(alerta)),
            "cartera": f.cartera or contexto.cartera_nombre,
            "origen": contexto.origen or None,
            "estado": f.estado,
            "nivel": alerta.nivel,
            "precio_disparo": float(f.precio_disparo) if f.precio_disparo is not None else None,
            "moneda": f.moneda or "",
            "distancia_pct": contexto.distancia_pct,
            "cantidad": contexto.cantidad,
            "precio_promedio": contexto.precio_promedio,
            "resultado_pct": contexto.resultado_pct,
            "en_cartera": contexto.en_cartera,
            "estrategia_id": contexto.estrategia_id,
            "estrategia_nombre": contexto.estrategia_nombre,
            "senal_tipo": contexto.senal_tipo,
            "senal_fecha": contexto.senal_fecha,
            "senal_motivo": contexto.senal_motivo,
            "variante": contexto.variante,
            "emitida_en": f.emitida_en,
            "entregada": bool(f.entregada),
        })
    return salida


def estado_configuracion(db: Session) -> dict:
    """Si los avisos están prendidos y configurados, y cuándo fue el último."""
    ultima = (
        db.query(AlertaPrecio)
        .filter(AlertaPrecio.emitida_en.isnot(None))
        .order_by(AlertaPrecio.emitida_en.desc())
        .first()
    )
    filas = db.query(AlertaPrecio).all()
    niveles = [f for f in filas if not alertas_engine.es_tipo_senal(f.tipo)]
    senales = [f for f in filas if alertas_engine.es_tipo_senal(f.tipo)]
    return {
        "habilitadas": telegram.alertas_habilitadas(),
        "configurado": telegram.configurado(),
        "canal": "telegram",
        "niveles_vigilados": len(niveles),
        "senales_vigiladas": len(senales),
        "estrategias_con_aviso": len(avisos_config.lados_por_estrategia(db)),
        "ultimo_aviso": ultima.emitida_en if ultima is not None else None,
        "sin_entregar": sum(
            1 for f in filas
            if f.estado == alertas_engine.ESTADO_DISPARADA and not f.entregada
        ),
    }
