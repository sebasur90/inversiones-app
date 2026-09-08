"""Motor puro del screener: "¿cuánto tiene que moverse el precio para que esta estrategia
dispare?". Sin dependencias de `Session`/DB/red — recibe `Barra`s ya resueltas y un DSL, igual que
`estrategia_engine`.

**Enfoque**: no hay forma cerrada de invertir un DSL arbitrario (árbol de hasta 20 nodos con
`y`/`o`/`no`, indicadores no lineales como RSI o Bollinger). Se busca numéricamente: se perturba el
*cierre* de la última barra en `δ%` y se re-evalúa `estrategia_engine.compilar()` sobre esa barra
modificada — la misma función que usa el backtest, así que el resultado es consistente por
construcción con lo que la app realmente operaría (ver test de coherencia en
`test_screener.py`). La búsqueda es una grilla logarítmica (ambos signos, de más cerca a más lejos)
seguida de bisección: ~15-20 evaluaciones por par ticker+estrategia.

**Costo**: recompilar el DSL entero sobre 750+ barras, 20 veces, por cada par, sería demasiado caro
para escanear un universo — `sma()`/`ema()`/etc. son O(N·W). Como sólo se perturba la *última*
barra, alcanza con recompilar sobre una cola corta de la serie (`barras_contexto`): lo bastante
larga para que el indicador converja al mismo valor en el último índice, no toda la historia.

**Stops** (`distancia_a_stops`) son un caso aparte: los niveles de stop loss / take profit /
trailing son precios exactos (fórmulas cerradas, ya usadas por `estrategia_engine.backtest`), así
que no necesitan búsqueda.
"""
from __future__ import annotations

from . import estrategia_engine, indicadores_engine
from .indicadores_engine import Barra

__all__ = [
    "distancia_al_disparo", "barras_contexto", "distancia_a_stops", "desglose_condiciones",
]


# ─── Contexto mínimo para re-evaluar sólo la última barra ────────────────────

# Sentinel: "hace falta la serie completa" (indicadores que dependen de toda la historia cargada,
# como OBV o EXTREMOS/PERCENTIL con `ventana=0`). El caller lo recorta con `min(., len(barras))`.
_CONTEXTO_HISTORICO = 10**9

# Clasificación de cada indicador según cómo converge su último valor:
# - "exacto": ventana fija (SMA, Bollinger, ESTOCASTICO, ...) — con `warm_up + 2` barras de cola el
#   último valor es idéntico al de la serie completa (mismo cálculo, misma ventana).
# - "recursivo": suavizado exponencial/Wilder (EMA, RSI, MACD, ATR) — no hay ventana fija, pero el
#   peso de la semilla decae geométricamente; `warm_up·3 + 12` barras deja un error residual muy
#   por debajo de la resolución de la grilla de búsqueda.
# - "historico": depende de toda la serie cargada (OBV; EXTREMOS/PERCENTIL con `ventana=0`) — no
#   hay atajo, se necesita la serie completa.
# - "ventana": como "exacto", pero con `ventana=0` (histórico expansivo) se comporta como
#   "historico" — se resuelve dinámicamente en `barras_contexto` según el parámetro real.
_FAMILIA_POR_TIPO: dict[str, str] = {
    "SMA": "exacto",
    "EMA": "recursivo",
    "RSI": "recursivo",
    "MACD": "recursivo",
    "BOLLINGER": "exacto",
    "ATR": "recursivo",
    "ESTOCASTICO": "exacto",
    "OBV": "historico",
    "VOLUMEN_PROMEDIO": "exacto",
    "EXTREMOS": "ventana",
    "PERCENTIL": "ventana",
    "RETORNO": "exacto",
}


