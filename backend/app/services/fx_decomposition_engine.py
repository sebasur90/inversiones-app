"""Motor puro de descomposición FX: separa efecto cambiario (MEP) del retorno de activos.

Sin dependencias de Session/DB/FastAPI: todas las funciones reciben valores ya calculados
y devuelven dicts planos. Esto lo hace testeable con pytest plano sin fixtures de BD.

Identidad matemática base (cuando MEP disponible en ambos extremos):
  (1 + TWR_ars_nominal) = (1 + TWR_usd) × (MEP_fin / MEP_inicio)

Se verifica esta identidad y se marca si se rompe más allá de tolerancia (sin ocultarla).
"""

TOLERANCIA_IDENTIDAD_FX = 0.0015


def descomponer_retorno_periodo(
    twr_ars: float | None,
    twr_usd: float | None,
    mep_inicio: float | None,
    mep_fin: float | None,
    tolerancia: float = TOLERANCIA_IDENTIDAD_FX,
) -> dict:
    """Descompone retorno ARS en efecto FX (MEP) + retorno de activos (USD).

    Parámetros:
    - twr_ars: TWR del período en ARS nominal (ej. 0.32 = +32%)
    - twr_usd: TWR del período en USD
    - mep_inicio: MEP al inicio del período
    - mep_fin: MEP al fin del período
    - tolerancia: umbral de diferencia porcentual para considerar identidad "verificada"

    Devuelve dict con campos:
    - estado: "ok" | "datos_insuficientes" | "mep_faltante"
    - periodo_desde/hasta: None (se completan a nivel analytics)
    - retorno_total_ars_pct: TWR_ars (None si estado != "ok")
    - retorno_activo_pct: TWR_usd (None si estado != "ok")
    - efecto_fx_pct: (MEP_fin/MEP_inicio - 1) (None si estado != "ok")
    - mep_inicio/mep_fin: valores (None si faltaba)
    - mep_aproximado: bool (se completa a nivel analytics)
    - identidad_verificada: bool (True si (1+twr_ars) ≈ (1+twr_usd)*(1+efecto_fx) dentro de tolerancia)
    """
    if twr_ars is None or twr_usd is None:
        return {
            "estado": "datos_insuficientes",
            "periodo_desde": None,
            "periodo_hasta": None,
            "retorno_total_ars_pct": None,
            "retorno_activo_pct": None,
            "efecto_fx_pct": None,
            "mep_inicio": None,
            "mep_fin": None,
            "mep_aproximado": False,
            "identidad_verificada": True,
        }

    if mep_inicio is None or mep_fin is None:
        return {
            "estado": "mep_faltante",
            "periodo_desde": None,
            "periodo_hasta": None,
            "retorno_total_ars_pct": twr_ars,
            "retorno_activo_pct": twr_usd,
            "efecto_fx_pct": None,
            "mep_inicio": mep_inicio,
            "mep_fin": mep_fin,
            "mep_aproximado": False,
            "identidad_verificada": True,
        }

    efecto_fx = mep_fin / mep_inicio - 1.0

    lhs = 1.0 + twr_ars
    rhs = (1.0 + twr_usd) * (1.0 + efecto_fx)

    identidad_verificada = abs(lhs - rhs) <= tolerancia

    return {
        "estado": "ok",
        "periodo_desde": None,
        "periodo_hasta": None,
        "retorno_total_ars_pct": twr_ars,
        "retorno_activo_pct": twr_usd,
        "efecto_fx_pct": efecto_fx,
        "mep_inicio": mep_inicio,
        "mep_fin": mep_fin,
        "mep_aproximado": False,
        "identidad_verificada": identidad_verificada,
    }


def descomponer_retorno_posicion(
    rendimiento_simple_ars: float | None,
    rendimiento_simple_usd: float | None,
    moneda: str,
    mep_promedio_compra: float | None,
    mep_actual: float | None,
) -> dict:
    """Descompone retorno de una posición en efecto FX + retorno de activos.

    Variante "aproximada" a nivel posición basada en rendimiento simple
    (no TWR, ya que múltiples lotes pueden tener distinto MEP de entrada).

    Parámetros:
    - rendimiento_simple_ars: simple return en ARS (ej. 0.15 = +15%)
    - rendimiento_simple_usd: simple return en USD
    - moneda: "ARS" | "USD" (moneda del instrumento)
    - mep_promedio_compra: MEP promedio ponderado de compras del activo
    - mep_actual: MEP actual

    Devuelve dict con:
    - estado: "ok" | "datos_insuficientes" | "mep_faltante" | "moneda_desconocida"
    - rendimiento_simple_ars_pct: None si estado != "ok"
    - rendimiento_simple_usd_pct: None si estado != "ok"
    - efecto_fx_pct: None si estado != "ok"
    - retorno_activo_pct: None si estado != "ok"
    - aproximado: True siempre (no es TWR)
    """
    if moneda not in ("ARS", "USD"):
        return {
            "estado": "moneda_desconocida",
            "rendimiento_simple_ars_pct": None,
            "rendimiento_simple_usd_pct": None,
            "efecto_fx_pct": None,
            "retorno_activo_pct": None,
            "aproximado": True,
        }

    if rendimiento_simple_ars is None or rendimiento_simple_usd is None:
        return {
            "estado": "datos_insuficientes",
            "rendimiento_simple_ars_pct": None,
            "rendimiento_simple_usd_pct": None,
            "efecto_fx_pct": None,
            "retorno_activo_pct": None,
            "aproximado": True,
        }

    if mep_promedio_compra is None or mep_actual is None:
        return {
            "estado": "mep_faltante",
            "rendimiento_simple_ars_pct": rendimiento_simple_ars,
            "rendimiento_simple_usd_pct": rendimiento_simple_usd,
            "efecto_fx_pct": None,
            "retorno_activo_pct": rendimiento_simple_usd,
            "aproximado": True,
        }

    efecto_fx = mep_actual / mep_promedio_compra - 1.0

    return {
        "estado": "ok",
        "rendimiento_simple_ars_pct": rendimiento_simple_ars,
        "rendimiento_simple_usd_pct": rendimiento_simple_usd,
        "efecto_fx_pct": efecto_fx,
        "retorno_activo_pct": rendimiento_simple_usd,
        "aproximado": True,
    }
