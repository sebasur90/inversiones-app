"""Motor puro de la propuesta de rebalanceo (compra/venta sugerida por posición).

Sin dependencias de `Session`/DB/FastAPI: recibe posiciones y objetivos ya resueltos y
devuelve una propuesta explicable (cada ítem trae su `motivo`), igual que el patrón de
`risk_engine.py`/`contribucion_engine.py`. Es puro cálculo — nunca escribe nada, lo que
garantiza que la simulación no pueda derivar en un registro accidental de movimientos reales.

Algoritmo, por eje:
- Eje "Ticker": el objetivo (si existe) es directo por ticker.
- Ejes "Cartera"/"Tipo"/"Sector": el delta de la categoría se reparte entre sus tickers
  proporcionalmente al valor actual de cada uno. Si un ticker de la categoría tiene además
  un objetivo propio cargado en el eje Ticker, ese objetivo manda para ese ticker y se
  resta del remanente de la categoría antes de prorratear el resto. Una categoría con
  objetivo pero sin ningún instrumento en cartera no inventa un ticker: se marca como
  "categoria_sin_instrumento" para que el usuario elija manualmente qué comprar.
"""
from dataclasses import dataclass, field, replace

EPS_USD = 0.01
EPS_PCT = 1e-9
ACCION_EPS_USD = 1.0  # por debajo de esto se considera "mantener" (ruido de redondeo)


@dataclass
class PosicionActual:
    ticker: str
    categoria: str  # etiqueta del ticker en el eje elegido (tipo/sector/cartera/ticker)
    valor_usd: float


@dataclass
class PropuestaItem:
    tipo: str  # "ticker" | "categoria_sin_instrumento"
    categoria: str
    peso_actual_pct: float
    peso_objetivo_pct: float
    delta_pp: float
    valor_actual_usd: float
    valor_objetivo_usd: float
    importe_sugerido_usd: float
    accion: str  # "comprar" | "vender" | "mantener"
    necesidad: str  # "necesario" | "opcional"
    comision_estimada_usd: float
    motivo: str
    posicion: str | None = None


@dataclass
class ResultadoPropuesta:
    items: list[PropuestaItem]
    sobrante_usd: float = 0.0


def _accion_desde_importe(importe_usd: float) -> str:
    if importe_usd > ACCION_EPS_USD:
        return "comprar"
    if importe_usd < -ACCION_EPS_USD:
        return "vender"
    return "mantener"


def _necesidad_desde_delta(delta_pp: float, tolerancia_pp: float) -> str:
    return "necesario" if abs(delta_pp) > tolerancia_pp else "opcional"


def _comision(importe_usd: float, accion: str, tasa_comision_pct: float) -> float:
    if accion == "mantener":
        return 0.0
    return round(abs(importe_usd) * tasa_comision_pct / 100, 2)


