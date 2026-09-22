"""Motor de 'Escenarios de vida': capa sencilla sobre el simulador de escenarios.

Traduce 7 preguntas cotidianas ("¿qué pasa si aporto más?", "¿qué pasa si dejo de
aportar?", ...) a `escenario_engine.EscenarioParams` y delega toda la matemática en
`escenario_engine.simular_escenario`. No reimplementa proyección: arma un
`PortfolioSnapshot` sintético (sin posiciones, sin MEP) que convierte al motor en
una calculadora de interés compuesto agnóstica de moneda.

Puro, sin dependencias de base de datos. Determinista.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import calendar
import math

from app.services import escenario_engine as ee


DISCLAIMER = "Simulación matemática basada en los supuestos ingresados."

MONEDAS_VALIDAS = ("USD", "ARS")

TIPO_BASE = "continuar_igual"
TIPOS_VIDA = (
    "continuar_igual",
    "aumentar_aporte",
    "disminuir_aporte",
    "dejar_de_aportar",
    "aporte_extraordinario",
    "retiro_extraordinario",
    "aumentar_aportes_anualmente",
)
TIPOS_CON_MONTO_O_PCT = ("aumentar_aporte", "disminuir_aporte")
TIPOS_EXTRAORDINARIOS = ("aporte_extraordinario", "retiro_extraordinario")


# ─── Tipos (dataclasses) ──────────────────────────────────────────────────

@dataclass
class SupuestosVida:
    """Supuestos compartidos por todos los escenarios de una comparación.

    `moneda` es sólo una unidad de cuenta: la simulación corre entera en esa unidad,
    sin MEP ni conversión. La diferencia entre ARS y USD la absorbe `inflacion_anual_pct`.
    """
    patrimonio_inicial: float
    aporte_mensual: float
    crecimiento_anual_pct: float
    horizonte_meses: int
    moneda: str = "USD"
    inflacion_anual_pct: Optional[float] = None


@dataclass
class EscenarioVidaSpec:
    """Un escenario de vida a simular contra los supuestos."""
    tipo: str
    monto: Optional[float] = None  # nuevo aporte mensual, o monto del extraordinario
    pct: Optional[float] = None    # % de cambio del aporte, o crecimiento anual de aportes
    mes: Optional[int] = None      # sólo aporte/retiro extraordinario


@dataclass
class PuntoVida:
    mes: int
    fecha: str                          # calendario real, no timedelta(days=30*mes)
    valor: float
    valor_real: Optional[float]         # deflactado; None si no hay inflación cargada
    aportado_acum: float                # del período, SIN el patrimonio inicial


@dataclass
class MetricasVida:
    patrimonio_final: float
    patrimonio_final_real: Optional[float]
    aportes_periodo: float              # neto del período (puede ser negativo con un retiro)
    crecimiento_estimado: float
    diferencia_vs_base: float           # 0.0 en la base
    diferencia_vs_base_pct: Optional[float]


@dataclass
class ResultadoVida:
    tipo: str
    nombre: str
    descripcion: str
    es_base: bool
    aporte_mensual_efectivo: float
    crecimiento_aporte_anual_pct: float
    mes_flujo_extraordinario: Optional[int]
    monto_flujo_extraordinario: Optional[float]
    se_agota_en_mes: Optional[int]
    puntos: list[PuntoVida]
    metricas: MetricasVida
    advertencias: list[str] = field(default_factory=list)


@dataclass
class ComparacionVida:
    supuestos: SupuestosVida
    resultados: list[ResultadoVida]     # resultados[0] es SIEMPRE la base
    disclaimer: str = DISCLAIMER
    advertencias: list[str] = field(default_factory=list)


# ─── Validación ────────────────────────────────────────────────────────────

def validar(supuestos: SupuestosVida, especificaciones: list[EscenarioVidaSpec]) -> None:
    """Levanta ValueError con mensaje en castellano si algo no cierra."""
    if supuestos.horizonte_meses <= 0:
        raise ValueError("horizonte_meses debe ser > 0")
    if supuestos.horizonte_meses > ee.MESES_MAX_SIMULACION:
        raise ValueError(f"horizonte_meses no puede superar {ee.MESES_MAX_SIMULACION}")
    if supuestos.moneda not in MONEDAS_VALIDAS:
        raise ValueError(f"moneda inválida: {supuestos.moneda}. Válidas: {MONEDAS_VALIDAS}")
    if not especificaciones:
        raise ValueError("Debe especificarse al menos un escenario")

    for spec in especificaciones:
        if spec.tipo not in TIPOS_VIDA:
            raise ValueError(f"tipo de escenario inválido: {spec.tipo}. Válidos: {TIPOS_VIDA}")

        if spec.tipo in TIPOS_CON_MONTO_O_PCT and spec.monto is None and spec.pct is None:
            raise ValueError(f"'{spec.tipo}' requiere 'monto' o 'pct'")

        if spec.tipo == "aumentar_aportes_anualmente" and spec.pct is None:
            raise ValueError("'aumentar_aportes_anualmente' requiere 'pct'")

        if spec.tipo in TIPOS_EXTRAORDINARIOS:
            if spec.monto is None:
                raise ValueError(f"'{spec.tipo}' requiere 'monto'")
            if spec.mes is None:
                raise ValueError(f"'{spec.tipo}' requiere 'mes'")
            if not (1 <= spec.mes <= supuestos.horizonte_meses):
                raise ValueError(
                    f"'mes' debe estar entre 1 y {supuestos.horizonte_meses} (horizonte_meses)"
                )


# ─── Traducción a EscenarioParams ──────────────────────────────────────────

def _snapshot_sintetico(supuestos: SupuestosVida, hoy: date) -> ee.PortfolioSnapshot:
    """Cartera sin posiciones ni MEP: el motor la trata como un bucket sintético
    que crece a `variacion_por_defecto_pct`, agnóstico de la unidad monetaria."""
    return ee.PortfolioSnapshot(
        fecha=hoy,
        posiciones=[],
        mep_actual=None,
        valor_total_usd=supuestos.patrimonio_inicial,
        total_invertido_usd=supuestos.patrimonio_inicial,
    )


def _params_de_escenario(supuestos: SupuestosVida, spec: EscenarioVidaSpec) -> ee.EscenarioParams:
    aporte_mensual = supuestos.aporte_mensual
    crecimiento_aporte_anual_pct = 0.0
    flujos_extraordinarios: list[ee.FlujoExtraordinario] = []

    if spec.tipo == TIPO_BASE:
        pass
    elif spec.tipo == "aumentar_aporte":
        aporte_mensual = (
            spec.monto if spec.monto is not None
            else supuestos.aporte_mensual * (1 + (spec.pct or 0.0) / 100)
        )
    elif spec.tipo == "disminuir_aporte":
        nuevo = (
            spec.monto if spec.monto is not None
            else supuestos.aporte_mensual * (1 - (spec.pct or 0.0) / 100)
        )
        aporte_mensual = max(0.0, nuevo)
    elif spec.tipo == "dejar_de_aportar":
        aporte_mensual = 0.0
    elif spec.tipo == "aporte_extraordinario":
        flujos_extraordinarios = [ee.FlujoExtraordinario(mes=spec.mes, monto_usd=abs(spec.monto or 0.0))]
    elif spec.tipo == "retiro_extraordinario":
        flujos_extraordinarios = [ee.FlujoExtraordinario(mes=spec.mes, monto_usd=-abs(spec.monto or 0.0))]
    elif spec.tipo == "aumentar_aportes_anualmente":
        crecimiento_aporte_anual_pct = spec.pct or 0.0
    else:
        raise ValueError(f"tipo de escenario inválido: {spec.tipo}")

    return ee.EscenarioParams(
        horizonte_meses=supuestos.horizonte_meses,
        variacion_dolar_pct=0.0,
        variacion_por_instrumento={},
        variacion_por_defecto_pct=supuestos.crecimiento_anual_pct,
        aporte_mensual_usd=aporte_mensual,
        crecimiento_aporte_anual_pct=crecimiento_aporte_anual_pct,
        retiro_mensual_usd=0.0,
        modo_dividendos="reinvertir_total",
        dividend_yield_anual_pct=0.0,
        pct_dividendo_reinvertido=None,
        comision_pct=0.0,
        inflacion_anual_pct=None,  # la deflación de la serie la hace esta capa, no el motor
        flujos_extraordinarios=flujos_extraordinarios,
    )


def _nombre_y_descripcion(supuestos: SupuestosVida, spec: EscenarioVidaSpec) -> tuple[str, str]:
    m = supuestos.moneda
    if spec.tipo == TIPO_BASE:
        return (
            "Continuar igual",
            f"Seguís aportando {supuestos.aporte_mensual:,.0f} {m} por mes, sin cambios.",
        )
    if spec.tipo == "aumentar_aporte":
        nuevo = (
            spec.monto if spec.monto is not None
            else supuestos.aporte_mensual * (1 + (spec.pct or 0.0) / 100)
        )
        return (
            f"Aportar {nuevo:,.0f} {m} por mes",
            f"Tu aporte mensual pasa de {supuestos.aporte_mensual:,.0f} a {nuevo:,.0f} {m}.",
        )
    if spec.tipo == "disminuir_aporte":
        nuevo = max(0.0, (
            spec.monto if spec.monto is not None
            else supuestos.aporte_mensual * (1 - (spec.pct or 0.0) / 100)
        ))
        return (
            f"Aportar {nuevo:,.0f} {m} por mes",
            f"Tu aporte mensual baja de {supuestos.aporte_mensual:,.0f} a {nuevo:,.0f} {m}.",
        )
    if spec.tipo == "dejar_de_aportar":
        return (
            "Dejar de aportar",
            "Dejás de aportar desde el primer mes; el patrimonio inicial sigue creciendo solo.",
        )
    if spec.tipo == "aporte_extraordinario":
        monto = abs(spec.monto or 0.0)
        return (
            f"Aportar {monto:,.0f} {m} extra",
            f"Sumás un aporte único de {monto:,.0f} {m} en el mes {spec.mes}.",
        )
    if spec.tipo == "retiro_extraordinario":
        monto = abs(spec.monto or 0.0)
        return (
            f"Retirar {monto:,.0f} {m}",
            f"Retirás {monto:,.0f} {m} en el mes {spec.mes}.",
        )
    if spec.tipo == "aumentar_aportes_anualmente":
        pct = spec.pct or 0.0
        return (
            f"Aumentar aportes {pct:.0f}% por año",
            f"Tu aporte mensual sube {pct:.0f}% cada 12 meses "
            "(el primer aumento impacta en el mes 13, no en el mes 2).",
        )
    return spec.tipo, ""


# ─── Post-proceso: fechas e inflación ──────────────────────────────────────

def _fecha_mes(inicio: date, mes: int) -> date:
    """Fecha `mes` meses de calendario después de `inicio` (no timedelta de 30 días)."""
    total = inicio.month - 1 + mes
    anio = inicio.year + total // 12
    mes_num = total % 12 + 1
    ultimo_dia_del_mes = calendar.monthrange(anio, mes_num)[1]
    dia = min(inicio.day, ultimo_dia_del_mes)
    return date(anio, mes_num, dia)


def _deflactar(valor: float, mes: int, inflacion_anual_pct: Optional[float]) -> Optional[float]:
    """Poder de compra de `valor` en moneda de hoy, a `inflacion_anual_pct` anual.

    Usa el mismo exponente que `escenario_engine` para el valor final, de forma que
    el último punto de la serie deflactada coincide exactamente con `patrimonio_final_real`.
    """
    if inflacion_anual_pct is None or inflacion_anual_pct <= 0:
        return None
    return valor / math.pow(1 + inflacion_anual_pct / 100, mes / 12)


def _mes_agotamiento(puntos: list[ee.PuntoProyeccion], tolerancia: float = 1e-6) -> Optional[int]:
    """Primer mes en el que el patrimonio, habiendo tenido valor, cae a (casi) cero."""
    hubo_valor = False
    for p in puntos:
        if p.valor_usd > tolerancia:
            hubo_valor = True
        elif hubo_valor:
            return p.mes
    return None


def _metricas(
    res: ee.ResultadoEscenario, supuestos: SupuestosVida, base_final: float
) -> MetricasVida:
    # capital_aportado_usd arranca en total_invertido_usd == patrimonio_inicial (ver
    # _snapshot_sintetico), así que hay que restarlo para obtener los aportes del período.
    aportes_periodo = res.capital_aportado_usd - supuestos.patrimonio_inicial
    patrimonio_final = res.patrimonio_final_usd
    diferencia_vs_base = patrimonio_final - base_final
    diferencia_vs_base_pct = (
        diferencia_vs_base / base_final * 100 if base_final > 0 else None
    )
    patrimonio_final_real = _deflactar(
        patrimonio_final, supuestos.horizonte_meses, supuestos.inflacion_anual_pct
    )

    return MetricasVida(
        patrimonio_final=patrimonio_final,
        patrimonio_final_real=patrimonio_final_real,
        aportes_periodo=aportes_periodo,
        crecimiento_estimado=res.ganancia_perdida_usd,
        diferencia_vs_base=diferencia_vs_base,
        diferencia_vs_base_pct=diferencia_vs_base_pct,
    )


# ─── Orquestación ───────────────────────────────────────────────────────────

def simular_vida(
    supuestos: SupuestosVida,
    especificaciones: list[EscenarioVidaSpec],
    hoy: Optional[date] = None,
) -> ComparacionVida:
    """Simula la base ('continuar igual') más cada escenario pedido, contra el
    mismo snapshot sintético (misma comparabilidad que el simulador Avanzado)."""
    hoy = hoy or date.today()
    validar(supuestos, especificaciones)

    specs = list(especificaciones)
    idx_base = next((i for i, s in enumerate(specs) if s.tipo == TIPO_BASE), None)
    if idx_base is None:
        specs = [EscenarioVidaSpec(tipo=TIPO_BASE)] + specs
    elif idx_base != 0:
        specs.insert(0, specs.pop(idx_base))

    snapshot = _snapshot_sintetico(supuestos, hoy)

    resultados: list[ResultadoVida] = []
    advertencias_globales: list[str] = []
    base_final = 0.0

    for i, spec in enumerate(specs):
        es_base = i == 0
        params = _params_de_escenario(supuestos, spec)
        res = ee.simular_escenario(snapshot, params)
        if es_base:
            base_final = res.patrimonio_final_usd

        metricas = _metricas(res, supuestos, base_final)
        puntos_vida = [
            PuntoVida(
                mes=p.mes,
                fecha=_fecha_mes(hoy, p.mes).isoformat(),
                valor=p.valor_usd,
                valor_real=_deflactar(p.valor_usd, p.mes, supuestos.inflacion_anual_pct),
                aportado_acum=p.capital_aportado_acum_usd - supuestos.patrimonio_inicial,
            )
            for p in res.puntos
        ]
        se_agota = _mes_agotamiento(res.puntos)

        advertencias: list[str] = []
        if spec.tipo == "retiro_extraordinario" and spec.monto is not None:
            solicitado = abs(spec.monto)
            aplicado = abs(res.flujo_extraordinario_aplicado_usd)
            if aplicado + 1e-6 < solicitado:
                advertencias.append(
                    f"En el mes {spec.mes} no alcanzaban los fondos: se retiró "
                    f"{aplicado:,.0f} {supuestos.moneda} de los {solicitado:,.0f} "
                    f"{supuestos.moneda} pedidos y el patrimonio quedó en cero."
                )
        if se_agota is not None and not advertencias:
            advertencias.append(f"Con estos supuestos, el patrimonio se agota en el mes {se_agota}.")

        nombre, descripcion = _nombre_y_descripcion(supuestos, spec)
        resultados.append(ResultadoVida(
            tipo=spec.tipo,
            nombre=nombre,
            descripcion=descripcion,
            es_base=es_base,
            aporte_mensual_efectivo=params.aporte_mensual_usd,
            crecimiento_aporte_anual_pct=params.crecimiento_aporte_anual_pct,
            mes_flujo_extraordinario=spec.mes if params.flujos_extraordinarios else None,
            monto_flujo_extraordinario=(
                params.flujos_extraordinarios[0].monto_usd if params.flujos_extraordinarios else None
            ),
            se_agota_en_mes=se_agota,
            puntos=puntos_vida,
            metricas=metricas,
            advertencias=advertencias,
        ))
        advertencias_globales.extend(advertencias)

    return ComparacionVida(
        supuestos=supuestos,
        resultados=resultados,
        advertencias=advertencias_globales,
    )
