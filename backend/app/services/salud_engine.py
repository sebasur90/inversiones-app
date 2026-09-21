"""Motor puro de "Salud de cartera": estados por dimensión + observaciones, sin score único.

Sin dependencias de `Session`/DB/FastAPI: recibe métricas ya calculadas (por los analytics
existentes) y devuelve estados explicables. Mismo criterio que `diagnostico_engine.py` — de
hecho reutiliza sus umbrales, para que las dos pantallas nunca se contradigan entre sí.

A propósito **no** calcula un score 0-100: cada dimensión tiene tres estados posibles
("normal" / "atencion" / "revisar") más "sin_datos" cuando falta información, y cada estado
declara la regla numérica exacta que lo produjo (`regla`) y de dónde sale el dato (`fuente`).
"""
from datetime import date

from .diagnostico_engine import (
    UMBRAL_DRAWDOWN_ADVERTENCIA,
    UMBRAL_DRAWDOWN_CRITICO,
    UMBRAL_VOLATILIDAD_ADVERTENCIA,
    UMBRAL_VOLATILIDAD_CRITICO,
    UMBRAL_HHI_TICKER_ADVERTENCIA,
    UMBRAL_HHI_TICKER_CRITICO,
    UMBRAL_VENCIMIENTO_DIAS,
    UMBRAL_COMISION_ADVERTENCIA_PCT,
    UMBRAL_COMISION_CRITICO_PCT,
    calcular_ratio_comisiones,
)

# ── Umbrales propios (no cubiertos por diagnostico_engine) ────────────────────────────────

# Concentración por ticker: si `Configuracion.peso_maximo` está cargado en el Sheet, se usa como
# umbral de "atención" y su 1.5x como "revisar" (ver `evaluar_concentracion`); si no, estos
# valores por defecto.
UMBRAL_PESO_TICKER_ATENCION_PCT = 20.0
UMBRAL_PESO_TICKER_REVISAR_PCT = 30.0
FACTOR_PESO_TICKER_REVISAR = 1.5

UMBRAL_PAIS_ATENCION_PCT = 70.0
UMBRAL_PAIS_REVISAR_PCT = 90.0

UMBRAL_EFFECTIVE_N_ATENCION = 5.0
UMBRAL_EFFECTIVE_N_REVISAR = 3.0

UMBRAL_LIQUIDEZ_ATENCION_PCT = 10.0
UMBRAL_LIQUIDEZ_REVISAR_PCT = 5.0

# `tipo_instrumento` y `sector` son texto libre del Sheet: se matchea por substring, sin
# distinguir mayúsculas/minúsculas — mismo criterio que `market_data/precios.py` para clasificar
# familias de instrumentos.
TIPOS_LIQUIDOS = ("fci",)
SECTORES_LIQUIDOS = ("liquidez",)
DIAS_VENCIMIENTO_LIQUIDO = 365

# Umbral de vencimiento próximo agregado (mismo criterio que diagnostico_engine).
UMBRAL_VENCIMIENTO_PROXIMO_DIAS = UMBRAL_VENCIMIENTO_DIAS

RANK_ESTADO = {"revisar": 0, "atencion": 1, "normal": 2, "sin_datos": 3}
RANK_SEVERIDAD = {"revisar": 0, "atencion": 1, "info": 2}
ETIQUETA_ESTADO = {"normal": "Normal", "atencion": "Atención", "revisar": "Revisar", "sin_datos": "Sin datos"}

ORDEN_DIMENSIONES = [
    "riesgo", "concentracion", "diversificacion", "liquidez",
    "costos", "vencimientos", "balance_objetivo", "calidad_datos",
]


def _peor_estado(*estados: str | None) -> str:
    """El estado más severo entre los recibidos, ignorando None. "sin_datos" sólo si no hay
    ningún estado real disponible."""
    reales = [e for e in estados if e is not None]
    if not reales:
        return "sin_datos"
    return min(reales, key=lambda e: RANK_ESTADO[e])


def _dimension(clave: str, nombre: str, estado: str, valor: str, regla: str, explicacion: str,
               fuente: str, pantalla: str, ayuda: str) -> dict:
    return {
        "clave": clave,
        "nombre": nombre,
        "estado": estado,
        "etiqueta": ETIQUETA_ESTADO[estado],
        "valor": valor,
        "regla": regla,
        "explicacion": explicacion,
        "fuente": fuente,
        "pantalla": pantalla,
        "ayuda": ayuda,
    }


def _observacion(id_: str, dimension: str, severidad: str, titulo: str, detecto: str,
                  valor: str, umbral: str, fuente: str, pantalla: str, accion: str) -> dict:
    return {
        "id": id_,
        "dimension": dimension,
        "severidad": severidad,
        "titulo": titulo,
        "detecto": detecto,
        "valor": valor,
        "umbral": umbral,
        "fuente": fuente,
        "pantalla": pantalla,
        "accion": accion,
    }


# ── Dimensiones ─────────────────────────────────────────────────────────────────────────────

