"""Motor puro de hallazgos y score de salud de cartera.

Sin dependencias de Session/DB/FastAPI: recibe métricas ya calculadas y devuelve hallazgos
priorizados + score de salud explicable. Es puro cálculo — nunca escribe, nunca modifica.
Igual que `risk_engine.py` o `rebalanceo_engine.py`.
"""
from datetime import date

# ── Umbrales de hallazgos ──────────────────────────────────────────────────────

UMBRAL_DRAWDOWN_ADVERTENCIA = -0.15
UMBRAL_DRAWDOWN_CRITICO = -0.30

UMBRAL_VOLATILIDAD_ADVERTENCIA = 0.30
UMBRAL_VOLATILIDAD_CRITICO = 0.45

UMBRAL_HHI_TICKER_ADVERTENCIA = 0.15
UMBRAL_HHI_TICKER_CRITICO = 0.25

FACTOR_REBALANCEO_CRITICO = 3.0

UMBRAL_VENCIMIENTO_DIAS = 90

UMBRAL_OBJETIVO_DEFICIT_CRITICO_PCT = 0.20

UMBRAL_COMISION_ADVERTENCIA_PCT = 0.01
UMBRAL_COMISION_CRITICO_PCT = 0.02
MESES_TRAILING_COMISIONES = 12

# ── Parámetros del score de salud (0-100 por dimensión) ──────────────────────

DD_REF_ANUALIZADO = 0.40
VOL_REF_ANUALIZADO = 0.50
CAGR_REF_ABSOLUTO = 0.15
EXCESO_REF_VS_BENCHMARK = 0.20
FACTOR_DEFICIT_OBJETIVO = 2.0

PESO_RIESGO = 25
PESO_CONCENTRACION = 20
PESO_DIVERSIFICACION = 15
PESO_PERFORMANCE = 20
PESO_OBJETIVO = 20

SEVERIDAD_RANK = {"critico": 0, "advertencia": 1, "info": 2}
TIPO_PRIORIDAD = [
    "stop_loss_disparado",
    "drawdown_elevado",
    "objetivo_inversion_riesgo",
    "objetivo_patrimonio_desviado",
    "vencimiento_proximo",
    "concentracion_alta",
    "rebalanceo_necesario",
    "comision_elevada",
    "volatilidad_elevada",
    "objetivo_precio_alcanzado",
]


# ── Utilidades ─────────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ── Funciones evaluadoras ──────────────────────────────────────────────────────

def evaluar_drawdown(drawdown: dict) -> dict | None:
    """Evalúa el drawdown máximo histórico."""
    if drawdown.get("estado") != "ok" or drawdown.get("maximo") is None:
        return None
    maximo = drawdown["maximo"]
    if maximo > UMBRAL_DRAWDOWN_ADVERTENCIA:
        return None
    severidad = "critico" if maximo <= UMBRAL_DRAWDOWN_CRITICO else "advertencia"
    return {
        "tipo": "drawdown_elevado",
        "severidad": severidad,
        "titulo": "Drawdown elevado" if severidad == "critico" else "Drawdown moderado",
        "explicacion": f"La cartera cayó {abs(maximo)*100:.1f}% en el peor momento de su historia.",
        "dato_disparador": {"drawdown_maximo_pct": round(maximo * 100, 1)},
        "pantalla": "/riesgo",
        "fecha_calculo": date.today(),
    }


def evaluar_volatilidad(volatilidad: dict) -> dict | None:
    """Evalúa la volatilidad anualizada."""
    if volatilidad.get("estado") != "ok" or volatilidad.get("anualizada") is None:
        return None
    anualizada = volatilidad["anualizada"]
    if anualizada < UMBRAL_VOLATILIDAD_ADVERTENCIA:
        return None
    severidad = "critico" if anualizada >= UMBRAL_VOLATILIDAD_CRITICO else "advertencia"
    return {
        "tipo": "volatilidad_elevada",
        "severidad": severidad,
        "titulo": "Volatilidad elevada" if severidad == "critico" else "Volatilidad moderada",
        "explicacion": f"Las variaciones mes a mes alcanzan {anualizada*100:.1f}% anualizadas.",
        "dato_disparador": {"volatilidad_anualizada_pct": round(anualizada * 100, 1)},
        "pantalla": "/riesgo",
        "fecha_calculo": date.today(),
    }


