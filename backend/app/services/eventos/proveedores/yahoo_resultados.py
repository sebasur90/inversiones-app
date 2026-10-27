"""Fechas de presentación de resultados desde Yahoo Finance (yfinance, ya dependencia; sin clave).

Cubre a los emisores del universo con símbolo en EE.UU. (CEDEARs y ADRs): las últimas presentaciones con
su EPS real y la próxima prevista. Las acciones que sólo cotizan en BYMA no tienen calendario en Yahoo
y se saltean.

- Una fecha pasada entra como `concluido`; una futura como `previsto`. Cuando Yahoo da un rango (dos
  fechas) la fecha es **estimada**: `precision_fecha="aproximada"`, y la pantalla lo muestra así.
- La hora viene en hora de Nueva York. Sin hora, el análisis no supone si fue antes o después del cierre.
- La relación con el ticker es directa y cierta (es el balance de la propia empresa): entra confirmada.
- Yahoo no es una fuente oficial: la verificación queda `sin_verificar`. La oficial es la comunicación
  de la empresa, que el usuario puede cargar como fuente.

`EVENTOS_RESULTADOS_ENABLED` (default `true`) lo apaga; `EVENTOS_RESULTADOS_MAX_POR_CORRIDA` (default 25)
limita cuántos emisores se consultan por corrida (rotando, como Marketaux). Ante un límite de tasa de
Yahoo se corta la corrida.
"""
from __future__ import annotations

import time as _time
from datetime import date, timedelta

from ...market_data import yahoo
from ...market_data.client import use_external_apis
from .base import (
    CAP_EVENTOS_PROGRAMADOS, ESTADO_OK, ESTADO_PARCIAL, ESTADO_RATE_LIMITED, ContextoProveedor, EventoCrudo,
    ProveedorEventos, ResultadoProveedor, booleano_env, entero_env,
)

PAUSA_SEG = 1.0
ANIOS_HISTORIA = 3
DIAS_FUTURO = 200


def _numero(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) else "s/d"


def eventos_de(simbolo: str, nombre: str | None, tickers: list[str], filas: list[dict], hoy: date) -> list[EventoCrudo]:
    """Pura: las filas de `yahoo.fetch_fechas_resultados` → eventos de resultados del emisor."""
    out = []
    for f in filas:
        fecha = f.get("fecha")
        if not isinstance(fecha, date) or not (hoy - timedelta(days=365 * ANIOS_HISTORIA) <= fecha <= hoy + timedelta(days=DIAS_FUTURO)):
            continue
        futuro = fecha >= hoy and f.get("eps_reportado") is None
        partes = [f"EPS estimado: {_numero(f.get('eps_estimado'))}"]
        if f.get("eps_reportado") is not None:
            partes.append(f"EPS informado: {_numero(f.get('eps_reportado'))}")
        if f.get("sorpresa_pct") is not None:
            partes.append(f"sorpresa: {f['sorpresa_pct']:+.1f} %")
        quien = nombre or simbolo
        out.append(EventoCrudo(
            proveedor="yahoo_resultados", id_externo=f"{simbolo}:{fecha.isoformat()}",
            titulo=f"Resultados trimestrales de {quien}", categoria="resultados", fecha_evento=fecha,
            hora_evento=f.get("hora"), zona_horaria="America/New_York" if f.get("hora") else None,
            precision_fecha="aproximada" if f.get("estimada") else "exacta",
            estado="previsto" if futuro else "concluido", programado=True,
            descripcion=f"Presentación de resultados de {quien} ({simbolo}). " + "; ".join(partes) + ". Fuente: Yahoo Finance.",
            fuente_principal="Yahoo Finance (calendario de resultados)",
            url_fuente=f"https://finance.yahoo.com/quote/{simbolo}/", pais=None,
            entidades={"empresas": [quien]},
            tickers=[{"ticker": t, "tipo_relacion": "directa", "relevancia": 1.0,
                      "justificacion": "Balance de la propia empresa"} for t in tickers],
        ))
    return out


class YahooResultados(ProveedorEventos):
    nombre = "yahoo_resultados"
    etiqueta = "Yahoo Finance (fechas de balances)"
    capacidades = (CAP_EVENTOS_PROGRAMADOS,)
    ayuda = "No necesita clave. Se apaga con EVENTOS_RESULTADOS_ENABLED=false."

    def habilitado(self) -> tuple[bool, str]:
        if not booleano_env("EVENTOS_RESULTADOS_ENABLED", True):
            return False, "Apagado con EVENTOS_RESULTADOS_ENABLED=false"
        if not use_external_apis():
            return False, "Las fuentes externas están apagadas (USE_EXTERNAL_APIS)"
        return True, ""

    def max_por_corrida(self) -> int:
        return entero_env("EVENTOS_RESULTADOS_MAX_POR_CORRIDA", 25, 1, 1000)

    def obtener(self, ctx: ContextoProveedor) -> ResultadoProveedor:
        candidatos = sorted((s for s in ctx.simbolos if s.simbolo and not s.es_accion_local), key=lambda s: s.simbolo)
        if not candidatos:
            return ResultadoProveedor(estado=ESTADO_OK, mensaje="No hay emisores con símbolo en EE.UU.")
        n = min(len(candidatos), max(0, ctx.solicitudes_disponibles))
        eventos: list[EventoCrudo] = []
        consultados = 0
        estado, mensaje = ESTADO_OK, ""
        for k in range(n):
            s = candidatos[(ctx.rotacion + k) % len(candidatos)]
            if k and PAUSA_SEG:
                _time.sleep(PAUSA_SEG)
            r = yahoo.fetch_fechas_resultados(s.simbolo)
            consultados += 1
            if r.estado == yahoo.ESTADO_RATE_LIMITED:
                estado, mensaje = (ESTADO_PARCIAL if eventos else ESTADO_RATE_LIMITED), "Yahoo pidió bajar el ritmo; se sigue en la próxima corrida."
                break
            if r.estado == yahoo.ESTADO_OK and r.datos:
                eventos.extend(eventos_de(s.simbolo, s.nombre, s.tickers, r.datos, ctx.hoy))
        if estado == ESTADO_OK:
            mensaje = f"{len(eventos)} fechas de {consultados} emisores"
        return ResultadoProveedor(estado=estado, mensaje=mensaje, eventos=eventos, solicitudes=consultados,
                                  rotacion=(ctx.rotacion + consultados) % len(candidatos))