def _recorrer_subiendo_bajando(cond: dict | None, maximo: list[int]) -> None:
    """Junta el mayor `barras` entre los nodos `subiendo`/`bajando` del árbol: `barras_minimas()`
    no lo contempla (no es warm-up de un indicador, es una mirada hacia atrás sobre su serie)."""
    if not cond:
        return
    op = cond.get("op")
    if op in ("y", "o"):
        for hijo in cond.get("condiciones", []) or []:
            _recorrer_subiendo_bajando(hijo, maximo)
    elif op == "no":
        _recorrer_subiendo_bajando(cond.get("condicion"), maximo)
    elif op in ("subiendo", "bajando"):
        maximo[0] = max(maximo[0], int(cond.get("barras", 1)))


def barras_contexto(dsl: dict) -> int:
    """Ruedas de cola a partir de las que recompilar el DSL para que el último índice converja al
    mismo valor que sobre la serie completa. `>= _CONTEXTO_HISTORICO` == "usar toda la serie"."""
    necesario = 0
    for item in dsl.get("indicadores", []) or []:
        tipo = item.get("tipo")
        espec = indicadores_engine.INDICADORES.get(tipo)
        if espec is None:
            continue  # DSL ya validado río arriba; defensivo nomás
        params = {**espec.params_default, **(item.get("params") or {})}
        warm_up = indicadores_engine.warm_up_barras(tipo, item.get("params"))
        familia = _FAMILIA_POR_TIPO.get(tipo)

        if familia == "ventana":
            familia = "historico" if int(params.get("ventana", 0)) == 0 else "exacto"

        if familia == "historico":
            return _CONTEXTO_HISTORICO
        elif familia == "recursivo":
            necesario = max(necesario, warm_up * 3 + 12)
        else:  # "exacto" (o clasificación desconocida: mismo trato conservador que "exacto")
            necesario = max(necesario, warm_up + 2)

    maximo_subiendo_bajando = [0]
    _recorrer_subiendo_bajando(dsl.get("entrada"), maximo_subiendo_bajando)
    _recorrer_subiendo_bajando(dsl.get("salida"), maximo_subiendo_bajando)

    # +2 mínimo: un `cruce_arriba`/`cruce_abajo` siempre necesita la barra anterior además de la
    # actual, incluso sin ningún indicador declarado (comparando `campo` contra `const`).
    return necesario + maximo_subiendo_bajando[0] + 2


# ─── Búsqueda del precio-gatillo ──────────────────────────────────────────────

def _perturbar_ultima_barra(barras: list[Barra], delta_pct: float) -> list[Barra]:
    """Nueva lista con el cierre de la última barra movido `delta_pct`%. `máximo`/`mínimo` se
    ensanchan si hace falta para que seguir siendo consistentes (`EXTREMOS`, `ESTOCASTICO`, `ATR`
    leen el rango de la barra, no sólo el cierre) — `apertura`/`volumen` quedan intactos."""
    if not barras:
        return barras
    ultima = barras[-1]
    nuevo_cierre = ultima.cierre * (1 + delta_pct / 100)
    nuevo_maximo = ultima.maximo if ultima.maximo is None else max(ultima.maximo, nuevo_cierre)
    nuevo_minimo = ultima.minimo if ultima.minimo is None else min(ultima.minimo, nuevo_cierre)
    perturbada = Barra(
        fecha=ultima.fecha, cierre=nuevo_cierre, apertura=ultima.apertura,
        maximo=nuevo_maximo, minimo=nuevo_minimo, volumen=ultima.volumen,
    )
    return [*barras[:-1], perturbada]


def _dispara(dsl: dict, ventana: list[Barra], condicion: str, delta_pct: float) -> bool:
    perturbada = _perturbar_ultima_barra(ventana, delta_pct)
    serie = estrategia_engine.compilar(dsl, perturbada)
    valor = (serie.entrada if condicion == "entrada" else serie.salida)[-1]
    return valor is True


# Grilla base, log-espaciada: se evalúan ambos signos en cada magnitud antes de pasar a la
# siguiente, así el primer disparo encontrado es, por construcción, el más cercano.
_GRILLA_BASE_PCT = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0)
_PASOS_BISECCION = 5


