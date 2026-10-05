"""Motor de alertas de precio: decide **cuándo avisar**, no cuánto vale nada.

Los niveles (stop-loss y precio objetivo de las posiciones, precio de compra de la watchlist) y
si están cruzados ya los calcula `inversiones_analytics._nivel_precio`; acá no se recalcula nada.
Lo único que resuelve este módulo es el problema que hace que una alerta sirva o moleste: **no
repetir el mismo aviso en cada corrida**.

El problema concreto: si la regla fuera "el precio está por debajo del stop-loss → avisar", un
precio que queda oscilando alrededor del nivel genera un aviso por corrida, para siempre. A los
dos días el usuario silencia el bot y la función deja de existir. Por eso cada nivel tiene estado:

- `armada`    — el precio está del lado "normal" del nivel; el próximo cruce avisa.
- `disparada` — ya se avisó de este cruce; no se vuelve a avisar.

Una alerta `disparada` **se re-arma** sólo cuando el precio vuelve al otro lado del nivel y se
aleja más que `BANDA_REARMADO_PCT`. Esa banda es la histéresis: sin ella, cruzar el nivel de ida
y de vuelta por centavos volvería a armar y a disparar, que es exactamente el spam que se quiere
evitar.

Módulo puro, sin `Session`, al estilo del resto de los `*_engine`.
"""
from __future__ import annotations

from dataclasses import dataclass

# Tipos de alerta.
TIPO_STOP_LOSS = "stop_loss"
TIPO_OBJETIVO = "objetivo"
TIPO_COMPRA_ZONA = "compra_zona"

TIPOS = (TIPO_STOP_LOSS, TIPO_OBJETIVO, TIPO_COMPRA_ZONA)

# Hacia dónde tiene que moverse el precio para disparar. El objetivo de una posición es un precio
# de **venta** (se cruza hacia arriba); el stop-loss y el objetivo de la watchlist son precios de
# **compra**/salida (se cruzan hacia abajo). Misma asimetría que documenta `database.WatchlistItem`.
_DISPARA_HACIA_ABAJO = frozenset({TIPO_STOP_LOSS, TIPO_COMPRA_ZONA})

ESTADO_ARMADA = "armada"
ESTADO_DISPARADA = "disparada"

# Cuánto tiene que alejarse el precio del nivel, del lado normal, para que una alerta ya disparada
# vuelva a quedar armada. 2% es suficiente para que el ruido intradiario no re-arme nada y chico
# como para que un movimiento real sí lo haga.
BANDA_REARMADO_PCT = 2.0

ETIQUETA_TIPO = {
    TIPO_STOP_LOSS: "Stop-loss disparado",
    TIPO_OBJETIVO: "Objetivo alcanzado",
    TIPO_COMPRA_ZONA: "Zona de compra",
}

# `cartera` vacía = la alerta no pertenece a ninguna cartera (watchlist). Se usa "" y no `None`
# porque el UNIQUE de la tabla incluye la columna, y en SQLite dos NULL no colisionan: con `None`
# se podrían acumular filas duplicadas del mismo nivel.
SIN_CARTERA = ""


@dataclass(frozen=True)
class Candidata:
    """Un nivel de precio vigente, con su precio actual y si hoy está cruzado.

    `cruzado` lo decide quien arma la candidata (reusando los flags que ya calcula el backend:
    `stop_loss_disparado`, `objetivo_alcanzado`, `en_zona`), no este módulo: el nivel puede estar
    definido como porcentaje sobre el precio de compra o como precio absoluto, y esa resolución
    ya vive en `_nivel_precio`.
    """
    ticker: str
    nombre: str
    tipo: str
    cartera: str
    nivel: float
    precio: float
    moneda: str
    cruzado: bool

    @property
    def clave(self) -> tuple[str, str, str]:
        return (self.ticker, self.tipo, self.cartera)


@dataclass(frozen=True)
class Alerta:
    """Un cruce que hay que avisar."""
    ticker: str
    nombre: str
    tipo: str
    cartera: str
    nivel: float
    precio: float
    moneda: str

    @property
    def clave(self) -> tuple[str, str, str]:
        return (self.ticker, self.tipo, self.cartera)


@dataclass(frozen=True)
class Decision:
    """Qué cambió en esta corrida.

    - `a_emitir`: cruces nuevos; hay que notificarlos y dejarlos `disparada`.
    - `a_rearmar`: claves que estaban `disparada` y el precio se alejó lo suficiente; vuelven a
      `armada` **sin** notificar (volver al lado normal no es noticia).
    - `a_crear`: claves vistas por primera vez que no están cruzadas; se guardan `armada` para
      que el próximo cruce sí avise.
    """
    a_emitir: list[Alerta]
    a_rearmar: list[tuple[str, str, str]]
    a_crear: list[tuple[str, str, str]]


def _lejos_del_nivel(candidata: Candidata, banda_pct: float) -> bool:
    """`True` si el precio está del lado normal del nivel y además a más de `banda_pct` de él."""
    if candidata.nivel == 0:
        return False
    margen = abs(candidata.nivel) * (banda_pct / 100.0)
    if candidata.tipo in _DISPARA_HACIA_ABAJO:
        # Dispara cuando el precio baja: se re-arma cuando sube por encima del nivel + banda.
        return candidata.precio > candidata.nivel + margen
    return candidata.precio < candidata.nivel - margen


