"""Historial de diagnósticos (point-in-time): qué decía la app de cada emisor, y cuándo.

Después de cada corrida de la ingesta de fundamentales (`scheduler.correr_fundamentales`) se recorre el
universo elegido, se calcula el diagnóstico de cada emisor —y, para lo que está en cartera o watchlist, el
comparador y el valor razonable— y **se guarda una fila sólo si algo cambió** respecto de la anterior
(`huella`). La fila es una foto que no se recalcula nunca: lleva la versión de las reglas que la produjo,
así que un cambio de reglas se distingue de un cambio de la empresa.

Por qué existe: sin historial no hay forma honesta de saber si "barata" o "calidad débil" anticiparon algo.
Reconstruir el pasado con las reglas y los datos de hoy sería mirar el futuro. El backtest
(`historial_engine`) sólo usa lo acumulado a partir de acá.

Va **fuera** de la ingesta a propósito: la ingesta escribe con un único commit bajo `sync_lock`, y calcular
cientos de diagnósticos con ese lock tomado frenaría el sync. Un fallo acá no toca la ingesta (y al revés).

`HISTORIAL_UNIVERSO` (coma-separado, default `cartera,watchlist`) elige qué emisores registrar; `catalogo`
suma todo el catálogo con datos (más CPU, no más red). Se mide en el servidor antes de subirlo.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import DiagnosticoHistorial
from . import clasificacion_engine as ce
from . import comparador_analytics, valor_razonable_analytics
from .valuacion_analytics import UNIVERSOS, Universo, _diagnostico, _evaluar, _tickers_universo

logger = logging.getLogger("historial_diagnosticos")

UNIVERSO_DEFAULT = "cartera,watchlist"


def universos_configurados() -> tuple[str, ...]:
    """Universos a registrar según `HISTORIAL_UNIVERSO`; lo inválido se ignora y, sin nada válido, rige el default."""
    crudo = os.getenv("HISTORIAL_UNIVERSO", UNIVERSO_DEFAULT)
    pedidos = tuple(dict.fromkeys(p for p in (x.strip().lower() for x in crudo.split(",")) if p in UNIVERSOS))
    return pedidos or tuple(UNIVERSO_DEFAULT.split(","))


def a_json(obj):
    """Datos serializables a una columna JSON: fechas a ISO, dataclasses a dict."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return a_json(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [a_json(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, float) and obj != obj:      # NaN no es JSON válido
        return None
    return obj


def _estados(diag) -> dict:
    return {
        d.clave: {
            "estado": d.estado, "nivel": d.nivel, "percentil": d.percentil,
            "razon": d.razones[0].texto if d.razones else d.resumen, "regla": d.regla,
        }
        for d in diag.dimensiones
    }


def _extracto_comparador(c: dict) -> dict:
    conclusion = c.get("conclusion")
    return {
        "version_reglas": c.get("version_reglas"), "estado": c.get("estado"),
        "seleccion": c.get("seleccion") or [],
        "ranking": [
            {k: r.get(k) for k in ("clave", "posicion_objetivo", "de", "tercio", "estado_objetivo", "nivel_objetivo")}
            for r in c.get("ranking") or []
        ],
        "conclusion": {k: conclusion.get(k) for k in ("regla_aplicada", "titulo", "firmeza")} if conclusion else None,
    }


def _extracto_valor(v: dict) -> dict:
    return {
        "version_reglas": v.get("version_reglas"), "estado": v.get("estado"), "lectura": v.get("lectura"),
        "confianza": v.get("confianza"), "moneda": v.get("moneda"), "precio": v.get("precio"),
        "escenarios": [
            {k: e.get(k) for k in ("clave", "valor", "margen_seguridad", "potencial")} for e in v.get("escenarios") or []
        ],
        "supuestos_por_defecto": (v.get("supuestos") or {}).get("por_defecto", True),
    }