def _grilla(limite_pct: float) -> list[float]:
    grilla = [m for m in _GRILLA_BASE_PCT if m < limite_pct]
    ultimo = grilla[-1] if grilla else 0.0
    # Más allá del tope de la grilla fija (12%) sigue log-espaciando (×1.5) en vez de saltar
    # directo a `limite_pct`: con un `limite_pct` grande (p.ej. 50%) el hueco 12→50 sería
    # demasiado ancho para que la bisección converja con la precisión habitual.
    while ultimo * 1.5 < limite_pct:
        ultimo *= 1.5
        grilla.append(ultimo)
    grilla.append(limite_pct)  # el límite siempre se prueba, aunque no caiga en la progresión
    return grilla


def distancia_al_disparo(
    dsl: dict, barras: list[Barra], condicion: str, limite_pct: float = 15.0,
) -> float | None:
    """δ% (con signo: negativo = el precio tiene que *bajar*) de menor magnitud tal que mover el
    cierre de la última barra ese δ% hace disparar `condicion` (`"entrada"` o `"salida"`).
    `None` si no dispara dentro de `±limite_pct` — puede ser una condición que ya no puede
    cumplirse hoy (p.ej. un `cruce_arriba` ya consumado ayer: ningún cierre de hoy lo repite).
    """
    if condicion not in ("entrada", "salida"):
        raise ValueError(f"condición inválida: {condicion!r}")
    if len(barras) < 2:
        return None

    contexto = barras_contexto(dsl)
    ventana = barras[-min(contexto, len(barras)):]

    if _dispara(dsl, ventana, condicion, 0.0):
        return 0.0

    anterior = 0.0
    for magnitud in _grilla(limite_pct):
        for signo in (1, -1):
            if _dispara(dsl, ventana, condicion, signo * magnitud):
                lo, hi = anterior, magnitud  # dispara(signo*anterior) es False, dispara(signo*hi) True
                for _ in range(_PASOS_BISECCION):
                    mid = (lo + hi) / 2
                    if _dispara(dsl, ventana, condicion, signo * mid):
                        hi = mid
                    else:
                        lo = mid
                return round(signo * hi, 4)
        anterior = magnitud
    return None


# ─── Stops (precio exacto, sin búsqueda) ──────────────────────────────────────

def distancia_a_stops(
    barras: list[Barra], indice_entrada: int, precio_entrada: float, riesgo: dict,
) -> list[dict]:
    """Distancia (%, con signo) del precio actual a cada nivel de riesgo activo de la operación
    abierta. Fórmulas idénticas a `estrategia_engine._chequear_salida`/`backtest` — el trailing usa
    la misma siembra (`maximo_barra`, arrancando en `precio_entrada`, sólo barras *posteriores* a
    la entrada lo mueven), para que el nivel coincida con el que realmente vigila el backtest."""
    if not barras:
        return []
    precio_actual = barras[-1].cierre
    resultados: list[dict] = []

    stop_loss_pct = riesgo.get("stop_loss_pct")
    if stop_loss_pct is not None:
        nivel = precio_entrada * (1 - stop_loss_pct / 100)
        resultados.append({"motivo": "stop_loss", "nivel": nivel, "distancia_pct": round((nivel / precio_actual - 1) * 100, 4)})

    take_profit_pct = riesgo.get("take_profit_pct")
    if take_profit_pct is not None:
        nivel = precio_entrada * (1 + take_profit_pct / 100)
        resultados.append({"motivo": "take_profit", "nivel": nivel, "distancia_pct": round((nivel / precio_actual - 1) * 100, 4)})

    trailing_stop_pct = riesgo.get("trailing_stop_pct")
    if trailing_stop_pct is not None:
        maximo_desde_entrada = precio_entrada
        for b in barras[indice_entrada + 1:]:
            maximo_desde_entrada = max(maximo_desde_entrada, estrategia_engine.maximo_barra(b))
        nivel = maximo_desde_entrada * (1 - trailing_stop_pct / 100)
        resultados.append({"motivo": "trailing_stop", "nivel": nivel, "distancia_pct": round((nivel / precio_actual - 1) * 100, 4)})

    return resultados


