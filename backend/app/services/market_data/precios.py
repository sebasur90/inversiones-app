"""Precios automáticos de renta fija (bonos soberanos, ONs, letras/LECAPs), renta variable
(acciones, CEDEARs) y FCI.

IOL es la fuente **primaria**: `fetch_precios_api`/`fetch_backfill_api` intentan IOL primero (los
paneles de `market_data.iol` traen docenas de símbolos por llamada) y sólo caen a data912/
analisistecnico —las fuentes públicas sin auth, ver `fetch_precios_renta_fija_api` y hermanas más
abajo— para los símbolos que IOL no cotizó (caída, sin cupo mensual, o no tiene ese ticker).
El Sheet sigue siendo necesario para lo que ninguna API cotiza: fondos propios, instrumentos
ilíquidos, etc.

Reglas comunes a todas las fuentes automáticas ('iol' y 'api'): sólo agregan el precio para
tickers que
  1. existen en la pestaña Instrumentos del Sheet,
  2. tienen al menos un precio manual previo en la pestaña Precios (necesario para calibrar la
     escala — ver abajo), y
  3. no tienen precio manual cargado para hoy (a nivel de `(ticker, fecha)`; qué pasa cuando IOL
     sí cotiza una fecha que el Sheet ya cubre —IOL puede desplazar al Sheet— se decide en
     `inversiones_sync.py`, no acá).

Escala: IOL y data912 cotizan la renta fija ARS por lámina de 100 VN y el Sheet la carga por 1 VN
(factor 100); para renta variable no hay una convención de lámina documentada, así que se aplica
el mismo tratamiento sin asumir 1:1. En ambos casos no se asume el factor a ciegas: para cada
ticker se compara la cotización de la API contra el último precio manual del Sheet y se aplica
1/100 si el ratio cae cerca de 100, o 1 si cae cerca de 1. Cualquier otro ratio -> no se carga y
se reporta (elección del usuario: "normalizar por ratio observado", 2026-08-28).

Backfill histórico: analisistecnico cubre renta fija soberana/letras (no ONs); IOL se usa además
para lo que analisistecnico no cubre (ONs, renta variable) — ver `fetch_backfill_iol`.
"""
from datetime import date, timedelta
from unicodedata import combining, normalize

from ...database import BarraOHLCV
from ..ohlcv_analytics import clave_serie
from ..validation.types import Severity, ValidationIssue
from . import analisistecnico, data912, yahoo
from . import iol as iol_client
from .ohlcv_types import BarraCruda

# `tipo_instrumento` en el Sheet es texto libre; se matchea por familia, sin acentos ni mayúsculas.
# Subcadenas inequívocas...
_SUBCADENAS_RENTA_FIJA = ("bono", "boncer", "obligacion negociable", "letra", "lecap", "lede")
# ...y tokens sueltos (para no confundir "ON" con la "on" de "accion" / "bono").
_TOKENS_RENTA_FIJA = {"on", "ons"}
# Renta variable (Ola 4): ninguna de las dos subcadenas aparece dentro de otra palabra del
# dominio, no hace falta el tratamiento por tokens sueltos de renta fija.
_SUBCADENAS_RENTA_VARIABLE = ("accion", "cedear")
# FCI: IOL expone todos los fondos en una sola llamada (`Titulos/FCI`); "fci" no es subcadena de
# ninguna palabra usada en las otras dos familias.
_SUBCADENAS_FCI = ("fci", "fondo comun de inversion")

# Ventanas de tolerancia alrededor de los dos factores de escala plausibles (1:1 y 1:100).
_RATIO_CERCA_DE_100 = (40.0, 250.0)
_RATIO_CERCA_DE_1 = (0.4, 2.5)

# Backfill histórico (soberanos/letras/CER vía analisistecnico; las ONs no tienen fuente).
_TOPE_BACKFILL = timedelta(days=366 * 5)   # piso duro: nunca más de ~5 años hacia atrás
_TOLERANCIA_PISO_DIAS = 40                 # "ya llegué al piso" si la serie 'api' arranca a <=40d de él
_MAX_BACKFILL_POR_SYNC = 15               # cota de peticiones por corrida (se atienden los huecos más grandes primero)
_REINTENTO_SIN_SERIE_DIAS = 90            # A3: un ticker sin serie histórica se reintenta cada ~90 días

# OHLCV (análisis técnico): piso más ancho que el de valuación (alcanza para una MM200 aunque el
# ticker se haya comprado hace poco) y cupo propio para el backfill de velas de la watchlist, que
# sí gasta llamadas HTTP nuevas (a diferencia del de cartera, que viaja gratis en la respuesta que
# ya se pide para valuación).
_PISO_TECNICO = timedelta(days=366 * 2)
_MAX_BACKFILL_OHLCV_POR_SYNC = 8


def _aplicar_factor_ohlcv(barra: BarraCruda, factor: float) -> BarraCruda:
    """Escala `o/h/l/c` por el mismo factor — nunca el volumen, que es nominal. Invariante: si
    `mínimo <= min(apertura, cierre)` y `máximo >= max(apertura, cierre)` antes de escalar, se
    preserva después (escalar sólo el cierre, el bug clásico, rompe la vela visualmente)."""
    return BarraCruda(
        fecha=barra.fecha,
        cierre=round(barra.cierre * factor, 6),
        apertura=round(barra.apertura * factor, 6) if barra.apertura is not None else None,
        maximo=round(barra.maximo * factor, 6) if barra.maximo is not None else None,
        minimo=round(barra.minimo * factor, 6) if barra.minimo is not None else None,
        volumen=barra.volumen,
    )


def _sin_acentos(s: str) -> str:
    return "".join(c for c in normalize("NFD", s) if not combining(c)).lower().strip()


def _factor_escala(px_api: float, px_sheet: float) -> float | None:
    """0.01 si `px_api` está ~100x sobre el precio del Sheet (data912/analisistecnico cotizan por
    lámina de 100 VN), 1.0 si están a la par, None si el ratio no cae cerca de ninguno de los dos."""
    if px_api <= 0 or px_sheet <= 0:
        return None
    ratio = px_api / px_sheet
    if _RATIO_CERCA_DE_100[0] <= ratio <= _RATIO_CERCA_DE_100[1]:
        return 0.01
    if _RATIO_CERCA_DE_1[0] <= ratio <= _RATIO_CERCA_DE_1[1]:
        return 1.0
    return None


def _es_renta_fija(tipo_instrumento: str) -> bool:
    t = _sin_acentos(tipo_instrumento or "")
    if any(sub in t for sub in _SUBCADENAS_RENTA_FIJA):
        return True
    tokens = set(t.replace("/", " ").replace("-", " ").split())
    return bool(tokens & _TOKENS_RENTA_FIJA)


def _es_renta_variable(tipo_instrumento: str) -> bool:
    t = _sin_acentos(tipo_instrumento or "")
    return any(sub in t for sub in _SUBCADENAS_RENTA_VARIABLE)


def _es_cedear(tipo_instrumento: str) -> bool:
    """Un CEDEAR: el ticker local *es* el del subyacente por construcción, así que la resolución
    automática del subyacente es segura (no hace falta match de nombre)."""
    return "cedear" in _sin_acentos(tipo_instrumento or "")


def _es_fci(tipo_instrumento: str) -> bool:
    t = _sin_acentos(tipo_instrumento or "")
    return any(sub in t for sub in _SUBCADENAS_FCI)


