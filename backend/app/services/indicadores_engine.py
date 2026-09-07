"""Motor puro de indicadores técnicos (SMA, EMA, RSI, MACD, Bollinger, ATR, estocástico, OBV, ...).

Sin dependencias de `Session`/DB/red: todas las funciones reciben `Barra`s (o listas de cierres)
ya resueltas por `ohlcv_analytics` y devuelven listas planas. Testeable con pytest sin fixtures
de base de datos, estilo `risk_engine.py`.

**Invariante central**: toda función de indicador (y `calcular`) devuelve una lista — o un dict
de listas, para los multi-salida — de la MISMA longitud que la entrada, con `None` durante el
warm-up. Nunca trunca, nunca rellena con `0.0`. Esto es lo que hace trivial alinear indicadores,
señales y velas por índice posicional en el front y en `estrategia_engine`.

Supuestos:
- **Índice posicional por rueda**, no por día calendario: `SMA(50)` son 50 *ruedas*, no 50 días
  de calendario. Evita inventar precios en los feriados, que en el mercado argentino son muchos.
- **Wilder ≠ EMA**: RSI y ATR suavizan con `(prev*(n-1)+x)/n` (Wilder); MACD usa EMA `2/(n+1)`.
  Confundirlos cambia los números.
- **Bollinger con desvío poblacional** (ddof=0) — deliberadamente distinto del
  `statistics.stdev` (ddof=1) que usa `risk_engine`; es la definición canónica del indicador.
- **Degradación sin OHLC**: `_hl(barra)` cae a `(cierre, cierre)`. El ATR degenera en `|Δcierre|`
  suavizado y el estocástico en un %R sobre cierres — la degradación correcta, mucho mejor que
  devolver todo `None`.
- Bordes: `rsi` con `avg_loss==0` → `100.0`; con `avg_gain==0` (y `avg_loss>0`) → `0.0`. Serie
  más corta que el warm-up → todo `None`, nunca excepción.

Relaciones entre indicadores que conviene explicitar (como Wilder vs EMA):
- **`PERCENTIL` no es min-max**: usa rank real `100·#{j: cierre[j] < cierre[i]} / (W-1)`. El
  min-max sobre una ventana *es literalmente* `ESTOCASTICO(N,1,1).k`; el rank da 0 exacto en el
  mínimo, 100 en el máximo, es resistente a outliers y admite `ventana=0` (histórico acumulado).
- **`EXTREMOS.dist_max_pct` con `ventana=0` *es* el drawdown desde el máximo histórico**; con
  `ventana=252`, el drawdown de 52 semanas. No hay un indicador `DRAWDOWN` aparte: sería el mismo
  cálculo con otro nombre.
- **Alcance de "histórico" (`ventana=0`)**: es *desde el inicio de la serie cargada*, no desde el
  debut del instrumento. Su `warm_up` devuelve `_WARM_UP_HISTORICO` para que el caller pida toda
  la historia disponible. Consecuencia: con `ventana=0` la primera barra es máximo y mínimo a la
  vez (`dist_min_pct[0] == dist_max_pct[0] == 0`).
"""
from __future__ import annotations

import bisect
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

# Ruedas de warm-up a pedir cuando un indicador se calcula "desde el inicio" (`ventana=0`):
# cubre toda la historia que `estrategias_analytics` carga (`max_barras=3000`).
_WARM_UP_HISTORICO = 3000


@dataclass(frozen=True)
class Barra:
    fecha: date
    cierre: float
    apertura: float | None = None
    maximo: float | None = None
    minimo: float | None = None
    volumen: float | None = None


def _hl(barra: Barra) -> tuple[float, float]:
    """(máximo, mínimo) de la barra; sin OHLC, degrada a (cierre, cierre)."""
    if barra.maximo is not None and barra.minimo is not None:
        return barra.maximo, barra.minimo
    return barra.cierre, barra.cierre


# ─── Indicadores base ────────────────────────────────────────────────────────

def sma(valores: list[float | None], periodo: int) -> list[float | None]:
    n = len(valores)
    out: list[float | None] = [None] * n
    if periodo <= 0:
        return out
    for i in range(n):
        if i + 1 < periodo:
            continue
        ventana = valores[i + 1 - periodo:i + 1]
        if any(v is None for v in ventana):
            continue
        out[i] = sum(ventana) / periodo
    return out


