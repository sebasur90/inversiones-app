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

**Cambios de diagnóstico** (`alertas_diagnostico_engine`). Tampoco hay nivel: avisa cuando una dimensión
del diagnóstico de una empresa (valuación, calidad, solidez) cambia de estado y el cambio se confirma. La
decisión es de ese módulo; acá viven sólo el tipo (`diagnostico:<dimensión>`), el contexto y el texto.

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
#: Zona de compra (`services/zonas_precio.py`). Conserva el nombre que tenía cuando el nivel era el
#: `Objetivo` escalar de la watchlist: así las filas de `alertas_precio` ya emitidas siguen siendo
#: las mismas y el interruptor `avisar_compra_zona` no cambia de significado.
TIPO_COMPRA_ZONA = "compra_zona"
#: Zona de venta: el precio sube y entra en el rango en el que el usuario quiere salir.
TIPO_VENTA_ZONA = "venta_zona"

#: Tipos de **nivel de precio**. Las señales de estrategia no están acá: su `tipo` se construye
#: con `tipo_senal()` y lleva el id de la estrategia adentro (ver más abajo).
TIPOS = (TIPO_STOP_LOSS, TIPO_OBJETIVO, TIPO_COMPRA_ZONA, TIPO_VENTA_ZONA)

# Hacia dónde tiene que moverse el precio para disparar. El objetivo de una posición y la zona de
# venta son precios de **venta** (se cruzan hacia arriba); el stop-loss y la zona de compra se
# cruzan hacia **abajo**. Misma asimetría que documenta `database.WatchlistItem`.
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
    TIPO_VENTA_ZONA: "Zona de venta",
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


# ─── Tipos compuestos de los cambios de diagnóstico ──────────────────────────
#
# Igual que las señales: la dimensión entra dentro de `tipo` porque el UNIQUE de `alertas_precio` no se
# puede ampliar sin reconstruir la tabla, y `cartera` queda vacía (el diagnóstico es del emisor, no de una
# tenencia: con dos carteras avisaría dos veces).

PREFIJO_DIAGNOSTICO = "diagnostico:"


def tipo_diagnostico(dimension: str) -> str:
    return f"{PREFIJO_DIAGNOSTICO}{dimension}"


def es_tipo_diagnostico(tipo: str) -> bool:
    return (tipo or "").startswith(PREFIJO_DIAGNOSTICO)


def dimension_de_tipo(tipo: str) -> str | None:
    return tipo[len(PREFIJO_DIAGNOSTICO):] if es_tipo_diagnostico(tipo) else None


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
    # Zonas: los dos bordes y el mercado de la serie. Van al mensaje porque un aviso que dice
    # "entró en la zona 170-180 USD (subyacente, NMS)" se entiende solo, y uno que dice "≤ 180"
    # sobre un CEDEAR hace pensar en pesos.
    zona_piso: float | None = None
    zona_techo: float | None = None
    mercado: str | None = None
    # Cambio de diagnóstico: qué dimensión, de qué estado a cuál, la razón principal y la regla, el
    # snapshot del que sale y la versión de las reglas. Fechas en ISO (columna JSON).
    diag_dimension: str | None = None
    diag_nombre_dimension: str | None = None
    diag_de: str | None = None
    diag_a: str | None = None
    diag_razon: str | None = None
    diag_regla: str | None = None
    diag_fecha_dato: str | None = None
    diag_version: int | None = None


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
    """`True` si el precio está del lado normal del nivel y además a más de `banda_pct` de él.

    Vale igual para una zona, y el borde opuesto **no** interviene: para una zona de compra de
    1150-1250, el estado "cruzado" es `precio <= 1250` (un precio de 900 está *más* adentro de la
    oportunidad, no afuera — ver `zonas_precio.estado_de_zona`). Salir por abajo del piso no es
    dejar de estar en zona, así que lo único que puede re-armar el aviso es volver por arriba del
    techo, que es exactamente lo que mide la banda.
    """
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


#: Tipo de alerta de cada lado de una zona. Mismo mapeo que `zonas_precio.TIPO_ALERTA`, duplicado
#: acá para que este módulo siga siendo puro (no importa servicios con `Session`).
TIPO_ALERTA_ZONA = {"compra": TIPO_COMPRA_ZONA, "venta": TIPO_VENTA_ZONA}


