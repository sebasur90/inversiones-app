"""Resolución única de la clasificación de cada instrumento: tipo, sector, industria, país, región.

**Todas las pantallas que agrupan por estos ejes leen de acá** (Exposición, Descomposición,
Rebalanceo, Contribución/Concentración, Salud, Diagnóstico, las fichas). Antes cada una leía el
texto crudo de la ficha del Sheet; ahora la clasificación combina cuatro fuentes campo por campo
(`clasificacion_engine.resolver`): la corrección manual hecha desde la app, el seed versionado,
lo que se derivó de Yahoo (`clasificacion_auto`) y la ficha del Sheet o de la watchlist.

`CLASIFICACION_AUTO` (env, default `true`) es el interruptor de reversión: en `false` el resolutor
devuelve **exactamente** el texto crudo del Sheet, que era el comportamiento previo.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ..database import (
    ClasificacionAuto, ClasificacionOverride, InstrumentoInversion, MovimientoInversion, WatchlistItem,
)
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
    return (os.getenv("CLASIFICACION_AUTO") or "true").strip().lower() in ("true", "1", "yes")


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
    # Tickers con movimientos pero sin ficha en el Sheet: antes caían enteros en "Sin
    # clasificar"; si Yahoo o el catálogo los conocen, ahora se clasifican igual.
    for (ticker,) in db.query(MovimientoInversion.ticker).distinct():
        if ticker and ticker not in resultado:
            c = ctx.resolver(ticker, None)
            if c.tipo or c.sector or c.pais:
                resultado[ticker] = c
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


# ── Correcciones manuales ────────────────────────────────────────────────────

CAMPOS_CORREGIBLES = ("tipo", "sector", "industria", "pais", "region", "simbolo_yahoo")


def _validar_valor(campo: str, valor: str) -> str:
    """Normaliza la corrección al vocabulario canónico. Un valor fuera del vocabulario en un campo
    cerrado (tipo, región) es un error: si no, la corrección no matchearía con nada."""
    valor = (valor or "").strip()
    if not valor:
        raise ValueError(f"{campo}: valor vacío (para volver al automático, borrá la corrección)")
    if campo == "tipo":
        if valor not in ce.TIPOS:
            raise ValueError(f"tipo debe ser uno de {', '.join(ce.TIPOS)}")
        return valor
    if campo == "region":
        canon = ce.region_canonica(valor)
        if canon not in ce.REGIONES:
            raise ValueError(f"región debe ser una de {', '.join(ce.REGIONES)}")
        return canon
    if campo == "sector":
        return ce.sector_canonico(valor) or valor
    if campo == "pais":
        return ce.pais_canonico(valor) or valor
    if campo == "simbolo_yahoo":
        return valor.upper()
    return valor


def get_clasificacion_ticker(db: Session, ticker: str) -> dict:
    ctx = Contexto(db)
    base = ctx.base(ticker)
    inst = db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
    wl = db.get(WatchlistItem, ticker)
    fila = inst or wl
    sheet = {"tipo_instrumento": fila.tipo_instrumento, "sector": fila.sector, "pais": fila.pais} if fila else {}
    resuelta = ctx.resolver(ticker, sheet)
    auto = ctx.auto.get(base)
    return {
        "ticker": ticker,
        "ticker_base": base,
        "resuelta": {
            "tipo": resuelta.tipo, "tipo_base": resuelta.tipo_base, "sector": resuelta.sector,
            "industria": resuelta.industria, "pais": resuelta.pais, "region": resuelta.region,
            "fuentes": dict(resuelta.fuentes),
        },
        "automatica": _auto_dict(auto),
        "sheet": {"tipo": sheet.get("tipo_instrumento"), "sector": sheet.get("sector"), "pais": sheet.get("pais")} if fila else {},
        "correcciones": dict(ctx.overrides.get(base, {})),
        "simbolo_yahoo": auto.simbolo_yahoo if auto else None,
        "estado_datos": auto.estado if auto else None,
        "opciones": {
            "tipo": list(ce.TIPOS),
            "sector": list(ce.SECTORES) + list(ce.SECTORES_EXTRA),
            "region": list(ce.REGIONES),
        },
    }


def corregir(db: Session, ticker: str, campos: dict[str, str | None]) -> None:
    """Guarda las correcciones de `campos` (sólo los que vienen con valor). Hace commit."""
    from datetime import datetime

    base = Contexto(db).base(ticker)
    ahora = datetime.utcnow()
    normalizados = {c: _validar_valor(c, v) for c, v in campos.items() if v is not None and c in CAMPOS_CORREGIBLES}
    for campo, valor in normalizados.items():
        fila = db.query(ClasificacionOverride).filter_by(ticker_base=base, campo=campo).one_or_none()
        if fila is None:
            db.add(ClasificacionOverride(ticker_base=base, campo=campo, valor=valor, fecha_actualizacion=ahora))
        else:
            fila.valor = valor
            fila.fecha_actualizacion = ahora
    db.commit()


def borrar_correccion(db: Session, ticker: str, campo: str) -> bool:
    base = Contexto(db).base(ticker)
    n = db.query(ClasificacionOverride).filter_by(ticker_base=base, campo=campo).delete()
    db.commit()
    return n > 0


def corregir_par(db: Session, ticker: str, par: str, accion: str) -> None:
    """Agrega o quita un par. Agregar algo que estaba quitado (o al revés) reemplaza la fila."""
    from datetime import datetime
    from ..database import ParOverride

    ctx = Contexto(db)
    base, par_base = ctx.base(ticker), ctx.base(par.strip().upper())
    if par_base == base:
        raise ValueError("un emisor no puede ser par de sí mismo")
    fila = db.query(ParOverride).filter_by(ticker_base=base, par=par_base).one_or_none()
    if fila is None:
        db.add(ParOverride(ticker_base=base, par=par_base, accion=accion, fecha=datetime.utcnow()))
    else:
        fila.accion = accion
        fila.fecha = datetime.utcnow()
    db.commit()


def borrar_correccion_par(db: Session, ticker: str, par: str) -> bool:
    from ..database import ParOverride

    ctx = Contexto(db)
    n = db.query(ParOverride).filter_by(ticker_base=ctx.base(ticker), par=ctx.base(par.strip().upper())).delete()
    db.commit()
    return n > 0
