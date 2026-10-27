"""Importación estructurada de eventos (calendarios oficiales, catálogo semilla, archivos del usuario). Puro.

Para lo que no tiene una API estable —fechas de elecciones, reuniones de la Reserva Federal o del BCRA,
feriados, calendarios corporativos—, en vez de un scraper frágil se mantiene un archivo JSON con el formato
de abajo. Se lee de `EVENTOS_IMPORTACION_DIR` (default `/app/data/eventos_programados`, en el volumen de
datos) en cada sincronización, o se sube desde la pantalla. **Ninguna fecha futura vive en el código.**

Formato (un objeto `{"eventos": [...]}` o directamente la lista):

    {
      "id": "ar-elecciones-legislativas-2027",       // obligatorio, estable: identifica al evento
      "titulo": "Elecciones legislativas nacionales", // obligatorio
      "categoria": "elecciones",                     // obligatorio, una de CATEGORIAS
      "fecha": "2027-10-24",                          // obligatorio (AAAA-MM-DD)
      "url_fuente": "https://www.electoral.gob.ar/",  // obligatorio (http/https)
      "fecha_fin": null, "hora": "08:00", "zona_horaria": "America/Argentina/Buenos_Aires",
      "precision": "exacta",            // exacta | aproximada | mes | anio | desconocida
      "estado": "previsto",             // previsto | confirmado | ... (default según la fecha)
      "pais": "Argentina", "region": null, "importancia": 3,
      "descripcion": "...", "fuente": "Cámara Nacional Electoral",
      "verificacion": "fuente_oficial", // default: sin_verificar
      "programado": true,
      "entidades": {"organismos": ["CNE"]},
      "tickers": [{"ticker": "^MERV", "relacion": "indice", "relevancia": 0.5, "motivo": "Índice local"}]
    }

Volver a importar el mismo archivo no duplica nada: el `id` es la clave (por origen). Los campos que el
usuario corrigió desde la app no se pisan.
"""
from __future__ import annotations

import re
from datetime import date, time

from . import CATEGORIAS, ESTADOS, PRECISIONES, VERIFICACIONES
from . import normalizacion_engine as ne
from .eventos_analytics import normalizar_ticker
from .proveedores.base import EventoCrudo

MAX_EVENTOS = 2000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _fecha(valor) -> date | None:
    if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor.strip()):
        try:
            d = date.fromisoformat(valor.strip())
        except ValueError:
            return None
        return d if 1900 <= d.year <= 2100 else None
    return None


def parsear(datos, proveedor: str, origen: str, hoy: date) -> tuple[list[EventoCrudo], list[str]]:
    """`(eventos, errores)`. Un ítem inválido no frena al resto: queda en `errores` con su posición."""
    items = datos.get("eventos") if isinstance(datos, dict) else datos
    if not isinstance(items, list):
        return [], ["El archivo tiene que ser una lista de eventos o un objeto con la clave \"eventos\""]
    if len(items) > MAX_EVENTOS:
        return [], [f"Demasiados eventos en un archivo (máximo {MAX_EVENTOS})"]
    eventos: list[EventoCrudo] = []
    errores: list[str] = []
    vistos: set[str] = set()
    for i, it in enumerate(items, start=1):
        error, ev = _parsear_item(it, proveedor, origen, hoy)
        if error:
            errores.append(f"#{i}: {error}")
        elif ev.id_externo in vistos:
            errores.append(f"#{i}: id repetido «{ev.id_externo}»")
        else:
            vistos.add(ev.id_externo)
            eventos.append(ev)
    return eventos, errores


def _parsear_item(it, proveedor: str, origen: str, hoy: date) -> tuple[str | None, EventoCrudo | None]:
    if not isinstance(it, dict):
        return "no es un objeto", None
    ident = str(it.get("id") or "").strip()
    if not _ID.match(ident):
        return "falta un «id» válido (letras, números, . _ : -)", None
    titulo = ne.texto_plano(it.get("titulo"), ne.MAX_TITULO)
    if not titulo:
        return "falta el título", None
    if it.get("categoria") not in CATEGORIAS:
        return f"categoría inválida «{it.get('categoria')}»", None
    fecha = _fecha(it.get("fecha"))
    if fecha is None:
        return "falta la fecha (AAAA-MM-DD)", None
    if not ne.url_valida(it.get("url_fuente")):
        return "falta una url_fuente http/https válida", None
    fin = _fecha(it.get("fecha_fin")) if it.get("fecha_fin") else None
    if it.get("fecha_fin") and (fin is None or fin < fecha):
        return "fecha_fin inválida", None
    hora = None
    if it.get("hora"):
        if not isinstance(it["hora"], str) or not _HORA.match(it["hora"]):
            return "hora inválida (HH:MM)", None
        h, m = it["hora"].split(":")
        hora = time(int(h), int(m))
    precision = it.get("precision") or "exacta"
    if precision not in PRECISIONES:
        return f"precisión inválida «{precision}»", None
    estado = it.get("estado") or ("previsto" if fecha >= hoy else "concluido")
    if estado not in ESTADOS:
        return f"estado inválido «{estado}»", None
    verificacion = it.get("verificacion") or "sin_verificar"
    if verificacion not in VERIFICACIONES:
        return f"verificación inválida «{verificacion}»", None
    importancia = it.get("importancia")
    if importancia is not None and importancia not in (1, 2, 3):
        return "importancia inválida (1 a 3)", None
    zona = it.get("zona_horaria")
    if zona:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(zona)
        except Exception:
            return f"zona horaria inválida «{zona}»", None
    tickers = []
    for v in it.get("tickers") or []:
        if not isinstance(v, dict) or normalizar_ticker(v.get("ticker")) is None:
            return "algún ticker es inválido", None
        rel = v.get("relevancia", 0.5)
        if not isinstance(rel, (int, float)) or not 0 <= rel <= 1:
            return "relevancia inválida (0 a 1)", None
        tickers.append({
            "ticker": normalizar_ticker(v["ticker"]), "tipo_relacion": v.get("relacion") or "otra",
            "relevancia": float(rel), "justificacion": ne.texto_plano(v.get("motivo"), 300),
        })
    entidades = it.get("entidades") if isinstance(it.get("entidades"), dict) else {}
    entidades = {k: [ne.texto_plano(str(x), 120) for x in v if x][:30] for k, v in entidades.items()
                 if k in ("empresas", "organismos", "sectores", "terminos") and isinstance(v, list)}
    return None, EventoCrudo(
        proveedor=proveedor, id_externo=ident, titulo=titulo, categoria=it["categoria"], fecha_evento=fecha,
        origen=origen, descripcion=ne.texto_plano(it.get("descripcion"), 4000), fecha_fin=fin, hora_evento=hora,
        zona_horaria=zona or None, precision_fecha=precision, estado=estado,
        programado=bool(it.get("programado", fecha >= hoy)), pais=ne.texto_plano(it.get("pais"), 80),
        region=ne.texto_plano(it.get("region"), 80), importancia=importancia, verificacion=verificacion,
        fuente_principal=ne.texto_plano(it.get("fuente"), 200), url_fuente=it["url_fuente"].strip(),
        entidades=entidades, tickers=tickers,
    )
