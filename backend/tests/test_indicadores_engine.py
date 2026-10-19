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


# ── extremos ──────────────────────────────────────────────────────────────────

def test_extremos_ventana_fija_valores_a_mano():
    # cierres con OHLC degradado a (cierre, cierre): la ventana de 3 toma max/min de los cierres.
    cierres = [10.0, 12.0, 11.0, 9.0, 13.0, 8.0]
    barras = _barras(cierres)
    out = ie.extremos(barras, ventana=3)
    assert out["maximo"][:2] == [None, None]        # rodante: None hasta ventana completa
    assert out["maximo"][2] == pytest.approx(12.0)  # max(10,12,11)
    assert out["minimo"][2] == pytest.approx(10.0)
    assert out["medio"][2] == pytest.approx(11.0)
    assert out["maximo"][3] == pytest.approx(12.0)  # max(12,11,9)
    assert out["minimo"][4] == pytest.approx(9.0)   # min(11,9,13)
    assert out["maximo"][5] == pytest.approx(13.0)  # max(9,13,8)
    for salida in out:
        assert len(out[salida]) == len(barras)


def test_extremos_usa_ohlc_cuando_esta():
    cierres = [10.0, 10.0, 10.0]
    maximos = [11.0, 15.0, 12.0]
    minimos = [8.0, 9.0, 7.0]
    barras = _barras(cierres, maximo=maximos, minimo=minimos)
    out = ie.extremos(barras, ventana=3)
    assert out["maximo"][2] == pytest.approx(15.0)  # del máximo de la vela, no del cierre
    assert out["minimo"][2] == pytest.approx(7.0)


def test_extremos_ventana_cero_es_acumulada_desde_el_inicio():
    cierres = [10.0, 8.0, 12.0, 9.0, 15.0, 5.0]
    barras = _barras(cierres)
    out = ie.extremos(barras, ventana=0)
    # Definido desde la barra 0; la primera barra es máximo y mínimo a la vez.
    assert out["maximo"][0] == pytest.approx(10.0)
    assert out["minimo"][0] == pytest.approx(10.0)
    assert out["dist_min_pct"][0] == pytest.approx(0.0)
    assert out["dist_max_pct"][0] == pytest.approx(0.0)
    assert out["maximo"] == pytest.approx([10, 10, 12, 12, 15, 15])
    assert out["minimo"] == pytest.approx([10, 8, 8, 8, 8, 5])


def test_extremos_signos_de_dist_pct_y_cero_en_el_extremo_nuevo():
    cierres = [10.0, 20.0, 5.0]  # barra 1 = máximo nuevo, barra 2 = mínimo nuevo
    barras = _barras(cierres)
    out = ie.extremos(barras, ventana=0)
    assert out["dist_max_pct"][1] == pytest.approx(0.0)     # cierra en el máximo
    assert out["dist_min_pct"][1] > 0                        # por encima del mínimo histórico
    assert out["dist_min_pct"][2] == pytest.approx(0.0)     # cierra en el mínimo
    assert out["dist_max_pct"][2] < 0                        # por debajo del máximo histórico


def test_extremos_maximo_sube_solo_en_maximo_nuevo():
    # Respalda el modismo `{"op":"subiendo","operando":{"ref":..,"salida":"maximo"}}` para
    # "hoy hizo máximo nuevo".
    cierres = [10.0, 12.0, 11.0, 15.0, 14.0]
    barras = _barras(cierres)
    maximo = ie.extremos(barras, ventana=0)["maximo"]
    subio = [maximo[i] > maximo[i - 1] for i in range(1, len(maximo))]
    assert subio == [True, False, True, False]


def test_extremos_dist_pct_none_si_denominador_cero():
    barras = _barras([0.0, 0.0, 0.0])
    out = ie.extremos(barras, ventana=0)
    assert out["dist_max_pct"] == [None, None, None]
    assert out["dist_min_pct"] == [None, None, None]


# ── percentil ─────────────────────────────────────────────────────────────────

def test_percentil_cero_en_el_minimo_y_cien_en_el_maximo():
    cierres = [50.0, 10.0, 30.0, 20.0, 40.0]
    out = ie.percentil(cierres, ventana=0)
    assert out[0] is None            # 1 solo dato: rank indefinido
    assert out[1] == pytest.approx(0.0)      # 10 es el mínimo de {50,10}
    assert out[-1] == pytest.approx(75.0)    # 40: 3 de {50,10,30,20} son menores -> 3/4*100
    creciente = ie.percentil([1.0, 2.0, 3.0, 4.0, 5.0], ventana=0)
    assert creciente[-1] == pytest.approx(100.0)  # el máximo