def evaluar(
    candidatas: list[Candidata],
    estados: dict[tuple[str, str, str], str],
    banda_pct: float = BANDA_REARMADO_PCT,
) -> Decision:
    """Decide qué avisar, comparando los niveles cruzados contra el estado guardado.

    `estados` mapea `(ticker, tipo, cartera)` al estado persistido. Una clave ausente es un nivel
    que se ve por primera vez: si ya está cruzado **se avisa** (es un cruce que el usuario no
    conocía), y si no, se guarda `armada`.
    """
    a_emitir: list[Alerta] = []
    a_rearmar: list[tuple[str, str, str]] = []
    a_crear: list[tuple[str, str, str]] = []

    for candidata in candidatas:
        previo = estados.get(candidata.clave)

        if candidata.cruzado:
            if previo == ESTADO_DISPARADA:
                continue  # ya se avisó de este cruce
            a_emitir.append(Alerta(
                ticker=candidata.ticker, nombre=candidata.nombre, tipo=candidata.tipo,
                cartera=candidata.cartera, nivel=candidata.nivel, precio=candidata.precio,
                moneda=candidata.moneda,
            ))
            continue

        if previo == ESTADO_DISPARADA:
            if _lejos_del_nivel(candidata, banda_pct):
                a_rearmar.append(candidata.clave)
            continue

        if previo is None:
            a_crear.append(candidata.clave)

    return Decision(a_emitir=a_emitir, a_rearmar=a_rearmar, a_crear=a_crear)


# ─── Armado de candidatas desde lo que ya calcula el backend ──────────────────

def candidatas_de_posiciones(rendimiento_por_ticker: list[dict], cartera: str) -> list[Candidata]:
    """Niveles de stop-loss y objetivo de las posiciones de una cartera.

    Entra tal cual lo devuelve `inversiones_analytics.get_rendimiento_por_ticker`.
    """
    salida: list[Candidata] = []
    for item in rendimiento_por_ticker:
        precio = item.get("precio_actual")
        if precio is None:
            continue
        for tipo, campo_nivel, campo_cruzado in (
            (TIPO_STOP_LOSS, "precio_stop_loss", "stop_loss_disparado"),
            (TIPO_OBJETIVO, "precio_objetivo", "objetivo_alcanzado"),
        ):
            nivel = item.get(campo_nivel)
            cruzado = item.get(campo_cruzado)
            # `None` en el flag significa "no hay nivel definido" o "precio actual cero": no es
            # una alerta armada, es la ausencia de alerta.
            if nivel is None or cruzado is None:
                continue
            salida.append(Candidata(
                ticker=item.get("ticker", ""), nombre=item.get("nombre") or item.get("ticker", ""),
                tipo=tipo, cartera=cartera, nivel=float(nivel), precio=float(precio),
                moneda=item.get("moneda") or "", cruzado=bool(cruzado),
            ))
    return salida


def candidatas_de_watchlist(watchlist: list[dict]) -> list[Candidata]:
    """Niveles de precio de compra de la watchlist.

    Entra tal cual lo devuelve `watchlist_analytics.get_watchlist`.
    """
    salida: list[Candidata] = []
    for item in watchlist:
        precio = item.get("precio_actual")
        nivel = item.get("precio_objetivo")
        en_zona = item.get("en_zona")
        if precio is None or nivel is None or en_zona is None:
            continue
        salida.append(Candidata(
            ticker=item.get("ticker", ""), nombre=item.get("nombre") or item.get("ticker", ""),
            tipo=TIPO_COMPRA_ZONA, cartera=SIN_CARTERA, nivel=float(nivel), precio=float(precio),
            moneda=item.get("moneda_precio") or item.get("moneda") or "", cruzado=bool(en_zona),
        ))
    return salida


# ─── Texto de la notificación ────────────────────────────────────────────────

def _fmt_precio(valor: float) -> str:
    """`1234.5` → `1.234,50`. Separadores de es-AR, que es cómo los muestra la app."""
    texto = f"{valor:,.2f}"
    return texto.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


def _linea(alerta: Alerta) -> str:
    comparador = "≤" if alerta.tipo in _DISPARA_HACIA_ABAJO else "≥"
    moneda = f"{alerta.moneda} " if alerta.moneda else ""
    etiqueta_cartera = f" · {alerta.cartera}" if alerta.cartera else ""
    return (
        f"• {alerta.ticker} ({alerta.nombre}){etiqueta_cartera}: "
        f"{moneda}{_fmt_precio(alerta.precio)} {comparador} {moneda}{_fmt_precio(alerta.nivel)}"
    )


def texto_notificacion(alertas: list[Alerta]) -> str:
    """Un solo mensaje con todos los cruces de la corrida, agrupados por tipo.

    Un mensaje por corrida y no uno por ticker: diez posiciones cruzando el mismo día son diez
    notificaciones que el usuario descarta sin leer.
    """
    if not alertas:
        return ""
    partes = ["🔔 Alertas de precio"]
    for tipo in TIPOS:
        del_tipo = [a for a in alertas if a.tipo == tipo]
        if not del_tipo:
            continue
        partes.append("")
        partes.append(ETIQUETA_TIPO[tipo])
        partes.extend(_linea(a) for a in sorted(del_tipo, key=lambda a: a.ticker))
    return "\n".join(partes)