def evaluar_riesgo(drawdown: dict, volatilidad: dict) -> dict:
    dd_ok = drawdown.get("estado") == "ok" and drawdown.get("maximo") is not None
    vol_ok = volatilidad.get("estado") == "ok" and volatilidad.get("anualizada") is not None

    if not dd_ok and not vol_ok:
        return _dimension(
            "riesgo", "Riesgo", "sin_datos", "Datos insuficientes",
            "Hace falta más historial de precios mensuales para calcular drawdown y volatilidad.",
            "Con pocos meses de historia todavía no se puede medir con confianza cuánto sube y baja tu cartera.",
            "Riesgo (retornos mensuales en USD)", "/riesgo", "salud_dim_riesgo",
        )

    dd_estado = None
    if dd_ok:
        maximo = drawdown["maximo"]
        dd_estado = "revisar" if maximo <= UMBRAL_DRAWDOWN_CRITICO else "atencion" if maximo <= UMBRAL_DRAWDOWN_ADVERTENCIA else "normal"
    vol_estado = None
    if vol_ok:
        anualizada = volatilidad["anualizada"]
        vol_estado = "revisar" if anualizada >= UMBRAL_VOLATILIDAD_CRITICO else "atencion" if anualizada >= UMBRAL_VOLATILIDAD_ADVERTENCIA else "normal"

    estado = _peor_estado(dd_estado, vol_estado)
    partes = []
    if dd_ok:
        partes.append(f"Caída máx. {drawdown['maximo']*100:.1f}%")
    if vol_ok:
        partes.append(f"volatilidad {volatilidad['anualizada']*100:.1f}% anual")
    valor = " · ".join(partes)

    return _dimension(
        "riesgo", "Riesgo", estado, valor,
        f"Atención si la caída máxima supera {abs(UMBRAL_DRAWDOWN_ADVERTENCIA)*100:.0f}% o la volatilidad "
        f"{UMBRAL_VOLATILIDAD_ADVERTENCIA*100:.0f}% anual; revisar si superan "
        f"{abs(UMBRAL_DRAWDOWN_CRITICO)*100:.0f}% / {UMBRAL_VOLATILIDAD_CRITICO*100:.0f}%.",
        "Cuánto llegó a caer tu cartera desde su punto más alto, y cuánto varía mes a mes.",
        "Riesgo (retornos mensuales en USD)", "/riesgo", "salud_dim_riesgo",
    )


def _umbrales_peso_ticker(peso_maximo: float | None) -> tuple[float, float]:
    atencion = peso_maximo if peso_maximo is not None else UMBRAL_PESO_TICKER_ATENCION_PCT
    revisar = round(atencion * FACTOR_PESO_TICKER_REVISAR, 2) if peso_maximo is not None else UMBRAL_PESO_TICKER_REVISAR_PCT
    return atencion, revisar


def evaluar_concentracion(concentracion: list[dict], exposicion_ticker: list[dict], peso_maximo: float | None) -> dict:
    item = next((c for c in concentracion if c.get("eje") == "Ticker"), None)
    hhi_ok = bool(item) and item.get("estado") == "ok" and item.get("hhi_normalizado") is not None
    top = exposicion_ticker[0] if exposicion_ticker else None

    if not hhi_ok and top is None:
        return _dimension(
            "concentracion", "Concentración", "sin_datos", "Datos insuficientes",
            "No hay posiciones valorizadas todavía.",
            "Muestra cuánto depende tu cartera de pocos instrumentos.",
            "Contribución (HHI) y Exposición › Ticker", "/contribucion", "salud_dim_concentracion",
        )

    atencion_pct, revisar_pct = _umbrales_peso_ticker(peso_maximo)
    hhi_estado = None
    if hhi_ok:
        hhi_norm = item["hhi_normalizado"]
        hhi_estado = "revisar" if hhi_norm >= UMBRAL_HHI_TICKER_CRITICO else "atencion" if hhi_norm >= UMBRAL_HHI_TICKER_ADVERTENCIA else "normal"
    peso_estado = None
    if top is not None:
        pct = top["porcentaje"]
        peso_estado = "revisar" if pct >= revisar_pct else "atencion" if pct >= atencion_pct else "normal"

    estado = _peor_estado(hhi_estado, peso_estado)
    partes = []
    if top is not None:
        partes.append(f"{top['etiqueta']} pesa {top['porcentaje']:.1f}%")
    if hhi_ok:
        partes.append(f"HHI {item['hhi_normalizado']:.3f} (N efectivo {item.get('effective_n') or 0:.1f})")
    valor = " · ".join(partes)

    origen_umbral = f"peso máximo configurado ({peso_maximo:.0f}%) × {FACTOR_PESO_TICKER_REVISAR}" if peso_maximo is not None else "umbral por defecto"
    return _dimension(
        "concentracion", "Concentración", estado, valor,
        f"Atención si una posición supera {atencion_pct:.0f}% de la cartera o el HHI normalizado supera "
        f"{UMBRAL_HHI_TICKER_ADVERTENCIA:.2f}; revisar si superan {revisar_pct:.0f}% ({origen_umbral}) o "
        f"{UMBRAL_HHI_TICKER_CRITICO:.2f}.",
        "Muestra cuánto depende tu cartera de pocos instrumentos.",
        "Contribución (HHI) y Exposición › Ticker", "/contribucion", "salud_dim_concentracion",
    )