def _resolver_factor(
    ticker: str,
    px_api: float,
    px_sheet: float,
    f_sheet: date,
    estado_por_ticker: dict[str, dict] | None,
) -> tuple[float | None, bool]:
    """Devuelve `(factor, calibrado_ahora)`.

    A1: si hay un `factor_escala` persistido para el ticker se reusa tal cual, salvo que haya
    aparecido un precio manual más nuevo que `factor_fecha` (referencia fresca → se revalida).
    Si no hay factor guardado se calibra por ratio contra el último precio manual (como siempre)
    y, cuando `estado_por_ticker` está disponible, se persiste."""
    est = estado_por_ticker.get(ticker) if estado_por_ticker is not None else None
    guardado = est.get("factor_escala") if est else None
    factor_fecha = est.get("factor_fecha") if est else None
    manual_mas_nuevo = factor_fecha is None or f_sheet > factor_fecha

    if guardado is not None and not manual_mas_nuevo:
        return float(guardado), False

    factor = _factor_escala(px_api, px_sheet)
    if factor is not None and estado_por_ticker is not None:
        entry = estado_por_ticker.setdefault(ticker, {})
        entry["factor_escala"] = factor
        entry["factor_fecha"] = f_sheet
    return factor, True


def _issue_moneda_difiere(ticker: str, moneda_sheet: str, moneda_inst: str) -> ValidationIssue | None:
    """A2: la fila 'api' se calibra y persiste en la moneda de la serie de Precios (contra la que
    se calibró el número), no en la declarada en Instrumentos. Si difieren, es un dato a revisar."""
    ms = (moneda_sheet or "").strip().upper()
    mi = (moneda_inst or "").strip().upper()
    if ms and mi and ms != mi:
        return ValidationIssue(
            tab="Precios (API)", campo=ticker, regla="moneda_sheet_difiere_instrumento",
            mensaje=(f"{ticker}: la serie de Precios está en {ms} pero Instrumentos lo declara "
                     f"en {mi}; la fila automática se guarda en {ms} (la escala se calibró contra esa serie)"),
            impacto="Revisar la moneda declarada del instrumento o la carga en la pestaña Precios",
            severidad=Severity.INFO,
        )
    return None


def _fetch_precios_live_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    hoy: date,
    predicate,
    fetch_fn,
    endpoints_label: str,
    estado_por_ticker: dict[str, dict] | None = None,
    nombre_fuente: str = "data912",
) -> tuple[list[dict] | None, list[ValidationIssue]]:
    """Motor común de `fetch_precios_renta_fija_api` y `fetch_precios_renta_variable_api`: matchea
    instrumentos por `predicate`, pide el precio del día con `fetch_fn` y calibra la escala contra
    el último precio del Sheet. Devuelve (filas, issues); `filas` son dicts listos para
    `PrecioInstrumento(**fila)` con `fuente="api"`. Devuelve None (no []) si la API no respondió en
    absoluto, para que el sync preserve las filas 'api' de una corrida anterior.

    `estado_por_ticker` (opcional): ticker -> dict con `factor_escala`/`factor_fecha` persistidos.
    Se muta in place con las (re)calibraciones para que el llamador las guarde (ver A1).

    `nombre_fuente`: de dónde salió `fetch_fn`, sólo para redactar los issues. El motor también lo
    usa IOL (ver `_fetch_precios_encadenado`), así que no puede quedar 'data912' hardcodeado en los
    mensajes: el usuario tiene que poder distinguir qué fuente disparó cada advertencia.
    """
    issues: list[ValidationIssue] = []

    objetivo = [i for i in instrumentos if predicate(i.get("tipo_instrumento", ""))]
    if not objetivo:
        return [], issues

    api_por_symbol = fetch_fn()
    if api_por_symbol is None:
        issues.append(ValidationIssue(
            tab="Precios (API)", regla="data912_no_disponible",
            mensaje=f"No se pudieron obtener precios de {endpoints_label} de {nombre_fuente}",
            impacto="Se mantiene el último precio automático guardado, si existía",
            severidad=Severity.ADVERTENCIA,
        ))
        return None, issues

    api_por_symbol = {sym.upper().strip(): px for sym, px in api_por_symbol.items()}

    ultimo_sheet: dict[str, tuple[date, float, str]] = {}
    for p in precios_sheet:
        t, f, px = p["ticker"], p["fecha"], float(p["precio"])
        if t not in ultimo_sheet or f > ultimo_sheet[t][0]:
            ultimo_sheet[t] = (f, px, p.get("moneda") or "")

    filas: list[dict] = []
    for inst in objetivo:
        ticker = inst["ticker"]
        if (ticker, hoy) in claves_excluir:
            continue  # el Sheet ya trae precio de hoy para este ticker

        px_api = api_por_symbol.get(ticker.upper().strip())
        if px_api is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="ticker_no_mapeado",
                mensaje=f"{ticker}: sin cotización en {nombre_fuente} ({endpoints_label})",
                impacto="Se sigue usando el precio manual del Sheet para este instrumento",
                severidad=Severity.INFO,
            ))
            continue

        prev = ultimo_sheet.get(ticker)
        if prev is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="sin_precio_para_calibrar",
                mensaje=(f"{ticker}: hay cotización en {nombre_fuente} pero no hay precio previo "
                         "en el Sheet para calibrar la escala"),
                impacto="No se carga el precio automático hasta tener una referencia manual",
                severidad=Severity.INFO,
            ))
            continue

        f_sheet, px_sheet, moneda_sheet = prev
        if px_sheet <= 0 or px_api <= 0:
            continue
        factor, calibrado_ahora = _resolver_factor(ticker, px_api, px_sheet, f_sheet, estado_por_ticker)
        if factor is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="escala_desconocida",
                mensaje=(f"{ticker}: {nombre_fuente} cotiza {px_api:g} y el último precio del "
                         f"Sheet es {px_sheet:g} (factor {px_api / px_sheet:.2f}, fuera de ~1 o ~100)"),
                impacto="No se carga el precio automático de este instrumento",
                severidad=Severity.ADVERTENCIA,
            ))
            continue

        issue_moneda = _issue_moneda_difiere(ticker, moneda_sheet, inst.get("moneda", ""))
        if issue_moneda is not None:
            issues.append(issue_moneda)

        filas.append({
            "fecha": hoy,
            "ticker": ticker,
            "precio": round(px_api * factor, 6),
            "moneda": (moneda_sheet or inst.get("moneda") or "ARS").strip().upper(),
            "fuente": "api",
        })

    return filas, issues


def fetch_precios_renta_fija_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
) -> tuple[list[dict] | None, list[ValidationIssue]]:
    """`instrumentos` / `precios_sheet`: los dicts ya validados del Sheet (mismo formato que
    persiste el sync). `claves_excluir`: pares (ticker, fecha) que ya trae el Sheet."""
    return _fetch_precios_live_api(
        instrumentos, precios_sheet, claves_excluir, hoy or date.today(),
        _es_renta_fija, data912.fetch_precios_renta_fija, "arg_bonds/arg_corp/arg_notes",
        estado_por_ticker,
    )


def fetch_precios_renta_variable_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
) -> tuple[list[dict] | None, list[ValidationIssue]]:
    """Ídem `fetch_precios_renta_fija_api` para acciones y CEDEARs (Ola 4). Sin backfill
    histórico: no hay fuente pública de serie diaria para renta variable, sólo el precio del día
    vía data912 `/live/arg_stocks` + `/live/arg_cedears`."""
    return _fetch_precios_live_api(
        instrumentos, precios_sheet, claves_excluir, hoy or date.today(),
        _es_renta_variable, data912.fetch_precios_renta_variable, "arg_stocks/arg_cedears",
        estado_por_ticker,
    )