def huella_de(fila: dict) -> str:
    """Hash de lo que hace que dos fotos sean "la misma": versiones, fecha del dato, estados, lectura y pares.

    Los percentiles, el precio y las métricas **no** entran: se mueven con cada snapshot de un par y
    llenarían la tabla de filas que no dicen nada nuevo. Quedan guardados en la foto que sí se registra.
    """
    nucleo = {
        "v": [fila["version_diagnostico"], fila.get("version_comparador"), fila.get("version_valor")],
        "fecha_dato": fila["fecha_dato"].isoformat() if fila.get("fecha_dato") else None,
        "estados": {k: [v["estado"], v["nivel"]] for k, v in sorted(fila["estados"].items())},
        "lectura": fila.get("lectura"),
        "pares": sorted(fila.get("pares") or []),
    }
    return hashlib.sha1(json.dumps(nucleo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def construir_fila(u: Universo, ticker: str, con_extras: bool, hoy: date) -> dict | None:
    """La foto de un emisor, o None si todavía no tiene fundamentales."""
    e = u.emisor(ticker)
    if e.snapshot is None or u.ficha(e.base) is None:
        return None
    grupo, res = _evaluar(u, e)
    diag = _diagnostico(u, e, grupo, res)
    ficha = u.ficha(e.base)
    mercado = valor_razonable_analytics.datos_mercado(e.snapshot)

    comparador = valor = None
    if con_extras:
        try:
            comparador = _extracto_comparador(comparador_analytics.calcular(u, ticker, ()))
        except Exception:
            logger.exception("historial: el comparador de %s falló; se registra sin él", ticker)
        try:
            valor = _extracto_valor(valor_razonable_analytics.calcular(u, ticker, ()))
        except Exception:
            logger.exception("historial: el valor razonable de %s falló; se registra sin él", ticker)

    fila = {
        "ticker_base": e.base,
        "fecha": hoy,
        "fecha_dato": e.snapshot.fecha,
        "version_diagnostico": diag.version_reglas,
        "version_comparador": comparador["version_reglas"] if comparador else None,
        "version_valor": valor["version_reglas"] if valor else None,
        "estados": a_json(_estados(diag)),
        "lectura": res.lectura if res else None,
        "confianza": diag.confianza,
        "metricas": a_json({
            "valores": ficha.valores, "extra": ficha.extra, "sector": ficha.sector, "es_etf": ficha.es_etf,
            "sin_ganancias": ficha.sin_ganancias, "recalculadas": ficha.recalculadas,
            "descartadas_moneda": ficha.descartadas_moneda, "periodo_contable": ficha.periodo_contable,
        }),
        "pares": list(grupo.pares),
        "comparador": comparador,
        "valor_razonable": valor,
        "precio": mercado.precio,
        "moneda": mercado.moneda,
    }
    fila["huella"] = huella_de(fila)
    return fila


def _ultimas_huellas(db: Session) -> dict[str, str]:
    ultimos = db.query(func.max(DiagnosticoHistorial.id)).group_by(DiagnosticoHistorial.ticker_base).subquery()
    return {
        f.ticker_base: f.huella
        for f in db.query(DiagnosticoHistorial.ticker_base, DiagnosticoHistorial.huella).filter(
            DiagnosticoHistorial.id.in_(ultimos))
    }


def registrar(db: Session, hoy: date | None = None, universos: tuple[str, ...] | None = None) -> dict:
    """Registra una foto por emisor del universo si cambió algo. Nunca lanza por un emisor: lo cuenta."""
    hoy = hoy or date.today()
    universos = universos or universos_configurados()
    u = Universo(db)
    ultimas = _ultimas_huellas(db)

    # (ticker, con_extras): el comparador y el valor razonable cuestan mucho más que el diagnóstico y sólo
    # interesan para lo que el usuario tiene o sigue.
    pendientes: dict[str, tuple[str, bool]] = {}
    for universo in universos:
        for ticker, en_cartera, en_watchlist in _tickers_universo(db, universo, u):
            e = u.emisor(ticker)
            if e.clasif.tipo_base in ce.TIPOS_BASE_SIN_AUTO:
                continue            # renta fija y FCI no tienen diagnóstico
            extras = en_cartera or en_watchlist
            previo = pendientes.get(e.base)
            pendientes[e.base] = (previo[0] if previo else ticker, extras or bool(previo and previo[1]))

    resumen = {"universos": list(universos), "emisores": len(pendientes), "nuevas": 0, "sin_cambios": 0,
               "sin_datos": 0, "errores": 0}
    for base, (ticker, extras) in sorted(pendientes.items()):
        try:
            fila = construir_fila(u, ticker, extras, hoy)
        except Exception:
            logger.exception("historial: falló el diagnóstico de %s", ticker)
            resumen["errores"] += 1
            continue
        if fila is None:
            resumen["sin_datos"] += 1
        elif ultimas.get(fila["ticker_base"]) == fila["huella"]:
            resumen["sin_cambios"] += 1
        else:
            db.add(DiagnosticoHistorial(**fila))
            resumen["nuevas"] += 1
    db.commit()
    logger.info("historial de diagnósticos: %s", resumen)
    return resumen


# ─── Lectura ─────────────────────────────────────────────────────────────────

def lista_historial(db: Session, ticker: str, limite: int = 200) -> dict:
    """Línea de tiempo de un emisor: las fotos más viejas primero, con qué cambió respecto de la anterior.

    Un cambio de `version_diagnostico` se marca aparte (`cambio_de_reglas`) y **no** se cuenta como cambio de
    la empresa: los estados de dos versiones distintas no son comparables.
    """
    from .clasificacion_analytics import Contexto

    base = Contexto(db).base(ticker.strip().upper())
    filas = (
        db.query(DiagnosticoHistorial).filter(DiagnosticoHistorial.ticker_base == base)
        .order_by(DiagnosticoHistorial.id.desc()).limit(limite).all()
    )[::-1]
    salida = []
    previa = None
    for f in filas:
        cambios = []
        cambio_reglas = previa is not None and f.version_diagnostico != previa.version_diagnostico
        if previa is not None and not cambio_reglas:
            for clave, dato in (f.estados or {}).items():
                antes = (previa.estados or {}).get(clave)
                if antes is not None and antes.get("estado") != dato.get("estado"):
                    cambios.append({"dimension": clave, "de": antes.get("estado"), "a": dato.get("estado")})
        salida.append({
            "id": f.id, "fecha": f.fecha, "fecha_dato": f.fecha_dato,
            "version_diagnostico": f.version_diagnostico, "version_comparador": f.version_comparador,
            "version_valor": f.version_valor,
            "estados": f.estados, "lectura": f.lectura, "confianza": f.confianza,
            "precio": float(f.precio) if f.precio is not None else None, "moneda": f.moneda,
            "valor_razonable": f.valor_razonable, "cambios": cambios, "cambio_de_reglas": cambio_reglas,
            "n_pares": len(f.pares or []),
        })
        previa = f
    return {"ticker_base": base, "total": len(salida), "items": salida[::-1]}


def backtest(db: Session) -> dict:
    """Retornos posteriores por estado, con lo registrado hasta hoy (ver `historial_engine`)."""
    from . import historial_engine

    filas = [
        {"id": f.id, "ticker_base": f.ticker_base, "fecha": f.fecha, "version_diagnostico": f.version_diagnostico,
         "estados": f.estados}
        for f in db.query(DiagnosticoHistorial).all()
    ]
    eventos = historial_engine.entradas_a_estado(filas)
    if not eventos:
        return historial_engine.retornos_posteriores([], {})
    u = Universo(db)
    series = {b: u.serie_usd(b) for b in {e["ticker_base"] for e in eventos}}
    return historial_engine.retornos_posteriores(eventos, series)
