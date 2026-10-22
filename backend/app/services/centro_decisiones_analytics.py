"""Orquestador del Centro de Decisiones: arma el análisis de un activo, la exploración por sector/país/temática y
el análisis de una posición existente, reutilizando los módulos que ya existen.

No calcula nada financiero propio: junta el diagnóstico de empresa (`valuacion_analytics`), el comparador de
alternativas (`comparador_analytics`), el valor razonable (`valor_razonable_analytics`), la lectura técnica
(`lectura_tecnica`), el riesgo de la serie semanal (`decision_datos`) y el simulador (`simulador_decision`), y se
los pasa a los motores puros (`evaluacion_engine`, `escenarios_entrada_engine`, `posicion_decision_engine`).

Arma el `Universo` de valuación **una sola vez por pedido**. Si una sección falla (una fuente que no responde,
un dato corrupto) esa sección queda `no_disponible` con su motivo y el resto del análisis sigue: nunca se
reemplaza lo que falta por un valor inventado.

Dos metodologías, dichas en la respuesta:
- El análisis del activo usa su diagnóstico contra sus pares automáticos, el valor razonable y la técnica.
- La **comparación con alternativas** vuelve a diagnosticar a cada miembro contra los demás miembros del grupo
  (`comparador_engine.rankear`), igual que el comparador: los percentiles de grupos distintos no se ordenan
  entre sí. Por eso el puntaje del activo en la tabla de alternativas puede diferir del de su análisis.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date

from sqlalchemy.orm import Session

from ..database import InstrumentoInversion, WatchlistItem
from . import catalogo_instrumentos, clasificacion_engine as ce
from . import comparador_analytics, comparador_engine, decision_datos, escenarios_entrada_engine as ee
from . import evaluacion_engine as ev
from . import indicadores_engine as ind
from . import interpretacion, lectura_tecnica, ohlcv_analytics, pares_engine, posicion_decision_engine as pde
from . import salud_engine, simulador_decision, tematicas as tm, valor_razonable_analytics, valuacion_engine as ve
from .cache import cache_por_sync
from .impacto_cartera_analytics import TickerDesconocido
from .inversiones_analytics import (
    _clasificados_valorizados, _tasa_comision_promedio, get_configuracion_cartera, get_pnl_realizado_no_realizado,
    get_rendimiento_por_ticker,
)
from .valuacion_analytics import Universo, _diagnostico, _estado_datos, _evaluar, _tickers_universo

logger = logging.getLogger(__name__)

VERSION_REGLAS = 1
FRACCION_MONTO_REF = 0.05
PERIODO_ATR = 14
BARRAS_ATR = 300
LIMITE_EXPLORAR = 60
MAX_ALTERNATIVAS = comparador_engine.MAX_ALTERNATIVAS


class NoEsPosicion(LookupError):
    """El ticker no tiene tenencia en la cartera pedida."""


def _seguro(nombre: str, secciones: dict, fn, *args, **kwargs):
    """Corre una sección; si falla queda `no_disponible` con el motivo y devuelve `None`."""
    try:
        res = fn(*args, **kwargs)
        secciones.setdefault(nombre, {"estado": "ok", "motivo": None})
        return res
    except (TickerDesconocido, ValueError) as exc:
        secciones[nombre] = {"estado": "no_disponible", "motivo": str(exc) or exc.__class__.__name__}
    except Exception as exc:     # una fuente rota no tumba el análisis
        logger.exception("centro de decisiones: falló la sección %s", nombre)
        secciones[nombre] = {"estado": "no_disponible", "motivo": f"error interno al calcular ({exc.__class__.__name__})"}
    return None


def _en_tecnico(db: Session, ticker: str) -> bool:
    return bool(db.query(InstrumentoInversion.ticker).filter(InstrumentoInversion.ticker == ticker).first()
                or db.query(WatchlistItem.ticker).filter(WatchlistItem.ticker == ticker).first())


def _tecnico(db: Session, ticker: str) -> dict | None:
    """Lectura técnica + ATR sobre la serie de referencia. `None` si el ticker no está en cartera ni watchlist."""
    if not _en_tecnico(db, ticker):
        return None
    variante = ohlcv_analytics.variante_efectiva(db, ticker, None)
    lectura = lectura_tecnica.leer_ticker(ticker, variante, db)
    serie = ohlcv_analytics.get_serie_barras(ticker, date.min, date.today(), db, max_barras=BARRAS_ATR, variante=variante)
    barras = serie["barras"]
    atr = ind.atr(barras, PERIODO_ATR)[-1] if len(barras) > PERIODO_ATR else None
    return {**lectura, "atr": atr, "periodo_atr": PERIODO_ATR}


def _moneda_instrumento(db: Session, ticker: str) -> str | None:
    inst = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    if inst is not None and inst.moneda:
        return inst.moneda
    return (catalogo_instrumentos.obtener(ticker) or {}).get("moneda")


def _sigue_dolar(e, moneda: str | None) -> bool:
    return e.clasif.tipo in (ce.TIPO_CEDEAR_ACCION, ce.TIPO_CEDEAR_ETF) or moneda == "USD"


def _encaje(db: Session, cartera: str | None, ticker: str, e, monto_ref_usd: float | None) -> dict:
    total = _clasificados_valorizados(cartera, db).total_usd()
    if total <= 0:
        return {"sin_cartera": True, "observaciones": []}
    monto = monto_ref_usd if monto_ref_usd else total * FRACCION_MONTO_REF
    sim = simulador_decision.simular_operaciones(cartera, db, [(ticker, monto)])
    ejes = {x["eje"]: x for x in sim["ejes"]}

    def _tiene(eje: str, etiqueta: str | None) -> bool:
        return bool(etiqueta) and any(f["etiqueta"] == etiqueta and f["antes_pct"] > 0 for f in ejes.get(eje, {}).get("items", []))

    return {
        "sin_cartera": False,
        "monto_ref_usd": monto,
        "monto_ref_texto": (f"{monto:,.0f} USD".replace(",", ".")
                            + (" (5 % de la cartera)" if not monto_ref_usd else "")),
        "observaciones": [o for o in sim["observaciones"] if o["nivel"] in ("revisar", "atencion")],
        "todas_observaciones": sim["observaciones"],
        "en_cartera": _tiene("Emisor", e.base),
        "sector_nuevo": bool(e.clasif.sector) and not _tiene("Sector", e.clasif.sector),
        "pais_nuevo": bool(e.clasif.pais) and not _tiene("País", e.clasif.pais),
        "peso_emisor": next(({"antes_pct": f["antes_pct"], "despues_pct": f["despues_pct"]}
                             for f in ejes.get("Emisor", {}).get("items", []) if f["etiqueta"] == e.base), None),
    }


def _precio_snapshot(e) -> tuple[float | None, str | None, date | None]:
    m = valor_razonable_analytics.datos_mercado(e.snapshot)
    return m.precio, m.moneda, (e.snapshot.fecha if e.snapshot else None)


def _insumos(u: Universo, db: Session, ticker: str, e, diag: dict | None, vr: dict | None, tecnico: dict | None,
             encaje: dict | None) -> ev.Insumos:
    ficha = u.ficha(e.base)
    moneda = _moneda_instrumento(db, ticker)
    fecha_precio = tecnico.get("fecha") if tecnico and tecnico.get("fecha") else _precio_snapshot(e)[2]
    return ev.Insumos(
        ticker=ticker, es_etf=e.es_etf, diagnostico=diag, valor_razonable=vr, tecnico=tecnico,
        riesgo=decision_datos.riesgo_de(u, e.base), encaje=encaje,
        metricas=dict(ficha.valores) if ficha else {}, extra=dict(ficha.extra) if ficha else {},
        sin_ganancias=bool(ficha and ficha.sin_ganancias), fecha_dato=ficha.fecha_dato if ficha else None,
        fecha_precio=fecha_precio, moneda_instrumento=moneda, sigue_dolar=_sigue_dolar(e, moneda),
    )


def _excluida(prefs: dict, base: str, e) -> str | None:
    ex = prefs.get("excluir") or {}
    if base in ex.get("tickers", []):
        return "ticker excluido en tus preferencias"
    if e.clasif.sector and e.clasif.sector in ex.get("sectores", []):
        return f"sector {e.clasif.sector} excluido en tus preferencias"
    if e.clasif.pais and e.clasif.pais in ex.get("paises", []):
        return f"país {e.clasif.pais} excluido en tus preferencias"
    if e.clasif.tipo and e.clasif.tipo in ex.get("tipos", []):
        return f"tipo {e.clasif.tipo} excluido en tus preferencias"
    return None


def _alternativas(u: Universo, db: Session, e, comp: dict, prefs: dict, cartera: str | None,
                  monto_ref_usd: float | None, hoy: date, secciones: dict) -> dict:
    """Evalúa al activo y a sus alternativas aptas con la misma metodología (diagnóstico dentro del grupo)."""
    if not comp or comp.get("estado") != "ok":
        return {"estado": (comp or {}).get("estado", "sin_datos"), "mensaje": (comp or {}).get("mensaje", ""),
                "items": [], "excluidas": [], "robustez": {}, "advertencias_fechas": [], "evaluaciones": {}}
    aptas, excluidas = [], []
    for a in comp["alternativas"]:
        if not a["en_ranking"]:
            continue
        motivo = _excluida(prefs, a["ticker_base"], u.emisor(a["ticker_base"]))
        if motivo:
            excluidas.append({"ticker": a["ticker_base"], "motivo": motivo})
        else:
            aptas.append(a)
    fichas = {e.base: u.ficha(e.base), **{a["ticker_base"]: u.ficha(a["ticker_base"]) for a in aptas}}
    fichas = {b: f for b, f in fichas.items() if f is not None}
    if len(fichas) < 3:
        return {"estado": "insuficiente", "mensaje": "Tras aplicar tus exclusiones quedan menos de 2 alternativas comparables.",
                "items": [], "excluidas": excluidas, "robustez": {}, "advertencias_fechas": [], "evaluaciones": {}}
    _, diags, _ = comparador_engine.rankear(e.base, fichas, hoy)

    evaluaciones: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for base in fichas:
        em = u.emisor(base)
        tec = _seguro(f"tecnico:{base}", secciones, _tecnico, db, base)
        enc = _seguro(f"encaje:{base}", secciones, _encaje, db, cartera, base, em, monto_ref_usd)
        ins = _insumos(u, db, base, em, asdict(diags[base]), None, tec, enc)
        evaluaciones[base] = ev.evaluar(ins, prefs, hoy)
        precio, moneda, fecha = _precio_snapshot(em)
        meta[base] = {"nombre": em.nombre, "precio_ref": precio, "moneda": moneda, "fecha_precio": fecha,
                      "fecha_dato": fichas[base].fecha_dato, "periodo_contable": fichas[base].periodo_contable,
                      "sector": em.clasif.sector, "industria": em.clasif.industria, "region": em.clasif.region,
                      "con_tecnico": tec is not None}
    secciones.pop(f"tecnico:{e.base}", None)

    robustez = {}
    confianzas = {b: (asdict(diags[b]).get("confianza")) for b in fichas}
    for enf in ev.ENFOQUES:
        pesos = ev.pesos_para({**prefs, "enfoque": enf, "pesos": None})
        puntajes = {b: ev.reordenar(evaluaciones[b], pesos, confianzas[b]) for b in fichas}
        validos = sorted(((p, b) for b, p in puntajes.items() if p is not None), reverse=True)
        robustez[enf] = validos[0][1] if len(validos) >= 2 else None

    obj_eval = evaluaciones[e.base]
    items = []
    comps_por_base = {a["ticker_base"]: a for a in aptas}
    for base, eva in evaluaciones.items():
        if base == e.base:
            continue
        diferencias = []
        for d in eva["dimensiones"]:
            po = ev.puntaje_de(obj_eval, d["clave"])
            if d["puntaje"] is None or po is None:
                continue
            delta = round(d["puntaje"] - po, 1)
            if abs(delta) >= 5:
                diferencias.append({"dimension": d["clave"], "nombre": d["nombre"], "delta": delta,
                                    "texto": f"{d['nombre']}: {'mejor' if delta > 0 else 'peor'} que {e.base} por "
                                             f"{abs(delta):.0f} puntos".replace(".", ",")})
        a = comps_por_base[base]
        items.append({
            "ticker": base, **{k: v for k, v in meta[base].items() if k not in ("periodo_contable",)},
            "comparabilidad": a["nivel"], "comparabilidad_resumen": a["resumen"], "origen": a["origen"],
            "evaluacion": eva, "diferencias": diferencias,
            "encaje_objetivo": next((d for d in eva["dimensiones"] if d["clave"] == ev.ENCAJE), None),
        })
    items.sort(key=lambda x: -(x["evaluacion"]["orden"]["puntaje"] if x["evaluacion"]["orden"]["puntaje"] is not None else -1))
    adv = decision_datos.compatibilidad_fechas(
        {"ticker": e.base, **meta[e.base]}, [{"ticker": b, **meta[b]} for b in meta if b != e.base])
    return {
        "estado": "ok", "mensaje": "", "items": items, "excluidas": excluidas, "robustez": robustez,
        "advertencias_fechas": adv, "evaluaciones": evaluaciones,
        "objetivo_en_grupo": {"ticker": e.base, **{k: v for k, v in meta[e.base].items() if k != "periodo_contable"},
                              "evaluacion": obj_eval},
        "metodo": ("cada miembro se diagnostica contra los demás miembros del grupo (como el comparador), con la "
                   "misma base de riesgo (serie semanal en USD) y el mismo monto de referencia para el encaje"),
    }


def _fuentes(e, ficha, tecnico: dict | None, mep_ok: bool, hoy: date) -> list[dict]:
    precio, _, fecha_snap = _precio_snapshot(e)
    out = [
        decision_datos.fuente("Fundamentales y múltiplos", "Yahoo (snapshot de la ingesta)", ficha.fecha_dato if ficha else None,
                              hoy, ev.DIAS_DATO_VIEJO),
        decision_datos.fuente("Último balance informado", "Yahoo (mostRecentQuarter)",
                              ficha.periodo_contable if ficha else None, hoy, 150),
        decision_datos.fuente("Serie semanal (riesgo, ~5 años)", "Yahoo (cierres semanales)", ficha.fecha_serie if ficha else None,
                              hoy, ev.DIAS_DATO_VIEJO),
    ]
    if tecnico:
        out.append(decision_datos.fuente(f"Serie diaria ({tecnico.get('variante')})", "serie de velas de la app",
                                         tecnico.get("fecha"), hoy, decision_datos.DIAS_PRECIO_VIEJO))
    else:
        out.append(decision_datos.fuente("Serie diaria (técnica)", "serie de velas de la app", None, hoy,
                                         nota="sólo para tickers de la cartera o la watchlist"))
    out.append(decision_datos.fuente("Precio del snapshot", "Yahoo", fecha_snap if precio else None, hoy, ev.DIAS_DATO_VIEJO))
    out.append({"dato": "Tipo de cambio MEP", "fuente": "planilla (Índices)", "fecha": None, "antiguedad_dias": None,
                "estado": "ok" if mep_ok else "falta", "nota": "" if mep_ok else "sin MEP: los montos en pesos quedan incompletos"})
    return out


def _escenarios(e, tecnico: dict | None, vr: dict | None, evaluacion: dict, prefs: dict, tasa: float | None) -> dict:
    if tecnico and tecnico.get("ultimo_cierre") is not None:
        precio, moneda, fecha, fuente = tecnico["ultimo_cierre"], tecnico.get("moneda"), tecnico.get("fecha"), f"serie:{tecnico.get('variante')}"
    else:
        precio, moneda, fecha = _precio_snapshot(e)
        fuente = "fundamentales"
    esc = {v["clave"]: v["valor"] for v in (vr or {}).get("escenarios", [])} if vr and vr.get("estado") == "ok" else {}
    ins = ee.Insumos(
        precio=precio, fecha_precio=fecha, moneda=moneda,
        atr=(tecnico or {}).get("atr"),
        soporte=((tecnico or {}).get("soporte") or {}).get("precio"),
        resistencia=((tecnico or {}).get("resistencia") or {}).get("precio"),
        rsi=((tecnico or {}).get("momentum") or {}).get("rsi"),
        valor_pesimista=esc.get("pesimista"), valor_base=esc.get("base"), valor_optimista=esc.get("optimista"),
        moneda_valor=(vr or {}).get("moneda"), tasa_comision_pct=tasa,
        banderas_criticas=[b["texto"] for b in evaluacion["banderas"] if b["severidad"] == ev.ALTA],
        datos_insuficientes=evaluacion["orden"]["incompleto"], horizonte=prefs.get("horizonte", "largo"),
    )
    salida = ee.construir(ins)
    salida["fuente_precio"] = fuente
    return salida


def _vr_resumen(vr: dict | None) -> dict | None:
    if not vr:
        return None
    claves = ("estado", "mensaje", "moneda", "precio", "escenarios", "lectura", "lectura_texto", "regla_lectura",
              "confianza", "convergen", "faltantes", "salvedad", "limites", "n_pares", "version_reglas", "analistas")
    return {k: vr.get(k) for k in claves}


def _comp_resumen(comp: dict | None) -> dict | None:
    if not comp:
        return None
    concl = comp.get("conclusion") or {}
    return {
        "estado": comp.get("estado"), "mensaje": comp.get("mensaje"), "version_reglas": comp.get("version_reglas"),
        "firmeza": concl.get("firmeza"), "titulo": concl.get("titulo"), "regla_aplicada": concl.get("regla_aplicada"),
        "rechazadas": [{"ticker": r["ticker_base"], "motivo": r.get("motivo")} for r in comp.get("rechazadas", [])][:10],
        "sugeridas": [s["ticker_base"] for s in comp.get("sugeridas", [])],
        "seleccion": comp.get("seleccion", []),
    }


def calcular_analisis(u: Universo, db: Session, ticker: str, prefs: dict, cartera: str | None, con: tuple,
                      monto_ref_usd: float | None, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    t = ticker.strip().upper()
    e = u.emisor(t)
    secciones: dict[str, dict] = {}
    base_salida = {
        "version_reglas": VERSION_REGLAS, "ticker": t, "ticker_base": e.base, "nombre": e.nombre,
        "fecha_analisis": hoy, "cartera": cartera, "preferencias": prefs, "es_etf": e.es_etf,
        "clasificacion": {"tipo": e.clasif.tipo, "tipo_base": e.clasif.tipo_base, "sector": e.clasif.sector,
                          "industria": e.clasif.industria, "pais": e.clasif.pais, "region": e.clasif.region},
        "estado_datos": _estado_datos(e), "en_cartera_o_watchlist": _en_tecnico(db, t),
    }
    if e.clasif.tipo_base in ce.TIPOS_BASE_SIN_AUTO:
        return {**base_salida, "estado": "no_aplica",
                "mensaje": "Bonos, ONs, letras y FCI no se analizan en el Centro de Decisiones: no hay fundamentales de empresa."}

    grupo, res = _evaluar(u, e)
    diag = asdict(_diagnostico(u, e, grupo, res))
    secciones["diagnostico"] = {"estado": "ok" if u.ficha(e.base) else "sin_datos",
                                "motivo": None if u.ficha(e.base) else "todavía no hay fundamentales de este emisor"}
    vr = _seguro("valor_razonable", secciones, valor_razonable_analytics.calcular, u, t, con)
    comp = _seguro("comparador", secciones, comparador_analytics.calcular, u, t, con)
    tecnico = _seguro("tecnico", secciones, _tecnico, db, t)
    if tecnico is None and secciones["tecnico"]["estado"] == "ok":
        secciones["tecnico"] = {"estado": "sin_datos", "motivo": "el ticker no está en la cartera ni en la watchlist"}
    encaje = _seguro("encaje", secciones, _encaje, db, cartera, t, e, monto_ref_usd)

    ins = _insumos(u, db, t, e, diag, vr, tecnico, encaje)
    evaluacion = ev.evaluar(ins, prefs, hoy)
    alternativas = _seguro("alternativas", secciones, _alternativas, u, db, e, comp, prefs, cartera, monto_ref_usd, hoy,
                           secciones) or {"estado": "no_disponible", "items": [], "excluidas": [], "robustez": {},
                                          "advertencias_fechas": [], "evaluaciones": {}}
    for k in [k for k in secciones if k.startswith(("tecnico:", "encaje:"))]:
        if secciones[k]["estado"] == "ok":
            secciones.pop(k)

    if alternativas.get("estado") == "ok":
        obj_grupo = alternativas["objetivo_en_grupo"]["evaluacion"]
        alts = [a["evaluacion"] for a in alternativas["items"]]
        conclusion = ev.concluir(obj_grupo, alts, alternativas["robustez"], (_comp_resumen(comp) or {}).get("firmeza"),
                                 alternativas["advertencias_fechas"])
    else:
        conclusion = ev.concluir(evaluacion, [], {}, None, [])
    tasa = _seguro("comisiones", secciones, _tasa_comision_promedio, cartera, db)
    escenarios = _seguro("escenarios", secciones, _escenarios, e, tecnico, vr, evaluacion, prefs, tasa)

    fortalezas = [f"{d['nombre']}: {f['texto']}" for d in evaluacion["dimensiones"] for f in d["factores"] if f["efecto"] > 0]
    debilidades = [f"{d['nombre']}: {f['texto']}" for d in evaluacion["dimensiones"] for f in d["factores"] if f["efecto"] < 0]
    from .inversiones_analytics import get_mep_actual
    salida = {
        **base_salida,
        "estado": "ok",
        "mensaje": "",
        "secciones": secciones,
        "fuentes": _fuentes(e, u.ficha(e.base), tecnico, bool(get_mep_actual(db)), hoy),
        "evaluacion": evaluacion,
        "fortalezas": fortalezas[:6],
        "debilidades": debilidades[:6],
        "diagnostico": diag,
        "valor_razonable": _vr_resumen(vr),
        "comparador": _comp_resumen(comp),
        "tecnico": tecnico,
        "riesgo": ins.riesgo,
        "encaje": {k: v for k, v in (encaje or {}).items() if k != "todas_observaciones"} if encaje else None,
        "alternativas": {k: v for k, v in alternativas.items() if k != "evaluaciones"},
        "escenarios": escenarios,
        "conclusion": conclusion,
        "versiones": {
            "centro": VERSION_REGLAS, "evaluacion": ev.VERSION_REGLAS, "diagnostico": diag.get("version_reglas"),
            "comparador": (comp or {}).get("version_reglas"), "valor_razonable": (vr or {}).get("version_reglas"),
            "escenarios": ee.VERSION_REGLAS, "simulador": simulador_decision.VERSION_REGLAS,
        },
    }
    salida["resumen"] = interpretacion.resumen_validado(salida)
    return salida


@cache_por_sync
def analizar(ticker: str, prefs: dict, cartera: str | None, con: tuple, monto_ref_usd: float | None, db: Session) -> dict:
    """Análisis completo de un activo con las preferencias dadas (ver el docstring del módulo)."""
    return calcular_analisis(Universo(db), db, ticker, prefs, cartera, con, monto_ref_usd)


# ---------------------------------------------------------------------------------------------
# Exploración por sector / industria / país / región / temática
# ---------------------------------------------------------------------------------------------

def _pesos_exploracion(prefs: dict) -> dict:
    base = ev.pesos_para(prefs)
    return {**prefs, "pesos": {d: (0 if d in (ev.TECNICO, ev.ENCAJE) else round(w)) for d, w in base.items()}}


@cache_por_sync
def explorar(prefs: dict, sector: str | None, industria: str | None, pais: str | None, region: str | None,
             tipo: str | None, tematica: str | None, db: Session) -> dict:
    """Ranking del universo de las preferencias con los filtros pedidos. Sin técnico ni encaje (se calculan al
    abrir cada activo): el orden de esta lista sólo usa fundamentales, valoración y riesgo."""
    if tematica is not None and tematica not in tm.TEMATICAS:
        raise ValueError(f"temática desconocida: {tematica}")
    u = Universo(db)
    prefs_exp = _pesos_exploracion(prefs)
    hoy = date.today()
    items, vistos, sin_dato_tematica = [], set(), 0
    excluidas = 0
    for ticker, en_cartera, en_watchlist in _tickers_universo(db, prefs.get("universo", "catalogo"), u):
        e = u.emisor(ticker)
        if e.base in vistos or e.clasif.tipo_base in ce.TIPOS_BASE_SIN_AUTO:
            continue
        vistos.add(e.base)
        c = e.clasif
        if (sector and c.sector != sector) or (pais and c.pais != pais) or (region and c.region != region) \
                or (tipo and c.tipo != tipo) or (industria and c.industria != industria):
            continue
        if _excluida(prefs, e.base, e):
            excluidas += 1
            continue
        grupo, res = _evaluar(u, e)
        diag = asdict(_diagnostico(u, e, grupo, res))
        ficha = u.ficha(e.base)
        if tematica:
            calidad = next((d["nivel"] for d in diag["dimensiones"] if d["clave"] == "calidad"), None)
            ok = tm.cumple(tematica, ficha, res.lectura if res else None, calidad)
            if ok is None:
                sin_dato_tematica += 1
                continue
            if not ok:
                continue
        ins = ev.Insumos(ticker=e.base, es_etf=e.es_etf, diagnostico=diag, riesgo=decision_datos.riesgo_de(u, e.base),
                         encaje={"sin_cartera": True}, metricas=dict(ficha.valores) if ficha else {},
                         extra=dict(ficha.extra) if ficha else {}, sin_ganancias=bool(ficha and ficha.sin_ganancias),
                         fecha_dato=ficha.fecha_dato if ficha else None)
        eva = ev.evaluar(ins, prefs_exp, hoy)
        items.append({
            "ticker": ticker, "ticker_base": e.base, "nombre": e.nombre, "tipo": c.tipo, "sector": c.sector,
            "industria": c.industria, "pais": c.pais, "region": c.region, "en_cartera": en_cartera,
            "en_watchlist": en_watchlist, "fecha_dato": ficha.fecha_dato if ficha else None,
            "estado_datos": _estado_datos(e), "orden": eva["orden"]["puntaje"], "incompleto": eva["orden"]["incompleto"],
            "dimensiones": [{"clave": d["clave"], "nombre": d["nombre"], "puntaje": d["puntaje"], "estado": d["estado"]}
                            for d in eva["dimensiones"] if d["clave"] not in (ev.TECNICO, ev.ENCAJE)],
            "banderas": [b["texto"] for b in eva["banderas"]],
        })
    items.sort(key=lambda x: (x["orden"] is None, -(x["orden"] or 0), x["ticker"]))
    return {
        "universo": prefs.get("universo", "catalogo"),
        "total": len(items),
        "items": items[:LIMITE_EXPLORAR],
        "truncado": len(items) > LIMITE_EXPLORAR,
        "sin_dato_tematica": sin_dato_tematica,
        "excluidas": excluidas,
        "tematica": {"clave": tematica, **tm.TEMATICAS[tematica]} if tematica else None,
        "nota": ("El orden de esta lista usa fundamentales, valoración y riesgo con tus pesos; el técnico y el encaje con "
                 "tu cartera se calculan al abrir cada activo."),
        "pesos": prefs_exp["pesos"],
    }


@cache_por_sync
def facetas(db: Session) -> dict:
    """Valores reales de sector, industria, país, región y tipo en el universo con datos, y la cobertura."""
    u = Universo(db)
    conteos = {k: {} for k in ("sectores", "industrias", "paises", "regiones", "tipos")}
    con_datos = 0
    for c in pares_engine.deduplicar(u.candidatos):
        e = u.emisor(c.ticker_base)
        con_datos += 1
        for clave, valor in (("sectores", e.clasif.sector), ("industrias", e.clasif.industria), ("paises", e.clasif.pais),
                             ("regiones", e.clasif.region), ("tipos", e.clasif.tipo)):
            if valor:
                conteos[clave][valor] = conteos[clave].get(valor, 0) + 1
    conocidos = sum(1 for b, a in u.ctx.auto.items() if a is not None)
    return {
        **{k: [{"valor": v, "n": n} for v, n in sorted(d.items(), key=lambda x: (-x[1], x[0]))] for k, d in conteos.items()},
        "tematicas": [{"clave": k, **v} for k, v in tm.TEMATICAS.items()],
        "tematicas_no_cubiertas": tm.NO_CUBIERTAS,
        "cobertura": {
            "con_fundamentales": con_datos,
            "emisores_conocidos": conocidos,
            "texto": (f"{con_datos} emisores de acciones, CEDEARs y ETFs del catálogo de IOL tienen fundamentales "
                      f"descargados (de {conocidos} clasificados). Bonos, ONs, letras y FCI no se cubren."),
        },
    }


# ---------------------------------------------------------------------------------------------
# Posición existente
# ---------------------------------------------------------------------------------------------

def analizar_posicion(ticker: str, cartera: str | None, prefs: dict, db: Session, tesis: dict | None,
                      invalidacion_cumplida: list[str]) -> dict:
    """Mantener / aumentar / reducir / salir de una posición. `tesis` = evaluación congelada de la última
    decisión guardada sobre el emisor (o None)."""
    t = ticker.strip().upper()
    rend = next((r for r in get_rendimiento_por_ticker(cartera, db) if r["ticker"] == t), None)
    if rend is None or not rend.get("cantidad_actual") or rend["cantidad_actual"] <= 0:
        raise NoEsPosicion(t)
    pnl = next((p for p in get_pnl_realizado_no_realizado(cartera, db)["por_ticker"] if p["ticker"] == t), None)
    analisis = analizar(t, prefs, cartera, (), None, db)
    secciones = {}

    valor = rend.get("valor_actual_usd") or 0.0
    sims = {}
    for clave, fraccion in pde.FRACCION_SIMULADA.items():
        sims[clave] = _seguro(f"simulacion:{clave}", secciones, simulador_decision.simular_operaciones,
                              cartera, db, [(t, valor * fraccion)]) if valor > 0 else None

    base = analisis.get("ticker_base") or t
    eje_emisor = next((x for x in (sims.get(pde.AUMENTAR) or sims.get(pde.REDUCIR) or {}).get("ejes", []) if x["eje"] == "Emisor"), None)
    peso_emisor = next((f["antes_pct"] for f in (eje_emisor or {}).get("items", []) if f["etiqueta"] == base), 0.0)
    total = _clasificados_valorizados(cartera, db).total_usd()
    peso_ticker = valor / total * 100 if total > 0 else None
    config = get_configuracion_cartera(cartera, db)
    umbrales = salud_engine._umbrales_peso_ticker(config["peso_maximo"])

    evaluacion = analisis.get("evaluacion") or {"dimensiones": [], "banderas": [], "orden": {"puntaje": None}}
    concl = analisis.get("conclusion") or {}
    alternativa_superior = concl.get("ganador") if concl.get("tipo") == ev.MAS_ATRACTIVA and concl.get("ganador") != base else None
    tesis_cmp = pde.comparar_tesis(tesis, evaluacion)
    opciones = pde.evaluar_opciones(evaluacion, base, peso_emisor, umbrales, sims, tesis_cmp, alternativa_superior,
                                    invalidacion_cumplida)

    reasignaciones = []
    for alt in ((analisis.get("alternativas") or {}).get("items") or [])[:3]:
        sim = _seguro(f"reasignacion:{alt['ticker']}", secciones, simulador_decision.simular_operaciones,
                      cartera, db, [(t, -valor * 0.5), (alt["ticker"], valor * 0.5)]) if valor > 0 else None
        if sim:
            reasignaciones.append({"destino": alt["ticker"], "nombre": alt.get("nombre"),
                                   "orden_destino": alt["evaluacion"]["orden"]["puntaje"],
                                   "monto_usd": valor * 0.5, "simulacion": sim})
    sim_liquidez = sims.get(pde.REDUCIR)

    return {
        "version_reglas": pde.VERSION_REGLAS,
        "ticker": t, "ticker_base": base, "nombre": rend.get("nombre"), "cartera": cartera,
        "situacion": {
            "cantidad": rend["cantidad_actual"], "precio_promedio": rend.get("precio_promedio"),
            "precio_actual": rend.get("precio_actual"), "fecha_precio": rend.get("fecha_precio"),
            "moneda": rend.get("moneda"), "valuado_al_costo": bool(rend.get("valuado_al_costo")),
            "valor_actual_usd": rend.get("valor_actual_usd"), "valor_actual_ars": rend.get("valor_actual_ars"),
            "valor_invertido_usd": rend.get("valor_invertido_usd"), "valor_invertido_ars": rend.get("valor_invertido_ars"),
            "rendimiento_usd": rend.get("rendimiento_simple_usd"), "rendimiento_ars": rend.get("rendimiento_simple_ars"),
            "realizado_usd": (pnl or {}).get("realizado_usd"), "realizado_ars": (pnl or {}).get("realizado_ars"),
            "no_realizado_usd": (pnl or {}).get("no_realizado_usd"), "no_realizado_ars": (pnl or {}).get("no_realizado_ars"),
            "ingresos_usd": (pnl or {}).get("ingresos_usd"), "ingresos_ars": (pnl or {}).get("ingresos_ars"),
            "peso_ticker_pct": peso_ticker, "peso_emisor_pct": peso_emisor,
            "sector": rend.get("sector"), "pais": rend.get("pais"),
            "peso_maximo": config["peso_maximo"], "umbral_atencion_pct": umbrales[0], "umbral_revisar_pct": umbrales[1],
            "nota_resultado": pde.NOTA_RESULTADO,
        },
        "tesis": tesis_cmp,
        "opciones": opciones,
        "reasignaciones": reasignaciones,
        "liquidez": {"simulacion": sim_liquidez, "texto": "Reducir a la mitad y dejar lo liberado sin invertir."} if sim_liquidez else None,
        "secciones": secciones,
        "analisis": analisis,
        "invalidacion_cumplida": invalidacion_cumplida,
    }