def ema(valores: list[float | None], periodo: int) -> list[float | None]:
    """EMA con semilla = SMA de las primeras `periodo` observaciones válidas."""
    n = len(valores)
    out: list[float | None] = [None] * n
    if periodo <= 0:
        return out
    k = 2 / (periodo + 1)
    prev: float | None = None
    for i in range(n):
        if prev is None:
            if i + 1 < periodo:
                continue
            ventana = valores[i + 1 - periodo:i + 1]
            if any(v is None for v in ventana):
                continue
            prev = sum(ventana) / periodo
            out[i] = prev
            continue
        v = valores[i]
        if v is None:
            prev = None
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def _rsi_desde_promedios(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rsi(cierres: list[float], periodo: int = 14) -> list[float | None]:
    n = len(cierres)
    out: list[float | None] = [None] * n
    if periodo <= 0 or n < periodo + 1:
        return out

    ganancias = [0.0] * n
    perdidas = [0.0] * n
    for i in range(1, n):
        delta = cierres[i] - cierres[i - 1]
        ganancias[i] = max(delta, 0.0)
        perdidas[i] = max(-delta, 0.0)

    avg_gain = sum(ganancias[1:periodo + 1]) / periodo
    avg_loss = sum(perdidas[1:periodo + 1]) / periodo
    out[periodo] = _rsi_desde_promedios(avg_gain, avg_loss)

    for i in range(periodo + 1, n):
        avg_gain = (avg_gain * (periodo - 1) + ganancias[i]) / periodo
        avg_loss = (avg_loss * (periodo - 1) + perdidas[i]) / periodo
        out[i] = _rsi_desde_promedios(avg_gain, avg_loss)
    return out


def macd(cierres: list[float], rapida: int = 12, lenta: int = 26, senal: int = 9) -> dict:
    ema_rapida = ema(cierres, rapida)
    ema_lenta = ema(cierres, lenta)
    linea_macd = [
        (r - l) if r is not None and l is not None else None
        for r, l in zip(ema_rapida, ema_lenta)
    ]
    linea_senal = ema(linea_macd, senal)
    histograma = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(linea_macd, linea_senal)
    ]
    return {"macd": linea_macd, "senal": linea_senal, "histograma": histograma}


def bollinger(cierres: list[float], periodo: int = 20, desvios: float = 2.0) -> dict:
    n = len(cierres)
    media = sma(cierres, periodo)
    superior: list[float | None] = [None] * n
    inferior: list[float | None] = [None] * n
    ancho_pct: list[float | None] = [None] * n
    pctb: list[float | None] = [None] * n
    for i in range(n):
        if media[i] is None:
            continue
        ventana = cierres[i + 1 - periodo:i + 1]
        varianza = sum((v - media[i]) ** 2 for v in ventana) / periodo
        sigma = varianza ** 0.5
        sup = media[i] + desvios * sigma
        inf = media[i] - desvios * sigma
        superior[i] = sup
        inferior[i] = inf
        ancho_pct[i] = ((sup - inf) / media[i] * 100) if media[i] != 0 else None
        rango = sup - inf
        pctb[i] = ((cierres[i] - inf) / rango) if rango != 0 else None
    return {"media": media, "superior": superior, "inferior": inferior, "ancho_pct": ancho_pct, "pctb": pctb}


def atr(barras: list[Barra], periodo: int = 14) -> list[float | None]:
    n = len(barras)
    out: list[float | None] = [None] * n
    if n < periodo + 1:
        return out

    tr = [0.0] * n
    for i in range(1, n):
        maximo, minimo = _hl(barras[i])
        cierre_prev = barras[i - 1].cierre
        tr[i] = max(maximo - minimo, abs(maximo - cierre_prev), abs(minimo - cierre_prev))

    avg = sum(tr[1:periodo + 1]) / periodo
    out[periodo] = avg
    for i in range(periodo + 1, n):
        avg = (avg * (periodo - 1) + tr[i]) / periodo
        out[i] = avg
    return out


