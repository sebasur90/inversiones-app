"""Motor puro de «Ciclos de mercado»: rotación relativa, rendimientos, riesgo, correlaciones y
descomposición de un país. Sin DB ni red: trabaja con series `[(fecha, cierre)]` ya cargadas.

**Rotación relativa (inspirada en los Relative Rotation Graphs, NO es la metodología propietaria JdK).**
Sobre cierres semanales alineados del grupo `P` y de su benchmark `B`, con ventana `n` (13 semanas):

    RS          = P / B
    RS_Ratio    = 100 · RS / EMA(RS, n)
    RS_Momentum = 100 · RS_Ratio / EMA(RS_Ratio, n)

100 es el punto neutral de los dos ejes. Con RS_Ratio ≥ 100 el grupo rinde en relación al benchmark
más que su propia media reciente; con RS_Momentum ≥ 100 esa fortaleza relativa está aumentando.

    Leading   = Ratio ≥ 100 y Momentum ≥ 100      Weakening = Ratio ≥ 100 y Momentum < 100
    Improving = Ratio < 100 y Momentum ≥ 100      Lagging   = Ratio < 100 y Momentum < 100

Reglas que evitan resultados engañosos:
- Las fechas se **intersectan**: sólo cuentan días en que operaron el grupo y el benchmark (un ETF
  y Bitcoin se comparan en los días hábiles de ambos). La barra semanal es el último día común de
  la semana ISO.
- Una semana sin ninguna fecha común es un **hueco** y la EMA no lo cruza: se usa el último tramo
  continuo. Nada se rellena ni se extrapola.
- Menos de `2·n + cola` semanas continuas: `datos_insuficientes`. Un último dato demasiado viejo:
  `desactualizado` y no se presenta ningún punto «actual».
- Un cambio de cuadrante es **confirmado** si se sostiene `confirmacion` semanas seguidas; si no,
  es transitorio.

Los rendimientos son de los cierres que se le pasan (ajustados por dividendos y splits cuando la
fuente los ajusta): de eso depende que sean de precio o totales, y lo informa el catálogo, no el motor.
"""
from __future__ import annotations

import calendar
import math
import statistics
from bisect import bisect_right
from datetime import date, timedelta

from . import contribucion_engine, correlaciones_engine, risk_engine
from . import indicadores_engine as ind

Serie = list[tuple[date, float]]

VERSION_ALGORITMO = "rrg-ema13-v1"
VENTANA_RRG = 13
COLA_DEFECTO = 8
CONFIRMACION_SEMANAS = 3
SMA_TENDENCIA_SEMANAS = 40
PENDIENTE_SEMANAS = 4
# Distancia máxima (días) a la que puede quedar un dato de la fecha pedida para usarse en un rendimiento.
TOLERANCIA_DIAS = 6
# Último dato más viejo que esto (días): se considera desactualizado.
DIAS_DESACTUALIZADO = 10
MIN_OBS_VOLATILIDAD_SEMANAL = 12
SEMANAS_POR_ANIO = 52
MAX_PUNTOS_TRAYECTORIA = 13
MAX_DESFASE_SEMANAS = 8

LEADING, WEAKENING, LAGGING, IMPROVING = "leading", "weakening", "lagging", "improving"
CUADRANTES = (LEADING, WEAKENING, LAGGING, IMPROVING)

ESTADO_OK = "ok"
ESTADO_INSUFICIENTE = "datos_insuficientes"
ESTADO_DESACTUALIZADO = "desactualizado"
ESTADO_SIN_DATOS = "sin_datos"
ESTADO_SIN_BENCHMARK = "sin_benchmark"

# Horizontes de rendimiento, en meses calendario.
HORIZONTES = {"1M": 1, "3M": 3, "6M": 6, "1A": 12, "3A": 36, "5A": 60, "10A": 120}
# Semanas que abarca la trayectoria según el período elegido en la pantalla.
SEMANAS_POR_PERIODO = {"3M": 13, "6M": 26, "1A": 52, "3A": 156}


# ---------------------------------------------------------------------------------------------
# Series y fechas
# ---------------------------------------------------------------------------------------------