# ─── Desglose de condiciones (para mostrar "qué falta") ───────────────────────

def _formato_operando(operando: dict, etiqueta_por_id: dict[str, str]) -> str:
    if "const" in operando:
        valor = operando["const"]
        return str(int(valor)) if isinstance(valor, float) and valor == int(valor) else str(valor)
    if "campo" in operando:
        return operando["campo"]
    if "ref" in operando:
        base = etiqueta_por_id.get(operando["ref"], operando["ref"])
        salida = operando.get("salida", "valor")
        return base if salida == "valor" else f"{base}.{salida}"
    return "?"


def desglose_condiciones(dsl: dict, barras: list[Barra], condicion: str) -> list[dict]:
    """Una fila por hoja del árbol de `condicion` (`"entrada"`/`"salida"`), con el valor actual de
    cada lado y si esa hoja individual cumple hoy. `cumple` se relee con
    `estrategia_engine._evaluar_condicion` sobre la hoja sola (no se puede derivar del booleano
    agregado de `compilar()`, que ya mezcla todo el árbol) — así queda garantizado que coincide
    exactamente con lo que evaluaría el backtest, sin reimplementar cada operador acá.
    """
    if condicion not in ("entrada", "salida"):
        raise ValueError(f"condición inválida: {condicion!r}")
    cond_dsl = dsl.get(condicion)
    if not cond_dsl or not barras:
        return []

    compilado = estrategia_engine.compilar(dsl, barras)
    etiqueta_por_id = {
        item["id"]: indicadores_engine.clave(item["tipo"], item.get("params"))
        for item in (dsl.get("indicadores") or [])
        if item.get("tipo") in indicadores_engine.INDICADORES
    }

    def _valor(operando: dict) -> float | None:
        serie = estrategia_engine.resolver_operando(operando, barras, compilado.series)
        return serie[-1] if serie else None

    filas: list[dict] = []

    def _recorrer(cond: dict) -> None:
        op = cond.get("op")
        if op in ("y", "o"):
            for hijo in cond.get("condiciones", []) or []:
                _recorrer(hijo)
            return
        if op == "no":
            hijo = cond.get("condicion")
            if hijo:
                _recorrer(hijo)
            return

        serie_hoja = estrategia_engine._evaluar_condicion(cond, barras, compilado.series)
        cumple = bool(serie_hoja[-1]) if serie_hoja and serie_hoja[-1] is not None else False

        if op == "entre":
            valor, minimo, maximo = cond["valor"], cond["minimo"], cond["maximo"]
            filas.append({
                "op": op, "cumple": cumple,
                "izq_etiqueta": _formato_operando(valor, etiqueta_por_id), "izq_valor": _valor(valor),
                "der_etiqueta": f"[{_formato_operando(minimo, etiqueta_por_id)}, {_formato_operando(maximo, etiqueta_por_id)}]",
                "der_valor": None,
            })
        elif op in ("subiendo", "bajando"):
            operando = cond["operando"]
            filas.append({
                "op": op, "cumple": cumple,
                "izq_etiqueta": _formato_operando(operando, etiqueta_por_id), "izq_valor": _valor(operando),
                "der_etiqueta": f"hace {int(cond.get('barras', 1))} barras", "der_valor": None,
            })
        else:  # comparadores + cruce_arriba/cruce_abajo: todos tienen izq/der
            izq, der = cond["izq"], cond["der"]
            filas.append({
                "op": op, "cumple": cumple,
                "izq_etiqueta": _formato_operando(izq, etiqueta_por_id), "izq_valor": _valor(izq),
                "der_etiqueta": _formato_operando(der, etiqueta_por_id), "der_valor": _valor(der),
            })

    _recorrer(cond_dsl)
    return filas