def evaluar_diversificacion(concentracion: list[dict]) -> dict:
    item_ticker = next((c for c in concentracion if c.get("eje") == "Ticker"), None)
    if not item_ticker or item_ticker.get("estado") != "ok" or item_ticker.get("effective_n") is None:
        return _dimension(
            "diversificacion", "Diversificación", "sin_datos", "Datos insuficientes",
            "No hay posiciones valorizadas todavía.",
            "Cuántas posiciones 'equivalentes' tiene realmente tu cartera, más allá de la cantidad de tickers.",
            "Contribución (HHI por Ticker y Tipo de instrumento)", "/contribucion", "salud_dim_diversificacion",
        )
    effective_n = item_ticker["effective_n"]
    estado = "revisar" if effective_n < UMBRAL_EFFECTIVE_N_REVISAR else "atencion" if effective_n < UMBRAL_EFFECTIVE_N_ATENCION else "normal"

    item_tipo = next((c for c in concentracion if c.get("eje") == "Tipo de instrumento"), None)
    n_tipos = item_tipo.get("n_componentes") if item_tipo and item_tipo.get("estado") == "ok" else None
    if n_tipos == 1:
        estado = _peor_estado(estado, "atencion")

    valor = f"N efectivo {effective_n:.1f} posiciones"
    if n_tipos is not None:
        valor += f" · {n_tipos} tipo{'s' if n_tipos != 1 else ''} de instrumento"

    return _dimension(
        "diversificacion", "Diversificación", estado, valor,
        f"Atención si el N efectivo es menor a {UMBRAL_EFFECTIVE_N_ATENCION:.0f} o hay un único tipo de "
        f"instrumento; revisar si es menor a {UMBRAL_EFFECTIVE_N_REVISAR:.0f}.",
        "Cuántas posiciones 'equivalentes' tiene realmente tu cartera, más allá de la cantidad de tickers.",
        "Contribución (HHI por Ticker y Tipo de instrumento)", "/contribucion", "salud_dim_diversificacion",
    )


def _es_liquido(item: dict, hoy: date) -> bool:
    tipo = (item.get("tipo_instrumento") or "").strip().lower()
    sector = (item.get("sector") or "").strip().lower()
    if any(t in tipo for t in TIPOS_LIQUIDOS):
        return True
    if any(s in sector for s in SECTORES_LIQUIDOS):
        return True
    venc = item.get("fecha_vencimiento")
    if venc is not None and (venc - hoy).days < DIAS_VENCIMIENTO_LIQUIDO:
        return True
    return False


def calcular_pct_liquido(inventario: list[dict], hoy: date | None = None) -> float | None:
    """% del valor de la cartera en posiciones líquidas (ver `_es_liquido`), o None si no hay
    ninguna posición valorizada. Función compartida entre `evaluar_liquidez` y los indicadores,
    para no calcular el mismo número dos veces."""
    hoy = hoy or date.today()
    con_valor = [it for it in inventario if it.get("valor_usd")]
    total = sum(it["valor_usd"] for it in con_valor)
    if total <= 0:
        return None
    liquido = sum(it["valor_usd"] for it in con_valor if _es_liquido(it, hoy))
    return liquido / total * 100


def evaluar_liquidez(inventario: list[dict], hoy: date | None = None) -> dict:
    pct = calcular_pct_liquido(inventario, hoy)
    if pct is None:
        return _dimension(
            "liquidez", "Liquidez", "sin_datos", "Datos insuficientes",
            "No hay posiciones valorizadas todavía.",
            "Qué parte de tu cartera podrías convertir en efectivo rápido y sin pérdida de valor.",
            "Posiciones (FCI, sector 'Liquidez' o vencimiento menor a 1 año)", "/exposicion", "salud_dim_liquidez",
        )
    estado = "revisar" if pct < UMBRAL_LIQUIDEZ_REVISAR_PCT else "atencion" if pct < UMBRAL_LIQUIDEZ_ATENCION_PCT else "normal"

    return _dimension(
        "liquidez", "Liquidez", estado, f"{pct:.1f}% de la cartera es líquida",
        f"Atención si menos de {UMBRAL_LIQUIDEZ_ATENCION_PCT:.0f}% de la cartera es líquida; revisar si es "
        f"menos de {UMBRAL_LIQUIDEZ_REVISAR_PCT:.0f}%. Se considera líquido un instrumento tipo FCI, con "
        f"sector 'Liquidez' o que vence en menos de 1 año.",
        "Qué parte de tu cartera podrías convertir en efectivo rápido y sin pérdida de valor.",
        "Posiciones (FCI, sector 'Liquidez' o vencimiento menor a 1 año)", "/exposicion", "salud_dim_liquidez",
    )