def normalizar(serie) -> Serie:
    """Ordena por fecha, deja un solo dato por fecha (el último) y descarta valores no positivos o no finitos."""
    por_fecha: dict[date, float] = {}
    for fecha, valor in serie or ():
        if valor is not None and math.isfinite(valor) and valor > 0:
            por_fecha[fecha] = float(valor)
    return sorted(por_fecha.items())


def normalizar_nivel(serie) -> Serie:
    """Como `normalizar`, pero para series que son un **nivel** (una tasa en % anual): conserva el cero y los negativos.
    Descartarlos, como se hace con un precio, abriría huecos falsos justo cuando la tasa estuvo más baja."""
    por_fecha: dict[date, float] = {}
    for fecha, valor in serie or ():
        if valor is not None and math.isfinite(valor):
            por_fecha[fecha] = float(valor)
    return sorted(por_fecha.items())


def _idx_semana(d: date) -> int:
    """Número de semana ISO continuo: dos semanas consecutivas difieren en 1 (también entre años)."""
    return (d - timedelta(days=d.weekday())).toordinal() // 7


def restar_meses(d: date, meses: int) -> date:
    total = d.year * 12 + (d.month - 1) - meses
    anio, mes = divmod(total, 12)
    mes += 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def semana_cerrada(fecha: date, hoy: date) -> bool:
    """La barra semanal de `fecha` ya no puede cambiar: su semana terminó (o es fin de semana)."""
    s_fecha, s_hoy = _idx_semana(fecha), _idx_semana(hoy)
    return s_fecha < s_hoy or (s_fecha == s_hoy and hoy.weekday() >= 5)


def alinear(a: Serie, b: Serie) -> list[tuple[date, float, float]]:
    """Sólo las fechas en que hay dato de las dos series."""
    db = dict(b)
    return [(f, v, db[f]) for f, v in a if f in db]


def semanal_comun(a: Serie, b: Serie) -> list[tuple[date, float, float]]:
    """Cierres semanales alineados: el último día común de cada semana ISO."""
    out: dict[int, tuple[date, float, float]] = {}
    for fila in alinear(a, b):
        out[_idx_semana(fila[0])] = fila
    return [out[k] for k in sorted(out)]


def semanal(serie: Serie) -> Serie:
    """Último cierre de cada semana ISO de una sola serie."""
    out: dict[int, tuple[date, float]] = {}
    for f, v in serie:
        out[_idx_semana(f)] = (f, v)
    return [out[k] for k in sorted(out)]


def ultimo_tramo_continuo(filas: list[tuple]) -> tuple[list[tuple], int]:
    """El último tramo sin semanas faltantes (`fila[0]` es la fecha) y cuántas filas se descartaron antes."""
    if not filas:
        return [], 0
    inicio = len(filas) - 1
    while inicio > 0 and _idx_semana(filas[inicio][0]) - _idx_semana(filas[inicio - 1][0]) == 1:
        inicio -= 1
    return filas[inicio:], inicio


def cierre_en(fechas: list[date], cierres: list[float], objetivo: date, tolerancia: int = TOLERANCIA_DIAS) -> float | None:
    """Último cierre con fecha ≤ `objetivo`, si no está a más de `tolerancia` días. `None` si la serie empieza después."""
    i = bisect_right(fechas, objetivo) - 1
    if i < 0 or (objetivo - fechas[i]).days > tolerancia:
        return None
    return cierres[i]


# ---------------------------------------------------------------------------------------------
# Rotación relativa
# ---------------------------------------------------------------------------------------------

def cuadrante(rs_ratio: float, rs_momentum: float) -> str:
    # Se redondea para que un empate exacto en 100 no dependa del error de punto flotante.
    fuerte = round(rs_ratio, 9) >= 100
    creciente = round(rs_momentum, 9) >= 100
    if fuerte:
        return LEADING if creciente else WEAKENING
    return IMPROVING if creciente else LAGGING