def generar_propuesta(
    posiciones: list[PosicionActual],
    objetivos_categoria: dict[str, float],
    objetivos_ticker: dict[str, float],
    eje: str,
    total_usd: float,
    tolerancia_pp: float,
    peso_maximo_pp: float | None,
    peso_minimo_pp: float | None,
    modo: str,
    aporte_usd: float,
    tasa_comision_pct: float,
) -> ResultadoPropuesta:
    total_efectivo = total_usd + aporte_usd if modo == "solo_aportes" else total_usd

    def _peso_actual(valor_usd: float) -> float:
        return round(valor_usd / total_usd * 100, 2) if total_usd > EPS_USD else 0.0

    def _peso_objetivo(valor_objetivo_usd: float) -> float:
        return round(valor_objetivo_usd / total_efectivo * 100, 2) if total_efectivo > EPS_USD else 0.0

    items: list[PropuestaItem] = []

    if eje == "Ticker":
        tickers = {p.ticker: p.valor_usd for p in posiciones}
        todos = set(tickers.keys()) | set(objetivos_ticker.keys())
        for ticker in todos:
            valor_actual = tickers.get(ticker, 0.0)
            peso_actual_pct = _peso_actual(valor_actual)
            if ticker in objetivos_ticker:
                objetivo_pct = objetivos_ticker[ticker]
                valor_objetivo = objetivo_pct / 100 * total_efectivo
                importe = valor_objetivo - valor_actual
                accion = _accion_desde_importe(importe)
                peso_objetivo_pct = _peso_objetivo(valor_objetivo)
                delta_pp = round(peso_objetivo_pct - peso_actual_pct, 2)
                items.append(PropuestaItem(
                    tipo="ticker",
                    posicion=ticker,
                    categoria=ticker,
                    peso_actual_pct=peso_actual_pct,
                    peso_objetivo_pct=peso_objetivo_pct,
                    delta_pp=delta_pp,
                    valor_actual_usd=round(valor_actual, 2),
                    valor_objetivo_usd=round(valor_objetivo, 2),
                    importe_sugerido_usd=round(importe, 2),
                    accion=accion,
                    necesidad=_necesidad_desde_delta(delta_pp, tolerancia_pp),
                    comision_estimada_usd=_comision(importe, accion, tasa_comision_pct),
                    motivo=f"Objetivo definido para {ticker}: {objetivo_pct:.1f}% de la cartera.",
                ))
            else:
                items.append(PropuestaItem(
                    tipo="ticker",
                    posicion=ticker,
                    categoria=ticker,
                    peso_actual_pct=peso_actual_pct,
                    peso_objetivo_pct=peso_actual_pct,
                    delta_pp=0.0,
                    valor_actual_usd=round(valor_actual, 2),
                    valor_objetivo_usd=round(valor_actual, 2),
                    importe_sugerido_usd=0.0,
                    accion="mantener",
                    necesidad="opcional",
                    comision_estimada_usd=0.0,
                    motivo="Sin objetivo definido para este instrumento.",
                ))
    else:
        por_categoria: dict[str, list[PosicionActual]] = {}
        for p in posiciones:
            por_categoria.setdefault(p.categoria, []).append(p)

        todas_categorias = set(objetivos_categoria.keys()) | set(por_categoria.keys())
        for categoria in todas_categorias:
            tickers_categoria = por_categoria.get(categoria, [])
            valor_actual_categoria = sum(t.valor_usd for t in tickers_categoria)

            if categoria not in objetivos_categoria:
                for t in tickers_categoria:
                    peso_actual_pct = _peso_actual(t.valor_usd)
                    items.append(PropuestaItem(
                        tipo="ticker",
                        posicion=t.ticker,
                        categoria=categoria,
                        peso_actual_pct=peso_actual_pct,
                        peso_objetivo_pct=peso_actual_pct,
                        delta_pp=0.0,
                        valor_actual_usd=round(t.valor_usd, 2),
                        valor_objetivo_usd=round(t.valor_usd, 2),
                        importe_sugerido_usd=0.0,
                        accion="mantener",
                        necesidad="opcional",
                        comision_estimada_usd=0.0,
                        motivo=f"La categoría '{categoria}' no tiene objetivo de rebalanceo definido.",
                    ))
                continue

            objetivo_pct_categoria = objetivos_categoria[categoria]
            valor_objetivo_categoria = objetivo_pct_categoria / 100 * total_efectivo
            peso_actual_categoria_pct = _peso_actual(valor_actual_categoria)
            peso_objetivo_categoria_pct = _peso_objetivo(valor_objetivo_categoria)
            delta_categoria_pp = round(peso_objetivo_categoria_pct - peso_actual_categoria_pct, 2)
            necesidad_categoria = _necesidad_desde_delta(delta_categoria_pp, tolerancia_pp)

            remanente = valor_objetivo_categoria - valor_actual_categoria
            sin_override = []
            for t in tickers_categoria:
                if t.ticker in objetivos_ticker:
                    objetivo_pct = objetivos_ticker[t.ticker]
                    valor_objetivo_t = objetivo_pct / 100 * total_efectivo
                    importe_t = valor_objetivo_t - t.valor_usd
                    remanente -= importe_t
                    accion_t = _accion_desde_importe(importe_t)
                    peso_actual_t = _peso_actual(t.valor_usd)
                    peso_objetivo_t = _peso_objetivo(valor_objetivo_t)
                    delta_pp_t = round(peso_objetivo_t - peso_actual_t, 2)
                    items.append(PropuestaItem(
                        tipo="ticker",
                        posicion=t.ticker,
                        categoria=categoria,
                        peso_actual_pct=peso_actual_t,
                        peso_objetivo_pct=peso_objetivo_t,
                        delta_pp=delta_pp_t,
                        valor_actual_usd=round(t.valor_usd, 2),
                        valor_objetivo_usd=round(valor_objetivo_t, 2),
                        importe_sugerido_usd=round(importe_t, 2),
                        accion=accion_t,
                        necesidad=_necesidad_desde_delta(delta_pp_t, tolerancia_pp),
                        comision_estimada_usd=_comision(importe_t, accion_t, tasa_comision_pct),
                        motivo=(
                            f"Objetivo propio definido para {t.ticker} ({objetivo_pct:.1f}%): "
                            "prioridad sobre el objetivo de la categoría."
                        ),
                    ))
                else:
                    sin_override.append(t)

            if not tickers_categoria:
                if remanente > EPS_USD:
                    items.append(PropuestaItem(
                        tipo="categoria_sin_instrumento",
                        posicion=None,
                        categoria=categoria,
                        peso_actual_pct=0.0,
                        peso_objetivo_pct=peso_objetivo_categoria_pct,
                        delta_pp=delta_categoria_pp,
                        valor_actual_usd=0.0,
                        valor_objetivo_usd=round(valor_objetivo_categoria, 2),
                        importe_sugerido_usd=round(remanente, 2),
                        accion="comprar",
                        necesidad=necesidad_categoria,
                        comision_estimada_usd=_comision(remanente, "comprar", tasa_comision_pct),
                        motivo=f"La categoría '{categoria}' no tiene instrumentos en cartera; elegí manualmente qué comprar.",
                    ))
                continue

            if not sin_override:
                continue

            base_valor = sum(t.valor_usd for t in sin_override)
            for t in sin_override:
                proporcion = t.valor_usd / base_valor if base_valor > EPS_USD else 1 / len(sin_override)
                importe_t = remanente * proporcion
                valor_objetivo_t = t.valor_usd + importe_t
                accion_t = _accion_desde_importe(importe_t)
                peso_actual_t = _peso_actual(t.valor_usd)
                peso_objetivo_t = _peso_objetivo(valor_objetivo_t)
                items.append(PropuestaItem(
                    tipo="ticker",
                    posicion=t.ticker,
                    categoria=categoria,
                    peso_actual_pct=peso_actual_t,
                    peso_objetivo_pct=peso_objetivo_t,
                    delta_pp=delta_categoria_pp,
                    valor_actual_usd=round(t.valor_usd, 2),
                    valor_objetivo_usd=round(valor_objetivo_t, 2),
                    importe_sugerido_usd=round(importe_t, 2),
                    accion=accion_t,
                    necesidad=necesidad_categoria,
                    comision_estimada_usd=_comision(importe_t, accion_t, tasa_comision_pct),
                    motivo=f"Se reparte según el peso actual de cada instrumento dentro de '{categoria}'.",
                ))

    if modo != "solo_aportes":
        items = _aplicar_banda_pesos(items, peso_minimo_pp, peso_maximo_pp, total_efectivo, tasa_comision_pct)
        return ResultadoPropuesta(items=items, sobrante_usd=0.0)

    return _aplicar_solo_aportes(items, aporte_usd, peso_maximo_pp, total_efectivo, tasa_comision_pct)