def evaluar_costos(ratio_comisiones: dict | None) -> dict:
    if ratio_comisiones is None:
        return _dimension(
            "costos", "Costos", "sin_datos", "Datos insuficientes",
            "No hay comisiones registradas en los movimientos.",
            "Cuánto te cuesta operar, expresado como porcentaje anual de tu cartera.",
            "Comisiones (últimos 12 meses, anualizadas)", "/comisiones", "salud_dim_costos",
        )
    ratio = ratio_comisiones["ratio"]
    estado = "revisar" if ratio >= UMBRAL_COMISION_CRITICO_PCT else "atencion" if ratio >= UMBRAL_COMISION_ADVERTENCIA_PCT else "normal"
    return _dimension(
        "costos", "Costos", estado, f"{ratio*100:.2f}% anual (${ratio_comisiones['anualizado_usd']:,.0f})",
        f"Atención si las comisiones anualizadas superan {UMBRAL_COMISION_ADVERTENCIA_PCT*100:.0f}% de la "
        f"cartera; revisar si superan {UMBRAL_COMISION_CRITICO_PCT*100:.0f}%.",
        "Cuánto te cuesta operar, expresado como porcentaje anual de tu cartera.",
        "Comisiones (últimos 12 meses, anualizadas)", "/comisiones", "salud_dim_costos",
    )


def evaluar_vencimientos(vencimientos: list[dict]) -> dict:
    if not vencimientos:
        return _dimension(
            "vencimientos", "Vencimientos", "sin_datos", "No aplica",
            "No tenés instrumentos con fecha de vencimiento (bonos, ONs, letras).",
            "Cuándo vencen tus bonos y si hay que planificar qué hacer con ese dinero.",
            "Vencimientos", "/vencimientos", "salud_dim_vencimientos",
        )
    vencidos = [v for v in vencimientos if v.get("vencido")]
    if vencidos:
        estado = "revisar"
        valor = f"{len(vencidos)} instrumento(s) ya vencido(s)"
    else:
        proximo = min(vencimientos, key=lambda v: v.get("dias_restantes", 9999))
        dias = proximo.get("dias_restantes", 9999)
        if dias <= UMBRAL_VENCIMIENTO_PROXIMO_DIAS:
            estado = "atencion"
            valor = f"{proximo.get('nombre', proximo.get('ticker'))} vence en {dias} días"
        else:
            estado = "normal"
            valor = f"Próximo vencimiento en {dias} días"

    return _dimension(
        "vencimientos", "Vencimientos", estado, valor,
        f"Revisar si hay instrumentos vencidos; atención si algo vence dentro de "
        f"{UMBRAL_VENCIMIENTO_PROXIMO_DIAS} días.",
        "Cuándo vencen tus bonos y si hay que planificar qué hacer con ese dinero.",
        "Vencimientos", "/vencimientos", "salud_dim_vencimientos",
    )


def evaluar_balance_objetivo(rebalanceo_ejes: list[dict], tolerancia_pp: float) -> dict:
    todos_items = [it for eje in rebalanceo_ejes for it in eje.get("items", [])]
    if not todos_items:
        return _dimension(
            "balance_objetivo", "Balance vs. objetivo", "sin_datos", "Sin objetivos cargados",
            "No hay porcentajes objetivo cargados en la pestaña Rebalanceo del Sheet.",
            "Qué tan lejos está tu cartera de los porcentajes objetivo que vos definiste.",
            "Balance de cartera", "/rebalanceo", "salud_dim_balance",
        )
    desviados = [it for it in todos_items if abs(it.get("delta_pp", 0)) > tolerancia_pp]
    if not desviados:
        estado = "normal"
        valor = "Todas las categorías dentro de tolerancia"
    else:
        peor = max(desviados, key=lambda it: abs(it.get("delta_pp", 0)))
        estado = "revisar" if abs(peor["delta_pp"]) >= 3 * tolerancia_pp else "atencion"
        valor = f"{len(desviados)} categoría(s) fuera de tolerancia (mayor: {peor['etiqueta']} {peor['delta_pp']:+.1f}pp)"

    return _dimension(
        "balance_objetivo", "Balance vs. objetivo", estado, valor,
        f"Atención si alguna categoría se desvía más de {tolerancia_pp:.1f}pp de su objetivo; revisar si se "
        f"desvía más de {3*tolerancia_pp:.1f}pp.",
        "Qué tan lejos está tu cartera de los porcentajes objetivo que vos definiste.",
        "Balance de cartera", "/rebalanceo", "salud_dim_balance",
    )


