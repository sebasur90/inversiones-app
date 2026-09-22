"""Motor puro para comparar históricamente una cartera contra una referencia (benchmark).

Sin dependencias de `Session`/DB. Reúne dos problemas que `opportunity_cost_engine` y
`benchmarks_analytics` no resuelven:

1. Normalizar la serie de niveles de la referencia a una moneda de destino común (`usd`,
   `ars_nominal`, `ars_real`), punto a punto — necesario porque hoy se compara, por ejemplo,
   un TWR en dólares contra el Dólar (MEP) expresado en pesos, lo que da un resultado sin
   sentido para el benchmark (~45% "de rendimiento" del dólar en dólares).
2. Calcular la evolución del valor "sombra" (cuánto valdrían los mismos flujos de caja si se
   hubieran invertido en la referencia) en una serie de fechas, no sólo en el valor final,
   de forma eficiente (O(n+m) en vez de recalcular `valor_shadow` desde cero en cada punto).

También arma las advertencias de homogeneidad (moneda, período, frecuencia, datos
aproximados) que la pantalla necesita mostrar explícitamente.
"""
import bisect
from dataclasses import dataclass, field
from datetime import date

from .risk_engine import _bisect_right_carry_forward

MONEDAS_DESTINO = ("usd", "ars_nominal", "ars_real")
MIN_MESES_SIGNIFICATIVO = 3
DIAS_BAJA_DENSIDAD = 20


def _nivel_ars(v: float, moneda_punto: str, mep_en_fecha: float | None) -> float | None:
    """Nivel en ARS nominal de un punto nativo, según su moneda declarada.

    `None` si el punto está en USD y no hay MEP conocido a esa fecha (no se puede convertir).
    """
    if moneda_punto == "ARS":
        return v
    if mep_en_fecha is None or mep_en_fecha == 0:
        return None
    return v * mep_en_fecha


def normalizar_serie(
    serie_nativa: list[tuple[date, float, str]],
    moneda_destino: str,
    serie_mep: list[tuple[date, float]],
    serie_cer: list[tuple[date, float]],
    cer_hoy: float | None,
) -> tuple[list[tuple[date, float]], int]:
    """Convierte una serie de niveles de la referencia a `moneda_destino`, punto a punto.

    Args:
        serie_nativa: (fecha, nivel, moneda) ordenada cronológicamente. La moneda es POR
            PUNTO (no una propiedad de toda la serie): la de un ticker puede variar de fila
            a fila según cómo se cargó el precio, y tratarla como constante inyectaría un
            salto falso al convertir.
        moneda_destino: "usd" | "ars_nominal" | "ars_real"
        serie_mep, serie_cer: series de `IndiceMercado`, ordenadas, con grillas de fechas
            independientes entre sí (ambos campos son nullable en filas distintas).
        cer_hoy: CER del día de valuación, para expresar "ars_real" a precios de hoy (misma
            convención que `inversiones_analytics._monto_ars_real`: `* cer_hoy / cer_fecha`,
            nunca dividir por `cer_fecha` a secas).

    Returns:
        (serie_normalizada, n_puntos_descartados). Un punto se descarta si falta el MEP o el
        CER de su fecha (sin dato de carry-forward anterior) o si un nivel/factor da 0.
    """
    if moneda_destino not in MONEDAS_DESTINO:
        raise ValueError(f"moneda_destino inválida: {moneda_destino}")
    if moneda_destino == "ars_real" and cer_hoy is None:
        return [], len(serie_nativa)

    fechas_mep = [f[0] for f in serie_mep]
    fechas_cer = [f[0] for f in serie_cer]

    resultado: list[tuple[date, float]] = []
    descartados = 0

    for fecha, v, moneda_punto in serie_nativa:
        idx_mep = _bisect_right_carry_forward(fechas_mep, fecha)
        mep_f = serie_mep[idx_mep][1] if idx_mep >= 0 else None

        if moneda_destino == "ars_nominal":
            nivel = _nivel_ars(v, moneda_punto, mep_f)
        elif moneda_destino == "usd":
            if moneda_punto == "USD":
                nivel = v
            elif mep_f is None or mep_f == 0:
                nivel = None
            else:
                nivel = v / mep_f
        else:  # ars_real
            nivel_ars = _nivel_ars(v, moneda_punto, mep_f)
            if nivel_ars is None:
                nivel = None
            else:
                idx_cer = _bisect_right_carry_forward(fechas_cer, fecha)
                cer_f = serie_cer[idx_cer][1] if idx_cer >= 0 else None
                if cer_f is None or cer_f == 0:
                    nivel = None
                else:
                    nivel = nivel_ars * (cer_hoy / cer_f)

        if nivel is None or nivel == 0:
            descartados += 1
            continue
        resultado.append((fecha, nivel))

    return resultado, descartados