def evaluar_concentracion(concentracion: list[dict]) -> dict | None:
    """Evalúa la concentración por eje Ticker (posición individual)."""
    item = next((c for c in concentracion if c.get("eje") == "Ticker"), None)
    if not item or item.get("estado") != "ok" or item.get("hhi_normalizado") is None:
        return None
    hhi_norm = item["hhi_normalizado"]
    if hhi_norm < UMBRAL_HHI_TICKER_ADVERTENCIA:
        return None
    severidad = "critico" if hhi_norm >= UMBRAL_HHI_TICKER_CRITICO else "advertencia"
    effective_n = item.get("effective_n", 0)
    return {
        "tipo": "concentracion_alta",
        "severidad": severidad,
        "titulo": "Concentración crítica" if severidad == "critico" else "Concentración elevada",
        "explicacion": f"Pocas posiciones dominan tu cartera (equivalente a ~{effective_n:.1f} posiciones diversificadas).",
        "dato_disparador": {"hhi_normalizado": round(hhi_norm, 3), "effective_n": round(effective_n, 1)},
        "pantalla": "/contribucion",
        "fecha_calculo": date.today(),
    }


def evaluar_rebalanceo(rebalanceo_ejes: list[dict], tolerancia_pp: float) -> dict | None:
    """Evalúa si hay posiciones fuera de tolerancia (eje Ticker)."""
    eje_ticker = next((e for e in rebalanceo_ejes if e.get("eje") == "Ticker"), None)
    if not eje_ticker:
        return None
    items = eje_ticker.get("items", [])
    necesarios = [it for it in items if abs(it.get("delta_pp", 0)) > tolerancia_pp]
    if not necesarios:
        return None
    peor = max(necesarios, key=lambda it: abs(it.get("delta_pp", 0)))
    severidad = "critico" if abs(peor.get("delta_pp", 0)) >= FACTOR_REBALANCEO_CRITICO * tolerancia_pp else "advertencia"
    return {
        "tipo": "rebalanceo_necesario",
        "severidad": severidad,
        "titulo": "Rebalanceo crítico necesario" if severidad == "critico" else "Rebalanceo recomendado",
        "explicacion": f"{len(necesarios)} posición(es) fuera de tolerancia. La mayor desviación es {peor.get('etiqueta', 'desconocida')} con {abs(peor.get('delta_pp', 0)):.1f}pp de delta.",
        "dato_disparador": {
            "posiciones_fuera_tolerancia": len(necesarios),
            "peor_posicion": peor.get("etiqueta", ""),
            "peor_delta_pp": round(peor.get("delta_pp", 0), 2),
        },
        "pantalla": "/rebalanceo",
        "fecha_calculo": date.today(),
    }


def evaluar_stop_loss(rendimiento_por_ticker: list[dict]) -> dict | None:
    """Evalúa si hay posiciones con stop-loss disparado."""
    disparados = [it for it in rendimiento_por_ticker if it.get("stop_loss_disparado")]
    if not disparados:
        return None
    nombres = [it.get("nombre", it.get("ticker", "desconocido")) for it in disparados]
    return {
        "tipo": "stop_loss_disparado",
        "severidad": "critico",
        "titulo": "Stop-loss disparado",
        "explicacion": f"{len(disparados)} posición(es) alcanzó su precio de stop-loss: {', '.join(nombres[:3])}{'...' if len(nombres) > 3 else ''}.",
        "dato_disparador": {
            "tickers": [it.get("ticker", "") for it in disparados],
            "cantidad": len(disparados),
        },
        "pantalla": "/posiciones",
        "fecha_calculo": date.today(),
    }