def evaluar_calidad_datos(calidad: dict | None, inventario: list[dict], tiene_precios_desactualizados: bool) -> dict:
    if not calidad or not calidad.get("ultimo_sync"):
        return _dimension(
            "calidad_datos", "Calidad de datos", "sin_datos", "Sin sincronizar",
            "Todavía no se sincronizó el Sheet/Excel con la aplicación.",
            "Qué tan limpios y completos llegaron tus datos en la última sincronización.",
            "Calidad de datos (último sync)", "/calidad-datos", "salud_dim_calidad_datos",
        )
    resultado = calidad["ultimo_sync"].get("resultado")
    estado_sync = "revisar" if resultado == "con_errores" else "atencion" if resultado == "con_advertencias" else "normal"

    sin_precio = [it for it in inventario if it.get("sin_precio")]
    desactualizados = [it for it in inventario if it.get("dias_precio") is not None and it["dias_precio"] > 45]
    sin_clasificar = [it for it in inventario if not it.get("sector") or not it.get("pais")]

    estado_precios = "revisar" if (sin_precio or tiene_precios_desactualizados or desactualizados) else "normal"
    estado_clasificacion = "atencion" if sin_clasificar else "normal"

    estado = _peor_estado(estado_sync, estado_precios, estado_clasificacion)
    partes = [f"Último sync: {resultado.replace('_', ' ')}"]
    if sin_precio:
        partes.append(f"{len(sin_precio)} sin precio")
    if desactualizados:
        partes.append(f"{len(desactualizados)} con precio desactualizado")
    if sin_clasificar:
        partes.append(f"{len(sin_clasificar)} sin sector/país")

    return _dimension(
        "calidad_datos", "Calidad de datos", estado, " · ".join(partes),
        "Revisar si el último sync tuvo errores, o hay posiciones sin precio o con precio de hace más de "
        "45 días; atención si el sync tuvo advertencias o faltan sector/país.",
        "Qué tan limpios y completos llegaron tus datos en la última sincronización.",
        "Calidad de datos (último sync) y Posiciones", "/calidad-datos", "salud_dim_calidad_datos",
    )


# ── Observaciones ("cosas para revisar") ───────────────────────────────────────────────────

def _obs_concentracion(exposicion_ticker: list[dict], peso_maximo: float | None) -> list[dict]:
    atencion_pct, revisar_pct = _umbrales_peso_ticker(peso_maximo)
    obs = []
    for item in exposicion_ticker:
        pct = item["porcentaje"]
        if pct < atencion_pct:
            continue
        severidad = "revisar" if pct >= revisar_pct else "atencion"
        obs.append(_observacion(
            f"peso_ticker:{item['etiqueta']}", "concentracion", severidad,
            f"{item['etiqueta']} representa {pct:.1f}% de la cartera",
            "Una posición individual pesa más que el umbral de concentración.",
            f"{pct:.1f}%", f"{revisar_pct:.0f}% (revisar) / {atencion_pct:.0f}% (atención)",
            "Exposición › Ticker", f"/ticker/{item['etiqueta']}", "Ver posición",
        ))
    return obs


def _obs_balance(rebalanceo_ejes: list[dict], tolerancia_pp: float) -> list[dict]:
    obs = []
    for eje in rebalanceo_ejes:
        for it in eje.get("items", []):
            delta = it.get("delta_pp", 0)
            if abs(delta) <= tolerancia_pp:
                continue
            severidad = "revisar" if abs(delta) >= 3 * tolerancia_pp else "atencion"
            obs.append(_observacion(
                f"balance:{eje['eje']}:{it['etiqueta']}", "balance_objetivo", severidad,
                f"{it['etiqueta']} está {delta:+.1f}pp lejos de su objetivo en {eje['eje'].lower()}",
                "Esta categoría se desvió del porcentaje objetivo configurado.",
                f"{it['porcentaje_actual']:.1f}% actual vs. {it['porcentaje_objetivo']:.1f}% objetivo",
                f"±{tolerancia_pp:.1f}pp de tolerancia",
                "Balance de cartera", "/rebalanceo", "Ver balance de cartera",
            ))
    return obs


def _obs_clasificacion(inventario: list[dict]) -> list[dict]:
    obs = []
    sin_sector = [it["ticker"] for it in inventario if not it.get("sector")]
    sin_pais = [it["ticker"] for it in inventario if not it.get("pais")]
    if sin_sector:
        obs.append(_observacion(
            "sin_sector", "calidad_datos", "atencion",
            f"{len(sin_sector)} instrumento(s) no tienen sector",
            "Faltan datos para clasificar por sector en tu Sheet.",
            ", ".join(sin_sector[:5]) + ("..." if len(sin_sector) > 5 else ""), "Sector completo",
            "Instrumentos (ficha del Sheet)", "/calidad-datos", "Revisar calidad de datos",
        ))
    if sin_pais:
        obs.append(_observacion(
            "sin_pais", "calidad_datos", "atencion",
            f"{len(sin_pais)} instrumento(s) no tienen país",
            "Faltan datos para clasificar por país en tu Sheet.",
            ", ".join(sin_pais[:5]) + ("..." if len(sin_pais) > 5 else ""), "País completo",
            "Instrumentos (ficha del Sheet)", "/calidad-datos", "Revisar calidad de datos",
        ))
    return obs


