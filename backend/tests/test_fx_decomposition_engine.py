"""Tests para fx_decomposition_engine.py (motor puro sin BD)."""
import pytest
from app.services.fx_decomposition_engine import (
    descomponer_retorno_periodo,
    descomponer_retorno_posicion,
    TOLERANCIA_IDENTIDAD_FX,
)


class TestDescomponerRetornoPeriodo:
    """Tests para descomponer_retorno_periodo (nivel cartera)."""

    def test_ok_identidad_exacta(self):
        """Caso base: identidad TWR verificada."""
        twr_usd = 0.15
        mep_inicio = 900.0
        mep_fin = 1020.0  # 13.33% de suba
        efecto_fx_esperado = mep_fin / mep_inicio - 1
        twr_ars_esperado = (1 + twr_usd) * (1 + efecto_fx_esperado) - 1

        resultado = descomponer_retorno_periodo(
            twr_ars=twr_ars_esperado,
            twr_usd=twr_usd,
            mep_inicio=mep_inicio,
            mep_fin=mep_fin,
        )

        assert resultado["estado"] == "ok"
        assert resultado["retorno_total_ars_pct"] == pytest.approx(twr_ars_esperado)
        assert resultado["retorno_activo_pct"] == pytest.approx(twr_usd)
        assert resultado["efecto_fx_pct"] == pytest.approx(efecto_fx_esperado)
        assert resultado["identidad_verificada"] is True
        assert resultado["mep_inicio"] == mep_inicio
        assert resultado["mep_fin"] == mep_fin

    def test_ok_identidad_rota_dentro_tolerancia(self):
        """Identidad ligeramente rota (pequeños redondeos) pero dentro tolerancia."""
        twr_usd = 0.15
        mep_inicio = 900.0
        mep_fin = 1020.0
        efecto_fx = mep_fin / mep_inicio - 1
        twr_ars_exacto = (1 + twr_usd) * (1 + efecto_fx) - 1
        twr_ars_redondeado = round(twr_ars_exacto, 4) + 0.0001

        resultado = descomponer_retorno_periodo(
            twr_ars=twr_ars_redondeado,
            twr_usd=twr_usd,
            mep_inicio=mep_inicio,
            mep_fin=mep_fin,
            tolerancia=TOLERANCIA_IDENTIDAD_FX,
        )

        assert resultado["estado"] == "ok"
        assert resultado["identidad_verificada"] is True

    def test_ok_identidad_rota_fuera_tolerancia(self):
        """Identidad rota significativamente (precio_faltante, etc.) pero devuelve números."""
        twr_usd = 0.15
        mep_inicio = 900.0
        mep_fin = 1020.0
        efecto_fx = mep_fin / mep_inicio - 1
        twr_ars_exacto = (1 + twr_usd) * (1 + efecto_fx) - 1
        twr_ars_roto = twr_ars_exacto + 0.05

        resultado = descomponer_retorno_periodo(
            twr_ars=twr_ars_roto,
            twr_usd=twr_usd,
            mep_inicio=mep_inicio,
            mep_fin=mep_fin,
            tolerancia=TOLERANCIA_IDENTIDAD_FX,
        )

        assert resultado["estado"] == "ok"
        assert resultado["identidad_verificada"] is False
        assert resultado["retorno_total_ars_pct"] == pytest.approx(twr_ars_roto)

    def test_datos_insuficientes_twr_ars_none(self):
        """TWR ARS falta → datos_insuficientes."""
        resultado = descomponer_retorno_periodo(
            twr_ars=None,
            twr_usd=0.15,
            mep_inicio=900.0,
            mep_fin=1020.0,
        )

        assert resultado["estado"] == "datos_insuficientes"
        assert resultado["retorno_total_ars_pct"] is None
        assert resultado["efecto_fx_pct"] is None

    def test_datos_insuficientes_twr_usd_none(self):
        """TWR USD falta → datos_insuficientes."""
        resultado = descomponer_retorno_periodo(
            twr_ars=0.32,
            twr_usd=None,
            mep_inicio=900.0,
            mep_fin=1020.0,
        )

        assert resultado["estado"] == "datos_insuficientes"
        assert resultado["retorno_total_ars_pct"] is None

    def test_mep_faltante_inicio(self):
        """MEP inicio falta → mep_faltante."""
        resultado = descomponer_retorno_periodo(
            twr_ars=0.32,
            twr_usd=0.15,
            mep_inicio=None,
            mep_fin=1020.0,
        )

        assert resultado["estado"] == "mep_faltante"
        assert resultado["efecto_fx_pct"] is None
        assert resultado["mep_inicio"] is None
        assert resultado["retorno_total_ars_pct"] == 0.32
        assert resultado["retorno_activo_pct"] == 0.15

    def test_mep_faltante_fin(self):
        """MEP fin falta → mep_faltante."""
        resultado = descomponer_retorno_periodo(
            twr_ars=0.32,
            twr_usd=0.15,
            mep_inicio=900.0,
            mep_fin=None,
        )

        assert resultado["estado"] == "mep_faltante"
        assert resultado["efecto_fx_pct"] is None
        assert resultado["mep_fin"] is None

    def test_negativo_retorno_activos(self):
        """Retorno negativo de activos con suba de MEP."""
        twr_usd = -0.10
        mep_inicio = 900.0
        mep_fin = 1020.0
        efecto_fx = mep_fin / mep_inicio - 1
        twr_ars = (1 + twr_usd) * (1 + efecto_fx) - 1

        resultado = descomponer_retorno_periodo(
            twr_ars=twr_ars,
            twr_usd=twr_usd,
            mep_inicio=mep_inicio,
            mep_fin=mep_fin,
        )

        assert resultado["estado"] == "ok"
        assert resultado["retorno_activo_pct"] == pytest.approx(twr_usd)
        assert resultado["efecto_fx_pct"] == pytest.approx(efecto_fx)


