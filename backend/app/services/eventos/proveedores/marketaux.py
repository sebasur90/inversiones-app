"""Marketaux (https://www.marketaux.com/): noticias financieras con entidades, tickers y sentimiento.

Configuración (variables de entorno, nunca en el código ni en el frontend):
- `MARKETAUX_API_TOKEN`: el token del plan. Sin él, el proveedor queda "no configurado" y no se llama.
- `MARKETAUX_MAX_SOLICITUDES_POR_CORRIDA` (default 5) y `MARKETAUX_LIMITE_DIARIO` (default 90): topes
  propios, contados en la base, por debajo del límite del plan (el gratuito da 100 por día).
- `MARKETAUX_ARTICULOS_POR_SOLICITUD` (default 3, lo que da el plan gratuito; 20 en Basic, 50 en
  Standard). Pedir más de lo que da el plan no falla, pero no trae más.

Cada corrida consulta `news/all` por tandas de símbolos del universo (cartera ∪ watchlist), rotando la
tanda entre corridas para cubrir a todos de a poco, con `filter_entities=true` (sólo las entidades
pedidas), `group_similar=true` y `published_after` de los últimos `DIAS_VENTANA` días. Si sobra cupo, una
última consulta general de macro y política.

Errores (documentados por Marketaux): 401 token inválido, 402 cupo del plan agotado, 403 endpoint fuera
del plan, 429 demasiadas solicitudes por minuto. Cualquiera de ellos corta la corrida y queda registrado;
lo ya traído se guarda igual.

El token viaja como parámetro de la consulta y nunca se loguea (`request_json` no loguea `params`). El
sentimiento que trae cada entidad se guarda como dato del proveedor: **no es un pronóstico del precio**.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from ...market_data.client import request_json, use_external_apis
from .. import normalizacion_engine as ne
from .base import (
    CAP_NOTICIAS_RANGO, CAP_NOTICIAS_TICKERS, ESTADO_CUPO_AGOTADO, ESTADO_ERROR, ESTADO_OK, ESTADO_PARCIAL,
    ESTADO_RATE_LIMITED, ContextoProveedor, NoticiaCruda, ProveedorEventos, ResultadoProveedor, entero_env,
)

URL = "https://api.marketaux.com/v1/news/all"
SIMBOLOS_POR_SOLICITUD = 5
DIAS_VENTANA = 3
CONSULTA_MACRO = (
    '"federal reserve" | "interest rates" | inflation | tariffs | election | sanctions | "central bank"'
)
TIMEOUT = 20.0

_ERRORES = {
    401: (ESTADO_ERROR, "El token de Marketaux no es válido (MARKETAUX_API_TOKEN)."),
    402: (ESTADO_CUPO_AGOTADO, "Se agotó el cupo diario del plan de Marketaux."),
    403: (ESTADO_ERROR, "El plan de Marketaux no incluye este endpoint."),
    429: (ESTADO_RATE_LIMITED, "Marketaux pidió bajar el ritmo (demasiadas solicitudes por minuto)."),
}


def token() -> str:
    return (os.getenv("MARKETAUX_API_TOKEN") or "").strip()


def _float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parsear_articulo(art: dict) -> NoticiaCruda | None:
    """Un artículo de `news/all` → `NoticiaCruda`, o `None` si le falta algo esencial o es inválido."""
    if not isinstance(art, dict):
        return None
    url = art.get("url")
    titulo = ne.texto_plano(art.get("title"), ne.MAX_TITULO)
    fecha = ne.parse_fecha(art.get("published_at"))
    if not ne.url_valida(url) or not titulo or fecha is None:
        return None
    entidades = []
    for ent in art.get("entities") or []:
        if not isinstance(ent, dict) or not ent.get("symbol"):
            continue
        en_titulo = any(
            isinstance(h, dict) and h.get("highlighted_in") == "title" for h in ent.get("highlights") or []
        )
        entidades.append({
            "simbolo": str(ent["symbol"]).upper()[:20],
            "nombre": ne.texto_plano(ent.get("name"), 120),
            "tipo": ne.texto_plano(ent.get("type"), 40),
            "industria": ne.texto_plano(ent.get("industry"), 80),
            "pais": ne.texto_plano(ent.get("country"), 40),
            "match_score": _float(ent.get("match_score")),
            "sentimiento": _float(ent.get("sentiment_score")),
            "en_titulo": en_titulo,
        })
    fuente = art.get("source")
    return NoticiaCruda(
        proveedor="marketaux", id_externo=str(art.get("uuid") or "")[:80] or None, url=url, titulo=titulo,
        fragmento=ne.texto_plano(art.get("description") or art.get("snippet")), fecha_publicacion=fecha,
        medio=ne.texto_plano(fuente, 120) if isinstance(fuente, str) else None,
        idioma=ne.texto_plano(art.get("language"), 8), entidades=entidades,
    )


class Marketaux(ProveedorEventos):
    nombre = "marketaux"
    etiqueta = "Marketaux (noticias financieras)"
    capacidades = (CAP_NOTICIAS_RANGO, CAP_NOTICIAS_TICKERS)
    ayuda = (
        "Creá una cuenta gratis en marketaux.com, copiá el token del panel y ponelo en "
        "MARKETAUX_API_TOKEN en el .env del servidor; después reiniciá el backend. El plan gratuito trae "
        "3 noticias por consulta y 100 consultas por día."
    )

    def configurado(self) -> tuple[bool, str]:
        return (True, "") if token() else (False, "Falta MARKETAUX_API_TOKEN")

    def habilitado(self) -> tuple[bool, str]:
        return (True, "") if use_external_apis() else (False, "Las fuentes externas están apagadas (USE_EXTERNAL_APIS)")

    def limite_diario(self) -> int | None:
        return entero_env("MARKETAUX_LIMITE_DIARIO", 90, 1, 100_000)

    def max_por_corrida(self) -> int:
        return entero_env("MARKETAUX_MAX_SOLICITUDES_POR_CORRIDA", 5, 1, 1000)

    def _consultar(self, params: dict) -> tuple[str, str, list[NoticiaCruda]]:
        status, body = request_json("GET", URL, params={"api_token": token(), **params}, timeout=TIMEOUT)
        if status is None:
            return ESTADO_ERROR, "Marketaux no respondió (timeout o red caída).", []
        if status in _ERRORES:
            estado, mensaje = _ERRORES[status]
            return estado, mensaje, []
        if status != 200 or not isinstance(body, dict):
            return ESTADO_ERROR, f"Marketaux respondió {status}.", []
        datos = body.get("data") if isinstance(body.get("data"), list) else []
        return ESTADO_OK, "", [n for n in (parsear_articulo(a) for a in datos) if n]

    def obtener(self, ctx: ContextoProveedor) -> ResultadoProveedor:
        # Ventana fija hacia atrás y no "desde la última noticia": las tandas rotan, así que un cursor global
        # haría perder lo que salió de una tanda mientras se consultaba otra. Lo repetido se descarta al
        # deduplicar.
        desde = datetime.utcnow() - timedelta(days=DIAS_VENTANA)
        comunes = {
            "language": "en,es", "group_similar": "true", "published_after": desde.strftime("%Y-%m-%dT%H:%M"),
            "limit": entero_env("MARKETAUX_ARTICULOS_POR_SOLICITUD", 3, 1, 100),
        }
        simbolos = sorted({s.simbolo.replace(".BA", "") for s in ctx.simbolos if s.simbolo})
        tandas = [simbolos[i:i + SIMBOLOS_POR_SOLICITUD] for i in range(0, len(simbolos), SIMBOLOS_POR_SOLICITUD)]
        presupuesto = max(0, ctx.solicitudes_disponibles)
        consultas: list[dict] = []
        rotacion = ctx.rotacion
        if tandas:
            # Una consulta queda reservada para la general de macro, salvo que el cupo sea de una sola.
            n_tandas = min(len(tandas), presupuesto - 1 if presupuesto > 1 else presupuesto)
            for k in range(n_tandas):
                tanda = tandas[(ctx.rotacion + k) % len(tandas)]
                consultas.append({**comunes, "symbols": ",".join(tanda), "filter_entities": "true"})
            rotacion = (ctx.rotacion + len(consultas)) % len(tandas)
        if len(consultas) < presupuesto:
            consultas.append({**comunes, "search": CONSULTA_MACRO})

        noticias: list[NoticiaCruda] = []
        gastadas = 0
        estado, mensaje = ESTADO_OK, ""
        for params in consultas:
            estado_c, mensaje_c, items = self._consultar(params)
            gastadas += 1
            noticias.extend(items)
            if estado_c != ESTADO_OK:
                estado, mensaje = (ESTADO_PARCIAL if noticias and estado_c == ESTADO_ERROR else estado_c), mensaje_c
                break
        cursor = max((n.fecha_publicacion for n in noticias), default=ctx.cursor)
        if estado == ESTADO_OK:
            mensaje = f"{len(noticias)} noticias en {gastadas} consultas"
        return ResultadoProveedor(estado=estado, mensaje=mensaje, noticias=noticias, solicitudes=gastadas,
                                  cursor=cursor, rotacion=rotacion)