def test_percentil_empates_no_cuentan_como_menor():
    # cuatro valores iguales y uno mayor: el mayor tiene rank 100, los iguales rank 0.
    out = ie.percentil([5.0, 5.0, 5.0, 5.0, 9.0], ventana=0)
    assert out[3] == pytest.approx(0.0)      # ningún 5 es < 5
    assert out[4] == pytest.approx(100.0)    # los cuatro 5 son < 9 -> 4/4*100


def test_percentil_rodante_none_hasta_ventana_completa():
    cierres = [float(i) for i in range(10)]
    out = ie.percentil(cierres, ventana=5)
    assert out[:4] == [None, None, None, None]
    assert out[4] is not None
    assert len(out) == len(cierres)


# ── retorno ───────────────────────────────────────────────────────────────────

def test_retorno_serie_mas_corta_que_periodo_todo_none():
    assert ie.retorno([100.0, 101.0, 102.0], periodo=20) == [None, None, None]


def test_retorno_valor_a_mano():
    cierres = [100.0, 110.0, 121.0]
    out = ie.retorno(cierres, periodo=1)
    assert out[0] is None
    assert out[1] == pytest.approx(10.0)
    assert out[2] == pytest.approx(10.0)
    assert ie.retorno([0.0, 100.0, 50.0], periodo=2)[2] is None  # cierre[i-periodo] == 0


# ── clave / parsear_clave ──────────────────────────────────────────────────────

