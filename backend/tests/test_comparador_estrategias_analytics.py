"""comparar_estrategias: adaptador Session/DB del comparador (services/
comparador_estrategias_analytics.py). Valores esperados calculados a mano (ver comentarios);
misma convención que `test_costo_oportunidad_analytics.py`.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import (
    Base, BarraOHLCV, EstrategiaTecnica, InstrumentoInversion, PrecioInstrumento, WatchlistItem,
)
from app.services.comparador_estrategias_analytics import comparar_estrategias

# ── Serie determinística de 30 ruedas: plana, sube, baja ────────────────────────────────────────
# idx 0-9: 100 (flat) | idx 10-19: 102..120 (+2/rueda) | idx 20-29: 117..90 (-3/rueda)
CIERRES = [100] * 10 + [100 + (i - 9) * 2 for i in range(10, 20)] + [120 - (i - 19) * 3 for i in range(20, 30)]
BASE_FECHA = date(2024, 1, 1)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _instrumento(db, ticker, moneda="USD"):
    db.add(InstrumentoInversion(ticker=ticker, nombre=ticker, tipo_instrumento="Accion", mercado="NYSE", moneda=moneda))


def _cargar_serie(db, ticker, cierres, base_fecha=BASE_FECHA, moneda="USD"):
    for i, c in enumerate(cierres):
        db.add(PrecioInstrumento(ticker=ticker, fecha=base_fecha + timedelta(days=i), precio=float(c), moneda=moneda, fuente="sheet"))


def _dsl(entrada, salida=None, indicadores=None, comision_pct=0.0, ticker=None):
    return {
        "version": 1,
        "indicadores": indicadores or [],
        "entrada": entrada,
        "salida": salida,
        "riesgo": {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": {"lado": "long", "comision_pct": comision_pct, "precio_ejecucion": "cierre", "demora_barras": 0},
    }


def _guardar_estrategia(db, nombre, dsl, ticker=None, variante="local") -> int:
    ahora = datetime.utcnow()
    e = EstrategiaTecnica(
        nombre=nombre, descripcion=None, ticker=ticker, tipo_preset=None, definicion=dsl,
        variante=variante, fecha_creacion=ahora, fecha_actualizacion=ahora,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e.id


# Estrategia A: entra cuando cierre > 110 (idx15, precio 112), sale cuando cierre < 95 (idx28, 93).
DSL_A = _dsl(
    {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 110}},
    {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 95}},
)
# Estrategia B: entra cuando cierre > 100 (idx10, precio 102), sale cuando cierre < 100 (idx26, 99).
DSL_B = _dsl(
    {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 100}},
    {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 100}},
)
# Nunca dispara: sin señales en toda la serie.
DSL_SIN_SENALES = _dsl({"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 999_999}})


class TestPuntosDelPedido:
    """Los 14 puntos del pedido + los anti-error de fechas y volatilidad."""

    def test_1_dos_filas_mismo_eje_de_fechas_y_largo_de_curva(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        id_b = _guardar_estrategia(db, "B", DSL_B)

        r = comparar_estrategias("AAA", (id_a, id_b), db)
        assert r["estado"] == "ok"
        filas = {f["estrategia_id"]: f for f in r["filas"]}
        assert set(filas.keys()) == {None, id_a, id_b}  # None = Comprar y mantener
        largo = len(r["fechas"])
        for f in r["filas"]:
            assert len(f["curva"]) == largo

    def test_2_diferencia_relativa_pct(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("AAA", (id_a,), db)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_a)
        # A: -16.9643%, B&H: -10.0% -> relativa = ((1-0.169643)/(1-0.10) - 1) * 100
        assert fila["diferencia_relativa_pct"] == pytest.approx(-7.7381, abs=1e-3)

    def test_3_diferencia_en_pp(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_b = _guardar_estrategia(db, "B", DSL_B)
        r = comparar_estrategias("AAA", (id_b,), db)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_b)
        # B: -2.9412%, B&H: -10.0% -> pp = -2.9412 - (-10.0) = 7.0588
        assert fila["diferencia_pp"] == pytest.approx(7.0588, abs=1e-3)

    def test_4_diferencia_monetaria(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("AAA", (id_a,), db, capital_inicial=1_000_000.0)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_a)
        assert fila["diferencia_monetaria"] == pytest.approx(-69643.0, abs=1.0)

    def test_5_capital_inicial_configurable_escala_capital_no_retorno(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r1 = comparar_estrategias("AAA", (id_a,), db, capital_inicial=1_000_000.0)
        r2 = comparar_estrategias("AAA", (id_a,), db, capital_inicial=2_000_000.0)
        f1 = next(f for f in r1["filas"] if f["estrategia_id"] == id_a)
        f2 = next(f for f in r2["filas"] if f["estrategia_id"] == id_a)
        assert f1["retorno_total_pct"] == pytest.approx(f2["retorno_total_pct"])
        assert f2["capital_final"] == pytest.approx(f1["capital_final"] * 2, rel=1e-6)
        assert f2["ganancia"] == pytest.approx(f1["ganancia"] * 2, rel=1e-6)

    def test_6_periodo_distinto_mueve_la_base_del_buy_and_hold(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r_completo = comparar_estrategias("AAA", (id_a,), db)
        r_recortado = comparar_estrategias("AAA", (id_a,), db, desde=BASE_FECHA + timedelta(days=10))
        bh_completo = next(f for f in r_completo["filas"] if f["estrategia_id"] is None)
        bh_recortado = next(f for f in r_recortado["filas"] if f["estrategia_id"] is None)
        assert bh_completo["retorno_total_pct"] == pytest.approx(-10.0)
        # Desde idx10 (cierre 102) hasta el final (cierre 90): (90/102 - 1) * 100
        assert bh_recortado["retorno_total_pct"] == pytest.approx(-11.7647, abs=1e-3)

    def test_7_ticker_sin_serie_da_sin_serie_sin_filas_ni_excepcion(self, db):
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("NOEXISTE", (id_a,), db)
        assert r["estado"] == "sin_serie"
        assert r["filas"] == []
        assert r["fechas"] == []

    def test_8_ventana_corta_da_datos_insuficientes(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES[:5])  # 5 < MIN_BARRAS_VENTANA (20)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("AAA", (id_a,), db)
        assert r["estado"] == "datos_insuficientes"
        assert r["filas"] == []

    def test_9_estrategia_sin_senales(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_s = _guardar_estrategia(db, "Sin señales", DSL_SIN_SENALES)
        r = comparar_estrategias("AAA", (id_s,), db)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_s)
        assert fila["estado"] == "sin_senales"
        assert fila["riesgo"]["operaciones"] == 0
        assert fila["capital_final"] is not None  # 0 operaciones = retorno 0%, no "sin dato"

    def test_10_buy_and_hold_coincide_con_metricas_de_cualquier_fila(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        id_b = _guardar_estrategia(db, "B", DSL_B)
        r = comparar_estrategias("AAA", (id_a, id_b), db)
        bh = next(f for f in r["filas"] if f["estrategia_id"] is None)
        assert bh["retorno_total_pct"] == pytest.approx(-10.0)
        assert bh["riesgo"]["operaciones"] == 1
        assert bh["riesgo"]["comisiones_pct_acum"] == pytest.approx(0.0)

    def test_11_sin_costos_mejora_el_retorno_exactamente_en_n_cerradas_por_2_por_comision(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        dsl_con_comision = _dsl(
            {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 110}},
            {"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 95}},
            comision_pct=0.6,
        )
        id_a = _guardar_estrategia(db, "A con comisión", dsl_con_comision)
        r_con = comparar_estrategias("AAA", (id_a,), db, sin_costos=False)
        r_sin = comparar_estrategias("AAA", (id_a,), db, sin_costos=True)
        f_con = next(f for f in r_con["filas"] if f["estrategia_id"] == id_a)
        f_sin = next(f for f in r_sin["filas"] if f["estrategia_id"] == id_a)
        assert f_sin["riesgo"]["comisiones_pct_acum"] == pytest.approx(0.0)
        # 1 operación cerrada * 2 lados * 0.6% = 1.2 pp de mejora exacta.
        assert (f_sin["retorno_total_pct"] - f_con["retorno_total_pct"]) == pytest.approx(1.2, abs=1e-3)

    def test_12_local_y_subyacente_no_mezclan_moneda(self, db):
        db.add(WatchlistItem(ticker="SUB1", nombre="Sub1", tipo_instrumento="CEDEAR", mercado="BCBA", moneda="ARS"))
        _cargar_serie(db, "SUB1", CIERRES, moneda="ARS")
        for i, c in enumerate(CIERRES):
            db.add(BarraOHLCV(
                ticker="SUB1@SUB", fecha=BASE_FECHA + timedelta(days=i), apertura=float(c), maximo=float(c),
                minimo=float(c), cierre=float(c), volumen=1000.0, moneda="USD", fuente="yahoo",
            ))
        db.commit()
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r_local = comparar_estrategias("SUB1", (id_a,), db, variante="local")
        r_sub = comparar_estrategias("SUB1", (id_a,), db, variante="subyacente")
        assert r_local["moneda"] == "ARS"
        assert r_sub["moneda"] == "USD"


class TestAntiErrores:
    def test_eje_de_fechas_identico_con_warmups_muy_distintos(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        dsl_mm200 = _dsl(
            {"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"ref": "mm200"}},
            indicadores=[{"id": "mm200", "tipo": "SMA", "params": {"periodo": 200}}],
        )
        dsl_rsi2 = _dsl(
            {"op": "menor", "izq": {"ref": "rsi2"}, "der": {"const": 10}},
            indicadores=[{"id": "rsi2", "tipo": "RSI", "params": {"periodo": 2}}],
        )
        id_mm = _guardar_estrategia(db, "MM200", dsl_mm200)
        id_rsi = _guardar_estrategia(db, "RSI2", dsl_rsi2)
        r = comparar_estrategias("AAA", (id_mm, id_rsi), db)
        assert r["estado"] == "ok"
        largo = len(r["fechas"])
        for f in r["filas"]:
            assert len(f["curva"]) == largo

    def test_volatilidad_con_menos_de_6_meses_es_datos_insuficientes_no_un_numero(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)  # 30 días, muy por debajo de 6 meses de historia
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("AAA", (id_a,), db)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_a)
        assert fila["riesgo"]["volatilidad_estado"] == "datos_insuficientes"
        assert fila["riesgo"]["volatilidad_anualizada_pct"] is None

    def test_divergencias_detecta_el_tramo_donde_una_sale_del_mercado_y_la_otra_no(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)  # sale en idx28 (fuera del mercado desde ahí)
        r = comparar_estrategias("AAA", (id_a,), db)  # referencia = Comprar y mantener (siempre dentro)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_a)
        assert len(fila["divergencias"]) >= 1
        assert all(t["invertida_referencia_pct"] == pytest.approx(100.0) for t in fila["divergencias"])

    def test_submuestreo_conserva_primer_y_ultimo_punto_en_series_largas(self, db):
        _instrumento(db, "AAA")
        cierres_largos = [100.0 + (i % 50) * 0.1 for i in range(700)]
        _cargar_serie(db, "AAA", cierres_largos)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("AAA", (id_a,), db)
        assert len(r["fechas"]) <= 400
        assert r["fechas"][0] == BASE_FECHA
        assert r["fechas"][-1] == BASE_FECHA + timedelta(days=699)

    def test_mejor_no_incluye_comprar_y_mantener(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        id_b = _guardar_estrategia(db, "B", DSL_B)
        r = comparar_estrategias("AAA", (id_a, id_b), db)
        assert r["mejor"]["estrategia_id"] == id_b  # B rinde -2.94%, A rinde -16.96%: B es mejor
        assert r["mejor"]["disclaimer"]

    def test_definicion_invalida_no_desaparece_en_silencio(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_invalida = _guardar_estrategia(db, "Rota", {"version": 1})  # sin 'entrada': inválida
        r = comparar_estrategias("AAA", (id_invalida,), db)
        fila = next(f for f in r["filas"] if f["estrategia_id"] == id_invalida)
        assert fila["estado"] == "definicion_invalida"
        assert len(fila["errores"]) > 0
        assert fila["curva"] == [None] * len(r["fechas"])

    def test_estrategia_omitida_se_avisa(self, db):
        _instrumento(db, "AAA")
        _cargar_serie(db, "AAA", CIERRES)
        id_a = _guardar_estrategia(db, "A", DSL_A)
        r = comparar_estrategias("AAA", (id_a, 999_999), db)
        assert r["estrategias_omitidas"] == [999_999]
        assert "estrategias_omitidas" in r["advertencias"]
