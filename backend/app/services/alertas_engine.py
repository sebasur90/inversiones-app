"""Motor de alertas: decide **cuándo avisar** y **cómo se lee el aviso**, no cuánto vale nada.

Dos familias de alerta, con antirrebote distinto porque la naturaleza del disparo es distinta:

**Niveles de precio** (stop-loss y objetivo de las posiciones, precio de compra de la watchlist).
Los niveles y si están cruzados ya los calcula `inversiones_analytics._nivel_precio`; acá no se
recalcula nada. Lo único que resuelve es el problema que hace que una alerta sirva o moleste: **no
repetir el mismo aviso en cada corrida**. Si la regla fuera "el precio está por debajo del
stop-loss → avisar", un precio oscilando alrededor del nivel genera un aviso por corrida, para
siempre; a los dos días el usuario silencia el bot. Por eso cada nivel tiene estado:

- `armada`    — el precio está del lado "normal" del nivel; el próximo cruce avisa.
- `disparada` — ya se avisó de este cruce; no se vuelve a avisar.

Una alerta `disparada` **se re-arma** sólo cuando el precio vuelve al otro lado del nivel y se
aleja más que `BANDA_REARMADO_PCT`. Esa banda es la histéresis: sin ella, cruzar el nivel de ida
y de vuelta por centavos volvería a armar y a disparar.

**Señales de estrategia técnica** (`estrategias_analytics.senales_recientes`). Acá no hay nivel
del cual alejarse, así que la histéresis no aplica: la clave de deduplicación es **la barra de la
señal**, que ya es única y monótona. Se avisa cuando `(fecha, tipo)` difiere de lo último avisado
para ese par (estrategia, ticker). Eso resuelve de una vez el rebote (la misma señal aparece
durante varias barras y sólo la primera avisa) y la secuencia compra → venta → compra (cada una
tiene barra distinta, así que cada una avisa una vez).

El texto del aviso vive también acá, en HTML de Telegram: el formato es parte de la decisión de
"cuándo avisar" —un aviso que no se entiende de un vistazo en el celular es un aviso que no
sirve—, y mantenerlo en el módulo puro lo deja testeable sin red ni DB.

Módulo puro, sin `Session`, al estilo del resto de los `*_engine`.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# ─── Tipos de alerta ─────────────────────────────────────────────────────────

TIPO_STOP_LOSS = "stop_loss"
TIPO_OBJETIVO = "objetivo"
TIPO_COMPRA_ZONA = "compra_zona"

#: Tipos de **nivel de precio**. Las señales de estrategia no están acá: su `tipo` se construye
#: con `tipo_senal()` y lleva el id de la estrategia adentro (ver más abajo).
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

#: Etiqueta corta de cada tipo de nivel. Para una alerta cualquiera (nivel o señal) usar
#: `etiqueta_de()`, que sabe además de los tipos compuestos.
ETIQUETA_TIPO = {
    TIPO_STOP_LOSS: "Stop-loss disparado",
    TIPO_OBJETIVO: "Objetivo alcanzado",
    TIPO_COMPRA_ZONA: "Zona de compra",
}

# `cartera` vacía = la alerta no pertenece a ninguna cartera (watchlist, o señal de estrategia).
# Se usa "" y no `None` porque el UNIQUE de la tabla incluye la columna, y en SQLite dos NULL no
# colisionan: con `None` se podrían acumular filas duplicadas del mismo nivel.
SIN_CARTERA = ""

ORIGEN_CARTERA = "cartera"
ORIGEN_WATCHLIST = "watchlist"

SENAL_COMPRA = "compra"
SENAL_VENTA = "venta"

# ─── Tipos compuestos de las señales de estrategia ───────────────────────────
#
# Una señal se identifica por (estrategia, ticker), así que el id de la estrategia tiene que
# entrar en la clave. Entra dentro de `tipo` en vez de en una columna nueva porque el UNIQUE de
# `alertas_precio` es `(ticker, tipo, cartera)` y SQLite no sabe alterar un UniqueConstraint sin
# reconstruir la tabla. `cartera` queda vacía a propósito: una señal es sobre la serie del ticker,
# no sobre una tenencia — si la cartera entrara en la clave, un ticker con tenencia en dos
# carteras avisaría dos veces y mover la tenencia re-dispararía la señal.

PREFIJO_SENAL = "estrategia:"


def tipo_senal(estrategia_id: int) -> str:
    return f"{PREFIJO_SENAL}{estrategia_id}"


def es_tipo_senal(tipo: str) -> bool:
    return (tipo or "").startswith(PREFIJO_SENAL)


def estrategia_de_tipo(tipo: str) -> int | None:
    """Id de la estrategia de un `tipo` compuesto, o `None` si no es una señal."""
    if not es_tipo_senal(tipo):
        return None
    try:
        return int(tipo[len(PREFIJO_SENAL):])
    except ValueError:
        return None


# ─── Datos del aviso ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Contexto:
    """Todo lo descriptivo del aviso: lo que lo hace entendible sin abrir la app.

    Va aparte de `Alerta` (que es la identidad del cruce) y se persiste completo en
    `AlertaPrecio.detalle`, porque el reintento de envío reconstruye el aviso **sólo** desde las
    columnas más ese JSON: un campo que no viaje acá se pierde y el reintento manda un texto
    distinto al original.

    Los porcentajes están en **puntos porcentuales** (`-4,5` = -4,5%), no en fracción, y ya con el
    signo que se muestra. `senal_fecha` es ISO: `detalle` es una columna JSON y `json.dumps` no
    serializa `date`.
    """
    origen: str = ""                        # ORIGEN_CARTERA | ORIGEN_WATCHLIST
    # Cartera a mostrar cuando no está en la clave de la alerta. Las señales de estrategia tienen
    # `cartera=""` (no son sobre una tenencia), pero el aviso igual tiene que decir de dónde sale.
    cartera_nombre: str | None = None
    distancia_pct: float | None = None      # precio vs. nivel
    cantidad: float | None = None
    precio_promedio: float | None = None
    resultado_pct: float | None = None
    carteras_extra: int = 0                 # el ticker también tiene tenencia en N carteras más
    nivel_modo: str | None = None           # "Porcentaje" | "Fijo"
    nivel_valor: float | None = None
    en_cartera: bool | None = None          # watchlist: ya hay tenencia de este ticker
    estrategia_id: int | None = None
    estrategia_nombre: str | None = None
    senal_tipo: str | None = None           # SENAL_COMPRA | SENAL_VENTA
    senal_fecha: str | None = None          # ISO "YYYY-MM-DD"
    senal_motivo: str | None = None
    variante: str | None = None             # "local" | "subyacente"
    barras_desde: int | None = None


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
    contexto: Contexto = Contexto()

    @property
    def clave(self) -> tuple[str, str, str]:
        return (self.ticker, self.tipo, self.cartera)


@dataclass(frozen=True)
class Alerta:
    """Un cruce (o una señal) que hay que avisar.

    `nivel` es `None` en las señales de estrategia: una señal no tiene nivel de precio, dispara
    porque se cumplió una condición sobre indicadores.
    """
    ticker: str
    nombre: str
    tipo: str
    cartera: str
    nivel: float | None
    precio: float
    moneda: str
    contexto: Contexto = Contexto()

    @property
    def clave(self) -> tuple[str, str, str]:
        return (self.ticker, self.tipo, self.cartera)


@dataclass(frozen=True)
class SenalCandidata:
    """Una señal fresca de estrategia técnica, tal como la devuelve `senales_recientes`."""
    ticker: str
    nombre: str
    estrategia_id: int
    estrategia_nombre: str
    tipo: str                 # SENAL_COMPRA | SENAL_VENTA
    fecha: str                # ISO
    precio: float
    moneda: str
    motivo: str = ""
    variante: str = "local"
    barras_desde: int = 0
    contexto: Contexto = Contexto()

    @property
    def clave(self) -> tuple[str, str, str]:
        return (self.ticker, tipo_senal(self.estrategia_id), SIN_CARTERA)


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


# ─── Round-trip del contexto por `AlertaPrecio.detalle` ──────────────────────

_VERSION_DETALLE = 1


def contexto_a_detalle(nombre: str, contexto: Contexto) -> dict:
    """`detalle` JSON de una fila de `alertas_precio`. Sólo tipos serializables."""
    datos = {"v": _VERSION_DETALLE, "nombre": nombre}
    for campo, valor in vars(contexto).items():
        if valor is None or valor == Contexto.__dataclass_fields__[campo].default:
            continue
        datos[campo] = valor
    return datos


def detalle_a_contexto(detalle: dict | None) -> Contexto:
    """Reconstruye el contexto desde `detalle`, tolerando lo que falte o sobre.

    Tolerante a propósito: las filas que ya están en la DB sólo tienen `{"nombre": ...}`, y el
    primer reintento después de un deploy tiene que renderizar algo razonable en vez de explotar.
    Las claves desconocidas (una versión futura del formato) se ignoran.
    """
    if not isinstance(detalle, dict):
        return Contexto()
    campos = Contexto.__dataclass_fields__
    return Contexto(**{k: v for k, v in detalle.items() if k in campos})


def nombre_de_detalle(detalle: dict | None, ticker: str) -> str:
    if isinstance(detalle, dict):
        return detalle.get("nombre") or ticker
    return ticker


# ─── Decisión: niveles ───────────────────────────────────────────────────────

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
                moneda=candidata.moneda, contexto=candidata.contexto,
            ))
            continue

        if previo == ESTADO_DISPARADA:
            if _lejos_del_nivel(candidata, banda_pct):
                a_rearmar.append(candidata.clave)
            continue

        if previo is None:
            a_crear.append(candidata.clave)

    return Decision(a_emitir=a_emitir, a_rearmar=a_rearmar, a_crear=a_crear)


# ─── Decisión: señales de estrategia ─────────────────────────────────────────

def evaluar_senales(
    senales: list[SenalCandidata],
    avisadas: dict[tuple[str, str, str], tuple[str | None, str | None]],
) -> list[Alerta]:
    """Señales que hay que avisar: las que no coinciden con la última avisada de su par.

    `avisadas` mapea `(ticker, tipo_senal, "")` a la `(fecha, tipo)` ya notificada. Una clave
    ausente es un par visto por primera vez y se avisa: a diferencia de un nivel, una señal fresca
    es noticia aunque sea la primera vez que se la ve (ya pasó, el usuario no la conocía).

    No hay `a_rearmar` ni `a_crear`: una señal que dejó de estar fresca simplemente no existe, no
    hay un estado intermedio que seguir.
    """
    salida: list[Alerta] = []
    for senal in senales:
        if avisadas.get(senal.clave) == (senal.fecha, senal.tipo):
            continue
        contexto = replace(
            senal.contexto,
            estrategia_id=senal.estrategia_id,
            estrategia_nombre=senal.estrategia_nombre,
            senal_tipo=senal.tipo,
            senal_fecha=senal.fecha,
            senal_motivo=senal.motivo or None,
            variante=senal.variante or None,
            barras_desde=senal.barras_desde,
        )
        salida.append(Alerta(
            ticker=senal.ticker, nombre=senal.nombre, tipo=tipo_senal(senal.estrategia_id),
            cartera=SIN_CARTERA, nivel=None, precio=senal.precio, moneda=senal.moneda,
            contexto=contexto,
        ))
    return salida


# ─── Armado de candidatas desde lo que ya calcula el backend ──────────────────

def distancia_pct(precio: float, nivel: float | None) -> float | None:
    """Cuánto está el precio por encima (+) o por debajo (-) del nivel, en puntos porcentuales.

    Se calcula sobre el nivel y no sobre el precio (que es lo que hace `pct_a_objetivo`) porque el
    aviso habla del nivel: "está 0,5% por debajo del stop" se entiende; "al stop le falta 0,5%
    hacia arriba" no.
    """
    if nivel is None or nivel == 0:
        return None
    return round((precio - nivel) / abs(nivel) * 100.0, 2)


def pct_desde_fraccion(valor) -> float | None:
    """Fracción (0,286) → puntos porcentuales (28,6). `None` pasa de largo."""
    return None if valor is None else round(float(valor) * 100.0, 2)


def candidatas_de_posiciones(rendimiento_por_ticker: list[dict], cartera: str) -> list[Candidata]:
    """Niveles de stop-loss y objetivo de las posiciones de una cartera.

    Entra tal cual lo devuelve `inversiones_analytics.get_rendimiento_por_ticker`; el contexto se
    arma con claves que esa fila **ya trae**, así que no hay ninguna consulta extra.
    """
    salida: list[Candidata] = []
    for item in rendimiento_por_ticker:
        precio = item.get("precio_actual")
        if precio is None:
            continue
        moneda = item.get("moneda") or ""
        resultado = (
            item.get("rendimiento_simple_ars") if moneda == "ARS"
            else item.get("rendimiento_simple_usd")
        )
        for tipo, campo_nivel, campo_cruzado, campo_modo, campo_valor in (
            (TIPO_STOP_LOSS, "precio_stop_loss", "stop_loss_disparado",
             "stop_loss_modo", "stop_loss_valor"),
            (TIPO_OBJETIVO, "precio_objetivo", "objetivo_alcanzado",
             "objetivo_modo", "objetivo_valor"),
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
                moneda=moneda, cruzado=bool(cruzado),
                contexto=Contexto(
                    origen=ORIGEN_CARTERA,
                    distancia_pct=distancia_pct(float(precio), float(nivel)),
                    cantidad=item.get("cantidad_actual"),
                    precio_promedio=item.get("precio_promedio"),
                    resultado_pct=pct_desde_fraccion(resultado),
                    nivel_modo=item.get(campo_modo),
                    nivel_valor=item.get(campo_valor),
                ),
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
            contexto=Contexto(
                origen=ORIGEN_WATCHLIST,
                distancia_pct=distancia_pct(float(precio), float(nivel)),
                en_cartera=item.get("en_cartera"),
            ),
        ))
    return salida


# ─── Texto de la notificación ────────────────────────────────────────────────
#
# El mensaje va en HTML de Telegram (`parse_mode=HTML`), que admite sólo un puñado de tags. Dos
# reglas que no se negocian: **todo dato se escapa** con `escapar_html` (hay instrumentos que se
# llaman "S&P 500" o "AT&T", y un `&` crudo hace que Telegram rechace el mensaje **entero** con
# 400), y **no se anidan tags** (funciona, pero es justo lo que se rompe con un escapado imperfecto).

#: Presupuesto de caracteres del mensaje. Telegram corta en 4096; se deja aire para que el recorte
#: lo haga este módulo, por bloques enteros, y no `telegram.enviar` a lo bruto.
PRESUPUESTO_CARACTERES = 3800

TITULO = "🔔 <b>Alertas de inversiones</b>"

ACCION_COMPRA = "COMPRA"
ACCION_VENTA = "VENTA"
ACCION_REVISAR = "REVISAR"

#: Claves de bloque de las señales. Las de nivel son directamente `TIPO_*`.
BLOQUE_SENAL_VENTA = "senal_venta"
BLOQUE_SENAL_COMPRA = "senal_compra"

#: Orden de los bloques en el mensaje: primero lo que pone capital en riesgo, después las salidas
#: por regla, después las tomas de ganancia, al final las entradas.
ORDEN_BLOQUES = (
    TIPO_STOP_LOSS,
    BLOQUE_SENAL_VENTA,
    TIPO_OBJETIVO,
    TIPO_COMPRA_ZONA,
    BLOQUE_SENAL_COMPRA,
)


@dataclass(frozen=True)
class _Bloque:
    icono: str
    titulo: str
    sufijo: str       # qué hacer con esto, en palabras; sin consejo de ejecución
    accion: str
    sustantivo: str   # para el resumen por conteo


BLOQUES = {
    TIPO_STOP_LOSS: _Bloque("🔴", "STOP-LOSS", "revisar salida", ACCION_REVISAR, "posiciones"),
    BLOQUE_SENAL_VENTA: _Bloque("🟠", "SEÑAL DE VENTA", "revisar salida", ACCION_VENTA, "señales"),
    TIPO_OBJETIVO: _Bloque(
        "🎯", "OBJETIVO ALCANZADO", "revisar toma de ganancia", ACCION_REVISAR, "posiciones"),
    TIPO_COMPRA_ZONA: _Bloque(
        "🟢", "OPORTUNIDAD DE COMPRA", "en zona", ACCION_COMPRA, "tickers"),
    BLOQUE_SENAL_COMPRA: _Bloque("🟢", "SEÑAL DE COMPRA", "", ACCION_COMPRA, "señales"),
}

#: Motivo de la señal en palabras. Mismo vocabulario que `motivosSalida.ts` en el front, para que
#: el glifo del gráfico, la tabla de operaciones y el aviso del celular digan lo mismo.
ETIQUETA_MOTIVO_SENAL = {
    "entrada": "entrada",
    "regla_salida": "regla de salida",
    "stop_loss": "stop loss de la estrategia",
    "take_profit": "take profit",
    "trailing_stop": "trailing stop",
    "max_barras": "plazo máximo",
}


def escapar_html(texto) -> str:
    """Escapa lo que HTML de Telegram interpreta. `&` primero, siempre."""
    return (
        str("" if texto is None else texto)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def bloque_de(alerta: Alerta) -> str:
    """Clave de bloque de una alerta: su tipo de nivel, o el bloque de señal según compra/venta."""
    if es_tipo_senal(alerta.tipo):
        return (
            BLOQUE_SENAL_VENTA if alerta.contexto.senal_tipo == SENAL_VENTA
            else BLOQUE_SENAL_COMPRA
        )
    return alerta.tipo


def _bloque_de_tipo(tipo: str, contexto: Contexto) -> _Bloque | None:
    if es_tipo_senal(tipo):
        clave = BLOQUE_SENAL_VENTA if contexto.senal_tipo == SENAL_VENTA else BLOQUE_SENAL_COMPRA
        return BLOQUES[clave]
    return BLOQUES.get(tipo)


def accion_de(tipo: str, contexto: Contexto = Contexto()) -> str:
    """`COMPRA` / `VENTA` / `REVISAR`: lo primero que el usuario necesita saber del aviso."""
    bloque = _bloque_de_tipo(tipo, contexto)
    return bloque.accion if bloque else ACCION_REVISAR


def etiqueta_de(tipo: str, contexto: Contexto = Contexto()) -> str:
    """Etiqueta legible de cualquier alerta, para la app.

    Hace falta porque el `tipo` de una señal es `"estrategia:7"`: mostrarlo crudo (que es lo que
    hacía `ETIQUETA_TIPO.get(tipo, tipo)`) deja un aviso ilegible en pantalla.
    """
    if es_tipo_senal(tipo):
        bloque = _bloque_de_tipo(tipo, contexto)
        base = "Señal de venta" if bloque and bloque.accion == ACCION_VENTA else "Señal de compra"
        return f"{base} · {contexto.estrategia_nombre}" if contexto.estrategia_nombre else base
    return ETIQUETA_TIPO.get(tipo, tipo)


def encabezado_texto(clave: str) -> str:
    """Encabezado del bloque sin HTML. Es lo que la app muestra en el historial de avisos."""
    bloque = BLOQUES.get(clave)
    if bloque is None:
        return clave
    return f"{bloque.icono} {bloque.titulo}" + (f" — {bloque.sufijo}" if bloque.sufijo else "")


def encabezado_html(clave: str) -> str:
    bloque = BLOQUES.get(clave)
    if bloque is None:
        return escapar_html(clave)
    cabeza = f"{bloque.icono} <b>{escapar_html(bloque.titulo)}</b>"
    return cabeza + (f" — {escapar_html(bloque.sufijo)}" if bloque.sufijo else "")


# ─── Formato de números, en es-AR ────────────────────────────────────────────

def _fmt_precio(valor: float) -> str:
    """`1234.5` → `1.234,50`. Separadores de es-AR, que es cómo los muestra la app."""
    texto = f"{valor:,.2f}"
    return texto.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


def _fmt_pct(valor: float | None) -> str:
    """Puntos porcentuales con signo explícito: `-0,5%`, `+28,6%`."""
    if valor is None:
        return ""
    texto = f"{abs(valor):,.1f}".replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return f"{'-' if valor < 0 else '+'}{texto}%"


def _fmt_cantidad(valor: float | None) -> str:
    """Cantidad sin decimales de relleno: `10`, `10,5`, `0,25`."""
    if valor is None:
        return ""
    texto = f"{valor:,.4f}".rstrip("0").rstrip(".")
    return texto.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


def _fmt_fecha_corta(iso: str | None) -> str:
    """`"2026-10-06"` → `"06/10"`. Entra lo que haya; si no parsea, se devuelve tal cual."""
    partes = (iso or "").split("-")
    return f"{partes[2][:2]}/{partes[1]}" if len(partes) == 3 else (iso or "")


def _monto(moneda: str, valor: float) -> str:
    prefijo = f"{escapar_html(moneda)} " if moneda else ""
    return f"<code>{prefijo}{_fmt_precio(valor)}</code>"


# ─── Render de cada aviso ────────────────────────────────────────────────────

NIVEL_COMPLETO = "completo"
NIVEL_COMPACTO = "compacto"


def _linea_identidad(alerta: Alerta) -> str:
    """Quién es y de dónde viene. Es la línea que hoy falta y hace al aviso ambiguo."""
    ctx = alerta.contexto
    partes = [f"<b>{escapar_html(alerta.ticker)}</b>"]
    if alerta.nombre and alerta.nombre != alerta.ticker:
        partes.append(f"({escapar_html(alerta.nombre)})")
    cabeza = " ".join(partes)

    cartera = alerta.cartera or ctx.cartera_nombre
    if cartera:
        origen = f"cartera {escapar_html(cartera)}"
        if ctx.carteras_extra:
            origen += f" (+{ctx.carteras_extra})"
    elif ctx.origen == ORIGEN_WATCHLIST or alerta.tipo == TIPO_COMPRA_ZONA:
        origen = "watchlist"
    else:
        origen = ""

    trozos = [cabeza] + ([origen] if origen else [])
    # En la watchlist, "ya tenés posición" es justo lo que desambigua si el aviso es una entrada
    # nueva o un refuerzo de algo que ya está en la cartera.
    if ctx.en_cartera:
        trozos.append("ya tenés posición")
    return " · ".join(trozos)


def _linea_nivel(alerta: Alerta) -> str:
    comparador = "≤" if alerta.tipo in _DISPARA_HACIA_ABAJO else "≥"
    sustantivo = "stop" if alerta.tipo == TIPO_STOP_LOSS else "objetivo"
    linea = (
        f"{_monto(alerta.moneda, alerta.precio)} {comparador} "
        f"{sustantivo} {_monto(alerta.moneda, alerta.nivel)}"
    )
    dist = _fmt_pct(alerta.contexto.distancia_pct)
    return f"{linea} ({dist})" if dist else linea


def _linea_senal(alerta: Alerta) -> str:
    ctx = alerta.contexto
    partes = [f"<b>{escapar_html(ctx.estrategia_nombre or 'Estrategia')}</b>"]
    motivo = ETIQUETA_MOTIVO_SENAL.get(ctx.senal_motivo or "", ctx.senal_motivo or "")
    if motivo:
        partes.append(escapar_html(motivo))
    return " · ".join(partes)


def _linea_precio_senal(alerta: Alerta) -> str:
    # "cierre del dd/mm" y no "precio": la serie OHLCV y `precios_instrumento` no coinciden por
    # diseño, y ver dos precios distintos del mismo ticker el mismo día hace desconfiar de todo.
    fecha = _fmt_fecha_corta(alerta.contexto.senal_fecha)
    cuando = f"cierre del {fecha}" if fecha else "cierre"
    linea = f"{cuando}: {_monto(alerta.moneda, alerta.precio)}"
    if (alerta.contexto.variante or "local") != "local":
        linea += " · serie del subyacente en USD"
    return linea


def _linea_tenencia(alerta: Alerta) -> str:
    """Cantidad, precio promedio de compra y resultado. Sólo en posiciones."""
    ctx = alerta.contexto
    partes = []
    if ctx.cantidad is not None:
        partes.append(f"{_fmt_cantidad(ctx.cantidad)} un.")
    if ctx.precio_promedio is not None:
        partes.append(f"PPC {_monto(alerta.moneda, ctx.precio_promedio)}")
    if ctx.resultado_pct is not None:
        partes.append(f"<b>{_fmt_pct(ctx.resultado_pct)}</b>")
    return " · ".join(partes)


def _lineas(alerta: Alerta, nivel_detalle: str) -> list[str]:
    """Las líneas de un aviso. `completo` = 3 o 4 líneas; `compacto` = exactamente una."""
    es_senal = es_tipo_senal(alerta.tipo)

    if nivel_detalle == NIVEL_COMPACTO:
        trozos = [f"<b>{escapar_html(alerta.ticker)}</b>"]
        cartera = alerta.cartera or alerta.contexto.cartera_nombre
        if cartera:
            trozos.append(escapar_html(cartera))
        elif alerta.contexto.origen == ORIGEN_WATCHLIST or alerta.tipo == TIPO_COMPRA_ZONA:
            trozos.append("watchlist")
        if es_senal:
            trozos.append(escapar_html(alerta.contexto.estrategia_nombre or "Estrategia"))
            trozos.append(_monto(alerta.moneda, alerta.precio))
        else:
            comparador = "≤" if alerta.tipo in _DISPARA_HACIA_ABAJO else "≥"
            trozos.append(
                f"{_monto(alerta.moneda, alerta.precio)} {comparador} "
                f"{_monto(alerta.moneda, alerta.nivel)}"
            )
        if alerta.contexto.resultado_pct is not None:
            trozos.append(f"<b>{_fmt_pct(alerta.contexto.resultado_pct)}</b>")
        return [" · ".join(trozos)]

    lineas = [_linea_identidad(alerta)]
    if es_senal:
        lineas.append(_linea_senal(alerta))
        lineas.append(_linea_precio_senal(alerta))
    elif alerta.nivel is not None:
        lineas.append(_linea_nivel(alerta))
    tenencia = _linea_tenencia(alerta)
    if tenencia:
        lineas.append(tenencia)
    return lineas


# ─── Armado del mensaje, con recorte por bloques ─────────────────────────────

def _agrupar(alertas: list[Alerta]) -> list[tuple[str, list[Alerta]]]:
    """Alertas por bloque, en `ORDEN_BLOQUES`; dentro, posiciones primero y lo más cerca del
    nivel arriba (es lo que sobrevive al recorte)."""
    por_bloque: dict[str, list[Alerta]] = {}
    for alerta in alertas:
        por_bloque.setdefault(bloque_de(alerta), []).append(alerta)

    def orden(alerta: Alerta):
        dist = alerta.contexto.distancia_pct
        es_posicion = bool(alerta.cartera or alerta.contexto.cartera_nombre)
        return (
            0 if es_posicion else 1,
            abs(dist) if dist is not None else 0.0,
            alerta.ticker,
        )

    return [
        (clave, sorted(por_bloque[clave], key=orden))
        for clave in ORDEN_BLOQUES if por_bloque.get(clave)
    ]


def _render(
    grupos: list[tuple[str, list[Alerta]]], nivel_detalle: str, tope: int | None = None,
) -> str:
    partes = [TITULO]
    for clave, grupo in grupos:
        partes.append("")
        partes.append(encabezado_html(clave))
        mostrados = grupo if tope is None else grupo[:tope]
        for indice, alerta in enumerate(mostrados):
            # En modo completo cada aviso ocupa varias líneas: sin la línea en blanco los avisos
            # de un mismo bloque se leen como uno solo.
            if nivel_detalle == NIVEL_COMPLETO and indice:
                partes.append("")
            partes.extend(_lineas(alerta, nivel_detalle))
        faltan = len(grupo) - len(mostrados)
        if faltan:
            partes.append(f"<i>… y {faltan} más de este tipo</i>")
    return "\n".join(partes)


def _render_resumen(grupos: list[tuple[str, list[Alerta]]]) -> str:
    """Último recurso: sólo los encabezados con el conteo. Nunca se pierde un grupo entero."""
    partes = [TITULO, ""]
    for clave, grupo in grupos:
        bloque = BLOQUES.get(clave)
        sustantivo = bloque.sustantivo if bloque else "avisos"
        cabeza = f"{bloque.icono} <b>{escapar_html(bloque.titulo)}</b>" if bloque else clave
        partes.append(f"{cabeza} — {len(grupo)} {sustantivo}")
    partes.append("")
    partes.append("<i>Abrí la app para el detalle.</i>")
    return "\n".join(partes)


def texto_notificacion(
    alertas: list[Alerta], presupuesto: int = PRESUPUESTO_CARACTERES,
) -> str:
    """Un solo mensaje con todos los avisos de la corrida, agrupados por bloque.

    Un mensaje por corrida y no uno por ticker: diez posiciones cruzando el mismo día son diez
    notificaciones que el usuario descarta sin leer.

    Si no entra en `presupuesto` se baja de escalón: detalle completo → compacto → compacto con
    tope por bloque → sólo conteos. **El recorte es siempre por avisos enteros**: cortar un
    mensaje con HTML a la mitad parte un tag y Telegram rechaza el mensaje completo, así que un
    recorte a lo bruto no pierde un pedazo, pierde todo. Y ningún bloque con avisos desaparece sin
    dejar su encabezado y su conteo.
    """
    if not alertas:
        return ""
    grupos = _agrupar(alertas)

    for nivel_detalle in (NIVEL_COMPLETO, NIVEL_COMPACTO):
        texto = _render(grupos, nivel_detalle)
        if len(texto) <= presupuesto:
            return texto

    for tope in range(10, 0, -1):
        texto = _render(grupos, NIVEL_COMPACTO, tope)
        if len(texto) <= presupuesto:
            return texto

    return _render_resumen(grupos)
