"""Calendario de eventos: listado con filtros, detalle, alta/edición/baja manual, fusión de duplicados,
vínculos con instrumentos y bandeja de noticias. Adaptador DB.

Reglas que protegen lo que hace el usuario:
- Lo que el usuario edita en un evento importado queda en `campos_editados`: ningún proveedor lo pisa.
- Borrar un evento **manual** lo borra. Borrar uno importado (catálogo, proveedor, importación) lo deja
  `descartado`: si se borrara, la próxima sincronización lo volvería a crear.
- Un vínculo automático que el usuario descarta queda como lápida (`estado_revision="descartada"`): la
  asociación automática nunca lo revive. Un vínculo manual borrado se borra.
- Un evento fusionado en otro queda con `fusionado_en_id` y deja de listarse; sus noticias y vínculos pasan
  al destino.

Validación en un solo lugar (`validar`), con un código por regla y su mensaje en `MENSAJE_ERROR`.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...database import EventoInstrumento, EventoMercado, NoticiaMercado
from . import (
    CAMPOS_EDITABLES, CATEGORIAS, CONFIANZAS, ESTADOS, ESTADOS_NOTICIA, ESTADOS_REVISION, ORIGENES,
    PRECISIONES, TIPOS_RELACION, VERIFICACIONES,
)
from . import normalizacion_engine as ne

LIMITE_MAXIMO = 500
MAX_TEXTO_CORTO = 300
MAX_TEXTO_LARGO = 4000
MAX_INSTRUMENTOS = 60
TICKER_RE = re.compile(r"^\^?[A-Z0-9][A-Z0-9._-]{0,14}$")

MENSAJE_ERROR = {
    "titulo_vacio": "El evento necesita un título",
    "texto_largo": "Algún texto es demasiado largo",
    "categoria_invalida": "La categoría no es válida",
    "fecha_invalida": "La fecha del evento no es válida",
    "fin_antes_de_inicio": "La fecha de finalización no puede ser anterior a la del evento",
    "precision_invalida": "La precisión de la fecha no es válida",
    "estado_invalido": "El estado no es válido",
    "verificacion_invalida": "El estado de verificación no es válido",
    "importancia_invalida": "La importancia va de 1 (baja) a 3 (alta)",
    "url_invalida": "La URL de la fuente tiene que empezar con http:// o https://",
    "ticker_invalido": "Algún ticker no es válido",
    "relacion_invalida": "El tipo de relación con el instrumento no es válido",
    "relevancia_invalida": "La relevancia va de 0 a 1",
    "revision_invalida": "El estado de revisión del vínculo no es válido",
    "demasiados_instrumentos": f"Un evento admite hasta {MAX_INSTRUMENTOS} instrumentos",
    "zona_invalida": "La zona horaria no es válida",
    "fusion_consigo_mismo": "No se puede fusionar un evento consigo mismo",
    "fusion_invalida": "El evento destino ya fue fusionado o descartado",
}


class EventoNoEncontrado(LookupError):
    pass


# ── Validación ──────────────────────────────────────────────────────────────────────────────────

def normalizar_ticker(t) -> str | None:
    s = (t or "").strip().upper()
    return s if TICKER_RE.match(s) else None


def _zona_valida(zona: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(zona)
        return True
    except Exception:
        return False


def validar(datos: dict, parcial: bool = False) -> str | None:
    """Código de `MENSAJE_ERROR`, o `None`. Con `parcial`, sólo se validan los campos presentes."""
    def hay(campo: str) -> bool:
        return campo in datos if parcial else True

    if hay("titulo") and not (datos.get("titulo") or "").strip():
        return "titulo_vacio"
    for campo in ("titulo", "subcategoria", "pais", "region", "fuente_principal"):
        if len(datos.get(campo) or "") > MAX_TEXTO_CORTO:
            return "texto_largo"
    for campo in ("descripcion", "resumen", "notas"):
        if len(datos.get(campo) or "") > MAX_TEXTO_LARGO:
            return "texto_largo"
    if hay("categoria") and datos.get("categoria") not in CATEGORIAS:
        return "categoria_invalida"
    if hay("fecha_evento") and not isinstance(datos.get("fecha_evento"), date):
        return "fecha_invalida"
    fin, ini = datos.get("fecha_fin"), datos.get("fecha_evento")
    if fin is not None and isinstance(ini, date) and fin < ini:
        return "fin_antes_de_inicio"
    if "precision_fecha" in datos and datos["precision_fecha"] not in PRECISIONES:
        return "precision_invalida"
    if "estado" in datos and datos["estado"] not in ESTADOS:
        return "estado_invalido"
    if "verificacion" in datos and datos["verificacion"] not in VERIFICACIONES:
        return "verificacion_invalida"
    if "importancia" in datos and datos["importancia"] not in (1, 2, 3):
        return "importancia_invalida"
    if datos.get("url_fuente") and not ne.url_valida(datos["url_fuente"]):
        return "url_invalida"
    if datos.get("zona_horaria") and not _zona_valida(datos["zona_horaria"]):
        return "zona_invalida"
    instrumentos = datos.get("instrumentos")
    if instrumentos is not None:
        if len(instrumentos) > MAX_INSTRUMENTOS:
            return "demasiados_instrumentos"
        for v in instrumentos:
            error = validar_vinculo(v)
            if error:
                return error
    return None


def validar_vinculo(v: dict) -> str | None:
    if normalizar_ticker(v.get("ticker")) is None:
        return "ticker_invalido"
    if v.get("tipo_relacion", "directa") not in TIPOS_RELACION:
        return "relacion_invalida"
    rel = v.get("relevancia", 1)
    if rel is None or not 0 <= float(rel) <= 1:
        return "relevancia_invalida"
    if v.get("estado_revision", "confirmada") not in ESTADOS_REVISION:
        return "revision_invalida"
    if len(v.get("justificacion") or "") > MAX_TEXTO_CORTO:
        return "texto_largo"
    return None


# ── Serialización ───────────────────────────────────────────────────────────────────────────────

def _hora(h: time | None) -> str | None:
    return h.strftime("%H:%M") if h else None


def vinculo_a_dict(v: EventoInstrumento) -> dict:
    return {
        "ticker": v.ticker, "tipo_relacion": v.tipo_relacion, "justificacion": v.justificacion,
        "metodo": v.metodo, "relevancia": float(v.relevancia) if v.relevancia is not None else None,
        "estado_revision": v.estado_revision,
    }


def noticia_a_dict(n: NoticiaMercado) -> dict:
    return {
        "id": n.id, "proveedor": n.proveedor, "medio": n.medio, "url": n.url, "titulo": n.titulo,
        "fragmento": n.fragmento, "idioma": n.idioma, "fecha_publicacion": n.fecha_publicacion,
        "fecha_captura": n.fecha_captura, "entidades": n.entidades or [],
        "categoria_sugerida": n.categoria_sugerida,
        "puntaje_relevancia": float(n.puntaje_relevancia) if n.puntaje_relevancia is not None else None,
        "evento_id": n.evento_id, "estado": n.estado,
    }


def a_dict(e: EventoMercado, vinculos: list[EventoInstrumento], n_noticias: int, hoy: date) -> dict:
    return {
        "id": e.id, "titulo": e.titulo, "descripcion": e.descripcion, "resumen": e.resumen, "notas": e.notas,
        "categoria": e.categoria, "subcategoria": e.subcategoria,
        "fecha_evento": e.fecha_evento, "fecha_fin": e.fecha_fin, "hora_evento": _hora(e.hora_evento),
        "zona_horaria": e.zona_horaria, "fecha_publicacion": e.fecha_publicacion,
        "precision_fecha": e.precision_fecha, "programado": bool(e.programado),
        "pais": e.pais, "region": e.region, "entidades": e.entidades or {},
        "importancia": e.importancia, "confianza_datos": e.confianza_datos, "estado": e.estado,
        "verificacion": e.verificacion, "origen": e.origen, "proveedor": e.proveedor,
        "fuente_principal": e.fuente_principal, "url_fuente": e.url_fuente,
        "fijado": bool(e.fijado), "descartado": bool(e.descartado), "fusionado_en_id": e.fusionado_en_id,
        "campos_editados": e.campos_editados or [],
        "es_futuro": e.fecha_evento >= hoy if e.fecha_evento else False,
        "instrumentos": [vinculo_a_dict(v) for v in sorted(vinculos, key=lambda x: (-float(x.relevancia or 0), x.ticker))],
        "n_noticias": n_noticias,
        "fecha_creacion": e.fecha_creacion, "fecha_actualizacion": e.fecha_actualizacion,
    }


def _vinculos_por_evento(db: Session, ids: list[int]) -> dict[int, list[EventoInstrumento]]:
    out: dict[int, list[EventoInstrumento]] = {}
    if not ids:
        return out
    for v in db.query(EventoInstrumento).filter(EventoInstrumento.evento_id.in_(ids)):
        out.setdefault(v.evento_id, []).append(v)
    return out


def _noticias_por_evento(db: Session, ids: list[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    if not ids:
        return out
    for (eid,) in db.query(NoticiaMercado.evento_id).filter(NoticiaMercado.evento_id.in_(ids)):
        out[eid] = out.get(eid, 0) + 1
    return out


# ── Listado ─────────────────────────────────────────────────────────────────────────────────────

def _texto_busqueda(e: EventoMercado, vinculos: list[EventoInstrumento]) -> str:
    ent = e.entidades or {}
    partes = [e.titulo, e.descripcion, e.resumen, e.subcategoria, e.pais, e.region, e.fuente_principal]
    for clave in ("empresas", "organismos", "sectores", "terminos"):
        partes.extend(str(x) for x in ent.get(clave) or [])
    partes.extend(v.ticker for v in vinculos)
    return " ".join(p for p in partes if p)


def _sectores(e: EventoMercado) -> set[str]:
    return {str(s).lower() for s in (e.entidades or {}).get("sectores") or []}


def listar(
    db: Session, *, desde: date | None = None, hasta: date | None = None,
    categorias: list[str] | None = None, paises: list[str] | None = None, tickers: list[str] | None = None,
    sectores: list[str] | None = None, tickers_cartera: set[str] | None = None,
    importancia_min: int | None = None, verificaciones: list[str] | None = None,
    origenes: list[str] | None = None, proveedores: list[str] | None = None, temporalidad: str = "todos",
    q: str | None = None, incluir_descartados: bool = False, orden: str = "desc",
    page: int = 1, limite: int = 100, hoy: date | None = None,
) -> dict:
    """Eventos que cumplen **todos** los filtros, paginados. `tickers_cartera` no vacío = sólo los
    vinculados (sin descartar) a algún instrumento de la cartera. Los campos simples filtran en SQL; los
    que viven en JSON (sectores) y la búsqueda de texto, en Python sobre lo ya acotado."""
    hoy = hoy or date.today()
    limite = max(1, min(limite, LIMITE_MAXIMO))
    page = max(1, page)
    query = db.query(EventoMercado).filter(EventoMercado.fusionado_en_id.is_(None))
    if not incluir_descartados:
        query = query.filter(EventoMercado.descartado == 0)
    if desde:
        query = query.filter(or_(EventoMercado.fecha_evento >= desde, EventoMercado.fecha_fin >= desde))
    if hasta:
        query = query.filter(EventoMercado.fecha_evento <= hasta)
    if temporalidad == "pasados":
        query = query.filter(EventoMercado.fecha_evento < hoy)
    elif temporalidad == "futuros":
        query = query.filter(EventoMercado.fecha_evento >= hoy)
    if categorias:
        query = query.filter(EventoMercado.categoria.in_(categorias))
    if paises:
        query = query.filter(or_(EventoMercado.pais.in_(paises), EventoMercado.region.in_(paises)))
    if importancia_min:
        query = query.filter(EventoMercado.importancia >= importancia_min)
    if verificaciones:
        query = query.filter(EventoMercado.verificacion.in_(verificaciones))
    if origenes:
        query = query.filter(EventoMercado.origen.in_(origenes))
    if proveedores:
        query = query.filter(EventoMercado.proveedor.in_(proveedores))
    filtro_tickers = {t.upper() for t in tickers or []}
    if tickers_cartera is not None:
        filtro_tickers = (filtro_tickers & tickers_cartera) if filtro_tickers else set(tickers_cartera)
        if not filtro_tickers:
            return {"total": 0, "page": page, "limite": limite, "eventos": []}
    if filtro_tickers:
        ids_con = db.query(EventoInstrumento.evento_id).filter(
            EventoInstrumento.ticker.in_(filtro_tickers), EventoInstrumento.estado_revision != "descartada",
        )
        query = query.filter(EventoMercado.id.in_(ids_con))

    if orden == "asc":
        query = query.order_by(EventoMercado.fecha_evento.asc(), EventoMercado.id.asc())
    else:
        query = query.order_by(EventoMercado.fijado.desc(), EventoMercado.fecha_evento.desc(), EventoMercado.id.desc())
    filas = query.all()

    vinculos = _vinculos_por_evento(db, [e.id for e in filas])
    if sectores:
        buscados = {s.lower() for s in sectores}
        filas = [e for e in filas if _sectores(e) & buscados]
    if q and q.strip():
        terminos = [t for t in ne.sin_acentos(q.lower()).split() if t]
        filas = [
            e for e in filas
            if all(t in ne.sin_acentos(_texto_busqueda(e, vinculos.get(e.id, [])).lower()) for t in terminos)
        ]

    total = len(filas)
    pagina = filas[(page - 1) * limite: page * limite]
    noticias = _noticias_por_evento(db, [e.id for e in pagina])
    return {
        "total": total, "page": page, "limite": limite,
        "eventos": [a_dict(e, vinculos.get(e.id, []), noticias.get(e.id, 0), hoy) for e in pagina],
    }


def obtener(db: Session, evento_id: int) -> EventoMercado:
    e = db.get(EventoMercado, evento_id)
    if e is None:
        raise EventoNoEncontrado(evento_id)
    return e


def detalle(db: Session, evento_id: int, hoy: date | None = None) -> dict:
    e = obtener(db, evento_id)
    vinculos = db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id).all()
    noticias = (
        db.query(NoticiaMercado).filter(NoticiaMercado.evento_id == e.id)
        .order_by(NoticiaMercado.fecha_publicacion.desc()).all()
    )
    out = a_dict(e, vinculos, len(noticias), hoy or date.today())
    out["noticias"] = [noticia_a_dict(n) for n in noticias]
    out["reglas_aplicadas"] = e.reglas_aplicadas or []
    return out


# ── Alta / edición / baja ───────────────────────────────────────────────────────────────────────

def _confianza_manual(datos: dict) -> str:
    if datos.get("verificacion") in ("fuente_oficial", "verificado_usuario", "multiples_fuentes"):
        return "alta" if datos.get("precision_fecha", "exacta") == "exacta" else "media"
    if datos.get("verificacion") == "rumor" or datos.get("precision_fecha") in ("anio", "desconocida"):
        return "baja"
    return "media"


def _aplicar(e: EventoMercado, datos: dict) -> list[str]:
    """Copia los campos editables presentes en `datos`. Devuelve los que cambiaron."""
    cambiados = []
    for campo in CAMPOS_EDITABLES:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo in ("titulo", "descripcion", "resumen", "notas", "subcategoria", "pais", "region", "fuente_principal"):
            valor = (valor or "").strip() or None
        if campo == "programado":
            valor = 1 if valor else 0
        if getattr(e, campo) != valor:
            setattr(e, campo, valor)
            cambiados.append(campo)
    return cambiados


def _guardar_vinculos_manuales(db: Session, e: EventoMercado, instrumentos: list[dict]) -> None:
    """Reemplaza los vínculos del evento por los del formulario. Los automáticos que el usuario sacó del
    formulario quedan como lápida (no se borran) para que la asociación automática no los recree."""
    nuevos = {normalizar_ticker(v["ticker"]): v for v in instrumentos}
    actuales = {v.ticker: v for v in db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id)}
    for ticker, v in actuales.items():
        if ticker in nuevos:
            continue
        if v.metodo == "automatico":
            v.estado_revision = "descartada"
        else:
            db.delete(v)
    for ticker, datos in nuevos.items():
        _upsert_vinculo(db, e, ticker, datos, actuales.get(ticker))


def _upsert_vinculo(db: Session, e: EventoMercado, ticker: str, datos: dict, fila: EventoInstrumento | None) -> EventoInstrumento:
    if fila is None:
        fila = EventoInstrumento(evento_id=e.id, ticker=ticker, fecha_creacion=datetime.utcnow())
        db.add(fila)
    fila.tipo_relacion = datos.get("tipo_relacion") or fila.tipo_relacion or "directa"
    if "justificacion" in datos:
        fila.justificacion = (datos.get("justificacion") or "").strip() or None
    if datos.get("relevancia") is not None:
        fila.relevancia = float(datos["relevancia"])
    elif fila.relevancia is None:
        fila.relevancia = 1
    fila.estado_revision = datos.get("estado_revision") or "confirmada"
    fila.metodo = "manual"   # cualquier toque del usuario lo vuelve manual: manda sobre el automático
    return fila


def crear(db: Session, datos: dict) -> tuple[EventoMercado | None, str | None]:
    """Alta manual. `(evento, None)` o `(None, codigo)`. Commitea."""
    error = validar(datos)
    if error:
        return None, error
    ahora = datetime.utcnow()
    e = EventoMercado(
        origen="manual", proveedor=None, precision_fecha="exacta", estado="confirmado",
        verificacion="sin_verificar", importancia=2, fecha_creacion=ahora, fecha_actualizacion=ahora,
    )
    _aplicar(e, datos)
    if "estado" not in datos:
        e.estado = "previsto" if e.fecha_evento >= date.today() else "concluido"
    e.confianza_datos = _confianza_manual({
        "verificacion": e.verificacion, "precision_fecha": e.precision_fecha,
    })
    e.clave_dedup = ne.clave_dedup(e.categoria, e.fecha_evento, e.titulo)
    db.add(e)
    db.flush()
    if datos.get("instrumentos"):
        _guardar_vinculos_manuales(db, e, datos["instrumentos"])
    db.commit()
    db.refresh(e)
    return e, None


def editar(db: Session, e: EventoMercado, datos: dict) -> str | None:
    """Edición parcial (sólo los campos presentes). En un evento importado, los campos tocados quedan en
    `campos_editados`. `fijado`/`descartado` son marcas del usuario. Commitea."""
    combinado = {"fecha_evento": e.fecha_evento, **datos}
    error = validar(combinado, parcial=True)
    if error:
        return error
    cambiados = _aplicar(e, datos)
    for marca in ("fijado", "descartado"):
        if marca in datos and datos[marca] is not None:
            nuevo = 1 if datos[marca] else 0
            if getattr(e, marca) != nuevo:
                setattr(e, marca, nuevo)
                cambiados.append(marca)
    if "instrumentos" in datos and datos["instrumentos"] is not None:
        _guardar_vinculos_manuales(db, e, datos["instrumentos"])
    if cambiados:
        if e.origen != "manual":
            e.campos_editados = sorted(set(e.campos_editados or []) | set(cambiados))
        if {"verificacion", "precision_fecha"} & set(cambiados):
            e.confianza_datos = _confianza_manual({"verificacion": e.verificacion, "precision_fecha": e.precision_fecha})
        if {"titulo", "categoria", "fecha_evento"} & set(cambiados):
            e.clave_dedup = ne.clave_dedup(e.categoria, e.fecha_evento, e.titulo)
    e.fecha_actualizacion = datetime.utcnow()
    db.commit()
    db.refresh(e)
    return None


def _soltar_noticias(db: Session, e: EventoMercado) -> None:
    for n in db.query(NoticiaMercado).filter(NoticiaMercado.evento_id == e.id):
        n.evento_id = None
        n.estado = "por_revisar"


def borrar(db: Session, e: EventoMercado) -> str:
    """`"borrado"` (manual) o `"descartado"` (importado: queda como lápida). Commitea."""
    if e.origen == "manual":
        _soltar_noticias(db, e)
        db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id).delete()
        for absorbido in db.query(EventoMercado).filter(EventoMercado.fusionado_en_id == e.id):
            absorbido.fusionado_en_id = None
        db.delete(e)
        db.commit()
        return "borrado"
    e.descartado = 1
    e.campos_editados = sorted(set(e.campos_editados or []) | {"descartado"})
    e.fecha_actualizacion = datetime.utcnow()
    db.commit()
    return "descartado"


def fusionar(db: Session, origen: EventoMercado, destino: EventoMercado) -> str | None:
    """Absorbe `origen` en `destino`: noticias y vínculos pasan al destino (sin pisar los que el destino
    ya tiene) y `origen` queda marcado como fusionado. Commitea."""
    if origen.id == destino.id:
        return "fusion_consigo_mismo"
    if destino.fusionado_en_id is not None or destino.descartado:
        return "fusion_invalida"
    for n in db.query(NoticiaMercado).filter(NoticiaMercado.evento_id == origen.id):
        n.evento_id = destino.id
    del_destino = {v.ticker for v in db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == destino.id)}
    for v in db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == origen.id).all():
        if v.ticker in del_destino:
            db.delete(v)
        else:
            v.evento_id = destino.id
    for absorbido in db.query(EventoMercado).filter(EventoMercado.fusionado_en_id == origen.id):
        absorbido.fusionado_en_id = destino.id
    origen.fusionado_en_id = destino.id
    if destino.verificacion in ("sin_verificar", "catalogo_revisar") and (origen.url_fuente or origen.proveedor) and (
        origen.url_fuente != destino.url_fuente
    ):
        destino.verificacion = "multiples_fuentes"
        destino.confianza_datos = "alta" if destino.precision_fecha == "exacta" else "media"
    ahora = datetime.utcnow()
    origen.fecha_actualizacion = destino.fecha_actualizacion = ahora
    db.commit()
    return None


# ── Vínculos con instrumentos ───────────────────────────────────────────────────────────────────

def guardar_vinculo(db: Session, e: EventoMercado, ticker: str, datos: dict) -> tuple[EventoInstrumento | None, str | None]:
    """Alta o corrección de un vínculo (confirmar, descartar, cambiar relevancia o motivo). Siempre
    queda como `manual`: la corrección del usuario manda. Commitea."""
    t = normalizar_ticker(ticker)
    error = validar_vinculo({**datos, "ticker": t or ""})
    if error:
        return None, error
    fila = db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id, EventoInstrumento.ticker == t).first()
    if fila is None and db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id).count() >= MAX_INSTRUMENTOS:
        return None, "demasiados_instrumentos"
    fila = _upsert_vinculo(db, e, t, datos, fila)
    e.fecha_actualizacion = datetime.utcnow()
    db.commit()
    db.refresh(fila)
    return fila, None


def quitar_vinculo(db: Session, e: EventoMercado, ticker: str) -> bool:
    """Un vínculo automático queda como lápida; uno manual se borra. `False` si no existía. Commitea."""
    t = normalizar_ticker(ticker)
    fila = db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id, EventoInstrumento.ticker == t).first()
    if fila is None:
        return False
    if fila.metodo == "automatico":
        fila.estado_revision = "descartada"
        fila.metodo = "manual"
    else:
        db.delete(fila)
    db.commit()
    return True


# ── Bandeja de noticias ─────────────────────────────────────────────────────────────────────────

def listar_noticias(db: Session, estado: str = "por_revisar", page: int = 1, limite: int = 50) -> dict:
    if estado not in ESTADOS_NOTICIA:
        raise ValueError("estado de noticia inválido")
    limite = max(1, min(limite, 200))
    page = max(1, page)
    query = db.query(NoticiaMercado).filter(NoticiaMercado.estado == estado)
    total = query.count()
    filas = query.order_by(NoticiaMercado.fecha_publicacion.desc()).offset((page - 1) * limite).limit(limite).all()
    return {"total": total, "page": page, "limite": limite, "noticias": [noticia_a_dict(n) for n in filas]}


def obtener_noticia(db: Session, noticia_id: int) -> NoticiaMercado:
    n = db.get(NoticiaMercado, noticia_id)
    if n is None:
        raise EventoNoEncontrado(noticia_id)
    return n


def asociar_noticia(db: Session, n: NoticiaMercado, e: EventoMercado) -> None:
    n.evento_id = e.id
    n.estado = "asociada"
    if e.verificacion == "sin_verificar" and db.query(NoticiaMercado).filter(NoticiaMercado.evento_id == e.id).count() >= 2:
        e.verificacion = "multiples_fuentes"
    e.fecha_actualizacion = datetime.utcnow()
    db.commit()


def descartar_noticia(db: Session, n: NoticiaMercado) -> None:
    n.estado = "descartada"
    n.evento_id = None
    db.commit()


def crear_evento_desde_noticia(db: Session, n: NoticiaMercado, datos: dict) -> tuple[EventoMercado | None, str | None]:
    """Un evento manual armado a partir de una noticia: la fecha de publicación es la de conocimiento y
    la del evento por defecto; el usuario puede corregir cualquiera. Los tickers que el proveedor
    identificó en la noticia se proponen como vínculos (el usuario los confirma o descarta)."""
    base = {
        "titulo": n.titulo, "descripcion": n.fragmento, "categoria": n.categoria_sugerida or "otro",
        "fecha_evento": n.fecha_publicacion.date(), "fecha_publicacion": n.fecha_publicacion,
        "url_fuente": n.url, "fuente_principal": n.medio, "verificacion": "sin_verificar",
    }
    base.update({k: v for k, v in datos.items() if v is not None})
    e, error = crear(db, base)
    if error:
        return None, error
    asociar_noticia(db, n, e)
    return e, None


# ── Utilidades para otros módulos ───────────────────────────────────────────────────────────────

def opciones(db: Session) -> dict:
    """Los valores admitidos por cada campo y los que ya aparecen en la base, para los selectores y
    filtros del frontend. Los tickers suman el universo de la app (cartera ∪ watchlist) y los benchmarks."""
    from ...database import InstrumentoInversion, WatchlistItem
    from ..benchmarks import BENCHMARKS
    from . import ETIQUETA_CATEGORIA

    paises, sectores, proveedores = set(), set(), set()
    for pais, region, entidades, proveedor in db.query(
        EventoMercado.pais, EventoMercado.region, EventoMercado.entidades, EventoMercado.proveedor,
    ).filter(EventoMercado.fusionado_en_id.is_(None)):
        paises.update(x for x in (pais, region) if x)
        sectores.update(str(s) for s in (entidades or {}).get("sectores") or [] if s)
        if proveedor:
            proveedores.add(proveedor)
    tickers = {t for (t,) in db.query(EventoInstrumento.ticker).distinct()}
    tickers |= {t for (t,) in db.query(InstrumentoInversion.ticker)}
    tickers |= {t for (t,) in db.query(WatchlistItem.ticker)}
    tickers |= set(BENCHMARKS)
    return {
        "categorias": [{"valor": c, "etiqueta": ETIQUETA_CATEGORIA[c]} for c in CATEGORIAS],
        "precisiones": list(PRECISIONES), "estados": list(ESTADOS), "verificaciones": list(VERIFICACIONES),
        "origenes": list(ORIGENES), "confianzas": list(CONFIANZAS), "tipos_relacion": list(TIPOS_RELACION),
        "paises": sorted(paises), "sectores": sorted(sectores), "proveedores": sorted(proveedores),
        "tickers": sorted(tickers),
    }
