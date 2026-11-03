"""Régimen macroeconómico de «Ciclos de mercado»: la estructura está lista, los datos todavía no.

Los cuatro escenarios salen de cruzar si el **crecimiento** y la **inflación** se están acelerando o
desacelerando. Determinarlos exige series macro globales confiables (actividad, inflación, tasas,
liquidez, condiciones financieras) que la app **no tiene**: sólo conoce CER, MEP, riesgo país e
inflación de INDEC, que describen a la Argentina. CER y MEP no son indicadores suficientes del régimen
global, así que acá el estado se declara `no_disponible` en vez de inventarlo, y se lista qué falta.

Esto no bloquea nada del análisis de precios. Cuando exista una fuente, se completa `INDICADORES` con su
`evaluar` y el estado de cada eje; la forma de la respuesta no cambia.
"""
from __future__ import annotations

ACELERANDO, DESACELERANDO = "acelerando", "desacelerando"

ESCENARIOS = (
    {"id": "reflacion", "nombre": "Reflación", "crecimiento": ACELERANDO, "inflacion": ACELERANDO},
    {"id": "expansion-equilibrada", "nombre": "Expansión equilibrada", "crecimiento": ACELERANDO, "inflacion": DESACELERANDO},
    {"id": "estanflacion", "nombre": "Estanflación", "crecimiento": DESACELERANDO, "inflacion": ACELERANDO},
    {"id": "desinflacion", "nombre": "Desinflación", "crecimiento": DESACELERANDO, "inflacion": DESACELERANDO},
)

# Qué haría falta, qué hay hoy y por qué no alcanza. `eje` = qué dimensión del régimen alimentaría.
INDICADORES = (
    {"id": "actividad", "nombre": "Actividad económica", "eje": "crecimiento", "disponible": False,
     "motivo": "No hay series de actividad global (PIB, producción industrial, PMI) cargadas."},
    {"id": "adelantados", "nombre": "Indicadores adelantados", "eje": "crecimiento", "disponible": False,
     "motivo": "No hay indicadores adelantados cargados."},
    {"id": "inflacion", "nombre": "Inflación", "eje": "inflacion", "disponible": False,
     "motivo": "La app tiene la inflación de INDEC (Argentina), no la de EE.UU. ni la global."},
    {"id": "tasas", "nombre": "Tasas de interés", "eje": "ambos", "disponible": True,
     "motivo": "Hay rendimientos del Tesoro de EE.UU. a 3 meses, 5, 10 y 30 años (pestaña Relaciones). No hay la tasa de política "
               "monetaria ni las de otras regiones, y solas no determinan crecimiento ni inflación."},
    {"id": "liquidez", "nombre": "Liquidez", "eje": "ambos", "disponible": False,
     "motivo": "No hay series de balance de bancos centrales ni de agregados monetarios."},
    {"id": "condiciones-financieras", "nombre": "Condiciones financieras", "eje": "ambos", "disponible": False,
     "motivo": "No hay índices de condiciones financieras ni de spreads de crédito."},
    {"id": "dolar", "nombre": "Dólar", "eje": "ambos", "disponible": False,
     "motivo": "Existe el grupo «Dólar» (ETF UUP) como serie de precios en Ciclos, pero el precio de un ETF no "
               "alcanza para decir si el dólar acelera o desacelera el crecimiento o la inflación."},
)

DISPONIBLE_HOY = (
    {"id": "cer", "nombre": "CER", "alcance": "Argentina"},
    {"id": "mep", "nombre": "Dólar MEP", "alcance": "Argentina"},
    {"id": "riesgo-pais", "nombre": "Riesgo país", "alcance": "Argentina"},
    {"id": "inflacion-indec", "nombre": "Inflación mensual de INDEC", "alcance": "Argentina"},
    {"id": "tasas-tesoro-eeuu", "nombre": "Rendimientos del Tesoro de EE.UU. (3 meses a 30 años)", "alcance": "EE.UU."},
)

ACLARACION = (
    "CER, MEP y riesgo país describen a la Argentina y las tasas del Tesoro sólo a EE.UU.: no alcanzan para determinar el régimen "
    "macroeconómico global (faltan actividad e inflación), y por eso la app no asigna ninguno de los cuatro escenarios."
)


def evaluar() -> dict:
    """Estado del régimen. Hoy siempre `no_disponible`; nunca un escenario supuesto."""
    return {
        "estado": "no_disponible",
        "escenario": None,
        "escenarios": [{**e, "actual": False} for e in ESCENARIOS],
        "indicadores_necesarios": [dict(i) for i in INDICADORES],
        "disponible_hoy": [dict(i) for i in DISPONIBLE_HOY],
        "aclaracion": ACLARACION,
        "falta": [i["nombre"] for i in INDICADORES if not i["disponible"]],
        "proxima_etapa": "Incorporar series macro globales con una fuente documentada y completar la clasificación de cada eje.",
    }