def evaluar_objetivo_precio(rendimiento_por_ticker: list[dict]) -> dict | None:
    """Evalúa si hay posiciones con objetivo de precio alcanzado."""
    alcanzados = [it for it in rendimiento_por_ticker if it.get("objetivo_alcanzado")]
    if not alcanzados:
        return None
    nombres = [it.get("nombre", it.get("ticker", "desconocido")) for it in alcanzados]
    return {
        "tipo": "objetivo_precio_alcanzado",
        "severidad": "info",
        "titulo": "Objetivo de precio alcanzado",
        "explicacion": f"{len(alcanzados)} posición(es) alcanzó su objetivo de precio: {', '.join(nombres[:3])}{'...' if len(nombres) > 3 else ''}. Considera tomar ganancias.",
        "dato_disparador": {
            "tickers": [it.get("ticker", "") for it in alcanzados],
            "cantidad": len(alcanzados),
        },
        "pantalla": "/posiciones",
        "fecha_calculo": date.today(),
    }


def evaluar_objetivo_inversion(objetivo: dict | None) -> dict | None:
    """Evalúa si el objetivo de inversión de la cartera está en riesgo."""
    if objetivo is None or objetivo.get("alcanzable"):
        return None
    monto_usd = objetivo.get("monto_usd", 0)
    deficit_usd = objetivo.get("deficit_usd", 0)
    if monto_usd <= 0:
        return None
    ratio_deficit = deficit_usd / monto_usd
    severidad = "critico" if ratio_deficit >= UMBRAL_OBJETIVO_DEFICIT_CRITICO_PCT else "advertencia"
    deficit_meses = objetivo.get("meses_restantes", 0)
    return {
        "tipo": "objetivo_inversion_riesgo",
        "severidad": severidad,
        "titulo": "Objetivo de inversión en riesgo",
        "explicacion": f"Te faltan ${deficit_usd:,.0f} para alcanzar tu objetivo de ${monto_usd:,.0f} en {deficit_meses} meses. Al ritmo actual no lo lograrás.",
        "dato_disparador": {
            "deficit_usd": round(deficit_usd, 2),
            "monto_objetivo_usd": round(monto_usd, 2),
            "deficit_pct": round(ratio_deficit * 100, 1),
            "meses_restantes": deficit_meses,
        },
        "pantalla": "/objetivo",
        "fecha_calculo": date.today(),
    }


def evaluar_vencimientos(vencimientos: list[dict]) -> dict | None:
    """Evalúa vencimientos próximos o vencidos."""
    if not vencimientos:
        return None
    vencidos = [v for v in vencimientos if v.get("vencido")]
    if vencidos:
        nombres = [v.get("nombre", v.get("ticker", "")) for v in vencidos[:3]]
        return {
            "tipo": "vencimiento_proximo",
            "severidad": "critico",
            "titulo": "Posiciones vencidas",
            "explicacion": f"{len(vencidos)} instrumento(s) ya vencieron: {', '.join(nombres)}{'...' if len(vencidos) > 3 else ''}.",
            "dato_disparador": {
                "cantidad_vencidos": len(vencidos),
                "tickers": [v.get("ticker", "") for v in vencidos],
            },
            "pantalla": "/vencimientos",
            "fecha_calculo": date.today(),
        }
    proximo = min(vencimientos, key=lambda v: v.get("dias_restantes", 9999))
    dias = proximo.get("dias_restantes", 0)
    if dias > UMBRAL_VENCIMIENTO_DIAS:
        return None
    return {
        "tipo": "vencimiento_proximo",
        "severidad": "advertencia",
        "titulo": "Vencimiento próximo",
        "explicacion": f"{proximo.get('nombre', proximo.get('ticker', ''))} vence en {dias} días.",
        "dato_disparador": {
            "ticker_proximo": proximo.get("ticker", ""),
            "dias_restantes": dias,
            "fecha_vencimiento": str(proximo.get("fecha_vencimiento", "")),
        },
        "pantalla": "/vencimientos",
        "fecha_calculo": date.today(),
    }


