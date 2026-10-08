"""Niveles de stop-loss y objetivo: resuelve **de dónde sale** el nivel vigente de cada ticker.

El stop-loss y el objetivo de una posición pueden venir de dos lados: de la pestaña `Instrumentos`
del Sheet (las columnas `Stop Loss Modo/Valor` y `Objetivo Modo/Valor`, que el sync espeja en
`instrumentos_inversion`) o de la app, donde el usuario los fija desde el detalle del ticker.
**Gana la app**: si hay override, el del Sheet queda como referencia y nada más.

El override no puede vivir en `instrumentos_inversion` porque el sync le hace DELETE + INSERT
completo en cada corrida (ver `NivelPrecioOverride`), así que va en una tabla propia y acá se
mezclan las dos fuentes. Este módulo es el **único** lugar donde se decide esa precedencia: sus
dos consumidores son `inversiones_analytics.get_rendimiento_por_ticker` (la lista de posiciones,
de donde comen alertas, diagnóstico y el frontend) y `ticker_analytics.get_ticker_position`.

El cálculo del nivel en sí **no** está acá: lo sigue haciendo `inversiones_analytics._nivel_precio`,
que es matemática pura sin `Session`. Acá sólo se resuelve qué `(modo, valor)` entra a esa función.

Sin `@cache_por_sync`: son lecturas de una tabla chica y escrituras del usuario, y el caché de
`get_rendimiento_por_ticker` ya cubre la parte cara.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..database import InstrumentoInversion, NivelPrecioOverride
from . import alertas_engine

#: Los dos niveles de una posición. Mismos strings que `alertas_engine`, porque son los que van en
#: `AlertaPrecio.tipo`: es lo que permite re-armar la alerta exacta del nivel que cambió.
TIPO_STOP_LOSS = alertas_engine.TIPO_STOP_LOSS
TIPO_OBJETIVO = alertas_engine.TIPO_OBJETIVO
TIPOS = (TIPO_STOP_LOSS, TIPO_OBJETIVO)

#: Modos admitidos, con la grafía exacta que espera `inversiones_analytics._nivel_precio` y que
#: valida el parser del Sheet (`validation/parsers._parse_nivel_precio`).
MODO_PORCENTAJE = "Porcentaje"
MODO_FIJO = "Fijo"
MODOS = (MODO_PORCENTAJE, MODO_FIJO)

ORIGEN_APP = "app"
ORIGEN_SHEET = "sheet"
ORIGEN_NINGUNO = "ninguno"

#: Techo del objetivo en modo porcentaje. Un x11 sobre el precio de compra ya es más probable que
#: sea un dedazo (poner el precio absoluto en el campo de porcentaje) que una intención.
LIMITE_OBJETIVO_PCT = 1000.0

#: Mensaje de cada código de error de `aplicar_cambios`, para que el router sólo haga el lookup y
#: no se escriba el texto dos veces.
MENSAJE_ERROR = {
    "sin_cambios": "No se mandó ningún nivel para cambiar",
    "modo_invalido": f"El modo tiene que ser '{MODO_PORCENTAJE}' o '{MODO_FIJO}'",
    "fijo_no_positivo": "Un precio fijo tiene que ser mayor que cero",
    "porcentaje_cero": "Un 0% deja el nivel en el precio de compra: no es un nivel",
    "signo_stop_loss": "El stop-loss en porcentaje va negativo (-5 = 5% por debajo del precio promedio de compra)",
    "signo_objetivo": "El objetivo en porcentaje va positivo (20 = 20% por encima del precio promedio de compra)",
    "porcentaje_fuera_de_rango": "El porcentaje está fuera de rango",
}


@dataclass(frozen=True)
class NivelEfectivo:
    """Un nivel ya resuelto: qué se usa para calcular, de dónde salió, y qué dice el Sheet.

    `modo`/`valor` son el nivel **vigente** (el de la app si hay override, el del Sheet si no).
    `modo_sheet`/`valor_sheet` son siempre los del Sheet, para poder mostrarlos como referencia y
    ofrecer "volver al valor del Sheet" sin una consulta aparte.
    """
    modo: Optional[str] = None
    valor: Optional[float] = None
    origen: str = ORIGEN_NINGUNO
    modo_sheet: Optional[str] = None
    valor_sheet: Optional[float] = None
    actualizado_en: Optional[datetime] = None  # sólo con origen "app"

    @property
    def par(self) -> tuple[Optional[str], Optional[float]]:
        """El `(modo, valor)` vigente: lo que define si el nivel cambió de verdad."""
        return self.modo, self.valor


@dataclass(frozen=True)
class NivelesTicker:
    objetivo: NivelEfectivo = NivelEfectivo()
    stop_loss: NivelEfectivo = NivelEfectivo()

    def de_tipo(self, tipo: str) -> NivelEfectivo:
        return self.stop_loss if tipo == TIPO_STOP_LOSS else self.objetivo


#: Un ticker sin instrumento ni override. Evita construir un `NivelesTicker` por cada ticker que
#: aparece en los movimientos pero no está en `instrumentos_inversion`.
VACIO = NivelesTicker()

#: `None` es un valor válido para `instrumento` (el ticker no está en el Sheet), así que no sirve
#: como "no me lo pasaste".
_NO_DADO = object()


# ── Lectura ───────────────────────────────────────────────────────────────────

def _campos_sheet(instrumento, tipo: str) -> tuple[Optional[str], Optional[float]]:
    if instrumento is None:
        return None, None
    if tipo == TIPO_STOP_LOSS:
        modo, valor = instrumento.stop_loss_modo, instrumento.stop_loss_valor
    else:
        modo, valor = instrumento.objetivo_modo, instrumento.objetivo_valor
    return modo, float(valor) if valor is not None else None


def _nivel_efectivo(instrumento, override: Optional[NivelPrecioOverride], tipo: str) -> NivelEfectivo:
    modo_sheet, valor_sheet = _campos_sheet(instrumento, tipo)

    # Una fila de override sin `modo` o sin `valor` se ignora y manda el Sheet. Hoy no se escribe
    # ninguna así (quitar un override borra la fila); el día que exista "override = sin nivel" la
    # decisión se toma acá, que es el único lugar que resuelve la precedencia.
    if override is not None and override.modo and override.valor is not None:
        return NivelEfectivo(
            modo=override.modo,
            valor=float(override.valor),
            origen=ORIGEN_APP,
            modo_sheet=modo_sheet,
            valor_sheet=valor_sheet,
            actualizado_en=override.fecha_actualizacion,
        )
    if modo_sheet and valor_sheet is not None:
        return NivelEfectivo(
            modo=modo_sheet, valor=valor_sheet, origen=ORIGEN_SHEET,
            modo_sheet=modo_sheet, valor_sheet=valor_sheet,
        )
    return NivelEfectivo(origen=ORIGEN_NINGUNO, modo_sheet=modo_sheet, valor_sheet=valor_sheet)


def resolver(instrumento, overrides: Optional[dict] = None) -> NivelesTicker:
    """Mezcla el instrumento del Sheet con los overrides de ese ticker. Pura, sin `Session`."""
    overrides = overrides or {}
    return NivelesTicker(
        objetivo=_nivel_efectivo(instrumento, overrides.get(TIPO_OBJETIVO), TIPO_OBJETIVO),
        stop_loss=_nivel_efectivo(instrumento, overrides.get(TIPO_STOP_LOSS), TIPO_STOP_LOSS),
    )


def overrides_por_ticker(db: Session) -> dict[str, dict[str, NivelPrecioOverride]]:
    """Todos los overrides en **una** consulta, indexados por ticker y tipo."""
    salida: dict[str, dict[str, NivelPrecioOverride]] = {}
    for fila in db.query(NivelPrecioOverride).all():
        salida.setdefault(fila.ticker, {})[fila.tipo] = fila
    return salida


def mapa_niveles_efectivos(db: Session, instrumentos: dict) -> dict[str, NivelesTicker]:
    """Niveles vigentes de todos los tickers, para los recorridos por cartera.

    Una sola consulta extra en total, nunca una por ticker: `get_rendimiento_por_ticker` se llama
    varias veces por request (flujo de caja, descomposición FX, vencimientos) y una vez por cartera
    en cada corrida de alertas.
    """
    overrides = overrides_por_ticker(db)
    tickers = set(instrumentos) | set(overrides)
    return {t: resolver(instrumentos.get(t), overrides.get(t)) for t in tickers}


def niveles_de_ticker(db: Session, ticker: str, instrumento=_NO_DADO) -> NivelesTicker:
    """Niveles vigentes de un solo ticker (detalle y endpoints de edición). Dos filas como máximo."""
    if instrumento is _NO_DADO:
        instrumento = (
            db.query(InstrumentoInversion).filter(InstrumentoInversion.ticker == ticker).first()
        )
    filas = db.query(NivelPrecioOverride).filter(NivelPrecioOverride.ticker == ticker).all()
    return resolver(instrumento, {f.tipo: f for f in filas})


# ── Escritura ─────────────────────────────────────────────────────────────────

def _validar(tipo: str, modo, valor) -> Optional[str]:
    """Reglas que dependen del tipo de nivel, así que no pueden ir en el schema de Pydantic.

    El signo **se rechaza, no se normaliza**: corregirlo en silencio (`-abs(valor)`) haría que el
    usuario crea que guardó otra cosa. Además mantiene un solo lenguaje con el Sheet, donde un
    stop-loss del 5% se escribe `-5`.
    """
    if modo not in MODOS:
        return "modo_invalido"
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return "modo_invalido"

    if modo == MODO_FIJO:
        return None if valor > 0 else "fijo_no_positivo"

    if valor == 0:
        return "porcentaje_cero"
    if tipo == TIPO_STOP_LOSS:
        if valor > 0:
            return "signo_stop_loss"
        if valor <= -100:  # no se puede perder más del 100% del precio de compra
            return "porcentaje_fuera_de_rango"
    else:
        if valor < 0:
            return "signo_objetivo"
        if valor > LIMITE_OBJETIVO_PCT:
            return "porcentaje_fuera_de_rango"
    return None


def _upsert(db: Session, ticker: str, tipo: str, modo: str, valor: float) -> None:
    ahora = datetime.now()
    fila = (
        db.query(NivelPrecioOverride)
        .filter(NivelPrecioOverride.ticker == ticker, NivelPrecioOverride.tipo == tipo)
        .first()
    )
    if fila is None:
        db.add(NivelPrecioOverride(
            ticker=ticker, tipo=tipo, modo=modo, valor=valor,
            fecha_creacion=ahora, fecha_actualizacion=ahora,
        ))
    else:
        fila.modo = modo
        fila.valor = valor
        fila.fecha_actualizacion = ahora


def _eliminar(db: Session, ticker: str, tipo: str) -> None:
    fila = (
        db.query(NivelPrecioOverride)
        .filter(NivelPrecioOverride.ticker == ticker, NivelPrecioOverride.tipo == tipo)
        .first()
    )
    if fila is not None:
        db.delete(fila)


def aplicar_cambios(
    db: Session, ticker: str, cambios: dict,
) -> tuple[Optional[NivelesTicker], Optional[str]]:
    """Aplica un cambio parcial de niveles y re-arma las alertas de los que cambiaron.

    `cambios` trae **sólo las claves que mandó el request**: `{"stop_loss": {...}}` no toca el
    objetivo, y `{"stop_loss": None}` borra ese override y vuelve al valor del Sheet. Los dos
    DELETE del router pasan por acá con `None`, así que hay un solo camino de escritura y un solo
    lugar que re-arma.

    Devuelve `(niveles, None)` o `(None, codigo_de_error)`; los códigos están en `MENSAJE_ERROR`.
    Valida **todo** antes de escribir nada: un PUT con los dos niveles donde uno está mal no deja
    el otro guardado a medias.
    """
    claves = [t for t in TIPOS if t in cambios]
    if not claves:
        return None, "sin_cambios"

    for tipo in claves:
        entrada = cambios[tipo]
        if entrada is None:
            continue
        error = _validar(tipo, entrada.get("modo"), entrada.get("valor"))
        if error:
            return None, error

    antes = niveles_de_ticker(db, ticker)
    for tipo in claves:
        entrada = cambios[tipo]
        if entrada is None:
            _eliminar(db, ticker, tipo)
        else:
            _upsert(db, ticker, tipo, entrada["modo"], float(entrada["valor"]))
    db.flush()
    despues = niveles_de_ticker(db, ticker)

    # Sólo lo que cambió de verdad: un PUT que reescribe el mismo nivel —o que borra un override
    # que coincidía con el del Sheet— no tiene por qué resucitar un aviso ya emitido.
    cambiados = [t for t in claves if antes.de_tipo(t).par != despues.de_tipo(t).par]
    if cambiados:
        # Import diferido: `alertas_analytics` importa `inversiones_analytics`, que importa este
        # módulo. A nivel de módulo sería un ciclo.
        from . import alertas_analytics
        alertas_analytics.rearmar_por_cambio_de_nivel(db, ticker, cambiados)

    db.commit()
    return despues, None


def a_dict(ticker: str, niveles: NivelesTicker) -> dict:
    """Forma que consume el schema `NivelesTickerOut`."""
    def uno(nivel: NivelEfectivo) -> dict:
        return {
            "modo": nivel.modo,
            "valor": nivel.valor,
            "origen": nivel.origen,
            "modo_sheet": nivel.modo_sheet,
            "valor_sheet": nivel.valor_sheet,
            "actualizado_en": nivel.actualizado_en,
        }
    return {"ticker": ticker, "objetivo": uno(niveles.objetivo), "stop_loss": uno(niveles.stop_loss)}