def serie_valor_shadow(
    flujos: list[tuple[date, float]],
    serie_niveles: list[tuple[date, float]],
    fechas: list[date],
) -> list[float | None]:
    """Valor de la referencia, en cada fecha de `fechas` (ascendentes), para los mismos flujos.

    Equivalencia con `opportunity_cost_engine.valor_shadow`: ese motor calcula, para un único
    `hasta`, `Σ (-monto_i) * (nivel_final / nivel_i)`. Sacando `nivel_final` como factor común
    queda `nivel_final * Σ(-monto_i / nivel_i)` — es decir, un acumulador de "unidades de la
    referencia" que sólo crece con flujos nuevos, multiplicado por el nivel del punto. Eso
    baja el costo de O(n·m) (recalcular todo en cada punto) a O(n+m).

    Semántica de `None`, igual que `valor_shadow` pero por punto en vez de global:
    - antes de que ocurra el primer flujo, el valor es `0.0` (todavía no se invirtió nada),
      igual que `valor_shadow` con `flujos=[]`;
    - si algún flujo ya ocurrido no tiene nivel de referencia en su fecha (anterior al primer
      dato de la serie) o cae en un nivel 0, ese punto y todos los posteriores quedan en
      `None` — el flujo sigue estando "adentro" del cálculo para cualquier fecha posterior;
    - si el propio punto de fecha `f` es anterior al primer dato de la serie, también es
      `None` (no hay con qué valuar).
    """
    if not serie_niveles or not flujos:
        # Mismo caso borde que `valor_shadow`: sin datos de la referencia, o sin flujos
        # todavía, el valor sombra es 0 para cualquier fecha.
        return [0.0 for _ in fechas]

    fechas_serie = [f[0] for f in serie_niveles]
    flujos_ordenados = sorted(flujos, key=lambda x: x[0])
    n_flujos = len(flujos_ordenados)

    idx_flujo = 0
    unidades = 0.0
    dañado = False
    resultado: list[float | None] = []

    for f in fechas:
        while idx_flujo < n_flujos and flujos_ordenados[idx_flujo][0] <= f:
            flujo_fecha, monto = flujos_ordenados[idx_flujo]
            nivel_flujo_idx = bisect.bisect_right(fechas_serie, flujo_fecha) - 1
            if nivel_flujo_idx < 0:
                dañado = True
            else:
                nivel_flujo = serie_niveles[nivel_flujo_idx][1]
                if nivel_flujo == 0:
                    dañado = True
                else:
                    unidades += (-monto) / nivel_flujo
            idx_flujo += 1

        if dañado:
            resultado.append(None)
            continue

        if idx_flujo == 0:
            resultado.append(0.0)
            continue

        nivel_final_idx = bisect.bisect_right(fechas_serie, f) - 1
        if nivel_final_idx < 0:
            resultado.append(None)
            continue
        nivel_final = serie_niveles[nivel_final_idx][1]
        if nivel_final == 0:
            resultado.append(None)
            continue

        resultado.append(unidades * nivel_final)

    return resultado


@dataclass
class ContextoComparacion:
    """Insumos para armar las advertencias de homogeneidad de una comparación ya calculada."""
    moneda_destino: str
    moneda_nativa_referencia: str          # "ARS" | "USD" | "mixta"
    referencia: str
    periodo_pedido_desde: date | None
    periodo_efectivo_desde: date | None
    periodo_hasta: date
    n_meses: int
    n_puntos_referencia: int
    dias_entre_puntos_referencia: float | None
    puntos_fx_descartados: int
    meses_sin_tenencia: int
    valuacion_aproximada: bool
    precio_faltante: bool


