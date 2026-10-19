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


def adx(barras: list[Barra], periodo: int = 14) -> dict:
    """ADX de Wilder con sus dos líneas direccionales.

    `+DM`/`-DM` son el avance del máximo/mínimo respecto de la barra previa (sólo cuenta el mayor de
    los dos y si es positivo); `TR` es el mismo rango verdadero del ATR. Los tres se suavizan con el
    método de Wilder (`s = s - s/n + x`, semilla = suma de las primeras `n`), y de ahí
    `+DI = 100·sm(+DM)/sm(TR)`, `-DI` ídem, `DX = 100·|+DI − −DI| / (+DI + −DI)`. El `ADX` es el
    promedio Wilder del `DX` (semilla = media de los primeros `n`).

    `di_mas`/`di_menos` existen desde el índice `periodo`; `adx`, desde `2·periodo − 1`.
    """
    n = len(barras)
    adx_out: list[float | None] = [None] * n
    di_mas: list[float | None] = [None] * n
    di_menos: list[float | None] = [None] * n
    if periodo < 1 or n < periodo + 1:
        return {"adx": adx_out, "di_mas": di_mas, "di_menos": di_menos}

    tr = [0.0] * n
    dm_mas = [0.0] * n
    dm_menos = [0.0] * n
    for i in range(1, n):
        maximo, minimo = _hl(barras[i])
        max_prev, min_prev = _hl(barras[i - 1])
        cierre_prev = barras[i - 1].cierre
        tr[i] = max(maximo - minimo, abs(maximo - cierre_prev), abs(minimo - cierre_prev))
        arriba, abajo = maximo - max_prev, min_prev - minimo
        if arriba > abajo and arriba > 0:
            dm_mas[i] = arriba
        elif abajo > arriba and abajo > 0:
            dm_menos[i] = abajo

    s_tr = sum(tr[1:periodo + 1])
    s_mas = sum(dm_mas[1:periodo + 1])
    s_menos = sum(dm_menos[1:periodo + 1])
    dx: list[float | None] = [None] * n
    for i in range(periodo, n):
        if i > periodo:
            s_tr += tr[i] - s_tr / periodo
            s_mas += dm_mas[i] - s_mas / periodo
            s_menos += dm_menos[i] - s_menos / periodo
        mas = 100.0 * s_mas / s_tr if s_tr else 0.0
        menos = 100.0 * s_menos / s_tr if s_tr else 0.0
        di_mas[i], di_menos[i] = mas, menos
        dx[i] = 100.0 * abs(mas - menos) / (mas + menos) if (mas + menos) else 0.0

    primero = 2 * periodo - 1
    if n > primero:
        valor = sum(dx[periodo:primero + 1]) / periodo
        adx_out[primero] = valor
        for i in range(primero + 1, n):
            valor = (valor * (periodo - 1) + dx[i]) / periodo
            adx_out[i] = valor
    return {"adx": adx_out, "di_mas": di_mas, "di_menos": di_menos}


def supertrend(barras: list[Barra], periodo: int = 10, multiplicador: float = 3.0) -> dict:
    """SuperTrend: bandas `(máx+mín)/2 ± multiplicador·ATR` que sólo se acercan al precio (la
    superior no sube y la inferior no baja mientras el cierre no las cruce).

    - `direccion`: `+1.0` en tendencia alcista (la línea es la banda inferior, por debajo del
      precio) o `-1.0` en bajista (la banda superior). Cambia cuando el cierre cruza la banda.
    - `valor`: la banda activa.
    La dirección inicial (primera barra con ATR) sale de si el cierre está sobre o bajo el medio de
    la barra; como viene de `None`, no cuenta como cambio de tendencia para un `cruce`.
    """
    n = len(barras)
    valor: list[float | None] = [None] * n
    direccion: list[float | None] = [None] * n
    ranges = atr(barras, periodo)
    sup_final = inf_final = None
    tendencia = 0
    for i in range(n):
        a = ranges[i]
        if a is None:
            continue
        maximo, minimo = _hl(barras[i])
        medio = (maximo + minimo) / 2
        sup_basica, inf_basica = medio + multiplicador * a, medio - multiplicador * a
        cierre = barras[i].cierre
        if sup_final is None:
            sup_final, inf_final = sup_basica, inf_basica
            tendencia = 1 if cierre >= medio else -1
        else:
            cierre_prev = barras[i - 1].cierre
            sup_final = sup_basica if (sup_basica < sup_final or cierre_prev > sup_final) else sup_final
            inf_final = inf_basica if (inf_basica > inf_final or cierre_prev < inf_final) else inf_final
            if tendencia == -1 and cierre > sup_final:
                tendencia = 1
            elif tendencia == 1 and cierre < inf_final:
                tendencia = -1
        direccion[i] = float(tendencia)
        valor[i] = inf_final if tendencia == 1 else sup_final
    return {"valor": valor, "direccion": direccion}


