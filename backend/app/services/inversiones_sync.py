"""Valida las filas del Google Sheet de inversiones y reemplaza las tablas espejo."""
import unicodedata
from datetime import date, datetime
from dateutil import parser as dateutil_parser
from sqlalchemy.orm import Session

from ..database import InstrumentoInversion, MovimientoInversion, PrecioInstrumento, IndiceMercado, ObjetivoInversion, RebalanceoObjetivo, BenchmarkValor, ConfiguracionCartera
from .sheets_client import fetch_sheet_data, fetch_objetivos_tab, fetch_rebalanceo_tab, fetch_benchmarks_tab, fetch_configuracion_tab

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

EJES_REBALANCEO = {"cartera": "Cartera", "tipo": "Tipo", "sector": "Sector", "ticker": "Ticker"}


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
    objetivos_validos = _validar_objetivos(fetch_objetivos_tab(), errores)
    rebalanceo_validos = _validar_rebalanceo(fetch_rebalanceo_tab(), errores, tickers_conocidos)
    benchmarks_validos = _validar_benchmarks(fetch_benchmarks_tab(), errores)
    configuracion_validos = _validar_configuracion(fetch_configuracion_tab(), errores)

    indices_mercado, advertencias = _consolidar_indices_mercado(cer_mep_movimientos, cer_mep_precios, errores)
    errores.extend(advertencias)

    db.query(MovimientoInversion).delete()
    db.query(PrecioInstrumento).delete()
    db.query(InstrumentoInversion).delete()
    db.query(IndiceMercado).delete()
    db.query(ObjetivoInversion).delete()
    db.query(RebalanceoObjetivo).delete()
    db.query(BenchmarkValor).delete()
    db.query(ConfiguracionCartera).delete()
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

    for objetivo in objetivos_validos:
        db.add(ObjetivoInversion(**objetivo))

    for rebalanceo in rebalanceo_validos:
        db.add(RebalanceoObjetivo(**rebalanceo))

    for benchmark in benchmarks_validos:
        db.add(BenchmarkValor(**benchmark))

    for configuracion in configuracion_validos:
        db.add(ConfiguracionCartera(**configuracion))

    db.commit()

    global _ultimo_sync
    _ultimo_sync = datetime.utcnow()

    return {
        "movimientos": len(movimientos_validos),
        "instrumentos": len(instrumentos_validos),
        "precios": len(precios_validos),
        "objetivos": len(objetivos_validos),
        "rebalanceo": len(rebalanceo_validos),
        "indices_mercado": len(indices_mercado),
        "benchmarks": len(benchmarks_validos),
        "configuracion": len(configuracion_validos),
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

        objetivo_modo, objetivo_valor, error_objetivo = _parse_nivel_precio(
            row.get("Objetivo Modo"), row.get("Objetivo Valor")
        )
        if error_objetivo:
            errores.append({"fila": row_num, "motivo": f"Objetivo inválido: {error_objetivo}"})
            continue

        stop_loss_modo, stop_loss_valor, error_stop = _parse_nivel_precio(
            row.get("Stop Loss Modo"), row.get("Stop Loss Valor")
        )
        if error_stop:
            errores.append({"fila": row_num, "motivo": f"Stop Loss inválido: {error_stop}"})
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
            "objetivo_modo": objetivo_modo,
            "objetivo_valor": objetivo_valor,
            "stop_loss_modo": stop_loss_modo,
            "stop_loss_valor": stop_loss_valor,
        })
        tickers.add(ticker)
    return validos, tickers


def _parse_nivel_precio(modo_raw, valor_raw) -> tuple[str | None, float | None, str | None]:
    """Parsea un par (Modo, Valor) de precio objetivo/stop loss. Devuelve (modo, valor, error)."""
    modo = (modo_raw or "").strip()
    valor_str = (valor_raw or "").strip()
    tiene_modo = bool(modo) and modo.lower() != "nan"
    tiene_valor = bool(valor_str) and valor_str.lower() != "nan"

    if not tiene_modo and not tiene_valor:
        return None, None, None
    if tiene_modo != tiene_valor:
        return None, None, "Modo y Valor deben completarse juntos"

    modo_normalizado = modo.strip().capitalize()
    if modo_normalizado not in ("Porcentaje", "Fijo"):
        return None, None, f"Modo desconocido: {modo}"

    valor = _parse_numero(valor_str)
    if valor is None:
        return None, None, f"Valor numérico inválido: {valor_str}"

    return modo_normalizado, valor, None


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


