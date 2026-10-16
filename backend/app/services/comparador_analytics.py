"""Adaptador DB → `comparador_engine`: "¿qué compraría en su lugar?" para un ticker.

Arma el `Universo` de valuación **una vez por request** (clasificación resuelta, fichas, pares y
correcciones manuales) y le pasa al motor puro los perfiles de los candidatos. No toca la red.
"""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from . import comparador_engine as ce
from . import pares_engine
from .cache import cache_por_sync
from .valuacion_analytics import Universo, _estado_datos, _fuerza_relativa


@cache_por_sync
def get_comparador(ticker: str, con: tuple, db: Session) -> dict:
    """Comparador de `ticker` contra las alternativas `con` (o contra su grupo de pares si `con` está vacío)."""
    return calcular(Universo(db), ticker, con)


def calcular(u: Universo, ticker: str, con: tuple = ()) -> dict:
    """El comparador sobre un `Universo` ya armado, sin caché: es lo que reutiliza el historial de
    diagnósticos para recorrer muchos tickers sin reconstruir el universo en cada uno."""
    e = u.emisor(ticker)
    grupo = u.pares(e)

    def _perfil(emisor) -> ce.Perfil:
        return ce.Perfil(
            c=u.candidato(emisor),
            en_grupo=emisor.base in grupo.pares,
            a_mano=emisor.base in grupo.agregados,
            quitado=emisor.base in grupo.quitados,
        )

    # Un solo perfil por emisor: PBR y PETR3 son el mismo y no cuentan dos veces como alternativa.
    pool = {c.ticker_base: ce.Perfil(
        c=c, en_grupo=c.ticker_base in grupo.pares, a_mano=c.ticker_base in grupo.agregados,
        quitado=c.ticker_base in grupo.quitados,
    ) for c in pares_engine.deduplicar(u.candidatos)}
    con_bases = list(dict.fromkeys(u.ctx.base(t) for t in con))
    for b in con_bases:
        if b not in pool:
            pool[b] = _perfil(u.emisor(b))   # sin datos todavía: el motor lo informa como rechazado
    for b in grupo.pares:
        if b not in pool:
            pool[b] = _perfil(u.emisor(b))

    res = ce.comparar(_perfil(e), list(pool.values()), u.ficha, con_bases)
    salida = asdict(res)
    ficha = u.ficha(e.base)
    seleccion = [a["ticker_base"] for a in salida["alternativas"]]
    salida.update({
        "ticker": ticker.upper(),
        "ticker_base": e.base,
        "nombre": e.nombre,
        "es_etf": e.es_etf,
        "estado_datos": _estado_datos(e),
        "fecha_dato": e.snapshot.fecha if e.snapshot else None,
        "seleccion": seleccion,
        "elegido_por_usuario": bool(con_bases),
        "fuerza_relativa": _fuerza_relativa(u, e.base, seleccion) if ficha is not None and seleccion else [],
    })
    return salida