def _obs_pais(concentracion: list[dict], exposicion_pais: list[dict]) -> list[dict]:
    """País dominante: usa el HHI de `concentracion` (con su bucket residual "Sin país") para
    decidir si hay al menos 2 países reales etiquetados, y el % del eje "País" de `get_exposicion`
    (que ya excluye los sin etiquetar) para el valor mostrado."""
    item = next((c for c in concentracion if c.get("eje") == "País"), None)
    if not item or item.get("estado") != "ok" or not exposicion_pais:
        return []
    n_reales = item.get("n_componentes_reales", item.get("n_componentes"))
    if n_reales is not None and n_reales < 2:
        return []
    top = exposicion_pais[0]
    pct = top["porcentaje"]
    if pct < UMBRAL_PAIS_ATENCION_PCT:
        return []
    severidad = "revisar" if pct >= UMBRAL_PAIS_REVISAR_PCT else "atencion"
    return [_observacion(
        "pais_dominante", "concentracion", severidad,
        f"{pct:.1f}% de la cartera está concentrada en {top['etiqueta']}",
        "Un solo país explica la mayor parte de tu cartera etiquetada.",
        f"{pct:.1f}%", f"{UMBRAL_PAIS_ATENCION_PCT:.0f}% (atención) / {UMBRAL_PAIS_REVISAR_PCT:.0f}% (revisar)",
        "Exposición › País", "/exposicion", "Ver exposición",
    )]


def _obs_precios(inventario: list[dict]) -> list[dict]:
    obs = []
    sin_precio = [it["ticker"] for it in inventario if it.get("sin_precio")]
    desactualizados = [(it["ticker"], it["dias_precio"]) for it in inventario if it.get("dias_precio") is not None and it["dias_precio"] > 45]
    if sin_precio:
        obs.append(_observacion(
            "sin_precio", "calidad_datos", "revisar",
            f"{len(sin_precio)} instrumento(s) sin precio",
            "No hay ninguna cotización cargada para estos tickers.",
            ", ".join(sin_precio[:5]) + ("..." if len(sin_precio) > 5 else ""), "Precio conocido",
            "Precios", "/precios", "Ver precios",
        ))
    if desactualizados:
        peor = max(desactualizados, key=lambda t: t[1])
        obs.append(_observacion(
            "precio_desactualizado", "calidad_datos", "atencion",
            f"{len(desactualizados)} instrumento(s) con precio desactualizado",
            "El último precio cargado tiene más de 45 días.",
            f"{peor[0]}: {peor[1]} días", "45 días",
            "Precios", "/precios", "Ver precios",
        ))
    return obs


def _obs_vencimientos(vencimientos: list[dict]) -> list[dict]:
    obs = []
    vencidos = [v for v in vencimientos if v.get("vencido")]
    if vencidos:
        nombres = ", ".join(v.get("nombre", v.get("ticker", "")) for v in vencidos[:3])
        obs.append(_observacion(
            "vencidos", "vencimientos", "revisar",
            f"{len(vencidos)} instrumento(s) ya vencieron",
            "Estos instrumentos superaron su fecha de vencimiento.",
            nombres, "Fecha de vencimiento ≤ hoy",
            "Vencimientos", "/vencimientos", "Ver vencimientos",
        ))
    proximos = [v for v in vencimientos if not v.get("vencido") and (v.get("dias_restantes") or 9999) <= UMBRAL_VENCIMIENTO_PROXIMO_DIAS]
    if proximos:
        total_usd = sum(v.get("valor_actual_usd") or 0 for v in proximos)
        obs.append(_observacion(
            "vencimiento_proximo", "vencimientos", "atencion",
            f"USD {total_usd:,.0f} vencen en los próximos {UMBRAL_VENCIMIENTO_PROXIMO_DIAS} días",
            "Hay instrumentos por vencer que conviene planificar.",
            f"{len(proximos)} instrumento(s)", f"{UMBRAL_VENCIMIENTO_PROXIMO_DIAS} días",
            "Flujo de caja proyectado", "/flujo-caja", "Ver flujo de caja",
        ))
    return obs


def _obs_costos(ratio_comisiones: dict | None) -> list[dict]:
    if ratio_comisiones is None or ratio_comisiones["ratio"] < UMBRAL_COMISION_ADVERTENCIA_PCT:
        return []
    ratio = ratio_comisiones["ratio"]
    severidad = "revisar" if ratio >= UMBRAL_COMISION_CRITICO_PCT else "atencion"
    return [_observacion(
        "costos", "costos", severidad,
        f"Pagaste ${ratio_comisiones['anualizado_usd']:,.0f} en comisiones anualizadas",
        "Las comisiones de los últimos 12 meses, anualizadas, son relevantes frente al valor de la cartera.",
        f"{ratio*100:.2f}% de la cartera", f"{UMBRAL_COMISION_ADVERTENCIA_PCT*100:.0f}% (atención) / "
        f"{UMBRAL_COMISION_CRITICO_PCT*100:.0f}% (revisar)",
        "Comisiones (últimos 12 meses)", "/comisiones", "Ver comisiones",
    )]


