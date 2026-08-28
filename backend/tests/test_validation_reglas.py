"""Tests para validación de reglas por pestaña."""
from datetime import date
from backend.app.services.validation.types import Severity
from backend.app.services.validation import (
    reglas_instrumentos,
    reglas_movimientos,
    reglas_precios,
    reglas_objetivos,
    reglas_rebalanceo,
    reglas_benchmarks,
    reglas_configuracion,
    reglas_tipos_cambio,
)


def test_instrumentos_ticker_vacio():
    """Ticker vacío → crítico/drop."""
    rows = [(2, {"Ticker": "", "Nombre": "Test", "Tipo Instrumento": "", "Mercado": "", "Moneda": "ARS"})]
    validos, tickers, issues = reglas_instrumentos.validar_instrumentos(rows)
    assert len(validos) == 0
    assert len(issues) == 1
    assert issues[0].severidad == Severity.CRITICO
    assert "ticker_vacio" in issues[0].regla


def test_instrumentos_ticker_duplicado():
    """Ticker duplicado → crítico/drop segundos."""
    # Tipo Instrumento y Mercado van completos para que el único issue sea el duplicado
    # (vacíos emiten sus propias advertencias de salvage).
    rows = [
        (2, {"Ticker": "AAPL", "Nombre": "Apple 1", "Tipo Instrumento": "Accion", "Mercado": "NYSE", "Moneda": "USD"}),
        (3, {"Ticker": "AAPL", "Nombre": "Apple 2", "Tipo Instrumento": "Accion", "Mercado": "NYSE", "Moneda": "USD"}),
    ]
    validos, tickers, issues = reglas_instrumentos.validar_instrumentos(rows)
    assert len(validos) == 1
    assert validos[0]["nombre"] == "Apple 1"  # gana la primera, se descarta la segunda
    assert "AAPL" in tickers
    assert len(issues) == 1
    assert issues[0].regla == "ticker_duplicado"
    assert issues[0].fila == 3


def test_instrumentos_moneda_invalida():
    """Moneda inválida → crítico/drop."""
    rows = [(2, {"Ticker": "AAPL", "Nombre": "Apple", "Tipo Instrumento": "", "Mercado": "", "Moneda": "EUR"})]
    validos, tickers, issues = reglas_instrumentos.validar_instrumentos(rows)
    assert len(validos) == 0
    assert len(issues) == 1
    assert "moneda_invalida" in issues[0].regla


def test_instrumentos_objetivo_invalido_salvage():
    """Objetivo inválido → advertencia/salvage (instrumento se guarda sin objetivo)."""
    rows = [(2, {
        "Ticker": "AAPL", "Nombre": "Apple", "Tipo Instrumento": "Stock", "Mercado": "NASDAQ",
        "Moneda": "USD", "Objetivo Modo": "Porcentaje", "Objetivo Valor": "no-es-numero"
    })]
    validos, tickers, issues = reglas_instrumentos.validar_instrumentos(rows)
    assert len(validos) == 1
    assert validos[0]["objetivo_modo"] is None
    assert validos[0]["objetivo_valor"] is None
    assert len(issues) == 1
    assert issues[0].severidad == Severity.ADVERTENCIA
    assert "objetivo_invalido" in issues[0].regla


def test_movimientos_precio_negativo():
    """Precio negativo → crítico/drop."""
    rows = [(2, {
        "Fecha": "2024-01-01", "Cartera": "Portfolio1", "Ticker": "AAPL",
        "Tipo Movimiento": "Compra", "Cantidad": "100", "Precio": "-10.5",
        "Moneda": "USD"
    })]
    validos, cer_mep, issues = reglas_movimientos.validar_movimientos(rows, {"AAPL"})
    assert len(validos) == 0
    assert any("precio_negativo" in i.regla for i in issues)


def test_movimientos_comision_negativa():
    """Comisión negativa → crítico/drop."""
    rows = [(2, {
        "Fecha": "2024-01-01", "Cartera": "Portfolio1", "Ticker": "AAPL",
        "Tipo Movimiento": "Compra", "Cantidad": "100", "Precio": "150",
        "Moneda": "USD", "Comisión": "-5"
    })]
    validos, cer_mep, issues = reglas_movimientos.validar_movimientos(rows, {"AAPL"})
    assert len(validos) == 0
    assert any("comision_negativa" in i.regla for i in issues)


def test_precios_precio_cero():
    """Precio == 0 → crítico/drop, igual que un precio negativo.

    Un 0 en la columna Precio del Sheet es casi siempre una celda vacía mal parseada, no una
    cotización real. Dejarlo pasar rompe toda valuación de esa fecha (y los retornos que la
    usan como base), así que se descarta la fila en vez de conservarla con una advertencia.
    """
    rows = [(2, {"Fecha": "2024-01-01", "Ticker": "AAPL", "Precio": "0", "Moneda": "USD"})]
    validos, cer_mep, issues = reglas_precios.validar_precios(rows)
    assert len(validos) == 0
    assert any("precio_no_positivo" in i.regla for i in issues)


