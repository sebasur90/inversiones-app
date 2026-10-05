"""Expansión de estrategias sobre el universo de tickers, con tope.

Una estrategia guardada puede tener `ticker` fijo o `ticker IS NULL` (reusable: corre sobre
cualquier serie — es lo que hace posible el screener y es cómo se siembran los 16 presets del
catálogo). Decidir sobre qué series corre cada estrategia, y cortar antes de que el producto
estrategias × tickers se vaya de las manos, es la misma regla para el screener y para las
señales recientes, así que vive acá y no duplicada en los dos.

Antes estaba sólo en `screener_analytics` (privada), y `estrategias_analytics.senales_recientes`
resolvía el problema descartando las estrategias sin ticker — con lo cual, al sembrarse todos los
presets con `ticker=None`, el endpoint de señales devolvía siempre una lista vacía.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..database import EstrategiaTecnica
from . import estrategia_engine, indicadores_engine

MAX_BARRAS_CORTO = 750
MAX_BARRAS_LARGO = 3000

# Cota de pares (estrategia × ticker) por corrida: una estrategia reusable sobre un universo
# grande multiplica rápido. Por encima de esto se corta y se avisa, en vez de tardar minutos o
# agotar la caché de `cache_por_sync` (`MAX_ENTRADAS = 256`).
MAX_PARES = 400

ORIGENES_VALIDOS = ("todos", "cartera", "watchlist")


def requiere_historico(dsl: dict) -> bool:
    """`True` si algún indicador del DSL necesita toda la serie cargada (OBV, o EXTREMOS/PERCENTIL
    con `ventana=0`) — ahí hace falta pedir `MAX_BARRAS_LARGO`, no `MAX_BARRAS_CORTO`."""
    for item in dsl.get("indicadores", []) or []:
        tipo = item.get("tipo")
        if tipo == "OBV":
            return True
        if tipo in ("EXTREMOS", "PERCENTIL"):
            espec = indicadores_engine.INDICADORES.get(tipo)
            if espec is None:
                continue
            params = {**espec.params_default, **(item.get("params") or {})}
            if int(params.get("ventana", 0)) == 0:
                return True
    return False


def max_barras_para(dsl: dict) -> int:
    """Cuántas ruedas pedirle a `get_serie_barras` para este DSL."""
    return MAX_BARRAS_LARGO if requiere_historico(dsl) else MAX_BARRAS_CORTO


def ticker_aplica(origen_ticker: str, origen_filtro: str) -> bool:
    if origen_filtro == "todos":
        return True
    if origen_filtro == "cartera":
        return origen_ticker in ("cartera", "ambos")
    return origen_ticker in ("watchlist", "ambos")  # origen_filtro == "watchlist"


def armar_pares(
    estrategias: list[EstrategiaTecnica],
    universo: list[dict],
    origen: str = "todos",
    max_pares: int = MAX_PARES,
) -> tuple[list[tuple[EstrategiaTecnica, dict]], bool]:
    """Pares (estrategia, info de ticker) a evaluar, y si hubo que truncar.

    Una estrategia con `ticker` propio corre sólo en ese ticker (y se omite si quedó filtrado
    afuera del universo); una sin ticker corre en todo el universo que pasó el filtro.
    """
    tickers_por_nombre = {t["ticker"]: t for t in universo if ticker_aplica(t["origen"], origen)}
    pares: list[tuple[EstrategiaTecnica, dict]] = []
    for estrategia in estrategias:
        if estrategia.ticker is not None:
            info = tickers_por_nombre.get(estrategia.ticker)
            candidatos = [info] if info is not None else []
        else:
            candidatos = list(tickers_por_nombre.values())
        for info in candidatos:
            if len(pares) >= max_pares:
                return pares, True
            pares.append((estrategia, info))
    return pares, False


def estrategias_validas(
    db: Session, estrategia_ids: tuple[int, ...] = (),
) -> tuple[list[EstrategiaTecnica], bool]:
    """Estrategias guardadas cuyo DSL valida, y si se omitió alguna por inválida.

    `estrategia_ids` vacío = todas. Una definición inválida no debería frenar al resto: se
    descarta y quien llama lo reporta como advertencia.
    """
    todas = db.query(EstrategiaTecnica).order_by(EstrategiaTecnica.nombre).all()
    if estrategia_ids:
        ids = set(estrategia_ids)
        todas = [e for e in todas if e.id in ids]
    validas = [e for e in todas if not estrategia_engine.validar_estrategia(e.definicion)]
    return validas, len(validas) < len(todas)
