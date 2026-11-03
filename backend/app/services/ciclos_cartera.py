"""Cruce de «Ciclos de mercado» con la cartera real: exposición por estado del ciclo, instrumentos de un
grupo y simulador de rotación.

No hay una segunda clasificación: las posiciones y su sector, país y región salen de los mismos cálculos que
Exposición (`_clasificados_valorizados` + `clasificacion_analytics`), con el mismo total de cartera y los
mismos buckets residuales («Sin clasificar», «Sin sector», «Sin país», «Sin región»). Nada se descarta.

Dos tipos de pertenencia, que no se mezclan:
- **Dimensiones excluyentes** (sector, región, país): cada posición cae en una sola categoría y cada
  dimensión suma 100 %. Es donde se reparte el capital por cuadrante.
- **Pertenencias superpuestas** (industrias, commodities, temas): una empresa puede ser tecnología,
  semiconductores e inteligencia artificial a la vez. Se informan aparte, **no se suman** entre sí ni con
  las dimensiones excluyentes; la unión de cada tipo cuenta cada posición una sola vez.

El simulador de rotación trabaja sobre una copia en memoria: no escribe movimientos, no modifica la cartera
y no estima ningún rendimiento futuro.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from sqlalchemy.orm import Session

from . import ciclos_analytics as ca
from . import ciclos_catalogo as cc
from . import ciclos_engine as eng
from . import clasificacion_analytics
from . import clasificacion_engine as ce
from . import impacto_cartera_engine as ie
from . import simulador_decision as sd
from .clasificacion_analytics import Contexto
from .etiquetas import BUCKETS_RESIDUALES, SIN_PAIS, SIN_REGION, SIN_SECTOR
from .inversiones_analytics import (
    _agrupar, _atributo, _clasificados_valorizados, get_configuracion_cartera, get_mep_actual,
    get_rendimiento_por_ticker,
)

VERSION_REGLAS = 1
CARTERA_SIMULADA = "(simulada)"
PREFIJO_DESTINO = "CICLO:"
TOLERANCIA_USD = 0.01
EPS = 1e-9

# (nombre en pantalla, atributo de la clasificación, eje del catálogo, bucket residual)
EJES_EXCLUYENTES = (
    ("Sector", "sector", "sector", SIN_SECTOR),
    ("Región", "region", "region", SIN_REGION),
    ("País", "pais", "pais", SIN_PAIS),
)
TIPOS_SUPERPUESTOS = ("industria", "commodity", "tema")

CUADRANTE_TEXTO = {
    eng.LEADING: "Leading (fortaleza y momentum relativos positivos)",
    eng.WEAKENING: "Weakening (fortaleza positiva, momentum en baja)",
    eng.LAGGING: "Lagging (fortaleza y momentum relativos negativos)",
    eng.IMPROVING: "Improving (fortaleza negativa, momentum en alza)",
}

AVISO_SUPERPUESTOS = (
    "Las industrias, los commodities y los temas pueden superponerse (por ejemplo, una misma empresa es tecnología, "
    "semiconductores e inteligencia artificial): no se suman entre sí ni con sector, región o país."
)


def _n(texto) -> str:
    return ce._clave(texto)


# ---------------------------------------------------------------------------------------------
# Pertenencia
# ---------------------------------------------------------------------------------------------

def _pertenece_directo(g: cc.Grupo, ticker: str, base: str, clasif) -> bool:
    if g.proxy and _n(g.proxy) in (_n(ticker), _n(base)):
        return True
    for eje, valores in g.eje_cartera:
        if clasif is not None and _n(clasif.get(eje)) in {_n(v) for v in valores}:
            return True
    for clave, valores in g.cartera.items():
        if not valores:
            continue
        if clave == "tickers":
            if {_n(ticker), _n(base)} & {_n(v) for v in valores}:
                return True
        elif clasif is not None and _n(clasif.get(clave)) in {_n(v) for v in valores}:
            return True
    return False


def pertenece(cat: cc.Catalogo, g: cc.Grupo, ticker: str, base: str, clasif) -> bool:
    """La posición pertenece al grupo o a alguno de sus hijos (el oro es también un commodity)."""
    if _pertenece_directo(g, ticker, base, clasif):
        return True
    return any(pertenece(cat, h, ticker, base, clasif) for h in cat.hijos(g.id) if h.activo)


def _por_ticker(pos) -> dict[str, list[float]]:
    """Valor en USD y ARS por ticker, sumando las carteras (en el consolidado un ticker puede estar en varias)."""
    out: dict[str, list[float]] = {}
    for _, t, usd, ars in pos.valores:
        acc = out.setdefault(t, [0.0, 0.0])
        acc[0] += usd
        acc[1] += ars
    return out


def _mapa_excluyente(cat: cc.Catalogo, eje_cat: str) -> dict[str, cc.Grupo]:
    return {_n(v): g for g in cat.activos() for e, valores in g.eje_cartera if e == eje_cat for v in valores}


# ---------------------------------------------------------------------------------------------
# Exposición por estado del ciclo
# ---------------------------------------------------------------------------------------------

def _estado_item(estado: dict | None, grupo: cc.Grupo | None, etiqueta: str) -> tuple[str, str | None, str | None, str | None]:
    """`(clave, cuadrante, confirmado, motivo)`: en qué rubro de «por cuadrante» cae una categoría."""
    if etiqueta in BUCKETS_RESIDUALES:
        return "sin_clasificar", None, None, "la posición no tiene esta clasificación"
    if grupo is None:
        return "sin_grupo", None, None, "la categoría no tiene un grupo en el catálogo de ciclos"
    if estado is None or estado["estado"] == eng.ESTADO_SIN_DATOS:
        return "sin_datos", None, None, (estado or {}).get("motivo") or "el grupo no tiene datos"
    if estado["estado"] == eng.ESTADO_DESACTUALIZADO:
        return "desactualizado", None, estado["confirmado"], estado.get("motivo")
    if estado["estado"] != eng.ESTADO_OK:
        return "insuficiente", None, None, estado.get("motivo")
    return estado["cuadrante"], estado["cuadrante"], estado["confirmado"], None


def _por_cuadrante(items: list[dict], campo: str) -> list[dict]:
    claves = [*eng.CUADRANTES, "sin_estado"]
    pesos = dict.fromkeys(claves, 0.0)
    for i in items:
        c = i[campo] if i[campo] in eng.CUADRANTES else "sin_estado"
        pesos[c] += i["porcentaje"]
    return [{"cuadrante": c, "porcentaje": round(pesos[c], 2)} for c in claves]


def _sin_estado_detalle(items: list[dict]) -> list[dict]:
    pesos: dict[str, float] = {}
    for i in items:
        if i["cuadrante"] is None:
            pesos[i["rubro"]] = pesos.get(i["rubro"], 0.0) + i["porcentaje"]
    return [{"motivo": k, "porcentaje": round(v, 2)} for k, v in sorted(pesos.items(), key=lambda kv: -kv[1])]


def exposicion(cartera: str | None, db: Session, benchmark: str | None = None, hoy: date | None = None) -> dict:
    """Dónde está el capital según el estado actual de cada ciclo. `cartera=None` es el consolidado."""
    hoy = hoy or date.today()
    cat = cc.cargar()
    pos = _clasificados_valorizados(cartera, db)
    estados = ca.estados_de_rotacion(db, benchmark, hoy)
    total = pos.total_usd()

    dimensiones = []
    for nombre, attr, eje_cat, residual in EJES_EXCLUYENTES:
        if attr == "region" and not clasificacion_analytics.modo_auto():
            continue
        mapa = _mapa_excluyente(cat, eje_cat)
        items = []
        for it in _agrupar(
            [(_atributo(pos.instrumentos, t, attr, pos.clasif), usd, ars) for _, t, usd, ars in pos.valores], sin_dato=residual,
        ):
            grupo = mapa.get(_n(it["etiqueta"]))
            rubro, cuadrante, confirmado, motivo = _estado_item(estados.get(grupo.id) if grupo else None, grupo, it["etiqueta"])
            items.append({**it, "grupo_id": grupo.id if grupo else None, "grupo_nombre": grupo.nombre if grupo else None,
                          "rubro": rubro, "cuadrante": cuadrante, "confirmado": confirmado, "motivo_sin_estado": motivo,
                          "residual": it["etiqueta"] in BUCKETS_RESIDUALES})
        dimensiones.append({
            "dimension": nombre, "items": items, "por_cuadrante": _por_cuadrante(items, "cuadrante"),
            "por_cuadrante_confirmado": _por_cuadrante(items, "confirmado"), "sin_estado_detalle": _sin_estado_detalle(items),
        })

    ctx = Contexto(db)
    valores = _por_ticker(pos)
    base_de = {t: ctx.base(t) for t in valores}
    superpuestas, uniones = [], {t: set() for t in TIPOS_SUPERPUESTOS}
    for g in cat.activos():
        if g.tipo not in TIPOS_SUPERPUESTOS or g.eje_cartera:
            continue
        miembros = [t for t in valores if pertenece(cat, g, t, base_de[t], pos.clasif.get(t))]
        if not miembros:
            continue
        uniones[g.tipo].update(miembros)
        usd = sum(valores[t][0] for t in miembros)
        est = estados.get(g.id)
        rubro, cuadrante, confirmado, motivo = _estado_item(est, g, g.nombre)
        superpuestas.append({
            "grupo_id": g.id, "nombre": g.nombre, "tipo": g.tipo, "padre": g.padre, "valor_usd": round(usd, 2),
            "porcentaje": round(usd / total * 100, 2) if total > EPS else 0.0, "emisores": sorted({base_de[t] for t in miembros}),
            "tickers": sorted(miembros), "rubro": rubro, "cuadrante": cuadrante, "confirmado": confirmado, "motivo_sin_estado": motivo,
            "lista_curada": g.lista_curada, "nota": g.nota,
        })
    superpuestas.sort(key=lambda s: -s["porcentaje"])
    union_pct = {tipo: round(sum(valores[t][0] for t in ts) / total * 100, 2) if total > EPS else 0.0 for tipo, ts in uniones.items()}

    sin_clasificar = []
    for t, (usd, _) in sorted(valores.items(), key=lambda kv: -kv[1][0]):
        faltan = [nombre.lower() for nombre, attr, _, _ in EJES_EXCLUYENTES
                  if (attr != "region" or clasificacion_analytics.modo_auto()) and not _atributo(pos.instrumentos, t, attr, pos.clasif)]
        if faltan or t in pos.sin_ficha:
            sin_clasificar.append({"ticker": t, "emisor": base_de[t], "valor_usd": round(usd, 2),
                                   "porcentaje": round(usd / total * 100, 2) if total > EPS else 0.0,
                                   "faltan": faltan, "sin_ficha": t in pos.sin_ficha})

    sector = next((d for d in dimensiones if d["dimension"] == "Sector"), None)
    pesos = {p["cuadrante"]: p["porcentaje"] for p in (sector["por_cuadrante"] if sector else [])}
    estados_ok = [e for e in estados.values() if e["estado"] == eng.ESTADO_OK]
    advertencias = []
    if not estados_ok:
        advertencias.append("Todavía no hay estados de rotación calculados (faltan datos de los proxies): la cartera aparece «sin estado».")
    if pos.avisos()["aproximadas"]:
        advertencias.append("Hay posiciones valuadas al costo por falta de cotización: los pesos las incluyen a ese valor.")
    return {
        "version_reglas": VERSION_REGLAS, "cartera": cartera, "total_usd": round(total, 2), "total_ars": round(pos.total_ars(), 2),
        "benchmark": benchmark, "dimensiones": dimensiones, "superpuestas": superpuestas, "aviso_superpuestos": AVISO_SUPERPUESTOS,
        "uniones_pct": union_pct, "sin_clasificar": sin_clasificar, "avisos": pos.avisos(),
        "resumen": {
            "en_leading_pct": pesos.get(eng.LEADING, 0.0), "en_weakening_pct": pesos.get(eng.WEAKENING, 0.0),
            "en_lagging_pct": pesos.get(eng.LAGGING, 0.0), "en_improving_pct": pesos.get(eng.IMPROVING, 0.0),
            "sin_estado_pct": pesos.get("sin_estado", 0.0), "dimension": "Sector",
            "lectura": "Porcentaje del capital por estado actual del sector en que está. Describe dónde está el capital hoy; no es una recomendación.",
        },
        "estados": {k: v for k, v in estados.items()},
        "advertencias": advertencias,
    }


# ---------------------------------------------------------------------------------------------
# Instrumentos de un grupo
# ---------------------------------------------------------------------------------------------

def instrumentos_de_grupo(cartera: str | None, db: Session, grupo_id: str, benchmark: str | None = None, hoy: date | None = None) -> dict:
    """Las posiciones de la cartera que pertenecen al grupo, juntando por emisor (un CEDEAR, su variante en
    dólares y su acción de origen son un solo emisor)."""
    hoy = hoy or date.today()
    cat = cc.cargar()
    g = ca._grupo(cat, grupo_id)
    pos = _clasificados_valorizados(cartera, db)
    ctx = Contexto(db)
    total = pos.total_usd()
    valores = _por_ticker(pos)
    rend = {r["ticker"]: r for r in get_rendimiento_por_ticker(cartera, db)}
    por_emisor: dict[str, list[str]] = {}
    for t in valores:
        b = ctx.base(t)
        if pertenece(cat, g, t, b, pos.clasif.get(t)):
            por_emisor.setdefault(b, []).append(t)

    expo_usd = sum(valores[t][0] for ts in por_emisor.values() for t in ts)
    filas = []
    for emisor, tickers in por_emisor.items():
        usd = sum(valores[t][0] for t in tickers)
        filas_r = [rend[t] for t in tickers if t in rend]
        actual = sum(r.get("valor_actual_usd") or 0.0 for r in filas_r)
        invertido = sum(r.get("valor_invertido_usd") or 0.0 for r in filas_r)
        incompleto = len(filas_r) < len(tickers) or any(
            r.get("costo_incompleto") or r.get("valuado_al_costo")
            or r.get("valor_invertido_usd") is None or r.get("valor_actual_usd") is None
            for r in filas_r)
        medible = not incompleto and invertido > EPS
        c = pos.clasif.get(max(tickers, key=lambda x: valores[x][0]))
        filas.append({
            "emisor": emisor, "tickers": sorted(tickers), "nombre": next((pos.instrumentos[t].nombre for t in tickers if t in pos.instrumentos), emisor),
            "valor_usd": round(usd, 2), "peso_cartera_pct": round(usd / total * 100, 2) if total > EPS else 0.0,
            "peso_en_grupo_pct": round(usd / expo_usd * 100, 2) if expo_usd > EPS else 0.0,
            "rendimiento_pct": round((actual / invertido - 1) * 100, 2) if medible else None,
            "resultado_usd": round(actual - invertido, 2) if medible else None,
            "rendimiento_no_calculable": None if medible else "falta cotización o costo de alguna posición",
            "clasificacion": {k: c.get(k) for k in ("tipo", "sector", "industria", "pais", "region")} if c else None,
            "fuentes": dict(c.fuentes) if c else {},
        })
    filas.sort(key=lambda f: -f["valor_usd"])
    medibles = [f for f in filas if f["resultado_usd"] is not None]
    estado = ca.estados_de_rotacion(db, benchmark, hoy).get(g.id)
    return {
        "grupo": ca._info_grupo(g), "estado": estado, "cartera": cartera,
        "exposicion_usd": round(expo_usd, 2), "exposicion_pct": round(expo_usd / total * 100, 2) if total > EPS else 0.0,
        "instrumentos": filas,
        "resultado_usd": round(sum(f["resultado_usd"] for f in medibles), 2) if medibles else None,
        "resultado_parcial": len(medibles) < len(filas),
        "regla": {**{f"exacta_{e}": list(v) for e, v in g.eje_cartera}, **{k: list(v) for k, v in g.cartera.items() if v}, "proxy": g.proxy},
        "avisos": [a for a in (AVISO_SUPERPUESTOS if not g.eje_cartera else None, g.nota) if a],
    }


# ---------------------------------------------------------------------------------------------
# Simulador de rotación
# ---------------------------------------------------------------------------------------------

def _clasificacion_destino(cat: cc.Catalogo, g: cc.Grupo) -> ce.ClasificacionResuelta:
    """Cómo se clasifica la posición simulada que representa al grupo de destino: sólo con lo que el catálogo
    afirma del grupo. Lo que no define queda sin dato (cae en «Sin …»)."""
    def _de_eje(grupo, eje):
        for e, valores in grupo.eje_cartera:
            if e == eje and len(valores) == 1:
                return valores[0]
        return None

    sector = pais = region = None
    actual = g
    while actual is not None and sector is None:
        sector = _de_eje(actual, "sector")
        actual = cat.grupos.get(actual.padre) if actual.padre else None
    if sector is None:
        sector = {"commodity": "Materias primas"}.get(g.tipo) or {"bitcoin": "Cripto", "ethereum": "Cripto", "bonos-eeuu": "Renta fija",
                                                                  "bonos-tesoro-largo": "Renta fija"}.get(g.id)
    pais = _de_eje(g, "pais")
    region = ce.region_canonica(g.region)
    if pais is None and region == ce.REGION_EEUU:
        pais = "Estados Unidos"
    return ce.ClasificacionResuelta(sector=sector, pais=pais, region=region, fuentes={})


def _validar_pct(pct) -> float:
    if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 0 < pct <= 100:
        raise ValueError("el porcentaje a trasladar debe ser mayor que 0 y hasta 100")
    return float(pct)


def simular_rotacion(
    cartera: str | None, db: Session, origen_id: str, destino_id: str, pct: float, benchmark: str | None = None,
    hoy: date | None = None,
) -> dict:
    """«¿Qué pasaría si traslado `pct` % de mi cartera del grupo `origen` al grupo `destino`?» Mezcla antes y después
    por emisor, instrumento, sector, país y región, con los umbrales de Salud y la distancia a los objetivos.

    `ValueError` si algo no vale; `ca.NoEncontrado` si un grupo no existe. No escribe nada.
    """
    pct = _validar_pct(pct)
    hoy = hoy or date.today()
    cat = cc.cargar()
    origen, destino = ca._grupo(cat, origen_id), ca._grupo(cat, destino_id)
    if origen.id == destino.id:
        raise ValueError("el grupo de origen y el de destino son el mismo")

    pos = _clasificados_valorizados(cartera, db)
    total = pos.total_usd()
    if total <= EPS:
        raise ValueError("la cartera no tiene posiciones valuadas")
    ctx = Contexto(db)
    valores_t = _por_ticker(pos)
    miembros = {t for t in valores_t if pertenece(cat, origen, t, ctx.base(t), pos.clasif.get(t))}
    expo = sum(valores_t[t][0] for t in miembros)
    monto = total * pct / 100
    if expo <= EPS:
        raise ValueError(f"la cartera no tiene exposición a {origen.nombre}: no hay nada para trasladar")
    if monto > expo + TOLERANCIA_USD:
        raise ValueError(f"{origen.nombre} pesa {expo / total * 100:.1f} % de la cartera: no se puede trasladar {pct:g} %")

    factor = max(0.0, 1.0 - monto / expo)
    mep = get_mep_actual(db)
    sintetico = f"{PREFIJO_DESTINO}{destino.id}"
    etiqueta_destino = f"Destino: {destino.nombre}"
    valores = [(c, t, u * factor, a * factor) if t in miembros else (c, t, u, a) for c, t, u, a in pos.valores]
    valores.append((cartera or CARTERA_SIMULADA, sintetico, monto, monto * mep if mep else 0.0))
    despues = replace(pos, valores=valores, clasif={**pos.clasif, sintetico: _clasificacion_destino(cat, destino)})

    def _entradas(p, etiqueta):
        return [(etiqueta(t), u, a) for _, t, u, a in p.valores]

    def _emisor(t):
        return etiqueta_destino if t == sintetico else ctx.base(t)

    def _instrumento(t):
        return etiqueta_destino if t == sintetico else t

    def _attr(p, t, a):
        return _atributo(p.instrumentos, t, a, p.clasif)

    ejes_in = [
        ie.EjeEntrada(ie.EJE_EMISOR, _agrupar(_entradas(pos, _emisor)), _agrupar(_entradas(despues, _emisor)), ""),
        ie.EjeEntrada("Instrumento", _agrupar(_entradas(pos, _instrumento)), _agrupar(_entradas(despues, _instrumento)), ""),
    ]
    clasificados = [("Sector", "sector", SIN_SECTOR), ("País", "pais", SIN_PAIS)]
    if clasificacion_analytics.modo_auto():
        clasificados.append(("Región", "region", SIN_REGION))
    for nombre, attr, sin_dato in clasificados:
        ejes_in.append(ie.EjeEntrada(
            nombre, _agrupar(_entradas(pos, lambda t, a=attr: _attr(pos, t, a)), sin_dato=sin_dato),
            _agrupar(_entradas(despues, lambda t, a=attr: _attr(despues, t, a)), sin_dato=sin_dato), ""))

    tickers_por_emisor: dict[str, list[str]] = {}
    for _, t, _, _ in despues.valores:
        lista = tickers_por_emisor.setdefault(_emisor(t), [])
        if t not in lista:
            lista.append(t)
    tickers_por_emisor = {k: sorted(v) for k, v in tickers_por_emisor.items()}
    nombres = {b: f.nombre for b, f in ctx.auto.items() if f.nombre and b in tickers_por_emisor}
    ejes = []
    for e in ejes_in:
        eje = ie.comparar_eje(e, tickers_por_emisor, nombres)
        for f in eje["items"]:
            f["afectada"] = abs(f["delta_pp"]) > 1e-9
        eje["etiqueta_compra"] = None
        ejes.append(eje)

    config = get_configuracion_cartera(cartera, db)
    observaciones = sd._observaciones(ejes, config["peso_maximo"], None)
    estados = ca.estados_de_rotacion(db, benchmark, hoy)
    ge, gd = estados.get(origen.id), estados.get(destino.id)
    if ge and gd and ge.get("cuadrante") and gd.get("cuadrante"):
        observaciones.append({
            "nivel": ie.INFO, "eje": "Ciclos",
            "texto": f"Hoy {origen.nombre} figura en {CUADRANTE_TEXTO[ge['cuadrante']]} y {destino.nombre} en {CUADRANTE_TEXTO[gd['cuadrante']]}, "
                     "cada uno contra su benchmark. Es una descripción del momento, no una señal.",
            "regla": "estado de rotación relativa al último dato disponible",
        })
    clasif_dest = despues.clasif[sintetico]
    for nombre, attr in (("sector", "sector"), ("país", "pais"), ("región", "region")):
        if attr == "region" and not clasificacion_analytics.modo_auto():
            continue
        if clasif_dest.get(attr) is None:
            observaciones.append({
                "nivel": ie.INFO, "eje": nombre.capitalize(), "regla": "el destino toma sólo lo que el catálogo afirma del grupo",
                "texto": f"El catálogo no define {nombre} para {destino.nombre}: el monto trasladado cuenta como «Sin {nombre}».",
            })
    orden = {ie.REVISAR: 0, ie.ATENCION: 1, ie.INFO: 2}
    observaciones.sort(key=lambda o: orden[o["nivel"]])

    notas = []
    if not mep:
        notas.append("No hay un MEP cargado: el total en pesos no incluye el monto trasladado.")
    return {
        "version_reglas": VERSION_REGLAS, "cartera": cartera,
        "rotacion": {
            "origen": {"id": origen.id, "nombre": origen.nombre, "exposicion_usd": round(expo, 2),
                       "exposicion_pct": round(expo / total * 100, 2), "estado": ge},
            "destino": {"id": destino.id, "nombre": destino.nombre, "proxy": destino.proxy, "estado": gd,
                        "clasificacion": {k: clasif_dest.get(k) for k in ("sector", "pais", "region")}},
            "pct_cartera": pct, "monto_usd": round(monto, 2), "pct_del_origen": round(monto / expo * 100, 2),
            "posiciones_origen": sorted(
                [{"ticker": t, "antes_usd": round(valores_t[t][0], 2), "despues_usd": round(valores_t[t][0] * factor, 2)} for t in miembros],
                key=lambda p: -p["antes_usd"]),
        },
        "total": {"antes_usd": round(total, 2), "despues_usd": round(despues.total_usd(), 2)},
        "ejes": ejes, "observaciones": observaciones,
        "rebalanceo": sd._rebalanceo(cartera, db, pos, despues, _attr),
        "supuestos": [
            "Cada posición del grupo de origen se reduce en la misma proporción.",
            f"El destino se simula como una posición con la clasificación que el catálogo afirma de {destino.nombre}; lo que no define queda en «Sin …».",
            "Lo trasladado se toma como porcentaje del valor total de la cartera, con las mismas cotizaciones que Exposición.",
            "No se estima ningún rendimiento futuro: sólo cómo quedaría la mezcla. No se calculan impuestos ni comisiones.",
            "Es una simulación en memoria: no escribe movimientos ni modifica la cartera.",
        ],
        "notas": notas, "avisos": pos.avisos(),
    }