def calcular_rrg(filas: list[tuple[date, float, float]], ventana: int = VENTANA_RRG) -> list[dict]:
    """RS-Ratio y RS-Momentum de cada semana en que ambos están definidos. `filas` = cierres semanales alineados continuos."""
    rs = [a / b for _, a, b in filas]
    ema_rs = ind.ema(rs, ventana)
    ratio = [100 * r / e if e else None for r, e in zip(rs, ema_rs)]
    ema_ratio = ind.ema(ratio, ventana)
    puntos = []
    for (fecha, _, _), x, e in zip(filas, ratio, ema_ratio):
        if x is None or not e:
            continue
        m = 100 * x / e
        puntos.append({"fecha": fecha, "rs_ratio": round(x, 6), "rs_momentum": round(m, 6), "cuadrante": cuadrante(x, m)})
    return puntos


def transiciones(puntos: list[dict], confirmacion: int = CONFIRMACION_SEMANAS) -> dict:
    """Cuándo pasó el grupo de un cuadrante a otro, distinguiendo lo confirmado de lo transitorio.

    Un tramo de `confirmacion` semanas seguidas o más en el mismo cuadrante está **confirmado**; uno más
    corto es **transitorio** y no interrumpe el cuadrante confirmado que lo rodea. El último tramo, si
    es corto y distinto del confirmado, queda como `pendiente` (todavía no se sabe).
    """
    runs: list[dict] = []
    for p in puntos:
        if runs and runs[-1]["cuadrante"] == p["cuadrante"]:
            runs[-1]["semanas"] += 1
            runs[-1]["hasta"] = p["fecha"]
        else:
            runs.append({"cuadrante": p["cuadrante"], "desde": p["fecha"], "hasta": p["fecha"], "semanas": 1})

    confirmados: list[dict] = []
    transitorios: list[dict] = []
    for i, r in enumerate(runs):
        if r["semanas"] >= confirmacion:
            if confirmados and confirmados[-1]["cuadrante"] == r["cuadrante"]:
                confirmados[-1]["hasta"] = r["hasta"]
                confirmados[-1]["semanas"] += r["semanas"]
            else:
                confirmados.append(dict(r))
        elif i < len(runs) - 1:
            transitorios.append({**r, "confirmado": False})

    cambios = []
    for i, c in enumerate(confirmados):
        cambios.append({
            "desde": c["desde"], "cuadrante": c["cuadrante"], "semanas": c["semanas"],
            "anterior": confirmados[i - 1]["cuadrante"] if i else None,
            "confirmado": True,
        })
    # Los transitorios sólo se informan si quedan dentro de la historia confirmada (no antes del primer tramo firme).
    primero = confirmados[0]["desde"] if confirmados else None
    transitorios = [t for t in transitorios if primero is not None and t["desde"] > primero]

    pendiente = None
    if runs and (not confirmados or runs[-1]["cuadrante"] != confirmados[-1]["cuadrante"]) and runs[-1]["semanas"] < confirmacion:
        pendiente = {**runs[-1], "confirmado": False}
    return {
        "confirmacion_semanas": confirmacion,
        "cambios_confirmados": cambios,
        "transitorios": transitorios,
        "pendiente": pendiente,
        "cuadrante_confirmado": confirmados[-1]["cuadrante"] if confirmados else None,
    }


def trayectoria(puntos: list[dict], semanas: int, max_puntos: int = MAX_PUNTOS_TRAYECTORIA) -> list[dict]:
    """Las últimas `semanas` del recorrido, con a lo sumo `max_puntos` puntos repartidos parejo (siempre incluye el último)."""
    cola = puntos[-semanas:] if semanas > 0 else []
    if len(cola) <= max_puntos:
        return list(cola)
    paso = (len(cola) - 1) / (max_puntos - 1)
    idx = sorted({round(i * paso) for i in range(max_puntos)})
    return [cola[i] for i in idx]