def estocastico(barras: list[Barra], periodo_k: int = 14, suavizado_k: int = 3, periodo_d: int = 3) -> dict:
    n = len(barras)
    k_crudo: list[float | None] = [None] * n
    for i in range(n):
        if i + 1 < periodo_k:
            continue
        ventana = barras[i + 1 - periodo_k:i + 1]
        maximos, minimos = zip(*(_hl(b) for b in ventana))
        hh, ll = max(maximos), min(minimos)
        rango = hh - ll
        k_crudo[i] = ((barras[i].cierre - ll) / rango * 100) if rango != 0 else 50.0
    k = sma(k_crudo, suavizado_k)
    d = sma(k, periodo_d)
    return {"k": k, "d": d}


def obv(barras: list[Barra]) -> list[float | None]:
    n = len(barras)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    if any(b.volumen is None for b in barras):
        return out
    acumulado = 0.0
    out[0] = 0.0
    for i in range(1, n):
        if barras[i].cierre > barras[i - 1].cierre:
            acumulado += barras[i].volumen
        elif barras[i].cierre < barras[i - 1].cierre:
            acumulado -= barras[i].volumen
        out[i] = acumulado
    return out


def volumen_promedio(barras: list[Barra], periodo: int = 20) -> list[float | None]:
    return sma([b.volumen for b in barras], periodo)


def extremos(barras: list[Barra], ventana: int = 20) -> dict:
    """Canal Donchian sobre `_hl()` **incluyendo la barra `i`** (sin lookahead: sólo mira hasta
    `i`). `ventana=0` = ventana expansiva desde el inicio de la serie (histórico acumulado).

    - `maximo`/`minimo`: extremos de la ventana; `medio = (maximo + minimo) / 2`.
    - `dist_max_pct = (cierre/maximo - 1)·100` (≤ 0, cero en máximo nuevo).
    - `dist_min_pct = (cierre/minimo - 1)·100` (≥ 0, cero en mínimo nuevo).
    - `dist_*_pct` es `None` si el denominador es 0.
    - Modo rodante (`ventana>0`): `None` hasta que la ventana está completa, como `sma`.
    """
    n = len(barras)
    maximo: list[float | None] = [None] * n
    minimo: list[float | None] = [None] * n
    medio: list[float | None] = [None] * n
    dist_max_pct: list[float | None] = [None] * n
    dist_min_pct: list[float | None] = [None] * n
    hl = [_hl(b) for b in barras]

    # Modo rodante: colas monótonas para O(N) (el naive O(N·W) se nota en `senales_recientes`,
    # que recorre todas las estrategias guardadas en cada carga de la watchlist).
    dq_hi: deque[int] = deque()   # índices, `hl[.][0]` decreciente
    dq_lo: deque[int] = deque()   # índices, `hl[.][1]` creciente
    run_hi: float | None = None
    run_lo: float | None = None
    for i in range(n):
        hi_i, lo_i = hl[i]
        if ventana <= 0:
            run_hi = hi_i if run_hi is None else max(run_hi, hi_i)
            run_lo = lo_i if run_lo is None else min(run_lo, lo_i)
            hi, lo = run_hi, run_lo
        else:
            while dq_hi and hl[dq_hi[-1]][0] <= hi_i:
                dq_hi.pop()
            dq_hi.append(i)
            while dq_lo and hl[dq_lo[-1]][1] >= lo_i:
                dq_lo.pop()
            dq_lo.append(i)
            if dq_hi[0] <= i - ventana:
                dq_hi.popleft()
            if dq_lo[0] <= i - ventana:
                dq_lo.popleft()
            if i + 1 < ventana:
                continue
            hi = hl[dq_hi[0]][0]
            lo = hl[dq_lo[0]][1]
        c = barras[i].cierre
        maximo[i] = hi
        minimo[i] = lo
        medio[i] = (hi + lo) / 2
        dist_max_pct[i] = (c / hi - 1) * 100 if hi != 0 else None
        dist_min_pct[i] = (c / lo - 1) * 100 if lo != 0 else None
    return {
        "maximo": maximo, "minimo": minimo, "medio": medio,
        "dist_max_pct": dist_max_pct, "dist_min_pct": dist_min_pct,
    }