def fetch_backfill_renta_fija_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    primeras_fechas_mov: dict[str, date],
    api_existentes_por_ticker: dict[str, date],
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
    ohlcv_existentes: dict[str, date] | None = None,
    barras_out: list[dict] | None = None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Puebla *hacia atrás* la serie `precios_instrumento` (`fuente='api'`) de renta fija con la
    serie diaria de analisistecnico. Complementa a `fetch_precios_renta_fija_api`, que sólo agrega
    el precio del día: sin esto la serie automática nunca tiene historia previa a que se prendiera
    `USE_EXTERNAL_APIS`.

    Se auto-limita: por cada ticker se baja hasta `piso = max(primer movimiento, hoy - 5 años)`, y
    no se vuelve a pedir la serie una vez que las filas `fuente='api'` ya llegan a ~el piso. Sólo
    se emiten fechas < hoy que el Sheet no cubra (el día de hoy lo maneja la ruta 'live').

    `primeras_fechas_mov`: ticker -> fecha del primer Movimiento (define el piso; sin movimientos
    no hay posición que valuar y se saltea). `api_existentes_por_ticker`: ticker -> fecha más
    antigua que ya tiene con `fuente='api'` (para la convergencia). Devuelve `(filas, issues)`;
    `filas` es siempre una lista (nunca None): un fallo puntual sólo se reintenta el próximo sync.

    `estado_por_ticker` (opcional, A1/A3): ticker -> dict con `factor_escala`/`factor_fecha` y
    `backfill_estado`/`backfill_intento`. Se muta in place. Un ticker marcado `'sin_serie'`,
    `'sin_serie_iol'` o `'completo'` no vuelve a consumir cupo (los dos `'sin_serie*'` se
    reintentan cada ~90 días). `'sin_serie_iol'` lo escribe `fetch_backfill_iol` *después* de esta
    función sobre el mismo ticker y también implica "analisistecnico no lo cubre": si no se lo
    tratara igual que `'sin_serie'`, el par de funciones se reintentaría mutuamente en cada sync
    (una reescribe el estado que gatea a la otra) y la cota de A3 no frenaría nunca.

    ONs corporativas: analisistecnico no las tiene (`fetch_historico_ohlcv` -> None). Se marcan
    `'sin_serie'` y se reporta un SyncIssue info **una sola vez** — siguen con la serie
    forward-only y su historia manual del Sheet.

    `ohlcv_existentes` / `barras_out` (opcionales, OHLCV): `ohlcv_existentes` es
    ticker -> fecha más antigua ya en `serie_ohlcv`; `barras_out` es una lista mutada in place con
    las barras derivadas de la MISMA respuesta que ya se pide para valuación — cero llamadas HTTP
    nuevas. Con `barras_out` presente, el rango pedido se amplía a `_PISO_TECNICO` (2 años) aunque
    el piso de valuación sea más corto (para tener suficiente historia para una MM200); sólo las
    fechas >= piso de valuación se emiten a `precios_instrumento`, a `barras_out` va el rango
    completo. **Regla de primer llenado**: un ticker con `backfill_estado == 'completo'` igual se
    vuelve a pedir si todavía no tiene ninguna fila en `serie_ohlcv` — si no, un ticker cuya
    valuación ya había convergido antes de que existiera esta feature jamás tendría velas.
    Gateado por `ohlcv_intento` (no por `backfill_intento`), para no interferir con la
    convergencia de valuación existente.
    """
    issues: list[ValidationIssue] = []
    hoy = hoy or date.today()
    ayer = hoy - timedelta(days=1)

    objetivo = [i for i in instrumentos if _es_renta_fija(i.get("tipo_instrumento", ""))]
    if not objetivo:
        return [], issues

    ultimo_sheet: dict[str, tuple[date, float, str]] = {}
    for p in precios_sheet:
        t, f, px = p["ticker"], p["fecha"], float(p["precio"])
        if t not in ultimo_sheet or f > ultimo_sheet[t][0]:
            ultimo_sheet[t] = (f, px, p.get("moneda") or "")

    # Qué tickers necesitan backfill y cuánto; se atienden los huecos más grandes primero.
    pendientes: list[tuple[int, dict, date, date]] = []
    for inst in objetivo:
        ticker = inst["ticker"]
        piso = primeras_fechas_mov.get(ticker)
        if piso is None:
            continue
        piso = max(piso, hoy - _TOPE_BACKFILL)
        piso_fetch = min(piso, hoy - _PISO_TECNICO) if barras_out is not None else piso

        ya = api_existentes_por_ticker.get(ticker)
        valuacion_convergida = ya is not None and ya <= piso + timedelta(days=_TOLERANCIA_PISO_DIAS)
        necesita_ohlcv = barras_out is not None and (ohlcv_existentes or {}).get(ticker) is None

        if valuacion_convergida and not necesita_ohlcv:
            continue  # la serie 'api' ya cubre hasta ~el piso y no hace falta poblar OHLCV

        est = estado_por_ticker.get(ticker) if estado_por_ticker is not None else None
        if est is not None:
            bf = est.get("backfill_estado")
            if bf == "completo":
                if not necesita_ohlcv:
                    continue  # A3: la serie histórica ya no baja más, no gastar cupo
                intento_ohlcv = est.get("ohlcv_intento")
                if intento_ohlcv is not None and (hoy - intento_ohlcv).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue  # regla de primer llenado, gateada por su propio cooldown
            elif bf in ("sin_serie", "sin_serie_iol"):
                intento = est.get("backfill_intento")
                if intento is None or (hoy - intento).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue  # A3: la fuente no lo cubre; se reintenta recién a los ~90 días

        hueco = (ya - piso).days if ya is not None else 10 ** 6
        pendientes.append((hueco, inst, piso, piso_fetch))

    pendientes.sort(key=lambda x: x[0], reverse=True)

    filas: list[dict] = []
    for _, inst, piso, piso_fetch in pendientes[:_MAX_BACKFILL_POR_SYNC]:
        ticker = inst["ticker"]
        ya = api_existentes_por_ticker.get(ticker)
        est_entry = estado_por_ticker.setdefault(ticker, {}) if estado_por_ticker is not None else None
        serie = analisistecnico.fetch_historico_ohlcv(ticker, piso_fetch, ayer)

        if serie is None:
            ya_reportado = est_entry is not None and est_entry.get("backfill_estado") == "sin_serie"
            if est_entry is not None:
                est_entry["backfill_estado"] = "sin_serie"
                est_entry["backfill_intento"] = hoy
            if not ya_reportado:
                issues.append(ValidationIssue(
                    tab="Precios (API)", campo=ticker, regla="sin_historico_backfill",
                    mensaje=(f"{ticker}: sin serie histórica en analisistecnico "
                             "(ON corporativa u otro instrumento no listado)"),
                    impacto=("La serie automática de este instrumento sólo crece hacia adelante; su "
                             "historia previa queda con lo cargado a mano en el Sheet"),
                    severidad=Severity.INFO,
                ))
            continue

        if est_entry is not None:
            est_entry["backfill_intento"] = hoy
            if est_entry.get("backfill_estado") in ("sin_serie", "sin_serie_iol"):
                est_entry["backfill_estado"] = None  # la fuente empezó a cubrirlo
            if barras_out is not None:
                est_entry["ohlcv_intento"] = hoy
        if not serie:
            continue

        prev = ultimo_sheet.get(ticker)
        if prev is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="sin_precio_para_calibrar",
                mensaje=(f"{ticker}: hay serie histórica pero no hay precio manual en el Sheet "
                         "para calibrar la escala"),
                impacto="No se hace backfill hasta tener una referencia manual",
                severidad=Severity.INFO,
            ))
            continue

        f_sheet, px_sheet, moneda_sheet = prev
        if px_sheet <= 0:
            continue

        # Sólo las barras >= piso de valuación importan para precios_instrumento y para calibrar
        # (si `barras_out` amplió el rango, las más viejas quedan fuera de esta selección).
        serie_valuacion = [b for b in serie if b.fecha >= piso]
        candidatos_ref = serie_valuacion or serie
        # Calibra contra el cierre de analisistecnico más cercano a la última fecha del Sheet.
        px_ref = min(candidatos_ref, key=lambda b: abs((b.fecha - f_sheet).days)).cierre
        factor, _ = _resolver_factor(ticker, px_ref, px_sheet, f_sheet, estado_por_ticker)
        if factor is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="escala_desconocida",
                mensaje=(f"{ticker}: analisistecnico cotiza {px_ref:g} cerca del {f_sheet} y el "
                         f"Sheet {px_sheet:g} (factor {px_ref / px_sheet:.2f}, fuera de ~1 o ~100)"),
                impacto="No se hace backfill de este instrumento",
                severidad=Severity.ADVERTENCIA,
            ))
            continue

        issue_moneda = _issue_moneda_difiere(ticker, moneda_sheet, inst.get("moneda", ""))
        if issue_moneda is not None:
            issues.append(issue_moneda)

        moneda = (moneda_sheet or inst.get("moneda") or "ARS").strip().upper()
        for b in serie_valuacion:
            if b.fecha >= hoy or (ticker, b.fecha) in claves_excluir:
                continue
            filas.append({
                "fecha": b.fecha,
                "ticker": ticker,
                "precio": round(b.cierre * factor, 6),
                "moneda": moneda,
                "fuente": "api",
            })

        if barras_out is not None:
            for b in serie:
                if b.fecha >= hoy:
                    continue
                escalada = _aplicar_factor_ohlcv(b, factor)
                barras_out.append({
                    "ticker": ticker, "fecha": escalada.fecha,
                    "apertura": escalada.apertura, "maximo": escalada.maximo, "minimo": escalada.minimo,
                    "cierre": escalada.cierre, "volumen": escalada.volumen,
                    "moneda": moneda, "fuente": "api",
                })
            if est_entry is not None:
                ya_ohlcv = (ohlcv_existentes or {}).get(ticker)
                min_serie_full = min((b.fecha for b in serie), default=None)
                if ya_ohlcv is not None and min_serie_full is not None and min_serie_full >= ya_ohlcv:
                    est_entry["ohlcv_estado"] = "completo"

        # A3: convergencia por "ya no baja más" — si la fecha más vieja devuelta no mejora
        # respecto de lo que ya hay en la DB, la serie no va a crecer hacia atrás: marcar completo.
        # Acotada al piso de valuación: no se toca por la ampliación de rango de OHLCV.
        min_serie = min((b.fecha for b in serie_valuacion), default=None)
        if est_entry is not None and ya is not None and min_serie is not None and min_serie >= ya:
            est_entry["backfill_estado"] = "completo"

    return filas, issues


# --- IOL como fuente primaria: paneles primero, data912/analisistecnico como red de contención --


def _fetch_precios_encadenado(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    hoy: date,
    predicate,
    fetch_iol_fn,
    fetch_fallback_fn,
    endpoints_label: str,
    familia_label: str,
    estado_por_ticker: dict[str, dict] | None = None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Precio del día para una familia (`predicate`): IOL primero, data912 sólo para los símbolos
    que IOL no cotizó (caída, sin cupo mensual, o no tiene ese ticker). Reusa el motor
    `_fetch_precios_live_api` dos veces sobre subconjuntos disjuntos de `instrumentos` para no
    duplicar la calibración de escala ni el resto de las reglas (precio previo requerido, moneda,
    A1/A3). Cada fila lleva `fuente` según de dónde salió: `'iol'` o `'api'`.

    A diferencia de `_fetch_precios_live_api`, nunca devuelve `None`: si tanto IOL como el
    fallback no responden, el llamador simplemente no tiene filas nuevas para esa familia (las
    filas ya persistidas de una corrida anterior no se tocan, ver `inversiones_sync.py`).
    """
    objetivo = [i for i in instrumentos if predicate(i.get("tipo_instrumento", ""))]
    if not objetivo:
        return [], []

    filas: list[dict] = []
    issues: list[ValidationIssue] = []

    iol_por_symbol = fetch_iol_fn()  # dict[str, tuple[float, str]] | None
    iol_symbols = {s.upper().strip() for s in iol_por_symbol} if iol_por_symbol else set()

    if iol_symbols:
        cubiertos = [i for i in objetivo if i["ticker"].upper().strip() in iol_symbols]
        precios_iol = {t: px for t, (px, _m) in iol_por_symbol.items()}
        f_iol, i_iol = _fetch_precios_live_api(
            cubiertos, precios_sheet, claves_excluir, hoy,
            lambda _t: True, lambda: precios_iol, "paneles", estado_por_ticker,
            nombre_fuente="IOL",
        )
        for f in (f_iol or []):
            f["fuente"] = "iol"
        filas.extend(f_iol or [])
        issues.extend(i_iol)
        restantes = [i for i in objetivo if i["ticker"].upper().strip() not in iol_symbols]
    else:
        restantes = objetivo
        if iol_por_symbol is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", regla="iol_no_disponible",
                mensaje=f"No se pudo obtener cotización de IOL para {familia_label} "
                        "(sin credenciales, sin cupo mensual, o caída)",
                impacto="Se usa data912 como respaldo para esta familia de instrumentos",
                severidad=Severity.INFO,
            ))

    if restantes:
        f_fb, i_fb = _fetch_precios_live_api(
            restantes, precios_sheet, claves_excluir, hoy,
            lambda _t: True, fetch_fallback_fn, endpoints_label, estado_por_ticker,
            nombre_fuente="data912",
        )
        if f_fb is not None:
            for f in f_fb:
                f["fuente"] = "api"
            filas.extend(f_fb)
        issues.extend(i_fb)

    return filas, issues