def keltner(barras: list[Barra], periodo: int = 20, multiplicador: float = 2.0) -> dict:
    """Canal de Keltner: EMA del cierre ± `multiplicador`·ATR (ambos de `periodo` ruedas).
    Las tres salidas arrancan juntas, cuando el ATR ya tiene valor."""
    n = len(barras)
    media = ema([b.cierre for b in barras], periodo)
    rango = atr(barras, periodo)
    out_media: list[float | None] = [None] * n
    superior: list[float | None] = [None] * n
    inferior: list[float | None] = [None] * n
    for i in range(n):
        if media[i] is None or rango[i] is None:
            continue
        out_media[i] = media[i]
        superior[i] = media[i] + multiplicador * rango[i]
        inferior[i] = media[i] - multiplicador * rango[i]
    return {"media": out_media, "superior": superior, "inferior": inferior}


def ichimoku(barras: list[Barra], tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> dict:
    """Ichimoku sin la línea Chikou (que mira al futuro).

    - `tenkan`/`kijun`: punto medio del canal de máximos y mínimos de 9 / 26 ruedas.
    - `senkou_a`: promedio de las dos anteriores; `senkou_b`: punto medio del canal de `senkou`
      ruedas. Ambas se dibujan adelantadas `kijun` ruedas; acá se **alinean a la barra en la que
      aplican**: el valor de la barra `i` es el calculado en `i − kijun`. Así la nube que se ve
      sobre la barra de hoy sólo usa datos de hace `kijun` ruedas — nunca del futuro, y es lo que
      puede comparar una condición del DSL sin lookahead.
    """
    n = len(barras)
    t = extremos(barras, tenkan)["medio"]
    k = extremos(barras, kijun)["medio"]
    b_raw = extremos(barras, senkou)["medio"]
    a_raw = [(t[i] + k[i]) / 2 if t[i] is not None and k[i] is not None else None for i in range(n)]

    def desplazar(serie: list[float | None]) -> list[float | None]:
        return [None] * min(kijun, n) + serie[:max(0, n - kijun)]

    return {"tenkan": t, "kijun": k, "senkou_a": desplazar(a_raw), "senkou_b": desplazar(b_raw)}


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


def _fn_adx(barras, params):
    return adx(barras, int(params["periodo"]))


def _fn_supertrend(barras, params):
    return supertrend(barras, int(params["periodo"]), float(params["multiplicador"]))


def _fn_keltner(barras, params):
    return keltner(barras, int(params["periodo"]), float(params["multiplicador"]))


def _fn_ichimoku(barras, params):
    return ichimoku(barras, int(params["tenkan"]), int(params["kijun"]), int(params["senkou"]))


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
    "ADX": EspecIndicador(
        _fn_adx, {"periodo": 14}, ("adx", "di_mas", "di_menos"), lambda p: 2 * int(p["periodo"]),
    ),
    "SUPERTREND": EspecIndicador(
        _fn_supertrend, {"periodo": 10, "multiplicador": 3.0}, ("valor", "direccion"),
        lambda p: int(p["periodo"]) + 1, {"multiplicador": (0.5, 6.0)},
    ),
    "KELTNER": EspecIndicador(
        _fn_keltner, {"periodo": 20, "multiplicador": 2.0}, ("media", "superior", "inferior"),
        lambda p: int(p["periodo"]) + 1, {"multiplicador": (0.5, 6.0)},
    ),
    "ICHIMOKU": EspecIndicador(
        _fn_ichimoku, {"tenkan": 9, "kijun": 26, "senkou": 52},
        ("tenkan", "kijun", "senkou_a", "senkou_b"),
        lambda p: max(2 * int(p["kijun"]), int(p["senkou"]) + int(p["kijun"])),
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