def rotacion(
    a: Serie, b: Serie, *, ventana: int = VENTANA_RRG, cola: int = COLA_DEFECTO,
    hoy: date | None = None, confirmacion: int = CONFIRMACION_SEMANAS,
) -> dict:
    """Estado de rotación de `a` contra `b`. Nunca lanza ni inventa: ante datos insuficientes lo dice."""
    a, b = normalizar(a), normalizar(b)
    base = {"estado": ESTADO_SIN_DATOS, "motivo": None, "ventana": ventana, "version": VERSION_ALGORITMO,
            "ultima_fecha": None, "semanas_usadas": 0, "actual": None, "puntos": [], "transiciones": None}
    if not a:
        return {**base, "motivo": "el grupo no tiene datos"}
    if not b:
        return {**base, "estado": ESTADO_SIN_BENCHMARK, "motivo": "el benchmark no tiene datos"}

    semanal_ab = semanal_comun(a, b)
    if not semanal_ab:
        return {**base, "estado": ESTADO_INSUFICIENTE, "motivo": "el grupo y el benchmark no comparten fechas"}
    tramo, descartadas = ultimo_tramo_continuo(semanal_ab)
    ultima = tramo[-1][0]
    base.update(ultima_fecha=ultima, semanas_usadas=len(tramo))

    minimo = 2 * ventana + cola
    if len(tramo) < minimo:
        motivo = f"hacen falta {minimo} semanas continuas en común y hay {len(tramo)}"
        if descartadas:
            motivo += f" (se descartaron {descartadas} anteriores a una semana sin datos)"
        return {**base, "estado": ESTADO_INSUFICIENTE, "motivo": motivo}

    puntos = calcular_rrg(tramo, ventana)
    out = {**base, "puntos": puntos, "transiciones": transiciones(puntos, confirmacion)}
    referencia = hoy or max(a[-1][0], b[-1][0])
    if (referencia - ultima).days > DIAS_DESACTUALIZADO:
        return {**out, "estado": ESTADO_DESACTUALIZADO,
                "motivo": f"el último dato en común es del {ultima.isoformat()}"}
    return {**out, "estado": ESTADO_OK, "actual": puntos[-1]}


# ---------------------------------------------------------------------------------------------
# Rendimientos
# ---------------------------------------------------------------------------------------------

def _arrays(serie: Serie) -> tuple[list[date], list[float]]:
    return [f for f, _ in serie], [v for _, v in serie]


def retorno_entre(serie: Serie, desde: date, hasta: date, tolerancia: int = TOLERANCIA_DIAS) -> tuple[float | None, str | None]:
    """`(retorno, motivo)` entre dos fechas objetivo. `None` si la serie no llega hasta `desde` o no tiene dato cerca."""
    if not serie:
        return None, "sin datos"
    fechas, cierres = _arrays(serie)
    if fechas[0] > desde:
        return None, "sin datos suficientes"
    c0 = cierre_en(fechas, cierres, desde, tolerancia)
    c1 = cierre_en(fechas, cierres, hasta, tolerancia)
    if c0 is None or c1 is None:
        return None, "sin dato cerca de la fecha"
    return c1 / c0 - 1.0, None


def rendimientos(a: Serie, b: Serie | None, hasta: date, horizontes: dict[str, int] | None = None) -> dict[str, dict]:
    """Rendimiento absoluto y relativo al benchmark por horizonte, con las mismas dos fechas objetivo para los dos.

    Si no hay historia suficiente el valor es `None` con `motivo`: no se acorta el período ni se estima.
    El anualizado se da desde un año en adelante.
    """
    a = normalizar(a)
    b = normalizar(b) if b is not None else None
    out: dict[str, dict] = {}
    for nombre, meses in (horizontes or HORIZONTES).items():
        desde = restar_meses(hasta, meses)
        ra, motivo = retorno_entre(a, desde, hasta)
        rb = retorno_entre(b, desde, hasta)[0] if b else None
        relativo = (1 + ra) / (1 + rb) - 1 if ra is not None and rb is not None else None
        anualizado = None
        if ra is not None and meses >= 12:
            anualizado = (1 + ra) ** (365.0 / (hasta - desde).days) - 1
        out[nombre] = {"absoluto": ra, "relativo": relativo, "anualizado": anualizado,
                       "desde": desde, "hasta": hasta, "motivo": motivo}
    return out


def horizontes_con_cobertura(tablas: list[dict[str, dict]]) -> list[str]:
    """Horizontes que alguna de las tablas cubre (para no mostrar columnas 5A/10A vacías)."""
    return [h for h in HORIZONTES if any(t.get(h, {}).get("absoluto") is not None for t in tablas)]


# ---------------------------------------------------------------------------------------------
# Riesgo y tendencia
# ---------------------------------------------------------------------------------------------

