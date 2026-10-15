"""Zonas de compra y de venta: el rango de precios en el que el usuario quiere entrar o salir.

Reemplaza al escalar `WatchlistItem.objetivo` (un único precio de compra) por un rango que se
dibuja y se arrastra sobre el gráfico de análisis técnico. Ver `database.ZonaPrecio` para el
modelo y el por qué de la clave `(ticker, tipo)`.

Estructura calcada de `niveles_analytics`, que resuelve el problema hermano (stop-loss y objetivo
de una posición): validación con códigos de error en un solo lugar, una lectura por ticker y otra
en bloque para los recorridos, y una escritura que re-arma las alertas afectadas dentro de la
misma transacción.

**Qué dispara.** El borde de disparo es el `techo` en una zona de compra (el precio baja y entra en
la banda) y el `piso` en una de venta (el precio sube y entra). El borde opuesto **no** dispara ni
decide nada: sirve para dibujar la banda y para informarlo en el aviso.

Que `en_zona` sea "cruzó el borde de disparo" y no "está estrictamente dentro del rango" es
deliberado: con una zona de compra de 1150-1250, un precio de 1000 está *más* adentro de la
oportunidad, no afuera, y además mantiene exactamente la semántica que tenía el badge de la
watchlist cuando el nivel era un escalar. Consecuencia: el borde opuesto tampoco puede re-armar la
alerta (si a 1000 sigue "en zona", salir por abajo no es un evento), así que el antirrebote es el
de siempre, la banda porcentual sobre el borde de disparo.

**Qué moneda.** Ninguna conversión: una zona se compara siempre contra el precio de **su propia
serie** (`variante`). Una zona `local` contra el precio cotizado acá; una `subyacente` contra la
serie del instrumento en EE.UU. en USD nativo. Mezclarlas compararía pesos contra dólares.

Sin `@cache_por_sync`, como `niveles_analytics`: es una tabla chica que además escribe el usuario.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ..database import ZonaPrecio
from . import alertas_engine

#: Los dos lados de una zona.
TIPO_COMPRA = "compra"
TIPO_VENTA = "venta"
TIPOS = (TIPO_COMPRA, TIPO_VENTA)

#: Sobre qué serie se mide. Mismos valores que `ohlcv_analytics` / el endpoint de serie técnica.
VARIANTE_LOCAL = "local"
VARIANTE_SUBYACENTE = "subyacente"
VARIANTES = (VARIANTE_LOCAL, VARIANTE_SUBYACENTE)

#: Tipo de `AlertaPrecio` de cada lado. La zona de compra reusa `compra_zona`, el tipo que ya
#: existía cuando el nivel era el `Objetivo` de la watchlist: así las filas ya emitidas siguen
#: siendo las mismas y el interruptor de avisos no cambia de significado.
TIPO_ALERTA = {
    TIPO_COMPRA: alertas_engine.TIPO_COMPRA_ZONA,
    TIPO_VENTA: alertas_engine.TIPO_VENTA_ZONA,
}

MENSAJE_ERROR = {
    "sin_cambios": "No se mandó ninguna zona para cambiar",
    "tipo_invalido": f"El tipo de zona tiene que ser '{TIPO_COMPRA}' o '{TIPO_VENTA}'",
    "variante_invalida": f"La variante tiene que ser '{VARIANTE_LOCAL}' o '{VARIANTE_SUBYACENTE}'",
    "zona_vacia": "Una zona necesita al menos uno de los dos bordes",
    "borde_no_positivo": "Los bordes de la zona tienen que ser mayores que cero",
    "bordes_invertidos": "El piso de la zona tiene que ser menor que el techo",
}


@dataclass(frozen=True)
class Zona:
    """Una zona ya resuelta. `piso`/`techo` en la moneda de su propia serie."""
    tipo: str
    variante: str = VARIANTE_LOCAL
    moneda: str = ""
    piso: Optional[float] = None
    techo: Optional[float] = None
    activa: bool = True
    # Apagada por la migración a la serie de referencia, no por el usuario. Sigue siendo
    # `activa=False`: las alertas y las distancias no la evalúan.
    vencida: bool = False
    notas: Optional[str] = None
    actualizado_en: Optional[datetime] = None

    @property
    def borde_disparo(self) -> Optional[float]:
        """El borde cuyo cruce dispara el aviso: el techo si se compra, el piso si se vende."""
        return self.techo if self.tipo == TIPO_COMPRA else self.piso

    @property
    def borde_informativo(self) -> Optional[float]:
        """El borde que **no** dispara: el piso en una zona de compra, el techo en una de venta.

        Se dibuja y se escribe en el aviso ("entró en la zona 1150-1250"), pero no participa de
        ninguna decisión. En particular no re-arma la alerta: salir por abajo del piso de una zona
        de compra no es dejar de estar en zona —es estar más barato—, así que lo único que puede
        re-armar el aviso es volver por arriba del techo (ver `alertas_engine._lejos_del_nivel`).
        """
        return self.piso if self.tipo == TIPO_COMPRA else self.techo

    @property
    def par(self) -> tuple:
        """Lo que define si la zona cambió de verdad (y entonces hay que re-armar la alerta)."""
        return (self.piso, self.techo, self.variante, self.activa)


@dataclass(frozen=True)
class ZonasTicker:
    compra: Optional[Zona] = None
    venta: Optional[Zona] = None

    def de_tipo(self, tipo: str) -> Optional[Zona]:
        return self.compra if tipo == TIPO_COMPRA else self.venta


VACIO = ZonasTicker()


# ── Cálculo (puro) ────────────────────────────────────────────────────────────

def estado_de_zona(
    zona: Optional[Zona], precio: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[bool]]:
    """`(precio_del_borde_de_disparo, pct_restante, en_zona)`.

    `pct_restante` sigue el criterio de `inversiones_analytics._nivel_precio`:
    `(nivel - precio_actual) / precio_actual`, negativo mientras el precio todavía no llegó al
    borde desde su lado. El frontend usa el valor absoluto como distancia.

    Devuelve `(None, None, None)` si no hay zona, si está apagada, si no tiene borde de disparo
    (zona abierta justo de ese lado) o si no hay precio: son todos "no se puede decir", distintos
    de un `False`.
    """
    if zona is None or not zona.activa or precio is None:
        return None, None, None
    nivel = zona.borde_disparo
    if nivel is None:
        return None, None, None
    if precio <= 0:
        return nivel, None, None

    pct_restante = (nivel - precio) / precio
    en_zona = precio <= nivel if zona.tipo == TIPO_COMPRA else precio >= nivel
    return nivel, pct_restante, en_zona


# ── Lectura ───────────────────────────────────────────────────────────────────

def _a_zona(fila: ZonaPrecio) -> Zona:
    return Zona(
        tipo=fila.tipo,
        variante=fila.variante or VARIANTE_LOCAL,
        moneda=fila.moneda or "",
        piso=float(fila.piso) if fila.piso is not None else None,
        techo=float(fila.techo) if fila.techo is not None else None,
        activa=bool(fila.activa),
        vencida=bool(getattr(fila, "vencida", 0)),
        notas=fila.notas,
        actualizado_en=fila.fecha_actualizacion,
    )


def _agrupar(filas: Iterable[ZonaPrecio]) -> ZonasTicker:
    por_tipo = {f.tipo: _a_zona(f) for f in filas}
    return ZonasTicker(compra=por_tipo.get(TIPO_COMPRA), venta=por_tipo.get(TIPO_VENTA))


def zonas_de_ticker(db: Session, ticker: str) -> ZonasTicker:
    """Las zonas de un solo ticker. Dos filas como máximo."""
    return _agrupar(db.query(ZonaPrecio).filter(ZonaPrecio.ticker == ticker).all())


def mapa_zonas(db: Session) -> dict[str, ZonasTicker]:
    """Todas las zonas en **una** consulta, por ticker.

    Lo usan los recorridos que necesitan la zona de muchos tickers a la vez (la watchlist entera,
    la corrida de alertas), igual que `niveles_analytics.mapa_niveles_efectivos`: nunca una
    consulta por ticker.
    """
    salida: dict[str, list[ZonaPrecio]] = {}
    for fila in db.query(ZonaPrecio).all():
        salida.setdefault(fila.ticker, []).append(fila)
    return {t: _agrupar(filas) for t, filas in salida.items()}


# ── Escritura ─────────────────────────────────────────────────────────────────

def _validar(tipo: str, entrada: dict) -> Optional[str]:
    """Reglas que dependen del tipo de zona, así que no van en el schema de Pydantic."""
    if tipo not in TIPOS:
        return "tipo_invalido"

    variante = entrada.get("variante") or VARIANTE_LOCAL
    if variante not in VARIANTES:
        return "variante_invalida"

    piso, techo = entrada.get("piso"), entrada.get("techo")
    if piso is None and techo is None:
        return "zona_vacia"
    for borde in (piso, techo):
        if borde is None:
            continue
        try:
            borde = float(borde)
        except (TypeError, ValueError):
            return "borde_no_positivo"
        if borde <= 0:
            return "borde_no_positivo"
    if piso is not None and techo is not None and float(piso) >= float(techo):
        return "bordes_invertidos"
    return None


def _upsert(db: Session, ticker: str, tipo: str, entrada: dict) -> None:
    ahora = datetime.now()
    fila = (
        db.query(ZonaPrecio)
        .filter(ZonaPrecio.ticker == ticker, ZonaPrecio.tipo == tipo)
        .first()
    )
    piso = entrada.get("piso")
    techo = entrada.get("techo")
    valores = {
        "variante": entrada.get("variante") or VARIANTE_LOCAL,
        "moneda": (entrada.get("moneda") or "").strip().upper(),
        "piso": float(piso) if piso is not None else None,
        "techo": float(techo) if techo is not None else None,
        "activa": 1 if entrada.get("activa", True) else 0,
        # Dibujar o editar la zona es la respuesta al aviso de "vencida": deja de estarlo.
        "vencida": 0,
        "notas": (entrada.get("notas") or "").strip() or None,
    }
    if fila is None:
        db.add(ZonaPrecio(
            ticker=ticker, tipo=tipo, fecha_creacion=ahora, fecha_actualizacion=ahora, **valores,
        ))
    else:
        for campo, valor in valores.items():
            setattr(fila, campo, valor)
        fila.fecha_actualizacion = ahora


def _eliminar(db: Session, ticker: str, tipo: str) -> None:
    fila = (
        db.query(ZonaPrecio)
        .filter(ZonaPrecio.ticker == ticker, ZonaPrecio.tipo == tipo)
        .first()
    )
    if fila is not None:
        db.delete(fila)


def aplicar_cambios(
    db: Session, ticker: str, cambios: dict,
) -> tuple[Optional[ZonasTicker], Optional[str]]:
    """Aplica un cambio parcial de zonas y re-arma las alertas de las que cambiaron.

    `cambios` trae **sólo las claves que mandó el request**: `{"compra": {...}}` no toca la zona de
    venta, y `{"compra": None}` borra la de compra. Mismo contrato que
    `niveles_analytics.aplicar_cambios`.

    Valida **todo** antes de escribir nada: un PUT con las dos zonas donde una está mal no deja la
    otra guardada a medias.

    Devuelve `(zonas, None)` o `(None, codigo_de_error)`; los códigos están en `MENSAJE_ERROR`.
    """
    claves = [t for t in TIPOS if t in cambios]
    if not claves:
        return None, "sin_cambios"

    for tipo in claves:
        entrada = cambios[tipo]
        if entrada is None:
            continue
        error = _validar(tipo, entrada)
        if error:
            return None, error

    antes = zonas_de_ticker(db, ticker)
    for tipo in claves:
        entrada = cambios[tipo]
        if entrada is None:
            _eliminar(db, ticker, tipo)
        else:
            _upsert(db, ticker, tipo, entrada)
    db.flush()
    despues = zonas_de_ticker(db, ticker)

    # Sólo lo que cambió de verdad: un PUT que reescribe la misma zona no tiene por qué resucitar
    # un aviso ya emitido.
    def _par(zonas: ZonasTicker, tipo: str):
        zona = zonas.de_tipo(tipo)
        return zona.par if zona is not None else None

    cambiados = [TIPO_ALERTA[t] for t in claves if _par(antes, t) != _par(despues, t)]
    if cambiados:
        # Import diferido: `alertas_analytics` importa `inversiones_analytics`, que importa
        # `niveles_analytics`, que importa este módulo indirectamente. A nivel de módulo sería un
        # ciclo — mismo motivo que en `niveles_analytics.aplicar_cambios`.
        from . import alertas_analytics
        alertas_analytics.rearmar_por_cambio_de_nivel(db, ticker, cambiados)

    db.commit()
    return despues, None


def a_dict(ticker: str, zonas: ZonasTicker) -> dict:
    """Forma que consume el schema `ZonasTickerOut`."""
    def una(zona: Optional[Zona]) -> Optional[dict]:
        if zona is None:
            return None
        return {
            "variante": zona.variante,
            "moneda": zona.moneda,
            "piso": zona.piso,
            "techo": zona.techo,
            "activa": zona.activa,
            "vencida": zona.vencida,
            "notas": zona.notas,
            "actualizado_en": zona.actualizado_en,
        }
    return {"ticker": ticker, "compra": una(zonas.compra), "venta": una(zonas.venta)}
