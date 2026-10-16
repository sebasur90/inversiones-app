"""Adaptador DB → `pares_engine` + `valuacion_engine`: valuación de cada emisor contra sus pares.

Arma el universo una sola vez por request: cada emisor con clasificación de Yahoo, su último
snapshot de fundamentales y la clasificación resuelta (`clasificacion_analytics.Contexto`: la
corrección manual y el seed pesan también acá). Sobre eso elige pares y evalúa.

Nada de esto toca la red: si un emisor todavía no tiene datos, se informa como pendiente y la
ingesta (`fundamentales_ingesta`) lo trae en su próxima corrida.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import (
    ClasificacionAuto, FundamentalesSnapshot, InstrumentoInversion, ParOverride, WatchlistItem,
)
from . import clasificacion_engine as ce
from . import diagnostico_empresa_engine, pares_engine, valuacion_engine
from .cache import cache_por_sync
from .clasificacion_analytics import Contexto
from .inversiones_analytics import _mep_sheet

UNIVERSOS = ("cartera", "watchlist", "catalogo")


@dataclass
class _Emisor:
    base: str
    auto: ClasificacionAuto | None
    snapshot: FundamentalesSnapshot | None
    clasif: ce.ClasificacionResuelta
    es_etf: bool
    # Serie semanal del snapshot más nuevo **que la tenga**: puede ser anterior al de los fundamentales
    # (si la descarga de la serie falló o un 429 cortó la corrida, el snapshot nuevo queda sin ella).
    serie: list | None = None
    fecha_serie: date | None = None

    @property
    def simbolo(self) -> str | None:
        return self.auto.simbolo_yahoo if self.auto else None

    @property
    def nombre(self) -> str | None:
        return self.auto.nombre if self.auto else None


class Universo:
    """Todos los emisores con datos, sus fichas y los overrides de pares. Una vez por request."""

    def __init__(self, db: Session):
        self.db = db
        self.ctx = Contexto(db)
        self._mep_cache: dict = {}

        ultimos = (
            db.query(FundamentalesSnapshot.simbolo_yahoo, func.max(FundamentalesSnapshot.fecha).label("f"))
            .group_by(FundamentalesSnapshot.simbolo_yahoo)
            .subquery()
        )
        snapshots = {
            s.simbolo_yahoo: s
            for s in db.query(FundamentalesSnapshot).join(
                ultimos,
                (FundamentalesSnapshot.simbolo_yahoo == ultimos.c.simbolo_yahoo)
                & (FundamentalesSnapshot.fecha == ultimos.c.f),
            )
        }

        # Sólo tres columnas: el JSON de métricas de cada foto no hace falta acá.
        self._series: dict[str, tuple[date, list]] = {}
        for simbolo, fecha, serie in (
            db.query(FundamentalesSnapshot.simbolo_yahoo, FundamentalesSnapshot.fecha,
                     FundamentalesSnapshot.serie_semanal)
            .order_by(FundamentalesSnapshot.fecha.desc())
        ):
            if serie and simbolo not in self._series:
                self._series[simbolo] = (fecha, serie)

        self.sheet: dict[str, dict] = {}
        for w in db.query(WatchlistItem):
            self.sheet[self.ctx.base(w.ticker)] = {"tipo_instrumento": w.tipo_instrumento, "sector": w.sector, "pais": w.pais}
        for i in db.query(InstrumentoInversion):
            self.sheet[self.ctx.base(i.ticker)] = {"tipo_instrumento": i.tipo_instrumento, "sector": i.sector, "pais": i.pais}

        self.emisores: dict[str, _Emisor] = {}
        for base, auto in self.ctx.auto.items():
            snap = snapshots.get(auto.simbolo_yahoo) if auto.simbolo_yahoo else None
            self.emisores[base] = self._emisor(base, auto, snap)

        self.agregar: dict[str, list[str]] = {}
        self.quitar: dict[str, list[str]] = {}
        for o in db.query(ParOverride).order_by(ParOverride.fecha):
            destino = self.agregar if o.accion == "agregar" else self.quitar
            destino.setdefault(o.ticker_base, []).append(o.par.upper())

        self._fichas: dict[str, valuacion_engine.Ficha | None] = {}
        self.candidatos = [self.candidato(e) for e in self.emisores.values()
                           if e.auto is not None and e.auto.estado == "ok" and e.snapshot is not None]

    def _emisor(self, base: str, auto: ClasificacionAuto | None, snap) -> _Emisor:
        clasif = self.ctx.resolver(base, self.sheet.get(base))
        es_etf = clasif.tipo == ce.TIPO_CEDEAR_ETF or (auto is not None and (auto.quote_type or "").upper() == "ETF")
        fecha_serie, serie = self._series.get(auto.simbolo_yahoo, (None, None)) if auto and auto.simbolo_yahoo else (None, None)
        return _Emisor(base=base, auto=auto, snapshot=snap, clasif=clasif, es_etf=es_etf,
                       serie=serie, fecha_serie=fecha_serie)

    def emisor(self, ticker: str) -> _Emisor:
        base = self.ctx.base(ticker)
        if base not in self.emisores:
            self.emisores[base] = self._emisor(base, None, None)
        return self.emisores[base]

    def candidato(self, e: _Emisor) -> pares_engine.Candidato:
        # La corrección manual se guarda en castellano ("Bebidas sin alcohol") y Yahoo trae el inglés
        # ("Beverages - Non-Alcoholic"): se comparan por la forma legible de las dos.
        industria = ce.industria_legible(
            (self.ctx.overrides.get(e.base) or {}).get("industria") or (e.auto.industria_raw if e.auto else None)
        )
        tamano = float(e.snapshot.market_cap_usd) if e.snapshot and e.snapshot.market_cap_usd is not None else None
        return pares_engine.Candidato(
            ticker_base=e.base,
            simbolo_yahoo=e.simbolo,
            nombre=e.nombre,
            es_etf=e.es_etf,
            sector=e.clasif.sector,
            industria_raw=industria,
            categoria=e.auto.categoria_etf_raw if e.auto else None,
            region=e.clasif.region,
            tamano_usd=tamano,
        )

    def _a_usd(self, moneda: str | None):
        if not moneda or moneda == "USD":
            return None, False
        if moneda == "ARS":
            def _f(fecha: date):
                mep = _mep_sheet(fecha, self.db, self._mep_cache)
                return 1.0 / mep if mep else None
            return _f, False
        return None, True  # otra moneda (BRL, EUR): se mide en moneda local y se avisa

    def ficha(self, base: str) -> valuacion_engine.Ficha | None:
        if base in self._fichas:
            return self._fichas[base]
        e = self.emisores.get(base)
        ficha = None
        if e is not None and e.snapshot is not None:
            ext = valuacion_engine.extraer_metricas(
                e.snapshot.metricas or {}, bool(e.snapshot.ratios_precio_confiables), e.es_etf, e.clasif.sector,
            )
            a_usd, aproximado = self._a_usd(e.snapshot.moneda)
            ext.valores.update(valuacion_engine.rendimientos(e.serie, a_usd))
            ficha = valuacion_engine.Ficha(
                ticker_base=base, valores=ext.valores, es_etf=e.es_etf, sin_ganancias=ext.sin_ganancias,
                recalculadas=ext.recalculadas, descartadas_moneda=ext.descartadas_moneda,
                fecha_dato=e.snapshot.fecha, momentum_aproximado=aproximado, sector=e.clasif.sector,
                fecha_serie=e.fecha_serie, extra=ext.extra, periodo_contable=ext.periodo_contable,
            )
        self._fichas[base] = ficha
        return ficha

    def pares(self, e: _Emisor) -> pares_engine.GrupoPares:
        return pares_engine.elegir_pares(
            self.candidato(e), self.candidatos,
            agregar=self.agregar.get(e.base), quitar=self.quitar.get(e.base),
        )

    def serie_usd(self, base: str) -> list[tuple[date, float]]:
        e = self.emisores.get(base)
        if e is None or e.snapshot is None:
            return []
        a_usd, _ = self._a_usd(e.snapshot.moneda)
        puntos = []
        for p in e.serie or []:
            try:
                f, c = date.fromisoformat(p["fecha"]), float(p["cierre"])
            except (KeyError, TypeError, ValueError):
                continue
            factor = a_usd(f) if a_usd else 1.0
            if factor:
                puntos.append((f, c * factor))
        return sorted(puntos)


def _estado_datos(e: _Emisor) -> str:
    if e.auto is None:
        return "pendiente"
    if e.auto.estado == "ok":
        return "ok" if e.snapshot is not None else "pendiente"
    return e.auto.estado or "pendiente"


def _clasificacion_dict(c: ce.ClasificacionResuelta) -> dict:
    return {
        "tipo": c.tipo, "tipo_base": c.tipo_base, "sector": c.sector, "industria": c.industria,
        "pais": c.pais, "region": c.region, "fuentes": dict(c.fuentes),
    }


def _fuerza_relativa(u: Universo, base: str, pares: list[str]) -> list[dict]:
    """Cierres semanales en USD del emisor y de cada par, alineados por fecha (hasta 5 años).

    Van **en precio, no normalizados**: la fecha base desde la que se compara la elige el usuario
    en el gráfico (p.ej. el piso de una baja), y el re-base a 100 y la mediana de los pares se
    calculan ahí, sobre esa fecha.
    """
    propia = u.serie_usd(base)
    if len(propia) < 2:
        return []
    series_pares = {p: dict(s) for p in pares if (s := u.serie_usd(p))}
    return [
        {
            "fecha": fecha,
            "propio": round(cierre, 6),
            "pares": {p: round(s[fecha], 6) for p, s in series_pares.items() if fecha in s},
        }
        for fecha, cierre in propia
    ]


def _evaluar(u: Universo, e: _Emisor) -> tuple[pares_engine.GrupoPares, valuacion_engine.ResultadoValuacion | None]:
    grupo = u.pares(e)
    ficha = u.ficha(e.base)
    if ficha is None:
        return grupo, None
    fichas_pares = [f for f in (u.ficha(p) for p in grupo.pares) if f is not None]
    return grupo, valuacion_engine.evaluar(ficha, fichas_pares)


def _diagnostico(u: Universo, e: _Emisor, grupo: pares_engine.GrupoPares,
                 res: valuacion_engine.ResultadoValuacion | None) -> diagnostico_empresa_engine.Diagnostico:
    ficha = u.ficha(e.base)
    if ficha is None or res is None:
        return diagnostico_empresa_engine.diagnostico_sin_datos()
    fichas_pares = [f for f in (u.ficha(p) for p in grupo.pares) if f is not None]
    return diagnostico_empresa_engine.diagnosticar(ficha, res, fichas_pares)


def _metrica_dict(r: valuacion_engine.ResultadoMetrica) -> dict:
    return {
        "clave": r.clave, "nombre": r.nombre, "grupo": r.grupo, "formato": r.formato,
        "valor": r.valor, "mediana_pares": r.mediana_pares, "n": r.n, "percentil": r.percentil,
        "banda": r.banda, "mayor_es_mejor": r.mayor_es_mejor, "metodo": r.metodo,
        "diferencia": r.diferencia,
    }


def _frase_dict(f: valuacion_engine.Frase) -> dict:
    return {"texto": f.texto, "regla": f.regla, "tono": f.tono, "metricas": list(f.metricas)}


@cache_por_sync
def get_valuacion_ticker(ticker: str, db: Session) -> dict:
    """Ficha completa de un ticker: clasificación con fuentes, pares, tabla lado a lado,
    percentiles, frases y fuerza relativa."""
    u = Universo(db)
    e = u.emisor(ticker)
    grupo, res = _evaluar(u, e)

    columnas = [e.base] + grupo.pares
    tabla = []
    if res is not None:
        for r in res.metricas:
            valores = {}
            for col in columnas:
                f = u.ficha(col)
                valores[col] = f.valores.get(r.clave) if f is not None else None
            tabla.append({
                **_metrica_dict(r),
                "origen": diagnostico_empresa_engine.origen_metrica(r.clave, u.ficha(e.base)),
                "valores": valores,
            })

    def _par_dict(p: str) -> dict:
        em = u.emisores.get(p)
        return {
            "ticker_base": p,
            "nombre": em.nombre if em else None,
            "tiene_datos": u.ficha(p) is not None,
            "agregado": p in grupo.agregados,
            "tamano_usd": float(em.snapshot.market_cap_usd) if em and em.snapshot and em.snapshot.market_cap_usd is not None else None,
        }

    return {
        "ticker": ticker.upper(),
        "ticker_base": e.base,
        "nombre": e.nombre,
        "simbolo_yahoo": e.simbolo,
        "metodo_mapeo": e.auto.metodo_mapeo if e.auto else None,
        "estado_datos": _estado_datos(e),
        "fecha_dato": e.snapshot.fecha if e.snapshot else None,
        "es_etf": e.es_etf,
        "clasificacion": _clasificacion_dict(e.clasif),
        "pares": {
            "criterio": grupo.criterio,
            "items": [_par_dict(p) for p in grupo.pares],
            "automaticos": grupo.automaticos,
            "agregados": grupo.agregados,
            "quitados": grupo.quitados,
        },
        "lectura": res.lectura if res else valuacion_engine.LECTURA_SIN_DATOS,
        "lectura_texto": res.lectura_texto if res else valuacion_engine.TEXTO_LECTURA[valuacion_engine.LECTURA_SIN_DATOS],
        "regla_lectura": res.regla_lectura if res else "todavía no hay fundamentales de este emisor",
        "frases": [_frase_dict(f) for f in res.frases] if res else [],
        "tabla": {"columnas": columnas, "filas": tabla},
        "n_pares_con_datos": res.n_pares_con_datos if res else 0,
        "fuerza_relativa": _fuerza_relativa(u, e.base, grupo.pares) if res else [],
        "advertencias": res.advertencias if res else [],
        "diagnostico": asdict(_diagnostico(u, e, grupo, res)),
    }


def _tickers_universo(db: Session, universo: str, u: Universo) -> list[tuple[str, bool, bool]]:
    """`(ticker, en_cartera, en_watchlist)` del universo pedido."""
    from .watchlist_analytics import _tickers_en_cartera

    cartera = _tickers_en_cartera(db, date.today())
    watchlist = {w.ticker for w in db.query(WatchlistItem.ticker)}
    if universo == "cartera":
        tickers = sorted(cartera)
    elif universo == "watchlist":
        tickers = sorted(watchlist)
    else:
        vistos: set[str] = set()
        tickers = []
        for c in pares_engine.deduplicar(u.candidatos):
            if c.ticker_base not in vistos:
                vistos.add(c.ticker_base)
                tickers.append(c.ticker_base)
        tickers.sort()
    bases_cartera = {u.ctx.base(t) for t in cartera}
    bases_watch = {u.ctx.base(t) for t in watchlist}
    return [(t, u.ctx.base(t) in bases_cartera, u.ctx.base(t) in bases_watch) for t in tickers]


@cache_por_sync
def get_valuacion_lista(
    universo: str,
    db: Session,
    tipo: str | None = None,
    sector: str | None = None,
    region: str | None = None,
    lectura: str | None = None,
) -> dict:
    """Una tarjeta por emisor del universo con su lectura y sus dos frases principales."""
    u = Universo(db)
    items = []
    vistos_base: set[str] = set()
    for ticker, en_cartera, en_watchlist in _tickers_universo(db, universo, u):
        e = u.emisor(ticker)
        if e.base in vistos_base:
            continue  # dos variantes del mismo emisor en cartera
        vistos_base.add(e.base)
        if e.clasif.tipo_base in ce.TIPOS_BASE_SIN_AUTO:
            continue  # renta fija y FCI: fuera de esta etapa
        c = e.clasif
        if tipo and c.tipo != tipo:
            continue
        if sector and c.sector != sector:
            continue
        if region and c.region != region:
            continue
        grupo, res = _evaluar(u, e)
        lect = res.lectura if res else valuacion_engine.LECTURA_SIN_DATOS
        if lectura and lect != lectura:
            continue
        diag = _diagnostico(u, e, grupo, res)
        items.append({
            "ticker": ticker,
            "ticker_base": e.base,
            "nombre": e.nombre,
            "tipo": c.tipo,
            "sector": c.sector,
            "region": c.region,
            "industria": c.industria,
            "lectura": lect,
            "lectura_texto": valuacion_engine.TEXTO_LECTURA[lect],
            "frases": [f.texto for f in res.frases[:2]] if res else [],
            "n_pares_con_datos": res.n_pares_con_datos if res else 0,
            "estado_datos": _estado_datos(e),
            "fecha_dato": e.snapshot.fecha if e.snapshot else None,
            "en_cartera": en_cartera,
            "en_watchlist": en_watchlist,
            "dimensiones": [{"clave": d.clave, "estado": d.estado, "nivel": d.nivel, "percentil": d.percentil}
                            for d in diag.dimensiones],
        })

    conteos: dict[str, int] = {}
    for it in items:
        conteos[it["lectura"]] = conteos.get(it["lectura"], 0) + 1
    return {"universo": universo, "total": len(items), "conteos": conteos, "items": items}
