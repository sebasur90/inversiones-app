"""Ingesta de clasificación y fundamentales desde Yahoo, de a poco y sin molestar al sync.

El universo es el catálogo de IOL entero (~460 emisores de renta variable una vez colapsadas las
variantes de moneda), más lo que haya en cartera o watchlist y los pares agregados a mano. Pedirlo
todo de una vez es pedirle a Yahoo que nos bloquee, así que cada corrida procesa a lo sumo
`FUNDAMENTALES_MAX_POR_CORRIDA` emisores (default 60, ~120 llamadas) en orden de prioridad:

1. cartera + watchlist sin clasificar;
2. el resto del catálogo con datos vencidos que es de la misma industria que algo propio (los
   pares de la cartera);
3. cartera + watchlist con fundamentales de más de `FRESCURA_PROPIOS_DIAS`;
4. resto del catálogo nunca visto;
5. resto del catálogo con fundamentales de más de `FRESCURA_RESTO_DIAS`.

Con dos corridas por día el universo completo se cubre en unos cuatro días y después queda en
régimen: los fundamentales cambian con cada balance trimestral, no a diario.

Decisiones:
- **Job aparte, nunca dentro del sync.** El sync ya hace ~30 llamadas a Yahoo y es lo que el
  usuario espera con la app abierta.
- **La red va fuera de `sync_lock`** y la escritura es **un solo commit** al final, con el lock
  tomado: el caché de analytics se invalida en cada commit, y SQLite con un escritor largo frena
  al resto.
- **Corte automático** ante un límite de tasa o `FALLOS_SEGUIDOS_CORTE` errores seguidos: seguir
  pidiendo sólo alarga el bloqueo. Lo ya obtenido se guarda igual.
- **Backoff** por emisor: `2^n` días (tope 30) tras `n` fallos; `no_encontrado` se reintenta a
  los `NO_ENCONTRADO_REINTENTO_DIAS`.
- No toca IOL. Respeta `USE_EXTERNAL_APIS`.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..database import (
    ClasificacionAuto, ClasificacionOverride, EstadoMarketDataTicker, FundamentalesSnapshot,
    IngestaFundamentales, InstrumentoInversion, ParOverride, WatchlistItem,
)
from . import clasificacion_engine as ce
from . import sync_lock
from .catalogo_instrumentos import cargar_catalogo
from .clasificacion_seed import cargar_seed
from .inversiones_analytics import get_mep_actual
from .market_data import yahoo
from .market_data.client import use_external_apis

logger = logging.getLogger("fundamentales_ingesta")

MAX_POR_CORRIDA_DEFAULT = 60
PAUSA_DEFAULT_SEG = 0.5
FRESCURA_PROPIOS_DIAS = 7
FRESCURA_RESTO_DIAS = 14
NO_ENCONTRADO_REINTENTO_DIAS = 90
BACKOFF_TOPE_DIAS = 30
FALLOS_SEGUIDOS_CORTE = 5
SNAPSHOTS_RETENIDOS = 8
LOCK_ESCRITURA_TIMEOUT_SEG = 300
MAX_TICKERS_SINCRONICO = 5

# Una sola ingesta a la vez (el job y el botón "Actualizar" de la app). No bloqueante.
_lock_ingesta = threading.Lock()

TIPOS_CATALOGO_APTOS = ("CEDEAR", "Acción")


def _entero_env(nombre: str, default: int, minimo: int, maximo: int) -> int:
    try:
        valor = int((os.getenv(nombre) or "").strip() or default)
    except ValueError:
        return default
    return valor if minimo <= valor <= maximo else default


def _float_env(nombre: str, default: float) -> float:
    try:
        valor = float((os.getenv(nombre) or "").strip() or default)
    except ValueError:
        return default
    return max(0.0, valor)


# ---------------------------------------------------------------------------------------------
# Universo
# ---------------------------------------------------------------------------------------------

@dataclass
class Emisor:
    ticker_base: str
    tipo_catalogo: str | None          # "CEDEAR" | "Acción" | None (extra agregado a mano)
    simbolo_yahoo: str | None = None
    metodo: str = ce.METODO_NO_APTO
    propio: bool = False               # en cartera o watchlist
    tickers_locales: set[str] = field(default_factory=set)


def _tipo_catalogo_de(tipo_texto: str | None) -> str | None:
    base = ce.tipo_base_de(tipo_texto)
    if base == ce.TIPO_BASE_CEDEAR:
        return "CEDEAR"
    if base == ce.TIPO_ACCION:
        return "Acción"
    return base  # Bono/ON/Letra/FCI o None


def construir_universo(db: Session) -> dict[str, Emisor]:
    """Todos los emisores que se pueden clasificar, por `ticker_base`.

    Incluye cartera y watchlist aunque no estén en el catálogo (un ticker cargado a mano en el
    Sheet) y los pares agregados a mano. La renta fija y los FCI quedan con `metodo=no_apto`.
    """
    catalogo = cargar_catalogo()
    seed = cargar_seed()
    variantes = ce.mapa_variantes(catalogo, seed["variantes"])
    overrides_simbolo = {
        o.ticker_base: o.valor
        for o in db.query(ClasificacionOverride).filter(ClasificacionOverride.campo == "simbolo_yahoo")
    }
    subyacentes = {
        e.ticker: e.simbolo_subyacente
        for e in db.query(EstadoMarketDataTicker).filter(EstadoMarketDataTicker.resolucion_estado == "ok")
        if e.simbolo_subyacente
    }

    universo: dict[str, Emisor] = {}

    def _agregar(ticker: str, tipo_catalogo: str | None, propio: bool) -> None:
        local = (ticker or "").strip().upper()
        if not local:
            return
        base = ce.ticker_base(local, variantes)
        em = universo.get(base)
        if em is None:
            em = universo[base] = Emisor(ticker_base=base, tipo_catalogo=tipo_catalogo)
        elif em.tipo_catalogo is None and tipo_catalogo:
            em.tipo_catalogo = tipo_catalogo
        em.propio = em.propio or propio
        em.tickers_locales.add(local)

    for entrada in catalogo:
        if entrada["tipo"] in TIPOS_CATALOGO_APTOS:
            _agregar(entrada["simbolo"], entrada["tipo"], propio=False)
    for fila in db.query(InstrumentoInversion.ticker, InstrumentoInversion.tipo_instrumento):
        _agregar(fila.ticker, _tipo_catalogo_de(fila.tipo_instrumento), propio=True)
    for fila in db.query(WatchlistItem.ticker, WatchlistItem.tipo_instrumento):
        _agregar(fila.ticker, _tipo_catalogo_de(fila.tipo_instrumento), propio=True)
    for fila in db.query(ParOverride.par).filter(ParOverride.accion == "agregar"):
        par = (fila.par or "").strip().upper()
        if par and ce.ticker_base(par, variantes) not in universo:
            # Un par agregado a mano que no está en el catálogo: se lo busca en Yahoo tal cual.
            universo[par] = Emisor(ticker_base=par, tipo_catalogo="CEDEAR", tickers_locales={par})

    for em in universo.values():
        subyacente = next((subyacentes[t] for t in sorted(em.tickers_locales) if t in subyacentes), None)
        em.simbolo_yahoo, em.metodo = ce.simbolo_yahoo(
            em.ticker_base,
            ce.tipo_base_de(em.tipo_catalogo),
            seed["simbolos_yahoo"],
            subyacente_resuelto=subyacente,
            override=overrides_simbolo.get(em.ticker_base),
        )
    return universo


# ---------------------------------------------------------------------------------------------
# Cola
# ---------------------------------------------------------------------------------------------

@dataclass
class Tarea:
    """Un pedido a Yahoo. Varios tickers base pueden compartir el símbolo (`PETR3`/`PBR`)."""
    simbolo_yahoo: str
    emisores: list[Emisor]
    prioridad: int


def _dias_desde(fecha: date | None, hoy: date) -> float:
    return math.inf if fecha is None else (hoy - fecha).days


def armar_cola(
    universo: dict[str, Emisor],
    estado: dict[str, ClasificacionAuto],
    hoy: date,
    solo: set[str] | None = None,
) -> list[Tarea]:
    """Las tareas pendientes, ordenadas por prioridad (ver docstring del módulo).

    `solo`: limita a esos tickers base e ignora frescura y backoff (el botón "Actualizar datos").
    """
    industrias_propias = {
        (estado[b].industria_raw or "").lower()
        for b, em in universo.items()
        if em.propio and b in estado and estado[b].industria_raw
    }

    por_simbolo: dict[str, list[Emisor]] = {}
    for em in universo.values():
        if em.simbolo_yahoo and em.metodo != ce.METODO_NO_APTO:
            if solo is not None and em.ticker_base not in solo:
                continue
            por_simbolo.setdefault(em.simbolo_yahoo, []).append(em)

    tareas: list[Tarea] = []
    for simbolo, emisores in por_simbolo.items():
        if solo is not None:
            tareas.append(Tarea(simbolo, emisores, 0))
            continue

        filas = [estado.get(em.ticker_base) for em in emisores]
        propio = any(em.propio for em in emisores)
        nunca = all(f is None or f.estado is None for f in filas)
        # El símbolo cambió (seed, override, subyacente nuevo): la fila vieja no vale.
        simbolo_cambio = any(
            f is not None and f.simbolo_yahoo is not None and f.simbolo_yahoo != simbolo for f in filas
        )
        proximo = max((f.proximo_intento for f in filas if f and f.proximo_intento), default=None)
        if proximo is not None and proximo > hoy and not simbolo_cambio:
            continue
        fecha_fund = min((f.fecha_fundamentales for f in filas if f and f.fecha_fundamentales), default=None)
        edad = _dias_desde(fecha_fund, hoy)

        if propio and (nunca or simbolo_cambio):
            prioridad = 1
        elif propio and edad > FRESCURA_PROPIOS_DIAS:
            prioridad = 3
        elif nunca:
            prioridad = 4
        elif simbolo_cambio or edad > FRESCURA_RESTO_DIAS:
            prioridad = 5
        else:
            continue
        # Lo ya clasificado de la misma industria que algo propio son los pares de la cartera:
        # se refrescan antes que el resto del catálogo.
        industria = next((f.industria_raw for f in filas if f and f.industria_raw), None)
        if prioridad == 5 and industria and industria.lower() in industrias_propias:
            prioridad = 2
        tareas.append(Tarea(simbolo, emisores, prioridad))

    def _orden(t: Tarea):
        fechas = [estado[em.ticker_base].fecha_fundamentales for em in t.emisores
                  if em.ticker_base in estado and estado[em.ticker_base].fecha_fundamentales]
        return (t.prioridad, min(fechas) if fechas else date.min, t.simbolo_yahoo)

    tareas.sort(key=_orden)
    return tareas


# ---------------------------------------------------------------------------------------------
# Conversión a USD
# ---------------------------------------------------------------------------------------------

def _cotizacion_fx(par: str) -> float | None:
    """Precio de un par de Yahoo (`"EURUSD=X"`). Aparte para poder stubearlo en tests."""
    dato = yahoo.fetch_ultimo_precio(par)
    return dato["precio"] if dato else None


class ConversorUSD:
    """Cuántos USD vale una unidad de cada moneda. ARS por el MEP de la DB (el mismo de toda la
    app); el resto por el par de Yahoo, pedido una vez por corrida."""

    def __init__(self, db: Session):
        self._db = db
        self._cache: dict[str, float | None] = {"USD": 1.0}

    def factor(self, moneda: str | None) -> float | None:
        if not moneda:
            return None
        if moneda in self._cache:
            return self._cache[moneda]
        valor: float | None
        if moneda == "ARS":
            mep = get_mep_actual(self._db)
            valor = 1.0 / mep if mep else None
        elif moneda in ("GBp", "GBX"):
            gbp = _cotizacion_fx("GBPUSD=X")
            valor = gbp / 100.0 if gbp else None
        else:
            valor = _cotizacion_fx(f"{moneda.upper()}USD=X")
        self._cache[moneda] = valor
        return valor


def _ratios_confiables(metricas: dict) -> bool:
    """Los ratios de precio de Yahoo (P/E, P/S, EV/EBITDA) mezclan monedas cuando el balance está
    en otra moneda que la cotización: el P/E de un ADR argentino sale de dividir dólares por
    pesos. En esos casos la valuación los recalcula con las magnitudes convertidas."""
    financiera = metricas.get("financialCurrency")
    cotizacion = metricas.get("currency")
    return not financiera or not cotizacion or financiera.upper() == cotizacion.upper()


def enriquecer_usd(metricas: dict, conversor: ConversorUSD) -> tuple[dict, float | None]:
    """Agrega `_usd` (magnitudes en USD y factores usados) y devuelve el market cap en USD."""
    f_cot = conversor.factor(metricas.get("currency"))
    f_fin = conversor.factor(metricas.get("financialCurrency") or metricas.get("currency"))
    usd: dict = {"factor_cotizacion": f_cot, "factor_financiera": f_fin}

    def _conv(clave: str, factor: float | None) -> float | None:
        v = metricas.get(clave)
        return v * factor if v is not None and factor is not None else None

    tamano = metricas.get("marketCap") or metricas.get("totalAssets")
    market_cap = tamano * f_cot if tamano is not None and f_cot is not None else None
    usd["market_cap"] = market_cap
    for clave in ("netIncomeToCommon", "totalRevenue", "ebitda", "freeCashflow"):
        usd[clave] = _conv(clave, f_fin)
    metricas = dict(metricas)
    metricas["_usd"] = usd
    return metricas, market_cap


# ---------------------------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------------------------

@dataclass
class _Obtenido:
    tarea: Tarea
    fundamentales: yahoo.ResultadoYahoo
    serie: yahoo.ResultadoYahoo | None
    metricas: dict | None = None        # `fundamentales.datos` + `_usd` (ver `enriquecer_usd`)
    market_cap_usd: float | None = None


def _proximo_intento(fallos: int, hoy: date) -> date:
    return hoy + timedelta(days=min(2 ** max(fallos, 1), BACKOFF_TOPE_DIAS))


def _aplicar(db: Session, obtenido: _Obtenido, hoy: date) -> bool:
    """Escribe el resultado de una tarea. Devuelve True si quedó con datos."""
    tarea = obtenido.tarea
    res = obtenido.fundamentales
    ok = res.estado == yahoo.ESTADO_OK

    if ok:
        metricas = obtenido.metricas or res.datos
        serie = obtenido.serie.datos if obtenido.serie and obtenido.serie.estado == yahoo.ESTADO_OK else None
        snap = (
            db.query(FundamentalesSnapshot)
            .filter_by(simbolo_yahoo=tarea.simbolo_yahoo, fecha=hoy)
            .one_or_none()
        )
        if snap is None:
            snap = FundamentalesSnapshot(simbolo_yahoo=tarea.simbolo_yahoo, fecha=hoy, fuente="yahoo")
            db.add(snap)
        snap.moneda = metricas.get("currency")
        snap.market_cap_usd = obtenido.market_cap_usd
        snap.metricas = metricas
        if serie is not None or snap.serie_semanal is None:
            snap.serie_semanal = serie
        snap.ratios_precio_confiables = 1 if _ratios_confiables(metricas) else 0

    for em in tarea.emisores:
        fila = db.get(ClasificacionAuto, em.ticker_base)
        if fila is None:
            fila = ClasificacionAuto(ticker_base=em.ticker_base, intentos_fallidos=0)
            db.add(fila)
        fila.tipo_catalogo = em.tipo_catalogo
        fila.simbolo_yahoo = tarea.simbolo_yahoo
        fila.metodo_mapeo = em.metodo
        if ok:
            # La clasificación viene en la misma respuesta que los fundamentales: se reescribe
            # siempre, así un cambio de sector en Yahoo (pasa con las reclasificaciones de GICS)
            # entra solo.
            c = ce.clasificar_desde_yahoo(res.datos, ce.tipo_base_de(em.tipo_catalogo))
            for campo in ("nombre", "quote_type", "sector_raw", "industria_raw", "pais_raw",
                          "categoria_etf_raw", "fund_family", "tipo", "sector", "industria",
                          "pais", "region", "clase_msci"):
                setattr(fila, campo, c[campo])
            fila.fecha_clasificacion = hoy
            fila.estado = "ok"
            fila.fecha_fundamentales = hoy
            fila.intentos_fallidos = 0
            fila.proximo_intento = None
            fila.ultimo_error = None
        elif res.estado == yahoo.ESTADO_NO_ENCONTRADO:
            fila.estado = "no_encontrado"
            fila.intentos_fallidos = (fila.intentos_fallidos or 0) + 1
            fila.proximo_intento = hoy + timedelta(days=NO_ENCONTRADO_REINTENTO_DIAS)
            fila.ultimo_error = res.error or "Yahoo no conoce el símbolo"
        else:
            # Un error suelto no borra una clasificación buena: sólo agenda el reintento.
            if fila.estado != "ok":
                fila.estado = "error"
            fila.intentos_fallidos = (fila.intentos_fallidos or 0) + 1
            fila.proximo_intento = _proximo_intento(fila.intentos_fallidos, hoy)
            fila.ultimo_error = res.error
    return ok


def _marcar_no_aptos(db: Session, universo: dict[str, Emisor]) -> None:
    for em in universo.values():
        if em.metodo == ce.METODO_NO_APTO and em.tipo_catalogo in TIPOS_CATALOGO_APTOS:
            fila = db.get(ClasificacionAuto, em.ticker_base)
            if fila is None:
                db.add(ClasificacionAuto(
                    ticker_base=em.ticker_base, tipo_catalogo=em.tipo_catalogo, estado="no_apto",
                    metodo_mapeo=ce.METODO_NO_APTO, intentos_fallidos=0,
                ))


def _purgar_snapshots(db: Session, simbolos: set[str]) -> None:
    for simbolo in simbolos:
        viejos = (
            db.query(FundamentalesSnapshot.id)
            .filter(FundamentalesSnapshot.simbolo_yahoo == simbolo)
            .order_by(FundamentalesSnapshot.fecha.desc())
            .offset(SNAPSHOTS_RETENIDOS)
            .all()
        )
        if viejos:
            db.query(FundamentalesSnapshot).filter(
                FundamentalesSnapshot.id.in_([v.id for v in viejos])
            ).delete(synchronize_session=False)


def _registrar(db: Session, **campos) -> None:
    fila = db.get(IngestaFundamentales, 1)
    if fila is None:
        fila = IngestaFundamentales(id=1)
        db.add(fila)
    fila.timestamp = datetime.utcnow()
    for nombre, valor in campos.items():
        setattr(fila, nombre, valor)


def cobertura(db: Session, universo: dict[str, Emisor] | None = None) -> dict:
    """Cuántos emisores aptos tienen datos. Para la banda de cobertura de la pantalla."""
    universo = universo if universo is not None else construir_universo(db)
    aptos = {b for b, em in universo.items() if em.metodo != ce.METODO_NO_APTO}
    estado = {f.ticker_base: f for f in db.query(ClasificacionAuto)}
    con_datos = sum(1 for b in aptos if b in estado and estado[b].estado == "ok")
    no_encontrados = sum(1 for b in aptos if b in estado and estado[b].estado == "no_encontrado")
    propios = {b for b in aptos if universo[b].propio}
    return {
        "aptos": len(aptos),
        "con_datos": con_datos,
        "no_encontrados": no_encontrados,
        "pendientes": len(aptos) - con_datos - no_encontrados,
        "propios": len(propios),
        "propios_con_datos": sum(1 for b in propios if b in estado and estado[b].estado == "ok"),
        "cobertura_pct": round(100.0 * con_datos / len(aptos), 1) if aptos else 0.0,
    }


def correr(
    db: Session,
    max_emisores: int | None = None,
    tickers: list[str] | None = None,
    pausa_seg: float | None = None,
) -> dict:
    """Una corrida de ingesta. Hace commit. Nunca lanza por red.

    `tickers`: sólo esos (locales o base, como mucho `MAX_TICKERS_SINCRONICO`), sin mirar frescura
    ni backoff. Es lo que usa el botón "Actualizar datos" de la ficha y el alta en watchlist.
    """
    if not use_external_apis():
        return {"resultado": "sin_fuentes", "procesados": 0, "ok": 0, "fallidos": 0}
    if not _lock_ingesta.acquire(blocking=False):
        return {"resultado": "en_curso", "procesados": 0, "ok": 0, "fallidos": 0}
    try:
        return _correr(db, max_emisores, tickers, pausa_seg)
    finally:
        _lock_ingesta.release()


def _correr(db, max_emisores, tickers, pausa_seg) -> dict:
    inicio = time.monotonic()
    hoy = date.today()
    tope = max_emisores if max_emisores is not None else _entero_env(
        "FUNDAMENTALES_MAX_POR_CORRIDA", MAX_POR_CORRIDA_DEFAULT, 1, 1000,
    )
    pausa = pausa_seg if pausa_seg is not None else _float_env("FUNDAMENTALES_PAUSA_SEG", PAUSA_DEFAULT_SEG)

    # -- 1. Lectura (corta) --
    universo = construir_universo(db)
    estado = {f.ticker_base: f for f in db.query(ClasificacionAuto)}
    solo = None
    if tickers:
        catalogo = cargar_catalogo()
        variantes = ce.mapa_variantes(catalogo, cargar_seed()["variantes"])
        solo = {ce.ticker_base(t, variantes) for t in tickers[:MAX_TICKERS_SINCRONICO]}
    cola = armar_cola(universo, estado, hoy, solo=solo)
    pendientes_total = len(cola)
    cola = cola[:tope]
    # Cierra la transacción de lectura: la parte de red puede tardar minutos.
    db.rollback()

    # -- 2. Red (sin lock). Incluye los tipos de cambio para pasar magnitudes a USD. --
    conversor = ConversorUSD(db)
    obtenidos: list[_Obtenido] = []
    rate_limited = False
    fallos_seguidos = 0
    for i, tarea in enumerate(cola):
        if i and pausa:
            time.sleep(pausa)
        res = yahoo.fetch_fundamentales(tarea.simbolo_yahoo)
        if res.estado == yahoo.ESTADO_RATE_LIMITED:
            rate_limited = True
            break
        obtenido = _Obtenido(tarea, res, None)
        if res.estado == yahoo.ESTADO_OK:
            obtenido.metricas, obtenido.market_cap_usd = enriquecer_usd(res.datos, conversor)
            serie = yahoo.fetch_cierres_semanales(tarea.simbolo_yahoo)
            if serie.estado == yahoo.ESTADO_RATE_LIMITED:
                rate_limited = True
                obtenidos.append(obtenido)
                break
            obtenido.serie = serie
        obtenidos.append(obtenido)
        fallos_seguidos = fallos_seguidos + 1 if res.estado == yahoo.ESTADO_ERROR else 0
        if fallos_seguidos >= FALLOS_SEGUIDOS_CORTE:
            logger.warning("fundamentales: %d errores seguidos, se corta la corrida", fallos_seguidos)
            break

    # -- 3. Escritura (un solo commit, con el lock del sync) --
    if not sync_lock.lock.acquire(timeout=LOCK_ESCRITURA_TIMEOUT_SEG):
        logger.warning("fundamentales: el sync no soltó el lock en %ds; se descarta la corrida",
                       LOCK_ESCRITURA_TIMEOUT_SEG)
        return {"resultado": "lock_ocupado", "procesados": len(obtenidos), "ok": 0, "fallidos": 0}
    db.rollback()  # la lectura del MEP abrió otra transacción
    try:
        ok = sum(1 for o in obtenidos if _aplicar(db, o, hoy))
        fallidos = len(obtenidos) - ok
        _marcar_no_aptos(db, universo)
        _purgar_snapshots(db, {o.tarea.simbolo_yahoo for o in obtenidos})
        db.flush()
        cob = cobertura(db, universo)
        duracion = int((time.monotonic() - inicio) * 1000)
        resultado = "rate_limited" if rate_limited else "ok"
        _registrar(
            db, duration_ms=duracion, procesados=len(obtenidos), ok=ok, fallidos=fallidos,
            rate_limited=1 if rate_limited else 0,
            pendientes=max(pendientes_total - len(obtenidos), 0), resultado=resultado,
            detalle={"cobertura": cob},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        sync_lock.lock.release()

    logger.info(
        "fundamentales: %d procesados (%d ok, %d fallidos)%s, cobertura %s%%, %d ms",
        len(obtenidos), ok, fallidos, ", cortado por límite de tasa" if rate_limited else "",
        cob["cobertura_pct"], duracion,
    )
    return {
        "resultado": resultado,
        "procesados": len(obtenidos),
        "ok": ok,
        "fallidos": fallidos,
        "pendientes": max(pendientes_total - len(obtenidos), 0),
        "cobertura": cob,
    }


def ultima_corrida(db: Session) -> dict | None:
    fila = db.get(IngestaFundamentales, 1)
    if fila is None:
        return None
    return {
        "timestamp": fila.timestamp,
        "duration_ms": fila.duration_ms,
        "procesados": fila.procesados,
        "ok": fila.ok,
        "fallidos": fila.fallidos,
        "rate_limited": bool(fila.rate_limited),
        "pendientes": fila.pendientes,
        "resultado": fila.resultado,
    }