def percentil(cierres: list[float], ventana: int = 100) -> list[float | None]:
    """Rank real del cierre dentro de la ventana: `100·#{j: cierre[j] < cierre[i]} / (W-1)`.

    0 exacto en el mínimo de la ventana, 100 en el máximo; los empates no cuentan como "menor".
    `ventana=0` = expansiva desde el inicio. Modo rodante: `None` hasta la ventana completa.
    Implementado con lista ordenada + `bisect` (O(N·logW)): el naive O(N·W) en modo expansivo
    sobre 3000 barras son ~9M comparaciones, y esto se recorre por cada estrategia guardada en
    cada carga de la watchlist.
    """
    n = len(cierres)
    out: list[float | None] = [None] * n
    ordenados: list[float] = []
    for i in range(n):
        c = cierres[i]
        bisect.insort(ordenados, c)
        if ventana > 0 and i >= ventana:
            del ordenados[bisect.bisect_left(ordenados, cierres[i - ventana])]
        w = len(ordenados)
        if ventana > 0 and w < ventana:
            continue
        if w <= 1:
            continue
        out[i] = 100.0 * bisect.bisect_left(ordenados, c) / (w - 1)
    return out


def retorno(cierres: list[float], periodo: int = 20) -> list[float | None]:
    """`(cierre[i]/cierre[i-periodo] - 1)·100`. `None` hasta la barra `periodo`, y si el
    denominador es 0. Serie más corta que el período → todo `None`."""
    n = len(cierres)
    out: list[float | None] = [None] * n
    if periodo <= 0:
        return out
    for i in range(periodo, n):
        base = cierres[i - periodo]
        if base == 0:
            continue
        out[i] = (cierres[i] / base - 1) * 100
    return out


# ─── Registro de indicadores ─────────────────────────────────────────────────

@dataclass(frozen=True)
class EspecIndicador:
    fn: Callable[[list[Barra], dict], dict[str, list]]
    params_default: dict = field(default_factory=dict)  # orden = orden posicional en `clave()`
    salidas: tuple[str, ...] = ("valor",)
    warm_up: Callable[[dict], int] = lambda p: 1
    # Rango declarativo por parámetro; el validador lo consulta antes de caer en su heurística
    # (float → 0.1..10, entero → 1..500). Permite p.ej. `ventana=0` en EXTREMOS/PERCENTIL.
    rangos: dict[str, tuple[float, float]] = field(default_factory=dict)


def _fn_sma(barras, params):
    return {"valor": sma([b.cierre for b in barras], int(params["periodo"]))}


def _fn_ema(barras, params):
    return {"valor": ema([b.cierre for b in barras], int(params["periodo"]))}


def _fn_rsi(barras, params):
    return {"valor": rsi([b.cierre for b in barras], int(params["periodo"]))}


def _fn_macd(barras, params):
    return macd([b.cierre for b in barras], int(params["rapida"]), int(params["lenta"]), int(params["senal"]))


def _fn_bollinger(barras, params):
    return bollinger([b.cierre for b in barras], int(params["periodo"]), float(params["desvios"]))


def _fn_atr(barras, params):
    return {"valor": atr(barras, int(params["periodo"]))}


def _fn_estocastico(barras, params):
    return estocastico(barras, int(params["periodo_k"]), int(params["suavizado_k"]), int(params["periodo_d"]))


def _fn_obv(barras, params):
    return {"valor": obv(barras)}


def _fn_volumen_promedio(barras, params):
    return {"valor": volumen_promedio(barras, int(params["periodo"]))}


def _fn_extremos(barras, params):
    return extremos(barras, int(params["ventana"]))


def _fn_percentil(barras, params):
    return {"valor": percentil([b.cierre for b in barras], int(params["ventana"]))}


def _fn_retorno(barras, params):
    return {"valor": retorno([b.cierre for b in barras], int(params["periodo"]))}


def _warm_up_ventana(p: dict) -> int:
    """`ventana` ruedas en modo rodante; toda la historia disponible con `ventana=0`."""
    return int(p["ventana"]) or _WARM_UP_HISTORICO


