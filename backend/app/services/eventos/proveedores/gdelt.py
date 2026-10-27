"""GDELT DOC 2.0 (https://www.gdeltproject.org/): descubrimiento de acontecimientos globales y geopolíticos
recientes que no necesariamente nombran a un ticker.

Límites que condicionan el diseño:
- busca sólo en una **ventana móvil de 3 meses**: no sirve para historia (para eso está el catálogo);
- no pide clave, pero limita a **una solicitud cada 5 segundos** por IP (responde 429 con un texto, no
  JSON). Detrás de un proxy compartido el 429 puede llegar aunque esta app no haya consultado nada;
- devuelve artículos (`articles[]`: `url`, `title`, `seendate`, `domain`, `language`, `sourcecountry`),
  sin entidades ni tickers.

Por eso: arranca **apagado** (`GDELT_ENABLED=false`), hace pocas consultas temáticas por corrida
(`GDELT_CONSULTAS`, separadas por `;`), espera ≥ 5 s entre una y otra, y sus resultados **nunca** se
convierten solos en eventos: van a la bandeja de revisión como candidatos. Un resultado de búsqueda no
es un acontecimiento verificado.
"""
from __future__ import annotations

import os
import time as _time
from datetime import datetime, timedelta

from ...market_data.client import request_json, use_external_apis
from .. import normalizacion_engine as ne
from .base import (
    CAP_NOTICIAS_RANGO, ESTADO_ERROR, ESTADO_OK, ESTADO_PARCIAL, ESTADO_RATE_LIMITED, ContextoProveedor,
    NoticiaCruda, ProveedorEventos, ResultadoProveedor, booleano_env, entero_env,
)

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
PAUSA_SEG = 6.0
MAX_REGISTROS = 25
VENTANA_MAX_DIAS = 85          # la API admite hasta ~3 meses hacia atrás
VENTANA_INICIAL_DIAS = 3
CONSULTAS_DEFAULT = (
    "(war OR invasion OR ceasefire) sourcelang:english",
    "(sanctions OR tariffs OR \"trade war\") sourcelang:english",
    "(\"central bank\" OR \"interest rates\") sourcelang:english",
    "(elecciones OR bcra OR \"banco central\") sourcecountry:argentina",
)


def consultas() -> list[str]:
    crudo = os.getenv("GDELT_CONSULTAS")
    if crudo is None:
        return list(CONSULTAS_DEFAULT)
    return [c.strip() for c in crudo.split(";") if c.strip()]


def parsear_articulo(art: dict) -> NoticiaCruda | None:
    if not isinstance(art, dict):
        return None
    url = art.get("url")
    titulo = ne.texto_plano(art.get("title"), ne.MAX_TITULO)
    fecha = ne.parse_fecha(art.get("seendate"))
    if not ne.url_valida(url) or not titulo or fecha is None:
        return None
    pais = ne.texto_plano(art.get("sourcecountry"), 60)
    return NoticiaCruda(
        proveedor="gdelt", id_externo=None, url=url, titulo=titulo, fecha_publicacion=fecha,
        medio=ne.texto_plano(art.get("domain"), 120), idioma=ne.texto_plano(art.get("language"), 30),
        fragmento=f"País del medio: {pais}" if pais else None,
    )


class Gdelt(ProveedorEventos):
    nombre = "gdelt"
    etiqueta = "GDELT (acontecimientos globales, últimos 3 meses)"
    capacidades = (CAP_NOTICIAS_RANGO,)
    ayuda = (
        "No necesita clave. Se prende con GDELT_ENABLED=true; sus resultados van siempre a la bandeja "
        "de revisión. Sólo cubre los últimos 3 meses y limita a una consulta cada 5 segundos."
    )
    solo_revision = True

    def habilitado(self) -> tuple[bool, str]:
        if not booleano_env("GDELT_ENABLED", False):
            return False, "Apagado (GDELT_ENABLED=false)"
        if not use_external_apis():
            return False, "Las fuentes externas están apagadas (USE_EXTERNAL_APIS)"
        return True, ""

    def max_por_corrida(self) -> int:
        return entero_env("GDELT_MAX_CONSULTAS_POR_CORRIDA", 4, 1, 20)

    def obtener(self, ctx: ContextoProveedor) -> ResultadoProveedor:
        ahora = datetime.utcnow()
        desde = max(ctx.cursor or (ahora - timedelta(days=VENTANA_INICIAL_DIAS)), ahora - timedelta(days=VENTANA_MAX_DIAS))
        lista = consultas()[: max(0, ctx.solicitudes_disponibles)]
        noticias: list[NoticiaCruda] = []
        estado, mensaje = ESTADO_OK, ""
        gastadas = 0
        for k, q in enumerate(lista):
            if k and PAUSA_SEG:
                _time.sleep(PAUSA_SEG)
            status, body = request_json("GET", URL, params={
                "query": q, "mode": "artlist", "format": "json", "maxrecords": str(MAX_REGISTROS), "sort": "HybridRel",
                "startdatetime": desde.strftime("%Y%m%d%H%M%S"), "enddatetime": ahora.strftime("%Y%m%d%H%M%S"),
            }, timeout=30.0)
            gastadas += 1
            if status == 429:
                estado, mensaje = (ESTADO_PARCIAL if noticias else ESTADO_RATE_LIMITED), "GDELT limita a una consulta cada 5 segundos por IP; se reintenta en la próxima corrida."
                break
            if status is None or status != 200:
                estado, mensaje = (ESTADO_PARCIAL if noticias else ESTADO_ERROR), f"GDELT no respondió bien ({status or 'sin respuesta'})."
                break
            articulos = body.get("articles") if isinstance(body, dict) else None
            for a in articulos or []:
                n = parsear_articulo(a)
                if n:
                    noticias.append(n)
        if estado == ESTADO_OK:
            mensaje = f"{len(noticias)} candidatos en {gastadas} consultas"
        cursor = ahora if estado == ESTADO_OK else ctx.cursor
        return ResultadoProveedor(estado=estado, mensaje=mensaje, noticias=noticias, solicitudes=gastadas, cursor=cursor)
