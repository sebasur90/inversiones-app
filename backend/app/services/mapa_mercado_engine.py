"""Motor puro del mapa de mercado: variaciones por calendario, conversión a USD y tamaño de empresa.

Sin DB ni red: recibe listas de `(fecha, cierre)` y devuelve números. El adaptador es
`mapa_mercado_ingesta` (descarga y guarda) y `mapa_mercado_analytics` (arma la respuesta).

Las variaciones son **razones** (0.012 = +1,2%), como en el resto de la app.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta

Cierres = list[tuple[date, float]]

# Ventanas en días corridos contra el último cierre. El día es la rueda anterior, no "ayer":
# un lunes se compara contra el viernes.
DIAS_SEMANA = 7
DIAS_MES = 30
DIAS_ANIO = 365

# Cuánto puede alejarse el cierre de referencia de la fecha pedida. Sin tope, una serie de 20
# días "mediría" el año contra su primer dato. Cubre feriados largos y fines de semana.
TOLERANCIA_DIAS = 6

# Un cierre más viejo que esto no es "el último día": el emisor está suspendido o no cotiza.
MAX_ANTIGUEDAD_ULTIMO_CIERRE_DIAS = 10

# Tamaño de empresa por capitalización en USD.
MEGA_USD = 200e9
GRANDE_USD = 10e9
MEDIANA_USD = 2e9

TAMANO_MEGA = "Mega (+200 mil M)"
TAMANO_GRANDE = "Grande (10-200 mil M)"
TAMANO_MEDIANA = "Mediana (2-10 mil M)"
TAMANO_CHICA = "Chica (-2 mil M)"
TAMANO_SIN_DATO = "Sin dato"
ORDEN_TAMANO = (TAMANO_MEGA, TAMANO_GRANDE, TAMANO_MEDIANA, TAMANO_CHICA, TAMANO_SIN_DATO)


@dataclass(frozen=True)
class Variaciones:
    fecha_cierre: date
    cierre: float
    var_1d: float | None
    var_1s: float | None
    var_1m: float | None
    var_1a: float | None


def _cierre_en_o_antes(fechas: list[date], cierres: list[float], objetivo: date) -> float | None:
    """Último cierre con fecha <= `objetivo`, si no está a más de `TOLERANCIA_DIAS` de distancia."""
    i = bisect_right(fechas, objetivo) - 1
    if i < 0:
        return None
    if (objetivo - fechas[i]).days > TOLERANCIA_DIAS:
        return None
    return cierres[i]


def _razon(actual: float, previo: float | None) -> float | None:
    if previo is None or previo <= 0:
        return None
    return actual / previo - 1.0


def variaciones(serie: Cierres, hoy: date | None = None) -> Variaciones | None:
    """Variación del último cierre contra la rueda anterior y contra hace 7, 30 y 365 días.

    `None` si la serie está vacía o el último cierre es demasiado viejo (`hoy` por parámetro para
    poder testearlo). Cada ventana es `None` por separado si la historia no llega.
    """
    if not serie:
        return None
    serie = sorted(serie, key=lambda p: p[0])
    fechas = [f for f, _ in serie]
    cierres = [c for _, c in serie]
    ultima, cierre = fechas[-1], cierres[-1]
    if hoy is not None and (hoy - ultima).days > MAX_ANTIGUEDAD_ULTIMO_CIERRE_DIAS:
        return None

    previo_1d = cierres[-2] if len(cierres) >= 2 else None
    return Variaciones(
        fecha_cierre=ultima,
        cierre=cierre,
        var_1d=_razon(cierre, previo_1d),
        var_1s=_razon(cierre, _cierre_en_o_antes(fechas, cierres, ultima - timedelta(days=DIAS_SEMANA))),
        var_1m=_razon(cierre, _cierre_en_o_antes(fechas, cierres, ultima - timedelta(days=DIAS_MES))),
        var_1a=_razon(cierre, _cierre_en_o_antes(fechas, cierres, ultima - timedelta(days=DIAS_ANIO))),
    )


def a_usd(serie_ars: Cierres, mep_por_fecha: dict[date, float]) -> Cierres | None:
    """Pasa una serie en pesos a dólares dividiendo cada cierre por el MEP de **esa** fecha.

    Para una fecha sin MEP se usa el último anterior (el MEP no se publica los feriados). Devuelve
    `None` si no hay MEP para cubrir la serie: convertir a medias mezclaría monedas.
    """
    if not serie_ars or not mep_por_fecha:
        return None
    fechas_mep = sorted(mep_por_fecha)
    out: Cierres = []
    for fecha, cierre in serie_ars:
        i = bisect_right(fechas_mep, fecha) - 1
        if i < 0 or (fecha - fechas_mep[i]).days > TOLERANCIA_DIAS:
            return None
        mep = mep_por_fecha[fechas_mep[i]]
        if not mep or mep <= 0:
            return None
        out.append((fecha, cierre / mep))
    return out


def tamano_empresa(market_cap_usd: float | None) -> str:
    if market_cap_usd is None or market_cap_usd <= 0:
        return TAMANO_SIN_DATO
    if market_cap_usd >= MEGA_USD:
        return TAMANO_MEGA
    if market_cap_usd >= GRANDE_USD:
        return TAMANO_GRANDE
    if market_cap_usd >= MEDIANA_USD:
        return TAMANO_MEDIANA
    return TAMANO_CHICA