def _aplicar_banda_pesos(
    items: list[PropuestaItem],
    peso_minimo_pp: float | None,
    peso_maximo_pp: float | None,
    total_efectivo: float,
    tasa_comision_pct: float,
) -> list[PropuestaItem]:
    """En modo rebalanceo completo, recorta el objetivo de cada instrumento a la banda
    [peso_minimo, peso_maximo] configurada.

    - El **techo** se aplica a todo instrumento en cartera: una sobreponderación se corrige
      vendiendo hasta el máximo, tenga o no un objetivo propio cargado.
    - El **piso** sólo se aplica a instrumentos que ya apuntan a un cambio (`delta_pp != 0`):
      un "mantener sin objetivo" no dispara compras hacia el mínimo, para no forzar la compra
      de posiciones ínfimas que el usuario dejó chicas a propósito.

    Recortar contra una banda dura rompe la identidad "los objetivos suman 100%": es inherente
    a un guardrail y queda anotado en el `motivo` de cada ítem tocado.
    """
    if total_efectivo <= EPS_USD or (peso_maximo_pp is None and peso_minimo_pp is None):
        return items

    techo_usd = peso_maximo_pp / 100 * total_efectivo if peso_maximo_pp is not None else None
    piso_usd = peso_minimo_pp / 100 * total_efectivo if peso_minimo_pp is not None else None

    ajustados: list[PropuestaItem] = []
    for it in items:
        if it.tipo != "ticker" or it.posicion is None:
            ajustados.append(it)
            continue

        objetivo = it.valor_objetivo_usd
        nuevo = objetivo
        toco: str | None = None
        if techo_usd is not None and nuevo > techo_usd + EPS_USD:
            nuevo, toco = techo_usd, f"peso máximo ({peso_maximo_pp:.1f}%)"
        elif piso_usd is not None and nuevo < piso_usd - EPS_USD and abs(it.delta_pp) > EPS_PCT:
            nuevo, toco = piso_usd, f"peso mínimo ({peso_minimo_pp:.1f}%)"

        if toco is None or abs(nuevo - objetivo) <= EPS_USD:
            ajustados.append(it)
            continue

        importe = nuevo - it.valor_actual_usd
        accion = _accion_desde_importe(importe)
        peso_objetivo_pct = round(nuevo / total_efectivo * 100, 2)
        ajustados.append(replace(
            it,
            peso_objetivo_pct=peso_objetivo_pct,
            valor_objetivo_usd=round(nuevo, 2),
            importe_sugerido_usd=round(importe, 2),
            delta_pp=round(peso_objetivo_pct - it.peso_actual_pct, 2),
            accion=accion,
            comision_estimada_usd=_comision(importe, accion, tasa_comision_pct),
            motivo=it.motivo + f" Recortado al {toco} configurado para la cartera.",
        ))
    return ajustados


