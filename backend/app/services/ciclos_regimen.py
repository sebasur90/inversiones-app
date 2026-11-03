"""Régimen macroeconómico de «Ciclos de mercado»: crecimiento e inflación, cada uno acelerando o desacelerando. Puro.

Los cuatro escenarios salen de cruzar los dos ejes:

| | Inflación acelera | Inflación desacelera |
|---|---|---|
| **Crecimiento acelera** | Reflación | Expansión equilibrada |
| **Crecimiento desacelera** | Estanflación | Desinflación |

**Cómo se decide cada eje** (la regla entera cabe en una línea y no esconde ajustes):

1. Cada serie del eje **vota**. Se mira su transformación (variación contra el mismo período de un año antes, o el nivel
   tal cual, según el catálogo) hoy y `meses_comparacion` meses antes: si hoy es mayor, la serie vota «acelera»; si es menor,
   «desacelera». Una serie cuyo sentido es inverso (más pedidos de subsidio = menos crecimiento) invierte su voto.
2. Una serie **sin datos, desactualizada o sin historia suficiente no vota**: no se completa ni se estima.
3. El eje se define por **mayoría estricta** y sólo si votaron al menos `minimo_votos` series. Con un empate o con pocos
   votos queda «no concluyente», y entonces **no se asigna ningún escenario**.

No hay puntaje único ni se ponderan las series. Liquidez, condiciones financieras y dólar se muestran como **contexto**: no
entran en la clasificación. Todo es de EE.UU. y de una fuente que entrega la versión vigente de datos que se revisan; describe
lo que muestran los datos, no anticipa nada ni recomienda operar.
"""
from __future__ import annotations

from datetime import date

from . import ciclos_engine as eng
from . import ciclos_macro_catalogo as mc

ACELERANDO, DESACELERANDO = "acelerando", "desacelerando"
SUBE, BAJA = "sube", "baja"
SIN_CAMBIO = "sin_cambio"
NO_CONCLUYENTE = "no_concluyente"

ESTADO_DISPONIBLE = "disponible"
ESTADO_NO_CONCLUYENTE = "no_concluyente"
ESTADO_NO_DISPONIBLE = "no_disponible"

ESCENARIOS = (
    {"id": "reflacion", "nombre": "Reflación", "crecimiento": ACELERANDO, "inflacion": ACELERANDO},
    {"id": "expansion-equilibrada", "nombre": "Expansión equilibrada", "crecimiento": ACELERANDO, "inflacion": DESACELERANDO},
    {"id": "estanflacion", "nombre": "Estanflación", "crecimiento": DESACELERANDO, "inflacion": ACELERANDO},
    {"id": "desinflacion", "nombre": "Desinflación", "crecimiento": DESACELERANDO, "inflacion": DESACELERANDO},
)

NOMBRE_EJE = {"crecimiento": "Crecimiento", "inflacion": "Inflación", "liquidez": "Liquidez",
              "condiciones_financieras": "Condiciones financieras", "dolar": "Dólar"}

#: Tolerancia (días) para tomar el dato de una fecha, según la frecuencia de la serie.
TOLERANCIA_DIAS = {"diaria": 6, "semanal": 10, "mensual": 12}

LIMITACIONES = (
    "Son datos de EE.UU. de FRED (Reserva Federal de St. Louis). No describen la economía argentina ni el resto del mundo.",
    "Los datos macro se revisan después de publicarse y FRED entrega la versión vigente: lo que se ve hoy puede cambiar, y mirar el pasado con datos ya corregidos no es lo que se veía en su momento.",
    "Hay rezago de publicación: cada dato lleva la fecha del período al que se refiere, y el más reciente puede tener uno o dos meses.",
    "La clasificación describe si cada serie viene acelerando o desacelerando frente a hace unos meses. No anticipa el régimen siguiente ni dice qué hacer con la cartera.",
)

ACLARACION_NO_DISPONIBLE = "Todavía no se descargaron las series macro (la ingesta de ciclos no corrió o FRED no respondió)."


def _transformado(obs: list[tuple[date, float]], fecha: date, transformacion: str, tolerancia: int) -> float | None:
    """La serie transformada en `fecha`: el nivel, o la variación porcentual contra 12 meses antes. `None` si falta dato."""
    fechas, valores = [f for f, _ in obs], [v for _, v in obs]
    v = eng.cierre_en(fechas, valores, fecha, tolerancia)
    if v is None:
        return None
    if transformacion == "nivel":
        return v
    base = eng.cierre_en(fechas, valores, eng.restar_meses(fecha, 12), tolerancia)
    if base is None or base <= 0 or fechas[0] > eng.restar_meses(fecha, 12):
        return None
    return (v / base - 1.0) * 100.0


