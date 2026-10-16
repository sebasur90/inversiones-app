"""Adaptador DB → `valor_razonable_engine`: valor razonable y escenarios de un ticker contra sus pares.

Arma el `Universo` de valuación **una vez por request** y le pasa al motor puro la ficha, las fichas de los
pares y el precio/tamaño del snapshot. No toca la red. Los supuestos editables del usuario viven en
`ValorSupuestos` (una fila por emisor).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from sqlalchemy.orm import Session

from ..database import ValorSupuestos
from . import valor_razonable_engine as vre
from .cache import cache_por_sync
from .valuacion_analytics import Universo, _diagnostico, _estado_datos, _evaluar


def _positivo(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def datos_mercado(snapshot) -> vre.DatosMercado:
    """Precio y tamaño en la moneda de cotización, tal como los informó Yahoo en el snapshot."""
    if snapshot is None:
        return vre.DatosMercado()
    m = snapshot.metricas or {}
    confiables = bool(snapshot.ratios_precio_confiables)
    analistas = None
    media = _positivo(m.get("targetMeanPrice"))
    if confiables and media is not None:
        analistas = {
            "media": media,
            "minimo": _positivo(m.get("targetLowPrice")),
            "maximo": _positivo(m.get("targetHighPrice")),
            "n": int(m["numberOfAnalystOpinions"]) if _positivo(m.get("numberOfAnalystOpinions")) else None,
        }
    return vre.DatosMercado(
        precio=_positivo(m.get("currentPrice")) or _positivo(m.get("regularMarketPrice")),
        moneda=m.get("currency") or snapshot.moneda,
        market_cap=_positivo(m.get("marketCap")),
        enterprise_value=_positivo(m.get("enterpriseValue")),
        ratios_confiables=confiables,
        analistas=analistas,
    )


def leer_supuestos(db: Session, base: str) -> vre.Supuestos:
    fila = db.query(ValorSupuestos).filter_by(ticker_base=base).one_or_none()
    try:
        return vre.normalizar_supuestos(fila.supuestos if fila else None)
    except ValueError:   # una fila vieja que ya no valida (cambió el catálogo de métodos): rige el cálculo por defecto
        return vre.Supuestos()


def guardar_supuestos(db: Session, ticker: str, crudo: dict) -> None:
    """Valida y guarda los supuestos del emisor (hace commit). Supuestos vacíos equivalen a borrarlos."""
    from .clasificacion_analytics import Contexto

    s = vre.normalizar_supuestos(crudo)   # ValueError con el mensaje para el usuario
    base = Contexto(db).base(ticker)
    if s.por_defecto:
        db.query(ValorSupuestos).filter_by(ticker_base=base).delete()
    else:
        guardado = {"ajuste_pct": s.ajuste_pct, "excluir": list(s.excluir), "multiplos": dict(s.multiplos)}
        fila = db.query(ValorSupuestos).filter_by(ticker_base=base).one_or_none()
        if fila is None:
            db.add(ValorSupuestos(ticker_base=base, supuestos=guardado, fecha_actualizacion=datetime.utcnow()))
        else:
            fila.supuestos = guardado
            fila.fecha_actualizacion = datetime.utcnow()
    db.commit()


def borrar_supuestos(db: Session, ticker: str) -> bool:
    from .clasificacion_analytics import Contexto

    n = db.query(ValorSupuestos).filter_by(ticker_base=Contexto(db).base(ticker)).delete()
    db.commit()
    return n > 0


@cache_por_sync
def get_valor_razonable(ticker: str, con: tuple, db: Session) -> dict:
    """Valor razonable de `ticker`. Sin `con` usa su grupo de pares; con `con=(A, B, …)` esos emisores."""
    return calcular(Universo(db), ticker, con)


def calcular(u: Universo, ticker: str, con: tuple = ()) -> dict:
    """El cálculo sobre un `Universo` ya armado, sin caché (lo reutiliza el historial de diagnósticos)."""
    db = u.db
    e = u.emisor(ticker)
    grupo, res_val = _evaluar(u, e)
    elegidos = [b for b in dict.fromkeys(u.ctx.base(t) for t in con) if b != e.base]
    bases = elegidos if elegidos else list(grupo.pares)
    fichas = [(b, u.ficha(b)) for b in bases]
    con_datos = [(b, f) for b, f in fichas if f is not None]

    diag = _diagnostico(u, e, grupo, res_val)
    resultado = vre.valor_razonable(
        u.ficha(e.base), [f for _, f in con_datos], datos_mercado(e.snapshot),
        leer_supuestos(db, e.base), confianza_datos=diag.confianza,
    )
    salida = asdict(resultado)
    sin_datos = [b for b, f in fichas if f is None]
    if sin_datos and resultado.estado != vre.ESTADO_NO_APLICA:
        salida["faltantes"] = salida["faltantes"] + [f"sin fundamentales todavía: {', '.join(sin_datos)}"]
    salida.update({
        "ticker": ticker.upper(),
        "ticker_base": e.base,
        "nombre": e.nombre,
        "es_etf": e.es_etf,
        "estado_datos": _estado_datos(e),
        "fecha_dato": e.snapshot.fecha if e.snapshot else None,
        "elegido_por_usuario": bool(elegidos),
        "pares": [{"ticker_base": b, "nombre": (u.emisores[b].nombre if b in u.emisores else None)}
                  for b, _ in con_datos],
    })
    return salida