def _familia_moneda(moneda_destino: str) -> str:
    return "usd" if moneda_destino == "usd" else "ars"


def _nombre_moneda(familia: str) -> str:
    return "dólares" if familia == "usd" else "pesos"


def advertencias_homogeneidad(ctx: ContextoComparacion) -> list[str]:
    """Lista de advertencias en español, en orden de severidad. Vacía si todo es homogéneo."""
    advertencias: list[str] = []

    if (
        ctx.periodo_pedido_desde is not None
        and ctx.periodo_efectivo_desde is not None
        and ctx.periodo_efectivo_desde > ctx.periodo_pedido_desde
    ):
        advertencias.append(
            f"Se pidió comparar desde el {ctx.periodo_pedido_desde.isoformat()}, pero el "
            f"período efectivamente comparado arranca el {ctx.periodo_efectivo_desde.isoformat()}: "
            "antes de esa fecha falta historia de la cartera o de la referencia."
        )

    if ctx.n_meses < MIN_MESES_SIGNIFICATIVO:
        palabra = "mes" if ctx.n_meses == 1 else "meses"
        advertencias.append(
            f"El período comparado tiene {ctx.n_meses} {palabra}. Con menos de 3 meses la "
            "comparación es demasiado corta para ser informativa."
        )

    if ctx.moneda_nativa_referencia == "mixta":
        advertencias.append(
            "La serie de la referencia tiene puntos cargados en pesos y puntos cargados en "
            "dólares. Cada punto se convirtió con el tipo de cambio de su fecha, pero conviene "
            "revisar la carga de esa serie."
        )
    elif ctx.moneda_nativa_referencia.lower() != _familia_moneda(ctx.moneda_destino):
        origen = _nombre_moneda(ctx.moneda_nativa_referencia.lower())
        destino = _nombre_moneda(_familia_moneda(ctx.moneda_destino))
        if ctx.moneda_destino == "ars_real":
            destino = "pesos a valores de hoy"
        advertencias.append(
            f"La referencia cotiza en {origen} y se convirtió a {destino} usando el dólar MEP "
            "de cada fecha. Parte de la diferencia que se ve corresponde al tipo de cambio, no "
            "al comportamiento de la referencia."
        )

    if ctx.moneda_destino == "ars_real":
        advertencias.append(
            "Los valores en pesos reales están expresados a precios de hoy usando el CER. Un "
            "CER incompleto en alguna fecha desplaza el resultado."
        )

    if ctx.dias_entre_puntos_referencia is not None and ctx.dias_entre_puntos_referencia > DIAS_BAJA_DENSIDAD:
        advertencias.append(
            f"La serie de la referencia tiene {ctx.n_puntos_referencia} puntos en el período, "
            f"aproximadamente uno cada {round(ctx.dias_entre_puntos_referencia)} días. La cartera "
            "se valúa con precios diarios: los movimientos intermedios de la referencia no se ven."
        )

    if ctx.puntos_fx_descartados > 0:
        advertencias.append(
            f"{ctx.puntos_fx_descartados} puntos de la serie de la referencia quedaron fuera "
            "porque falta el tipo de cambio o el CER de esa fecha."
        )

    if ctx.meses_sin_tenencia > 0:
        advertencias.append(
            f"La cartera no tuvo posiciones en {ctx.meses_sin_tenencia} de los {ctx.n_meses} "
            "meses comparados. Esos meses quedan planos en la evolución de la cartera, mientras "
            "la referencia sí se mueve."
        )

    if ctx.valuacion_aproximada:
        advertencias.append(
            "Algunas valuaciones de la cartera usan el último precio conocido o el costo de "
            "compra porque falta cotización en esa fecha."
        )

    if ctx.precio_faltante:
        advertencias.append(
            "Hay posiciones sin precio ni costo conocido en alguna fecha: quedaron fuera de la "
            "valuación de la cartera."
        )

    return advertencias
