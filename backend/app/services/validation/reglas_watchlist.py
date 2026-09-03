"""Validación de la pestaña Watchlist (instrumentos a seguir que todavía no están en cartera).

A diferencia de `Instrumentos`, una fila de acá no alimenta ningún cálculo de cartera: sólo sirve
para comparar el precio de mercado contra una zona de compra. Por eso casi todo se salva en vez de
descartarse — el único crítico es no poder identificar el ticker.
"""
from .types import ValidationIssue, Severity
from .parsers import _parse_numero

MONEDAS_VALIDAS = ("ARS", "USD")

MONEDA_DEFAULT = "ARS"


def validar_watchlist(rows: list[tuple[int, dict]]) -> tuple[list[dict], list[ValidationIssue]]:
    """Valida filas de Watchlist. Devuelve (validos, issues)."""
    validos: list[dict] = []
    tickers: set[str] = set()
    issues: list[ValidationIssue] = []

    for row_num, row in rows:
        ticker = (row.get("Ticker") or "").strip()
        if not ticker:
            issues.append(ValidationIssue(
                tab="Watchlist", fila=row_num, regla="ticker_vacio",
                mensaje="Ticker vacío", impacto="No se puede seguir el instrumento",
                severidad=Severity.CRITICO
            ))
            continue

        if ticker in tickers:
            issues.append(ValidationIssue(
                tab="Watchlist", fila=row_num, regla="ticker_duplicado",
                mensaje=f"Ticker duplicado: {ticker}", impacto="Se descarta este duplicado",
                severidad=Severity.CRITICO
            ))
            continue

        # Objetivo — advertencia/salvage: la fila se sigue mostrando, pero sin alerta de zona.
        objetivo = None
        objetivo_raw = (row.get("Objetivo") or "").strip()
        if objetivo_raw and objetivo_raw.lower() != "nan":
            objetivo = _parse_numero(objetivo_raw)
        if objetivo is None or objetivo <= 0:
            issues.append(ValidationIssue(
                tab="Watchlist", fila=row_num, campo="Objetivo",
                regla="objetivo_watchlist_invalido",
                mensaje=f"Objetivo inválido o vacío: {objetivo_raw or '(vacío)'}",
                impacto="El instrumento se sigue listando pero no genera alerta de zona de compra",
                severidad=Severity.ADVERTENCIA
            ))
            objetivo = None

        # Moneda — advertencia/salvage a ARS (en Instrumentos es crítico porque ahí sí entra en los
        # cálculos de cartera; acá sólo define en qué unidad se muestra el precio).
        moneda = (row.get("Moneda") or "").strip().upper()
        if moneda not in MONEDAS_VALIDAS:
            issues.append(ValidationIssue(
                tab="Watchlist", fila=row_num, campo="Moneda", regla="moneda_invalida",
                mensaje=f"Moneda inválida o vacía: {moneda or '(vacío)'}",
                impacto=f"Se asume {MONEDA_DEFAULT}",
                severidad=Severity.ADVERTENCIA
            ))
            moneda = MONEDA_DEFAULT

        # Tipo Instrumento vacío — advertencia/salvage. Sin tipo no se puede clasificar la familia
        # (renta fija / variable / FCI), así que tampoco se le busca precio automático.
        tipo_inst = (row.get("Tipo Instrumento") or "").strip()
        if not tipo_inst:
            issues.append(ValidationIssue(
                tab="Watchlist", fila=row_num, campo="Tipo Instrumento",
                regla="tipo_instrumento_vacio",
                mensaje="Tipo Instrumento vacío",
                impacto="No se puede buscar el precio automático de este instrumento",
                severidad=Severity.ADVERTENCIA
            ))

        validos.append({
            "ticker": ticker,
            "nombre": row.get("Nombre") or ticker,
            "tipo_instrumento": tipo_inst,
            "mercado": (row.get("Mercado") or "").strip(),
            "moneda": moneda,
            "pais": row.get("País") or row.get("Pais") or None,
            "sector": row.get("Sector") or None,
            "objetivo": objetivo,
        })
        tickers.add(ticker)

    return validos, issues
