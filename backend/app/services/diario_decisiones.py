"""Diario de decisiones del Centro de Decisiones: guardar, listar, revisar y avisar.

- **Guardar** vuelve a correr el análisis en el servidor y congela su salida completa (`DecisionSnapshot`
  inicial). El cliente sólo manda parámetros y lo que eligió el usuario: ningún número calculado viaja desde el
  navegador, así que lo guardado es exactamente lo que la app concluyó.
- Lo calculado es **inmutable**. El usuario sólo cambia `ejecutada`, `nota`, `revisar_el` y `estado`.
- **Revisar** recalcula el análisis de hoy, lo compara con la foto inicial (`revision_engine`) y guarda una fila
  nueva con su propia foto: nunca pisa la decisión ni las revisiones anteriores.
- **Avisar**: una vez por evento (revisión vencida, invalidación de precio cumplida) por Telegram, con el
  interruptor `avisar_revision_decision` de Ajustes → Avisos. Apagado, el evento se marca igual como avisado
  (como los niveles silenciados): prenderlo después no dispara una andanada de avisos viejos.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..database import Decision, DecisionAlternativa, DecisionRevision, DecisionSnapshot, MovimientoInversion
from . import aprendizaje_engine, avisos_config, benchmarks, centro_decisiones_analytics as cda
from . import decision_preferencias, diario_operaciones, ohlcv_analytics, revision_engine
from .valuacion_analytics import Universo

logger = logging.getLogger(__name__)

MODOS = ("oportunidad", "posicion")
ACCIONES_OPORTUNIDAD = ("entrar_ahora", "esperar_tecnica", "esperar_valoracion", "escalonada", "descartar", "profundizar",
                        "elegir_alternativa", "ninguna")
ACCIONES_POSICION = ("mantener", "aumentar", "reducir", "salir", "reasignar", "ninguna")
ACCIONES = tuple(dict.fromkeys(ACCIONES_OPORTUNIDAD + ACCIONES_POSICION))
ESCENARIO_DE_ACCION = {"entrar_ahora": "entrar_ahora", "esperar_tecnica": "esperar_tecnica",
                       "esperar_valoracion": "esperar_valoracion", "escalonada": "escalonada"}
REVISAR_DIAS_DEFAULT = {"corto": 30, "mediano": 90, "largo": 180}
MAX_NOTA = 2000
CAMPO_AVISO = "avisar_revision_decision"


class DecisionNoEncontrada(LookupError):
    pass


def _f(v) -> float | None:
    return float(v) if v is not None else None


# ---------------------------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------------------------

def _alternativas_de(db: Session, decision_id: int) -> list[dict]:
    return [{"ticker": a.ticker, "rol": a.rol, "orden": _f(a.orden), "precio_ref": _f(a.precio_ref), "moneda": a.moneda,
             "dimensiones": a.dimensiones, "motivo": a.motivo}
            for a in db.query(DecisionAlternativa).filter_by(decision_id=decision_id).order_by(DecisionAlternativa.id)]


def a_dict(db: Session, d: Decision, completo: bool = False) -> dict:
    salida = {
        "id": d.id, "creada_en": d.creada_en, "cartera": d.cartera, "modo": d.modo, "ticker": d.ticker,
        "ticker_base": d.ticker_base, "nombre": d.nombre, "preferencias": d.preferencias, "conclusion": d.conclusion,
        "accion_elegida": d.accion_elegida, "ejecutada": bool(d.ejecutada), "nota": d.nota, "argumentos": d.argumentos,
        "riesgos": d.riesgos, "supuestos": d.supuestos, "condiciones": d.condiciones, "versiones": d.versiones,
        "calidad": d.calidad, "orden": _f(d.orden), "precio_ref": _f(d.precio_ref), "moneda": d.moneda,
        "fecha_precio": d.fecha_precio, "fecha_dato": d.fecha_dato, "volatilidad_ref": _f(d.volatilidad_ref),
        "revisar_el": d.revisar_el, "estado": d.estado,
        "n_revisiones": db.query(DecisionRevision).filter_by(decision_id=d.id).count(),
        "alternativas": _alternativas_de(db, d.id),
    }
    if completo:
        snap = (db.query(DecisionSnapshot).filter_by(decision_id=d.id, tipo="inicial").order_by(DecisionSnapshot.id).first())
        salida["snapshot"] = snap.payload if snap else None
        salida["revisiones"] = [revision_dict(r) for r in
                                db.query(DecisionRevision).filter_by(decision_id=d.id).order_by(DecisionRevision.id)]
    return salida


def revision_dict(r: DecisionRevision) -> dict:
    return {"id": r.id, "decision_id": r.decision_id, "creada_en": r.creada_en, "comparacion": r.comparacion,
            "evaluacion_proceso": r.evaluacion_proceso, "nota": r.nota, "version": r.version}


def obtener(db: Session, decision_id: int) -> Decision:
    d = db.query(Decision).filter(Decision.id == decision_id).first()
    if d is None:
        raise DecisionNoEncontrada(decision_id)
    return d


def listar(db: Session, ticker: str | None = None, estado: str | None = None, limite: int = 100) -> list[dict]:
    q = db.query(Decision)
    if ticker:
        t = ticker.strip().upper()
        q = q.filter((Decision.ticker == t) | (Decision.ticker_base == t))
    if estado:
        q = q.filter(Decision.estado == estado)
    return [a_dict(db, d) for d in q.order_by(Decision.creada_en.desc(), Decision.id.desc()).limit(limite)]


def ultima_tesis(db: Session, ticker_base: str) -> dict | None:
    """La evaluación congelada de la última decisión sobre el emisor (para comparar la tesis con hoy)."""
    d = (db.query(Decision).filter(Decision.ticker_base == ticker_base)
         .order_by(Decision.creada_en.desc(), Decision.id.desc()).first())
    if d is None:
        return None
    snap = db.query(DecisionSnapshot).filter_by(decision_id=d.id, tipo="inicial").first()
    payload = (snap.payload if snap else None) or {}
    evaluacion = payload.get("evaluacion") or (payload.get("analisis") or {}).get("evaluacion")
    if not evaluacion:
        return None
    return {**evaluacion, "decision_id": d.id, "creada_en": d.creada_en, "accion_elegida": d.accion_elegida}


# ---------------------------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------------------------

def _condiciones(analisis: dict, accion: str) -> dict:
    escenarios = {e["clave"]: e for e in ((analisis.get("escenarios") or {}).get("escenarios") or [])}
    esc_info = analisis.get("escenarios") or {}
    moneda, fuente = esc_info.get("moneda"), esc_info.get("fuente_precio")
    clave = ESCENARIO_DE_ACCION.get(accion, "entrar_ahora")
    esc = escenarios.get(clave) or escenarios.get("entrar_ahora")
    entrada, invalidacion = {}, []
    if esc and esc.get("disponible"):
        entrada = {"escenario": esc["clave"], "texto": esc.get("condicion"), "precio": esc.get("precio_entrada"),
                   "moneda": moneda, "fuente": fuente}
        if esc.get("invalidacion") is not None:
            invalidacion.append({"tipo": "precio_bajo", "valor": esc["invalidacion"], "moneda": moneda, "fuente": fuente,
                                 "texto": f"cierre por debajo de {esc['invalidacion']:.2f} {moneda or ''} ({esc.get('regla_invalidacion')})".strip()})
    invalidacion.append({"tipo": "dimension", "dimension": "fundamentales", "umbral": 35.0,
                         "texto": "Fundamentales por debajo de 35 (deterioro de calidad, crecimiento o solidez)"})
    invalidacion.append({"tipo": "dimension", "dimension": "valoracion", "umbral": 35.0,
                         "texto": "Valoración por debajo de 35 (pasa a estar entre las más caras de sus pares)"})
    return {"entrada": entrada, "salida": {}, "invalidacion": invalidacion}


def _analisis_para(db: Session, modo: str, ticker: str, cartera: str | None, prefs: dict, con: tuple,
                   monto_ref_usd: float | None) -> tuple[dict, dict]:
    """`(analisis_del_activo, payload_a_congelar)`."""
    if modo == "posicion":
        base = Universo(db).ctx.base(ticker)
        pos = cda.analizar_posicion(ticker, cartera, prefs, db, ultima_tesis(db, base), [])
        return pos["analisis"], pos
    a = cda.analizar(ticker, prefs, cartera, con, monto_ref_usd, db)
    return a, a


def crear(db: Session, modo: str, ticker: str, accion_elegida: str, cartera: str | None = None,
          preferencias: dict | None = None, con: tuple = (), monto_ref_usd: float | None = None, nota: str | None = None,
          ejecutada: bool = False, revisar_en_dias: int | None = None, alternativa_elegida: str | None = None,
          ahora: datetime | None = None) -> dict:
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de: {', '.join(MODOS)}")
    validas = ACCIONES_POSICION if modo == "posicion" else ACCIONES_OPORTUNIDAD
    if accion_elegida not in validas:
        raise ValueError(f"acción no válida para el modo {modo}: {accion_elegida}")
    if nota and len(nota) > MAX_NOTA:
        raise ValueError(f"la nota admite hasta {MAX_NOTA} caracteres")
    if revisar_en_dias is not None and not 1 <= revisar_en_dias <= 1100:
        raise ValueError("la revisión debe ser entre 1 y 1100 días")
    ahora = ahora or datetime.utcnow()
    prefs = decision_preferencias.combinar(db, preferencias)
    t = ticker.strip().upper()
    analisis, payload = _analisis_para(db, modo, t, cartera, prefs, con, monto_ref_usd)
    if analisis.get("estado") != "ok":
        raise ValueError(analisis.get("mensaje") or "no se puede analizar este instrumento")

    ev = analisis["evaluacion"]
    concl = analisis["conclusion"]
    esc = analisis.get("escenarios") or {}
    alternativas = (analisis.get("alternativas") or {}).get("items") or []
    elegida = (alternativa_elegida or "").strip().upper() or None
    if accion_elegida in ("elegir_alternativa", "reasignar") and not elegida:
        raise ValueError("indicá la alternativa elegida")
    if elegida and elegida not in {a["ticker"] for a in alternativas} | {analisis["ticker_base"]}:
        raise ValueError(f"{elegida} no está entre las alternativas analizadas")

    banderas_altas = [b for b in ev["banderas"] if b["severidad"] == "alta"]
    riesgos = [{"texto": b["texto"], "regla": b["regla"], "severidad": b["severidad"], "tipo": "observado"} for b in ev["banderas"]]
    riesgo_dim = next((d for d in ev["dimensiones"] if d["clave"] == "riesgo"), None)
    for f in (riesgo_dim or {}).get("factores", []):
        riesgos.append({"texto": f["texto"], "regla": f["regla"], "severidad": "media" if f["efecto"] < 0 else "info",
                        "tipo": "observado"})
    riesgos += [{"texto": t_, "regla": "", "severidad": "info", "tipo": "hipotesis"}
                for t_ in concl["respuestas"].get("invalidaria", [])]

    supuestos = [
        f"Preferencias: horizonte {prefs['horizonte']}, objetivo {prefs['objetivo']}, enfoque {prefs['enfoque']}, "
        f"moneda {prefs['moneda']}.",
        "Pesos de las dimensiones: " + ", ".join(f"{k} {v:.0f}" for k, v in ev["orden"]["pesos"].items()),
        "El valor razonable es relativo a los múltiplos de los pares, no un valor intrínseco.",
        (esc.get("regla_potencial") or ""),
    ]
    vol = (analisis.get("riesgo") or {}).get("volatilidad")
    revisar_el = (ahora.date() + timedelta(days=revisar_en_dias or REVISAR_DIAS_DEFAULT[prefs["horizonte"]]))
    fecha_dato = next((f["fecha"] for f in analisis.get("fuentes", []) if f["dato"].startswith("Fundamentales")), None)
    favorable = next((e.get("favorable_pct") for e in esc.get("escenarios", [])
                      if e["clave"] == ESCENARIO_DE_ACCION.get(accion_elegida, "entrar_ahora")), None)

    d = Decision(
        creada_en=ahora, cartera=cartera, modo=modo, ticker=t, ticker_base=analisis["ticker_base"],
        nombre=analisis.get("nombre"), preferencias=jsonable_encoder(prefs),
        conclusion=jsonable_encoder({**{k: concl[k] for k in ("tipo", "titulo", "ganador", "respuestas", "condiciones",
                                                            "evidencia_en_contra", "regla", "salvedad")},
                                     "favorable_pct": favorable}),
        accion_elegida=accion_elegida, ejecutada=1 if ejecutada else 0, nota=(nota or None),
        argumentos=jsonable_encoder({"a_favor": analisis.get("fortalezas", []),
                                     "en_contra": concl.get("evidencia_en_contra", [])}),
        riesgos=jsonable_encoder(riesgos), supuestos=[s for s in supuestos if s],
        condiciones=jsonable_encoder(_condiciones(analisis, accion_elegida)),
        versiones=jsonable_encoder(analisis.get("versiones") or {}),
        calidad=jsonable_encoder({
            "cobertura": ev["orden"]["cobertura"], "incompleto": ev["orden"]["incompleto"], "motivo": ev["orden"]["motivo"],
            "incertidumbre": concl["respuestas"].get("incertidumbre"),
            "firmeza": (analisis.get("comparador") or {}).get("firmeza"),
            "advertencias_fechas": (analisis.get("alternativas") or {}).get("advertencias_fechas", []),
            "secciones_no_disponibles": [k for k, v in (analisis.get("secciones") or {}).items() if v["estado"] != "ok"],
            "banderas_altas": len(banderas_altas),
            "concentracion_revisar": any(o.get("nivel") == "revisar" for o in (analisis.get("encaje") or {}).get("observaciones", [])),
        }),
        orden=ev["orden"]["puntaje"], precio_ref=esc.get("precio"), moneda=esc.get("moneda"),
        fecha_precio=_fecha(esc.get("fecha_precio")), fecha_dato=_fecha(fecha_dato), volatilidad_ref=vol,
        revisar_el=revisar_el, estado="abierta",
    )
    db.add(d)
    db.flush()
    principal = elegida or analisis["ticker_base"]
    obj_grupo = (analisis.get("alternativas") or {}).get("objetivo_en_grupo")
    filas = [(analisis["ticker_base"], ev["orden"]["puntaje"], esc.get("precio"), esc.get("moneda"), ev["dimensiones"])]
    if obj_grupo is None:
        pass
    for a in alternativas:
        filas.append((a["ticker"], a["evaluacion"]["orden"]["puntaje"], a.get("precio_ref"), a.get("moneda"),
                      a["evaluacion"]["dimensiones"]))
    for tk, orden, precio, moneda, dims in filas:
        db.add(DecisionAlternativa(
            decision_id=d.id, ticker=tk,
            rol="elegida" if tk == principal and accion_elegida not in ("descartar", "ninguna") else "evaluada",
            orden=orden, precio_ref=precio, moneda=moneda,
            dimensiones=jsonable_encoder([{"clave": x["clave"], "puntaje": x["puntaje"], "estado": x["estado"]} for x in dims]),
        ))
    db.add(DecisionSnapshot(decision_id=d.id, tipo="inicial", creada_en=ahora, payload=jsonable_encoder(payload)))
    db.commit()
    return a_dict(db, d, completo=True)


def _fecha(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def actualizar(db: Session, decision_id: int, ejecutada: bool | None = None, nota: str | None = None,
               revisar_el: date | None = None, estado: str | None = None) -> dict:
    """Sólo los campos del usuario. Lo calculado (conclusión, fotos, alternativas) no se toca."""
    d = obtener(db, decision_id)
    if nota is not None:
        if len(nota) > MAX_NOTA:
            raise ValueError(f"la nota admite hasta {MAX_NOTA} caracteres")
        d.nota = nota or None
    if ejecutada is not None:
        d.ejecutada = 1 if ejecutada else 0
    if revisar_el is not None:
        if revisar_el < d.creada_en.date():
            raise ValueError("la fecha de revisión no puede ser anterior a la decisión")
        d.revisar_el = revisar_el
        d.aviso_revision_en = None
    if estado is not None:
        if estado not in ("abierta", "cerrada"):
            raise ValueError("estado debe ser abierta o cerrada")
        d.estado = estado
    db.commit()
    return a_dict(db, d, completo=True)


def borrar(db: Session, decision_id: int) -> None:
    d = obtener(db, decision_id)
    for modelo in (DecisionRevision, DecisionSnapshot, DecisionAlternativa):
        db.query(modelo).filter_by(decision_id=d.id).delete()
    db.delete(d)
    db.commit()


# ---------------------------------------------------------------------------------------------
# Revisar
# ---------------------------------------------------------------------------------------------

def _cierre_en(barras, fecha: date | None):
    if not barras:
        return None
    if fecha is None:
        return barras[-1].cierre
    previas = [b for b in barras if b.fecha <= fecha]
    return previas[-1].cierre if previas else None


def precio_actual(db: Session, ticker: str, fuente: str | None, u: Universo | None = None) -> tuple[float | None, str | None]:
    """Precio de hoy en la **misma fuente** que se usó al decidir (serie diaria local/subyacente o snapshot)."""
    if fuente and fuente.startswith("serie:"):
        variante = fuente.split(":", 1)[1] or "local"
        serie = ohlcv_analytics.get_serie_barras(ticker, date.min, date.today(), db, max_barras=1, variante=variante)
        if serie["barras"]:
            return serie["barras"][-1].cierre, serie["moneda"]
    u = u or Universo(db)
    p, m, _ = cda._precio_snapshot(u.emisor(ticker))
    return p, m


def _volatilidad_desde(u: Universo, base: str, desde: date) -> float | None:
    from .decision_datos import volatilidad_anual
    return volatilidad_anual([c for f, c in u.serie_usd(base) if f >= desde])   # None con menos de ~6 meses


def _movimientos_posteriores(db: Session, d: Decision, u: Universo) -> list[dict]:
    salida = []
    for m in db.query(MovimientoInversion).filter(MovimientoInversion.fecha >= d.creada_en.date()):
        if m.ticker == d.ticker or u.ctx.base(m.ticker) == d.ticker_base:
            if d.cartera and m.cartera != d.cartera:
                continue
            salida.append({"fecha": m.fecha, "ticker": m.ticker, "tipo": m.tipo_movimiento, "cartera": m.cartera})
    return salida[:20]


def revisar(db: Session, decision_id: int, evaluacion_proceso: str | None = None, nota: str | None = None,
            ahora: datetime | None = None) -> dict:
    if evaluacion_proceso is not None and evaluacion_proceso not in ("bien", "regular", "mal"):
        raise ValueError("evaluacion_proceso debe ser bien, regular o mal")
    if nota and len(nota) > MAX_NOTA:
        raise ValueError(f"la nota admite hasta {MAX_NOTA} caracteres")
    ahora = ahora or datetime.utcnow()
    d = obtener(db, decision_id)
    inicial_snap = db.query(DecisionSnapshot).filter_by(decision_id=d.id, tipo="inicial").first()
    inicial = (inicial_snap.payload if inicial_snap else {}) or {}
    inicial_analisis = inicial.get("analisis") if d.modo == "posicion" else inicial
    alternativas = _alternativas_de(db, d.id)
    con = tuple(a["ticker"] for a in alternativas if a["ticker"] != d.ticker_base)[:cda.MAX_ALTERNATIVAS]
    prefs = decision_preferencias.normalizar(d.preferencias)
    actual = cda.analizar(d.ticker, prefs, d.cartera, con, None, db)

    u = Universo(db)
    fuente = ((d.condiciones or {}).get("entrada") or {}).get("fuente") or (inicial_analisis.get("escenarios") or {}).get("fuente_precio")
    p_hoy, m_hoy = precio_actual(db, d.ticker, fuente, u)
    bench = None
    if d.moneda:
        simbolo = benchmarks.por_defecto(d.moneda)
        barras = benchmarks.barras(db, simbolo)
        inicio, fin = _cierre_en(barras, d.fecha_precio or d.creada_en.date()), _cierre_en(barras, None)
        if inicio and fin:
            bench = {"simbolo": simbolo, "nombre": benchmarks.BENCHMARKS[simbolo]["nombre"], "inicio": inicio, "fin": fin}
    alt_hoy = {}
    for a in alternativas:
        alt_hoy[a["ticker"]] = cda._precio_snapshot(u.emisor(a["ticker"]))[0]
    decision_dict = {**a_dict(db, d), "creada_en": d.creada_en}
    comparacion = revision_engine.comparar(
        decision_dict, inicial_analisis or {}, actual, p_hoy, m_hoy, bench, alt_hoy,
        _volatilidad_desde(u, d.ticker_base or d.ticker, d.creada_en.date()), _movimientos_posteriores(db, d, u),
        ahora.date(),
    )
    if bench is None:
        comparacion["benchmark_nota"] = "El índice de referencia todavía no está en la base: no se compara contra el mercado."
    snap = DecisionSnapshot(decision_id=d.id, tipo="revision", creada_en=ahora, payload=jsonable_encoder(actual))
    db.add(snap)
    db.flush()
    r = DecisionRevision(decision_id=d.id, creada_en=ahora, snapshot_id=snap.id, comparacion=jsonable_encoder(comparacion),
                         evaluacion_proceso=evaluacion_proceso, nota=nota or None, version=revision_engine.VERSION_REGLAS)
    db.add(r)
    db.commit()
    return revision_dict(r)


def calificar_revision(db: Session, revision_id: int, evaluacion_proceso: str | None, nota: str | None) -> dict:
    """El usuario califica su propio proceso en una revisión ya hecha (no toca la comparación calculada)."""
    r = db.query(DecisionRevision).filter(DecisionRevision.id == revision_id).first()
    if r is None:
        raise DecisionNoEncontrada(revision_id)
    if evaluacion_proceso is not None and evaluacion_proceso not in ("bien", "regular", "mal"):
        raise ValueError("evaluacion_proceso debe ser bien, regular o mal")
    if nota is not None and len(nota) > MAX_NOTA:
        raise ValueError(f"la nota admite hasta {MAX_NOTA} caracteres")
    if evaluacion_proceso is not None:
        r.evaluacion_proceso = evaluacion_proceso
    if nota is not None:
        r.nota = nota or None
    db.commit()
    return revision_dict(r)


# ---------------------------------------------------------------------------------------------
# Pendientes, aprendizaje y avisos
# ---------------------------------------------------------------------------------------------

def _invalidacion_cumplida(db: Session, d: Decision, u: Universo) -> list[str]:
    conds = [c for c in (d.condiciones or {}).get("invalidacion", []) if c.get("tipo") in ("precio_bajo", "precio_sobre")]
    if not conds:
        return []
    salida = []
    for c in conds:
        p, m = precio_actual(db, d.ticker, c.get("fuente"), u)
        cumplidas = revision_engine.condiciones_cumplidas([c], p, m, None)
        if cumplidas and cumplidas[0]["cumplida"]:
            salida.append(c.get("texto") or "condición de precio")
    return salida


def pendientes(db: Session, hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    abiertas = db.query(Decision).filter(Decision.estado == "abierta").order_by(Decision.revisar_el).all()
    if not abiertas:
        return []
    u = Universo(db)
    salida = []
    for d in abiertas:
        motivos = []
        if d.revisar_el and d.revisar_el <= hoy:
            motivos.append(f"llegó la fecha de revisión ({d.revisar_el.isoformat()})")
        motivos += [f"invalidación cumplida: {t}" for t in _invalidacion_cumplida(db, d, u)]
        if motivos:
            salida.append({**a_dict(db, d), "motivos": motivos})
    return salida


def invalidacion_de_ticker(db: Session, ticker_base: str) -> list[str]:
    """Condiciones de precio cumplidas de las decisiones abiertas sobre un emisor."""
    u = Universo(db)
    salida = []
    for d in db.query(Decision).filter(Decision.ticker_base == ticker_base, Decision.estado == "abierta"):
        salida += _invalidacion_cumplida(db, d, u)
    return salida


def _ventas_cerca_de_minimos(diario: dict) -> tuple[int, int] | None:
    ventas = [o for o in diario.get("operaciones", []) if o.get("tipo") == "venta" and o.get("rango_52s_pct") is not None]
    if not ventas:
        return None
    return sum(1 for o in ventas if o["rango_52s_pct"] <= 30), len(ventas)


def aprendizaje(db: Session, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    decisiones = []
    for d in db.query(Decision).order_by(Decision.id):
        decisiones.append({
            "id": d.id, "accion_elegida": d.accion_elegida, "conclusion_tipo": (d.conclusion or {}).get("tipo"),
            "ejecutada": bool(d.ejecutada), "revisar_el": d.revisar_el, "condiciones": d.condiciones,
            "banderas_altas": (d.calidad or {}).get("banderas_altas", 0) > 0,
            "concentracion_revisar": bool((d.calidad or {}).get("concentracion_revisar")),
            "favorable_pct": (d.conclusion or {}).get("favorable_pct"),
        })
    revisiones = [{"decision_id": r.decision_id, "comparacion": r.comparacion} for r in db.query(DecisionRevision)]
    diario = None
    try:
        diario = diario_operaciones.get_diario(db)
        diario = {**diario, "ventas_tras_caida": _ventas_cerca_de_minimos(diario)}
    except Exception:   # el diario de operaciones es complementario: sin él igual hay aprendizaje de decisiones
        logger.exception("aprendizaje: no se pudo leer el diario de operaciones")
    return aprendizaje_engine.patrones(decisiones, revisiones, diario, hoy)


def avisar_revisiones(db: Session, notificar: bool = True, hoy: date | None = None) -> dict:
    """Manda por Telegram las revisiones vencidas y las invalidaciones de precio nuevas (una vez por evento)."""
    from .notificaciones import telegram

    hoy = hoy or date.today()
    habilitado = bool(getattr(avisos_config.obtener(db), CAMPO_AVISO, 1))
    abiertas = db.query(Decision).filter(Decision.estado == "abierta").all()
    if not abiertas:
        return {"eventos": 0, "entregado": False}
    u = Universo(db)
    eventos: list[tuple[Decision, str, str]] = []
    for d in abiertas:
        if d.revisar_el and d.revisar_el <= hoy and d.aviso_revision_en is None:
            eventos.append((d, "revision", f"llegó la fecha de revisión ({d.revisar_el.isoformat()})"))
        if d.aviso_invalidacion_en is None:
            for texto in _invalidacion_cumplida(db, d, u):
                eventos.append((d, "invalidacion", f"se cumplió la invalidación: {texto}"))
                break
    if not eventos:
        return {"eventos": 0, "entregado": False}
    ahora = datetime.utcnow()

    def _marcar():
        for d, tipo, _ in eventos:
            if tipo == "revision":
                d.aviso_revision_en = ahora
            else:
                d.aviso_invalidacion_en = ahora
        db.commit()

    if not habilitado or not notificar:
        _marcar()
        return {"eventos": len(eventos), "entregado": False, "motivo": "aviso silenciado"}
    lineas = ["<b>DECISIÓN PARA REVISAR</b>"]
    for d, _, texto in eventos:
        lineas.append(f"• {d.ticker} ({d.accion_elegida.replace('_', ' ')}, {d.creada_en.date().isoformat()}): {texto}")
    lineas.append("Abrí Centro de Decisiones → Historial para revisarla. Información de seguimiento, no una indicación de operar.")
    entregado, motivo = telegram.enviar("\n".join(lineas), parse_mode="HTML")
    if entregado:
        _marcar()
    else:
        logger.warning("avisos de decisiones sin entregar: %s", motivo)
    return {"eventos": len(eventos), "entregado": entregado, "motivo": motivo}