def retornos_semanales(semanal_serie: Serie) -> list[float]:
    """Retornos entre semanas consecutivas; si falta una semana no se encadena a través del hueco."""
    out = []
    for (f0, c0), (f1, c1) in zip(semanal_serie, semanal_serie[1:]):
        if _idx_semana(f1) - _idx_semana(f0) == 1:
            out.append(c1 / c0 - 1.0)
    return out


def volatilidad_anualizada(retornos: list[float], periodos_por_anio: int = SEMANAS_POR_ANIO) -> dict:
    n = len(retornos)
    if n < MIN_OBS_VOLATILIDAD_SEMANAL:
        return {"estado": ESTADO_INSUFICIENTE, "anualizada": None, "n_obs": n}
    return {"estado": ESTADO_OK, "anualizada": statistics.stdev(retornos) * math.sqrt(periodos_por_anio), "n_obs": n}


def drawdown(semanal_serie: Serie) -> dict:
    """Máxima caída desde un pico, caída actual y semanas que tardó en recuperar el pico (o `None` si no lo hizo)."""
    res = risk_engine.calcular_drawdown(semanal_serie)
    if res["estado"] != "ok":
        return {"estado": ESTADO_INSUFICIENTE, "maximo": None, "actual": None, "fecha_pico": None,
                "fecha_valle": None, "recuperacion_semanas": None, "en_recuperacion": None}
    recuperacion = None
    if res["maximo"] < 0:
        valor_pico = next(v for f, v in semanal_serie if f == res["fecha_pico"])
        for f, v in semanal_serie:
            if f > res["fecha_valle"] and v >= valor_pico:
                recuperacion = (f - res["fecha_valle"]).days // 7
                break
    return {"estado": ESTADO_OK, "maximo": res["maximo"], "actual": res["actual"], "fecha_pico": res["fecha_pico"],
            "fecha_valle": res["fecha_valle"], "recuperacion_semanas": recuperacion,
            "en_recuperacion": res["en_recuperacion"]}


def tendencia(semanal_serie: Serie, periodo: int = SMA_TENDENCIA_SEMANAS) -> dict:
    """Distancia del último cierre a su media de `periodo` semanas y pendiente de esa media en 4 semanas."""
    cierres = [c for _, c in semanal_serie]
    sma = ind.sma(cierres, periodo)
    if not sma or sma[-1] is None:
        return {"estado": ESTADO_INSUFICIENTE, "periodo_semanas": periodo, "distancia": None, "pendiente": None}
    previa = sma[-1 - PENDIENTE_SEMANAS] if len(sma) > PENDIENTE_SEMANAS else None
    return {"estado": ESTADO_OK, "periodo_semanas": periodo, "distancia": cierres[-1] / sma[-1] - 1.0,
            "pendiente": sma[-1] / previa - 1.0 if previa else None}


def ventana_semanal(serie: Serie, desde: date | None, hasta: date | None) -> Serie:
    return [(f, c) for f, c in semanal(serie) if (desde is None or f >= desde) and (hasta is None or f <= hasta)]


def riesgo(serie: Serie, desde: date | None = None, hasta: date | None = None) -> dict:
    """Volatilidad anualizada y drawdown de la serie semanal dentro de la ventana."""
    sem = ventana_semanal(normalizar(serie), desde, hasta)
    return {"volatilidad": volatilidad_anualizada(retornos_semanales(sem)), "drawdown": drawdown(sem),
            "semanas": len(sem)}


def analizar(
    a: Serie, b: Serie | None, hasta: date, *, ventana: int = VENTANA_RRG, cola: int = COLA_DEFECTO,
    hoy: date | None = None, meses_riesgo: int = 36,
) -> dict:
    """Todo lo que se muestra de un grupo: rotación, rendimientos, riesgo y tendencia. Cada pieza con su propio estado."""
    a = normalizar(a)
    return {
        "ultima_fecha": a[-1][0] if a else None,
        "rotacion": rotacion(a, b or [], ventana=ventana, cola=cola, hoy=hoy),
        "rendimientos": rendimientos(a, b, hasta),
        "riesgo": riesgo(a, restar_meses(hasta, meses_riesgo), hasta),
        "tendencia": tendencia(semanal(a)),
    }


