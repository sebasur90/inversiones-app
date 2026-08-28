"""Precios automáticos de renta fija (bonos soberanos, ONs, letras/LECAPs) vía data912.

El Sheet siempre gana. La API sólo agrega el precio **del día** para tickers de renta fija que:
  1. existen en la pestaña Instrumentos del Sheet,
  2. tienen al menos un precio manual previo en la pestaña Precios (necesario para calibrar la
     escala — ver abajo), y
  3. no tienen precio manual cargado para hoy.

Escala: data912 cotiza la renta fija ARS por lámina de 100 VN y el Sheet la carga por 1 VN
(factor 100). No se asume el factor a ciegas: para cada ticker se compara la cotización de la
API contra el último precio manual del Sheet y se aplica 1/100 si el ratio cae cerca de 100, o
1 si cae cerca de 1. Cualquier otro ratio -> no se carga y se reporta (elección del usuario:
"normalizar por ratio observado", 2026-08-28).
"""
from datetime import date
from unicodedata import combining, normalize

from ..validation.types import Severity, ValidationIssue
from . import data912

# `tipo_instrumento` en el Sheet es texto libre; se matchea por familia, sin acentos ni mayúsculas.
# Subcadenas inequívocas...
_SUBCADENAS_RENTA_FIJA = ("bono", "boncer", "obligacion negociable", "letra", "lecap", "lede")
# ...y tokens sueltos (para no confundir "ON" con la "on" de "accion" / "bono").
_TOKENS_RENTA_FIJA = {"on", "ons"}

# Ventanas de tolerancia alrededor de los dos factores de escala plausibles (1:1 y 1:100).
_RATIO_CERCA_DE_100 = (40.0, 250.0)
_RATIO_CERCA_DE_1 = (0.4, 2.5)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in normalize("NFD", s) if not combining(c)).lower().strip()


def _es_renta_fija(tipo_instrumento: str) -> bool:
    t = _sin_acentos(tipo_instrumento or "")
    if any(sub in t for sub in _SUBCADENAS_RENTA_FIJA):
        return True
    tokens = {tok for tok in t.replace("/", " ").replace("-", " ").split()}
    return bool(tokens & _TOKENS_RENTA_FIJA)


def fetch_precios_renta_fija_api(
    instrumentos: list[dict],
    precios_sheet: list[dict],
    claves_excluir: set[tuple[str, date]],
    hoy: date | None = None,
) -> tuple[list[dict] | None, list[ValidationIssue]]:
    """Devuelve (filas, issues). `filas` son dicts listos para `PrecioInstrumento(**fila)` con
    `fuente="api"`. Devuelve None (no []) si data912 no respondió en absoluto, para que el sync
    preserve las filas 'api' de una corrida anterior.

    `instrumentos` / `precios_sheet`: los dicts ya validados del Sheet (mismo formato que
    persiste el sync). `claves_excluir`: pares (ticker, fecha) que ya trae el Sheet.
    """
    issues: list[ValidationIssue] = []
    hoy = hoy or date.today()

    objetivo = [i for i in instrumentos if _es_renta_fija(i.get("tipo_instrumento", ""))]
    if not objetivo:
        return [], issues

    api_por_symbol = data912.fetch_precios_renta_fija()
    if api_por_symbol is None:
        issues.append(ValidationIssue(
            tab="Precios (API)", regla="data912_no_disponible",
            mensaje="No se pudieron obtener precios de renta fija de data912",
            impacto="Se mantiene el último precio automático guardado, si existía",
            severidad=Severity.ADVERTENCIA,
        ))
        return None, issues

    api_por_symbol = {sym.upper().strip(): px for sym, px in api_por_symbol.items()}

    ultimo_sheet: dict[str, tuple[date, float]] = {}
    for p in precios_sheet:
        t, f, px = p["ticker"], p["fecha"], float(p["precio"])
        if t not in ultimo_sheet or f > ultimo_sheet[t][0]:
            ultimo_sheet[t] = (f, px)

    filas: list[dict] = []
    for inst in objetivo:
        ticker = inst["ticker"]
        if (ticker, hoy) in claves_excluir:
            continue  # el Sheet ya trae precio de hoy para este ticker

        px_api = api_por_symbol.get(ticker.upper().strip())
        if px_api is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="ticker_no_mapeado",
                mensaje=f"{ticker}: sin cotización en data912 (arg_bonds/arg_corp/arg_notes)",
                impacto="Se sigue usando el precio manual del Sheet para este instrumento",
                severidad=Severity.INFO,
            ))
            continue

        prev = ultimo_sheet.get(ticker)
        if prev is None:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="sin_precio_para_calibrar",
                mensaje=(f"{ticker}: hay cotización en data912 pero no hay precio previo en el "
                         "Sheet para calibrar la escala"),
                impacto="No se carga el precio automático hasta tener una referencia manual",
                severidad=Severity.INFO,
            ))
            continue

        _, px_sheet = prev
        if px_sheet <= 0:
            continue
        ratio = px_api / px_sheet
        if _RATIO_CERCA_DE_100[0] <= ratio <= _RATIO_CERCA_DE_100[1]:
            factor = 0.01
        elif _RATIO_CERCA_DE_1[0] <= ratio <= _RATIO_CERCA_DE_1[1]:
            factor = 1.0
        else:
            issues.append(ValidationIssue(
                tab="Precios (API)", campo=ticker, regla="escala_desconocida",
                mensaje=(f"{ticker}: data912 cotiza {px_api:g} y el último precio del Sheet es "
                         f"{px_sheet:g} (factor {ratio:.2f}, fuera de ~1 o ~100)"),
                impacto="No se carga el precio automático de este instrumento",
                severidad=Severity.ADVERTENCIA,
            ))
            continue

        filas.append({
            "fecha": hoy,
            "ticker": ticker,
            "precio": round(px_api * factor, 6),
            "moneda": inst.get("moneda") or "ARS",
            "fuente": "api",
        })

    return filas, issues
