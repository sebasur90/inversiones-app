"""Tests numéricos del motor puro de indicadores técnicos (services/indicadores_engine.py)."""
from datetime import date, timedelta

import pytest

from app.services import indicadores_engine as ie


def _barras(cierres, apertura=None, maximo=None, minimo=None, volumen=None):
    base = date(2024, 1, 1)
    out = []
    for i, c in enumerate(cierres):
        out.append(ie.Barra(
            fecha=base + timedelta(days=i),
            cierre=c,
            apertura=apertura[i] if apertura else None,
            maximo=maximo[i] if maximo else None,
            minimo=minimo[i] if minimo else None,
            volumen=volumen[i] if volumen else None,
        ))
    return out


# ── sma / ema ─────────────────────────────────────────────────────────────────

def test_sma_valores_a_mano_y_largo_warmup():
    valores = [1, 2, 3, 4, 5, 6]
    out = ie.sma(valores, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)   # (1+2+3)/3
    assert out[3] == pytest.approx(3.0)   # (2+3+4)/3
    assert out[5] == pytest.approx(5.0)   # (4+5+6)/3
    assert len(out) == len(valores)


def test_ema_semilla_es_sma_y_largo_correcto():
    valores = [1, 2, 3, 4, 5]
    out = ie.ema(valores, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)  # semilla = SMA(1,2,3)
    k = 2 / 4
    esperado_3 = 4 * k + 2.0 * (1 - k)
    assert out[3] == pytest.approx(esperado_3)
    assert len(out) == len(valores)


def test_sma_serie_mas_corta_que_periodo_es_todo_none():
    assert ie.sma([1, 2], 5) == [None, None]


# ── rsi ───────────────────────────────────────────────────────────────────────

def test_rsi_secuencia_canonica_de_wilder():
    # Secuencia clásica usada en el ejemplo de Wilder (14 períodos), precios de cierre.
    cierres = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
    ]
    out = ie.rsi(cierres, periodo=14)
    assert out[:14] == [None] * 14
    assert out[14] is not None
    assert out[14] == pytest.approx(70.53, abs=0.5)


def test_rsi_bordes_avg_loss_cero_y_avg_gain_cero():
    subiendo = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    out = ie.rsi(subiendo, periodo=14)
    assert out[14] == pytest.approx(100.0)

    bajando = list(reversed(subiendo))
    out2 = ie.rsi(bajando, periodo=14)
    assert out2[14] == pytest.approx(0.0)


def test_rsi_serie_corta_todo_none():
    assert ie.rsi([1.0, 2.0, 3.0], periodo=14) == [None, None, None]


# ── macd ──────────────────────────────────────────────────────────────────────

def test_macd_histograma_es_macd_menos_senal():
    cierres = [float(10 + i + (i % 5)) for i in range(60)]
    out = ie.macd(cierres, rapida=12, lenta=26, senal=9)
    assert set(out.keys()) == {"macd", "senal", "histograma"}
    for m, s, h in zip(out["macd"], out["senal"], out["histograma"]):
        if m is None or s is None:
            assert h is None
        else:
            assert h == pytest.approx(m - s)
    assert len(out["macd"]) == len(cierres)


# ── bollinger ─────────────────────────────────────────────────────────────────

def test_bollinger_serie_constante_bandas_iguales():
    cierres = [100.0] * 25
    out = ie.bollinger(cierres, periodo=20, desvios=2.0)
    for i in range(19, 25):
        assert out["media"][i] == pytest.approx(100.0)
        assert out["superior"][i] == pytest.approx(100.0)
        assert out["inferior"][i] == pytest.approx(100.0)
        assert out["ancho_pct"][i] == pytest.approx(0.0)
    assert len(out["media"]) == len(cierres)


def test_bollinger_warmup_none_antes_del_periodo():
    cierres = [float(100 + i) for i in range(19)]
    out = ie.bollinger(cierres, periodo=20)
    assert out["media"] == [None] * 19


# ── atr ───────────────────────────────────────────────────────────────────────

def test_atr_close_only_igual_a_wilder_de_delta_cierre_absoluto():
    cierres = [100.0, 102.0, 101.0, 105.0, 103.0, 108.0, 107.0, 106.0, 110.0, 111.0,
               109.0, 112.0, 114.0, 113.0, 115.0]
    barras = _barras(cierres)
    out = ie.atr(barras, periodo=14)
    assert out[:14] == [None] * 14

    deltas_abs = [abs(cierres[i] - cierres[i - 1]) for i in range(1, len(cierres))]
    avg = sum(deltas_abs[:14]) / 14
    assert out[14] == pytest.approx(avg)