# ---------------------------------------------------------------------------------------------
# Series normalizadas y comparación
# ---------------------------------------------------------------------------------------------

def base_100(series: dict[str, Serie], desde: date | None = None, hasta: date | None = None, paso: str = "D") -> dict:
    """Series rebasadas a 100 en la primera fecha en que **todas** tienen dato (intersección: nada se rellena).

    `paso="S"` toma el último día común de cada semana (para rangos largos).
    """
    norm = {k: normalizar(v) for k, v in series.items()}
    if not norm or any(not v for v in norm.values()):
        return {"fecha_base": None, "filas": []}
    comunes = set.intersection(*(set(f for f, _ in v) for v in norm.values()))
    fechas = sorted(f for f in comunes if (desde is None or f >= desde) and (hasta is None or f <= hasta))
    if paso == "S":
        ult: dict[int, date] = {}
        for f in fechas:
            ult[_idx_semana(f)] = f
        fechas = [ult[k] for k in sorted(ult)]
    if not fechas:
        return {"fecha_base": None, "filas": []}
    mapas = {k: dict(v) for k, v in norm.items()}
    base_ = {k: mapas[k][fechas[0]] for k in mapas}
    filas = [{"fecha": f, **{k: 100.0 * (mapas[k][f] / base_[k]) for k in mapas}} for f in fechas]   # (v/base) = 1 exacto en la base
    return {"fecha_base": fechas[0], "filas": filas}


def comparar(series: dict[str, Serie], desde: date, hasta: date) -> dict:
    """Rendimiento, volatilidad, drawdown y recuperación de varios grupos **sobre el mismo período**.

    Si alguno empieza después de `desde`, el período de todos se acorta a la fecha en que arranca el
    último (y `periodo_ajustado` lo avisa): comparar ventanas distintas no es comparar.
    """
    norm = {k: normalizar(v) for k, v in series.items()}
    con_datos = {k: v for k, v in norm.items() if v}
    if not con_datos:
        return {"desde": desde, "hasta": hasta, "periodo_ajustado": False, "grupos": {}}
    inicio = max(desde, max(v[0][0] for v in con_datos.values()))
    out = {}
    for k, v in con_datos.items():
        r, motivo = retorno_entre(v, inicio, hasta)
        out[k] = {"retorno": r, "motivo": motivo, **riesgo(v, inicio, hasta)}
    # Las series sin datos quedan visibles, no se descartan en silencio.
    for k in norm:
        out.setdefault(k, {"retorno": None, "motivo": "sin datos", "volatilidad": None, "drawdown": None, "semanas": 0})
    return {"desde": inicio, "hasta": hasta, "periodo_ajustado": inicio > desde, "grupos": out}


# ---------------------------------------------------------------------------------------------
# Correlaciones
# ---------------------------------------------------------------------------------------------

def grilla_semanal(desde: date, hasta: date) -> list[date]:
    """Los viernes entre `desde` y `hasta`."""
    d = desde + timedelta(days=(4 - desde.weekday()) % 7)
    out = []
    while d <= hasta:
        out.append(d)
        d += timedelta(days=7)
    return out


def retornos_en_grilla(serie: Serie, grilla: list[date], tolerancia: int) -> dict[date, float]:
    """Retorno entre cada par de fechas consecutivas de la grilla, a partir del último cierre ≤ la fecha
    (a lo sumo `tolerancia` días antes). Si falta alguno de los dos extremos, ese período no existe: no se
    encadena a través del hueco ni se completa."""
    fechas, cierres = _arrays(serie)
    out: dict[date, float] = {}
    previo = None
    for g in grilla:
        c = cierre_en(fechas, cierres, g, tolerancia) if fechas else None
        if c is not None and previo is not None:
            out[g] = c / previo - 1.0
        previo = c
    return out


