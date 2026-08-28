"""Orquesta las fuentes de `market_data` en las estructuras que `inversiones_sync` persiste.

Cada función devuelve (filas, issues) y nunca lanza: si una fuente falla, se reporta como
advertencia y se sigue con lo que sí respondió (o con nada, si todo falló).
"""
from datetime import date

from ...services.validation.types import ValidationIssue, Severity
from . import argentina_datos

BENCHMARK_INFLACION_INDEC = "Inflación (INDEC)"


def fetch_indices_mercado_api(fechas_excluir: set[date]) -> tuple[list[dict] | None, list[ValidationIssue]]:
    """Serie diaria de CER (vía UVA) y MEP para completar `IndiceMercado`.

    `fechas_excluir` son las fechas que ya vienen del Sheet (Movimientos/Precios/Tipos de Cambio):
    esas fechas ganan siempre, la API sólo llena huecos.

    Devuelve None (en vez de lista vacía) cuando NINGUNA de las dos fuentes respondió, para que
    el llamador distinga "no había nada nuevo" de "la API no está disponible ahora mismo" y no
    borre lo que ya se había guardado de una corrida anterior.
    """
    issues: list[ValidationIssue] = []

    uva = argentina_datos.fetch_uva_serie()
    if uva is None:
        issues.append(ValidationIssue(
            tab="CER/MEP (API)", regla="uva_no_disponible",
            mensaje="No se pudo obtener el índice UVA de ArgentinaDatos",
            impacto="Se mantiene el histórico automático de CER previamente guardado, si existía",
            severidad=Severity.ADVERTENCIA,
        ))

    mep = argentina_datos.fetch_dolar_mep_historico()
    if mep is None:
        issues.append(ValidationIssue(
            tab="CER/MEP (API)", regla="mep_no_disponible",
            mensaje="No se pudo obtener el dólar MEP histórico de ArgentinaDatos",
            impacto="Se mantiene el histórico automático de MEP previamente guardado, si existía",
            severidad=Severity.ADVERTENCIA,
        ))

    if uva is None and mep is None:
        return None, issues

    por_fecha: dict[date, dict] = {}
    for fecha, valor in (uva or []):
        if fecha in fechas_excluir:
            continue
        por_fecha.setdefault(fecha, {"fecha": fecha, "cer": None, "mep": None})["cer"] = valor
    for fecha, valor in (mep or []):
        if fecha in fechas_excluir:
            continue
        por_fecha.setdefault(fecha, {"fecha": fecha, "cer": None, "mep": None})["mep"] = valor

    filas = []
    for row in por_fecha.values():
        row["fuente"] = "api"
        filas.append(row)
    return filas, issues


def fetch_benchmarks_api() -> tuple[list[dict] | None, list[ValidationIssue]]:
    """Benchmarks automáticos adicionales para `BenchmarkValor`.

    Hoy sólo Inflación (INDEC): índice mensual construido por interés compuesto sobre la
    variación % mensual publicada. MERVAL y S&P 500 quedaron afuera — no encontramos una API
    gratuita y confiable con nivel histórico de esos índices (ver PLAN, sección "Ola 2").

    Devuelve None (no `[]`) si la fuente falló, para que el llamador no borre el benchmark
    automático de una corrida anterior por una falla de red transitoria.
    """
    issues: list[ValidationIssue] = []
    inflacion = argentina_datos.fetch_inflacion_mensual()
    if inflacion is None:
        issues.append(ValidationIssue(
            tab="Benchmarks (API)", regla="inflacion_no_disponible",
            mensaje="No se pudo obtener la inflación mensual de ArgentinaDatos",
            impacto="Se mantiene el benchmark de inflación automático previamente guardado, si existía",
            severidad=Severity.ADVERTENCIA,
        ))
        return None, issues

    nivel = 100.0
    filas = []
    for fecha, variacion_pct in inflacion:
        nivel = nivel * (1 + variacion_pct / 100.0)
        filas.append({
            "fecha": fecha,
            "benchmark": BENCHMARK_INFLACION_INDEC,
            "valor": nivel,
            "fuente": "api",
        })
    return filas, issues
