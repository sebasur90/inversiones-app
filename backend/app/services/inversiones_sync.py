"""Valida las filas del Google Sheet de inversiones y reemplaza las tablas espejo."""
import unicodedata
from datetime import date, datetime
from dateutil import parser as dateutil_parser
from sqlalchemy.orm import Session

from ..database import InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado
from .sheets_client import fetch_sheet_data

# Estado en memoria del proceso: se resetea al reiniciar el backend.
_ultimo_sync: datetime | None = None


def get_ultimo_sync() -> datetime | None:
    return _ultimo_sync

TIPOS_MOVIMIENTO = {
    "compra": "compra",
    "venta": "venta",
    "dividendo": "dividendo",
    "cupon": "cupon",
    "renta": "dividendo",
    "amortizacion": "amortizacion",
}

MONEDAS_VALIDAS = ("ARS", "USD")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _normalize_tipo_movimiento(raw: str) -> str | None:
    key = _strip_accents(raw).strip().lower()
    return TIPOS_MOVIMIENTO.get(key)


def _parse_fecha(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    try:
        return dateutil_parser.parse(raw, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def _parse_numero(raw: str, es_indice: bool = False) -> float | None:
    """Parsea un número admitiendo notación ARS ("1.234,56") o US ("1,234.56").

    Cuando el número trae un único separador ("," o "."), es ambiguo: puede ser decimal
    ("1,5") o separador de miles ("1.519" = 1519). Con un solo "," se asume separador de
    miles si todos los grupos después tienen 3 dígitos (ej. "1,234" = 1234), igual para
    todos los campos. Con un solo "." eso solo se asume para CER/MEP (es_indice=True), ya
    que el Sheet los carga sin decimales (ej. "1.519" = 1519); para Cantidad/Precio/Comisión
    un "." aislado siempre se toma como decimal, porque esos campos pueden llevar
    legítimamente 3 decimales (ej. "1519.384").
    """
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace(" ", "").replace("$", "").replace("US$", "").replace("USD", "").replace("ARS", "")
    try:
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            partes = s.split(",")
            if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
        elif "." in s:
            partes = s.split(".")
            if es_indice and len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                s = s.replace(".", "")
        return float(s)
    except ValueError:
        return None


def sync_from_sheet(db: Session) -> dict:
    """Trae el Sheet completo y reemplaza las 3 tablas espejo. No toca la DB si falla la lectura."""
    data = fetch_sheet_data()

    errores: list[dict] = []

    instrumentos_validos, tickers_conocidos = _validar_instrumentos(data.get("Instrumentos", []), errores)
    movimientos_validos, cer_mep_movimientos = _validar_movimientos(data.get("Movimientos", []), tickers_conocidos, errores)
    precios_validos, cer_mep_precios = _validar_precios(data.get("Precios", []), errores)

    indices_mercado, advertencias = _consolidar_indices_mercado(cer_mep_movimientos, cer_mep_precios, errores)
    errores.extend(advertencias)

    db.query(MovimientoInversion).delete()
    db.query(PrecioInstrumento).delete()
    db.query(InstrumentoInversion).delete()
    db.query(IndiceMercado).delete()
    db.flush()

    for inst in instrumentos_validos:
        db.add(InstrumentoInversion(**inst))
    db.flush()

    for mov in movimientos_validos:
        db.add(MovimientoInversion(
            fecha=mov["fecha"],
            cartera=mov["cartera"],
            ticker=mov["ticker"],
            tipo_movimiento=mov["tipo_movimiento"],
            cantidad=mov["cantidad"],
            precio=mov["precio"],
            moneda=mov["moneda"],
            comision=mov["comision"],
        ))

    for precio in precios_validos:
        db.add(PrecioInstrumento(**precio))

    for indice in indices_mercado:
        db.add(IndiceMercado(**indice))

    db.commit()

    global _ultimo_sync
    _ultimo_sync = datetime.utcnow()

    return {
        "movimientos": len(movimientos_validos),
        "instrumentos": len(instrumentos_validos),
        "precios": len(precios_validos),
        "indices_mercado": len(indices_mercado),
        "errores": errores,
    }


def _validar_instrumentos(rows: list[tuple[int, dict]], errores: list[dict]) -> tuple[list[dict], set[str]]:
    validos = []
    tickers = set()
    for row_num, row in rows:
        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            errores.append({"fila": row_num, "motivo": "Ticker vacío en Instrumentos"})
            continue
        if ticker in tickers:
            errores.append({"fila": row_num, "motivo": f"Ticker duplicado en Instrumentos: {ticker}"})
            continue

        fecha_venc = None
        fecha_venc_raw = (row.get("Fecha Vencimiento") or "").strip()
        if fecha_venc_raw and fecha_venc_raw.lower() != "nan":
            fecha_venc = _parse_fecha(fecha_venc_raw)
            if fecha_venc is None:
                errores.append({"fila": row_num, "motivo": f"Fecha Vencimiento inválida: {fecha_venc_raw}"})
                continue

        validos.append({
            "ticker": ticker,
            "nombre": row.get("Nombre") or ticker,
            "tipo_instrumento": row.get("Tipo Instrumento") or "",
            "mercado": row.get("Mercado") or "",
            "moneda": (row.get("Moneda") or "").strip().upper(),
            "pais": row.get("País") or row.get("Pais") or None,
            "sector": row.get("Sector") or None,
            "fecha_vencimiento": fecha_venc,
        })
        tickers.add(ticker)
    return validos, tickers


def _validar_movimientos(rows: list[tuple[int, dict]], tickers_conocidos: set[str], errores: list[dict]) -> tuple[list[dict], list[dict]]:
    parsed = []
    cer_mep_datos = []
    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            errores.append({"fila": row_num, "motivo": f"Fecha inválida: {fecha_raw}"})
            continue

        cartera = (row.get("Cartera") or "").strip()
        if not cartera:
            errores.append({"fila": row_num, "motivo": "Cartera vacía"})
            continue

        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            errores.append({"fila": row_num, "motivo": "Ticker vacío"})
            continue

        tipo_raw = (row.get("Tipo Movimiento") or "").strip()
        tipo = _normalize_tipo_movimiento(tipo_raw)
        if tipo is None:
            errores.append({"fila": row_num, "motivo": f"Tipo Movimiento inválido: {tipo_raw}"})
            continue

        cantidad_raw = (row.get("Cantidad") or "").strip()
        cantidad = None
        if cantidad_raw:
            cantidad = _parse_numero(cantidad_raw)
            if cantidad is None:
                errores.append({"fila": row_num, "motivo": f"Cantidad inválida: {cantidad_raw}"})
                continue
        elif tipo in ("compra", "venta", "amortizacion"):
            errores.append({"fila": row_num, "motivo": "Cantidad requerida para este tipo de movimiento"})
            continue

        precio_raw = (row.get("Precio") or "").strip()
        precio = _parse_numero(precio_raw)
        if precio is None:
            errores.append({"fila": row_num, "motivo": f"Precio inválido: {precio_raw}"})
            continue

        moneda = (row.get("Moneda") or "").strip().upper()
        if moneda not in MONEDAS_VALIDAS:
            errores.append({"fila": row_num, "motivo": f"Moneda inválida: {moneda}"})
            continue

        comision_raw = (row.get("Comisión") or row.get("Comision") or "").strip()
        comision = 0.0
        if comision_raw:
            parsed_comision = _parse_numero(comision_raw)
            if parsed_comision is None:
                errores.append({"fila": row_num, "motivo": f"Comisión inválida: {comision_raw}"})
                continue
            comision = parsed_comision

        cer_raw = (row.get("CER") or "").strip()
        cer = None
        if cer_raw:
            cer = _parse_numero(cer_raw, es_indice=True)

        mep_raw = (row.get("MEP") or "").strip()
        mep = None
        if mep_raw:
            mep = _parse_numero(mep_raw, es_indice=True)

        if cer or mep:
            cer_mep_datos.append({"fecha": fecha, "cer": cer, "mep": mep})

        if ticker not in tickers_conocidos:
            errores.append({"fila": row_num, "motivo": f"Advertencia: ticker '{ticker}' sin ficha en Instrumentos, queda sin clasificar"})

        parsed.append({
            "row_num": row_num,
            "fecha": fecha,
            "cartera": cartera,
            "ticker": ticker,
            "tipo_movimiento": tipo,
            "cantidad": cantidad,
            "precio": precio,
            "moneda": moneda,
            "comision": comision,
        })

    # Validar tenencia no negativa procesando en orden cronológico por (cartera, ticker)
    parsed.sort(key=lambda m: (m["fecha"], m["row_num"]))
    tenencias: dict[tuple[str, str], float] = {}
    validos = []
    for mov in parsed:
        key = (mov["cartera"], mov["ticker"])
        actual = tenencias.get(key, 0.0)
        if mov["tipo_movimiento"] == "compra":
            actual += mov["cantidad"] or 0.0
        elif mov["tipo_movimiento"] in ("venta", "amortizacion"):
            cant = mov["cantidad"] or 0.0
            if cant - actual > 1e-6:
                errores.append({
                    "fila": mov["row_num"],
                    "motivo": (
                        f"Tenencia insuficiente para {mov['tipo_movimiento']} de {mov['ticker']} "
                        f"en '{mov['cartera']}' ({cant} > {actual})"
                    ),
                })
                continue
            actual -= cant
        tenencias[key] = actual
        validos.append(mov)

    return validos, cer_mep_datos


def _validar_precios(rows: list[tuple[int, dict]], errores: list[dict]) -> tuple[list[dict], list[dict]]:
    validos = []
    vistos: set[tuple[date, str]] = set()
    cer_mep_datos = []
    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            errores.append({"fila": row_num, "motivo": f"Fecha inválida: {fecha_raw}"})
            continue

        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            errores.append({"fila": row_num, "motivo": "Ticker vacío en Precios"})
            continue

        precio_raw = (row.get("Precio") or "").strip()
        precio = _parse_numero(precio_raw)
        if precio is None:
            errores.append({"fila": row_num, "motivo": f"Precio inválido: {precio_raw}"})
            continue

        moneda = (row.get("Moneda") or "").strip().upper()
        if moneda not in MONEDAS_VALIDAS:
            errores.append({"fila": row_num, "motivo": f"Moneda inválida: {moneda}"})
            continue

        cer_raw = (row.get("CER") or "").strip()
        cer = None
        if cer_raw:
            cer = _parse_numero(cer_raw, es_indice=True)

        mep_raw = (row.get("MEP") or "").strip()
        mep = None
        if mep_raw:
            mep = _parse_numero(mep_raw, es_indice=True)

        if cer or mep:
            cer_mep_datos.append({"fecha": fecha, "cer": cer, "mep": mep})

        key = (fecha, ticker)
        if key in vistos:
            errores.append({"fila": row_num, "motivo": f"Precio duplicado para {ticker} en {fecha.isoformat()}"})
            continue
        vistos.add(key)

        validos.append({"fecha": fecha, "ticker": ticker, "precio": precio, "moneda": moneda})

    return validos, cer_mep_datos


def _consolidar_indices_mercado(cer_mep_movimientos: list[dict], cer_mep_precios: list[dict], errores: list[dict]) -> tuple[list[dict], list[dict]]:
    """Consolida CER/MEP de Movimientos y Precios por fecha, resolviendo conflictos."""
    indices_por_fecha: dict[date, dict] = {}
    advertencias: list[dict] = []

    # Procesar Movimientos primero, luego Precios
    for item in cer_mep_movimientos + cer_mep_precios:
        fecha = item["fecha"]
        cer = item.get("cer")
        mep = item.get("mep")

        if fecha not in indices_por_fecha:
            indices_por_fecha[fecha] = {"fecha": fecha, "cer": cer, "mep": mep}
        else:
            existente = indices_por_fecha[fecha]
            # Si hay conflicto en CER, usar el último y advertir
            if cer is not None and existente["cer"] is not None and abs(cer - existente["cer"]) > 1e-6:
                advertencias.append({
                    "fila": 0,  # No tenemos número de fila aquí
                    "motivo": f"CER inconsistente para {fecha.isoformat()}, se usó el último valor cargado"
                })
            if cer is not None:
                existente["cer"] = cer

            # Si hay conflicto en MEP, usar el último y advertir
            if mep is not None and existente["mep"] is not None and abs(mep - existente["mep"]) > 1e-6:
                advertencias.append({
                    "fila": 0,
                    "motivo": f"MEP inconsistente para {fecha.isoformat()}, se usó el último valor cargado"
                })
            if mep is not None:
                existente["mep"] = mep

    return list(indices_por_fecha.values()), advertencias