def test_precios_precio_negativo():
    """Precio negativo → crítico/drop."""
    rows = [(2, {"Fecha": "2024-01-01", "Ticker": "AAPL", "Precio": "-10", "Moneda": "USD"})]
    validos, cer_mep, issues = reglas_precios.validar_precios(rows)
    assert len(validos) == 0
    assert any("precio_no_positivo" in i.regla for i in issues)


def test_objetivos_monto_invalido():
    """Monto USD inválido → crítico/drop."""
    rows = [(2, {
        "Cartera": "Portfolio1", "Nombre": "Objetivo1", "Monto USD": "no-es-numero",
        "Fecha Límite": "2025-12-31"
    })]
    validos, issues = reglas_objetivos.validar_objetivos(rows, {"Portfolio1"})
    assert len(validos) == 0
    assert any("monto_usd_invalido" in i.regla for i in issues)


def test_rebalanceo_porcentaje_fuera_rango():
    """Porcentaje fuera [0,100] → crítico/drop."""
    rows = [(2, {
        "Cartera": None, "Eje": "Tipo", "Categoría": "Acciones",
        "Porcentaje Objetivo": "150"
    })]
    validos, issues = reglas_rebalanceo.validar_rebalanceo(rows, set(), set())
    assert len(validos) == 0
    assert any("porcentaje_objetivo_invalido" in i.regla for i in issues)


def test_benchmarks_valor_negativo():
    """Valor negativo → crítico/drop."""
    rows = [(2, {"Fecha": "2024-01-01", "Benchmark": "SP500", "Valor": "-100"})]
    validos, issues = reglas_benchmarks.validar_benchmarks(rows)
    assert len(validos) == 0
    assert any("valor_no_positivo" in i.regla for i in issues)


def test_tipos_cambio_ok():
    """Fila válida de CER y de MEP → ambas se parsean con su campo correspondiente."""
    rows = [
        (2, {"Fecha": "2026-02-18", "Tipo": "CER", "Valor": "103.6"}),
        (3, {"Fecha": "2026-02-18", "Tipo": "MEP", "Valor": "818"}),
    ]
    validos, issues = reglas_tipos_cambio.validar_tipos_cambio(rows)
    assert len(validos) == 2
    assert not issues
    campos = {v["campo"]: v["valor"] for v in validos}
    assert campos["cer"] == 103.6
    assert campos["mep"] == 818.0


def test_tipos_cambio_tipo_no_reconocido():
    """Tipo distinto de CER/MEP → advertencia/drop, no bloquea el resto."""
    rows = [(2, {"Fecha": "2026-02-18", "Tipo": "UVA", "Valor": "100"})]
    validos, issues = reglas_tipos_cambio.validar_tipos_cambio(rows)
    assert len(validos) == 0
    assert any("tipo_no_reconocido" in i.regla for i in issues)
    assert issues[0].severidad == Severity.ADVERTENCIA


def test_tipos_cambio_valor_no_positivo():
    """Valor <= 0 → crítico/drop."""
    rows = [(2, {"Fecha": "2026-02-18", "Tipo": "CER", "Valor": "-1"})]
    validos, issues = reglas_tipos_cambio.validar_tipos_cambio(rows)
    assert len(validos) == 0
    assert any("valor_no_positivo" in i.regla for i in issues)
    assert issues[0].severidad == Severity.CRITICO


def test_tipos_cambio_duplicado():
    """Misma fecha+tipo repetida → se descarta la segunda como advertencia."""
    rows = [
        (2, {"Fecha": "2026-02-18", "Tipo": "CER", "Valor": "103.6"}),
        (3, {"Fecha": "2026-02-18", "Tipo": "CER", "Valor": "999"}),
    ]
    validos, issues = reglas_tipos_cambio.validar_tipos_cambio(rows)
    assert len(validos) == 1
    assert validos[0]["valor"] == 103.6
    assert any("valor_duplicado" in i.regla for i in issues)


def test_configuracion_peso_minimo_mayor_maximo():
    """Peso Mín > Peso Máx → advertencia/salvage (anula ambos)."""
    rows = [(2, {
        "Cartera": "Portfolio1", "Peso Máximo": "30", "Peso Mínimo": "50"
    })]
    validos, issues = reglas_configuracion.validar_configuracion(rows)
    assert len(validos) == 1
    assert validos[0]["peso_maximo"] is None
    assert validos[0]["peso_minimo"] is None
    assert any("peso_minimo_mayor_maximo" in i.regla for i in issues)
