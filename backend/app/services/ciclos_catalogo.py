"""Catálogo de grupos de «Ciclos de mercado» (`catalogos/ciclos_grupos.json`) y sus períodos históricos.

Es la única fuente de qué se mide y contra qué: los algoritmos no conocen ningún símbolo. Agregar o
corregir un proxy es editar el JSON. Mismo esquema de ubicación que `clasificacion_seed`: override por
entorno y, si no, `catalogos/` montado en el contenedor o en la raíz del repo.

La validación **descarta sólo el grupo inválido** (y lo que depende de él) y lo registra en
`Catalogo.errores`; un archivo ausente o roto equivale a un catálogo vacío. Nunca lanza.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger("ciclos_catalogo")

TIPOS = ("sector", "industria", "commodity", "region", "pais", "activo", "tema")
TIPOS_RENDIMIENTO = ("total", "precio")
EJES_CARTERA = ("sector", "region", "pais")
CLAVES_CARTERA = ("sector", "industria", "pais", "region", "tickers")
COTIZACIONES_FX = ("local_por_usd", "usd_por_local", "mep")
METODOS_SINTETICO = ("equiponderado_semanal",)
FUENTE_DEFECTO = "Yahoo Finance"

ROL_PROXY = "proxy"
ROL_INDICE = "indice_local"
ROL_FX = "fx"
MONEDA_FX = "FX"

_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Grupo:
    id: str
    nombre: str
    tipo: str
    vistas: tuple[str, ...]
    padre: str | None
    descripcion: str
    proxy: str | None
    benchmark: str | None
    moneda: str
    region: str | None
    fuente: str
    tipo_rendimiento: str
    activo: bool
    exclusivo: bool
    es_benchmark: bool
    lista_curada: bool
    nota: str | None
    eje_cartera: tuple[tuple[str, tuple[str, ...]], ...] = ()
    cartera: dict = field(default_factory=dict)
    indice_local: dict | None = None
    fx: dict | None = None
    sintetico: dict | None = None


@dataclass(frozen=True)
class Simbolo:
    """Un símbolo de Yahoo que la ingesta tiene que bajar y qué moneda se guarda con él."""
    simbolo: str
    moneda: str
    rol: str


@dataclass
class Catalogo:
    version: int = 0
    grupos: dict[str, Grupo] = field(default_factory=dict)
    periodos: list[dict] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    def activos(self) -> list[Grupo]:
        return [g for g in self.grupos.values() if g.activo]

    def benchmarks(self) -> list[Grupo]:
        return [g for g in self.activos() if g.es_benchmark]

    def hijos(self, id_: str) -> list[Grupo]:
        return [g for g in self.grupos.values() if g.padre == id_]

    def simbolos(self) -> dict[str, Simbolo]:
        """Todo lo que hay que bajar para los grupos activos: proxies, índices locales y tipos de cambio."""
        out: dict[str, Simbolo] = {}
        for g in self.activos():
            if g.proxy:
                out.setdefault(g.proxy, Simbolo(g.proxy, g.moneda, ROL_PROXY))
            if g.indice_local and g.indice_local.get("simbolo"):
                s = g.indice_local["simbolo"]
                out.setdefault(s, Simbolo(s, g.indice_local.get("moneda") or g.moneda, ROL_INDICE))
            if g.fx and g.fx.get("simbolo"):
                s = g.fx["simbolo"]
                out.setdefault(s, Simbolo(s, MONEDA_FX, ROL_FX))
        return out


# ---------------------------------------------------------------------------------------------
# Ubicación y lectura
# ---------------------------------------------------------------------------------------------

def _ruta(nombre: str, env: str) -> str:
    override = os.getenv(env)
    if override:
        return override
    base = os.path.dirname(__file__)
    candidatos = (
        os.path.join(base, "..", "..", "catalogos", nombre),
        os.path.join(base, "..", "..", "..", "catalogos", nombre),
    )
    for ruta in candidatos:
        if os.path.exists(ruta):
            return ruta
    return candidatos[-1]


def _leer(ruta: str, errores: list[str]) -> dict:
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except FileNotFoundError:
        errores.append(f"no existe {os.path.basename(ruta)}")
        return {}
    except (OSError, ValueError) as exc:
        errores.append(f"{os.path.basename(ruta)} ilegible: {exc}")
        return {}
    if not isinstance(datos, dict):
        errores.append(f"{os.path.basename(ruta)}: se esperaba un objeto")
        return {}
    return datos


# ---------------------------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------------------------

def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _lista_texto(v) -> tuple[str, ...]:
    if not isinstance(v, (list, tuple)):
        return ()
    return tuple(s for s in (_texto(x) for x in v) if s)


def _armar(crudo: dict, defecto_por_tipo: dict) -> Grupo:
    """Un `Grupo` a partir de su JSON; lanza `ValueError` con el motivo si no es válido."""
    if not isinstance(crudo, dict):
        raise ValueError("no es un objeto")
    id_ = _texto(crudo.get("id")) or ""
    if not _ID_RE.match(id_):
        raise ValueError(f"id inválido {id_!r} (minúsculas, números y guiones)")
    nombre = _texto(crudo.get("nombre"))
    if not nombre:
        raise ValueError("falta el nombre")
    tipo = _texto(crudo.get("tipo"))
    if tipo not in TIPOS:
        raise ValueError(f"tipo inválido {tipo!r}")

    d = {**(defecto_por_tipo.get(tipo) or {}), **{k: v for k, v in crudo.items() if k not in ("id",)}}

    proxy = _texto(d.get("proxy"))
    sintetico = d.get("sintetico")
    if (proxy is None) == (sintetico is None):
        raise ValueError("debe tener `proxy` o `sintetico`, uno solo")
    if sintetico is not None:
        if not isinstance(sintetico, dict) or sintetico.get("metodo") not in METODOS_SINTETICO:
            raise ValueError(f"sintético: método inválido (permitidos {METODOS_SINTETICO})")
        miembros = _lista_texto(sintetico.get("miembros"))
        if len(miembros) < 2:
            raise ValueError("sintético: hacen falta al menos 2 miembros")
        sintetico = {"metodo": sintetico["metodo"], "miembros": list(miembros)}

    tipo_rend = _texto(d.get("tipo_rendimiento")) or "total"
    if tipo_rend not in TIPOS_RENDIMIENTO:
        raise ValueError(f"tipo_rendimiento inválido {tipo_rend!r}")

    vistas = _lista_texto(d.get("vistas")) or (tipo,)
    for v in vistas:
        if v not in TIPOS:
            raise ValueError(f"vista inválida {v!r}")

    eje_cartera: list[tuple[str, tuple[str, ...]]] = []
    for e in d.get("eje_cartera") or []:
        eje, valores = (_texto(e.get("eje")), _lista_texto(e.get("valores"))) if isinstance(e, dict) else (None, ())
        if eje not in EJES_CARTERA or not valores:
            raise ValueError(f"eje_cartera inválido: {e!r}")
        eje_cartera.append((eje, valores))

    cartera = {}
    for k, v in (d.get("cartera") or {}).items():
        if k not in CLAVES_CARTERA:
            raise ValueError(f"cartera: clave desconocida {k!r}")
        cartera[k] = _lista_texto(v)

    indice_local = d.get("indice_local")
    if indice_local is not None:
        if not isinstance(indice_local, dict) or not _texto(indice_local.get("simbolo")):
            raise ValueError("indice_local: falta `simbolo`")
        indice_local = {"simbolo": _texto(indice_local["simbolo"]), "moneda": _texto(indice_local.get("moneda")) or "USD"}

    fx = d.get("fx")
    if fx is not None:
        cot = _texto(fx.get("cotizacion")) if isinstance(fx, dict) else None
        if cot not in COTIZACIONES_FX:
            raise ValueError(f"fx: cotizacion inválida {cot!r}")
        simbolo_fx = _texto(fx.get("simbolo"))
        if cot != "mep" and not simbolo_fx:
            raise ValueError("fx: falta `simbolo`")
        fx = {"simbolo": simbolo_fx, "cotizacion": cot}

    es_benchmark = bool(d.get("es_benchmark", False))
    return Grupo(
        id=id_, nombre=nombre, tipo=tipo, vistas=vistas, padre=_texto(d.get("padre")),
        descripcion=_texto(d.get("descripcion")) or "", proxy=proxy,
        benchmark=_texto(d.get("benchmark")), moneda=(_texto(d.get("moneda")) or "USD").upper(),
        region=_texto(d.get("region")), fuente=_texto(d.get("fuente")) or FUENTE_DEFECTO,
        tipo_rendimiento=tipo_rend, activo=bool(d.get("activo", True)),
        exclusivo=bool(d.get("exclusivo", False)), es_benchmark=es_benchmark,
        lista_curada=bool(d.get("lista_curada", False)), nota=_texto(d.get("nota")),
        eje_cartera=tuple(eje_cartera), cartera=cartera, indice_local=indice_local, fx=fx,
        sintetico=sintetico,
    )


def _validar_relaciones(grupos: dict[str, Grupo], errores: list[str]) -> dict[str, Grupo]:
    """Descarta, hasta que no quede ninguno, los grupos con referencias rotas o categorías repetidas."""
    grupos = dict(grupos)
    while True:
        malos: dict[str, str] = {}
        reclamado: dict[tuple[str, str], str] = {}
        for g in grupos.values():
            if g.padre is not None and (g.padre == g.id or g.padre not in grupos):
                malos[g.id] = f"padre inexistente {g.padre!r}"
                continue
            if g.benchmark is None and not g.es_benchmark:
                malos[g.id] = "sin benchmark (y no es benchmark)"
                continue
            if g.benchmark is not None:
                b = grupos.get(g.benchmark)
                if b is None or not b.es_benchmark:
                    malos[g.id] = f"benchmark {g.benchmark!r} inexistente o sin `es_benchmark`"
                    continue
            if g.sintetico is not None:
                for m in g.sintetico["miembros"]:
                    miembro = grupos.get(m)
                    if miembro is None or miembro.sintetico is not None or m == g.id:
                        malos[g.id] = f"sintético: miembro {m!r} inexistente o también sintético"
                        break
                if g.id in malos:
                    continue
            if g.activo:
                for eje, valores in g.eje_cartera:
                    for v in valores:
                        previo = reclamado.get((eje, v))
                        if previo is not None:
                            malos[g.id] = f"{eje} {v!r} ya lo reclama {previo!r}"
                            break
                        reclamado[(eje, v)] = g.id
                    if g.id in malos:
                        break
        if padre_ciclico := _ciclos_de_padres(grupos):
            for id_ in padre_ciclico:
                malos.setdefault(id_, "ciclo en `padre`")
        if not malos:
            return grupos
        for id_, motivo in malos.items():
            errores.append(f"grupo {id_}: {motivo}; se descarta")
            grupos.pop(id_, None)


def _ciclos_de_padres(grupos: dict[str, Grupo]) -> set[str]:
    en_ciclo: set[str] = set()
    for g in grupos.values():
        visto, actual = set(), g
        while actual is not None and actual.padre in grupos:
            if actual.id in visto:
                en_ciclo.add(g.id)
                break
            visto.add(actual.id)
            actual = grupos.get(actual.padre)
    return en_ciclo


def construir(datos_grupos: dict, datos_periodos: dict | None = None) -> Catalogo:
    """Valida el contenido ya leído. Puro: lo usan `cargar()` y los tests."""
    cat = Catalogo(version=int(datos_grupos.get("version") or 0))
    defecto = datos_grupos.get("defecto_por_tipo") or {}
    vistos: set[str] = set()
    armados: dict[str, Grupo] = {}
    for crudo in datos_grupos.get("grupos") or []:
        id_ = crudo.get("id") if isinstance(crudo, dict) else None
        try:
            g = _armar(crudo, defecto)
        except ValueError as exc:
            cat.errores.append(f"grupo {id_!r}: {exc}; se descarta")
            continue
        if g.id in vistos:
            cat.errores.append(f"grupo {g.id}: id repetido; se descarta el segundo")
            continue
        vistos.add(g.id)
        armados[g.id] = g
    cat.grupos = _validar_relaciones(armados, cat.errores)
    cat.periodos = _periodos(datos_periodos or {}, cat.errores)
    return cat


def _periodos(datos: dict, errores: list[str]) -> list[dict]:
    out, vistos = [], set()
    for p in datos.get("periodos") or []:
        try:
            id_ = _texto(p.get("id"))
            desde = date.fromisoformat(p["desde"])
            hasta = date.fromisoformat(p["hasta"]) if p.get("hasta") else None
            if not id_ or id_ in vistos or not _texto(p.get("nombre")):
                raise ValueError("id repetido o sin nombre")
            if hasta is not None and hasta <= desde:
                raise ValueError("`hasta` debe ser posterior a `desde`")
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            errores.append(f"período {p.get('id') if isinstance(p, dict) else p!r}: {exc}; se descarta")
            continue
        vistos.add(id_)
        out.append({"id": id_, "nombre": _texto(p["nombre"]), "desde": desde, "hasta": hasta, "nota": _texto(p.get("nota"))})
    return out


_cache: dict[tuple, Catalogo] = {}


def cargar() -> Catalogo:
    """El catálogo vigente. Se vuelve a leer sólo si cambió alguno de los dos archivos."""
    errores: list[str] = []
    ruta_g = _ruta("ciclos_grupos.json", "CICLOS_CATALOGO_FILE")
    ruta_p = _ruta("ciclos_periodos.json", "CICLOS_PERIODOS_FILE")
    try:
        clave = (ruta_g, os.path.getmtime(ruta_g), ruta_p, os.path.getmtime(ruta_p) if os.path.exists(ruta_p) else 0)
    except OSError:
        clave = (ruta_g, 0.0, ruta_p, 0.0)
    if clave in _cache:
        return _cache[clave]
    cat = construir(_leer(ruta_g, errores), _leer(ruta_p, errores) if os.path.exists(ruta_p) else {})
    cat.errores = errores + cat.errores
    for e in cat.errores:
        logger.warning("catálogo de ciclos: %s", e)
    _cache.clear()
    _cache[clave] = cat
    return cat
