"""Adaptador Session/DB → respuesta del mapa de mercado.

Una **lista plana** con todos los emisores de renta variable del catálogo de IOL (acciones
locales, CEDEARs y ETFs), cada uno con su clasificación, su capitalización, su variación reciente
y su relación con el usuario (en cartera, en watchlist, peso). La agrupación y el tamaño los arma
el frontend, así cambiar de eje en pantalla no vuelve a pedir nada.

Reutiliza, sin recalcular: el universo y el símbolo de Yahoo de `fundamentales_ingesta`, la
clasificación resuelta de `clasificacion_analytics.Contexto` (manual > seed > Yahoo > Sheet, la que
manda en todas las pantallas) y la valuación de cartera de `_clasificados_valorizados`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import ClasificacionAuto, FundamentalesSnapshot, VariacionMercado, WatchlistItem
from . import clasificacion_engine as ce
from . import mapa_mercado_engine as eng
from .cache import cache_por_sync
from .clasificacion_analytics import Contexto
from .fundamentales_ingesta import construir_universo
from .inversiones_analytics import _clasificados_valorizados


def _num(x) -> float | None:
    return float(x) if x is not None else None


def _ticker_representativo(base: str, locales: set[str]) -> str:
    """El ticker local con el que se abre la ficha: el propio emisor si cotiza con ese nombre
    (`AAPL`), si no el primero alfabético (`PETR3` → el que haya)."""
    return base if (base in locales or not locales) else sorted(locales)[0]


def _market_caps(db: Session) -> dict[str, float]:
    """Último `market_cap_usd` de cada símbolo de Yahoo."""
    ultimos = (
        db.query(FundamentalesSnapshot.simbolo_yahoo, func.max(FundamentalesSnapshot.fecha).label("f"))
        .group_by(FundamentalesSnapshot.simbolo_yahoo)
        .subquery()
    )
    return {
        s.simbolo_yahoo: float(s.market_cap_usd)
        for s in db.query(FundamentalesSnapshot).join(
            ultimos,
            (FundamentalesSnapshot.simbolo_yahoo == ultimos.c.simbolo_yahoo)
            & (FundamentalesSnapshot.fecha == ultimos.c.f),
        )
        if s.market_cap_usd is not None
    }


def _pesos_cartera(db: Session, ctx: Contexto) -> dict[str, float]:
    """% de cada emisor (por `ticker_base`) sobre la cartera consolidada. Mismo criterio de total
    que la pantalla principal; los montos no salen de acá (los tapa el modo privacidad)."""
    pos = _clasificados_valorizados(None, db)
    por_base: dict[str, float] = {}
    for _cart, ticker, valor_usd, _ars in pos.valores:
        base = ctx.base(ticker)
        por_base[base] = por_base.get(base, 0.0) + valor_usd
    total = sum(por_base.values())
    if total <= 0:
        return {b: 0.0 for b in por_base}
    return {b: 100.0 * v / total for b, v in por_base.items()}


@cache_por_sync
def get_mapa_mercado(db: Session) -> dict:
    ctx = Contexto(db)
    universo = construir_universo(db)
    caps = _market_caps(db)
    variaciones = {v.simbolo_yahoo: v for v in db.query(VariacionMercado)}
    pesos = _pesos_cartera(db, ctx)
    en_watchlist = {ctx.base(w.ticker) for w in db.query(WatchlistItem)}
    fichas = {w.ticker: w for w in db.query(WatchlistItem)}

    items: list[dict] = []
    for base, em in sorted(universo.items()):
        if em.metodo == ce.METODO_NO_APTO:
            continue
        auto = ctx.auto.get(base)
        # Un emisor que Yahoo no conoce y que no es del usuario no aporta nada al mapa.
        if not em.propio and (auto is None or auto.estado != "ok"):
            continue
        ticker = _ticker_representativo(base, em.tickers_locales)
        ficha = fichas.get(ticker)
        clasif = ctx.resolver(
            ticker, {"tipo_instrumento": ficha.tipo_instrumento, "sector": ficha.sector, "pais": ficha.pais}
            if ficha else None,
        )
        cap = caps.get(em.simbolo_yahoo) if em.simbolo_yahoo else None
        var = variaciones.get(em.simbolo_yahoo) if em.simbolo_yahoo else None
        peso = pesos.get(base)
        items.append({
            "ticker": ticker,
            "ticker_base": base,
            "nombre": auto.nombre if auto and auto.nombre else None,
            "tipo": clasif.tipo,
            "sector": clasif.sector,
            "industria": clasif.industria,
            "region": clasif.region,
            "pais": clasif.pais,
            "tamano_empresa": eng.tamano_empresa(cap),
            "market_cap_usd": cap,
            "var_1d": _num(var.var_1d) if var else None,
            "var_1s": _num(var.var_1s) if var else None,
            "var_1m": _num(var.var_1m) if var else None,
            "var_1a": _num(var.var_1a) if var else None,
            "moneda_variacion": var.moneda if var else None,
            "fecha_cierre": var.fecha_cierre if var else None,
            "en_cartera": peso is not None,
            "en_watchlist": base in en_watchlist,
            "peso_cartera": round(peso, 4) if peso is not None else None,
            "tiene_logo": False,
        })

    avisos: list[str] = []
    en_ars = sum(1 for i in items if i["moneda_variacion"] == "ARS")
    if en_ars:
        avisos.append(
            f"{en_ars} acciones locales se muestran con su variación en pesos: falta el dólar MEP para convertirlas."
        )
    sin_var = sum(1 for i in items if i["var_1d"] is None)
    if sin_var:
        avisos.append(f"{sin_var} emisores todavía no tienen variación y se ven en gris.")

    actualizado = db.query(func.max(VariacionMercado.actualizado)).scalar()
    return {
        "items": items,
        "cobertura": {
            "total": len(items),
            "con_variacion": sum(1 for i in items if i["var_1d"] is not None),
            "con_market_cap": sum(1 for i in items if i["market_cap_usd"] is not None),
            "con_logo": sum(1 for i in items if i["tiene_logo"]),
            "con_sector": sum(1 for i in items if i["sector"]),
        },
        "actualizado": actualizado if isinstance(actualizado, datetime) else None,
        "avisos": avisos,
    }