INDICADORES: dict[str, EspecIndicador] = {
    "SMA": EspecIndicador(_fn_sma, {"periodo": 50}, ("valor",), lambda p: int(p["periodo"])),
    "EMA": EspecIndicador(_fn_ema, {"periodo": 20}, ("valor",), lambda p: int(p["periodo"])),
    "RSI": EspecIndicador(_fn_rsi, {"periodo": 14}, ("valor",), lambda p: int(p["periodo"]) + 1),
    "MACD": EspecIndicador(
        _fn_macd, {"rapida": 12, "lenta": 26, "senal": 9}, ("macd", "senal", "histograma"),
        lambda p: int(p["lenta"]) + int(p["senal"]),
    ),
    "BOLLINGER": EspecIndicador(
        _fn_bollinger, {"periodo": 20, "desvios": 2.0}, ("media", "superior", "inferior", "ancho_pct", "pctb"),
        lambda p: int(p["periodo"]), {"desvios": (0.5, 4.0)},
    ),
    "ATR": EspecIndicador(_fn_atr, {"periodo": 14}, ("valor",), lambda p: int(p["periodo"]) + 1),
    "ESTOCASTICO": EspecIndicador(
        _fn_estocastico, {"periodo_k": 14, "suavizado_k": 3, "periodo_d": 3}, ("k", "d"),
        lambda p: int(p["periodo_k"]) + int(p["suavizado_k"]) + int(p["periodo_d"]),
    ),
    "OBV": EspecIndicador(_fn_obv, {}, ("valor",), lambda p: 1),
    "VOLUMEN_PROMEDIO": EspecIndicador(_fn_volumen_promedio, {"periodo": 20}, ("valor",), lambda p: int(p["periodo"])),
    "EXTREMOS": EspecIndicador(
        _fn_extremos, {"ventana": 20},
        ("maximo", "minimo", "medio", "dist_max_pct", "dist_min_pct"),
        _warm_up_ventana, {"ventana": (0, 500)},
    ),
    "PERCENTIL": EspecIndicador(
        _fn_percentil, {"ventana": 100}, ("valor",), _warm_up_ventana, {"ventana": (0, 500)},
    ),
    "RETORNO": EspecIndicador(
        _fn_retorno, {"periodo": 20}, ("valor",), lambda p: int(p["periodo"]) + 1,
    ),
}


def _resolver_params(nombre: str, params: dict | None) -> dict:
    espec = INDICADORES.get(nombre)
    if espec is None:
        raise ValueError(f"indicador desconocido: {nombre!r}")
    return {**espec.params_default, **(params or {})}


def calcular(nombre: str, barras: list[Barra], params: dict | None = None) -> dict[str, list]:
    espec = INDICADORES[nombre]
    return espec.fn(barras, _resolver_params(nombre, params))


def warm_up_barras(nombre: str, params: dict | None = None) -> int:
    espec = INDICADORES[nombre]
    return espec.warm_up(_resolver_params(nombre, params))


def _formato_param(valor) -> str:
    if isinstance(valor, float) and valor == int(valor):
        return str(int(valor))
    return str(valor)


def clave(nombre: str, params: dict | None = None) -> str:
    """`"SMA(50)"`, `"MACD(12,26,9)"` — contrato del query param del endpoint de serie técnica."""
    espec = INDICADORES.get(nombre)
    if espec is None:
        raise ValueError(f"indicador desconocido: {nombre!r}")
    resueltos = _resolver_params(nombre, params)
    if not espec.params_default:
        return nombre
    valores = ",".join(_formato_param(resueltos[k]) for k in espec.params_default)
    return f"{nombre}({valores})"


_CLAVE_RE = re.compile(r"^([A-Z_]+)(?:\(([^)]*)\))?$")


def parsear_clave(s: str) -> tuple[str, dict]:
    """Inversa de `clave()`. Lanza `ValueError` con mensaje en castellano ante cualquier formato inválido."""
    m = _CLAVE_RE.match((s or "").strip())
    if not m:
        raise ValueError(f"clave de indicador inválida: {s!r}")
    nombre, valores_raw = m.group(1), m.group(2)
    espec = INDICADORES.get(nombre)
    if espec is None:
        raise ValueError(f"indicador desconocido: {nombre!r}")

    nombres_params = list(espec.params_default.keys())
    partes = [p.strip() for p in valores_raw.split(",")] if valores_raw else []
    if len(partes) != len(nombres_params):
        raise ValueError(
            f"{nombre} espera {len(nombres_params)} parámetro(s) ({', '.join(nombres_params)}), "
            f"recibió {len(partes)}"
        )

    params: dict = {}
    for nombre_p, valor_str in zip(nombres_params, partes):
        default = espec.params_default[nombre_p]
        try:
            params[nombre_p] = float(valor_str) if isinstance(default, float) else int(valor_str)
        except ValueError:
            raise ValueError(f"parámetro inválido para {nombre}.{nombre_p}: {valor_str!r}")
    return nombre, params
