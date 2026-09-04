"""La serie de CER se arma con dos fuentes (Sheet y API) y sólo se usa como cociente: si una
fuente trae otra base, contamina el deflactado de todas las fechas vecinas. `reglas_cer` detecta
esas filas por continuidad."""
from datetime import date, timedelta

from app.services.validation.reglas_cer import (
    detectar_cer_fuera_de_serie,
    RATIO_MIN,
    TASA_DIARIA_MAX,
)


def _serie_limpia(n: int = 60, inicio: float = 1000.0, diaria: float = 0.001):
    """CER acumulado creciendo a ritmo constante, un valor por día."""
    d0 = date(2026, 1, 1)
    return [(d0 + timedelta(days=i), inicio * (1 + diaria) ** i) for i in range(n)]


def test_serie_limpia_no_descarta_nada():
    descartadas, issues = detectar_cer_fuera_de_serie(_serie_limpia())
    assert descartadas == set()
    assert issues == []


def test_descarta_valor_en_otra_base():
    """El caso real: filas del Sheet con el CER en otra base (~2,5x más chico)."""
    serie = _serie_limpia()
    fecha_mala = serie[30][0]
    serie[30] = (fecha_mala, serie[30][1] / 2.5253)

    descartadas, issues = detectar_cer_fuera_de_serie(serie)

    assert descartadas == {fecha_mala}
    assert issues[0].regla == "cer_fuera_de_serie"
    assert issues[0].severidad.value == "advertencia"


def test_descarta_error_de_escala():
    """Un CER 1000x (separador de miles mal parseado) rompe la continuidad igual que un cambio
    de base."""
    serie = _serie_limpia()
    fecha_mala = serie[40][0]
    serie[40] = (fecha_mala, serie[40][1] * 1000)

    descartadas, _ = detectar_cer_fuera_de_serie(serie)

    assert descartadas == {fecha_mala}


def test_un_outlier_no_arrastra_a_los_siguientes():
    """El ancla no se mueve cuando un punto se descarta: si se moviera, el outlier pasaría a ser
    la referencia y todo lo posterior caería con él."""
    serie = _serie_limpia()
    fecha_mala = serie[10][0]
    serie[10] = (fecha_mala, 5.0)

    descartadas, _ = detectar_cer_fuera_de_serie(serie)

    assert descartadas == {fecha_mala}


def test_varios_outliers_intercalados():
    serie = _serie_limpia()
    malas = {serie[i][0] for i in (12, 13, 33, 47)}
    for i in (12, 13, 33, 47):
        serie[i] = (serie[i][0], serie[i][1] / 2.5)

    descartadas, issues = detectar_cer_fuera_de_serie(serie)

    assert descartadas == malas
    assert len(issues) == 4


def test_outlier_al_principio_no_arrastra_al_resto():
    """El ancla es el tramo coherente más largo, no el primer punto: una fila mala al inicio no
    puede definir la base de toda la serie."""
    serie = _serie_limpia()
    fecha_mala = serie[0][0]
    serie[0] = (fecha_mala, serie[0][1] * 500)

    descartadas, _ = detectar_cer_fuera_de_serie(serie)

    assert descartadas == {fecha_mala}


def test_cer_nunca_baja():
    """El CER es acumulado: una baja es dato malo, por chica que sea."""
    serie = _serie_limpia()
    fecha_mala = serie[20][0]
    serie[20] = (fecha_mala, serie[19][1] * (RATIO_MIN - 0.01))

    descartadas, _ = detectar_cer_fuera_de_serie(serie)

    assert fecha_mala in descartadas


def test_acepta_salto_inflacionario_real():
    """Marzo/2024: el CER llegó a subir 3,73% en un día. No es un error de datos."""
    serie = _serie_limpia()
    serie[25] = (serie[25][0], serie[24][1] * 1.0373)
    for i in range(26, len(serie)):
        serie[i] = (serie[i][0], serie[i - 1][1] * 1.001)

    descartadas, _ = detectar_cer_fuera_de_serie(serie)

    assert descartadas == set()


def test_el_limite_diario_se_compone_en_los_huecos():
    """Con un hueco de varios días el techo acompaña: la serie no siempre es diaria."""
    d0 = date(2026, 1, 1)
    serie = [(d0, 1000.0), (d0 + timedelta(days=10), 1000.0 * (1 + TASA_DIARIA_MAX) ** 9)]
    serie += [(d0 + timedelta(days=10 + i), serie[1][1]) for i in range(1, 5)]

    descartadas, _ = detectar_cer_fuera_de_serie(serie)

    assert descartadas == set()


def test_serie_demasiado_corta_no_se_juzga():
    """Con dos puntos no hay serie contra la cual medir continuidad."""
    assert detectar_cer_fuera_de_serie([(date(2026, 1, 1), 1.0), (date(2026, 1, 2), 900.0)]) == (set(), [])