def evaluar_serie(s: mc.SerieMacro, obs: list[tuple[date, float]], hoy: date, meses: int, dias_maximos: dict[str, int]) -> dict:
    """Valor de la serie hoy y `meses` antes, cuánto cambió y (si clasifica) su voto. Nunca inventa un dato."""
    base = {
        "id": s.id, "nombre": s.nombre, "eje": s.eje, "frecuencia": s.frecuencia, "unidad": s.unidad,
        "transformacion": s.transformacion, "sentido": s.sentido, "descripcion": s.descripcion, "nota": s.nota,
        "clasifica": s.clasifica, "fecha": None, "valor": None, "fecha_previa": None, "valor_previo": None, "cambio": None,
        "tendencia": None, "voto": None, "estado": "sin_datos", "motivo": None,
    }
    obs = eng.normalizar_nivel(obs)
    if not obs:
        return {**base, "motivo": "todavía no se descargó la serie"}
    fecha = obs[-1][0]
    base["fecha"] = fecha
    if (hoy - fecha).days > dias_maximos.get(s.frecuencia, 75):
        return {**base, "estado": "desactualizada", "motivo": f"el último dato es del {fecha.isoformat()}: demasiado viejo para usarlo"}
    tol = TOLERANCIA_DIAS[s.frecuencia]
    previa = eng.restar_meses(fecha, meses)
    actual = _transformado(obs, fecha, s.transformacion, tol)
    anterior = _transformado(obs, previa, s.transformacion, tol)
    base.update(valor=actual, valor_previo=anterior)
    if actual is None or anterior is None:
        return {**base, "estado": "sin_historia", "motivo": "no hay historia suficiente para compararla con hace unos meses"}
    cambio = actual - anterior
    base.update(cambio=cambio, fecha_previa=previa, estado="ok",
                tendencia=SUBE if cambio > 0 else (BAJA if cambio < 0 else SIN_CAMBIO))
    if s.clasifica:
        base["voto"] = SIN_CAMBIO if cambio == 0 else (ACELERANDO if cambio * s.sentido > 0 else DESACELERANDO)
    return base


def evaluar_eje(series: list[dict], minimo_votos: int) -> dict:
    """Mayoría estricta de los votos, si votaron al menos `minimo_votos` series. Si no, no concluye (y dice por qué)."""
    a = sum(1 for s in series if s["voto"] == ACELERANDO)
    d = sum(1 for s in series if s["voto"] == DESACELERANDO)
    votaron = a + d
    base = {"acelerando": a, "desacelerando": d, "votaron": votaron, "total": len(series), "minimo_votos": minimo_votos}
    if votaron < minimo_votos:
        return {**base, "estado": NO_CONCLUYENTE, "motivo": f"votaron {votaron} de {len(series)} series y hacen falta al menos {minimo_votos}"}
    if a == d:
        return {**base, "estado": NO_CONCLUYENTE, "motivo": f"empate: {a} series aceleran y {d} desaceleran"}
    return {**base, "estado": ACELERANDO if a > d else DESACELERANDO, "motivo": None}


def evaluar(series_obs: dict[str, list[tuple[date, float]]] | None = None, cat: mc.CatalogoMacro | None = None, hoy: date | None = None) -> dict:
    """Estado del régimen. `series_obs` = `{id de serie: [(fecha, valor)]}`. Sin datos: `no_disponible`, nunca un escenario supuesto."""
    cat = cat if cat is not None else mc.cargar()
    hoy = hoy or date.today()
    series_obs = series_obs or {}
    evaluadas = {s.id: evaluar_serie(s, series_obs.get(s.id, []), hoy, cat.meses_comparacion, cat.dias_maximos) for s in cat.series.values()}
    ejes = {}
    for eje in mc.EJES_CLASIFICAN:
        lista = [evaluadas[s.id] for s in cat.por_eje(eje)]
        ejes[eje] = {"nombre": NOMBRE_EJE[eje], "series": lista, **evaluar_eje(lista, cat.minimo_votos)}
    contexto = {eje: [evaluadas[s.id] for s in cat.por_eje(eje)] for eje in mc.EJES_CONTEXTO if cat.por_eje(eje)}

    hay_datos = any(s["valor"] is not None for s in evaluadas.values())
    crec, infl = ejes["crecimiento"]["estado"], ejes["inflacion"]["estado"]
    escenario = next((e for e in ESCENARIOS if e["crecimiento"] == crec and e["inflacion"] == infl), None)
    if not hay_datos:
        estado, aclaracion = ESTADO_NO_DISPONIBLE, ACLARACION_NO_DISPONIBLE
    elif escenario:
        estado = ESTADO_DISPONIBLE
        aclaracion = (f"Crecimiento {crec} e inflación {infl}, según la mayoría de las series de cada eje. "
                      "Describe cómo vienen los datos frente a hace unos meses; no anticipa el régimen siguiente.")
    else:
        estado = ESTADO_NO_CONCLUYENTE
        sin = [f"{NOMBRE_EJE[e].lower()}: {ejes[e]['motivo']}" for e in mc.EJES_CLASIFICAN if ejes[e]["estado"] == NO_CONCLUYENTE]
        aclaracion = "No se asigna ningún escenario porque " + "; ".join(sin) + "."

    usadas = [s for e in ejes.values() for s in e["series"] if s["voto"] in (ACELERANDO, DESACELERANDO)]
    fechas = [s["fecha"] for s in usadas]
    return {
        "estado": estado,
        "escenario": escenario["nombre"] if escenario and estado == ESTADO_DISPONIBLE else None,
        "escenario_id": escenario["id"] if escenario and estado == ESTADO_DISPONIBLE else None,
        "escenarios": [{**e, "actual": bool(escenario and estado == ESTADO_DISPONIBLE and e["id"] == escenario["id"])} for e in ESCENARIOS],
        "ejes": ejes, "contexto": contexto, "aclaracion": aclaracion,
        "meses_comparacion": cat.meses_comparacion, "minimo_votos": cat.minimo_votos,
        "dato_mas_reciente": max(fechas, default=None), "dato_mas_viejo": min(fechas, default=None),
        "falta": [f"{s['nombre']} ({s['motivo']})" for s in evaluadas.values() if s["estado"] != "ok"],
        "errores_catalogo": list(cat.errores),
        "fuente": mc.FUENTE, "limitaciones": list(LIMITACIONES),
    }