def cambios_en_grilla(serie: Serie, grilla: list[date], tolerancia: int) -> dict[date, float]:
    """Como `retornos_en_grilla`, pero la **diferencia** entre fechas consecutivas (puntos porcentuales de una tasa).
    Un rendimiento sobre una tasa no tiene sentido (pasar de 0,1 % a 0,2 % no es «+100 %»)."""
    fechas, cierres = _arrays(serie)
    out: dict[date, float] = {}
    previo = None
    for g in grilla:
        c = cierre_en(fechas, cierres, g, tolerancia) if fechas else None
        if c is not None and previo is not None:
            out[g] = c - previo
        previo = c
    return out


def matriz_correlacion(
    series: dict[str, Serie], desde: date, hasta: date, frecuencia: str = "semanal",
    grilla_diaria: list[date] | None = None,
) -> dict:
    """Pearson entre los retornos de cada par, medidos sobre las **mismas fechas** (una grilla común).

    Semanal: viernes (un dato cuenta si es de a lo sumo 3 días antes). Diaria: los días de `grilla_diaria`
    (p. ej. las ruedas del benchmark), con el dato exacto de ese día. Informa la cantidad de observaciones
    y el período efectivo de cada par. Es correlación, no causalidad.
    """
    if frecuencia == "diaria":
        grilla = [g for g in (grilla_diaria or []) if desde <= g <= hasta]
        tolerancia = 0
    else:
        grilla = grilla_semanal(desde, hasta)
        tolerancia = 3
    ids = list(series)
    rets = {k: retornos_en_grilla(normalizar(series[k]), grilla, tolerancia) for k in ids}
    res = correlaciones_engine.construir_matriz(
        ids, rets, correlaciones_engine.MIN_OBS_POR_FRECUENCIA["diaria" if frecuencia == "diaria" else "semanal"],
        max(len(grilla) - 1, 0),
    )
    fechas = sorted({f for r in rets.values() for f in r})
    return {**res, "ids": ids, "frecuencia": frecuencia, "n_periodos": max(len(grilla) - 1, 0),
            "periodo": {"desde": fechas[0] if fechas else None, "hasta": fechas[-1] if fechas else None}}


def desfases(
    a: Serie, b: Serie, desde: date, hasta: date, max_semanas: int = MAX_DESFASE_SEMANAS,
    nivel_a: bool = False, nivel_b: bool = False,
) -> dict:
    """Correlación entre el retorno semanal de `a` en la semana t y el de `b` en la semana t+k, para k entre
    −max y +max. **k > 0 significa que `a` va primero.** Son hipótesis estadísticas, no predicciones.

    `nivel_a` / `nivel_b`: la serie es una tasa (un nivel en %), así que en lugar del retorno se usa su cambio semanal
    en puntos porcentuales.

    Con 2·max+1 desfases probados es normal que alguno supere la banda por azar (la banda es ±1,96/√n:
    cubre 95 % de un solo desfase, no de todos).
    """
    grilla = grilla_semanal(desde, hasta)
    def _semanal(serie: Serie, nivel: bool) -> dict[int, float]:
        medidas = cambios_en_grilla(normalizar_nivel(serie), grilla, 3) if nivel else retornos_en_grilla(normalizar(serie), grilla, 3)
        return {_idx_semana(f): v for f, v in medidas.items()}

    ra, rb = _semanal(a, nivel_a), _semanal(b, nivel_b)
    filas = []
    for k in range(-max_semanas, max_semanas + 1):
        rb_desplazado = {t - k: v for t, v in rb.items()}
        res = contribucion_engine.calcular_correlacion_par(ra, rb_desplazado, correlaciones_engine.MIN_OBS_POR_FRECUENCIA["semanal"])
        filas.append({"desfase_semanas": k, "valor": res["valor"], "n_obs": res["n_obs"], "estado": res["estado"]})
    n0 = next((f["n_obs"] for f in filas if f["desfase_semanas"] == 0), 0)
    banda = 1.96 / math.sqrt(n0) if n0 > 0 else None
    for f in filas:
        f["supera_azar"] = bool(banda is not None and f["valor"] is not None and abs(f["valor"]) > banda)
    validas = [f for f in filas if f["valor"] is not None]
    mejor = max(validas, key=lambda f: abs(f["valor"])) if validas else None
    return {"desfases": filas, "banda_azar": banda, "mejor": mejor, "max_semanas": max_semanas}


# ---------------------------------------------------------------------------------------------
# Sintético y país
# ---------------------------------------------------------------------------------------------

