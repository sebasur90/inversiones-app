"""Motor de simulación determinista de escenarios.

Este módulo contiene la lógica pura de proyección financiera.
No tiene dependencias de base de datos ni estado implícito.
Las funciones son deterministas: dados los mismos inputs, siempre producen el mismo output.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
import math


# ─── Constantes defensivas ────────────────────────────────────────────────

TASA_MIN_PCT = -99.0  # Guarda contra 1+i <= 0 en compounding
MESES_MAX_SIMULACION = 1200  # 100 años, tope defensivo


# ─── Tipos (dataclasses) ──────────────────────────────────────────────────

@dataclass
class PosicionSnapshot:
    """Posición en cartera en un punto en el tiempo."""
    ticker: str
    valor_usd: float
    moneda: str  # Moneda nativa del instrumento: "ARS" o "USD"


@dataclass
class PortfolioSnapshot:
    """Estado de la cartera en un punto en el tiempo."""
    fecha: date
    posiciones: list[PosicionSnapshot]
    mep_actual: Optional[float]  # MEP al inicio, None si no disponible
    valor_total_usd: float  # Suma de valores_usd de posiciones
    total_invertido_usd: float  # Capital total aportado históricamente


@dataclass
class EscenarioParams:
    """Parámetros de un escenario de simulación."""
    horizonte_meses: int
    variacion_dolar_pct: float  # Shock de dólar aplicado al MEP inicial (no predicción)
    variacion_por_instrumento: dict[str, float]  # Overrides por ticker
    variacion_por_defecto_pct: float  # Variación aplicada a instrumentos sin override
    aporte_mensual_usd: float
    crecimiento_aporte_anual_pct: float  # Crecimiento anual del aporte
    retiro_mensual_usd: float
    modo_dividendos: str  # "reinvertir_total" | "reinvertir_parcial" | "retirar"
    dividend_yield_anual_pct: float
    pct_dividendo_reinvertido: Optional[float]  # Solo si modo_dividendos == "reinvertir_parcial"
    comision_pct: float  # Comisión sobre aporte bruto
    inflacion_anual_pct: Optional[float]  # Si se provee, computa patrimonio real deflacionado


@dataclass
class PuntoProyeccion:
    """Un punto en la trayectoria de proyección."""
    mes: int
    fecha: str  # YYYY-MM-DD
    valor_usd: float
    capital_aportado_acum_usd: float
    dividendos_acum_usd: float


@dataclass
class ResultadoEscenario:
    """Resultado completo de una simulación."""
    puntos: list[PuntoProyeccion]
    patrimonio_inicial_usd: float
    patrimonio_final_usd: float
    ganancia_perdida_usd: float
    rendimiento_pct: float
    capital_aportado_usd: float
    efecto_mercado_usd: float
    efecto_dolar_usd: float
    dividendos_usd: float
    comisiones_usd: float
    patrimonio_final_real_usd: Optional[float] = None  # Si inflacion_anual_pct


# ─── Presets de escenarios ────────────────────────────────────────────────

PRESETS = {
    "alcista": {
        "variacion_por_defecto_pct": 20.0,
        "variacion_dolar_pct": 5.0,
        "dividend_yield_anual_pct": 2.0,
    },
    "bajista": {
        "variacion_por_defecto_pct": -10.0,
        "variacion_dolar_pct": 10.0,
        "dividend_yield_anual_pct": 1.5,
    },
    "crisis": {
        "variacion_por_defecto_pct": -35.0,
        "variacion_dolar_pct": 60.0,
        "dividend_yield_anual_pct": 0.5,
    },
    "personalizado": {},
}


def resolver_preset(
    tipo_preset: str,
    params_personalizados: Optional[dict] = None
) -> dict:
    """Resuelve un preset de escenario, llenando defaults si corresponde.

    Args:
        tipo_preset: Una de "alcista", "bajista", "crisis", "personalizado".
        params_personalizados: Dict con overrides. Solo para tipo_preset != "personalizado",
                               se llenan los campos faltantes desde PRESETS.

    Returns:
        Dict con los parámetros resueltos (todavía no instancia EscenarioParams).
    """
    if tipo_preset not in PRESETS:
        raise ValueError(f"tipo_preset inválido: {tipo_preset}")

    if tipo_preset == "personalizado":
        return params_personalizados or {}

    # Preset no personalizado: llenar defaults desde PRESETS[tipo_preset]
    preset_defaults = PRESETS[tipo_preset]
    result = dict(preset_defaults)
    if params_personalizados:
        result.update(params_personalizados)
    return result


def _tasa_mensual_desde_anual(tasa_anual_pct: float) -> float:
    """Convierte tasa anual a tasa mensual compuesta.

    Usa el mismo clamp defensivo que el motor TS (proyeccion.ts).
    """
    t = max(tasa_anual_pct, TASA_MIN_PCT)
    if t == 0:
        return 0.0
    return math.pow(1 + t / 100, 1 / 12) - 1


def _aporte_del_mes(base_usd: float, crecimiento_anual_pct: float, mes: int) -> float:
    """Calcula aporte del mes dado crecimiento anual de aportes.

    El aporte crece en escalones anuales (12 meses = 1 año de crecimiento).
    """
    escalon = (mes - 1) // 12
    return base_usd * math.pow(1 + crecimiento_anual_pct / 100, escalon)


def simular_escenario(
    snapshot: PortfolioSnapshot,
    params: EscenarioParams
) -> ResultadoEscenario:
    """Simula un escenario mes a mes.

    Parámetros:
        snapshot: Estado inicial de la cartera.
        params: Parámetros del escenario.

    Retorna:
        ResultadoEscenario con la proyección completa.

    Notas:
        - Horizonte de proyección: params.horizonte_meses meses.
        - FX shock: aplicado como glide lineal mes a mes (no es predicción, es un choque simple).
        - Las posiciones sin precio conocido (no en snapshot) no existen en la proyección.
        - Si snapshot.posiciones está vacío, los aportes se acumulan en un bucket sintético
          que crece a la tasa de variacion_por_defecto_pct.
        - Los aportes y retiros se prorratea entre posiciones (o en el bucket sintético si vacío).
        - Dividendos se calculan portfolio-wide a partir del valor total del mes.
        - Capital aportado = capital_inicial + sum(aportes) - sum(retiros).
        - Rendimiento = ganancia_perdida / capital_aportado (aportes excluidos de retorno).
    """
    if params.horizonte_meses <= 0:
        raise ValueError("horizonte_meses debe ser > 0")
    if params.horizonte_meses > MESES_MAX_SIMULACION:
        raise ValueError(f"horizonte_meses no puede superar {MESES_MAX_SIMULACION}")

    # ─── Setup inicial ─────────────────────────────────────────────────────

    # Posiciones iniciales: si está vacía, usamos un bucket sintético
    posiciones = {pos.ticker: {"valor_usd": pos.valor_usd, "moneda": pos.moneda}
                  for pos in snapshot.posiciones}
    tiene_posiciones = len(posiciones) > 0

    # MEP inicial e interpolación
    mep_inicio = snapshot.mep_actual or 1.0  # Fallback a 1.0 si no disponible
    if snapshot.mep_actual is None:
        # MEP no disponible: el shock de dólar no se aplica.
        mep_horizonte = mep_inicio
    else:
        mep_horizonte = mep_inicio * (1 + params.variacion_dolar_pct / 100)

    # Tasas mensuales por instrumento
    tasas_mensuales = {}
    for ticker in posiciones.keys():
        v_anual = params.variacion_por_instrumento.get(
            ticker, params.variacion_por_defecto_pct
        )
        tasas_mensuales[ticker] = _tasa_mensual_desde_anual(v_anual)

    # Si no hay posiciones, usar una tasa por defecto para el bucket sintético
    if not tiene_posiciones:
        tasa_sintetica = _tasa_mensual_desde_anual(params.variacion_por_defecto_pct)

    # Acumuladores
    valor_total = snapshot.valor_total_usd
    capital_aportado_acum = snapshot.total_invertido_usd
    dividendos_acum = 0.0
    comisiones_acum = 0.0
    puntos = []

    # Punto 0 (mes=0, hoy)
    puntos.append(PuntoProyeccion(
        mes=0,
        fecha=snapshot.fecha.isoformat(),
        valor_usd=valor_total,
        capital_aportado_acum_usd=capital_aportado_acum,
        dividendos_acum_usd=dividendos_acum
    ))

    # ─── Loop mes a mes ────────────────────────────────────────────────────

    for mes in range(1, params.horizonte_meses + 1):
        # 1. Crecer posiciones según su tasa
        if tiene_posiciones:
            for ticker, pos in posiciones.items():
                tasa_m = tasas_mensuales[ticker]
                pos["valor_usd"] *= (1 + tasa_m)
        else:
            # Bucket sintético
            valor_total *= (1 + tasa_sintetica)

        # 2. MEP: interpolación lineal mes a mes
        if snapshot.mep_actual is not None:
            mep_mes = mep_inicio + (mep_horizonte - mep_inicio) * (mes / params.horizonte_meses)
            # Ajustar posiciones ARS por el cambio de MEP
            # (incremento de MEP = ganancia en USD para posiciones ARS)
            if tiene_posiciones:
                mep_mes_anterior = (mep_inicio + (mep_horizonte - mep_inicio) *
                                    ((mes - 1) / params.horizonte_meses))
                mep_cambio_ratio = mep_mes / mep_mes_anterior if mep_mes_anterior > 0 else 1.0
                for ticker, pos in posiciones.items():
                    if pos["moneda"] == "ARS":
                        pos["valor_usd"] *= mep_cambio_ratio

        # 3. Recalcular valor total
        if tiene_posiciones:
            valor_total = sum(pos["valor_usd"] for pos in posiciones.values())

        # 4. Dividendos del mes
        dividendo_mes = valor_total * (params.dividend_yield_anual_pct / 100 / 12)
        dividendos_acum += dividendo_mes

        # 5. Aplicar modo_dividendos
        if params.modo_dividendos == "reinvertir_total":
            # Prorratea el dividendo entre posiciones
            if tiene_posiciones and valor_total > 0:
                for ticker, pos in posiciones.items():
                    pos["valor_usd"] += dividendo_mes * (pos["valor_usd"] / valor_total)
            else:
                valor_total += dividendo_mes
        elif params.modo_dividendos == "reinvertir_parcial":
            pct = params.pct_dividendo_reinvertido or 0.0
            reinvertido = dividendo_mes * (pct / 100)
            if tiene_posiciones and valor_total > 0:
                for ticker, pos in posiciones.items():
                    pos["valor_usd"] += reinvertido * (pos["valor_usd"] / valor_total)
            else:
                valor_total += reinvertido
            # El resto sale de la cartera (no se reinvierte)
        # elif modo == "retirar": dividendos se pagan fuera, no afecta cartera

        # 6. Recalcular valor total tras dividendos
        if tiene_posiciones:
            valor_total = sum(pos["valor_usd"] for pos in posiciones.values())

        # 7. Aporte del mes (antes de comisión)
        aporte_mes = _aporte_del_mes(params.aporte_mensual_usd,
                                      params.crecimiento_aporte_anual_pct, mes)
        aporte_neto = aporte_mes - params.retiro_mensual_usd

        # 8. Comisión sobre aporte bruto
        comision_mes = aporte_mes * (params.comision_pct / 100)
        comisiones_acum += comision_mes

        # 9. Agregar aporte (neto de retiro)
        if aporte_neto != 0:
            if tiene_posiciones and valor_total > 0:
                # Prorratea entre posiciones
                for ticker, pos in posiciones.items():
                    pos["valor_usd"] += aporte_neto * (pos["valor_usd"] / valor_total)
            else:
                valor_total += aporte_neto

        # 10. Recalcular valor total
        if tiene_posiciones:
            valor_total = sum(pos["valor_usd"] for pos in posiciones.values())

        # 11. Actualizar acumuladores
        capital_aportado_acum += aporte_neto

        # 12. Registrar punto
        fecha_mes = snapshot.fecha + timedelta(days=30 * mes)  # Aprox, mes de 30 días
        puntos.append(PuntoProyeccion(
            mes=mes,
            fecha=fecha_mes.isoformat(),
            valor_usd=valor_total,
            capital_aportado_acum_usd=capital_aportado_acum,
            dividendos_acum_usd=dividendos_acum
        ))

    # ─── Descomposición efecto mercado vs efecto dólar ───────────────────

    patrimonio_final = valor_total
    patrimonio_inicial = snapshot.valor_total_usd

    # Si hay shock de dólar, descomponer corriendo el motor sin FX
    # (pero SIN recursión: esta rama ya NO hace descomposición)
    efecto_dolar_usd = 0.0
    if params.variacion_dolar_pct != 0 and len(snapshot.posiciones) > 0:
        # Correr el motor SIN shock de dólar para calcular efecto FX
        # Usamos los mismos parámetros pero con variacion_dolar_pct=0
        # IMPORTANTE: esto no triggea descomposición porque variacion_dolar_pct=0
        params_sin_fx = EscenarioParams(
            horizonte_meses=params.horizonte_meses,
            variacion_dolar_pct=0.0,
            variacion_por_instrumento=params.variacion_por_instrumento,
            variacion_por_defecto_pct=params.variacion_por_defecto_pct,
            aporte_mensual_usd=params.aporte_mensual_usd,
            crecimiento_aporte_anual_pct=params.crecimiento_aporte_anual_pct,
            retiro_mensual_usd=params.retiro_mensual_usd,
            modo_dividendos=params.modo_dividendos,
            dividend_yield_anual_pct=params.dividend_yield_anual_pct,
            pct_dividendo_reinvertido=params.pct_dividendo_reinvertido,
            comision_pct=params.comision_pct,
            inflacion_anual_pct=None,
        )
        resultado_sin_fx = simular_escenario(snapshot, params_sin_fx)
        efecto_dolar_usd = patrimonio_final - resultado_sin_fx.patrimonio_final_usd

    ganancia_perdida = patrimonio_final - capital_aportado_acum
    efecto_mercado = ganancia_perdida - efecto_dolar_usd - dividendos_acum

    # Rendimiento: ganancia_perdida / capital_aportado (excluyendo aportes del retorno)
    rendimiento_pct = (ganancia_perdida / capital_aportado_acum * 100) if capital_aportado_acum != 0 else 0.0

    # Inflación (opcional)
    patrimonio_final_real = None
    if params.inflacion_anual_pct is not None and params.inflacion_anual_pct > 0:
        meses_anos = params.horizonte_meses / 12
        patrimonio_final_real = patrimonio_final / math.pow(
            1 + params.inflacion_anual_pct / 100, meses_anos
        )

    return ResultadoEscenario(
        puntos=puntos,
        patrimonio_inicial_usd=patrimonio_inicial,
        patrimonio_final_usd=patrimonio_final,
        ganancia_perdida_usd=ganancia_perdida,
        rendimiento_pct=rendimiento_pct,
        capital_aportado_usd=capital_aportado_acum,
        efecto_mercado_usd=efecto_mercado,
        efecto_dolar_usd=efecto_dolar_usd,
        dividendos_usd=dividendos_acum,
        comisiones_usd=comisiones_acum,
        patrimonio_final_real_usd=patrimonio_final_real,
    )