def memo_paneles(db):
    """Callable que pide los paneles de IOL una sola vez y cachea la respuesta.

    Los paneles de `_PANELES` traen renta fija y renta variable en la MISMA tanda de respuestas: se
    piden una vez por sync y se reusan para todas las familias y rutas (precios de cartera y de
    watchlist). Sin este memo cada una gastaría la tanda entera por separado -> varias veces el
    consumo del cupo mensual de IOL.
    """
    cache: list = []

    def _paneles():
        if not cache:
            cache.append(iol_client.fetch_precios_paneles(db))
        return cache[0]

    return _paneles


def memo_fci(db):
    """Igual que `memo_paneles`, para la llamada única a `Titulos/FCI`."""
    cache: list = []

    def _fci():
        if not cache:
            cache.append(iol_client.fetch_precios_fci(db))
        return cache[0]

    return _fci


def fetch_precios_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    db,
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
    paneles_fn=None,
    fci_fn=None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Precio del día para renta fija + renta variable + FCI, IOL primero y data912 como
    respaldo (FCI no tiene respaldo público: si IOL no lo cotiza, no se carga). Punto de entrada
    único que reemplaza a llamar `fetch_precios_renta_fija_api`/`fetch_precios_renta_variable_api`
    por separado desde `inversiones_sync.py`.

    `db`: la sesión del sync (no se usa para leer/escribir precios acá, sólo se le pasa a
    `iol_auth`, que cuenta el cupo mensual sobre esa misma sesión en vez de abrir una propia --
    ver la docstring de `iol_auth`).

    `paneles_fn` / `fci_fn`: memos de las llamadas a IOL compartidos con otras rutas de la misma
    corrida (ver `memo_paneles` / `memo_fci`). Si no se pasan, se arman propios."""
    hoy = hoy or date.today()
    filas: list[dict] = []
    issues: list[ValidationIssue] = []

    _paneles = paneles_fn or memo_paneles(db)
    _fci = fci_fn or memo_fci(db)

    for predicate, fallback_fn, label, familia in (
        (_es_renta_fija, data912.fetch_precios_renta_fija,
         "arg_bonds/arg_corp/arg_notes", "renta fija"),
        (_es_renta_variable, data912.fetch_precios_renta_variable,
         "arg_stocks/arg_cedears", "renta variable"),
    ):
        f, i = _fetch_precios_encadenado(
            instrumentos, precios_sheet, claves_excluir, hoy, predicate,
            _paneles, fallback_fn, label, familia, estado_por_ticker,
        )
        filas.extend(f)
        issues.extend(i)

    # FCI: sin respaldo público — si IOL no responde, directamente no hay filas para esta familia.
    fci_objetivo = [i for i in instrumentos if _es_fci(i.get("tipo_instrumento", ""))]
    if fci_objetivo:
        iol_fci = _fci()
        if iol_fci is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", regla="iol_no_disponible",
                mensaje="No se pudo obtener cotización de IOL para FCI (sin credenciales, sin "
                        "cupo mensual, o caída)",
                impacto="No hay respaldo público para FCI: se mantiene el último precio automático",
                severidad=Severity.INFO,
            ))
        else:
            precios_iol_fci = {t: px for t, (px, _m) in iol_fci.items()}
            f_fci, i_fci = _fetch_precios_live_api(
                fci_objetivo, precios_sheet, claves_excluir, hoy,
                lambda _t: True, lambda: precios_iol_fci, "Titulos/FCI", estado_por_ticker,
                nombre_fuente="IOL",
            )
            for f in (f_fci or []):
                f["fuente"] = "iol"
            filas.extend(f_fci or [])
            issues.extend(i_fci)

    return filas, issues


def fetch_precios_watchlist(
    watchlist: list[dict],
    precios_sheet: list[dict],
    db,
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
    paneles_fn=None,
    fci_fn=None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Precio del día para los tickers de la pestaña `Watchlist` (los que NO están en cartera).

    Reusa `fetch_precios_api` entero -- las tres familias, el encadenado IOL -> data912 y la
    calibración de escala son los mismos. Lo único propio es de dónde sale la **referencia de
    escala**: un ticker de watchlist no tiene precios manuales en la pestaña `Precios`, así que se
    le arma una referencia sintética con su propio `Objetivo`, que está expresado en la misma
    unidad en la que el usuario piensa el precio. Si además cargó precios reales de ese ticker en
    `Precios`, esos ganan (son una referencia observada, no una intención).

    Consecuencia a tener presente: si el objetivo está a más de ~2.5x del precio de mercado, el
    ratio cae fuera de las ventanas de `_factor_escala` y el precio no se carga (issue
    `escala_desconocida`). Se destraba cargando un precio manual del ticker en la pestaña `Precios`.

    Devuelve (filas, issues); las filas tienen la forma `{ticker, fecha, precio, moneda, fuente}`,
    lista para `PrecioWatchlist`.
    """
    hoy = hoy or date.today()
    if not watchlist:
        return [], []

    tickers_wl = {w["ticker"] for w in watchlist}
    precios_ref = [p for p in precios_sheet if p["ticker"] in tickers_wl]
    con_referencia_real = {p["ticker"] for p in precios_ref}
    for w in watchlist:
        if w["ticker"] in con_referencia_real or w.get("objetivo") is None:
            continue
        precios_ref.append({
            "ticker": w["ticker"],
            "fecha": hoy,
            "precio": float(w["objetivo"]),
            "moneda": w.get("moneda") or "ARS",
        })

    filas, issues = fetch_precios_api(
        watchlist, precios_ref, set(), db, hoy=hoy, estado_por_ticker=estado_por_ticker,
        paneles_fn=paneles_fn, fci_fn=fci_fn,
    )

    # Los issues salen rotulados como si vinieran de la cartera: se re-rotulan para que en Calidad
    # de datos se vea de qué pestaña salió cada uno, y las dos reglas de calibración explican el
    # remedio propio de la watchlist (la referencia acá es el Objetivo, no un precio manual).
    for issue in issues:
        issue.tab = "Watchlist (API)"
        if issue.regla in ("sin_precio_para_calibrar", "escala_desconocida"):
            issue.impacto = (
                "No se carga el precio de este instrumento de la watchlist. Cargá un precio "
                "manual del ticker en la pestaña Precios, o revisá que el Objetivo esté en la "
                "misma unidad que la cotización"
            )

    return filas, issues


