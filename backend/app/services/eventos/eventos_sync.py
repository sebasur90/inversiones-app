"""Sincronización del Calendario de eventos: proveedores → normalizar → deduplicar → clasificar → asociar →
guardar. Adaptador DB.

Garantías:
- **Idempotente**: una segunda corrida no duplica noticias (id del proveedor y URL normalizada) ni
  eventos (`origen` + `proveedor` + `id_externo`, y similitud con eventos cercanos de la misma categoría).
- **Lo del usuario manda**: los campos en `campos_editados` no se pisan; un evento descartado o fusionado
  no se recrea; los vínculos manuales y las lápidas no se tocan; los eventos manuales nunca se modifican.
- **Una fuente que falla no rompe nada**: su estado queda registrado (`EstadoFuenteEventos`) y lo que ya
  había en la base sigue igual.
- **La red va fuera del lock**: primero se consulta a los proveedores y después se escribe todo en un solo
  commit, tomando el lock del sync del Sheet con timeout (como `mapa_mercado_ingesta`).
- Nunca toca movimientos, instrumentos ni precios: la cartera sigue saliendo del Sheet.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from ...database import EstadoFuenteEventos, EventoInstrumento, EventoMercado, NoticiaMercado
from .. import sync_lock
from ..clasificacion_engine import pais_canonico, region_de_pais
from . import asociacion_engine as ae
from . import clasificacion_engine as ce
from . import normalizacion_engine as ne
from .proveedores import todos
from .proveedores.base import (
    ESTADO_CUPO_AGOTADO, ESTADO_DESACTIVADO, ESTADO_ERROR, ESTADO_NO_CONFIGURADO, ESTADO_OK, ESTADO_PARCIAL,
    ContextoProveedor, EventoCrudo, NoticiaCruda, ProveedorEventos, ResultadoProveedor, SimboloUniverso,
)

logger = logging.getLogger("eventos")

LOCK_ESCRITURA_TIMEOUT_SEG = 300
_lock_corrida = threading.Lock()

CATEGORIAS_EN_DESARROLLO = ("geopolitica", "crisis_financiera")


def en_curso() -> bool:
    return _lock_corrida.locked()


# ── Universo: qué emisores consultar y cómo traducir símbolos externos a tickers de la app ────────

@dataclass
class Universo:
    simbolos: list[SimboloUniverso] = field(default_factory=list)
    info: dict[str, dict] = field(default_factory=dict)              # ticker → {sector, pais}
    simbolo_a_tickers: dict[str, list[str]] = field(default_factory=dict)
    cartera: set[str] = field(default_factory=set)


def construir_universo(db: Session, hoy: date | None = None) -> Universo:
    """Cartera ∪ watchlist con su símbolo en Yahoo/EE.UU., su sector y su país. Los bonos, ONs y FCI no
    tienen símbolo externo y quedan fuera de las consultas (pero sí reciben vínculos por país)."""
    from ...database import EstadoMarketDataTicker
    from .. import clasificacion_analytics, ohlcv_analytics
    from ..benchmarks import BENCHMARKS
    from ..clasificacion_engine import TIPO_ACCION, TIPO_BASE_CEDEAR, tipo_base_de
    from ..watchlist_analytics import _tickers_en_cartera

    u = Universo()
    tecnicos = ohlcv_analytics.listar_tickers_tecnicos(db)
    if not tecnicos:
        u.simbolo_a_tickers = {s: [s] for s in BENCHMARKS}
        return u
    clasif = clasificacion_analytics.clasificaciones(db)
    ctx = clasificacion_analytics.Contexto(db)
    u.cartera = {t.upper() for t in _tickers_en_cartera(db, hoy or date.today())}
    subyacentes = {
        e.ticker: e.simbolo_subyacente for e in db.query(EstadoMarketDataTicker)
        if e.simbolo_subyacente and e.resolucion_estado == "ok"
    }
    por_simbolo: dict[str, SimboloUniverso] = {}
    for t in tecnicos:
        ticker = t["ticker"]
        c = clasif.get(ticker)
        u.info[ticker] = {"sector": c.sector if c else None, "pais": c.pais if c else None}
        base = ctx.base(ticker)
        tipo = tipo_base_de((c.tipo if c else None) or t.get("tipo_instrumento") or "")
        auto = ctx.auto.get(base)
        simbolo, local = None, False
        if subyacentes.get(ticker):
            simbolo = subyacentes[ticker].upper()          # CEDEAR o ADR de una acción local
        elif tipo == TIPO_BASE_CEDEAR or t.get("variante_referencia") == "subyacente":
            simbolo = (auto.simbolo_yahoo if auto and auto.simbolo_yahoo else base.replace(".", "-")).upper()
        elif tipo == TIPO_ACCION:
            simbolo = (auto.simbolo_yahoo if auto and auto.simbolo_yahoo else f"{base}.BA").upper()
            local = simbolo.endswith(".BA")
        if not simbolo:
            continue
        s = por_simbolo.setdefault(simbolo, SimboloUniverso(simbolo=simbolo, tickers=[], nombre=t.get("nombre"), es_accion_local=local))
        if ticker not in s.tickers:
            s.tickers.append(ticker)
        s.en_cartera = s.en_cartera or ticker.upper() in u.cartera
    u.simbolos = sorted(por_simbolo.values(), key=lambda s: s.simbolo)
    for s in u.simbolos:
        for clave in {s.simbolo, s.simbolo.replace(".BA", "")}:
            u.simbolo_a_tickers.setdefault(clave, [])
            for t in s.tickers:
                if t not in u.simbolo_a_tickers[clave]:
                    u.simbolo_a_tickers[clave].append(t)
    for b in BENCHMARKS:
        u.simbolo_a_tickers.setdefault(b, [b])
    return u


# ── Estado de las fuentes ─────────────────────────────────────────────────────────────────────

def _fila_estado(db: Session, nombre: str) -> EstadoFuenteEventos:
    fila = db.get(EstadoFuenteEventos, nombre)
    if fila is None:
        fila = EstadoFuenteEventos(proveedor=nombre, solicitudes_hoy=0, nuevos=0, rotacion=0)
        db.add(fila)
    return fila


def _registrar(fila: EstadoFuenteEventos, estado: str, mensaje: str, nuevos: int = 0) -> None:
    ahora = datetime.utcnow()
    fila.ultima_corrida = ahora
    fila.estado = estado
    fila.mensaje = (mensaje or "")[:900]
    fila.nuevos = nuevos
    if estado in (ESTADO_OK, ESTADO_PARCIAL):
        fila.ultimo_ok = ahora


def usadas_hoy(fila: EstadoFuenteEventos | None, hoy: date) -> int:
    return (fila.solicitudes_hoy or 0) if fila is not None and fila.fecha_cupo == hoy else 0


def estado_fuentes(db: Session, hoy: date | None = None) -> dict:
    """Lo que la pantalla muestra de cada proveedor. Sin secretos: sólo si está configurado y qué pasó."""
    hoy = hoy or date.today()
    filas = {f.proveedor: f for f in db.query(EstadoFuenteEventos)}
    fuentes = []
    for p in todos():
        fila = filas.get(p.nombre)
        conf, motivo_conf = p.configurado()
        hab, motivo_hab = p.habilitado()
        fuentes.append({
            "proveedor": p.nombre, "etiqueta": p.etiqueta, "capacidades": list(p.capacidades),
            "configurado": conf, "habilitado": hab, "motivo": motivo_conf or motivo_hab or None,
            "ayuda": p.ayuda, "solo_revision": p.solo_revision,
            "limite_diario": p.limite_diario(), "solicitudes_hoy": usadas_hoy(fila, hoy),
            "ultima_corrida": fila.ultima_corrida if fila else None, "ultimo_ok": fila.ultimo_ok if fila else None,
            "estado": fila.estado if fila else None, "mensaje": fila.mensaje if fila else None,
            "nuevos": fila.nuevos if fila else 0,
        })
    corridas = [f["ultima_corrida"] for f in fuentes if f["ultima_corrida"]]
    return {
        "fuentes": fuentes,
        "por_revisar": db.query(NoticiaMercado).filter(NoticiaMercado.estado == "por_revisar").count(),
        "en_curso": en_curso(),
        "ultima_sincronizacion": max(corridas) if corridas else None,
    }


# ── Corrida ───────────────────────────────────────────────────────────────────────────────────

def correr(db: Session, proveedores: list[ProveedorEventos] | None = None, hoy: date | None = None) -> dict:
    """Una sincronización completa. Hace commit. Nunca lanza por un proveedor."""
    if not _lock_corrida.acquire(blocking=False):
        return {"resultado": "en_curso"}
    try:
        return _correr(db, proveedores if proveedores is not None else todos(), hoy or date.today())
    finally:
        _lock_corrida.release()


def _correr(db: Session, proveedores: list[ProveedorEventos], hoy: date) -> dict:
    # -- 1. Lectura y plan (corto) --
    universo = construir_universo(db, hoy)
    resumen: dict[str, dict] = {}
    planes: list[tuple[ProveedorEventos, ContextoProveedor, int]] = []
    for p in proveedores:
        fila = _fila_estado(db, p.nombre)
        conf, motivo = p.configurado()
        if not conf:
            _registrar(fila, ESTADO_NO_CONFIGURADO, motivo)
            resumen[p.nombre] = {"estado": ESTADO_NO_CONFIGURADO}
            continue
        hab, motivo = p.habilitado()
        if not hab:
            _registrar(fila, ESTADO_DESACTIVADO, motivo)
            resumen[p.nombre] = {"estado": ESTADO_DESACTIVADO}
            continue
        usadas = usadas_hoy(fila, hoy)
        limite = p.limite_diario()
        disponibles = p.max_por_corrida() if limite is None else min(p.max_por_corrida(), limite - usadas)
        if disponibles <= 0:
            _registrar(fila, ESTADO_CUPO_AGOTADO, f"Se alcanzó el tope diario configurado ({limite} solicitudes)")
            resumen[p.nombre] = {"estado": ESTADO_CUPO_AGOTADO}
            continue
        planes.append((p, ContextoProveedor(
            hoy=hoy, simbolos=universo.simbolos, cursor=fila.cursor, rotacion=fila.rotacion or 0,
            solicitudes_disponibles=disponibles,
        ), usadas))
    db.commit()   # deja registrados los no configurados y suelta la transacción antes de la red

    # -- 2. Red (sin lock) --
    resultados: list[tuple[ProveedorEventos, ResultadoProveedor, int]] = []
    for p, ctx, usadas in planes:
        try:
            res = p.obtener(ctx)
        except Exception:
            logger.exception("eventos: el proveedor %s falló", p.nombre)
            res = ResultadoProveedor(estado=ESTADO_ERROR, mensaje="El proveedor falló de forma inesperada (ver logs)")
        resultados.append((p, res, usadas))

    # -- 3. Escritura (un solo commit, con el lock del sync) --
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("eventos: el sync no soltó el lock en %ds; se descarta la corrida", LOCK_ESCRITURA_TIMEOUT_SEG)
        return {"resultado": "lock_ocupado", "proveedores": resumen}
    try:
        for p, res, usadas in resultados:
            cuenta = {"eventos": incorporar_eventos(db, res.eventos, universo, hoy)} if res.eventos else {}
            if res.noticias:
                cuenta["noticias"] = incorporar_noticias(db, p, res.noticias, universo, hoy)
            nuevos = (cuenta.get("eventos", {}).get("nuevos", 0) + cuenta.get("noticias", {}).get("eventos_nuevos", 0)
                      + cuenta.get("noticias", {}).get("a_revision", 0))
            fila = _fila_estado(db, p.nombre)
            fila.solicitudes_hoy = usadas + res.solicitudes
            fila.fecha_cupo = hoy
            if res.cursor:
                fila.cursor = res.cursor
            if res.rotacion is not None:
                fila.rotacion = res.rotacion
            _registrar(fila, res.estado, res.mensaje, nuevos)
            resumen[p.nombre] = {"estado": res.estado, "solicitudes": res.solicitudes, **cuenta}
        resumen["reasociados"] = reasociar(db, universo)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("eventos: no se pudo guardar la corrida")
        raise
    finally:
        sync_lock.lock.release()
    logger.info("eventos: corrida %s", resumen)
    return {"resultado": "ok", "proveedores": resumen}


# ── Eventos estructurados (balances, calendarios, catálogo) ────────────────────────────────────

def _campos_crudo(c: EventoCrudo, importancia: int) -> dict:
    return {
        "titulo": c.titulo, "descripcion": c.descripcion, "categoria": c.categoria, "fecha_evento": c.fecha_evento,
        "fecha_fin": c.fecha_fin, "hora_evento": c.hora_evento, "zona_horaria": c.zona_horaria,
        "fecha_publicacion": c.fecha_publicacion, "precision_fecha": c.precision_fecha, "estado": c.estado,
        "programado": 1 if c.programado else 0, "pais": pais_canonico(c.pais) if c.pais else None,
        "region": c.region or (region_de_pais(pais_canonico(c.pais)) if c.pais else None),
        "verificacion": c.verificacion, "fuente_principal": c.fuente_principal, "url_fuente": c.url_fuente,
        "entidades": c.entidades or {}, "importancia": importancia,
    }


def _importancia_crudo(c: EventoCrudo, universo: Universo) -> int:
    if c.importancia is not None:
        return c.importancia
    base = ce.IMPORTANCIA_BASE.get(c.categoria, 1)
    if c.categoria == "resultados" and any(v["ticker"] in universo.cartera for v in c.tickers):
        base += 1   # el balance de una tenencia importa más que el de una empresa de la watchlist
    return min(3, base)


def _eventos_cercanos(db: Session, desde: date, hasta: date) -> list[dict]:
    filas = db.query(EventoMercado).filter(
        EventoMercado.fecha_evento >= desde - timedelta(days=ne.TOLERANCIA_DIAS_EVENTO),
        EventoMercado.fecha_evento <= hasta + timedelta(days=ne.TOLERANCIA_DIAS_EVENTO),
        EventoMercado.fusionado_en_id.is_(None),
    ).all()
    return [{"id": e.id, "categoria": e.categoria, "fecha": e.fecha_evento, "tokens": ne.tokens(e.titulo), "fila": e} for e in filas]


def incorporar_eventos(db: Session, crudos: list[EventoCrudo], universo: Universo, hoy: date) -> dict:
    """Upsert de eventos estructurados. No commitea. Devuelve los conteos."""
    cuenta = Counter()
    if not crudos:
        return dict(cuenta)
    cercanos = _eventos_cercanos(db, min(c.fecha_evento for c in crudos), max(c.fecha_evento for c in crudos))
    ahora = datetime.utcnow()
    for c in crudos:
        importancia = _importancia_crudo(c, universo)
        campos = _campos_crudo(c, importancia)
        fila = db.query(EventoMercado).filter(
            EventoMercado.origen == c.origen, EventoMercado.proveedor == c.proveedor,
            EventoMercado.id_externo == c.id_externo,
        ).first()
        if fila is not None:
            if fila.descartado or fila.fusionado_en_id is not None:
                cuenta["omitidos"] += 1
                continue
            editados = set(fila.campos_editados or [])
            fecha_anterior = fila.fecha_evento
            cambio = False
            for campo, valor in campos.items():
                if campo not in editados and getattr(fila, campo) != valor:
                    setattr(fila, campo, valor)
                    cambio = True
            if (fecha_anterior != fila.fecha_evento and fecha_anterior >= hoy and fila.fecha_evento >= hoy
                    and "estado" not in editados and c.estado == "previsto"):
                fila.estado = "reprogramado"
            if cambio:
                fila.confianza_datos = ce.confianza_datos(fila.verificacion, fila.precision_fecha, 1)
                fila.clave_dedup = ne.clave_dedup(fila.categoria, fila.fecha_evento, fila.titulo)
                fila.fecha_actualizacion = ahora
                cuenta["actualizados"] += 1
            else:
                cuenta["sin_cambios"] += 1
        else:
            dup = ne.evento_duplicado({"categoria": c.categoria, "fecha": c.fecha_evento, "tokens": ne.tokens(c.titulo)}, cercanos)
            if dup is not None:
                cuenta["duplicados"] += 1
                continue
            fila = EventoMercado(
                origen=c.origen, proveedor=c.proveedor, id_externo=c.id_externo,
                confianza_datos=ce.confianza_datos(c.verificacion, c.precision_fecha, 1),
                clave_dedup=ne.clave_dedup(c.categoria, c.fecha_evento, c.titulo), version_reglas=ce.VERSION_REGLAS,
                reglas_aplicadas=[f"importado de {c.proveedor} ({c.origen})"], fecha_creacion=ahora, fecha_actualizacion=ahora,
                **campos,
            )
            db.add(fila)
            db.flush()
            cercanos.append({"id": fila.id, "categoria": fila.categoria, "fecha": fila.fecha_evento,
                             "tokens": ne.tokens(fila.titulo), "fila": fila})
            cuenta["nuevos"] += 1
        _vincular(db, fila, c.tickers, universo, entidades=[], texto=ne.sin_acentos(f"{c.titulo} {c.descripcion or ''}").lower())
    return dict(cuenta)


def _vincular(db: Session, e: EventoMercado, declarados: list[dict], universo: Universo, entidades: list[dict], texto: str) -> None:
    """Vínculos automáticos: los que el proveedor declara con certeza (confirmados) y los que propone la
    asociación (propuestos). Lápidas y vínculos manuales no se tocan."""
    actuales = {v.ticker: v for v in db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id)}
    intocables = {t for t, v in actuales.items() if v.metodo == "manual" or v.estado_revision == "descartada"}
    ahora = datetime.utcnow()

    def poner(d: dict, estado: str) -> None:
        t = d["ticker"]
        if t in intocables:
            return
        fila = actuales.get(t)
        if fila is None:
            fila = EventoInstrumento(evento_id=e.id, ticker=t, metodo="automatico", estado_revision=estado, fecha_creacion=ahora)
            db.add(fila)
            actuales[t] = fila
        elif fila.estado_revision == "propuesta" and estado == "confirmada":
            fila.estado_revision = estado
        fila.tipo_relacion = d.get("tipo_relacion") or "otra"
        fila.relevancia = float(d.get("relevancia") if d.get("relevancia") is not None else 0.5)
        fila.justificacion = d.get("justificacion")

    for d in declarados:
        poner(d, "confirmada")
    declarados_t = {d["ticker"] for d in declarados}
    for d in ae.proponer(
        categoria=e.categoria, pais=e.pais, entidades=entidades, texto=texto,
        simbolo_a_tickers=universo.simbolo_a_tickers, universo=universo.info,
        lapidas=intocables, manuales=declarados_t,
    ):
        if d["ticker"] in actuales and actuales[d["ticker"]].estado_revision == "confirmada":
            continue
        poner(d, "propuesta")


def reasociar(db: Session, universo: Universo) -> int:
    """Vuelve a proponer vínculos de los eventos importados y del catálogo con el universo de hoy (un
    ticker agregado a la watchlist recibe los eventos de su país). No toca manuales ni lápidas. No commitea."""
    if not universo.info:
        return 0
    filas = db.query(EventoMercado).filter(
        EventoMercado.origen.in_(("catalogo", "importacion", "calendario_oficial")),
        EventoMercado.descartado == 0, EventoMercado.fusionado_en_id.is_(None),
    ).all()
    for e in filas:
        _vincular(db, e, [], universo, entidades=[], texto=ne.sin_acentos(f"{e.titulo} {e.descripcion or ''}").lower())
    return len(filas)


# ── Noticias ──────────────────────────────────────────────────────────────────────────────────

def _dominio(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _fusionar_entidades(noticias: list[NoticiaCruda]) -> list[dict]:
    por_simbolo: dict[str, dict] = {}
    for n in noticias:
        for ent in n.entidades:
            s = ent.get("simbolo")
            actual = por_simbolo.get(s)
            if actual is None or (ent.get("match_score") or 0) > (actual.get("match_score") or 0) or ent.get("en_titulo"):
                por_simbolo[s] = {**ent, "en_titulo": bool(ent.get("en_titulo") or (actual or {}).get("en_titulo"))}
    return list(por_simbolo.values())


def incorporar_noticias(db: Session, proveedor: ProveedorEventos, noticias: list[NoticiaCruda], universo: Universo, hoy: date) -> dict:
    """Guarda las noticias nuevas y decide, por grupo de duplicados, si se incorporan solas como evento, se
    suman a uno existente o van a la bandeja de revisión. No commitea."""
    cuenta = Counter()
    items = []
    urls_lote, ids_lote = set(), set()
    for n in noticias:
        url_n = ne.normalizar_url(n.url)
        if url_n is None:
            cuenta["invalidas"] += 1
            continue
        if url_n in urls_lote or (n.id_externo and n.id_externo in ids_lote):
            cuenta["repetidas"] += 1
            continue
        urls_lote.add(url_n)
        if n.id_externo:
            ids_lote.add(n.id_externo)
        items.append({"n": n, "proveedor": n.proveedor, "id_externo": n.id_externo, "url_normalizada": url_n,
                      "tokens": ne.tokens(n.titulo), "fecha": n.fecha_publicacion})
    if not items:
        return dict(cuenta)

    ya_url = {u for (u,) in db.query(NoticiaMercado.url_normalizada).filter(NoticiaMercado.url_normalizada.in_(urls_lote))}
    ya_id = {i for (i,) in db.query(NoticiaMercado.id_externo).filter(
        NoticiaMercado.proveedor == proveedor.nombre, NoticiaMercado.id_externo.in_(ids_lote))} if ids_lote else set()
    nuevos = [i for i in items if i["url_normalizada"] not in ya_url and not (i["id_externo"] and i["id_externo"] in ya_id)]
    cuenta["ya_guardadas"] += len(items) - len(nuevos)
    if not nuevos:
        return dict(cuenta)

    f_min = min(i["fecha"] for i in nuevos) - timedelta(hours=ne.VENTANA_HORAS)
    f_max = max(i["fecha"] for i in nuevos) + timedelta(hours=ne.VENTANA_HORAS)
    recientes = [
        {"proveedor": r.proveedor, "id_externo": r.id_externo, "url_normalizada": r.url_normalizada,
         "tokens": frozenset((r.huella_titulo or "").split()), "fecha": r.fecha_publicacion, "fila": r}
        for r in db.query(NoticiaMercado).filter(NoticiaMercado.fecha_publicacion >= f_min, NoticiaMercado.fecha_publicacion <= f_max)
    ]
    cercanos = _eventos_cercanos(db, f_min.date(), f_max.date())
    ahora = datetime.utcnow()

    for grupo in ne.agrupar_duplicados(nuevos):
        miembros = [nuevos[k] for k in grupo]
        rep = miembros[0]["n"]
        previa = next((r["fila"] for m in miembros for r in recientes if ne.son_duplicadas(m, r)), None)
        entidades = _fusionar_entidades([m["n"] for m in miembros])
        fuertes = [ent for ent in entidades if ce.mencion_fuerte(ent) and universo.simbolo_a_tickers.get(ent.get("simbolo"))]
        clas = ce.clasificar(rep.titulo, rep.fragmento, en_universo=bool(fuertes))
        evento: EventoMercado | None = None
        if previa is not None:
            evento = db.get(EventoMercado, previa.evento_id) if previa.evento_id else None
            motivo = "misma noticia que otra ya guardada"
        elif proveedor.solo_revision:
            motivo = "fuente de descubrimiento: siempre pasa por revisión"
        else:
            incorporar, motivo = ce.decidir_incorporacion(clas, menciona_universo=bool(fuertes))
            if incorporar:
                fecha = rep.fecha_publicacion.date()
                dup = ne.evento_duplicado({"categoria": clas["categoria"], "fecha": fecha, "tokens": ne.tokens(rep.titulo)}, cercanos)
                if dup is not None:
                    evento = dup["fila"]
                else:
                    evento = _crear_evento_de_noticias(db, proveedor, miembros, clas, motivo, fuertes, universo, ahora)
                    cercanos.append({"id": evento.id, "categoria": evento.categoria, "fecha": evento.fecha_evento,
                                     "tokens": ne.tokens(evento.titulo), "fila": evento})
                    cuenta["eventos_nuevos"] += 1
        if evento is not None and (evento.descartado or evento.fusionado_en_id is not None):
            evento = db.get(EventoMercado, evento.fusionado_en_id) if evento.fusionado_en_id else None
        for m in miembros:
            n = m["n"]
            puntaje = max((ent.get("match_score") or 0 for ent in n.entidades), default=None)
            db.add(NoticiaMercado(
                proveedor=n.proveedor, id_externo=n.id_externo, medio=n.medio, url=n.url, url_normalizada=m["url_normalizada"],
                titulo=n.titulo, fragmento=n.fragmento, idioma=n.idioma, fecha_publicacion=n.fecha_publicacion,
                fecha_captura=ahora, entidades=n.entidades, huella_titulo=" ".join(sorted(m["tokens"])),
                categoria_sugerida=clas["categoria"], puntaje_relevancia=puntaje,
                evento_id=evento.id if evento else None, estado="asociada" if evento else "por_revisar",
            ))
            cuenta["guardadas"] += 1
        if evento is None:
            cuenta["a_revision"] += 1
        else:
            cuenta["asociadas_a_evento"] += 1
            _reforzar(db, evento, miembros, fuertes, universo)
    db.flush()
    return dict(cuenta)


def _pais_de_entidades(fuertes: list[dict]) -> str | None:
    paises = Counter(pais_canonico(e.get("pais")) for e in fuertes if e.get("pais"))
    return paises.most_common(1)[0][0] if paises else None


def _crear_evento_de_noticias(db, proveedor, miembros, clas, motivo, fuertes, universo, ahora) -> EventoMercado:
    rep = miembros[0]["n"]
    dominios = {_dominio(m["n"].url) for m in miembros}
    verificacion = "multiples_fuentes" if len(dominios) >= 2 else "sin_verificar"
    pais = _pais_de_entidades(fuertes)
    e = EventoMercado(
        titulo=rep.titulo, descripcion=rep.fragmento, categoria=clas["categoria"],
        fecha_evento=rep.fecha_publicacion.date(), fecha_publicacion=rep.fecha_publicacion,
        # La fecha del acontecimiento se aproxima con la de publicación: puede haber ocurrido antes.
        precision_fecha="aproximada",
        estado="en_desarrollo" if clas["categoria"] in CATEGORIAS_EN_DESARROLLO else "concluido",
        pais=pais, region=region_de_pais(pais) if pais else None,
        entidades={"empresas": sorted({ent.get("nombre") or ent["simbolo"] for ent in fuertes})},
        importancia=clas["importancia"], confianza_datos=ce.confianza_datos(verificacion, "aproximada", len(dominios)),
        verificacion=verificacion, origen="proveedor", proveedor=proveedor.nombre,
        id_externo=(rep.id_externo or miembros[0]["url_normalizada"])[:200],
        fuente_principal=rep.medio, url_fuente=rep.url,
        clave_dedup=ne.clave_dedup(clas["categoria"], rep.fecha_publicacion.date(), rep.titulo),
        version_reglas=clas["version"], reglas_aplicadas=[*clas["reglas"], f"incorporado solo: {motivo}"],
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    )
    db.add(e)
    db.flush()
    return e


def _reforzar(db: Session, e: EventoMercado, miembros: list[dict], fuertes: list[dict], universo: Universo) -> None:
    """Una noticia más que respalda al evento: puede subir la verificación (si el usuario no la fijó) y
    sumar vínculos automáticos."""
    if e.origen != "manual" and "verificacion" not in set(e.campos_editados or []) and e.verificacion == "sin_verificar":
        dominios = {_dominio(n.url) for n in db.query(NoticiaMercado).filter(NoticiaMercado.evento_id == e.id)}
        dominios |= {_dominio(m["n"].url) for m in miembros}
        if e.url_fuente:
            dominios.add(_dominio(e.url_fuente))
        if len(dominios) >= 2:
            e.verificacion = "multiples_fuentes"
            e.confianza_datos = ce.confianza_datos(e.verificacion, e.precision_fecha, len(dominios))
    if e.origen != "manual":
        texto = ne.sin_acentos(" ".join(f"{m['n'].titulo} {m['n'].fragmento or ''}" for m in miembros)).lower()
        _vincular(db, e, [], universo, entidades=fuertes, texto=texto)
