"""Orquestación de simulaciones de escenarios (DB-aware)."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import EscenarioSimulacion
from app.services import escenario_engine
from app.services.inversiones_analytics import (
    _clasificados_valorizados,
    get_resumen,
    get_mep_actual,
)


def construir_snapshot(
    cartera: str | None,
    db: Session
) -> escenario_engine.PortfolioSnapshot:
    """Construye un snapshot de la cartera actual.

    Args:
        cartera: Nombre de cartera (None = Consolidado).
        db: Session de SQLAlchemy.

    Returns:
        PortfolioSnapshot listo para simular.
    """
    # Obtener posiciones valorizadas
    valores, clasificados, instrumentos = _clasificados_valorizados(cartera, db)

    # Construir lista de posiciones
    posiciones = []
    for cart, ticker, valor_usd, valor_ars in clasificados:
        if valor_usd <= 0:
            continue
        instrumento = instrumentos.get(ticker)
        moneda = instrumento.moneda if instrumento else "USD"
        posiciones.append(escenario_engine.PosicionSnapshot(
            ticker=ticker,
            valor_usd=valor_usd,
            moneda=moneda,
        ))

    # Obtener total invertido
    resumen = get_resumen(cartera, db)
    total_invertido = resumen.total_invertido_usd

    # Obtener MEP actual
    mep_actual = get_mep_actual(db)

    # Calcular valor total
    valor_total = sum(p.valor_usd for p in posiciones)

    from datetime import date
    return escenario_engine.PortfolioSnapshot(
        fecha=date.today(),
        posiciones=posiciones,
        mep_actual=mep_actual,
        valor_total_usd=valor_total,
        total_invertido_usd=total_invertido,
    )


def crear_escenario(
    cartera: str | None,
    nombre: str,
    tipo_preset: str,
    parametros: dict,
    db: Session
) -> EscenarioSimulacion:
    """Crea y persiste un nuevo escenario."""
    ahora = datetime.utcnow()
    escenario = EscenarioSimulacion(
        cartera=cartera,
        nombre=nombre,
        tipo_preset=tipo_preset,
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
        parametros=parametros,
    )
    db.add(escenario)
    db.commit()
    db.refresh(escenario)
    return escenario


def listar_escenarios(
    cartera: str | None,
    db: Session
) -> list[EscenarioSimulacion]:
    """Lista escenarios para una cartera."""
    query = db.query(EscenarioSimulacion)
    if cartera is not None:
        query = query.filter(EscenarioSimulacion.cartera == cartera)
    else:
        query = query.filter(EscenarioSimulacion.cartera.is_(None))
    return query.all()


def obtener_escenario(
    escenario_id: int,
    db: Session
) -> EscenarioSimulacion | None:
    """Obtiene un escenario por ID."""
    return db.query(EscenarioSimulacion).filter(EscenarioSimulacion.id == escenario_id).first()


def duplicar_escenario(
    escenario_id: int,
    nuevo_nombre: str | None,
    db: Session
) -> EscenarioSimulacion | None:
    """Duplica un escenario con un nuevo nombre."""
    original = obtener_escenario(escenario_id, db)
    if original is None:
        return None

    nombre_nuevo = nuevo_nombre or f"{original.nombre} (copia)"
    return crear_escenario(
        cartera=original.cartera,
        nombre=nombre_nuevo,
        tipo_preset=original.tipo_preset,
        parametros=original.parametros,
        db=db,
    )


def eliminar_escenario(
    escenario_id: int,
    db: Session
) -> bool:
    """Elimina un escenario. Retorna True si existía, False si no."""
    escenario = obtener_escenario(escenario_id, db)
    if escenario is None:
        return False
    db.delete(escenario)
    db.commit()
    return True


def simular_escenario_cartera(
    cartera: str | None,
    request,  # EscenarioSimulacionRequest
    db: Session
) -> dict:
    """Ejecuta múltiples simulaciones contra el mismo snapshot.

    Args:
        cartera: Nombre de cartera (None = Consolidado).
        request: EscenarioSimulacionRequest con lista de escenarios.
        db: Session de SQLAlchemy.

    Returns:
        Dict con estructura EscenarioSimulacionOut (antes de convertir a Pydantic).
    """
    from datetime import datetime
    from app.schemas import EscenarioParamsIn

    # Construir snapshot UNA SOLA VEZ (garantiza comparabilidad)
    snapshot = construir_snapshot(cartera, db)

    # Obtener resumen actual
    resumen_actual = get_resumen(cartera, db)

    # Procesar cada escenario
    resultados = []
    advertencias_set = set()

    for item in request.escenarios:
        # Resolver parámetros (llenar defaults si es preset)
        parametros_dict = escenario_engine.resolver_preset(
            item.tipo_preset,
            item.parametros.model_dump() if item.parametros else None,
        )

        # Convertir a EscenarioParams (puede tener defaults)
        params_in = EscenarioParamsIn(**parametros_dict)
        params = escenario_engine.EscenarioParams(
            horizonte_meses=params_in.horizonte_meses,
            variacion_dolar_pct=params_in.variacion_dolar_pct,
            variacion_por_instrumento=params_in.variacion_por_instrumento,
            variacion_por_defecto_pct=params_in.variacion_por_defecto_pct,
            aporte_mensual_usd=params_in.aporte_mensual_usd,
            crecimiento_aporte_anual_pct=params_in.crecimiento_aporte_anual_pct,
            retiro_mensual_usd=params_in.retiro_mensual_usd,
            modo_dividendos=params_in.modo_dividendos,
            dividend_yield_anual_pct=params_in.dividend_yield_anual_pct,
            pct_dividendo_reinvertido=params_in.pct_dividendo_reinvertido,
            comision_pct=params_in.comision_pct,
            inflacion_anual_pct=params_in.inflacion_anual_pct,
        )

        # Simular
        resultado_engine = escenario_engine.simular_escenario(snapshot, params)

        # Convertr a dict de salida
        puntos_out = [
            {
                "mes": p.mes,
                "fecha": p.fecha,
                "valor_usd": p.valor_usd,
                "capital_aportado_acum_usd": p.capital_aportado_acum,
                "dividendos_acum_usd": p.dividendos_acum,
            }
            for p in resultado_engine.puntos
        ]

        diferencia_vs_actual = resultado_engine.patrimonio_final_usd - snapshot.valor_total_usd

        resultado_out = {
            "nombre": item.nombre or item.tipo_preset,
            "tipo_preset": item.tipo_preset,
            "puntos": puntos_out,
            "patrimonio_inicial_usd": resultado_engine.patrimonio_inicial_usd,
            "patrimonio_final_usd": resultado_engine.patrimonio_final_usd,
            "ganancia_perdida_usd": resultado_engine.ganancia_perdida_usd,
            "rendimiento_pct": resultado_engine.rendimiento_pct,
            "capital_aportado_usd": resultado_engine.capital_aportado_usd,
            "efecto_mercado_usd": resultado_engine.efecto_mercado_usd,
            "efecto_dolar_usd": resultado_engine.efecto_dolar_usd,
            "dividendos_usd": resultado_engine.dividendos_usd,
            "comisiones_usd": resultado_engine.comisiones_usd,
            "patrimonio_final_real_usd": resultado_engine.patrimonio_final_real_usd,
            "diferencia_vs_actual_usd": diferencia_vs_actual,
            "es_simulado": True,
        }
        resultados.append(resultado_out)

    # Advertencias
    if snapshot.mep_actual is None and any(e.variacion_dolar_pct != 0 for e in [escenario_engine.EscenarioParams(
        horizonte_meses=p["horizonte_meses"],
        variacion_dolar_pct=p.get("variacion_dolar_pct", 0),
        variacion_por_instrumento=p.get("variacion_por_instrumento", {}),
        variacion_por_defecto_pct=p.get("variacion_por_defecto_pct", 0),
        aporte_mensual_usd=p.get("aporte_mensual_usd", 0),
        crecimiento_aporte_anual_pct=p.get("crecimiento_aporte_anual_pct", 0),
        retiro_mensual_usd=p.get("retiro_mensual_usd", 0),
        modo_dividendos=p.get("modo_dividendos", "reinvertir_total"),
        dividend_yield_anual_pct=p.get("dividend_yield_anual_pct", 0),
        pct_dividendo_reinvertido=p.get("pct_dividendo_reinvertido"),
        comision_pct=p.get("comision_pct", 0),
        inflacion_anual_pct=p.get("inflacion_anual_pct"),
    ) for p in [item.parametros.model_dump() if item.parametros else {} for item in request.escenarios]]):
        advertencias_set.add("MEP no disponible: shock de dólar no aplicado a instrumentos ARS")

    if len(snapshot.posiciones) == 0 and snapshot.valor_total_usd == 0:
        advertencias_set.add("Cartera vacía: aportes se acumulan en un bucket sintético")

    # Intrumentos sin precio
    tickers_simulados = {p.ticker for p in snapshot.posiciones}
    # (ya están filtrados por _clasificados_valorizados, así que no hay que advertir más)

    return {
        "cartera": cartera,
        "fecha_simulacion": datetime.utcnow(),
        "actual_valor_usd": snapshot.valor_total_usd,
        "resultados": resultados,
        "advertencias": list(advertencias_set),
    }