def fetch_backfill_iol(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    primeras_fechas_mov: dict[str, date],
    api_existentes_por_ticker: dict[str, date],
    db,
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
    ohlcv_existentes: dict[str, date] | None = None,
    barras_out: list[dict] | None = None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Backfill histórico vía IOL para lo que `fetch_backfill_renta_fija_api` (analisistecnico) no
    cubre: ONs corporativas (marcadas `backfill_estado == 'sin_serie'`) y renta variable (acciones/
    CEDEARs, que hoy no tienen ninguna fuente de historia). Se corre *después* de esa función y
    reutiliza las mismas cotas (`_TOPE_BACKFILL`, `_MAX_BACKFILL_POR_SYNC`,
    `_REINTENTO_SIN_SERIE_DIAS`) y el mismo `estado_por_ticker`, así que converge igual y no gasta
    cupo de más. Un ticker que tampoco tiene serie en IOL se marca `'sin_serie_iol'` (no
    `'sin_serie'`, para no confundirlo con "sin serie en analisistecnico pero sin probar IOL
    todavía" en corridas donde IOL esté deshabilitada).

    Devuelve siempre una lista (nunca None): un fallo puntual sólo se reintenta el próximo sync.

    `ohlcv_existentes` / `barras_out`: ver `fetch_backfill_renta_fija_api` — mismo contrato
    (rango ampliado a `_PISO_TECNICO`, regla de primer llenado, cero llamadas HTTP nuevas: viaja
    en la misma respuesta de `fetch_historico_ohlcv` que ya se pide para valuación).
    """
    issues: list[ValidationIssue] = []
    hoy = hoy or date.today()
    ayer = hoy - timedelta(days=1)

    objetivo = [
        i for i in instrumentos
        if _es_renta_variable(i.get("tipo_instrumento", ""))
        or (_es_renta_fija(i.get("tipo_instrumento", ""))
            and (estado_por_ticker or {}).get(i["ticker"], {}).get("backfill_estado") in
            ("sin_serie", "sin_serie_iol"))
    ]
    if not objetivo:
        return [], issues

    ultimo_sheet: dict[str, tuple[date, float, str]] = {}
    for p in precios_sheet:
        t, f, px = p["ticker"], p["fecha"], float(p["precio"])
        if t not in ultimo_sheet or f > ultimo_sheet[t][0]:
            ultimo_sheet[t] = (f, px, p.get("moneda") or "")

    pendientes: list[tuple[int, dict, date, date]] = []
    for inst in objetivo:
        ticker = inst["ticker"]
        piso = primeras_fechas_mov.get(ticker)
        if piso is None:
            continue
        piso = max(piso, hoy - _TOPE_BACKFILL)
        piso_fetch = min(piso, hoy - _PISO_TECNICO) if barras_out is not None else piso

        ya = api_existentes_por_ticker.get(ticker)
        valuacion_convergida = ya is not None and ya <= piso + timedelta(days=_TOLERANCIA_PISO_DIAS)
        necesita_ohlcv = barras_out is not None and (ohlcv_existentes or {}).get(ticker) is None

        if valuacion_convergida and not necesita_ohlcv:
            continue

        est = estado_por_ticker.get(ticker) if estado_por_ticker is not None else None
        if est is not None:
            bf = est.get("backfill_estado")
            if bf == "completo":
                if not necesita_ohlcv:
                    continue
                intento_ohlcv = est.get("ohlcv_intento")
                if intento_ohlcv is not None and (hoy - intento_ohlcv).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue
            elif bf == "sin_serie_iol":
                intento = est.get("backfill_intento")
                if intento is None or (hoy - intento).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue

        hueco = (ya - piso).days if ya is not None else 10 ** 6
        pendientes.append((hueco, inst, piso, piso_fetch))

    pendientes.sort(key=lambda x: x[0], reverse=True)

    filas: list[dict] = []
    for _, inst, piso, piso_fetch in pendientes[:_MAX_BACKFILL_POR_SYNC]:
        ticker = inst["ticker"]
        ya = api_existentes_por_ticker.get(ticker)
        est_entry = estado_por_ticker.setdefault(ticker, {}) if estado_por_ticker is not None else None
        serie = iol_client.fetch_historico_ohlcv(db, ticker, piso_fetch, ayer)

        if serie is None:
            ya_reportado = est_entry is not None and est_entry.get("backfill_estado") == "sin_serie_iol"
            if est_entry is not None:
                est_entry["backfill_estado"] = "sin_serie_iol"
                est_entry["backfill_intento"] = hoy
            if not ya_reportado:
                issues.append(ValidationIssue(
                    tab="Precios (API)", campo=ticker, regla="sin_historico_backfill_iol",
                    mensaje=f"{ticker}: sin serie histórica tampoco en IOL",
                    impacto="La serie automática de este instrumento sólo crece hacia adelante",
                    severidad=Severity.INFO,
                ))
            continue

        if est_entry is not None:
            est_entry["backfill_intento"] = hoy
            if est_entry.get("backfill_estado") in ("sin_serie", "sin_serie_iol"):
                est_entry["backfill_estado"] = None
            if barras_out is not None:
                est_entry["ohlcv_intento"] = hoy
        if not serie:
            continue

        prev = ultimo_sheet.get(ticker)
        if prev is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="sin_precio_para_calibrar",
                mensaje=(f"{ticker}: hay serie histórica en IOL pero no hay precio manual en el "
                         "Sheet para calibrar la escala"),
                impacto="No se hace backfill hasta tener una referencia manual",
                severidad=Severity.INFO,
            ))
            continue

        f_sheet, px_sheet, moneda_sheet = prev
        if px_sheet <= 0:
            continue

        serie_valuacion = [b for b in serie if b.fecha >= piso]
        candidatos_ref = serie_valuacion or serie
        px_ref = min(candidatos_ref, key=lambda b: abs((b.fecha - f_sheet).days)).cierre
        factor, _ = _resolver_factor(ticker, px_ref, px_sheet, f_sheet, estado_por_ticker)
        if factor is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="escala_desconocida",
                mensaje=(f"{ticker}: IOL cotiza {px_ref:g} cerca del {f_sheet} y el Sheet "
                         f"{px_sheet:g} (factor {px_ref / px_sheet:.2f}, fuera de ~1 o ~100)"),
                impacto="No se hace backfill de este instrumento",
                severidad=Severity.ADVERTENCIA,
            ))
            continue

        issue_moneda = _issue_moneda_difiere(ticker, moneda_sheet, inst.get("moneda", ""))
        if issue_moneda is not None:
            issues.append(issue_moneda)

        moneda = (moneda_sheet or inst.get("moneda") or "ARS").strip().upper()
        for b in serie_valuacion:
            if b.fecha >= hoy or (ticker, b.fecha) in claves_excluir:
                continue
            filas.append({
                "fecha": b.fecha,
                "ticker": ticker,
                "precio": round(b.cierre * factor, 6),
                "moneda": moneda,
                "fuente": "iol",
            })

        if barras_out is not None:
            for b in serie:
                if b.fecha >= hoy:
                    continue
                escalada = _aplicar_factor_ohlcv(b, factor)
                barras_out.append({
                    "ticker": ticker, "fecha": escalada.fecha,
                    "apertura": escalada.apertura, "maximo": escalada.maximo, "minimo": escalada.minimo,
                    "cierre": escalada.cierre, "volumen": escalada.volumen,
                    "moneda": moneda, "fuente": "iol",
                })
            if est_entry is not None:
                ya_ohlcv = (ohlcv_existentes or {}).get(ticker)
                min_serie_full = min((b.fecha for b in serie), default=None)
                if ya_ohlcv is not None and min_serie_full is not None and min_serie_full >= ya_ohlcv:
                    est_entry["ohlcv_estado"] = "completo"

        min_serie = min((b.fecha for b in serie_valuacion), default=None)
        if est_entry is not None and ya is not None and min_serie is not None and min_serie >= ya:
            est_entry["backfill_estado"] = "completo"

    return filas, issues


def fetch_backfill_ohlcv_watchlist(
    watchlist: list[dict],
    precios_sheet: list[dict],
    ohlcv_existentes: dict[str, date],
    db,
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Backfill de velas para tickers de la watchlist — función propia, a diferencia del backfill
    de cartera: esos tickers no tienen movimientos (sin piso de valuación) ni filas en
    `precios_instrumento`, y su referencia de escala es sintética.

    Piso `hoy - _PISO_TECNICO` (2 años, alcanza para una MM200 y el backtest, cuesta la mitad que
    el piso de cartera). Referencia de escala: **exactamente** la misma construcción que
    `fetch_precios_watchlist` — precio manual de `Precios` si existe, si no una fila sintética con
    el `Objetivo`. El factor sale de `_resolver_factor`, que normalmente reusa el `factor_escala`
    ya persistido por la ruta live: el gráfico y la tarjeta de watchlist no pueden divergir de
    escala. Fuera de las ventanas de ratio conocidas -> issue `escala_desconocida` con el mismo
    texto de remedio que ya usa la watchlist.

    analisistecnico primero (gratis); IOL sólo si el primero devuelve `None`. El loop se corta a
    `_MAX_BACKFILL_OHLCV_POR_SYNC` tickers por corrida: analisistecnico no tiene cupo mensual, pero
    cada GET es tiempo de pared con la transacción del sync abierta (y este backfill hace
    `delete()`+`flush()` dentro del loop), así que igual hay que racionarlo — mismo patrón que los
    otros tres backfills de este módulo.

    `ohlcv_existentes`: ticker -> fecha más antigua ya en `serie_ohlcv` (define qué tickers
    todavía no convergieron). `estado_por_ticker` (opcional): se muta in place con
    `ohlcv_estado`/`ohlcv_intento` — mismos valores que `backfill_estado`
    ('completo'/'sin_serie'/'sin_serie_iol') pero para este pipeline, independiente del de
    valuación (`backfill_estado`), que no existe para estos tickers.

    Devuelve siempre una lista (nunca None): un fallo puntual sólo se reintenta el próximo sync.
    """
    issues: list[ValidationIssue] = []
    hoy = hoy or date.today()
    ayer = hoy - timedelta(days=1)
    if not watchlist:
        return [], issues

    tickers_wl = {w["ticker"] for w in watchlist}
    precios_ref = [p for p in precios_sheet if p["ticker"] in tickers_wl]
    con_referencia_real = {p["ticker"] for p in precios_ref}

    ultimo_sheet: dict[str, tuple[date, float, str]] = {}
    for p in precios_ref:
        t, f, px = p["ticker"], p["fecha"], float(p["precio"])
        if t not in ultimo_sheet or f > ultimo_sheet[t][0]:
            ultimo_sheet[t] = (f, px, p.get("moneda") or "")
    for w in watchlist:
        if w["ticker"] in con_referencia_real or w.get("objetivo") is None:
            continue
        ultimo_sheet.setdefault(w["ticker"], (hoy, float(w["objetivo"]), w.get("moneda") or "ARS"))

    piso_global = hoy - _PISO_TECNICO

    pendientes: list[dict] = []
    for w in watchlist:
        ticker = w["ticker"]
        ya = ohlcv_existentes.get(ticker)
        if ya is not None and ya <= piso_global + timedelta(days=_TOLERANCIA_PISO_DIAS):
            continue  # la serie de velas ya cubre hasta ~el piso

        est = estado_por_ticker.get(ticker) if estado_por_ticker is not None else None
        if est is not None:
            oe = est.get("ohlcv_estado")
            if oe == "completo":
                continue
            if oe in ("sin_serie", "sin_serie_iol"):
                intento = est.get("ohlcv_intento")
                if intento is None or (hoy - intento).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue

        hueco = (ya - piso_global).days if ya is not None else 10 ** 6
        pendientes.append({"hueco": hueco, "w": w})

    pendientes.sort(key=lambda x: x["hueco"], reverse=True)

    filas: list[dict] = []
    llamadas_iol = 0
    # Cota por corrida (huecos más grandes primero, ya ordenados arriba): acota el tiempo de pared
    # con la transacción del sync abierta. Es el único de los cuatro backfills del módulo que le
    # faltaba.
    for item in pendientes[:_MAX_BACKFILL_OHLCV_POR_SYNC]:
        w = item["w"]
        ticker = w["ticker"]
        ya = ohlcv_existentes.get(ticker)
        est_entry = estado_por_ticker.setdefault(ticker, {}) if estado_por_ticker is not None else None

        # Serie local: para un CEDEAR se pide `TICKER:CEDEAR` (el CEDEAR local en ARS), no el
        # ticker pelado — que analisistecnico resuelve a la acción del NASDAQ en USD y hace que el
        # ratio contra el `Objetivo` en ARS caiga fuera de las ventanas de `_factor_escala`
        # (issue `escala_desconocida` y todas las velas descartadas). Con `TICKER:CEDEAR` el ratio
        # vuelve a ~1 y la serie carga sin tocar la calibración.
        simbolo_local = f"{ticker}:CEDEAR" if _es_cedear(w.get("tipo_instrumento", "")) else ticker
        if est_entry is not None:
            anterior = est_entry.get("simbolo_local")
            if anterior is not None and anterior != simbolo_local:
                # El símbolo local cambió: las velas viejas pueden estar en otra unidad. Se
                # borran una sola vez, antes de reescribir con la serie nueva.
                db.query(BarraOHLCV).filter(BarraOHLCV.ticker == ticker).delete(synchronize_session=False)
                db.flush()
                ya = None
            est_entry["simbolo_local"] = simbolo_local

        serie = analisistecnico.fetch_historico_ohlcv(simbolo_local, piso_global, ayer)
        fuente_barras = "api"
        if serie is None:
            if llamadas_iol >= _MAX_BACKFILL_OHLCV_POR_SYNC:
                continue  # cupo de IOL agotado para esta corrida; se reintenta el próximo sync
            serie = iol_client.fetch_historico_ohlcv(db, ticker, piso_global, ayer)
            llamadas_iol += 1
            fuente_barras = "iol"

        if serie is None:
            ya_reportado = est_entry is not None and est_entry.get("ohlcv_estado") == "sin_serie_iol"
            if est_entry is not None:
                est_entry["ohlcv_estado"] = "sin_serie_iol"
                est_entry["ohlcv_intento"] = hoy
            if not ya_reportado:
                issues.append(ValidationIssue(
                    tab="Watchlist (OHLCV)", campo=ticker, regla="sin_historico_ohlcv",
                    mensaje=f"{ticker}: sin serie histórica de velas en analisistecnico ni IOL",
                    impacto="Este ticker de la watchlist se grafica sólo con lo que se acumule de acá en más",
                    severidad=Severity.INFO,
                ))
            continue

        if est_entry is not None:
            est_entry["ohlcv_intento"] = hoy
            if est_entry.get("ohlcv_estado") in ("sin_serie", "sin_serie_iol"):
                est_entry["ohlcv_estado"] = None
        if not serie:
            continue

        prev = ultimo_sheet.get(ticker)
        if prev is None:
            continue  # sin precio manual ni Objetivo: no hay referencia de escala posible

        f_ref, px_ref_sheet, moneda_sheet = prev
        if px_ref_sheet <= 0:
            continue
        px_ref = min(serie, key=lambda b: abs((b.fecha - f_ref).days)).cierre
        factor, _ = _resolver_factor(ticker, px_ref, px_ref_sheet, f_ref, estado_por_ticker)

        # El factor persistido se calibró contra la fuente de la ruta *live* (IOL/data912), que no
        # es necesariamente la misma que la de las velas: para un CEDEAR, IOL cotiza el CEDEAR en
        # ARS y analisistecnico puede resolver el mismo símbolo a la acción en USD (~11x de
        # diferencia). Reusar el factor a ciegas cargaría velas en otra unidad que la tarjeta de
        # la watchlist — justo lo que el reuso quería evitar. Por eso el factor reusado igual se
        # valida contra ESTA serie: si no concuerda, no se cargan velas y se reporta.
        factor_observado = _factor_escala(px_ref, px_ref_sheet)
        if factor is None or factor_observado != factor:
            issues.append(ValidationIssue(
                tab="Watchlist (OHLCV)", campo=ticker, regla="escala_desconocida",
                mensaje=(f"{ticker}: la fuente de velas cotiza {px_ref:g} y la referencia "
                         f"({'precio manual' if ticker in con_referencia_real else 'Objetivo'}) "
                         f"es {px_ref_sheet:g} (factor {px_ref / px_ref_sheet:.2f}, "
                         f"incompatible con la escala {factor if factor is not None else '~1 o ~100'} "
                         "de la cotización)"),
                impacto=("No se cargan velas de este ticker de la watchlist: el gráfico quedaría "
                         "en otra unidad que el precio de la tarjeta. Cargá un precio manual del "
                         "ticker en la pestaña Precios, o revisá que el Objetivo esté en la misma "
                         "unidad que la cotización"),
                severidad=Severity.ADVERTENCIA,
            ))
            continue

        moneda = (moneda_sheet or w.get("moneda") or "ARS").strip().upper()
        for b in serie:
            if b.fecha >= hoy:
                continue
            escalada = _aplicar_factor_ohlcv(b, factor)
            filas.append({
                "ticker": ticker, "fecha": escalada.fecha,
                "apertura": escalada.apertura, "maximo": escalada.maximo, "minimo": escalada.minimo,
                "cierre": escalada.cierre, "volumen": escalada.volumen,
                "moneda": moneda, "fuente": fuente_barras,
            })

        min_serie = min((b.fecha for b in serie), default=None)
        if est_entry is not None and ya is not None and min_serie is not None and min_serie >= ya:
            est_entry["ohlcv_estado"] = "completo"

    return filas, issues


# --- Serie del subyacente en USD (yfinance) -----------------------------------------------------
#
# Para un CEDEAR (o una acción local con ADR) se baja la serie del instrumento subyacente tal
# como cotiza en EE.UU., en USD nativo, para correr indicadores y backtests sobre el precio real
# del mercado de origen en vez del CEDEAR local en ARS. Fuente: yfinance (ajusta splits solo y da
# ~40 años de historia). Cero créditos de IOL, sin auth.
#
# Se guarda bajo la clave derivada `TICKER@SUB` en `serie_ohlcv` (ver `ohlcv_analytics`). **No
# pasa por `_factor_escala`**: esa función reconcilia una serie contra el precio de referencia
# *local* (Sheet / Objetivo); el subyacente es otro instrumento, en otro mercado, en otra moneda.
# En su lugar:
#   G1 — sólo se baja si `fetch_info` confirmó `moneda == "USD"` (resolución previa).
#   G2 — la moneda sale de la fuente, nunca del Sheet ni del `WatchlistItem`.
#   G3 — cordura: >=2 barras, cierres finitos y positivos.
#   G4 — aislamiento de escritura: sólo `serie_ohlcv`, que ningún analytic de patrimonio /
#        exposición / riesgo lee.

_PISO_SUBYACENTE = timedelta(days=366 * 5)      # 5 años (yfinance trae todo en una sola llamada)
_TOLERANCIA_PISO_SUBYACENTE_DIAS = 40
_COLA_STALE_DIAS = 3                            # el tope de la serie se refresca si atrasa más
_REINTENTO_RESOLUCION_DIAS = 180               # cooldown de un `sin_subyacente`
_MAX_RESOLUCIONES_SUBYACENTE = 10
_MAX_BACKFILL_SUBYACENTE_POR_SYNC = 12

# Tokens de razón social sin valor discriminante para el match de nombre de una acción local.
_STOP_NOMBRE = {
    "sa", "s", "a", "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "plc", "nv", "ag", "the", "class", "cedear", "adr", "holding", "holdings",
    "group", "grupo", "and", "de", "argentina",
}


def _tokens_nombre(s: str) -> set[str]:
    t = _sin_acentos(s or "")
    for ch in ".,-/()&":
        t = t.replace(ch, " ")
    return {w for w in t.split() if len(w) > 1 and w not in _STOP_NOMBRE}


def _nombre_matchea(a: str, b: str) -> bool:
    """¿Los dos nombres de empresa se parecen lo suficiente? Heurística conservadora: al menos la
    mitad de los tokens significativos del más corto en común. Para acciones locales el ticker
    pelado puede resolver a **otra empresa** en Yahoo, así que si no matchea no se adivina."""
    ta, tb = _tokens_nombre(a), _tokens_nombre(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    return bool(inter) and len(inter) / min(len(ta), len(tb)) >= 0.5


def resolver_subyacente(
    activos: list[dict],
    estado_por_ticker: dict[str, dict],
    hoy: date | None = None,
    max_resoluciones: int = _MAX_RESOLUCIONES_SUBYACENTE,
) -> list[ValidationIssue]:
    """Resuelve, para los tickers de renta variable de `activos`, el símbolo del subyacente en
    Yahoo (ticker pelado, por la convención de Yahoo) y lo cachea en `estado_por_ticker`.

    Un solo `yahoo.fetch_info(ticker)` por ticker no resuelto todavía, hasta `max_resoluciones`
    por corrida. Se acepta el subyacente sólo si `moneda == "USD"` (G1). CEDEAR → aceptación
    automática (el ticker local es el del subyacente). Acción local → sólo si el nombre del
    instrumento matchea el que devuelve Yahoo (el pelado puede ser otra empresa). Un
    `sin_subyacente` se reintenta a los ~180 días.

    Muta `estado_por_ticker` in place (`simbolo_subyacente`, `mercado_subyacente`,
    `moneda_subyacente`, `resolucion_estado`, `resolucion_intento`). Devuelve issues INFO.
    """
    hoy = hoy or date.today()
    issues: list[ValidationIssue] = []

    candidatos: list[dict] = []
    for a in activos:
        if not _es_renta_variable(a.get("tipo_instrumento", "")):
            continue
        ticker = a["ticker"]
        est = estado_por_ticker.setdefault(ticker, {})
        estado = est.get("resolucion_estado")
        if estado == "ok" or estado == "ticker_no_apto":
            continue
        if estado == "sin_subyacente":
            intento = est.get("resolucion_intento")
            if intento is not None and (hoy - intento).days < _REINTENTO_RESOLUCION_DIAS:
                continue
        candidatos.append(a)

    for a in candidatos[:max_resoluciones]:
        ticker = a["ticker"]
        est = estado_por_ticker.setdefault(ticker, {})
        est["resolucion_intento"] = hoy
        es_cedear = _es_cedear(a.get("tipo_instrumento", ""))

        info = yahoo.fetch_info(ticker)
        if info is None:
            est["resolucion_estado"] = "sin_subyacente"
            issues.append(ValidationIssue(
                tab="Subyacente (USD)", campo=ticker, regla="subyacente_no_resuelto",
                mensaje=f"{ticker}: Yahoo no devolvió información del símbolo",
                impacto="La pestaña Subyacente (USD) no está disponible para este ticker; se reintenta en ~180 días",
                severidad=Severity.INFO,
            ))
            continue

        if info.get("moneda") != "USD":
            est["resolucion_estado"] = "sin_subyacente"
            issues.append(ValidationIssue(
                tab="Subyacente (USD)", campo=ticker, regla="subyacente_no_usd",
                mensaje=(f"{ticker}: el símbolo en Yahoo cotiza en {info.get('moneda') or '¿?'}, "
                         "no en USD"),
                impacto="No se baja serie del subyacente (sólo se acepta un subyacente en USD)",
                severidad=Severity.INFO,
            ))
            continue

        if not es_cedear and not _nombre_matchea(a.get("nombre", ""), info.get("nombre") or ""):
            est["resolucion_estado"] = "sin_subyacente"
            issues.append(ValidationIssue(
                tab="Subyacente (USD)", campo=ticker, regla="subyacente_nombre_no_matchea",
                mensaje=(f"{ticker}: el nombre en Yahoo ('{info.get('nombre') or '¿?'}') no se "
                         f"parece al del instrumento ('{a.get('nombre') or '¿?'}')"),
                impacto=("El ticker pelado podría ser otra empresa en Yahoo; no se baja serie del "
                         "subyacente sin un match de nombre"),
                severidad=Severity.INFO,
            ))
            continue

        est["resolucion_estado"] = "ok"
        est["simbolo_subyacente"] = ticker
        est["mercado_subyacente"] = info.get("mercado") or ""
        est["moneda_subyacente"] = "USD"

    return issues


def fetch_backfill_ohlcv_subyacente(
    activos: list[dict],
    ohlcv_existentes: dict[str, date],
    ohlcv_maximos: dict[str, date],
    estado_por_ticker: dict[str, dict],
    hoy: date | None = None,
    max_llamadas: int = _MAX_BACKFILL_SUBYACENTE_POR_SYNC,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Baja/actualiza la serie del subyacente en USD (`TICKER@SUB`) para los tickers de `activos`
    con `resolucion_estado == "ok"`.

    Dos trabajos priorizados dentro de `max_llamadas`: (1) **refresco de cola** — esta serie no
    tiene ruta *live* que le escriba el cierre del día, así que sin esto se congela; (2) backfill
    hacia atrás hasta `_PISO_SUBYACENTE`. yfinance devuelve toda la historia en una sola llamada,
    así que ambos trabajos se resuelven con el mismo fetch por ticker.

    `ohlcv_existentes` / `ohlcv_maximos`: clave `@SUB` -> fecha más antigua / más nueva ya en
    `serie_ohlcv`. Emite filas `{ticker=clave, ..., moneda="USD", fuente="yahoo"}` para el upsert
    del sync. No usa `db`, no cae a IOL, no pasa por `_factor_escala`.
    """
    hoy = hoy or date.today()
    ayer = hoy - timedelta(days=1)
    issues: list[ValidationIssue] = []

    piso = hoy - _PISO_SUBYACENTE

    pendientes: list[tuple[int, str, str]] = []
    for a in activos:
        ticker = a["ticker"]
        est = estado_por_ticker.get(ticker) or {}
        if est.get("resolucion_estado") != "ok":
            continue
        simbolo = est.get("simbolo_subyacente")
        if not simbolo or est.get("moneda_subyacente") != "USD":  # G1
            continue

        clave = clave_serie(ticker, "subyacente")
        min_ya = ohlcv_existentes.get(clave)
        max_ya = ohlcv_maximos.get(clave)
        convergido_atras = min_ya is not None and min_ya <= piso + timedelta(days=_TOLERANCIA_PISO_SUBYACENTE_DIAS)
        cola_fresca = max_ya is not None and max_ya >= ayer - timedelta(days=_COLA_STALE_DIAS)

        if convergido_atras and cola_fresca:
            continue

        if min_ya is None:
            prioridad = 0                      # todavía no hay nada
        elif not cola_fresca:
            prioridad = 1                      # refresco de cola
        else:
            prioridad = 2                      # sólo falta backfill hacia atrás
        pendientes.append((prioridad, ticker, simbolo))

    pendientes.sort(key=lambda x: x[0])

    filas: list[dict] = []
    for _prioridad, ticker, simbolo in pendientes[:max_llamadas]:
        serie = yahoo.fetch_historico_ohlcv(simbolo, piso, ayer)
        if serie is None:
            issues.append(ValidationIssue(
                tab="Subyacente (USD)", campo=ticker, regla="subyacente_sin_serie",
                mensaje=f"{ticker}: yfinance no devolvió la serie de {simbolo}",
                impacto="Se reintenta el próximo sync; la pestaña Subyacente (USD) queda con lo ya bajado",
                severidad=Severity.INFO,
            ))
            continue
        if len(serie) < 2:  # G3
            continue

        clave = clave_serie(ticker, "subyacente")
        for b in serie:
            if b.fecha >= hoy or b.cierre <= 0:
                continue
            filas.append({
                "ticker": clave, "fecha": b.fecha,
                "apertura": b.apertura, "maximo": b.maximo, "minimo": b.minimo,
                "cierre": b.cierre, "volumen": b.volumen,
                "moneda": "USD", "fuente": "yahoo",  # G2
            })

    return filas, issues