def candidatas_de_zonas(zonas: list[dict]) -> list[Candidata]:
    """Zonas de compra y de venta, de cartera y de watchlist.

    Cada fila la arma `alertas_analytics` ya resuelta, porque qué precio corresponde depende de la
    serie sobre la que está medida la zona (`variante`): el precio local cotizado acá, o el del
    subyacente en USD. **Nunca se convierte de moneda**: una zona se compara contra el precio de su
    propia serie, y si ese precio no está, no hay candidata (es mejor no avisar que avisar con el
    número equivocado).

    Claves de cada fila: `ticker`, `nombre`, `tipo` (`"compra"`/`"venta"`), `nivel` (el borde que
    dispara), `precio`, `moneda`, `variante`, `mercado`, `cruzado`, y el contexto de origen
    (`origen`, `cartera_nombre`, `en_cartera`, `cantidad`, `precio_promedio`, `carteras_extra`,
    `zona_piso`, `zona_techo`). El borde que no dispara viaja sólo como `zona_piso`/`zona_techo`,
    para el texto del aviso: no participa de la decisión (ver `_lejos_del_nivel`).

    `cartera` siempre vacía: una zona es una decisión sobre el **instrumento**, no sobre una
    tenencia (igual que los niveles de la watchlist y que las señales). Si la cartera entrara en la
    clave, el mismo ticker en dos carteras avisaría dos veces de la misma zona.
    """
    salida: list[Candidata] = []
    for fila in zonas:
        tipo_zona = fila.get("tipo") or ""
        tipo = TIPO_ALERTA_ZONA.get(tipo_zona)
        precio = fila.get("precio")
        nivel = fila.get("nivel")
        if tipo is None or precio is None or nivel is None:
            continue
        precio, nivel = float(precio), float(nivel)
        salida.append(Candidata(
            ticker=fila.get("ticker", ""), nombre=fila.get("nombre") or fila.get("ticker", ""),
            tipo=tipo, cartera=SIN_CARTERA, nivel=nivel, precio=precio,
            moneda=fila.get("moneda") or "", cruzado=bool(fila.get("cruzado")),
            contexto=Contexto(
                origen=fila.get("origen") or ORIGEN_WATCHLIST,
                cartera_nombre=fila.get("cartera_nombre"),
                distancia_pct=distancia_pct(precio, nivel),
                en_cartera=fila.get("en_cartera"),
                cantidad=fila.get("cantidad"),
                precio_promedio=fila.get("precio_promedio"),
                resultado_pct=fila.get("resultado_pct"),
                carteras_extra=fila.get("carteras_extra") or 0,
                variante=fila.get("variante") or "local",
                mercado=fila.get("mercado"),
                zona_piso=fila.get("zona_piso"),
                zona_techo=fila.get("zona_techo"),
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
BLOQUE_DIAGNOSTICO = "diagnostico"

#: Orden de los bloques en el mensaje: primero lo que pone capital en riesgo, después las salidas
#: por regla, después las tomas de ganancia, al final las entradas.
ORDEN_BLOQUES = (
    TIPO_STOP_LOSS,
    BLOQUE_SENAL_VENTA,
    TIPO_OBJETIVO,
    TIPO_VENTA_ZONA,
    TIPO_COMPRA_ZONA,
    BLOQUE_SENAL_COMPRA,
    BLOQUE_DIAGNOSTICO,
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
    TIPO_VENTA_ZONA: _Bloque(
        "🔵", "ZONA DE VENTA", "revisar salida", ACCION_VENTA, "tickers"),
    TIPO_COMPRA_ZONA: _Bloque(
        "🟢", "OPORTUNIDAD DE COMPRA", "en zona", ACCION_COMPRA, "tickers"),
    BLOQUE_SENAL_COMPRA: _Bloque("🟢", "SEÑAL DE COMPRA", "", ACCION_COMPRA, "señales"),
    BLOQUE_DIAGNOSTICO: _Bloque("🔎", "CAMBIO DE DIAGNÓSTICO", "", ACCION_REVISAR, "cambios"),
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
    if es_tipo_diagnostico(alerta.tipo):
        return BLOQUE_DIAGNOSTICO
    if es_tipo_senal(alerta.tipo):
        return (
            BLOQUE_SENAL_VENTA if alerta.contexto.senal_tipo == SENAL_VENTA
            else BLOQUE_SENAL_COMPRA
        )
    return alerta.tipo


def _bloque_de_tipo(tipo: str, contexto: Contexto) -> _Bloque | None:
    if es_tipo_diagnostico(tipo):
        return BLOQUES[BLOQUE_DIAGNOSTICO]
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
    if es_tipo_diagnostico(tipo):
        nombre = contexto.diag_nombre_dimension or (dimension_de_tipo(tipo) or "").capitalize()
        return f"Cambio de diagnóstico · {nombre}" if nombre else "Cambio de diagnóstico"
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
    elif ctx.origen == ORIGEN_WATCHLIST:
        origen = "watchlist"
    else:
        origen = ""

    trozos = [cabeza] + ([origen] if origen else [])
    # En la watchlist, "ya tenés posición" es justo lo que desambigua si el aviso es una entrada
    # nueva o un refuerzo de algo que ya está en la cartera.
    if ctx.en_cartera:
        trozos.append("ya tenés posición")
    return " · ".join(trozos)


#: Tipos de nivel que son una zona (tienen rango y serie propia).
_TIPOS_ZONA = frozenset({TIPO_COMPRA_ZONA, TIPO_VENTA_ZONA})


def _sufijo_serie(alerta: Alerta) -> str:
    """Sobre qué serie se midió, cuando no es la local.

    Es imprescindible en una zona en dólares: sin esto, "entró en zona ≤ 180" sobre un CEDEAR que
    cotiza a 26.000 pesos se lee como un error de la app.
    """
    if (alerta.contexto.variante or "local") == "local":
        return ""
    mercado = escapar_html(alerta.contexto.mercado or "")
    return f" · subyacente{f' en {mercado}' if mercado else ''}"


def _linea_nivel(alerta: Alerta) -> str:
    comparador = "≤" if alerta.tipo in _DISPARA_HACIA_ABAJO else "≥"

    if alerta.tipo in _TIPOS_ZONA:
        ctx = alerta.contexto
        piso, techo = ctx.zona_piso, ctx.zona_techo
        # El comparador va una sola vez, antes del sustantivo, como en "≤ stop 96,00": el borde
        # que disparó ya queda implícito ahí.
        if piso is not None and techo is not None:
            zona = f"zona {_monto(alerta.moneda, piso)}–{_monto(alerta.moneda, techo)}"
        else:
            zona = f"zona {_monto(alerta.moneda, alerta.nivel)}"
        linea = f"{_monto(alerta.moneda, alerta.precio)} {comparador} {zona}"
        dist = _fmt_pct(ctx.distancia_pct)
        if dist:
            linea += f" ({dist})"
        return linea + _sufijo_serie(alerta)

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


def _linea_diagnostico(alerta: Alerta) -> str:
    ctx = alerta.contexto
    nombre = escapar_html(ctx.diag_nombre_dimension or dimension_de_tipo(alerta.tipo) or "Diagnóstico")
    return f"<b>{nombre}</b>: {escapar_html(ctx.diag_de or '—')} → <b>{escapar_html(ctx.diag_a or '—')}</b>"


def _lineas_diagnostico(alerta: Alerta, nivel_detalle: str) -> list[str]:
    ctx = alerta.contexto
    if nivel_detalle == NIVEL_COMPACTO:
        trozos = [f"<b>{escapar_html(alerta.ticker)}</b>"]
        if alerta.cartera or ctx.cartera_nombre:
            trozos.append(escapar_html(alerta.cartera or ctx.cartera_nombre))
        elif ctx.origen == ORIGEN_WATCHLIST:
            trozos.append("watchlist")
        trozos.append(_linea_diagnostico(alerta))
        return [" · ".join(trozos)]
    lineas = [_linea_identidad(alerta), _linea_diagnostico(alerta)]
    if ctx.diag_razon:
        lineas.append(escapar_html(ctx.diag_razon))
    # Sin consejo de ejecución: el aviso dice qué cambió y con qué datos, nada más.
    pie = ["información de seguimiento, no una indicación de operar"]
    fecha = _fmt_fecha_corta(ctx.diag_fecha_dato)
    if fecha:
        pie.insert(0, f"dato del {fecha}")
    if ctx.diag_version is not None:
        pie.insert(-1, f"reglas v{ctx.diag_version}")
    lineas.append(f"<i>{escapar_html(' · '.join(pie))}</i>")
    return lineas


def _lineas(alerta: Alerta, nivel_detalle: str) -> list[str]:
    """Las líneas de un aviso. `completo` = 3 o 4 líneas; `compacto` = exactamente una."""
    if es_tipo_diagnostico(alerta.tipo):
        return _lineas_diagnostico(alerta, nivel_detalle)
    es_senal = es_tipo_senal(alerta.tipo)

    if nivel_detalle == NIVEL_COMPACTO:
        trozos = [f"<b>{escapar_html(alerta.ticker)}</b>"]
        cartera = alerta.cartera or alerta.contexto.cartera_nombre
        if cartera:
            trozos.append(escapar_html(cartera))
        elif alerta.contexto.origen == ORIGEN_WATCHLIST:
            trozos.append("watchlist")
        if es_senal:
            trozos.append(escapar_html(alerta.contexto.estrategia_nombre or "Estrategia"))
            trozos.append(_monto(alerta.moneda, alerta.precio))
        else:
            comparador = "≤" if alerta.tipo in _DISPARA_HACIA_ABAJO else "≥"
            nivel = (
                f"{_monto(alerta.moneda, alerta.precio)} {comparador} "
                f"{_monto(alerta.moneda, alerta.nivel)}"
            )
            # Hasta en el modo compacto la serie tiene que aparecer: dos monedas distintas sin
            # aclarar cuál es cuál es peor que un mensaje más largo.
            trozos.append(nivel + _sufijo_serie(alerta))
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