def evaluar_comisiones(comisiones: dict, valor_actual_usd: float) -> dict | None:
    """Evalúa si la comisión anualizada es elevada."""
    if valor_actual_usd <= 0:
        return None
    por_mes = comisiones.get("por_mes", [])
    if not por_mes:
        return None
    por_mes_sorted = sorted(por_mes, key=lambda p: p.get("periodo", ""))
    trailing = por_mes_sorted[-MESES_TRAILING_COMISIONES:]
    total_trailing = sum(p.get("total_usd", 0) for p in trailing)
    meses_cubiertos = len(trailing)
    if meses_cubiertos == 0:
        return None
    anualizado = total_trailing * (12 / meses_cubiertos)
    ratio = anualizado / valor_actual_usd
    if ratio < UMBRAL_COMISION_ADVERTENCIA_PCT:
        return None
    severidad = "critico" if ratio >= UMBRAL_COMISION_CRITICO_PCT else "advertencia"
    return {
        "tipo": "comision_elevada",
        "severidad": severidad,
        "titulo": "Comisión elevada" if severidad == "critico" else "Comisión moderada",
        "explicacion": f"Pagaste ${anualizado:,.0f} en comisiones anualizadas ({ratio*100:.2f}% de tu cartera).",
        "dato_disparador": {
            "comision_anualizada_usd": round(anualizado, 2),
            "comision_pct_cartera": round(ratio * 100, 2),
            "meses_cubiertos": meses_cubiertos,
        },
        "pantalla": "/comisiones",
        "fecha_calculo": date.today(),
    }


def priorizar_hallazgos(hallazgos: list[dict]) -> list[dict]:
    """Ordena hallazgos por severidad (crítico primero) y luego por TIPO_PRIORIDAD."""
    return sorted(
        hallazgos,
        key=lambda h: (SEVERIDAD_RANK.get(h.get("severidad", "info"), 2), TIPO_PRIORIDAD.index(h.get("tipo", "")) if h.get("tipo", "") in TIPO_PRIORIDAD else 999),
    )


# ── Funciones de score ─────────────────────────────────────────────────────────

def score_riesgo(drawdown: dict, volatilidad: dict) -> dict | None:
    """Score compuesto de riesgo (drawdown + volatilidad)."""
    partes = []
    if drawdown.get("estado") == "ok" and drawdown.get("maximo") is not None:
        dd_score = _clamp(100 - abs(drawdown["maximo"]) / DD_REF_ANUALIZADO * 100)
        partes.append(dd_score)
    if volatilidad.get("estado") == "ok" and volatilidad.get("anualizada") is not None:
        vol_score = _clamp(100 - volatilidad["anualizada"] / VOL_REF_ANUALIZADO * 100)
        partes.append(vol_score)
    if not partes:
        return None
    promedio = sum(partes) / len(partes)
    dd_val = drawdown.get("maximo")
    vol_val = volatilidad.get("anualizada")
    detalle = f"Drawdown máx. {abs(dd_val)*-100:.1f}%" if dd_val else "Drawdown: datos insuficientes"
    if vol_val:
        detalle += f", volatilidad {vol_val*100:.1f}% anualizada"
    return {"score": round(promedio, 1), "detalle": detalle}


def score_concentracion(concentracion: list[dict]) -> dict | None:
    """Score de concentración (eje Ticker)."""
    item = next((c for c in concentracion if c.get("eje") == "Ticker"), None)
    if not item or item.get("estado") != "ok" or item.get("hhi_normalizado") is None:
        return None
    score = _clamp((1 - item["hhi_normalizado"]) * 100)
    detalle = f"HHI normalizado {item.get('hhi_normalizado', 0):.3f}, N efectivo {item.get('effective_n', 0):.1f}"
    return {"score": round(score, 1), "detalle": detalle}


