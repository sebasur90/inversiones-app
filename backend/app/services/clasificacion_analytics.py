"""Resolución única de la clasificación de cada instrumento: tipo, sector, industria, país, región.

**Todas las pantallas que agrupan por estos ejes leen de acá** (Exposición, Descomposición,
Rebalanceo, Contribución/Concentración, Salud, Diagnóstico, las fichas). Antes cada una leía el
texto crudo de la ficha del Sheet; ahora la clasificación combina cuatro fuentes campo por campo
(`clasificacion_engine.resolver`): la corrección manual hecha desde la app, el seed versionado,
lo que se derivó de Yahoo (`clasificacion_auto`) y la ficha del Sheet o de la watchlist.

`CLASIFICACION_AUTO` (env) es el interruptor: en `false` (el default por ahora) el resolutor
devuelve **exactamente** el texto crudo del Sheet, que era el comportamiento previo.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ..database import ClasificacionAuto, ClasificacionOverride, InstrumentoInversion, WatchlistItem
from . import clasificacion_engine as ce
from .cache import cache_por_sync
from .catalogo_instrumentos import cargar_catalogo
from .clasificacion_seed import cargar_seed

# Atributos que se piden con `atributo()` -> campo de `ClasificacionResuelta`. `tipo_instrumento`
# es el tipo fino (lo que se muestra); `tipo_base` es la familia gruesa (lo que entienden los
# objetivos de Rebalanceo).
CAMPO_POR_ATRIBUTO = {
    "tipo_instrumento": "tipo",
    "tipo_base": "tipo_base",
    "sector": "sector",
    "pais": "pais",
    "region": "region",
    "industria": "industria",
}


def modo_auto() -> bool:
    return (os.getenv("CLASIFICACION_AUTO") or "false").strip().lower() in ("true", "1", "yes")


def _desde_sheet(tipo, sector, pais) -> ce.ClasificacionResuelta:
    """El comportamiento previo, tal cual: el texto crudo de la ficha, sin normalizar."""
    return ce.ClasificacionResuelta(
        tipo=tipo, tipo_base=tipo, sector=sector, pais=pais, region=None, industria=None,
        fuentes={c: (ce.FUENTE_SHEET if v else None) for c, v in
                 (("tipo", tipo), ("sector", sector), ("pais", pais), ("industria", None), ("region", None))},
    )


def _auto_dict(fila: ClasificacionAuto | None) -> dict:
    if fila is None or fila.estado != "ok":
        return {}
    return {
        "tipo": fila.tipo, "sector": fila.sector, "industria": fila.industria,
        "pais": fila.pais, "region": fila.region,
    }


class Contexto:
    """Lo que hace falta para resolver cualquier ticker, cargado una vez por request."""

    def __init__(self, db: Session):
        catalogo = cargar_catalogo()
        self.seed = cargar_seed()
        self.variantes = ce.mapa_variantes(catalogo, self.seed["variantes"])
        self.auto = {f.ticker_base: f for f in db.query(ClasificacionAuto)}
        self.overrides: dict[str, dict] = {}
        for o in db.query(ClasificacionOverride):
            self.overrides.setdefault(o.ticker_base, {})[o.campo] = o.valor
        self.tipo_catalogo = {e["simbolo"].upper(): e["tipo"] for e in catalogo}

    def base(self, ticker: str) -> str:
        return ce.ticker_base(ticker, self.variantes)

    def resolver(self, ticker: str, sheet: dict | None = None) -> ce.ClasificacionResuelta:
        base = self.base(ticker)
        sheet = dict(sheet or {})
        if not sheet.get("tipo_instrumento"):
            # Un ticker sin ficha (un par del catálogo): el tipo sale del panel de IOL.
            sheet["tipo_instrumento"] = self.tipo_catalogo.get(ticker.upper()) or self.tipo_catalogo.get(base)
        return ce.resolver(
            override=self.overrides.get(base),
            seed=self.seed["exposicion"].get(base),
            auto=_auto_dict(self.auto.get(base)),
            sheet=sheet,
        )


@cache_por_sync
def clasificaciones(db: Session) -> dict[str, ce.ClasificacionResuelta]:
    """Clasificación de cada ticker de cartera (ficha del Sheet) y de la watchlist, por ticker
    **local** (`AAPLD`, no `AAPL`): es la clave con la que las pantallas tienen las posiciones."""
    instrumentos = list(db.query(InstrumentoInversion))
    watchlist = list(db.query(WatchlistItem))

    if not modo_auto():
        resultado = {w.ticker: _desde_sheet(w.tipo_instrumento, w.sector, w.pais) for w in watchlist}
        resultado.update({i.ticker: _desde_sheet(i.tipo_instrumento, i.sector, i.pais) for i in instrumentos})
        return resultado

    ctx = Contexto(db)
    resultado = {}
    for w in watchlist:
        # El país de la watchlist es el default "argentina" del alta (la plaza, no el emisor):
        # `resolver` ya lo ignora para CEDEARs.
        resultado[w.ticker] = ctx.resolver(
            w.ticker, {"tipo_instrumento": w.tipo_instrumento, "sector": w.sector, "pais": w.pais},
        )
    for i in instrumentos:
        resultado[i.ticker] = ctx.resolver(
            i.ticker, {"tipo_instrumento": i.tipo_instrumento, "sector": i.sector, "pais": i.pais},
        )
    return resultado


def atributo(clasif: dict, ticker: str, attr: str):
    """Valor de `attr` para `ticker` (ver `CAMPO_POR_ATRIBUTO`), o None si no hay dato."""
    c = clasif.get(ticker)
    if c is None:
        return None
    return c.get(CAMPO_POR_ATRIBUTO.get(attr, attr))


def diferencias(db: Session) -> list[dict]:
    """Por ticker de cartera y watchlist: qué dice el Sheet y qué dice la clasificación resuelta
    (con fuentes), sólo donde difieren. Es lo que hay que mirar antes de confiar en el modo
    automático, independientemente de si está prendido."""
    ctx = Contexto(db)
    filas = [(i.ticker, i.tipo_instrumento, i.sector, i.pais, True) for i in db.query(InstrumentoInversion)]
    en_cartera = {f[0] for f in filas}
    filas += [(w.ticker, w.tipo_instrumento, w.sector, w.pais, False)
              for w in db.query(WatchlistItem) if w.ticker not in en_cartera]

    salida = []
    for ticker, tipo, sector, pais, cartera in sorted(filas):
        sheet = _desde_sheet(tipo, sector, pais)
        auto = ctx.resolver(ticker, {"tipo_instrumento": tipo, "sector": sector, "pais": pais})
        cambios = {}
        for campo in ("tipo", "sector", "pais"):
            antes, despues = sheet.get(campo), auto.get(campo)
            if (antes or None) != (despues or None):
                cambios[campo] = {"antes": antes, "despues": despues, "fuente": auto.fuentes.get(campo)}
        if cambios:
            salida.append({
                "ticker": ticker,
                "ticker_base": ctx.base(ticker),
                "en_cartera": cartera,
                "region": auto.region,
                "cambios": cambios,
            })
    return salida
