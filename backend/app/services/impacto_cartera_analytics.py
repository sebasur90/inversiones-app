"""Adaptador DB → `impacto_cartera_engine`: "si sumara N USD de X, ¿cómo cambiaría mi cartera?".

Parte de `inversiones_analytics._clasificados_valorizados` (el criterio único de totales: lo que no tiene
cotización va al costo, con aviso) y le suma una tenencia simulada **en memoria**: no escribe nada, no
estima precio ni cantidad, no toca movimientos ni planilla. Cada eje se agrupa con `_agrupar`, la misma
función de Exposición, así que "antes" coincide con esa pantalla.

Sin caché: los parámetros (ticker, monto) son libres, igual que `rebalanceo/simular`.
"""
from __future__ import annotations

import re
from dataclasses import replace

from sqlalchemy.orm import Session

from ..database import WatchlistItem
from . import clasificacion_analytics
from . import clasificacion_engine as ce
from . import impacto_cartera_engine as engine
from .clasificacion_analytics import Contexto
from .etiquetas import SIN_CLASIFICAR, SIN_PAIS, SIN_REGION, SIN_SECTOR
from .inversiones_analytics import (
    _agrupar, _atributo, _clasificados_valorizados, get_configuracion_cartera, get_mep_actual,
)

MONTO_MAXIMO_USD = 1_000_000_000.0
CARTERA_SIMULADA = "(simulada)"
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")

class TickerDesconocido(LookupError):
    """El ticker no está en la cartera, la watchlist ni el catálogo."""


def _clasificacion_nueva(ctx: Contexto, db: Session, ticker: str) -> ce.ClasificacionResuelta:
    """Clasificación de un ticker que no está en las posiciones, con el mismo criterio que `clasificaciones()`."""
    w = db.query(WatchlistItem).filter_by(ticker=ticker).one_or_none()
    sheet = {"tipo_instrumento": w.tipo_instrumento, "sector": w.sector, "pais": w.pais} if w else None
    if not clasificacion_analytics.modo_auto():
        return clasificacion_analytics._desde_sheet(
            sheet and sheet["tipo_instrumento"], sheet and sheet["sector"], sheet and sheet["pais"])
    return ctx.resolver(ticker, sheet)


def _conocido(ctx: Contexto, db: Session, ticker: str, base: str, pos) -> bool:
    return bool(
        ticker in pos.clasif or ticker in pos.instrumentos
        or ctx.auto.get(base) is not None
        or ticker in ctx.tipo_catalogo or base in ctx.tipo_catalogo
        or db.query(WatchlistItem).filter_by(ticker=ticker).first() is not None
    )


def simular_aporte(cartera: str | None, db: Session, ticker: str, monto_usd: float) -> dict:
    """Cómo cambiarían los pesos de la cartera (o del consolidado) al sumar `monto_usd` de `ticker`.

    Lanza `ValueError` si el ticker o el monto no son válidos y `TickerDesconocido` si el ticker no existe.
    """
    t = (ticker or "").strip().upper()
    if not _TICKER.match(t):
        raise ValueError("el ticker no es válido")
    if not isinstance(monto_usd, (int, float)) or not 0 < monto_usd <= MONTO_MAXIMO_USD:
        raise ValueError(f"el monto debe ser mayor que 0 y hasta {MONTO_MAXIMO_USD:,.0f} USD".replace(",", "."))

    pos = _clasificados_valorizados(cartera, db)
    ctx = Contexto(db)
    base = ctx.base(t)
    if not _conocido(ctx, db, t, base, pos):
        raise TickerDesconocido(t)

    clasif_nueva = pos.clasif.get(t) or _clasificacion_nueva(ctx, db, t)
    mep = get_mep_actual(db)
    monto_ars = monto_usd * mep if mep else 0.0
    cartera_compra = cartera or CARTERA_SIMULADA

    despues = replace(pos, valores=pos.valores + [(cartera_compra, t, float(monto_usd), monto_ars)],
                      clasif={**pos.clasif, t: clasif_nueva})

    def _entradas(p, etiqueta):
        return [(etiqueta(tk), v_usd, v_ars) for _, tk, v_usd, v_ars in p.valores]

    ejes = [engine.EjeEntrada(
        engine.EJE_EMISOR,
        _agrupar(_entradas(pos, ctx.base)),
        _agrupar(_entradas(despues, ctx.base)),
        base,
    )]
    clasificados = [("Sector", "sector", SIN_SECTOR), ("País", "pais", SIN_PAIS)]
    if clasificacion_analytics.modo_auto():
        clasificados.append(("Región", "region", SIN_REGION))
    clasificados.append(("Tipo de instrumento", "tipo_instrumento", SIN_CLASIFICAR))
    for nombre, attr, sin_dato in clasificados:
        de_hoy = _agrupar(_entradas(pos, lambda tk, a=attr: _atributo(pos.instrumentos, tk, a, pos.clasif)), sin_dato=sin_dato)
        de_despues = _agrupar(
            _entradas(despues, lambda tk, a=attr: _atributo(despues.instrumentos, tk, a, despues.clasif)), sin_dato=sin_dato)
        ejes.append(engine.EjeEntrada(
            nombre, de_hoy, de_despues, clasificacion_analytics.atributo(despues.clasif, t, attr) or sin_dato))

    tickers_por_emisor: dict[str, list[str]] = {}
    for _, tk, _, _ in despues.valores:
        lista = tickers_por_emisor.setdefault(ctx.base(tk), [])
        if tk not in lista:
            lista.append(tk)
    nombres = {b: f.nombre for b, f in ctx.auto.items() if f.nombre and b in tickers_por_emisor}
    en_cartera = [tk for tk in tickers_por_emisor.get(base, []) if any(tk == x for _, x, _, _ in pos.valores)]

    config = get_configuracion_cartera(cartera, db)
    resultado = engine.construir(ejes, engine.Datos(
        ticker=t, emisor=base, monto_usd=float(monto_usd),
        total_antes_usd=pos.total_usd(), total_despues_usd=despues.total_usd(),
        peso_maximo=config["peso_maximo"], emisor_en_cartera=en_cartera,
        tickers_por_emisor=tickers_por_emisor, nombres=nombres,
    ))

    notas = []
    if not mep:
        notas.append("No hay un MEP cargado: el total en pesos no incluye el monto simulado.")
    if not pos.valores:
        notas.append("La cartera no tiene posiciones valuadas: el monto simulado sería el 100 % de la cartera.")

    return {
        **resultado,
        "ticker": t,
        "emisor": base,
        "nombre": nombres.get(base),
        "cartera": cartera,
        "monto_usd": float(monto_usd),
        "monto_ars": monto_ars,
        "total": {
            "antes_usd": pos.total_usd(), "despues_usd": despues.total_usd(),
            "antes_ars": pos.total_ars(), "despues_ars": despues.total_ars(),
        },
        "clasificacion": {
            "tipo": clasif_nueva.tipo, "sector": clasif_nueva.sector, "pais": clasif_nueva.pais,
            "region": clasif_nueva.region,
        },
        "notas": notas,
        "avisos": pos.avisos(),
    }