def _obs_liquidez(dim_liquidez: dict) -> list[dict]:
    if dim_liquidez["estado"] not in ("atencion", "revisar"):
        return []
    return [_observacion(
        "liquidez", "liquidez", dim_liquidez["estado"],
        "Tu cartera tiene poca liquidez disponible",
        "Poca parte de la cartera está en instrumentos fácilmente convertibles en efectivo.",
        dim_liquidez["valor"], f"{UMBRAL_LIQUIDEZ_ATENCION_PCT:.0f}% (atención) / {UMBRAL_LIQUIDEZ_REVISAR_PCT:.0f}% (revisar)",
        "Posiciones (FCI, sector 'Liquidez' o vencimiento < 1 año)", "/exposicion", "Ver exposición",
    )]


def _obs_diversificacion(dim_diversificacion: dict) -> list[dict]:
    if dim_diversificacion["estado"] not in ("atencion", "revisar"):
        return []
    return [_observacion(
        "diversificacion", "diversificacion", dim_diversificacion["estado"],
        "Pocas posiciones concentran la mayor parte de tu cartera",
        "El número efectivo de posiciones es bajo: pocos instrumentos explican casi todo el valor.",
        dim_diversificacion["valor"], f"N efectivo < {UMBRAL_EFFECTIVE_N_ATENCION:.0f} (atención) / {UMBRAL_EFFECTIVE_N_REVISAR:.0f} (revisar)",
        "Contribución", "/contribucion", "Ver contribución",
    )]


def _obs_riesgo(dim_riesgo: dict) -> list[dict]:
    if dim_riesgo["estado"] not in ("atencion", "revisar"):
        return []
    return [_observacion(
        "riesgo", "riesgo", dim_riesgo["estado"],
        "El riesgo reciente de tu cartera está elevado",
        dim_riesgo["explicacion"], dim_riesgo["valor"], dim_riesgo["regla"],
        "Riesgo", "/riesgo", "Ver riesgo",
    )]


def _obs_calidad_sync(calidad: dict | None) -> list[dict]:
    if not calidad or not calidad.get("ultimo_sync"):
        return []
    resultado = calidad["ultimo_sync"].get("resultado")
    if resultado not in ("con_errores", "con_advertencias"):
        return []
    n_criticos = calidad["ultimo_sync"].get("filas_error", 0)
    n_adv = calidad["ultimo_sync"].get("filas_advertencia", 0)
    severidad = "revisar" if resultado == "con_errores" else "atencion"
    return [_observacion(
        "sync", "calidad_datos", severidad,
        "La última sincronización tuvo problemas",
        "El último sync con el Sheet/Excel reportó filas con errores o advertencias.",
        f"{n_criticos} crítico(s), {n_adv} advertencia(s)", "0 críticos",
        "Calidad de datos (último sync)", "/calidad-datos", "Revisar calidad de datos",
    )]


def generar_observaciones(
    exposicion_ticker: list[dict],
    peso_maximo: float | None,
    rebalanceo_ejes: list[dict],
    tolerancia_pp: float,
    inventario: list[dict],
    vencimientos: list[dict],
    ratio_comisiones: dict | None,
    calidad: dict | None,
    dim_liquidez: dict,
    dim_diversificacion: dict,
    dim_riesgo: dict,
    concentracion: list[dict],
    exposicion_pais: list[dict],
) -> list[dict]:
    obs = (
        _obs_concentracion(exposicion_ticker, peso_maximo)
        + _obs_balance(rebalanceo_ejes, tolerancia_pp)
        + _obs_clasificacion(inventario)
        + _obs_pais(concentracion, exposicion_pais)
        + _obs_precios(inventario)
        + _obs_vencimientos(vencimientos)
        + _obs_costos(ratio_comisiones)
        + _obs_liquidez(dim_liquidez)
        + _obs_diversificacion(dim_diversificacion)
        + _obs_riesgo(dim_riesgo)
        + _obs_calidad_sync(calidad)
    )
    return sorted(obs, key=lambda o: RANK_SEVERIDAD.get(o["severidad"], 2))


# ── Indicadores (sección "Resumen general") ────────────────────────────────────────────────

def _indicador(clave: str, nombre: str, texto: str, pantalla: str, ayuda: str,
               valor_usd: float | None = None, valor_ars: float | None = None,
               valor_pct: float | None = None) -> dict:
    return {
        "clave": clave, "nombre": nombre, "texto": texto, "pantalla": pantalla, "ayuda": ayuda,
        "valor_usd": valor_usd, "valor_ars": valor_ars, "valor_pct": valor_pct,
    }


