"""Impacto en activos: la serie de un instrumento con los eventos marcados (pasados y futuros) y el
comportamiento observado alrededor de cada uno. Adaptador DB sobre `estudio_engine`.

Series: las del análisis técnico (`ohlcv_analytics.get_serie_barras`, con la variante de referencia del
ticker: el subyacente en USD ajustado para un CEDEAR, la serie local de BYMA para el resto) o un benchmark
(`SPY`, `QQQ`, `^MERV`). Son series de **análisis**, separadas de las que valúan la cartera: acá no se toca
`precios_instrumento` ni ningún total.

Eventos futuros: la serie termina en su **última barra real**; los eventos posteriores vuelven como marcas
`futuro=true` con su fecha y sin precio. Nada se extrapola.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ...database import EventoInstrumento, EventoMercado
from .. import benchmarks, ohlcv_analytics
from . import estudio_engine as ee

DIAS_FUTURO_DEFAULT = 180
# Sin vínculo con el ticker, un evento de importancia alta se muestra igual como "general" si no está atado a
# nadie en particular o si es de una categoría que mueve a todo el mercado.
CATEGORIAS_GENERALES = ("banco_central", "geopolitica", "crisis_financiera", "elecciones", "sanciones_aranceles")
MAX_TICKERS_POR_EVENTO = 10


class TickerSinSerie(LookupError):
    """El ticker no está en el universo de la app (cartera ∪ watchlist) ni es un benchmark."""


def universo_tickers(db: Session) -> list[dict]:
    """Tickers analizables: cartera ∪ watchlist y los benchmarks."""
    out = [{"ticker": t["ticker"], "nombre": t["nombre"], "origen": t["origen"]} for t in ohlcv_analytics.listar_tickers_tecnicos(db)]
    out += [{"ticker": s, "nombre": b["nombre"], "origen": "benchmark"} for s, b in benchmarks.BENCHMARKS.items()]
    return out


def serie(db: Session, ticker: str, desde: date | None = None) -> dict:
    """`{ticker, nombre, moneda, variante, mercado, fuente_serie, advertencias, puntos: [(fecha, cierre, volumen)]}`."""
    hoy = date.today()
    if ticker in benchmarks.BENCHMARKS:
        benchmarks.asegurar(db, ticker)
        barras = benchmarks.barras(db, ticker, desde)
        info = benchmarks.BENCHMARKS[ticker]
        return {
            "ticker": ticker, "nombre": info["nombre"], "moneda": info["moneda"], "variante": "benchmark",
            "mercado": ee.mercado_de(ticker, "local").nombre, "fuente_serie": "velas" if barras else "sin_datos",
            "advertencias": [] if barras else ["sin_serie"],
            "puntos": [(b.fecha, b.cierre, b.volumen) for b in barras if b.cierre],
        }
    if not any(t["ticker"] == ticker for t in ohlcv_analytics.listar_tickers_tecnicos(db)):
        raise TickerSinSerie(ticker)
    variante = ohlcv_analytics.variante_efectiva(db, ticker, None)
    s = ohlcv_analytics.get_serie_barras(ticker, desde or date(1990, 1, 1), hoy, db, max_barras=None, variante=variante)
    return {
        "ticker": ticker, "nombre": s.get("nombre") or ticker, "moneda": s.get("moneda"), "variante": variante,
        "mercado": ee.mercado_de(ticker, variante).nombre, "fuente_serie": s.get("fuente_serie"),
        "advertencias": list(s.get("advertencias") or []) + ([s["motivo"]] if s.get("motivo") else []),
        "puntos": [(b.fecha, b.cierre, b.volumen) for b in s.get("barras") or [] if b.cierre],
    }


def _bench(db: Session, pedido: str | None, moneda: str | None, ticker: str, desde: date | None) -> tuple[str | None, list]:
    if pedido == "ninguno":
        return None, []
    simbolo = pedido if pedido in benchmarks.BENCHMARKS else benchmarks.por_defecto(moneda or "USD")
    if simbolo == ticker:
        return None, []
    if not benchmarks.asegurar(db, simbolo):
        return simbolo, []
    return simbolo, [(b.fecha, b.cierre) for b in benchmarks.barras(db, simbolo, desde) if b.cierre]


def _evento_dict(e: EventoMercado) -> dict:
    return {
        "id": e.id, "titulo": e.titulo, "categoria": e.categoria, "importancia": e.importancia,
        "fecha_evento": e.fecha_evento, "hora_evento": e.hora_evento, "zona_horaria": e.zona_horaria,
        "fecha_publicacion": e.fecha_publicacion, "programado": bool(e.programado),
    }


def _eventos_del_ticker(db: Session, ticker: str, desde: date | None, hasta: date | None,
                        categorias: list[str] | None, importancia_min: int | None, incluir_generales: bool) -> list[tuple[EventoMercado, EventoInstrumento | None]]:
    q = db.query(EventoMercado).filter(EventoMercado.descartado == 0, EventoMercado.fusionado_en_id.is_(None))
    if desde:
        q = q.filter(EventoMercado.fecha_evento >= desde)
    if hasta:
        q = q.filter(EventoMercado.fecha_evento <= hasta)
    if categorias:
        q = q.filter(EventoMercado.categoria.in_(categorias))
    if importancia_min:
        q = q.filter(EventoMercado.importancia >= importancia_min)
    eventos = q.order_by(EventoMercado.fecha_evento).all()
    vinculos = {v.evento_id: v for v in db.query(EventoInstrumento).filter(EventoInstrumento.ticker == ticker)}
    con_algun_vinculo = {eid for (eid,) in db.query(EventoInstrumento.evento_id).filter(
        EventoInstrumento.estado_revision != "descartada").distinct()}
    out = []
    for e in eventos:
        v = vinculos.get(e.id)
        if v is not None:
            if v.estado_revision != "descartada":   # descartado = el usuario dijo que no es relevante para este ticker
                out.append((e, v))
        elif incluir_generales and e.importancia >= 3 and (e.id not in con_algun_vinculo or e.categoria in CATEGORIAS_GENERALES):
            out.append((e, None))
    return out


def impacto(db: Session, ticker: str, *, desde: date | None = None, hasta: date | None = None,
            categorias: list[str] | None = None, importancia_min: int | None = None, benchmark: str | None = None,
            incluir_generales: bool = True, dias_futuro: int = DIAS_FUTURO_DEFAULT) -> dict:
    """La serie del ticker en `[desde, hoy]`, el benchmark y las marcas de eventos en `[desde, hasta]`
    (`hasta` por defecto: hoy + `dias_futuro`, para ver lo que viene)."""
    hoy = date.today()
    s = serie(db, ticker, desde)
    puntos = s.pop("puntos")
    fechas = [p[0] for p in puntos]
    simbolo_b, bench = _bench(db, benchmark, s["moneda"], ticker, desde)
    hasta_ev = hasta or (hoy + timedelta(days=dias_futuro))
    mercado = ee.NYSE if s["mercado"] == "NYSE" else ee.BYMA
    ultima = fechas[-1] if fechas else None
    marcas = []
    for e, v in _eventos_del_ticker(db, ticker, desde or (fechas[0] if fechas else None), hasta_ev,
                                     categorias, importancia_min, incluir_generales):
        futuro = ultima is None or e.fecha_evento > ultima
        ref = ee.rueda_referencia(fechas, _evento_dict(e), mercado) if not futuro else None
        marcas.append({
            "evento_id": e.id, "titulo": e.titulo, "categoria": e.categoria, "importancia": e.importancia,
            "fecha_evento": e.fecha_evento, "precision_fecha": e.precision_fecha, "estado": e.estado,
            "verificacion": e.verificacion, "futuro": futuro,
            "fecha_referencia": ref["fecha"] if ref else None, "regla_referencia": ref["regla"] if ref else None,
            "relacion": v.tipo_relacion if v else "general",
            "relevancia": float(v.relevancia) if v and v.relevancia is not None else None,
            "revision": v.estado_revision if v else None,
        })
    return {
        **s, "ultima_fecha": ultima, "desde": fechas[0] if fechas else desde, "hasta": hasta_ev,
        "serie": [{"fecha": f, "cierre": c} for f, c, _ in puntos],
        "benchmark": ({"simbolo": simbolo_b, "nombre": benchmarks.BENCHMARKS[simbolo_b]["nombre"],
                       "serie": [{"fecha": f, "cierre": c} for f, c in bench if not fechas or f >= fechas[0]]}
                      if simbolo_b and bench else None),
        "marcas": marcas,
    }


def _otros_eventos(db: Session, e: EventoMercado, ticker: str) -> list[dict]:
    margen = timedelta(days=ee.VENTANA_LARGA * 2)
    pares = _eventos_del_ticker(db, ticker, e.fecha_evento - margen, e.fecha_evento + margen, None, 2, True)
    return [_evento_dict(o) for o, _ in pares if o.id != e.id]


def analisis(db: Session, evento_id: int, ticker: str, benchmark: str | None = None) -> dict:
    """Comportamiento observado de `ticker` alrededor del evento, con benchmark y eventos superpuestos."""
    e = db.get(EventoMercado, evento_id)
    if e is None:
        raise LookupError(evento_id)
    s = serie(db, ticker)
    puntos = s.pop("puntos")
    simbolo_b, bench = _bench(db, benchmark, s["moneda"], ticker, None)
    mercado = ee.NYSE if s["mercado"] == "NYSE" else ee.BYMA
    res = ee.analizar(puntos, _evento_dict(e), mercado, bench, _otros_eventos(db, e, ticker))
    v = db.query(EventoInstrumento).filter(EventoInstrumento.evento_id == e.id, EventoInstrumento.ticker == ticker).first()
    return {
        "evento_id": e.id, "titulo": e.titulo, "categoria": e.categoria, **s,
        "benchmark": {"simbolo": simbolo_b, "nombre": benchmarks.BENCHMARKS[simbolo_b]["nombre"]} if simbolo_b and bench else None,
        "relacion": v.tipo_relacion if v else None, **res,
        "avisos": res["avisos"] + list(s["advertencias"]) + ([] if (bench or not simbolo_b) else ["sin_benchmark"]),
    }


def analisis_evento(db: Session, evento_id: int, benchmark: str | None = None) -> list[dict]:
    """El análisis para cada instrumento vinculado al evento (sin descartar), hasta `MAX_TICKERS_POR_EVENTO`.
    Los que no tienen serie se informan con su motivo en vez de omitirse."""
    vinculos = (db.query(EventoInstrumento)
                .filter(EventoInstrumento.evento_id == evento_id, EventoInstrumento.estado_revision != "descartada")
                .order_by(EventoInstrumento.relevancia.desc(), EventoInstrumento.ticker).limit(MAX_TICKERS_POR_EVENTO).all())
    out = []
    for v in vinculos:
        try:
            out.append(analisis(db, evento_id, v.ticker, benchmark))
        except TickerSinSerie:
            out.append({"evento_id": evento_id, "ticker": v.ticker, "avisos": ["fuera_del_universo"], "ventanas": [],
                        "superpuestos": [], "referencia": None, "leyenda": ee.LEYENDA, "relacion": v.tipo_relacion})
    return out


def patron_categoria(db: Session, ticker: str, categoria: str, n: int = 5) -> dict:
    """Cómo se comportó el ticker en las `n` ruedas posteriores a los eventos de una categoría que lo
    afectan, contra su línea de base (todas las ventanas de `n` ruedas de la serie)."""
    s = serie(db, ticker)
    puntos = s.pop("puntos")
    fechas = [p[0] for p in puntos]
    mercado = ee.NYSE if s["mercado"] == "NYSE" else ee.BYMA
    casos = []
    for e, _ in _eventos_del_ticker(db, ticker, fechas[0] if fechas else None, fechas[-1] if fechas else None,
                                     [categoria], None, True):
        ref = ee.rueda_referencia(fechas, _evento_dict(e), mercado)
        if ref["indice"] is None:
            continue
        w = ee.ventana(puntos, ref["indice"], n)
        casos.append({"evento_id": e.id, "titulo": e.titulo, "fecha_evento": e.fecha_evento,
                      "fecha_referencia": ref["fecha"], "rueda_pct": w["rueda_pct"], "posterior_pct": w["posterior_pct"],
                      "completa": w["completa"]})
    resumen = ee.patron(casos, ee.retornos_base(puntos, n))
    return {"ticker": ticker, "categoria": categoria, "n": n, "moneda": s["moneda"], "variante": s["variante"],
            **resumen, "casos": casos, "leyenda": ee.LEYENDA}
