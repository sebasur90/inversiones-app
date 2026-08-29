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

from ..validation.types import Severity, ValidationIssue
from . import analisistecnico, data912
from . import iol as iol_client

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
    tokens = {tok for tok in t.replace("/", " ").replace("-", " ").split()}
    return bool(tokens & _TOKENS_RENTA_FIJA)


def _es_renta_variable(tipo_instrumento: str) -> bool:
    t = _sin_acentos(tipo_instrumento or "")
    return any(sub in t for sub in _SUBCADENAS_RENTA_VARIABLE)


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

    ONs corporativas: analisistecnico no las tiene (`fetch_historico_bono` -> None). Se marcan
    `'sin_serie'` y se reporta un SyncIssue info **una sola vez** — siguen con la serie
    forward-only y su historia manual del Sheet.
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
    pendientes: list[tuple[int, dict, date]] = []
    for inst in objetivo:
        ticker = inst["ticker"]
        piso = primeras_fechas_mov.get(ticker)
        if piso is None:
            continue
        piso = max(piso, hoy - _TOPE_BACKFILL)
        ya = api_existentes_por_ticker.get(ticker)
        if ya is not None and ya <= piso + timedelta(days=_TOLERANCIA_PISO_DIAS):
            continue  # la serie 'api' ya cubre hasta ~el piso

        est = estado_por_ticker.get(ticker) if estado_por_ticker is not None else None
        if est is not None:
            bf = est.get("backfill_estado")
            if bf == "completo":
                continue  # A3: la serie histórica ya no baja más, no gastar cupo
            if bf in ("sin_serie", "sin_serie_iol"):
                intento = est.get("backfill_intento")
                if intento is None or (hoy - intento).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue  # A3: la fuente no lo cubre; se reintenta recién a los ~90 días

        hueco = (ya - piso).days if ya is not None else 10 ** 6
        pendientes.append((hueco, inst, piso))

    pendientes.sort(key=lambda x: x[0], reverse=True)

    filas: list[dict] = []
    for _, inst, piso in pendientes[:_MAX_BACKFILL_POR_SYNC]:
        ticker = inst["ticker"]
        ya = api_existentes_por_ticker.get(ticker)
        est_entry = estado_por_ticker.setdefault(ticker, {}) if estado_por_ticker is not None else None
        serie = analisistecnico.fetch_historico_bono(ticker, piso, ayer)

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
        # Calibra contra el cierre de analisistecnico más cercano a la última fecha del Sheet.
        px_ref = min(serie, key=lambda fp: abs((fp[0] - f_sheet).days))[1]
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
        for f, px in serie:
            if f >= hoy or (ticker, f) in claves_excluir:
                continue
            filas.append({
                "fecha": f,
                "ticker": ticker,
                "precio": round(px * factor, 6),
                "moneda": moneda,
                "fuente": "api",
            })

        # A3: convergencia por "ya no baja más" — si la fecha más vieja devuelta no mejora
        # respecto de lo que ya hay en la DB, la serie no va a crecer hacia atrás: marcar completo.
        min_serie = min((f for f, _ in serie), default=None)
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


def fetch_precios_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    db,
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Precio del día para renta fija + renta variable + FCI, IOL primero y data912 como
    respaldo (FCI no tiene respaldo público: si IOL no lo cotiza, no se carga). Punto de entrada
    único que reemplaza a llamar `fetch_precios_renta_fija_api`/`fetch_precios_renta_variable_api`
    por separado desde `inversiones_sync.py`.

    `db`: la sesión del sync (no se usa para leer/escribir precios acá, sólo se le pasa a
    `iol_auth`, que cuenta el cupo mensual sobre esa misma sesión en vez de abrir una propia --
    ver la docstring de `iol_auth`)."""
    hoy = hoy or date.today()
    filas: list[dict] = []
    issues: list[ValidationIssue] = []

    # Los paneles de `_PANELES` traen renta fija y renta variable en la MISMA tanda de respuestas:
    # se piden una sola vez por sync y se reusan para las dos familias. Sin este memo cada familia
    # gastaría la tanda entera por separado -> el doble de consumo del cupo mensual de IOL.
    _paneles_memo: list = []

    def _paneles():
        if not _paneles_memo:
            _paneles_memo.append(iol_client.fetch_precios_paneles(db))
        return _paneles_memo[0]

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
        iol_fci = iol_client.fetch_precios_fci(db)
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


def fetch_backfill_iol(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    primeras_fechas_mov: dict[str, date],
    api_existentes_por_ticker: dict[str, date],
    db,
    hoy: date | None = None,
    estado_por_ticker: dict[str, dict] | None = None,
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

    pendientes: list[tuple[int, dict, date]] = []
    for inst in objetivo:
        ticker = inst["ticker"]
        piso = primeras_fechas_mov.get(ticker)
        if piso is None:
            continue
        piso = max(piso, hoy - _TOPE_BACKFILL)
        ya = api_existentes_por_ticker.get(ticker)
        if ya is not None and ya <= piso + timedelta(days=_TOLERANCIA_PISO_DIAS):
            continue

        est = estado_por_ticker.get(ticker) if estado_por_ticker is not None else None
        if est is not None:
            bf = est.get("backfill_estado")
            if bf == "completo":
                continue
            if bf == "sin_serie_iol":
                intento = est.get("backfill_intento")
                if intento is None or (hoy - intento).days < _REINTENTO_SIN_SERIE_DIAS:
                    continue

        hueco = (ya - piso).days if ya is not None else 10 ** 6
        pendientes.append((hueco, inst, piso))

    pendientes.sort(key=lambda x: x[0], reverse=True)

    filas: list[dict] = []
    for _, inst, piso in pendientes[:_MAX_BACKFILL_POR_SYNC]:
        ticker = inst["ticker"]
        ya = api_existentes_por_ticker.get(ticker)
        est_entry = estado_por_ticker.setdefault(ticker, {}) if estado_por_ticker is not None else None
        serie = iol_client.fetch_historico(db, ticker, piso, ayer)

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
        px_ref = min(serie, key=lambda fp: abs((fp[0] - f_sheet).days))[1]
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
        for f, px in serie:
            if f >= hoy or (ticker, f) in claves_excluir:
                continue
            filas.append({
                "fecha": f,
                "ticker": ticker,
                "precio": round(px * factor, 6),
                "moneda": moneda,
                "fuente": "iol",
            })

        min_serie = min((f for f, _ in serie), default=None)
        if est_entry is not None and ya is not None and min_serie is not None and min_serie >= ya:
            est_entry["backfill_estado"] = "completo"

    return filas, issues