def construir_indicadores(
    resumen: dict,
    riesgo: dict,
    concentracion: list[dict],
    exposicion_ticker: list[dict],
    inventario: list[dict],
    ratio_comisiones: dict | None,
    calidad: dict | None,
) -> list[dict]:
    """Indicadores de la sección "Resumen general": todos derivados de analytics ya existentes,
    sin recalcular nada. Los `valor_usd`/`valor_ars` dejan que el frontend elija según el toggle
    ARS/USD; `texto` es un resumen ya armado para cuando no aplica ese toggle."""
    items = [
        _indicador(
            "patrimonio", "Patrimonio", "", "/resumen", "salud_indicador_patrimonio",
            valor_usd=resumen.get("valor_actual_usd"), valor_ars=resumen.get("valor_actual_ars"),
        ),
        _indicador(
            "rendimiento", "Rendimiento (TWR)",
            f"{resumen['twr_usd']*100:+.1f}% USD" if resumen.get("twr_usd") is not None else "—",
            "/rendimiento", "salud_indicador_rendimiento",
            valor_pct=resumen["twr_usd"] * 100 if resumen.get("twr_usd") is not None else None,
        ),
    ]

    drawdown, volatilidad = riesgo.get("drawdown", {}), riesgo.get("volatilidad", {})
    items.append(_indicador(
        "drawdown", "Drawdown máximo",
        f"{drawdown['maximo']*100:.1f}%" if drawdown.get("estado") == "ok" and drawdown.get("maximo") is not None else "—",
        "/riesgo", "salud_indicador_drawdown",
        valor_pct=drawdown["maximo"] * 100 if drawdown.get("estado") == "ok" and drawdown.get("maximo") is not None else None,
    ))
    items.append(_indicador(
        "volatilidad", "Volatilidad anualizada",
        f"{volatilidad['anualizada']*100:.1f}%" if volatilidad.get("estado") == "ok" and volatilidad.get("anualizada") is not None else "—",
        "/riesgo", "salud_indicador_volatilidad",
        valor_pct=volatilidad["anualizada"] * 100 if volatilidad.get("estado") == "ok" and volatilidad.get("anualizada") is not None else None,
    ))

    top = exposicion_ticker[0] if exposicion_ticker else None
    items.append(_indicador(
        "concentracion", "Concentración",
        f"{top['etiqueta']} {top['porcentaje']:.1f}%" if top else "—",
        "/contribucion", "salud_indicador_concentracion",
        valor_pct=top["porcentaje"] if top else None,
    ))

    item_ticker = next((c for c in concentracion if c.get("eje") == "Ticker"), None)
    effective_n = item_ticker.get("effective_n") if item_ticker and item_ticker.get("estado") == "ok" else None
    items.append(_indicador(
        "diversificacion", "Diversificación (N efectivo)",
        f"{effective_n:.1f} posiciones" if effective_n is not None else "—",
        "/contribucion", "salud_indicador_diversificacion",
        valor_pct=effective_n,
    ))

    pct_liquido = calcular_pct_liquido(inventario)
    items.append(_indicador(
        "liquidez", "Liquidez",
        f"{pct_liquido:.1f}% líquida" if pct_liquido is not None else "—",
        "/exposicion", "salud_indicador_liquidez", valor_pct=pct_liquido,
    ))

    items.append(_indicador(
        "costos", "Costos anuales",
        f"{ratio_comisiones['ratio']*100:.2f}%" if ratio_comisiones else "—",
        "/comisiones", "salud_indicador_costos",
        valor_pct=ratio_comisiones["ratio"] * 100 if ratio_comisiones else None,
    ))

    ultimo_sync = calidad.get("ultimo_sync") if calidad else None
    items.append(_indicador(
        "calidad_datos", "Calidad de datos",
        f"Health score {ultimo_sync['health_score']} ({ultimo_sync['resultado'].replace('_', ' ')})" if ultimo_sync else "Sin sincronizar",
        "/calidad-datos", "salud_indicador_calidad_datos",
        valor_pct=ultimo_sync["health_score"] if ultimo_sync else None,
    ))

    return items


# ── Ensamblado final ────────────────────────────────────────────────────────────────────────

def armar_salud(
    cartera: str | None,
    dimensiones: list[dict],
    observaciones: list[dict],
    indicadores: list[dict],
    exposicion_moneda: list[dict],
    exposicion_tipo: list[dict],
) -> dict:
    resumen = {"n_revisar": 0, "n_atencion": 0, "n_normal": 0, "n_sin_datos": 0}
    clave_por_estado = {"revisar": "n_revisar", "atencion": "n_atencion", "normal": "n_normal", "sin_datos": "n_sin_datos"}
    for dim in dimensiones:
        resumen[clave_por_estado[dim["estado"]]] += 1

    return {
        "cartera": cartera,
        "indicadores": indicadores,
        "dimensiones": dimensiones,
        "observaciones": observaciones,
        "exposicion_moneda": exposicion_moneda,
        "exposicion_tipo": exposicion_tipo,
        "resumen": resumen,
        "fecha_calculo": date.today(),
    }
