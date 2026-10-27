"""Interfaz común de los proveedores del Calendario de eventos.

Un proveedor trae **noticias** (`NoticiaCruda`), **eventos programados o ya estructurados**
(`EventoCrudo`), o ambos, y declara qué sabe hacer en `capacidades`. La interfaz no conoce a la UI ni a
la base: el orquestador (`eventos_sync`) normaliza, deduplica, clasifica y persiste.

Contrato de `obtener`:
- **nunca lanza**: un fallo de red, un timeout, un límite de uso o una respuesta rara vuelven como
  `ResultadoProveedor(estado=...)` con un mensaje para mostrar;
- no gasta más de `ctx.solicitudes_disponibles` solicitudes y devuelve cuántas gastó;
- devuelve el `cursor` (último instante traído) para que la próxima corrida no vuelva a pedir lo mismo;
- trata todo lo que llega como dato no confiable (las URLs y los textos se validan después, igual).

Sin credenciales configuradas, `configurado()` devuelve `(False, motivo)` y el orquestador no lo llama:
la pantalla y los eventos manuales siguen funcionando.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, time

ESTADO_OK = "ok"
ESTADO_PARCIAL = "parcial"              # trajo algo pero cortó antes (límite, una consulta falló)
ESTADO_NO_CONFIGURADO = "no_configurado"
ESTADO_DESACTIVADO = "desactivado"
ESTADO_RATE_LIMITED = "rate_limited"
ESTADO_CUPO_AGOTADO = "cupo_agotado"
ESTADO_ERROR = "error"

CAP_NOTICIAS_RANGO = "noticias_rango"
CAP_NOTICIAS_TICKERS = "noticias_tickers"
CAP_EVENTOS_PROGRAMADOS = "eventos_programados"


@dataclass
class NoticiaCruda:
    proveedor: str
    url: str
    titulo: str
    fecha_publicacion: datetime          # UTC naive
    id_externo: str | None = None
    fragmento: str | None = None
    medio: str | None = None
    idioma: str | None = None
    # [{simbolo, nombre, tipo, industria, pais, match_score, sentimiento, en_titulo}]
    entidades: list[dict] = field(default_factory=list)


@dataclass
class EventoCrudo:
    proveedor: str
    id_externo: str
    titulo: str
    categoria: str
    fecha_evento: date
    origen: str = "proveedor"            # proveedor | calendario_oficial | importacion | catalogo
    descripcion: str | None = None
    fecha_fin: date | None = None
    hora_evento: time | None = None
    zona_horaria: str | None = None
    fecha_publicacion: datetime | None = None
    precision_fecha: str = "exacta"
    estado: str = "confirmado"
    programado: bool = False
    pais: str | None = None
    region: str | None = None
    importancia: int | None = None       # None = la decide la clasificación
    verificacion: str = "sin_verificar"
    fuente_principal: str | None = None
    url_fuente: str | None = None
    entidades: dict = field(default_factory=dict)
    # [{ticker, tipo_relacion, relevancia, justificacion}] que el proveedor conoce con certeza
    tickers: list[dict] = field(default_factory=list)


@dataclass
class SimboloUniverso:
    """Un emisor del universo de la app tal como lo piden los proveedores externos."""
    simbolo: str                          # símbolo de Yahoo / EE.UU. (`AAPL`, `GGAL.BA`)
    tickers: list[str]                    # tickers de la app que representa (`AAPL`, `AAPLD`)
    nombre: str | None = None
    en_cartera: bool = False
    es_accion_local: bool = False


@dataclass
class ContextoProveedor:
    hoy: date
    simbolos: list[SimboloUniverso]
    cursor: datetime | None = None
    rotacion: int = 0
    solicitudes_disponibles: int = 0


@dataclass
class ResultadoProveedor:
    estado: str
    mensaje: str = ""
    noticias: list[NoticiaCruda] = field(default_factory=list)
    eventos: list[EventoCrudo] = field(default_factory=list)
    solicitudes: int = 0
    cursor: datetime | None = None
    rotacion: int | None = None


def entero_env(nombre: str, default: int, minimo: int = 0, maximo: int = 10_000) -> int:
    try:
        valor = int((os.getenv(nombre) or "").strip() or default)
    except ValueError:
        return default
    return valor if minimo <= valor <= maximo else default


def booleano_env(nombre: str, default: bool) -> bool:
    crudo = (os.getenv(nombre) or "").strip().lower()
    if not crudo:
        return default
    return crudo in ("true", "1", "yes")


class ProveedorEventos:
    """Base de los proveedores. Cada uno define sus atributos y sobreescribe lo que soporta."""

    nombre: str = ""
    etiqueta: str = ""
    capacidades: tuple[str, ...] = ()
    #: Cómo habilitarlo, para mostrar en la pantalla cuando falta configuración.
    ayuda: str = ""
    #: Sus noticias nunca se incorporan solas como eventos: van a la bandeja de revisión.
    solo_revision: bool = False
    #: Usa la red (se apaga con `USE_EXTERNAL_APIS=false`).
    usa_red: bool = True

    def configurado(self) -> tuple[bool, str]:
        return True, ""

    def habilitado(self) -> tuple[bool, str]:
        return True, ""

    def limite_diario(self) -> int | None:
        """Tope de solicitudes por día calendario, o `None` si no tiene."""
        return None

    def max_por_corrida(self) -> int:
        return 1

    def obtener(self, ctx: ContextoProveedor) -> ResultadoProveedor:  # pragma: no cover - abstracto
        raise NotImplementedError