def score_diversificacion(concentracion: list[dict]) -> dict | None:
    """Score de diversificación (promedio de HHI sobre 3 ejes)."""
    ejes_diversificacion = ("Tipo de instrumento", "Sector", "Mercado")
    valores = [
        (1 - c.get("hhi_normalizado", 0)) * 100
        for c in concentracion
        if c.get("eje") in ejes_diversificacion and c.get("estado") == "ok"
    ]
    if not valores:
        return None
    score = _clamp(sum(valores) / len(valores))
    detalle = f"Diversificación en {len(valores)} ejes (tipo, sector, mercado)"
    return {"score": round(score, 1), "detalle": detalle}


def score_performance(calmar: dict, benchmark_retorno_anualizado: float | None) -> dict | None:
    """Score de performance (CAGR vs benchmark o vs referencia absoluta)."""
    if calmar.get("estado") != "ok" or calmar.get("retorno_anualizado") is None:
        return None
    cagr = calmar["retorno_anualizado"]
    if benchmark_retorno_anualizado is not None:
        exceso = cagr - benchmark_retorno_anualizado
        score = _clamp(50 + (exceso / EXCESO_REF_VS_BENCHMARK) * 50)
        detalle = f"CAGR {cagr*100:.1f}% vs benchmark {benchmark_retorno_anualizado*100:.1f}% (exceso {exceso*100:+.1f}pp)"
    else:
        score = _clamp((cagr / CAGR_REF_ABSOLUTO) * 100)
        detalle = f"CAGR {cagr*100:.1f}% (sin benchmark)"
    return {"score": round(score, 1), "detalle": detalle}


def score_objetivo(objetivo: dict | None) -> dict | None:
    """Score de cumplimiento de objetivo."""
    if objetivo is None:
        return None
    if objetivo.get("alcanzable"):
        return {"score": 100.0, "detalle": "Objetivo alcanzable al ritmo actual"}
    monto_usd = objetivo.get("monto_usd", 0)
    deficit_usd = objetivo.get("deficit_usd", 0)
    if monto_usd <= 0:
        return None
    ratio_deficit = deficit_usd / monto_usd
    score = _clamp(100 - ratio_deficit * 100 * FACTOR_DEFICIT_OBJETIVO)
    detalle = f"Avance {(1-ratio_deficit)*100:.1f}%, faltan {deficit_usd:,.0f} USD"
    return {"score": round(score, 1), "detalle": detalle}


def calcular_salud_cartera(dimensiones_raw: dict[str, dict | None]) -> dict:
    """Calcula score total de salud renormalizando pesos por dimensiones presentes."""
    pesos = {
        "riesgo": PESO_RIESGO,
        "concentracion": PESO_CONCENTRACION,
        "diversificacion": PESO_DIVERSIFICACION,
        "performance": PESO_PERFORMANCE,
        "objetivo": PESO_OBJETIVO,
    }
    presentes = {k: v for k, v in dimensiones_raw.items() if v is not None}
    peso_presente_total = sum(pesos[k] for k in presentes)

    score_total = None
    if presentes:
        score_total = round(
            sum(v["score"] * pesos[k] for k, v in presentes.items()) / peso_presente_total, 1
        )

    dimensiones = [
        {
            "nombre": k,
            "score": dimensiones_raw[k]["score"] if dimensiones_raw[k] else None,
            "peso": pesos[k],
            "estado": "ok" if dimensiones_raw[k] else "excluida",
            "detalle": dimensiones_raw[k]["detalle"] if dimensiones_raw[k] else "Datos insuficientes",
        }
        for k in pesos
    ]

    return {
        "score_total": score_total,
        "dimensiones": dimensiones,
        "fecha_calculo": date.today(),
    }