class TestDescomponerRetornoPosicion:
    """Tests para descomponer_retorno_posicion (nivel posición)."""

    def test_ok_moneda_ars(self):
        """Posición en ARS con MEP disponible."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=0.20,
            rendimiento_simple_usd=0.05,
            moneda="ARS",
            mep_promedio_compra=900.0,
            mep_actual=1020.0,
        )

        assert resultado["estado"] == "ok"
        assert resultado["rendimiento_simple_ars_pct"] == 0.20
        assert resultado["rendimiento_simple_usd_pct"] == 0.05
        assert resultado["efecto_fx_pct"] == pytest.approx(0.13333, abs=1e-4)
        assert resultado["retorno_activo_pct"] == 0.05
        assert resultado["aproximado"] is True

    def test_ok_moneda_usd(self):
        """Posición en USD (efecto FX debe ser cero o mínimo)."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=0.10,
            rendimiento_simple_usd=0.10,
            moneda="USD",
            mep_promedio_compra=900.0,
            mep_actual=900.0,
        )

        assert resultado["estado"] == "ok"
        assert resultado["efecto_fx_pct"] == pytest.approx(0.0)
        assert resultado["retorno_activo_pct"] == 0.10

    def test_moneda_desconocida(self):
        """Moneda inválida → moneda_desconocida."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=0.20,
            rendimiento_simple_usd=0.05,
            moneda="EUR",
            mep_promedio_compra=900.0,
            mep_actual=1020.0,
        )

        assert resultado["estado"] == "moneda_desconocida"
        assert resultado["rendimiento_simple_ars_pct"] is None
        assert resultado["efecto_fx_pct"] is None

    def test_datos_insuficientes_rendimiento_ars_none(self):
        """Rendimiento ARS falta → datos_insuficientes."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=None,
            rendimiento_simple_usd=0.05,
            moneda="ARS",
            mep_promedio_compra=900.0,
            mep_actual=1020.0,
        )

        assert resultado["estado"] == "datos_insuficientes"
        assert resultado["efecto_fx_pct"] is None

    def test_datos_insuficientes_rendimiento_usd_none(self):
        """Rendimiento USD falta → datos_insuficientes."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=0.20,
            rendimiento_simple_usd=None,
            moneda="ARS",
            mep_promedio_compra=900.0,
            mep_actual=1020.0,
        )

        assert resultado["estado"] == "datos_insuficientes"
        assert resultado["efecto_fx_pct"] is None

    def test_mep_faltante_promedio_compra(self):
        """MEP promedio compra falta → mep_faltante."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=0.20,
            rendimiento_simple_usd=0.05,
            moneda="ARS",
            mep_promedio_compra=None,
            mep_actual=1020.0,
        )

        assert resultado["estado"] == "mep_faltante"
        assert resultado["efecto_fx_pct"] is None
        assert resultado["rendimiento_simple_ars_pct"] == 0.20

    def test_mep_faltante_actual(self):
        """MEP actual falta → mep_faltante."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=0.20,
            rendimiento_simple_usd=0.05,
            moneda="ARS",
            mep_promedio_compra=900.0,
            mep_actual=None,
        )

        assert resultado["estado"] == "mep_faltante"
        assert resultado["efecto_fx_pct"] is None

    def test_negativo_rendimiento(self):
        """Rendimiento negativo → debe calcularse igual."""
        resultado = descomponer_retorno_posicion(
            rendimiento_simple_ars=-0.10,
            rendimiento_simple_usd=-0.20,
            moneda="ARS",
            mep_promedio_compra=900.0,
            mep_actual=1020.0,
        )

        assert resultado["estado"] == "ok"
        assert resultado["rendimiento_simple_ars_pct"] == -0.10
        assert resultado["rendimiento_simple_usd_pct"] == -0.20