def _validar_benchmarks(rows: list[tuple[int, dict]], errores: list[dict]) -> list[dict]:
    validos = []
    vistos: set[tuple[date, str]] = set()
    for row_num, row in rows:
        fecha_raw = (row.get("Fecha") or "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            errores.append({"fila": row_num, "motivo": f"Fecha inválida: {fecha_raw}"})
            continue

        benchmark = (row.get("Benchmark") or "").strip()
        if not benchmark:
            errores.append({"fila": row_num, "motivo": "Benchmark vacío"})
            continue

        valor_raw = (row.get("Valor") or "").strip()
        valor = _parse_numero(valor_raw)
        if valor is None:
            errores.append({"fila": row_num, "motivo": f"Valor inválido: {valor_raw}"})
            continue

        key = (fecha, benchmark)
        if key in vistos:
            errores.append({"fila": row_num, "motivo": f"Valor duplicado para {benchmark} en {fecha.isoformat()}"})
            continue
        vistos.add(key)

        validos.append({"fecha": fecha, "benchmark": benchmark, "valor": valor})

    return validos


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


def _validar_objetivos(rows: list[tuple[int, dict]], errores: list[dict]) -> list[dict]:
    validos = []
    carteras_vistas: set[str] = set()
    for row_num, row in rows:
        cartera = (row.get("Cartera") or "").strip()
        if not cartera:
            errores.append({"fila": row_num, "motivo": "Cartera vacía en Objetivos"})
            continue

        if cartera in carteras_vistas:
            errores.append({"fila": row_num, "motivo": f"Objetivo duplicado para cartera: {cartera}"})
            continue

        nombre = (row.get("Nombre") or "").strip()
        if not nombre:
            errores.append({"fila": row_num, "motivo": "Nombre vacío en Objetivos"})
            continue

        fecha_raw = (row.get("Fecha Límite") or row.get("Fecha Limite") or "").strip()
        fecha_limite = _parse_fecha(fecha_raw)
        if fecha_limite is None:
            errores.append({"fila": row_num, "motivo": f"Fecha Límite inválida: {fecha_raw}"})
            continue

        monto_raw = (row.get("Monto USD") or "").strip()
        monto_usd = _parse_numero(monto_raw)
        if monto_usd is None:
            errores.append({"fila": row_num, "motivo": f"Monto USD inválido: {monto_raw}"})
            continue

        icono = (row.get("Icono") or "").strip() or "🎯"

        validos.append({
            "cartera": cartera,
            "nombre": nombre,
            "icono": icono,
            "monto_usd": monto_usd,
            "fecha_limite": fecha_limite,
        })
        carteras_vistas.add(cartera)

    return validos


def _validar_rebalanceo(rows: list[tuple[int, dict]], errores: list[dict], tickers_conocidos: set[str]) -> list[dict]:
    validos = []
    seen: set[tuple[str | None, str, str]] = set()
    sumas: dict[tuple[str | None, str], float] = {}

    for row_num, row in rows:
        cartera_raw = (row.get("Cartera") or "").strip()
        cartera = None if not cartera_raw or _strip_accents(cartera_raw).lower() == "consolidado" else cartera_raw

        eje_raw = (row.get("Eje") or "").strip()
        eje = EJES_REBALANCEO.get(_strip_accents(eje_raw).lower())
        if eje is None:
            errores.append({"fila": row_num, "motivo": f"Eje desconocido en Rebalanceo: {eje_raw}"})
            continue

        if eje == "Cartera" and cartera is not None:
            errores.append({
                "fila": row_num,
                "motivo": "El eje 'Cartera' solo aplica a nivel Consolidado; dejá la columna Cartera vacía o escribí 'Consolidado'",
            })
            continue

        categoria = (row.get("Categoría") or row.get("Categoria") or "").strip()
        if not categoria:
            errores.append({"fila": row_num, "motivo": "Categoría vacía en Rebalanceo"})
            continue

        if eje == "Ticker" and categoria not in tickers_conocidos:
            errores.append({"fila": row_num, "motivo": f"Ticker desconocido en Rebalanceo: {categoria}"})
            continue

        porcentaje_raw = (row.get("Porcentaje Objetivo") or "").strip()
        porcentaje = _parse_numero(porcentaje_raw)
        if porcentaje is None or porcentaje < 0 or porcentaje > 100:
            errores.append({"fila": row_num, "motivo": f"Porcentaje Objetivo inválido: {porcentaje_raw}"})
            continue

        key = (cartera, eje, categoria)
        if key in seen:
            errores.append({
                "fila": row_num,
                "motivo": f"Objetivo de rebalanceo duplicado para {cartera or 'Consolidado'} / {eje} / {categoria}",
            })
            continue
        seen.add(key)

        grupo = (cartera, eje)
        sumas[grupo] = sumas.get(grupo, 0.0) + porcentaje

        validos.append({
            "cartera": cartera,
            "eje": eje,
            "categoria": categoria,
            "porcentaje_objetivo": porcentaje,
        })

    for (cartera, eje), suma in sumas.items():
        if suma > 100.5:
            errores.append({
                "fila": 0,
                "motivo": f"Advertencia: los objetivos de Rebalanceo para {cartera or 'Consolidado'} / {eje} suman {suma:.1f}% (>100%)",
            })

    return validos


def _validar_configuracion(rows: list[tuple[int, dict]], errores: list[dict]) -> list[dict]:
    """Valida la pestaña Configuracion (Cartera | Benchmark | Rendimiento Objetivo |
    Peso Máximo | Peso Mínimo | Tolerancia). Todos los campos salvo Cartera son opcionales:
    una fila puede tener sólo alguno de ellos completo ("no obligar a completar campos
    innecesarios")."""
    validos = []
    carteras_vistas: set[str | None] = set()

    for row_num, row in rows:
        cartera_raw = (row.get("Cartera") or "").strip()
        cartera = None if not cartera_raw or _strip_accents(cartera_raw).lower() == "consolidado" else cartera_raw

        if cartera in carteras_vistas:
            errores.append({
                "fila": row_num,
                "motivo": f"Configuración duplicada para cartera: {cartera or 'Consolidado'}",
            })
            continue

        benchmark = (row.get("Benchmark") or "").strip() or None

        def _campo_opcional(nombre_col: str, nombre_error: str) -> tuple[float | None, bool]:
            raw = (row.get(nombre_col) or "").strip()
            if not raw:
                return None, True
            valor = _parse_numero(raw)
            if valor is None:
                errores.append({"fila": row_num, "motivo": f"{nombre_error} inválido: {raw}"})
                return None, False
            return valor, True

        rendimiento_objetivo, ok1 = _campo_opcional("Rendimiento Objetivo", "Rendimiento Objetivo")
        peso_maximo, ok2 = _campo_opcional("Peso Máximo", "Peso Máximo")
        peso_minimo, ok3 = _campo_opcional("Peso Mínimo", "Peso Mínimo")
        tolerancia, ok4 = _campo_opcional("Tolerancia", "Tolerancia")
        if not (ok1 and ok2 and ok3 and ok4):
            continue

        if peso_maximo is not None and not (0 <= peso_maximo <= 100):
            errores.append({"fila": row_num, "motivo": f"Peso Máximo fuera de rango [0,100]: {peso_maximo}"})
            continue
        if peso_minimo is not None and not (0 <= peso_minimo <= 100):
            errores.append({"fila": row_num, "motivo": f"Peso Mínimo fuera de rango [0,100]: {peso_minimo}"})
            continue
        if peso_maximo is not None and peso_minimo is not None and peso_minimo > peso_maximo:
            errores.append({"fila": row_num, "motivo": f"Peso Mínimo ({peso_minimo}) mayor que Peso Máximo ({peso_maximo})"})
            continue
        if tolerancia is not None and tolerancia < 0:
            errores.append({"fila": row_num, "motivo": f"Tolerancia negativa: {tolerancia}"})
            continue

        validos.append({
            "cartera": cartera,
            "benchmark": benchmark,
            "rendimiento_objetivo": rendimiento_objetivo,
            "peso_maximo": peso_maximo,
            "peso_minimo": peso_minimo,
            "tolerancia": tolerancia,
        })
        carteras_vistas.add(cartera)

    return validos
