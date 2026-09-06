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
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable


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


# ─── Registro de indicadores ─────────────────────────────────────────────────

@dataclass(frozen=True)
class EspecIndicador:
    fn: Callable[[list[Barra], dict], dict[str, list]]
    params_default: dict = field(default_factory=dict)  # orden = orden posicional en `clave()`
    salidas: tuple[str, ...] = ("valor",)
    warm_up: Callable[[dict], int] = lambda p: 1


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
        lambda p: int(p["periodo"]),
    ),
    "ATR": EspecIndicador(_fn_atr, {"periodo": 14}, ("valor",), lambda p: int(p["periodo"]) + 1),
    "ESTOCASTICO": EspecIndicador(
        _fn_estocastico, {"periodo_k": 14, "suavizado_k": 3, "periodo_d": 3}, ("k", "d"),
        lambda p: int(p["periodo_k"]) + int(p["suavizado_k"]) + int(p["periodo_d"]),
    ),
    "OBV": EspecIndicador(_fn_obv, {}, ("valor",), lambda p: 1),
    "VOLUMEN_PROMEDIO": EspecIndicador(_fn_volumen_promedio, {"periodo": 20}, ("valor",), lambda p: int(p["periodo"])),
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