def test_clave_y_parsear_clave_son_inversas():
    casos = [
        ("SMA", {"periodo": 50}),
        ("MACD", {"rapida": 12, "lenta": 26, "senal": 9}),
        ("BOLLINGER", {"periodo": 20, "desvios": 2.0}),
        ("OBV", {}),
        ("EXTREMOS", {"ventana": 0}),
        ("EXTREMOS", {"ventana": 20}),
        ("PERCENTIL", {"ventana": 100}),
        ("RETORNO", {"periodo": 20}),
        ("ADX", {"periodo": 14}),
        ("SUPERTREND", {"periodo": 10, "multiplicador": 3.0}),
        ("SUPERTREND", {"periodo": 7, "multiplicador": 1.5}),
        ("KELTNER", {"periodo": 20, "multiplicador": 2.0}),
        ("ICHIMOKU", {"tenkan": 9, "kijun": 26, "senkou": 52}),
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


# ── ADX / SuperTrend / Keltner / Ichimoku ─────────────────────────────────────

# Máximos, mínimos y cierres de la serie corta usada para calcular a mano.
_H = [10, 12, 13, 12, 14, 9, 8]
_L = [8, 9, 10, 9, 11, 6, 5]
_C = [9, 11, 12, 10, 13, 7, 6]


def _ohlc():
    return _barras([float(c) for c in _C], maximo=[float(h) for h in _H], minimo=[float(l) for l in _L])


def test_adx_valores_a_mano():
    # TR = [-, 3, 3, 3, 4]; +DM = [-, 2, 1, 0, 2]; -DM = [-, 0, 0, 1, 0]. Con periodo 2, Wilder:
    # i=2: sTR=6, s+=3, s-=0 → +DI=50, -DI=0, DX=100.   i=3: sTR=6, s+=1.5, s-=1 → +DI=25, -DI=16.67, DX=20.
    # ADX(3) = (100+20)/2 = 60.   i=4: sTR=7, s+=2.75, s-=0.5 → DX=69.23; ADX(4) = (60+69.23)/2.
    out = ie.adx(_ohlc()[:5], periodo=2)
    assert out["di_mas"][:2] == [None, None] and out["adx"][:3] == [None, None, None]
    assert out["di_mas"][2] == pytest.approx(50.0) and out["di_menos"][2] == pytest.approx(0.0)
    assert out["di_mas"][3] == pytest.approx(25.0) and out["di_menos"][3] == pytest.approx(100 / 6)
    assert out["adx"][3] == pytest.approx(60.0)
    assert out["di_mas"][4] == pytest.approx(100 * 2.75 / 7) and out["di_menos"][4] == pytest.approx(100 * 0.5 / 7)
    assert out["adx"][4] == pytest.approx((60.0 + 100 * 2.25 / 3.25) / 2)


def test_adx_serie_corta_devuelve_none():
    out = ie.adx(_ohlc()[:2], periodo=5)
    assert out["adx"] == [None, None] and out["di_mas"] == [None, None]


def test_adx_tendencia_limpia_tiende_a_100():
    cierres = [float(100 + 2 * i) for i in range(60)]
    barras = _barras(cierres, maximo=[c + 1 for c in cierres], minimo=[c - 1 for c in cierres])
    out = ie.adx(barras, periodo=14)
    assert out["adx"][-1] > 90 and out["di_menos"][-1] == pytest.approx(0.0)


def test_supertrend_valores_a_mano_y_cambio_de_direccion():
    # ATR(2) = [-, -, 3, 3, 3.5, 5.25, 4.125]; multiplicador 1.
    out = ie.supertrend(_ohlc(), periodo=2, multiplicador=1.0)
    assert out["valor"][:2] == [None, None] and out["direccion"][:2] == [None, None]
    assert out["direccion"][2:5] == [1.0, 1.0, 1.0]
    assert out["valor"][2] == pytest.approx(8.5)      # banda inferior: 11.5 − 3
    assert out["valor"][3] == pytest.approx(8.5)      # la inferior no baja
    assert out["valor"][4] == pytest.approx(9.0)      # sube con el precio: 12.5 − 3.5
    # En i=5 el cierre (7) perfora la inferior (9): pasa a bajista y la línea es la banda superior.
    assert out["direccion"][5] == -1.0 and out["valor"][5] == pytest.approx(12.75)
    assert out["direccion"][6] == -1.0 and out["valor"][6] == pytest.approx(10.625)   # la superior no sube


def test_supertrend_el_primer_valor_no_es_un_cruce():
    out = ie.supertrend(_ohlc(), periodo=2, multiplicador=1.0)
    assert out["direccion"][1] is None and out["direccion"][2] == 1.0   # None → +1: no hay cruce de 0


def test_keltner_valores_a_mano():
    barras = _ohlc()
    out = ie.keltner(barras, periodo=2, multiplicador=2.0)
    # EMA(2) con semilla SMA: i=1 → 10; i=2 → 10 + (12−10)·2/3. ATR(2) en i=2 = 3.
    assert out["media"][:2] == [None, None]
    media = 10 + 2 * 2 / 3
    assert out["media"][2] == pytest.approx(media)
    assert out["superior"][2] == pytest.approx(media + 6)
    assert out["inferior"][2] == pytest.approx(media - 6)


def test_ichimoku_valores_a_mano_y_alineacion():
    cierres = [10.0, 12.0, 11.0, 9.0, 13.0, 8.0, 14.0, 15.0]
    out = ie.ichimoku(_barras(cierres), tenkan=2, kijun=3, senkou=4)
    assert out["tenkan"][1] == pytest.approx(11.0) and out["tenkan"][7] == pytest.approx(14.5)
    assert out["kijun"][2] == pytest.approx(11.0) and out["kijun"][7] == pytest.approx(11.5)
    # Las nubes se desplazan `kijun` (3) barras: lo calculado en i−3 aplica en i.
    assert out["senkou_a"][:5] == [None] * 5
    assert out["senkou_a"][5] == pytest.approx(11.25)   # (tenkan 11.5 + kijun 11) / 2 calculado en i=2
    assert out["senkou_a"][6] == pytest.approx(10.25)
    assert out["senkou_b"][5] is None and out["senkou_b"][6] == pytest.approx(10.5)
    assert out["senkou_b"][7] == pytest.approx(11.0)


def test_ichimoku_sin_lookahead():
    cierres = [float(100 + ((i * 7) % 13)) for i in range(80)]
    completa = ie.ichimoku(_barras(cierres))
    for corte in (50, 65):
        parcial = ie.ichimoku(_barras(cierres[:corte]))
        for salida in completa:
            assert parcial[salida] == completa[salida][:corte]


@pytest.mark.parametrize("nombre", ["ADX", "SUPERTREND", "KELTNER", "ICHIMOKU"])
def test_indicadores_nuevos_respetan_su_warm_up(nombre):
    barras = _barras([float(100 + ((i * 3) % 11)) for i in range(200)],
                     maximo=[float(101 + ((i * 3) % 11)) for i in range(200)],
                     minimo=[float(99 + ((i * 3) % 11)) for i in range(200)])
    out = ie.calcular(nombre, barras)
    warm = ie.warm_up_barras(nombre)
    for salida, serie in out.items():
        primero = next((i for i, v in enumerate(serie) if v is not None), None)
        assert primero is not None and primero <= warm, (nombre, salida, primero, warm)
