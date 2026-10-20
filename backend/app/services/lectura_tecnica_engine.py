"""Motor puro de la "lectura" del gráfico: tendencia, momentum, niveles cercanos y fuerza relativa,
cada uno como un estado con nombre más los números que lo deciden.

Sin DB ni red. Siempre sobre barras **diarias** (la misma serie con la que corren estrategias y
alertas), sin importar el período o el intervalo que el gráfico esté mostrando.

Las reglas son simples y fijas a propósito: la pantalla muestra el número junto al estado para que
se pueda verificar a ojo, y no un puntaje que haya que creerle.

- **Tendencia**, contra la SMA(50): *alcista* si el cierre está arriba de la media y la media está
  más alta que hace `RUEDAS_PENDIENTE` ruedas; *bajista* si las dos cosas van al revés; *mixta* si
  no coinciden (el precio cruzó la media pero la media todavía no giró, o viceversa).
- **Momentum**, RSI(14): *sobrecompra* arriba de 70, *sobreventa* abajo de 30, *neutral* entre medio.
- **Niveles**: entre los soportes y resistencias automáticos de las últimas `VENTANA_NIVELES`
  ruedas, el soporte más alto debajo del cierre y la resistencia más baja encima.
- **Fuerza relativa**: retorno del activo en las últimas `RUEDAS_FUERZA` ruedas menos el del
  índice, en puntos porcentuales. *Mejor* o *peor* si la diferencia pasa `UMBRAL_FUERZA_PUNTOS`;
  *parecida* si no.
"""
from __future__ import annotations

from . import indicadores_engine as ind
from . import niveles_auto_engine

PERIODO_SMA = 50
RUEDAS_PENDIENTE = 10
PERIODO_RSI = 14
RSI_SOBRECOMPRA = 70.0
RSI_SOBREVENTA = 30.0
VENTANA_NIVELES = 250
RUEDAS_FUERZA = 63
UMBRAL_FUERZA_PUNTOS = 1.0

# Lo que hay que leer para que todas las partes tengan con qué calcularse.
BARRAS_NECESARIAS = max(VENTANA_NIVELES, PERIODO_SMA + RUEDAS_PENDIENTE, RUEDAS_FUERZA + 1)


def _pct(a: float, b: float) -> float:
    return (a / b - 1.0) * 100.0


def tendencia(cierres: list[float]) -> dict | None:
    """`None` si no hay `PERIODO_SMA + RUEDAS_PENDIENTE` ruedas: sin media no hay tendencia."""
    if len(cierres) < PERIODO_SMA + RUEDAS_PENDIENTE:
        return None
    media = ind.sma(cierres, PERIODO_SMA)
    actual, previa = media[-1], media[-1 - RUEDAS_PENDIENTE]
    if actual is None or previa is None or actual <= 0 or previa <= 0:
        return None
    cierre = cierres[-1]
    if cierre > actual and actual > previa:
        estado = "alcista"
    elif cierre < actual and actual < previa:
        estado = "bajista"
    else:
        estado = "mixta"
    return {
        "estado": estado, "sma": actual, "periodo_sma": PERIODO_SMA,
        "distancia_pct": _pct(cierre, actual), "pendiente_pct": _pct(actual, previa),
        "ruedas_pendiente": RUEDAS_PENDIENTE,
    }


def momentum(cierres: list[float]) -> dict | None:
    valores = ind.rsi(cierres, PERIODO_RSI)
    if not valores or valores[-1] is None:
        return None
    rsi = valores[-1]
    if rsi > RSI_SOBRECOMPRA:
        estado = "sobrecompra"
    elif rsi < RSI_SOBREVENTA:
        estado = "sobreventa"
    else:
        estado = "neutral"
    return {"estado": estado, "rsi": rsi, "periodo_rsi": PERIODO_RSI}


def niveles_cercanos(barras: list[ind.Barra]) -> tuple[dict | None, dict | None]:
    """`(soporte, resistencia)` más cercanos al último cierre; cualquiera puede faltar."""
    if not barras:
        return None, None
    cierre = barras[-1].cierre
    niveles = niveles_auto_engine.niveles_automaticos(barras[-VENTANA_NIVELES:])

    def salida(n: dict) -> dict:
        return {
            "precio": n["precio"], "toques": n["toques"], "ultima_fecha": n["ultima_fecha"],
            "distancia_pct": _pct(n["precio"], cierre),
        }

    soportes = [n for n in niveles if n["tipo"] == "soporte"]
    resistencias = [n for n in niveles if n["tipo"] == "resistencia"]
    soporte = max(soportes, key=lambda n: n["precio"]) if soportes else None
    resistencia = min(resistencias, key=lambda n: n["precio"]) if resistencias else None
    return (salida(soporte) if soporte else None, salida(resistencia) if resistencia else None)


def fuerza_relativa(cierres: list[float], cierres_bench: list[float | None]) -> dict | None:
    """`cierres_bench` alineado barra a barra con `cierres` (ver `fuerza_relativa_engine`).
    `None` si falta el índice en cualquiera de las dos puntas de la ventana."""
    if len(cierres) <= RUEDAS_FUERZA or len(cierres_bench) != len(cierres):
        return None
    inicio = -1 - RUEDAS_FUERZA
    a0, a1 = cierres[inicio], cierres[-1]
    b0, b1 = cierres_bench[inicio], cierres_bench[-1]
    if not a0 or not a1 or not b0 or not b1 or a0 <= 0 or b0 <= 0:
        return None
    retorno, retorno_bench = _pct(a1, a0), _pct(b1, b0)
    diferencia = retorno - retorno_bench
    if diferencia > UMBRAL_FUERZA_PUNTOS:
        estado = "mejor"
    elif diferencia < -UMBRAL_FUERZA_PUNTOS:
        estado = "peor"
    else:
        estado = "parecida"
    return {
        "estado": estado, "retorno_pct": retorno, "retorno_benchmark_pct": retorno_bench,
        "diferencia_puntos": diferencia, "ruedas": RUEDAS_FUERZA,
    }


def leer(barras: list[ind.Barra], cierres_bench: list[float | None] | None = None) -> dict:
    """La lectura completa. Las partes que no se pueden calcular quedan en `None`."""
    cierres = [b.cierre for b in barras]
    soporte, resistencia = niveles_cercanos(barras)
    return {
        "fecha": barras[-1].fecha if barras else None,
        "ultimo_cierre": cierres[-1] if cierres else None,
        "tendencia": tendencia(cierres),
        "momentum": momentum(cierres),
        "soporte": soporte,
        "resistencia": resistencia,
        "fuerza_relativa": fuerza_relativa(cierres, cierres_bench) if cierres_bench is not None else None,
    }
