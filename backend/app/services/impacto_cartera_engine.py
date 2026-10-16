"""Impacto de sumar un monto a la cartera: cómo cambian los pesos. Puro: sin DB ni red.

Responde "si sumara N dólares de X, ¿cuánto pesaría X y cómo cambiaría la mezcla por emisor, sector,
país, región y tipo?". **No persiste nada, no estima precios ni cantidades y no recomienda**: es la
aritmética de los pesos antes y después, más observaciones que salen de los umbrales que ya usa Salud
de cartera (`salud_engine`), citados tal cual.

El adaptador (`impacto_cartera_analytics`) entrega, por eje, la agrupación de hoy y la de después
calculadas con `inversiones_analytics._agrupar` —la misma que usa Exposición—, así que "antes" es
exactamente lo que muestra esa pantalla. Acá sólo se comparan.

El eje **Emisor** es propio de esta etapa: agrupa un CEDEAR, su acción de origen y las variantes de
moneda como un único emisor (`Contexto.base`), porque tener KO y KOD no es diversificar. Los otros ejes
(sector, país, región, tipo) heredan el criterio de Exposición.

Regla de lenguaje: ningún texto de este módulo dice qué hacer con la operación; los textos describen
cómo quedaría la cartera ("pasaría", "quedaría"). Un test lo garantiza.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import contribucion_engine as ce
from . import salud_engine as se
from .etiquetas import BUCKETS_RESIDUALES

VERSION_REGLAS = 1

EJE_EMISOR = "Emisor"
EJES_RESIDUAL = {
    "Sector": "Sin sector", "País": "Sin país", "Región": "Sin región", "Tipo de instrumento": "Sin clasificar",
}

REVISAR, ATENCION, INFO = "revisar", "atencion", "info"


@dataclass
class EjeEntrada:
    """Un eje ya agrupado por el adaptador: `antes`/`despues` son `[{etiqueta, valor_usd, valor_ars, porcentaje}]`."""
    nombre: str
    antes: list[dict]
    despues: list[dict]
    etiqueta_compra: str            # en qué fila cae el monto simulado


@dataclass
class Observacion:
    nivel: str                      # REVISAR | ATENCION | INFO
    texto: str
    regla: str = ""
    eje: str = ""


@dataclass
class Datos:
    """Todo lo que el motor necesita además de los ejes."""
    ticker: str
    emisor: str
    monto_usd: float
    total_antes_usd: float
    total_despues_usd: float
    peso_maximo: float | None = None
    emisor_en_cartera: list[str] = field(default_factory=list)   # tickers que ya tiene de ese emisor
    tickers_por_emisor: dict[str, list[str]] = field(default_factory=dict)
    nombres: dict[str, str] = field(default_factory=dict)


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f} %".replace(".", ",")


def _peso(items: list[dict], etiqueta: str) -> float:
    return next((float(i["porcentaje"]) for i in items if i["etiqueta"] == etiqueta), 0.0)


def _valor(items: list[dict], etiqueta: str, clave: str) -> float:
    return next((float(i[clave]) for i in items if i["etiqueta"] == etiqueta), 0.0)


def _concentracion(items: list[dict]) -> dict:
    pesos = [float(i["porcentaje"]) for i in items]
    hhi = ce.calcular_hhi(pesos)
    mayor = max(items, key=lambda i: i["porcentaje"]) if items else None
    return {
        "hhi_normalizado": hhi["hhi_normalizado"],
        "n_efectivo": hhi["effective_n"],
        "mayor": {"etiqueta": mayor["etiqueta"], "porcentaje": float(mayor["porcentaje"])} if mayor else None,
    }


def comparar_eje(e: EjeEntrada, tickers_por_emisor: dict[str, list[str]] | None = None,
                 nombres: dict[str, str] | None = None) -> dict:
    """Filas antes/después/Δ puntos de un eje, ordenadas por el peso de después, y su concentración."""
    etiquetas = list(dict.fromkeys([i["etiqueta"] for i in e.despues] + [i["etiqueta"] for i in e.antes]))
    filas = []
    for et in etiquetas:
        a, d = _peso(e.antes, et), _peso(e.despues, et)
        fila = {
            "etiqueta": et,
            "antes_pct": a, "despues_pct": d, "delta_pp": d - a,
            "antes_usd": _valor(e.antes, et, "valor_usd"), "despues_usd": _valor(e.despues, et, "valor_usd"),
            "afectada": et == e.etiqueta_compra,
            "residual": et in BUCKETS_RESIDUALES,
        }
        if e.nombre == EJE_EMISOR:
            fila["tickers"] = (tickers_por_emisor or {}).get(et, [])
            fila["nombre"] = (nombres or {}).get(et)
        filas.append(fila)
    filas.sort(key=lambda f: (-f["despues_pct"], f["etiqueta"]))
    return {
        "eje": e.nombre,
        "etiqueta_compra": e.etiqueta_compra,
        "items": filas,
        "antes": _concentracion(e.antes),
        "despues": _concentracion(e.despues),
    }


# ---------------------------------------------------------------------------------------------
# Observaciones (umbrales de Salud de cartera, citados)
# ---------------------------------------------------------------------------------------------

def _obs_emisor(eje: dict, d: Datos) -> list[Observacion]:
    fila = next((f for f in eje["items"] if f["afectada"]), None)
    if fila is None:
        return []
    atencion, revisar = se._umbrales_peso_ticker(d.peso_maximo)
    origen = "peso máximo configurado en tu cartera" if d.peso_maximo is not None else "umbral por defecto"
    regla = (f"umbrales de Salud de cartera por emisor ({origen}): atención desde {_pct(atencion)}, "
             f"revisar desde {_pct(revisar)}")
    a, p = fila["antes_pct"], fila["despues_pct"]
    if p < atencion:
        return []
    nivel = REVISAR if p >= revisar else ATENCION
    umbral = revisar if nivel == REVISAR else atencion
    palabra = "revisar" if nivel == REVISAR else "atención"
    if a >= atencion:
        texto = (f"{d.emisor} ya pesaba {_pct(a)} de la cartera y pasaría a {_pct(p)}, por encima del umbral de "
                 f"{palabra} ({_pct(umbral)}).")
    else:
        texto = (f"{d.emisor} pasaría de {_pct(a)} a {_pct(p)} de la cartera, por encima del umbral de "
                 f"{palabra} ({_pct(umbral)}).")
    return [Observacion(nivel, texto, regla, EJE_EMISOR)]


def _obs_pais(eje: dict) -> list[Observacion]:
    fila = next((f for f in eje["items"] if f["afectada"]), None)
    if fila is None or fila["residual"]:
        return []
    a, p = fila["antes_pct"], fila["despues_pct"]
    if p < se.UMBRAL_PAIS_ATENCION_PCT or p <= a:
        return []
    nivel = REVISAR if p >= se.UMBRAL_PAIS_REVISAR_PCT else ATENCION
    umbral = se.UMBRAL_PAIS_REVISAR_PCT if nivel == REVISAR else se.UMBRAL_PAIS_ATENCION_PCT
    palabra = "revisar" if nivel == REVISAR else "atención"
    return [Observacion(
        nivel,
        f"{fila['etiqueta']} pasaría de {_pct(a)} a {_pct(p)} de la cartera, por encima del umbral de {palabra} ({_pct(umbral)}).",
        f"umbrales de Salud de cartera por país: atención desde {_pct(se.UMBRAL_PAIS_ATENCION_PCT)}, "
        f"revisar desde {_pct(se.UMBRAL_PAIS_REVISAR_PCT)}",
        "País",
    )]


def _nivel_efectivo(n: float | None) -> int:
    """0 = normal, 1 = atención, 2 = revisar."""
    if n is None:
        return 0
    return 2 if n < se.UMBRAL_EFFECTIVE_N_REVISAR else 1 if n < se.UMBRAL_EFFECTIVE_N_ATENCION else 0


def _obs_diversificacion(eje: dict) -> list[Observacion]:
    a, d = eje["antes"]["n_efectivo"], eje["despues"]["n_efectivo"]
    if a is None or d is None:
        return []
    regla = (f"umbrales de Salud de cartera: atención por debajo de {se.UMBRAL_EFFECTIVE_N_ATENCION:g} emisores "
             f"equivalentes, revisar por debajo de {se.UMBRAL_EFFECTIVE_N_REVISAR:g}")
    na, nd = _nivel_efectivo(a), _nivel_efectivo(d)
    num = lambda v: f"{v:.1f}".replace(".", ",")      # noqa: E731
    if nd > na:
        return [Observacion(
            REVISAR if nd == 2 else ATENCION,
            f"La diversificación por emisor bajaría de {num(a)} a {num(d)} emisores equivalentes.", regla, EJE_EMISOR)]
    if nd < na:
        return [Observacion(
            INFO, f"La diversificación por emisor subiría de {num(a)} a {num(d)} emisores equivalentes.", regla, EJE_EMISOR)]
    return []


def _obs_residuales(ejes: list[dict], d: Datos) -> list[Observacion]:
    obs = []
    for eje in ejes:
        residual = EJES_RESIDUAL.get(eje["eje"])
        if residual and eje["etiqueta_compra"] == residual:
            obs.append(Observacion(
                INFO,
                f"No hay {eje['eje'].lower()} cargado para {d.emisor}: el monto simulado cuenta en «{residual}». "
                "Podés corregir la clasificación en la ficha del ticker.",
                "las posiciones sin dato de un eje van a su bucket residual, igual que en Exposición", eje["eje"],
            ))
    return obs


def construir(ejes_in: list[EjeEntrada], d: Datos) -> dict:
    ejes = [comparar_eje(e, d.tickers_por_emisor, d.nombres) for e in ejes_in]
    obs: list[Observacion] = []
    for eje in ejes:
        if eje["eje"] == EJE_EMISOR:
            obs += _obs_emisor(eje, d) + _obs_diversificacion(eje)
        elif eje["eje"] == "País":
            obs += _obs_pais(eje)
    obs += _obs_residuales(ejes, d)
    if d.emisor_en_cartera:
        obs.append(Observacion(
            INFO,
            f"Ya tenés {d.emisor} en la cartera ({', '.join(d.emisor_en_cartera)}): el monto simulado se suma a esa misma exposición.",
            "un CEDEAR, su acción de origen y sus variantes de moneda son un solo emisor", EJE_EMISOR,
        ))
    orden = {REVISAR: 0, ATENCION: 1, INFO: 2}
    obs.sort(key=lambda o: orden[o.nivel])      # estable: conserva el orden de generación dentro de cada nivel
    return {
        "version_reglas": VERSION_REGLAS,
        "ejes": ejes,
        "observaciones": [o.__dict__ for o in obs],
        "peso_monto_pct": d.monto_usd / d.total_despues_usd * 100.0 if d.total_despues_usd > 0 else None,
    }