def sintetico_equiponderado(series: list[Serie]) -> Serie:
    """Índice base 100 que encadena el promedio simple de los retornos semanales de los miembros.

    Sólo existe en las semanas en que **todos** los miembros tienen dato; el retorno entre dos semanas
    disponibles se mide sobre ese mismo tramo para todos. Una semana en que falta alguno no aparece (hueco):
    no se rellena. El hueco lo detectan después la rotación y los retornos por semanas.
    """
    semanales = [dict((_idx_semana(f), (f, c)) for f, c in semanal(normalizar(s))) for s in series]
    if not semanales or any(not s for s in semanales):
        return []
    comunes = sorted(set.intersection(*(set(s) for s in semanales)))
    if not comunes:
        return []
    nivel = 100.0
    out: Serie = [(max(s[comunes[0]][0] for s in semanales), nivel)]
    for previa, actual in zip(comunes, comunes[1:]):
        nivel *= 1 + statistics.fmean(s[actual][1] / s[previa][1] - 1.0 for s in semanales)
        out.append((max(s[actual][0] for s in semanales), nivel))
    return out


def efecto_cambiario(retorno_fx: float, cotizacion: str) -> float:
    """Efecto sobre el rendimiento en USD de un activo local, dado el cambio del tipo de cambio.

    `local_por_usd` (BRL=X: pesos por dólar): si sube, la moneda local se deprecia y resta. `usd_por_local`
    (EURUSD=X) o un tipo de cambio de la forma contraria suma.
    """
    return 1 / (1 + retorno_fx) - 1 if cotizacion in ("local_por_usd", "mep") else retorno_fx


def descomponer_pais(
    proxy: Serie, indice_local: Serie | None, fx: Serie | None, cotizacion: str | None,
    desde: date, hasta: date,
) -> dict:
    """Separa, sobre las mismas dos fechas, tres cosas que **no son equivalentes**:

    1. `proxy_usd`: rendimiento del ETF del país en dólares (incluye distribuciones, gastos y composición propios).
    2. `indice_local`: rendimiento del índice local en su moneda (de precio).
    3. `efecto_fx`: lo que el tipo de cambio le suma o resta a un inversor en dólares.

    Con eso: `indice_local_usd = (1 + local)·(1 + efecto_fx) − 1` y `diferencia_vehiculo = proxy_usd −
    indice_local_usd`. Cualquier pieza sin dato cercano a las fechas queda en `None` con su motivo; no se estima.
    """
    proxy = normalizar(proxy)
    out = {"desde": desde, "hasta": hasta, "proxy_usd": None, "indice_local": None, "efecto_fx": None,
           "indice_local_usd": None, "diferencia_vehiculo": None, "motivos": {}, "completa": False}

    def _pieza(nombre, serie):
        serie = normalizar(serie) if serie else []
        r, motivo = retorno_entre(serie, desde, hasta)
        if r is None and serie and (hasta - serie[-1][0]).days > TOLERANCIA_DIAS:
            motivo = f"el último dato es del {serie[-1][0].isoformat()}"
        if motivo:
            out["motivos"][nombre] = motivo
        return r

    out["proxy_usd"] = _pieza("proxy_usd", proxy)
    out["indice_local"] = _pieza("indice_local", indice_local) if indice_local else None
    if not indice_local:
        out["motivos"]["indice_local"] = "no hay índice local de referencia" if indice_local is None else "el índice local no tiene datos"
    r_fx = _pieza("efecto_fx", fx) if fx else None
    if not fx:
        out["motivos"]["efecto_fx"] = "no hay tipo de cambio de referencia" if fx is None else "el tipo de cambio no tiene datos"
    if r_fx is not None and cotizacion:
        out["efecto_fx"] = efecto_cambiario(r_fx, cotizacion)
    if out["indice_local"] is not None and out["efecto_fx"] is not None:
        out["indice_local_usd"] = (1 + out["indice_local"]) * (1 + out["efecto_fx"]) - 1
        if out["proxy_usd"] is not None:
            out["diferencia_vehiculo"] = out["proxy_usd"] - out["indice_local_usd"]
            out["completa"] = True
    return out