def _aplicar_solo_aportes(
    items: list[PropuestaItem],
    aporte_usd: float,
    peso_maximo_pp: float | None,
    total_efectivo: float,
    tasa_comision_pct: float,
) -> ResultadoPropuesta:
    """Reparte el aporte entre las categorías por debajo de su objetivo, sin vender nada.

    Los ítems con `accion == "vender"` se descartan a propósito: el sentido de este modo es
    corregir la cartera únicamente con dinero nuevo, así que las sobreponderaciones se diluyen
    comprando el resto en vez de desarmando posiciones (evita costos y hechos imponibles).
    """
    resultado: list[PropuestaItem] = []
    compras = [it for it in items if it.accion == "comprar"]
    otros = [it for it in items if it.accion != "comprar" and it.accion != "vender"]

    necesidad_total = sum(it.importe_sugerido_usd for it in compras)
    prorratea = necesidad_total > aporte_usd + EPS_USD
    factor = (aporte_usd / necesidad_total) if (prorratea and necesidad_total > EPS_USD) else 1.0

    asignado_total = 0.0
    for it in compras:
        importe = it.importe_sugerido_usd * factor
        if peso_maximo_pp is not None and total_efectivo > EPS_USD:
            techo_usd = peso_maximo_pp / 100 * total_efectivo
            importe = max(0.0, min(importe, techo_usd - it.valor_actual_usd))
        asignado_total += importe
        motivo = it.motivo
        if prorratea:
            motivo += " Aporte no alcanza para cerrar todas las brechas; se distribuyó proporcionalmente a la brecha faltante."
        elif peso_maximo_pp is not None and importe < it.importe_sugerido_usd - EPS_USD:
            motivo += f" Limitado por el peso máximo configurado ({peso_maximo_pp:.1f}%)."
        resultado.append(PropuestaItem(
            tipo=it.tipo,
            posicion=it.posicion,
            categoria=it.categoria,
            peso_actual_pct=it.peso_actual_pct,
            peso_objetivo_pct=it.peso_objetivo_pct,
            delta_pp=it.delta_pp,
            valor_actual_usd=it.valor_actual_usd,
            valor_objetivo_usd=it.valor_objetivo_usd,
            importe_sugerido_usd=round(importe, 2),
            accion=_accion_desde_importe(importe),
            necesidad=it.necesidad,
            comision_estimada_usd=_comision(importe, "comprar", tasa_comision_pct) if importe > EPS_USD else 0.0,
            motivo=motivo,
        ))

    resultado.extend(otros)
    sobrante = max(0.0, aporte_usd - asignado_total)
    return ResultadoPropuesta(items=resultado, sobrante_usd=round(sobrante, 2))
