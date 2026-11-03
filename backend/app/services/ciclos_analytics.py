"""Adaptador DB → `ciclos_engine`: panorama de rotación, detalle de un grupo, relaciones y ficha de país.

Las series salen de `serie_ohlcv` bajo `SIMBOLO@BENCH` (las baja `ciclos_ingesta`) y se leen con
`benchmarks.barras`; no se duplica ningún histórico. El catálogo (`ciclos_catalogo`) dice qué proxy mide
cada grupo y contra qué benchmark.

Reglas que atraviesan todo:
- **La rotación (RS-Ratio/RS-Momentum) se calcula siempre sobre las series en USD**: el tipo de cambio se
  cancela en el cociente grupo/benchmark, así que el estado de rotación no depende de la moneda elegida.
  Rendimientos, riesgo y gráficos sí se convierten a pesos (por el MEP de cada fecha, sin completar
  fechas en que no hay MEP).
- Un grupo sin serie, con historia corta o desactualizado se informa tal cual (`estado` + `motivo`): nada se
  estima ni se completa.
- Cada respuesta lleva `meta` con fuente, fechas, moneda, tipo de rendimiento, benchmark y limitaciones.
- No hay score único: cada dimensión (rotación, rendimiento, riesgo, tendencia) se informa por separado.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..database import CiclosProxyEstado, IndiceMercado
from . import benchmarks, ciclos_catalogo as cc, ciclos_engine as eng, ciclos_regimen
from .cache import cache_por_sync

MONEDAS = ("USD", "ARS")
MESES_PERIODO = {"3M": 3, "6M": 6, "1A": 12, "3A": 36}
MESES_HORIZONTE = {"1A": 12, "3A": 36, "5A": 60, "10A": 120}
TOLERANCIA_MEP_DIAS = 7
MAX_EXTRA = 5
MAX_CORRELACION = 15
MAX_COMPARACION = 6
SEMANAS_HISTORIAL_DETALLE = 260
CAMBIOS_RECIENTES_SEMANAS = 26
MAX_CAMBIOS = 12
# Más de tres años (con holgura para el año bisiesto) en un gráfico diario es ruido: se pasa a semanal.
DIAS_PASO_SEMANAL = 1100
GRUPOS_CORRELACION_DEFECTO = (
    "tecnologia", "semiconductores", "consumo-basico", "energia", "materiales", "oro", "bitcoin",
    "nasdaq-100", "emergentes", "brasil", "china",
)

LIMITACIONES_GENERALES = (
    "Cada grupo se mide con un proxy (un ETF o índice): no es el sector o mercado completo.",
    "Rendimiento pasado: no anticipa el futuro. La rotación y el momentum describen lo ocurrido, no predicen.",
    "La rotación relativa es una metodología propia inspirada en RRG (no la de los indicadores JdK).",
)


class NoEncontrado(LookupError):
    """El grupo, período o benchmark pedido no existe en el catálogo."""


# ---------------------------------------------------------------------------------------------
# Acceso a las series
# ---------------------------------------------------------------------------------------------

class Fuentes:
    """Series del catálogo para una consulta: lee cada símbolo una sola vez y convierte de moneda."""

    def __init__(self, db: Session, cat: cc.Catalogo):
        self.db, self.cat = db, cat
        self._series: dict[str, eng.Serie] = {}
        self._estados: dict[str, CiclosProxyEstado] | None = None
        self._mep: tuple[list[date], list[float]] | None = None
        self.sin_mep = False

    def simbolo(self, simbolo: str) -> eng.Serie:
        if simbolo not in self._series:
            self._series[simbolo] = eng.normalizar([(b.fecha, b.cierre) for b in benchmarks.barras(self.db, simbolo)])
        return self._series[simbolo]

    def estados(self) -> dict[str, CiclosProxyEstado]:
        if self._estados is None:
            self._estados = {e.simbolo: e for e in self.db.query(CiclosProxyEstado).all()}
        return self._estados

    def nativa(self, g: cc.Grupo) -> eng.Serie:
        """Serie del grupo en su moneda de referencia (hoy siempre USD)."""
        if g.moneda != "USD":
            return []
        if g.sintetico:
            miembros = [self.cat.grupos[m] for m in g.sintetico["miembros"]]
            return eng.sintetico_equiponderado([self.nativa(m) for m in miembros])
        return self.simbolo(g.proxy)

    def motivo_sin_datos(self, g: cc.Grupo) -> str | None:
        if g.moneda != "USD":
            return f"moneda de referencia {g.moneda} no soportada"
        if g.sintetico:
            return "algún miembro del grupo sintético no tiene datos"
        est = self.estados().get(g.proxy)
        if est is None:
            return f"todavía no se descargó {g.proxy} (la ingesta de ciclos no corrió)"
        if est.estado == "no_encontrado":
            return f"Yahoo no devolvió datos para {g.proxy}"
        if est.estado == "error" and est.error:
            return f"error al descargar {g.proxy}: {est.error}"
        return "sin datos"

    def mep(self) -> tuple[list[date], list[float]]:
        if self._mep is None:
            filas = (self.db.query(IndiceMercado.fecha, IndiceMercado.mep)
                     .filter(IndiceMercado.mep.isnot(None)).order_by(IndiceMercado.fecha).all())
            self._mep = ([f for f, _ in filas], [float(m) for _, m in filas])
        return self._mep

    def en_moneda(self, serie: eng.Serie, moneda: str) -> eng.Serie:
        """USD → la moneda pedida. En pesos, cada fecha usa el MEP de ese día (o de hasta `TOLERANCIA_MEP_DIAS`
        antes); una fecha sin MEP se descarta, no se completa."""
        if moneda == "USD":
            return serie
        fechas, valores = self.mep()
        if not fechas:
            self.sin_mep = True
            return []
        out = []
        for f, c in serie:
            i = bisect_right(fechas, f) - 1
            if i >= 0 and (f - fechas[i]).days <= TOLERANCIA_MEP_DIAS:
                out.append((f, c * valores[i]))
        if len(out) < len(serie):
            self.sin_mep = True
        return out

    def serie_mep(self) -> eng.Serie:
        fechas, valores = self.mep()
        return list(zip(fechas, valores))


# ---------------------------------------------------------------------------------------------
# Piezas comunes
# ---------------------------------------------------------------------------------------------

def _validar_moneda(moneda: str) -> str:
    m = (moneda or "").upper()
    if m not in MONEDAS:
        raise ValueError(f"moneda inválida {moneda!r} (USD o ARS)")
    return m


def _grupo(cat: cc.Catalogo, id_: str) -> cc.Grupo:
    g = cat.grupos.get(id_)
    if g is None or not g.activo:
        raise NoEncontrado(f"grupo inexistente: {id_}")
    return g


def _benchmark_por_defecto(cat: cc.Catalogo, grupos: list[cc.Grupo]) -> cc.Grupo | None:
    elegidos = [g.benchmark for g in grupos if g.benchmark]
    if elegidos:
        mas_comun = max(set(elegidos), key=elegidos.count)
        if mas_comun in cat.grupos and cat.grupos[mas_comun].activo:
            return cat.grupos[mas_comun]
    return next(iter(cat.benchmarks()), None)


def _resolver_benchmark(cat: cc.Catalogo, benchmark: str | None, grupos: list[cc.Grupo]) -> cc.Grupo | None:
    if benchmark:
        g = cat.grupos.get(benchmark)
        if g is None or not g.activo or not g.es_benchmark:
            raise NoEncontrado(f"benchmark inexistente: {benchmark}")
        return g
    return _benchmark_por_defecto(cat, grupos)


def _benchmark_efectivo(cat: cc.Catalogo, g: cc.Grupo, pedido: str | None = None) -> cc.Grupo | None:
    """Contra qué se mide `g`: el pedido, el habitual del grupo o, si el grupo es un benchmark sin otro
    (S&P 500, Global), el otro benchmark: EE.UU. se mide contra Global y Global contra EE.UU."""
    if pedido:
        return _resolver_benchmark(cat, pedido, [g])
    id_ = g.benchmark or ("global" if g.id != "global" else "estados-unidos")
    b = cat.grupos.get(id_)
    return b if b is not None and b.activo and b.id != g.id else None


def _info_grupo(g: cc.Grupo) -> dict:
    return {
        "id": g.id, "nombre": g.nombre, "tipo": g.tipo, "padre": g.padre, "proxy": g.proxy,
        "benchmark": g.benchmark, "moneda": g.moneda, "region": g.region, "fuente": g.fuente,
        "tipo_rendimiento": g.tipo_rendimiento, "exclusivo": g.exclusivo, "lista_curada": g.lista_curada,
        "nota": g.nota, "descripcion": g.descripcion,
    }


def _rrg_resumen(rot: dict, semanas: int) -> dict:
    tr = rot["transiciones"]
    cambios = [c for c in (tr["cambios_confirmados"] if tr else []) if c["anterior"] is not None]
    return {
        "estado": rot["estado"], "motivo": rot["motivo"], "ventana": rot["ventana"], "ultima_fecha": rot["ultima_fecha"],
        "semanas_usadas": rot["semanas_usadas"], "actual": rot["actual"],
        # Un punto viejo no se dibuja como si fuera actual.
        "trayectoria": eng.trayectoria(rot["puntos"], semanas) if rot["estado"] == eng.ESTADO_OK else [],
        "cuadrante_confirmado": tr["cuadrante_confirmado"] if tr else None,
        "pendiente": tr["pendiente"] if tr else None,
        "ultimo_cambio": cambios[-1] if cambios else None,
    }


def _ultima_actualizacion(fuentes: Fuentes):
    oks = [e.ultimo_ok for e in fuentes.estados().values() if e.ultimo_ok]
    return max(oks) if oks else None


def _meta(
    fuentes: Fuentes, grupos: list[cc.Grupo], bench: cc.Grupo | None, *, moneda: str, desde: date | None,
    hasta: date | None, ultima_fecha_datos: date | None, advertencias: list[str] | None = None,
    nota_moneda: bool = True,
) -> dict:
    """Lo que cada gráfico y tabla debe poder responder: fuente, fechas, período, moneda, tipo de rendimiento,
    benchmark y limitaciones de cobertura."""
    tipos = sorted({g.tipo_rendimiento for g in grupos} | ({bench.tipo_rendimiento} if bench else set()))
    advertencias = list(advertencias or [])
    if len(tipos) > 1:
        advertencias.append("Se mezclan rendimientos totales (con distribuciones) y de precio: la comparación no es homogénea.")
    if any("roll" in (g.nota or "") for g in grupos):
        advertencias.append("Algunos grupos son ETFs de futuros: su rendimiento incluye el efecto del roll de contratos y no es el precio spot.")
    if moneda == "ARS" and fuentes.sin_mep:
        advertencias.append("En pesos: las fechas sin MEP se descartaron (no se completaron); la serie puede tener huecos.")
    if moneda == "ARS" and nota_moneda:
        advertencias.append("El estado de rotación (cuadrantes) se calcula en dólares: no cambia con la moneda elegida.")
    fuentes_txt = sorted({g.fuente for g in grupos} | ({bench.fuente} if bench else set())) or [cc.FUENTE_DEFECTO]
    return {
        "fuente": ", ".join(fuentes_txt) + " (cierres diarios ajustados por dividendos y splits)",
        "ultima_actualizacion": _ultima_actualizacion(fuentes),
        "ultima_fecha_datos": ultima_fecha_datos,
        "periodo": {"desde": desde, "hasta": hasta},
        "moneda": moneda,
        "tipo_rendimiento": "mixto" if len(tipos) > 1 else (tipos[0] if tipos else None),
        "benchmark": {"id": bench.id, "nombre": bench.nombre, "proxy": bench.proxy} if bench else None,
        "limitaciones": list(LIMITACIONES_GENERALES),
        "advertencias": advertencias,
    }


def _por_serie_vacia(motivo: str | None) -> dict:
    return {"estado": eng.ESTADO_SIN_DATOS, "motivo": motivo or "sin datos"}


def _cambios_liderazgo(grupos_payload: list[dict], hasta: date | None) -> list[dict]:
    """Cambios de cuadrante **confirmados** en las últimas semanas, del más reciente al más antiguo."""
    if hasta is None:
        return []
    out = []
    for p in grupos_payload:
        c = (p.get("rrg") or {}).get("ultimo_cambio")
        if c and (hasta - c["desde"]).days <= CAMBIOS_RECIENTES_SEMANAS * 7:
            out.append({"grupo_id": p["id"], "nombre": p["nombre"], "desde": c["desde"], "de": c["anterior"],
                        "a": c["cuadrante"], "semanas": c["semanas"]})
    out.sort(key=lambda c: c["desde"], reverse=True)
    return out[:MAX_CAMBIOS]


# ---------------------------------------------------------------------------------------------
# Panorama
# ---------------------------------------------------------------------------------------------

def _opciones(cat: cc.Catalogo) -> dict:
    return {
        "tipos": [t for t in cc.TIPOS if any(t in g.vistas for g in cat.activos())],
        "benchmarks": [{"id": g.id, "nombre": g.nombre, "proxy": g.proxy} for g in cat.benchmarks()],
        "periodos": list(MESES_PERIODO),
        "monedas": list(MONEDAS),
    }


@cache_por_sync
def panorama(
    db: Session, tipo: str = "sector", benchmark: str | None = None, moneda: str = "USD", periodo: str = "6M",
    grupos: tuple | None = None, ventana: int = eng.VENTANA_RRG, cola: int = eng.COLA_DEFECTO, hoy: date | None = None,
) -> dict:
    """Mapa de rotación, mapa de calor y cambios de liderazgo de un tipo de grupos contra un benchmark."""
    moneda = _validar_moneda(moneda)
    if tipo not in cc.TIPOS:
        raise ValueError(f"tipo inválido {tipo!r}")
    if periodo not in MESES_PERIODO:
        raise ValueError(f"período inválido {periodo!r} (3M, 6M, 1A o 3A)")
    if not 3 <= ventana <= 52 or not 1 <= cola <= 52:
        raise ValueError("ventana debe estar entre 3 y 52 semanas y cola entre 1 y 52")
    hoy = hoy or date.today()
    cat = cc.cargar()
    fuentes = Fuentes(db, cat)

    disponibles = [g for g in cat.activos() if tipo in g.vistas]
    if grupos is not None:
        pedidos = set(grupos)
        desconocidos = pedidos - {g.id for g in disponibles}
        if desconocidos:
            raise ValueError(f"grupos que no son de tipo {tipo}: {', '.join(sorted(desconocidos))}")
        disponibles = [g for g in disponibles if g.id in pedidos]
    bench = _resolver_benchmark(cat, benchmark, disponibles)
    base = {"filtros": {"tipo": tipo, "benchmark": bench.id if bench else None, "moneda": moneda, "periodo": periodo,
                        "ventana": ventana, "cola": cola, "grupos": [g.id for g in disponibles]},
            "opciones": {**_opciones(cat), "grupos": [{"id": g.id, "nombre": g.nombre} for g in cat.activos() if tipo in g.vistas]},
            "regimen": ciclos_regimen.evaluar()}

    b_usd = fuentes.nativa(bench) if bench else []
    if not b_usd:
        return {**base, "benchmark": _info_grupo(bench) if bench else None, "grupos": [], "horizontes": [], "fechas_horizontes": {},
                "cambios_liderazgo": [], "cobertura": {"total": len(disponibles), "con_rotacion": 0, "sin_datos": [], "insuficientes": [], "desactualizados": []},
                "meta": _meta(fuentes, disponibles, bench, moneda=moneda, desde=None, hasta=None, ultima_fecha_datos=None,
                              advertencias=["El benchmark no tiene datos: no se puede calcular ninguna rotación."]),
                "motivo": f"el benchmark {bench.nombre if bench else ''} no tiene datos: {fuentes.motivo_sin_datos(bench) if bench else 'no hay benchmarks'}"}

    hasta = b_usd[-1][0]
    b_m = fuentes.en_moneda(b_usd, moneda)
    semanas = eng.SEMANAS_POR_PERIODO[periodo]
    payloads, tablas = [], []
    cobertura = {"total": 0, "con_rotacion": 0, "sin_datos": [], "insuficientes": [], "desactualizados": []}
    for g in disponibles:
        if bench and g.id == bench.id:
            continue
        cobertura["total"] += 1
        a_usd = fuentes.nativa(g)
        info = _info_grupo(g)
        if not a_usd:
            motivo = fuentes.motivo_sin_datos(g)
            cobertura["sin_datos"].append({"id": g.id, "nombre": g.nombre, "motivo": motivo})
            payloads.append({**info, "ultima_fecha": None, "rrg": _por_serie_vacia(motivo), "rendimientos": {}, "riesgo": None, "tendencia": None})
            continue
        rot = eng.rotacion(a_usd, b_usd, ventana=ventana, cola=cola, hoy=hoy)
        a_m = fuentes.en_moneda(a_usd, moneda)
        rend = eng.rendimientos(a_m, b_m, hasta)
        tablas.append(rend)
        if rot["estado"] == eng.ESTADO_OK:
            cobertura["con_rotacion"] += 1
        elif rot["estado"] == eng.ESTADO_DESACTUALIZADO:
            cobertura["desactualizados"].append({"id": g.id, "nombre": g.nombre, "motivo": rot["motivo"]})
        else:
            cobertura["insuficientes"].append({"id": g.id, "nombre": g.nombre, "motivo": rot["motivo"]})
        payloads.append({
            **info, "ultima_fecha": a_usd[-1][0], "rrg": _rrg_resumen(rot, semanas),
            "rendimientos": {h: {"absoluto": v["absoluto"], "relativo": v["relativo"], "motivo": v["motivo"]} for h, v in rend.items()},
            "riesgo": eng.riesgo(a_m, eng.restar_meses(hasta, 36), hasta), "tendencia": eng.tendencia(eng.semanal(a_m)),
        })

    cubiertos = set(eng.horizontes_con_cobertura(tablas))
    horizontes = [h for h in eng.HORIZONTES if h in ("1M", "3M", "6M", "1A") or h in cubiertos]
    advertencias = []
    if cobertura["sin_datos"]:
        advertencias.append(f"{len(cobertura['sin_datos'])} grupo(s) sin datos: se muestran sin rotación ni rendimientos.")
    if cobertura["desactualizados"]:
        advertencias.append(f"{len(cobertura['desactualizados'])} grupo(s) con datos desactualizados: no se dibujan como actuales.")
    if cobertura["insuficientes"]:
        advertencias.append(f"{len(cobertura['insuficientes'])} grupo(s) con historia insuficiente para calcular la rotación.")
    if bench and any(g.benchmark and g.benchmark != bench.id for g in disponibles):
        advertencias.append(f"Todos los grupos se miden contra {bench.nombre}, aunque el benchmark habitual de alguno sea otro.")
    return {
        **base, "benchmark": {**_info_grupo(bench), "ultima_fecha": hasta}, "grupos": payloads, "horizontes": horizontes,
        "fechas_horizontes": {h: {"desde": eng.restar_meses(hasta, eng.HORIZONTES[h]), "hasta": hasta} for h in horizontes},
        "cambios_liderazgo": _cambios_liderazgo(payloads, hasta), "cobertura": cobertura, "motivo": None,
        "meta": _meta(fuentes, [g for g in disponibles if g.id != bench.id], bench, moneda=moneda,
                      desde=eng.restar_meses(hasta, MESES_PERIODO[periodo]), hasta=hasta, ultima_fecha_datos=hasta,
                      advertencias=advertencias),
    }


# ---------------------------------------------------------------------------------------------
# Detalle de un grupo
# ---------------------------------------------------------------------------------------------

def _rango(cat: cc.Catalogo, horizonte: str | None, desde: date | None, hasta: date | None, periodo_id: str | None,
           ultima: date, primera: date) -> tuple[date, date, str]:
    if periodo_id:
        p = next((p for p in cat.periodos if p["id"] == periodo_id), None)
        if p is None:
            raise NoEncontrado(f"período inexistente: {periodo_id}")
        return p["desde"], p["hasta"] or ultima, f"período «{p['nombre']}»"
    if desde or hasta:
        d, h = desde or primera, hasta or ultima
        if d >= h:
            raise ValueError("`desde` debe ser anterior a `hasta`")
        return d, h, "fechas elegidas"
    if horizonte in (None, "max"):
        return primera, ultima, "toda la historia disponible"
    if horizonte not in MESES_HORIZONTE:
        raise ValueError(f"horizonte inválido {horizonte!r} (1A, 3A, 5A, 10A o max)")
    return eng.restar_meses(ultima, MESES_HORIZONTE[horizonte]), ultima, f"últimos {horizonte}"


def _resumen_grupo(fuentes: Fuentes, g: cc.Grupo, b_usd: eng.Serie, moneda: str, hoy: date, ventana: int, hasta: date) -> dict:
    a_usd = fuentes.nativa(g)
    a_m = fuentes.en_moneda(a_usd, moneda)
    b_m = fuentes.en_moneda(b_usd, moneda) if b_usd else None
    rot = eng.rotacion(a_usd, b_usd, ventana=ventana, hoy=hoy)
    return {
        "rotacion": rot,
        "rendimientos": eng.rendimientos(a_m, b_m, hasta),
        "riesgo": eng.riesgo(a_m, eng.restar_meses(hasta, 36), hasta),
        "tendencia": eng.tendencia(eng.semanal(a_m)),
        "a_m": a_m, "b_m": b_m,
    }


def detalle(
    db: Session, grupo_id: str, *, benchmark: str | None = None, moneda: str = "USD", horizonte: str | None = "3A",
    desde: date | None = None, hasta: date | None = None, periodo_id: str | None = None, con: tuple = (),
    ventana: int = eng.VENTANA_RRG, hoy: date | None = None,
) -> dict:
    """Ficha de un grupo: rendimiento normalizado, fortaleza relativa, historial de rotación y un período a elegir."""
    moneda = _validar_moneda(moneda)
    hoy = hoy or date.today()
    cat = cc.cargar()
    g = _grupo(cat, grupo_id)
    pedidos = [i for i in dict.fromkeys(con) if i != g.id]
    if len(pedidos) > MAX_EXTRA:
        raise ValueError(f"se pueden comparar hasta {MAX_EXTRA} grupos adicionales")
    extras = [_grupo(cat, i) for i in pedidos]
    bench = _benchmark_efectivo(cat, g, benchmark)
    if bench and bench.id == g.id:
        bench = None
    fuentes = Fuentes(db, cat)
    a_usd = fuentes.nativa(g)
    b_usd = fuentes.nativa(bench) if bench else []
    info = {**_info_grupo(g), "hijos": [{"id": h.id, "nombre": h.nombre} for h in cat.hijos(g.id) if h.activo],
            "pertenencia": {**{f"exacta_{e}": list(v) for e, v in g.eje_cartera}, **{k: list(v) for k, v in g.cartera.items() if v}}}
    if not a_usd:
        motivo = fuentes.motivo_sin_datos(g)
        return {"grupo": info, "estado": eng.ESTADO_SIN_DATOS, "motivo": motivo, "benchmark": _info_grupo(bench) if bench else None,
                "rotacion": None, "rendimientos": {}, "riesgo": None, "tendencia": None, "series": [], "filas": [], "rango": None,
                "periodo_analizado": None, "periodos": _periodos(cat),
                "meta": _meta(fuentes, [g], bench, moneda=moneda, desde=None, hasta=None, ultima_fecha_datos=None,
                              advertencias=[f"{g.nombre} no tiene datos: {motivo}."])}

    hasta_datos = (b_usd or a_usd)[-1][0]
    resumen = _resumen_grupo(fuentes, g, b_usd, moneda, hoy, ventana, hasta_datos)
    d_rango, h_rango, etiqueta_rango = _rango(cat, horizonte, desde, hasta, periodo_id, hasta_datos, a_usd[0][0])

    series_m = {g.id: resumen["a_m"]}
    nombres = [{"id": g.id, "nombre": g.nombre, "rol": "grupo"}]
    if bench:
        series_m[bench.id] = resumen["b_m"]
        nombres.append({"id": bench.id, "nombre": bench.nombre, "rol": "benchmark"})
    for x in extras:
        series_m[x.id] = fuentes.en_moneda(fuentes.nativa(x), moneda)
        nombres.append({"id": x.id, "nombre": x.nombre, "rol": "adicional"})
    paso = "S" if (h_rango - d_rango).days > DIAS_PASO_SEMANAL else "D"
    normal = eng.base_100(series_m, d_rango, h_rango, paso)
    filas = normal["filas"]
    if bench and filas:
        for f in filas:
            f["relativo"] = 100.0 * f[g.id] / f[bench.id]         # los dos arrancan en 100: el cociente arranca en 100

    rot = resumen["rotacion"]
    rango = {
        "etiqueta": etiqueta_rango, "desde_pedido": d_rango, "hasta_pedido": h_rango,
        "desde_efectivo": normal["fecha_base"], "hasta_efectivo": filas[-1]["fecha"] if filas else None,
        "recortado": bool(normal["fecha_base"] and normal["fecha_base"] > d_rango + timedelta(days=7)), "paso": paso,
    }
    analizado = eng.comparar(series_m, d_rango, h_rango) if filas else None
    if analizado and bench:
        rb = analizado["grupos"].get(bench.id, {}).get("retorno")
        for k, v in analizado["grupos"].items():
            v["relativo"] = (1 + v["retorno"]) / (1 + rb) - 1 if v.get("retorno") is not None and rb is not None and k != bench.id else None
    advertencias = []
    if rango["recortado"]:
        advertencias.append(f"El rango pedido empieza antes de que haya datos de todas las series: se muestra desde {normal['fecha_base'].isoformat()}.")
    if not bench:
        advertencias.append("Sin benchmark: no hay rotación ni rendimiento relativo.")
    elif not b_usd:
        advertencias.append(f"El benchmark {bench.nombre} no tiene datos: {fuentes.motivo_sin_datos(bench)}.")
    if rot["estado"] == eng.ESTADO_DESACTUALIZADO:
        advertencias.append(rot["motivo"].capitalize() + ": no se muestra como estado actual.")
    return {
        "grupo": info, "estado": rot["estado"], "motivo": rot["motivo"],
        "benchmark": ({**_info_grupo(bench), "ultima_fecha": b_usd[-1][0] if b_usd else None} if bench else None),
        "rotacion": {
            **_rrg_resumen(rot, eng.SEMANAS_POR_PERIODO["1A"]), "version": rot["version"],
            "puntos": rot["puntos"][-SEMANAS_HISTORIAL_DETALLE:], "transiciones": rot["transiciones"],
        },
        "rendimientos": resumen["rendimientos"], "riesgo": resumen["riesgo"], "tendencia": resumen["tendencia"],
        "series": nombres, "filas": filas, "rango": rango, "periodo_analizado": analizado, "periodos": _periodos(cat),
        "meta": _meta(fuentes, [g] + extras, bench, moneda=moneda, desde=d_rango, hasta=h_rango,
                      ultima_fecha_datos=a_usd[-1][0], advertencias=advertencias),
    }


def _periodos(cat: cc.Catalogo) -> list[dict]:
    return [{"id": p["id"], "nombre": p["nombre"], "desde": p["desde"], "hasta": p["hasta"], "nota": p["nota"]} for p in cat.periodos]


# ---------------------------------------------------------------------------------------------
# Relaciones
# ---------------------------------------------------------------------------------------------

def _series_usd(fuentes: Fuentes, ids: list[str]) -> tuple[dict[str, eng.Serie], list[dict], list[cc.Grupo]]:
    cat = fuentes.cat
    grupos = [_grupo(cat, i) for i in dict.fromkeys(ids)]
    series, sin_datos = {}, []
    for g in grupos:
        s = fuentes.nativa(g)
        if s:
            series[g.id] = s
        else:
            sin_datos.append({"id": g.id, "nombre": g.nombre, "motivo": fuentes.motivo_sin_datos(g)})
    return series, sin_datos, grupos


def correlaciones(
    db: Session, *, ids: tuple | None = None, periodo: str = "1A", frecuencia: str | None = None, hoy: date | None = None,
) -> dict:
    """Matriz de correlación (Pearson) entre retornos de los grupos elegidos, sobre fechas comunes y en dólares."""
    if periodo not in MESES_PERIODO:
        raise ValueError(f"período inválido {periodo!r} (3M, 6M, 1A o 3A)")
    frecuencia = frecuencia or ("diaria" if periodo == "3M" else "semanal")
    if frecuencia not in ("diaria", "semanal"):
        raise ValueError("frecuencia inválida (diaria o semanal)")
    cat = cc.cargar()
    ids_efectivos = list(ids) if ids else [i for i in GRUPOS_CORRELACION_DEFECTO if i in cat.grupos and cat.grupos[i].activo]
    if not 2 <= len(ids_efectivos) <= MAX_CORRELACION:
        raise ValueError(f"hay que elegir entre 2 y {MAX_CORRELACION} grupos")
    fuentes = Fuentes(db, cat)
    series, sin_datos, grupos = _series_usd(fuentes, ids_efectivos)
    if len(series) < 2:
        return {"estado": eng.ESTADO_INSUFICIENTE, "motivo": "menos de dos grupos con datos", "sin_datos": sin_datos, "nombres": {},
                "matriz": None, "pares": [], "meta": _meta(fuentes, grupos, None, moneda="USD", desde=None, hasta=None, ultima_fecha_datos=None, nota_moneda=False)}
    hasta = max(s[-1][0] for s in series.values())
    desde = eng.restar_meses(hasta, MESES_PERIODO[periodo])
    grilla = None
    if frecuencia == "diaria":
        ref = fuentes.nativa(cat.grupos["estados-unidos"]) if "estados-unidos" in cat.grupos else []
        if not ref:
            raise ValueError("la correlación diaria necesita la serie de referencia (S&P 500) para fijar las ruedas")
        grilla = [f for f, _ in ref]
    res = eng.matriz_correlacion(series, desde, hasta, frecuencia, grilla)
    advertencias = ["Correlación no implica causalidad: indica que dos series se movieron juntas en este período, no por qué.",
                    "Se calcula con retornos en dólares de fechas comunes; con pocas observaciones el coeficiente es poco confiable."]
    if res["pocos_datos"]:
        advertencias.append("Más de la mitad de los pares no alcanzó el mínimo de observaciones: se muestran sin valor.")
    if sin_datos:
        advertencias.append(f"{len(sin_datos)} grupo(s) sin datos quedaron afuera de la matriz.")
    return {
        "estado": eng.ESTADO_OK, "motivo": None, "periodo": periodo, "frecuencia": frecuencia,
        "nombres": {g.id: g.nombre for g in grupos}, "ids": res["ids"], "matriz": res["matriz"], "pares": res["pares"],
        "n_periodos": res["n_periodos"], "periodo_efectivo": res["periodo"], "correlacion_promedio": res["correlacion_promedio"],
        "sin_datos": sin_datos,
        "escala": [{"desde": 0.7, "texto": "se movieron muy parecido"}, {"desde": 0.3, "texto": "se movieron algo parecido"},
                   {"desde": -0.3, "texto": "sin relación lineal clara"}, {"desde": -0.7, "texto": "tendieron a moverse en sentido opuesto"},
                   {"desde": -1.0, "texto": "se movieron casi en espejo"}],
        "meta": _meta(fuentes, grupos, None, moneda="USD", desde=desde, hasta=hasta, ultima_fecha_datos=hasta,
                      advertencias=advertencias, nota_moneda=False),
    }


def desfases(db: Session, *, a: str, b: str, meses: int = 36, hoy: date | None = None) -> dict:
    """Correlación entre el retorno semanal de `a` y el de `b` desplazado k semanas. Hipótesis estadísticas, no predicciones."""
    if not 12 <= meses <= 120:
        raise ValueError("`meses` debe estar entre 12 y 120")
    cat = cc.cargar()
    fuentes = Fuentes(db, cat)
    series, sin_datos, grupos = _series_usd(fuentes, [a, b])
    par = next((p for p in cat.pares_desfase if p["grupos"] == [a, b]), None)
    if len(series) < 2 or a == b:
        return {"estado": eng.ESTADO_INSUFICIENTE, "motivo": "hacen falta dos grupos distintos con datos", "sin_datos": sin_datos,
                "desfases": [], "mejor": None, "nombres": {g.id: g.nombre for g in grupos}, "nota_par": par and par["nota"],
                "meta": _meta(fuentes, grupos, None, moneda="USD", desde=None, hasta=None, ultima_fecha_datos=None, nota_moneda=False)}
    hasta = max(series[a][-1][0], series[b][-1][0])
    desde = eng.restar_meses(hasta, meses)
    res = eng.desfases(series[a], series[b], desde, hasta)
    return {
        "estado": eng.ESTADO_OK if res["mejor"] else eng.ESTADO_INSUFICIENTE,
        "motivo": None if res["mejor"] else "pocas observaciones para calcular desfases", "a": a, "b": b,
        "nombres": {g.id: g.nombre for g in grupos}, "desfases": res["desfases"], "mejor": res["mejor"], "banda_azar": res["banda_azar"],
        "max_semanas": res["max_semanas"], "nota_par": par and par["nota"], "sin_datos": sin_datos,
        "lectura": "k > 0: el retorno de «a» de una semana se parece al de «b» k semanas después. Es una hipótesis estadística, no una predicción.",
        "meta": _meta(fuentes, grupos, None, moneda="USD", desde=desde, hasta=hasta, ultima_fecha_datos=hasta, nota_moneda=False, advertencias=[
            "Se probaron 17 desfases: es esperable que alguno supere la banda de azar sin que haya relación real.",
            "Correlación con desfase no implica causalidad ni permite anticipar movimientos.",
        ]),
    }


def comparacion(
    db: Session, *, ids: tuple, benchmark: str | None = None, moneda: str = "USD", desde: date | None = None,
    hasta: date | None = None, periodo_id: str | None = None, hoy: date | None = None,
) -> dict:
    """Rendimiento, volatilidad, drawdown y recuperación de varios grupos sobre el mismo período exacto."""
    moneda = _validar_moneda(moneda)
    hoy = hoy or date.today()
    if not 2 <= len(ids) <= MAX_COMPARACION:
        raise ValueError(f"hay que elegir entre 2 y {MAX_COMPARACION} grupos")
    cat = cc.cargar()
    fuentes = Fuentes(db, cat)
    grupos = [_grupo(cat, i) for i in dict.fromkeys(ids)]
    bench = _resolver_benchmark(cat, benchmark, grupos) if benchmark else None
    nativas = {g.id: fuentes.nativa(g) for g in grupos}
    con_datos = {k: v for k, v in nativas.items() if v}
    sin_datos = [{"id": g.id, "nombre": g.nombre, "motivo": fuentes.motivo_sin_datos(g)} for g in grupos if not nativas[g.id]]
    if not con_datos:
        return {"estado": eng.ESTADO_SIN_DATOS, "motivo": "ninguno de los grupos tiene datos", "sin_datos": sin_datos, "grupos": [], "filas": [],
                "meta": _meta(fuentes, grupos, bench, moneda=moneda, desde=None, hasta=None, ultima_fecha_datos=None)}
    ultima = max(s[-1][0] for s in con_datos.values())
    primera = min(s[0][0] for s in con_datos.values())
    d, h, etiqueta = _rango(cat, "3A", desde, hasta, periodo_id, ultima, primera)
    series_m = {k: fuentes.en_moneda(v, moneda) for k, v in con_datos.items()}
    b_m = fuentes.en_moneda(fuentes.nativa(bench), moneda) if bench else []
    todas = dict(series_m)
    if bench and b_m:
        todas[bench.id] = b_m
    comp = eng.comparar(todas, d, h)
    rb = (comp["grupos"].get(bench.id) or {}).get("retorno") if bench else None
    filas_cmp = []
    for g in grupos:
        v = comp["grupos"].get(g.id) or {"retorno": None, "motivo": "sin datos", "volatilidad": None, "drawdown": None, "semanas": 0}
        r = v.get("retorno")
        rot = eng.rotacion(nativas[g.id], fuentes.nativa(bench), hoy=hoy) if bench and nativas[g.id] and bench.id != g.id else None
        filas_cmp.append({
            **_info_grupo(g), "retorno": r, "motivo": v.get("motivo"),
            "relativo": (1 + r) / (1 + rb) - 1 if r is not None and rb is not None and g.id != (bench.id if bench else None) else None,
            "volatilidad": v.get("volatilidad"), "drawdown": v.get("drawdown"), "semanas": v.get("semanas"),
            "rotacion_actual": ({"estado": rot["estado"], "cuadrante": rot["actual"]["cuadrante"] if rot["actual"] else None} if rot else None),
        })
    paso = "S" if (h - d).days > DIAS_PASO_SEMANAL else "D"
    normal = eng.base_100(series_m, comp["desde"], h, paso)
    advertencias = []
    if comp["periodo_ajustado"]:
        advertencias.append(f"El período se acortó a {comp['desde'].isoformat()}, cuando empieza el grupo con menos historia, para comparar la misma ventana.")
    if sin_datos:
        advertencias.append(f"{len(sin_datos)} grupo(s) sin datos no entran en la comparación.")
    return {
        "estado": eng.ESTADO_OK, "motivo": None, "etiqueta_periodo": etiqueta,
        "periodo": {"desde_pedido": d, "hasta_pedido": h, "desde": comp["desde"], "hasta": h, "ajustado": comp["periodo_ajustado"]},
        "grupos": filas_cmp, "series": [{"id": g.id, "nombre": g.nombre} for g in grupos if g.id in series_m],
        "filas": normal["filas"], "fecha_base": normal["fecha_base"], "paso": paso, "sin_datos": sin_datos, "periodos": _periodos(cat),
        "meta": _meta(fuentes, grupos, bench, moneda=moneda, desde=comp["desde"], hasta=h, ultima_fecha_datos=ultima, advertencias=advertencias),
    }


# ---------------------------------------------------------------------------------------------
# Países
# ---------------------------------------------------------------------------------------------

def _fx_serie(fuentes: Fuentes, g: cc.Grupo) -> eng.Serie | None:
    if not g.fx:
        return None
    return fuentes.serie_mep() if g.fx["cotizacion"] == "mep" else fuentes.simbolo(g.fx["simbolo"])


def _moneda_local_en_usd(fx: eng.Serie, cotizacion: str, desde: date, hasta: date) -> list[dict]:
    """Valor de la moneda local en dólares, base 100: sube cuando la moneda local se aprecia."""
    pts = [(f, 1 / v if cotizacion in ("local_por_usd", "mep") else v) for f, v in eng.semanal(eng.normalizar(fx)) if desde <= f <= hasta]
    return [{"fecha": f, "valor": 100.0 * v / pts[0][1]} for f, v in pts] if pts else []


MACRO_AR_DIAS = 365


def _macro(db: Session, g: cc.Grupo) -> dict:
    if g.id != "argentina":
        return {"estado": "no_disponible", "motivo": "La app no tiene datos macroeconómicos de este país."}
    from .inversiones_analytics import get_indices_mercado
    res = get_indices_mercado(MACRO_AR_DIAS, db)
    ultimo = {c: next((p for p in reversed(res["puntos"]) if p[c] is not None), None) for c in ("mep", "cer", "riesgo_pais")}
    if not any(ultimo.values()):
        return {"estado": "no_disponible", "motivo": "Todavía no hay MEP, CER ni riesgo país cargados."}
    return {
        "estado": "parcial", "motivo": "Sólo CER, MEP, riesgo país e inflación de INDEC: no describen el ciclo económico completo.",
        "ultimo": {c: ({"fecha": p["fecha"], "valor": p[c]} if p else None) for c, p in ultimo.items()},
        "variacion_12m_pct": {"mep": res["variacion_mep_pct"], "cer": res["variacion_cer_pct"], "riesgo_pais": res["variacion_riesgo_pais_pct"]},
        "inflacion_mensual": res["inflacion_mensual"][-6:],
    }


def pais(db: Session, grupo_id: str, *, meses: int = 12, benchmark: str | None = None, moneda: str = "USD", hoy: date | None = None) -> dict:
    """Ficha de un país o región: ETF en USD, índice local y tipo de cambio por separado, rotación y contexto."""
    moneda = _validar_moneda(moneda)
    if meses not in (3, 6, 12, 36):
        raise ValueError("`meses` debe ser 3, 6, 12 o 36")
    hoy = hoy or date.today()
    cat = cc.cargar()
    g = _grupo(cat, grupo_id)
    if not ({"pais", "region"} & set(g.vistas)):
        raise NoEncontrado(f"{g.nombre} no es un país ni una región")
    bench = _benchmark_efectivo(cat, g, benchmark)
    fuentes = Fuentes(db, cat)
    a_usd = fuentes.nativa(g)
    b_usd = fuentes.nativa(bench) if bench else []
    if not a_usd:
        motivo = fuentes.motivo_sin_datos(g)
        return {"grupo": _info_grupo(g), "estado": eng.ESTADO_SIN_DATOS, "motivo": motivo, "resumen": None, "descomposicion": None,
                "meta": _meta(fuentes, [g], bench, moneda=moneda, desde=None, hasta=None, ultima_fecha_datos=None, advertencias=[f"{g.nombre} no tiene datos: {motivo}."])}
    hasta = a_usd[-1][0]
    resumen = _resumen_grupo(fuentes, g, b_usd, moneda, hoy, eng.VENTANA_RRG, hasta)
    idx = fuentes.simbolo(g.indice_local["simbolo"]) if g.indice_local else None
    fx = _fx_serie(fuentes, g)
    cot = g.fx["cotizacion"] if g.fx else None
    desde = eng.restar_meses(hasta, meses)
    por_horizonte = {
        f"{m}M" if m < 12 else f"{m // 12}A": eng.descomponer_pais(a_usd, idx, fx, cot, eng.restar_meses(hasta, m), hasta)
        for m in (3, 6, 12, 36)
    }
    comercio = None
    if "commodities-amplios" in cat.grupos and g.id != "commodities-amplios":
        com = fuentes.nativa(cat.grupos["commodities-amplios"])
        if com:
            h = max(hasta, com[-1][0])
            mc = eng.matriz_correlacion({g.id: a_usd, "commodities-amplios": com}, eng.restar_meses(h, 36), h, "semanal")
            p = mc["pares"][0] if mc["pares"] else None
            comercio = {"valor": p["valor"] if p else None, "n_obs": p["n_obs"] if p else 0, "estado": p["estado"] if p else eng.ESTADO_INSUFICIENTE,
                        "lectura": "Correlación semanal de 3 años con commodities amplios (DBC). Es una relación observada, no una medida de exposición."}
    advertencias = ["El ETF en USD mezcla el mercado local, el tipo de cambio, las distribuciones y los gastos del vehículo: no equivale al índice local ni al efecto cambiario."]
    if g.indice_local and (not idx):
        advertencias.append(f"El índice local {g.indice_local['simbolo']} no tiene datos.")
    elif idx and (hasta - idx[-1][0]).days > eng.DIAS_DESACTUALIZADO:
        advertencias.append(f"El índice local {g.indice_local['simbolo']} está desactualizado (último dato {idx[-1][0].isoformat()}).")
    if g.fx and cot == "mep" and not fuentes.serie_mep():
        advertencias.append("No hay MEP cargado: no se puede separar el efecto cambiario.")
    return {
        "grupo": {**_info_grupo(g), "indice_local": g.indice_local, "fx": g.fx}, "estado": resumen["rotacion"]["estado"], "motivo": resumen["rotacion"]["motivo"],
        "benchmark": _info_grupo(bench) if bench else None,
        "resumen": {"rotacion": _rrg_resumen(resumen["rotacion"], eng.SEMANAS_POR_PERIODO["1A"]), "rendimientos": resumen["rendimientos"],
                    "riesgo": resumen["riesgo"], "tendencia": resumen["tendencia"]},
        "descomposicion": por_horizonte, "meses": meses,
        "moneda_local_vs_usd": _moneda_local_en_usd(fx, cot, desde, hasta) if fx and cot else [],
        "macro": _macro(db, g), "relacion_commodities": comercio,
        "comparaciones": [c for c in cat.comparaciones if g.id in c["grupos"]],
        "meta": _meta(fuentes, [g], bench, moneda=moneda, desde=desde, hasta=hasta, ultima_fecha_datos=hasta, advertencias=advertencias),
    }


# ---------------------------------------------------------------------------------------------
# Catálogo y cobertura
# ---------------------------------------------------------------------------------------------

def estados_de_rotacion(db: Session, benchmark: str | None = None, hoy: date | None = None) -> dict[str, dict]:
    """`{grupo_id: {estado, cuadrante, confirmado, ultima_fecha, benchmark}}` de todos los grupos activos, contra
    `benchmark` o contra el habitual de cada uno. Lo usa la vista de cartera."""
    hoy = hoy or date.today()
    cat = cc.cargar()
    fuentes = Fuentes(db, cat)
    out: dict[str, dict] = {}
    for g in cat.activos():
        # Un grupo que es el propio benchmark pedido se mide contra su alternativa, no contra sí mismo.
        b = _benchmark_efectivo(cat, g, benchmark if benchmark != g.id else None)
        if b is None:
            continue
        a, bb = fuentes.nativa(g), fuentes.nativa(b)
        if not a:
            out[g.id] = {"estado": eng.ESTADO_SIN_DATOS, "cuadrante": None, "confirmado": None, "ultima_fecha": None, "benchmark": b.id,
                         "motivo": fuentes.motivo_sin_datos(g)}
            continue
        rot = eng.rotacion(a, bb, hoy=hoy)
        tr = rot["transiciones"]
        out[g.id] = {"estado": rot["estado"], "cuadrante": rot["actual"]["cuadrante"] if rot["actual"] else None,
                     "confirmado": tr["cuadrante_confirmado"] if tr else None, "ultima_fecha": rot["ultima_fecha"], "benchmark": b.id,
                     "motivo": rot["motivo"]}
    return out
