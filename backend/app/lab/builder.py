"""Builder Python del laboratorio de estrategias: escribís la lógica con operadores de Python y
sale el **DSL JSON canónico** que ya valida `services.estrategia_engine.validar_estrategia` y
persiste la app. No es un motor nuevo: la validación es *la misma función*, cero drift.

    from app.lab import Estrategia, ind, precio, entre, todas, alguna, negar

    canal = ind.EXTREMOS(ventana=0)                 # 0 = histórico acumulado
    est = (Estrategia("Mínimo histórico")
           .comprar(canal.dist_min_pct <= 1.0)
           .vender(canal.dist_max_pct >= -1.0)
           .riesgo(stop_loss_pct=20)
           .ejecucion(comision_pct=0.6, precio_ejecucion="apertura_siguiente", demora_barras=1))
    dsl = est.definicion()

Reglas del builder:

- Operadores: ``<`` ``<=`` ``>`` ``>=`` → comparadores; ``&`` ``|`` ``~`` → ``y`` / ``o`` / ``no``.
  Los números crudos se levantan a ``{"const": n}``.
- Lo que no tiene operador Python va como método o función: ``entre(x, a, b)``,
  ``.cruza_arriba(y)``, ``.cruza_abajo(y)``, ``.subiendo(barras=1)``, ``.bajando(...)``, y las
  formas explícitas ``todas(...)`` / ``alguna(...)`` / ``negar(...)``.
- **``bool(condicion)`` levanta ``TypeError``**: sin eso, ``a and b`` devolvería ``b`` en silencio
  y exportarías una estrategia que no es la que escribiste. También atrapa ``if cond:`` y las
  comparaciones encadenadas ``1 < x < 2`` (Python las convierte en ``and``).
- **Aplanado**: ``a & b & c`` → un solo nodo ``y`` con tres hijos; ``~~a`` → ``a``. El validador
  comparte el contador de nodos entre entrada y salida (20 máx.), así que encadenar sin aplanar
  se queda sin presupuesto enseguida.
- **Ids determinísticos** derivados del slug de ``indicadores_engine.clave()``: ``SMA(50)`` →
  ``sma_50``, ``EXTREMOS(0)`` → ``extremos_0``, ``OBV`` → ``obv``. El mismo builder da el mismo
  JSON; no hay colisiones por construcción; dos ``ind.SMA(50)`` sueltos colapsan en un indicador.
- ``definicion()`` / ``a_dict()`` / ``a_json()`` / ``backtest()`` / ``exportar()`` corren
  ``validar_estrategia`` y levantan ``EstrategiaInvalida`` (subclase de ``ValueError``). Nada sale
  del laboratorio sin ser válido.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ..services.estrategia_engine import validar_estrategia
from ..services.indicadores_engine import INDICADORES, clave

__all__ = [
    "Estrategia", "EstrategiaInvalida", "Condicion",
    "ind", "precio", "entre", "todas", "alguna", "negar",
]


class EstrategiaInvalida(ValueError):
    """Errores de `validar_estrategia`, ya en castellano. `errores` guarda la lista cruda."""

    def __init__(self, errores: list[str]):
        self.errores = list(errores)
        super().__init__("; ".join(self.errores) or "estrategia inválida")


# ─── Operandos ───────────────────────────────────────────────────────────────

def _slug(clave_str: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clave_str.lower()).strip("_")


def _a_operando(valor) -> "_ExpresionOperando":
    if isinstance(valor, _ExpresionOperando):
        return valor
    if isinstance(valor, bool):
        raise TypeError("un booleano no es un operando del DSL; usá un número, precio.<campo> o ind.<TIPO>(...)")
    if isinstance(valor, (int, float)):
        return _OperandoConst(valor)
    raise TypeError(
        f"no sé usar {valor!r} como operando: pasá un número, precio.<campo> o una salida de indicador"
    )


class _ExpresionOperando:
    """Cualquier cosa comparable en el DSL: un `{campo}`, un `{const}` o una salida de indicador."""

    def _operando_dict(self) -> dict:  # pragma: no cover - abstracto
        raise NotImplementedError

    def _indicadores(self) -> list["Indicador"]:
        return []

    def _cmp(self, otro, op: str) -> "Condicion":
        o = _a_operando(otro)
        return Condicion(
            {"op": op, "izq": self._operando_dict(), "der": o._operando_dict()},
            [*self._indicadores(), *o._indicadores()],
        )

    def __lt__(self, otro): return self._cmp(otro, "menor")
    def __le__(self, otro): return self._cmp(otro, "menor_igual")
    def __gt__(self, otro): return self._cmp(otro, "mayor")
    def __ge__(self, otro): return self._cmp(otro, "mayor_igual")

    def cruza_arriba(self, otro) -> "Condicion": return self._cmp(otro, "cruce_arriba")
    def cruza_abajo(self, otro) -> "Condicion": return self._cmp(otro, "cruce_abajo")

    def subiendo(self, barras: int = 1) -> "Condicion":
        return Condicion(
            {"op": "subiendo", "operando": self._operando_dict(), "barras": int(barras)},
            list(self._indicadores()),
        )

    def bajando(self, barras: int = 1) -> "Condicion":
        return Condicion(
            {"op": "bajando", "operando": self._operando_dict(), "barras": int(barras)},
            list(self._indicadores()),
        )


class _OperandoConst(_ExpresionOperando):
    def __init__(self, valor):
        self.valor = valor

    def _operando_dict(self) -> dict:
        return {"const": self.valor}


class _OperandoCampo(_ExpresionOperando):
    def __init__(self, campo: str):
        self.campo = campo

    def _operando_dict(self) -> dict:
        return {"campo": self.campo}


class _SalidaIndicador(_ExpresionOperando):
    def __init__(self, indicador: "Indicador", salida: str):
        self.indicador = indicador
        self.salida = salida

    def _operando_dict(self) -> dict:
        return {"ref": self.indicador.id, "salida": self.salida}

    def _indicadores(self) -> list["Indicador"]:
        return [self.indicador]


class Indicador(_ExpresionOperando):
    """`ind.SMA(periodo=50)`. Para los mono-salida es operando por sí mismo; para los multi-salida
    se elige la salida por atributo (`ind.MACD().macd`), validado contra `espec.salidas`."""

    def __init__(self, tipo: str, params: dict, posicionales: tuple = ()):
        espec = INDICADORES[tipo]
        nombres = list(espec.params_default)
        if len(posicionales) > len(nombres):
            raise TypeError(
                f"{tipo} acepta {len(nombres)} parámetro(s) posicional(es) ({', '.join(nombres) or '(ninguno)'}), "
                f"se pasaron {len(posicionales)}"
            )
        por_posicion = dict(zip(nombres, posicionales))
        chocan = set(por_posicion) & set(params)
        if chocan:
            raise TypeError(f"{tipo}: parámetro(s) {sorted(chocan)} pasado(s) por posición y por nombre a la vez")
        params = {**por_posicion, **params}
        desconocidos = set(params) - set(espec.params_default)
        if desconocidos:
            raise TypeError(
                f"{tipo}: parámetro(s) desconocido(s) {sorted(desconocidos)}; "
                f"válidos: {list(espec.params_default) or '(ninguno)'}"
            )
        resueltos = {**espec.params_default, **params}
        for nombre_p, valor_p in resueltos.items():
            if not isinstance(valor_p, (int, float)) or isinstance(valor_p, bool):
                raise TypeError(f"{tipo}.{nombre_p} debe ser numérico (recibió {valor_p!r})")
            rango = espec.rangos.get(nombre_p)
            if rango is not None and not (rango[0] <= valor_p <= rango[1]):
                raise ValueError(f"{tipo}.{nombre_p} debe estar entre {rango[0]} y {rango[1]} (recibió {valor_p})")
        # `object.__setattr__` no hace falta (no es frozen), pero fijamos el orden posicional.
        self.tipo = tipo
        self.params = {k: resueltos[k] for k in espec.params_default}
        self.salidas = tuple(espec.salidas)
        self.clave = clave(tipo, self.params)
        self.id = _slug(self.clave)

    def _operando_dict(self) -> dict:
        if len(self.salidas) == 1:
            return {"ref": self.id}
        raise AttributeError(
            f"{self.tipo} tiene varias salidas ({', '.join(self.salidas)}); elegí una, "
            f"p.ej. ind.{self.tipo}(...).{self.salidas[0]}"
        )

    def _indicadores(self) -> list["Indicador"]:
        return [self]

    def __getattr__(self, nombre: str):
        # Sólo se llama si el atributo no existe por la vía normal.
        salidas = self.__dict__.get("salidas", ())
        if nombre in salidas:
            return _SalidaIndicador(self, nombre)
        raise AttributeError(
            f"{self.__dict__.get('tipo', '?')} no tiene la salida {nombre!r}. "
            f"Salidas válidas: {', '.join(salidas) or '(ninguna)'}"
        )

    def __repr__(self) -> str:
        return f"<Indicador {self.id}={self.clave}>"


# ─── Condiciones ─────────────────────────────────────────────────────────────

class Condicion:
    """Nodo del árbol de condiciones. Se combina con `&` `|` `~`; nunca con `and`/`or`/`not`."""

    def __init__(self, dsl: dict, indicadores: list[Indicador] | None = None):
        self.dsl = dsl
        registro: dict[str, Indicador] = {}
        for it in indicadores or []:
            registro.setdefault(it.id, it)
        self._indicadores = registro

    @property
    def indicadores(self) -> list[Indicador]:
        return list(self._indicadores.values())

    def _combinar(self, op: str, otro) -> "Condicion":
        otro = _exigir_condicion(otro, "combinación con & / |")
        hijos: list[dict] = []
        for c in (self, otro):
            if c.dsl.get("op") == op and isinstance(c.dsl.get("condiciones"), list):
                hijos.extend(c.dsl["condiciones"])
            else:
                hijos.append(c.dsl)
        return Condicion({"op": op, "condiciones": hijos}, [*self.indicadores, *otro.indicadores])

    def __and__(self, otro) -> "Condicion":
        return self._combinar("y", otro)

    def __or__(self, otro) -> "Condicion":
        return self._combinar("o", otro)

    def __invert__(self) -> "Condicion":
        if self.dsl.get("op") == "no":  # ~~a → a
            return Condicion(self.dsl["condicion"], self.indicadores)
        return Condicion({"op": "no", "condicion": self.dsl}, self.indicadores)

    def __bool__(self):
        raise TypeError(
            "una condición del builder no se puede evaluar como booleano de Python. "
            "Usá los operadores '&' (y), '|' (o), '~' (no) — no 'and', 'or', 'not', ni 'if cond:', "
            "ni comparaciones encadenadas como '1 < x < 2'."
        )

    def __repr__(self) -> str:
        return f"<Condicion {json.dumps(self.dsl, ensure_ascii=False)}>"


def _exigir_condicion(x, contexto: str) -> Condicion:
    if isinstance(x, Condicion):
        return x
    if isinstance(x, _ExpresionOperando):
        raise TypeError(
            f"{contexto}: {x!r} es un operando, no una condición. Compará algo: "
            "p.ej. `ind.SMA(50) > precio.cierre`."
        )
    raise TypeError(f"{contexto}: se esperaba una condición del builder, no {x!r}")


def entre(valor, minimo, maximo) -> Condicion:
    ops = [_a_operando(valor), _a_operando(minimo), _a_operando(maximo)]
    inds = [i for o in ops for i in o._indicadores()]
    return Condicion(
        {"op": "entre", "valor": ops[0]._operando_dict(),
         "minimo": ops[1]._operando_dict(), "maximo": ops[2]._operando_dict()},
        inds,
    )


def todas(*condiciones) -> Condicion:
    if not condiciones:
        raise TypeError("todas() necesita al menos una condición")
    acc = _exigir_condicion(condiciones[0], "todas()")
    for c in condiciones[1:]:
        acc = acc & c
    return acc


def alguna(*condiciones) -> Condicion:
    if not condiciones:
        raise TypeError("alguna() necesita al menos una condición")
    acc = _exigir_condicion(condiciones[0], "alguna()")
    for c in condiciones[1:]:
        acc = acc | c
    return acc


def negar(condicion) -> Condicion:
    return ~_exigir_condicion(condicion, "negar()")


# ─── Fábricas: `ind` y `precio` ──────────────────────────────────────────────

class _FabricaIndicadores:
    """`ind.SMA(periodo=50)` — se genera dinámicamente desde `indicadores_engine.INDICADORES`,
    así cada indicador nuevo del motor aparece solo. `__dir__` alimenta el autocompletado."""

    def __getattr__(self, tipo: str):
        if tipo in INDICADORES:
            def constructor(*posicionales, **params):
                return Indicador(tipo, params, posicionales)
            constructor.__name__ = tipo
            constructor.__doc__ = (
                f"{tipo}({', '.join(f'{k}={v!r}' for k, v in INDICADORES[tipo].params_default.items())}) "
                f"-> salidas: {', '.join(INDICADORES[tipo].salidas)}"
            )
            return constructor
        raise AttributeError(
            f"indicador desconocido: {tipo!r}. Disponibles: {', '.join(sorted(INDICADORES))}"
        )

    def __dir__(self):
        return sorted(INDICADORES)


class _Precio:
    _CAMPOS = ("cierre", "apertura", "maximo", "minimo", "volumen")

    def __getattr__(self, nombre: str):
        if nombre in _Precio._CAMPOS:
            return _OperandoCampo(nombre)
        raise AttributeError(f"precio no tiene el campo {nombre!r}; válidos: {', '.join(_Precio._CAMPOS)}")

    def __dir__(self):
        return list(_Precio._CAMPOS)


ind = _FabricaIndicadores()
precio = _Precio()


# ─── Estrategia ──────────────────────────────────────────────────────────────

_RIESGO_VACIO = {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None}
_EJECUCION_DEFAULT = {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0}

FORMATO_ARCHIVO = "inversiones-app/estrategia"
FORMATO_VERSION = 1


class Estrategia:
    def __init__(self, nombre: str, descripcion: str | None = None):
        self.nombre = nombre
        self.descripcion = descripcion
        self.ticker: str | None = None
        self.variante: str = "local"
        self._entrada: Condicion | None = None
        self._salida: Condicion | None = None
        self._riesgo = dict(_RIESGO_VACIO)
        self._ejecucion = dict(_EJECUCION_DEFAULT)

    # -- construcción encadenable -------------------------------------------------
    def comprar(self, condicion) -> "Estrategia":
        self._entrada = _exigir_condicion(condicion, ".comprar()")
        return self

    def vender(self, condicion) -> "Estrategia":
        self._salida = _exigir_condicion(condicion, ".vender()")
        return self

    def riesgo(self, **kwargs) -> "Estrategia":
        self._riesgo.update(kwargs)
        return self

    def ejecucion(self, **kwargs) -> "Estrategia":
        self._ejecucion.update(kwargs)
        return self

    def para(self, ticker: str | None = None, variante: str | None = None) -> "Estrategia":
        """Sólo metadatos del sobre exportado; la lógica es reusable en cualquier activo."""
        if ticker is not None:
            self.ticker = ticker
        if variante is not None:
            self.variante = variante
        return self

    # -- salida -----------------------------------------------------------------
    def _dsl_sin_validar(self) -> dict:
        if self._entrada is None:
            raise EstrategiaInvalida(["falta la condición de compra: usá .comprar(...)"])
        registro: dict[str, Indicador] = {}
        for cond in (self._entrada, self._salida):
            if cond is not None:
                for it in cond.indicadores:
                    registro.setdefault(it.id, it)
        indicadores = [
            {"id": it.id, "tipo": it.tipo, "params": dict(it.params)}
            for it in sorted(registro.values(), key=lambda i: i.id)
        ]
        return {
            "version": 1,
            "indicadores": indicadores,
            "entrada": self._entrada.dsl,
            "salida": self._salida.dsl if self._salida is not None else None,
            "riesgo": dict(self._riesgo),
            "ejecucion": dict(self._ejecucion),
        }

    def definicion(self) -> dict:
        dsl = self._dsl_sin_validar()
        errores = validar_estrategia(dsl)
        if errores:
            raise EstrategiaInvalida(errores)
        return dsl

    a_dict = definicion

    def a_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.definicion(), ensure_ascii=False, indent=indent)

    def sobre(self) -> dict:
        """El sobre versionado que consume el importador de la app (fase 4)."""
        return {
            "formato": FORMATO_ARCHIVO,
            "formato_version": FORMATO_VERSION,
            "exportado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "ticker": self.ticker,
            "variante": self.variante,
            "definicion": self.definicion(),
        }

    def exportar(self, ruta) -> Path:
        ruta = Path(ruta)
        ruta.write_text(json.dumps(self.sobre(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return ruta

    # -- evaluación (delegada a `evaluacion.py` para no importar pandas en el módulo) ----
    def dataframe(self, barras):
        from .evaluacion import a_dataframe
        return a_dataframe(barras, self.definicion())

    def backtest(self, barras):
        from .evaluacion import ResultadoLab
        from ..services import estrategia_engine
        dsl = self.definicion()
        return ResultadoLab(estrategia_engine.backtest(dsl, barras), dsl)

    def __repr__(self) -> str:
        return f"<Estrategia {self.nombre!r}>"
