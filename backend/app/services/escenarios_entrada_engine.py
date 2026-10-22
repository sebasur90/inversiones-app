"""Escenarios de entrada de un activo: entrar ahora, esperar una condición técnica, esperar una valoración
más atractiva, entrada escalonada o descartar por ahora. Puro: sin DB ni red.

**No son predicciones.** Cada escenario dice qué condición lo activaría, de dónde sale ese nivel (regla
explícita), dónde quedaría invalidado y cuánto habría hasta los valores pesimista / base / optimista del
valor razonable por múltiplos de pares. Ese "potencial" es **hipotético** y relativo a los pares: no es un
rendimiento esperado ni una estimación estadística.

Niveles (todos con su regla visible):
- Soporte: el soporte automático más cercano por debajo del precio (pivotes fractales agrupados por ATR, ver
  `niveles_auto_engine`) que trae la lectura técnica.
- Invalidación técnica: soporte − 1 ATR(14); sin soporte, entrada − 2 ATR(14). Sin ATR no se inventa: el
  escenario dice que falta.
- Valoración: el valor razonable base (o el pesimista si el precio ya está dentro del rango).
- Escalonada: tres tramos iguales: ahora, en el soporte y en soporte − 1 ATR.

Fórmulas: `potencial = (V − P) / P`; `riesgo hasta la invalidación = (I − P) / P`; comisión estimada ida y
vuelta = 2 × tasa promedio histórica de tus operaciones (si no hay comisiones cargadas, se dice).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

VERSION_REGLAS = 1

AHORA, ESPERAR_TECNICA, ESPERAR_VALORACION, ESCALONADA, DESCARTAR = (
    "entrar_ahora", "esperar_tecnica", "esperar_valoracion", "escalonada", "descartar")
RSI_ESPERA = 40.0
ATR_INVALIDACION_SOPORTE = 1.0
ATR_INVALIDACION_SIN_SOPORTE = 2.0
HORIZONTE_MESES = {"corto": 3, "mediano": 12, "largo": 36}

REGLA_INVALIDACION = (
    f"soporte − {ATR_INVALIDACION_SOPORTE:g} ATR(14); sin soporte detectado, entrada − {ATR_INVALIDACION_SIN_SOPORTE:g} ATR(14)"
)
REGLA_POTENCIAL = ("(valor − precio de entrada) ÷ precio de entrada, contra los valores pesimista / base / optimista del valor "
                   "razonable por múltiplos de pares (cuartil 1 / mediana / cuartil 3). Hipotético, no un rendimiento esperado")
SALVEDAD = ("Escenarios hipotéticos con reglas fijas: no predicen el precio ni garantizan nada. El potencial es relativo a "
            "los múltiplos de los pares, no un rendimiento esperado estimado estadísticamente.")


@dataclass
class Insumos:
    precio: float | None
    fecha_precio: date | None
    moneda: str | None
    atr: float | None = None
    soporte: float | None = None
    resistencia: float | None = None
    rsi: float | None = None
    valor_pesimista: float | None = None
    valor_base: float | None = None
    valor_optimista: float | None = None
    moneda_valor: str | None = None            # moneda del valor razonable (la del snapshot de Yahoo)
    tasa_comision_pct: float | None = None
    banderas_criticas: list[str] = field(default_factory=list)
    datos_insuficientes: bool = False
    horizonte: str = "largo"


@dataclass
class Escenario:
    clave: str
    nombre: str
    disponible: bool
    condicion: str
    fundamento: str
    precio_entrada: float | None = None
    tramos: list[dict] = field(default_factory=list)
    invalidacion: float | None = None
    regla_invalidacion: str = ""
    riesgo_pct: float | None = None
    favorable_pct: float | None = None
    base_pct: float | None = None
    desfavorable_pct: float | None = None
    comision_pct: float | None = None
    faltantes: list[str] = field(default_factory=list)
    incertidumbres: list[str] = field(default_factory=list)


def _ratio(a: float | None, b: float | None) -> float | None:
    return (a - b) / b if a is not None and b is not None and b > 0 else None


def _num(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _potenciales(e: Escenario, ins: Insumos, valores_comparables: bool) -> None:
    if e.precio_entrada is None:
        return
    if not valores_comparables:
        e.faltantes.append("rango de valor razonable (sin conclusión por múltiplos de pares, o en otra moneda)")
        return
    e.favorable_pct = _ratio(ins.valor_optimista, e.precio_entrada)
    e.base_pct = _ratio(ins.valor_base, e.precio_entrada)
    e.desfavorable_pct = _ratio(ins.valor_pesimista, e.precio_entrada)


def _invalidacion(ins: Insumos, entrada: float | None) -> tuple[float | None, str | None]:
    if entrada is None:
        return None, None
    if ins.atr is None:
        return None, "ATR(14) (sin serie diaria no hay medida de volatilidad para fijar la invalidación)"
    if ins.soporte is not None and ins.soporte < entrada:
        return ins.soporte - ATR_INVALIDACION_SOPORTE * ins.atr, None
    return entrada - ATR_INVALIDACION_SIN_SOPORTE * ins.atr, None


def _completar(e: Escenario, ins: Insumos, valores_comparables: bool) -> Escenario:
    inv, falta = _invalidacion(ins, e.precio_entrada)
    e.invalidacion = inv
    e.regla_invalidacion = REGLA_INVALIDACION
    if falta:
        e.faltantes.append(falta)
    e.riesgo_pct = _ratio(inv, e.precio_entrada)
    if inv is not None and inv <= 0:
        e.invalidacion, e.riesgo_pct = None, None
        e.faltantes.append("la invalidación por ATR queda en un precio no positivo: la volatilidad es demasiado alta para esta regla")
    _potenciales(e, ins, valores_comparables)
    e.comision_pct = 2 * ins.tasa_comision_pct / 100 if ins.tasa_comision_pct is not None else None
    if ins.tasa_comision_pct is None:
        e.faltantes.append("comisión (no hay comisiones cargadas en tus movimientos para estimarla)")
    return e


def construir(ins: Insumos) -> dict:
    meses = HORIZONTE_MESES.get(ins.horizonte, 36)
    comparables = (ins.valor_base is not None and ins.valor_pesimista is not None and ins.valor_optimista is not None
                   and (ins.moneda_valor is None or ins.moneda is None or ins.moneda_valor == ins.moneda))
    incert_comunes = []
    if ins.valor_base is not None and not comparables:
        incert_comunes.append(f"el valor razonable está en {ins.moneda_valor} y el precio en {ins.moneda}: no se comparan")
    escenarios: list[Escenario] = []

    if ins.precio is None:
        return {
            "version_reglas": VERSION_REGLAS, "estado": "sin_datos", "precio": None, "fecha_precio": None, "moneda": ins.moneda,
            "horizonte_meses": meses, "escenarios": [],
            "mensaje": "No hay un precio de referencia: no se pueden armar escenarios.",
            "regla_potencial": REGLA_POTENCIAL, "salvedad": SALVEDAD,
        }

    p = ins.precio
    ahora = Escenario(AHORA, "Entrar ahora", True, f"al precio de referencia {_num(p)} {ins.moneda or ''}".strip(),
                      f"último precio conocido ({ins.fecha_precio.isoformat() if ins.fecha_precio else 'sin fecha'})",
                      precio_entrada=p, incertidumbres=list(incert_comunes))
    escenarios.append(_completar(ahora, ins, comparables))

    if ins.soporte is not None and ins.soporte < p:
        tec = Escenario(ESPERAR_TECNICA, "Esperar una condición técnica", True,
                        f"que el precio llegue al soporte de {_num(ins.soporte)} ({_ratio(ins.soporte, p) * 100:.1f} % desde hoy)".replace(".", ","),
                        "soporte automático más cercano por debajo del precio (pivotes de 5 ruedas agrupados por 0,5 ATR, ≥ 2 toques)",
                        precio_entrada=ins.soporte, incertidumbres=list(incert_comunes) + ["el precio puede no llegar nunca al soporte"])
        escenarios.append(_completar(tec, ins, comparables))
    elif ins.rsi is not None:
        tec = Escenario(ESPERAR_TECNICA, "Esperar una condición técnica", True,
                        f"que el RSI(14) baje de {RSI_ESPERA:.0f} (hoy {ins.rsi:.0f})",
                        "sin soporte detectado debajo del precio; se usa el RSI como condición de espera",
                        incertidumbres=["la condición no fija un precio: el nivel de entrada se conoce recién cuando ocurra"])
        escenarios.append(tec)
    else:
        escenarios.append(Escenario(ESPERAR_TECNICA, "Esperar una condición técnica", False, "—", "",
                                    faltantes=["serie diaria de precios (la lectura técnica corre sobre cartera y watchlist)"]))

    if comparables:
        objetivo = ins.valor_pesimista if p <= ins.valor_base else ins.valor_base
        regla = ("el precio ya está debajo del valor base: se espera el pesimista (cuartil 1 de los pares)"
                 if p <= ins.valor_base else "valor razonable base (mediana de los múltiplos de los pares)")
        if objetivo < p:
            val = Escenario(ESPERAR_VALORACION, "Esperar una valoración más atractiva", True,
                            f"que el precio baje a {_num(objetivo)} ({_ratio(objetivo, p) * 100:.1f} % desde hoy)".replace(".", ","),
                            regla, precio_entrada=objetivo,
                            incertidumbres=list(incert_comunes) + ["los múltiplos de los pares también se mueven"])
            escenarios.append(_completar(val, ins, comparables))
        else:
            escenarios.append(Escenario(ESPERAR_VALORACION, "Esperar una valoración más atractiva", False,
                                        "el precio ya está por debajo del valor pesimista de sus pares", regla))
    else:
        escenarios.append(Escenario(ESPERAR_VALORACION, "Esperar una valoración más atractiva", False, "—", "",
                                    faltantes=["valor razonable concluyente por múltiplos de pares"]))

    if ins.soporte is not None and ins.soporte < p and ins.atr is not None and ins.soporte - ins.atr > 0:
        niveles = [p, ins.soporte, ins.soporte - ins.atr]
        promedio = sum(niveles) / 3
        esc = Escenario(ESCALONADA, "Entrada escalonada", True,
                        "tres tramos iguales: ahora, en el soporte y en soporte − 1 ATR",
                        "reparte el precio de entrada; si el precio no baja, sólo se completa el primer tramo",
                        precio_entrada=promedio,
                        tramos=[{"precio": n, "fraccion": 1 / 3} for n in niveles],
                        incertidumbres=list(incert_comunes) + ["el precio medio supone que se completan los tres tramos"])
        escenarios.append(_completar(esc, ins, comparables))
    else:
        escenarios.append(Escenario(ESCALONADA, "Entrada escalonada", False, "—", "",
                                    faltantes=["soporte por debajo del precio y ATR(14) (serie diaria)"]))

    motivos = list(ins.banderas_criticas)
    if ins.datos_insuficientes:
        motivos.append("los datos no alcanzan para un análisis completo")
    escenarios.append(Escenario(
        DESCARTAR, "Descartar por ahora", bool(motivos),
        "; ".join(motivos) if motivos else "no hay banderas críticas ni falta de datos que lo sugieran",
        "se activa con banderas críticas o datos insuficientes; siempre es una opción válida",
    ))

    return {
        "version_reglas": VERSION_REGLAS,
        "estado": "ok",
        "precio": p,
        "fecha_precio": ins.fecha_precio,
        "moneda": ins.moneda,
        "horizonte_meses": meses,
        "escenarios": [asdict(e) for e in escenarios],
        "mensaje": "",
        "regla_potencial": REGLA_POTENCIAL,
        "salvedad": SALVEDAD,
    }