def test_atr_con_ohlc_respeta_true_range():
    cierres = [100.0] * 16
    maximos = [101.0] * 16
    minimos = [99.0] * 16
    barras = _barras(cierres, maximo=maximos, minimo=minimos)
    out = ie.atr(barras, periodo=14)
    assert out[14] == pytest.approx(2.0)


# ── estocastico ───────────────────────────────────────────────────────────────

def test_estocastico_k_y_d_en_rango_0_100():
    cierres = [float(100 + ((i * 7) % 13) - 6) for i in range(40)]
    barras = _barras(cierres)
    out = ie.estocastico(barras, periodo_k=14, suavizado_k=3, periodo_d=3)
    for v in out["k"]:
        if v is not None:
            assert 0.0 <= v <= 100.0
    for v in out["d"]:
        if v is not None:
            assert 0.0 <= v <= 100.0
    assert len(out["k"]) == len(cierres)


# ── obv / volumen_promedio ─────────────────────────────────────────────────────

def test_obv_acumula_signo_de_la_variacion():
    cierres = [10.0, 11.0, 10.5, 12.0]
    volumenes = [100.0, 100.0, 100.0, 100.0]
    barras = _barras(cierres, volumen=volumenes)
    out = ie.obv(barras)
    assert out == [0.0, 100.0, 0.0, 100.0]


def test_obv_sin_volumen_es_todo_none():
    barras = _barras([10.0, 11.0, 12.0])
    assert ie.obv(barras) == [None, None, None]


def test_volumen_promedio_degrada_a_none_sin_datos():
    barras = _barras([10.0] * 25)
    assert ie.volumen_promedio(barras, periodo=20) == [None] * 25


# ── registro INDICADORES: invariante de alineación ────────────────────────────

@pytest.mark.parametrize("nombre", list(ie.INDICADORES.keys()))
def test_invariante_longitud_igual_a_entrada_para_todo_indicador(nombre):
    cierres = [float(100 + ((i * 3) % 11) - 5) for i in range(60)]
    maximos = [c + 1.0 for c in cierres]
    minimos = [c - 1.0 for c in cierres]
    volumenes = [float(1000 + i) for i in range(60)]
    barras = _barras(cierres, maximo=maximos, minimo=minimos, volumen=volumenes)

    resultado = ie.calcular(nombre, barras)
    espec = ie.INDICADORES[nombre]
    assert set(resultado.keys()) == set(espec.salidas)
    for salida in espec.salidas:
        assert len(resultado[salida]) == len(barras)


# ── clave / parsear_clave ──────────────────────────────────────────────────────

def test_clave_y_parsear_clave_son_inversas():
    casos = [
        ("SMA", {"periodo": 50}),
        ("MACD", {"rapida": 12, "lenta": 26, "senal": 9}),
        ("BOLLINGER", {"periodo": 20, "desvios": 2.0}),
        ("OBV", {}),
    ]
    for nombre, params in casos:
        s = ie.clave(nombre, params)
        nombre2, params2 = ie.parsear_clave(s)
        assert nombre2 == nombre
        assert params2 == params


def test_clave_formatea_sin_decimales_espurios():
    assert ie.clave("SMA", {"periodo": 50}) == "SMA(50)"
    assert ie.clave("MACD", {"rapida": 12, "lenta": 26, "senal": 9}) == "MACD(12,26,9)"
    assert ie.clave("OBV") == "OBV"


def test_parsear_clave_invalida_lanza_valueerror():
    with pytest.raises(ValueError):
        ie.parsear_clave("NOEXISTE(1)")
    with pytest.raises(ValueError):
        ie.parsear_clave("SMA(1,2)")
    with pytest.raises(ValueError):
        ie.parsear_clave("no es una clave")


def test_warm_up_barras():
    assert ie.warm_up_barras("SMA", {"periodo": 50}) == 50
    assert ie.warm_up_barras("RSI", {"periodo": 14}) == 15
    assert ie.warm_up_barras("MACD", {"rapida": 12, "lenta": 26, "senal": 9}) == 35
