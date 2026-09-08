"""Tests del screener: motor puro (`screener_engine`) y endpoint (`routers/tecnico.py`)."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, EstrategiaTecnica, InstrumentoInversion, PrecioInstrumento, WatchlistItem, get_db
from app.main import app
from app.services import estrategia_engine as ee
from app.services import indicadores_engine, screener_analytics, screener_engine as se
from app.services.indicadores_engine import Barra


def _barras(cierres, aperturas=None, maximos=None, minimos=None):
    base = date(2024, 1, 1)
    out = []
    for i, c in enumerate(cierres):
        out.append(Barra(
            fecha=base + timedelta(days=i), cierre=c,
            apertura=aperturas[i] if aperturas else None,
            maximo=maximos[i] if maximos else None,
            minimo=minimos[i] if minimos else None,
        ))
    return out


def _dsl_base(entrada, salida=None, riesgo=None, ejecucion=None, indicadores=None):
    return {
        "version": 1,
        "indicadores": indicadores or [],
        "entrada": entrada,
        "salida": salida,
        "riesgo": riesgo or {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": ejecucion or {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0},
    }


# ── distancia_al_disparo ──────────────────────────────────────────────────────────────────────

def test_distancia_cero_si_ya_dispara_hoy():
    barras = _barras([100.0] * 10 + [10.0])  # cierre << const: entrada ya cumple
    dsl = _dsl_base({"op": "menor", "izq": {"campo": "cierre"}, "der": {"const": 50}})
    assert se.distancia_al_disparo(dsl, barras, "entrada") == 0.0


def test_distancia_coincide_con_formula_analitica_y_signo_negativo():
    # menor(cierre, 95): con cierre=100, dispara cuando cierre <= 95, es decir delta <= -5%.
    barras = _barras([100.0] * 20)
    dsl = _dsl_base({"op": "menor_igual", "izq": {"campo": "cierre"}, "der": {"const": 95.0}})
    distancia = se.distancia_al_disparo(dsl, barras, "entrada")
    assert distancia is not None
    assert distancia < 0
    assert distancia == pytest.approx(-5.0, abs=0.02)


def test_distancia_positiva_cuando_hay_que_subir():
    barras = _barras([100.0] * 20)
    dsl = _dsl_base({"op": "mayor_igual", "izq": {"campo": "cierre"}, "der": {"const": 103.0}})
    distancia = se.distancia_al_disparo(dsl, barras, "entrada")
    assert distancia == pytest.approx(3.0, abs=0.02)


def test_distancia_es_coherente_con_el_motor_de_backtest():
    # Aplicar el delta encontrado al cierre real y verificar contra `compilar()`, la misma función
    # que usa `backtest()` — así queda garantizado que el screener no "inventa" una señal.
    barras = _barras([100.0, 102.0, 101.0, 99.0, 103.0, 97.0, 105.0])
    dsl = _dsl_base({"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 108.0}})
    distancia = se.distancia_al_disparo(dsl, barras, "entrada")
    assert distancia is not None

    perturbada = list(barras[:-1]) + [Barra(
        fecha=barras[-1].fecha, cierre=barras[-1].cierre * (1 + distancia / 100),
    )]
    assert ee.compilar(dsl, perturbada).entrada[-1] is True

    # Un pelo menos no debería alcanzar (comprobamos con la magnitud recortada al 90%).
    corta = list(barras[:-1]) + [Barra(
        fecha=barras[-1].fecha, cierre=barras[-1].cierre * (1 + (distancia * 0.9) / 100),
    )]
    assert ee.compilar(dsl, corta).entrada[-1] is not True


def test_distancia_none_si_no_puede_dispararse_dentro_del_limite():
    # cruce_arriba ya consumido en la barra anterior: mover sólo el cierre de la última barra
    # nunca hace que la anterior "cruce" retroactivamente.
    barras = _barras([90.0, 100.0, 101.0])  # cruzó entre la barra 0 y la 1; la 2 ya está arriba
    dsl = _dsl_base(
        {"op": "cruce_arriba", "izq": {"campo": "cierre"}, "der": {"const": 95.0}},
    )
    assert se.distancia_al_disparo(dsl, barras, "entrada", limite_pct=15.0) is None


def test_distancia_respeta_limite_pct():
    barras = _barras([100.0] * 20)
    dsl = _dsl_base({"op": "mayor_igual", "izq": {"campo": "cierre"}, "der": {"const": 130.0}})  # +30%
    assert se.distancia_al_disparo(dsl, barras, "entrada", limite_pct=15.0) is None
    # Más allá del tope de la grilla fija (12%) la búsqueda sigue log-espaciando pero con pasos más
    # anchos: la precisión ahí es más laxa que la que promete la grilla base (≤0.15%).
    assert se.distancia_al_disparo(dsl, barras, "entrada", limite_pct=50.0) == pytest.approx(30.0, abs=0.5)


def test_condicion_invalida_lanza():
    barras = _barras([100.0] * 5)
    dsl = _dsl_base({"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}})
    with pytest.raises(ValueError):
        se.distancia_al_disparo(dsl, barras, "otra_cosa")


def test_serie_corta_devuelve_none():
    assert se.distancia_al_disparo(_dsl_base({"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}}), _barras([100.0]), "entrada") is None


# ── barras_contexto ────────────────────────────────────────────────────────────────────────────

def test_barras_contexto_exhaustiva_todos_los_indicadores_clasificados():
    assert set(se._FAMILIA_POR_TIPO.keys()) == set(indicadores_engine.INDICADORES.keys())


@pytest.mark.parametrize("tipo,params", [
    ("SMA", {"periodo": 50}),
    ("RSI", {"periodo": 14}),
    ("MACD", {"rapida": 12, "lenta": 26, "senal": 9}),
])
def test_barras_contexto_recorta_sin_cambiar_el_veredicto_en_la_ultima_barra(tipo, params):
    n = 400
    base = date(2023, 1, 1)
    barras = []
    precio = 100.0
    for i in range(n):
        precio *= 1 + (0.003 if i % 5 else -0.01)
        barras.append(Barra(fecha=base + timedelta(days=i), cierre=precio))

    ref_id = "ind1"
    campo_salida = "macd" if tipo == "MACD" else "valor"
    dsl = _dsl_base(
        {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"ref": ref_id, "salida": campo_salida}},
        indicadores=[{"id": ref_id, "tipo": tipo, "params": params}],
    )

    contexto = se.barras_contexto(dsl)
    assert contexto < n  # la optimización realmente recorta

    completa = ee.compilar(dsl, barras).entrada[-1]
    recortada = ee.compilar(dsl, barras[-contexto:]).entrada[-1]
    assert completa == recortada


def test_barras_contexto_historico_para_ventana_cero():
    dsl = _dsl_base(
        {"op": "menor_igual", "izq": {"ref": "ext", "salida": "dist_min_pct"}, "der": {"const": 1}},
        indicadores=[{"id": "ext", "tipo": "EXTREMOS", "params": {"ventana": 0}}],
    )
    assert se.barras_contexto(dsl) >= se._CONTEXTO_HISTORICO


def test_barras_contexto_subiendo_bajando_suma_barras():
    dsl = _dsl_base({"op": "subiendo", "operando": {"campo": "cierre"}, "barras": 30})
    assert se.barras_contexto(dsl) >= 30


# ── distancia_a_stops ──────────────────────────────────────────────────────────────────────────

def test_distancia_a_stop_loss_exacta():
    barras = _barras([100.0, 105.0, 98.0])
    riesgo = {"stop_loss_pct": 10.0, "take_profit_pct": None, "trailing_stop_pct": None}
    stops = se.distancia_a_stops(barras, indice_entrada=0, precio_entrada=100.0, riesgo=riesgo)
    assert len(stops) == 1
    nivel_esperado = 100.0 * 0.9  # 90.0
    precio_actual = barras[-1].cierre  # 98.0
    assert stops[0]["motivo"] == "stop_loss"
    assert stops[0]["nivel"] == pytest.approx(90.0)
    # `distancia_a_stops` redondea a 4 decimales; la tolerancia acompaña ese redondeo.
    assert stops[0]["distancia_pct"] == pytest.approx((90.0 / 98.0 - 1) * 100, abs=1e-4)


def test_distancia_a_trailing_usa_maximo_desde_entrada_como_el_backtest():
    # Semilla == precio_entrada; sólo las barras *posteriores* a la entrada mueven el trailing.
    barras = _barras([100.0, 120.0, 90.0], maximos=[100.0, 125.0, 91.0], minimos=[99.0, 119.0, 88.0])
    riesgo = {"stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": 20.0}
    stops = se.distancia_a_stops(barras, indice_entrada=0, precio_entrada=100.0, riesgo=riesgo)
    assert len(stops) == 1
    # maximo_desde_entrada = max(100, maximo_barra(barra1)=125, maximo_barra(barra2)=91) = 125
    assert stops[0]["nivel"] == pytest.approx(125.0 * 0.8)


def test_distancia_a_take_profit_exacta():
    barras = _barras([100.0, 108.0])
    riesgo = {"stop_loss_pct": None, "take_profit_pct": 15.0, "trailing_stop_pct": None}
    stops = se.distancia_a_stops(barras, indice_entrada=0, precio_entrada=100.0, riesgo=riesgo)
    assert stops[0]["nivel"] == pytest.approx(115.0)


# ── desglose_condiciones ───────────────────────────────────────────────────────────────────────

def test_desglose_condiciones_reporta_valores_y_cumple():
    barras = _barras([100.0] * 14 + [50.0])  # RSI se desploma con la última barra
    dsl = _dsl_base(
        {"op": "y", "condiciones": [
            {"op": "menor", "izq": {"ref": "rsi14"}, "der": {"const": 100}},
            {"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 999}},
        ]},
        indicadores=[{"id": "rsi14", "tipo": "RSI", "params": {"periodo": 14}}],
    )
    filas = se.desglose_condiciones(dsl, barras, "entrada")
    assert len(filas) == 2
    fila_rsi = next(f for f in filas if f["izq_etiqueta"] == "RSI(14)")
    assert fila_rsi["cumple"] is True
    assert fila_rsi["izq_valor"] is not None
    fila_cierre = next(f for f in filas if f["izq_etiqueta"] == "cierre")
    assert fila_cierre["cumple"] is False
    assert fila_cierre["der_etiqueta"] == "999"


def test_desglose_condiciones_vacio_sin_regla_de_salida():
    dsl = _dsl_base({"op": "mayor", "izq": {"campo": "cierre"}, "der": {"const": 0}})
    assert se.desglose_condiciones(dsl, _barras([100.0]), "salida") == []


# ── endpoint /tecnico/screener ────────────────────────────────────────────────────────────────

def _dsl_rsi_sobreventa():
    return {
        "version": 1,
        "indicadores": [{"id": "rsi14", "tipo": "RSI", "params": {"periodo": 14}}],
        "entrada": {"op": "menor", "izq": {"ref": "rsi14"}, "der": {"const": 30}},
        "salida": {"op": "mayor", "izq": {"ref": "rsi14"}, "der": {"const": 60}},
        "riesgo": {"stop_loss_pct": 10.0, "take_profit_pct": None, "trailing_stop_pct": None, "max_barras": None},
        "ejecucion": {"lado": "long", "comision_pct": 0.0, "precio_ejecucion": "cierre", "demora_barras": 0},
    }


@pytest.fixture
def client_screener():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    db.add(InstrumentoInversion(ticker="AL30", nombre="Bono AL30", tipo_instrumento="Bono", mercado="MERVAL", moneda="USD"))
    db.add(WatchlistItem(ticker="GGAL", nombre="Galicia", tipo_instrumento="Accion", mercado="BCBA", moneda="ARS"))

    base = date.today() - timedelta(days=60)
    # AL30: precio cayendo fuerte las últimas ruedas -> RSI bajo, cerca de "menor que 30".
    precio = 100.0
    for i in range(50):
        precio *= 0.985 if i > 35 else 1.001
        db.add(PrecioInstrumento(ticker="AL30", fecha=base + timedelta(days=i), precio=precio, moneda="USD", fuente="sheet"))
    # GGAL: precio subiendo levemente -> lejos de disparar.
    precio_g = 100.0
    for i in range(50):
        precio_g *= 1.002
        db.add(PrecioInstrumento(ticker="GGAL", fecha=base + timedelta(days=i), precio=precio_g, moneda="ARS", fuente="sheet"))
    # GGAL vive en watchlist, no en instrumentos: precios_instrumento sólo sirve a AL30 acá; agrego
    # también a `precios_instrumento` para GGAL igual, `get_serie_barras` lo acepta sin requerir
    # que el ticker esté en `InstrumentoInversion`.

    ahora = datetime.utcnow()
    db.add(EstrategiaTecnica(
        nombre="RSI sobreventa reusable", ticker=None, tipo_preset="rsi_sobreventa",
        definicion=_dsl_rsi_sobreventa(), variante="local",
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    ))
    db.add(EstrategiaTecnica(
        nombre="Rota", ticker=None, tipo_preset=None,
        definicion={"version": 2, "entrada": None}, variante="local",  # DSL inválido a propósito
        fecha_creacion=ahora, fecha_actualizacion=ahora,
    ))
    db.commit()
    db.close()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_screener_endpoint_filtra_por_umbral_y_ordena_por_cercania(client_screener):
    r = client_screener.post("/api/inversiones/tecnico/screener", json={"umbral_pct": 15.0})
    assert r.status_code == 200
    body = r.json()
    assert body["umbral_pct"] == 15.0
    tickers = [f["ticker"] for f in body["filas"]]
    assert "AL30" in tickers  # RSI hundido: tiene que aparecer
    if len(body["filas"]) > 1:
        distancias = [abs(f["distancia_pct"]) for f in body["filas"]]
        assert distancias == sorted(distancias)
    for fila in body["filas"]:
        assert abs(fila["distancia_pct"]) <= 15.0
    # La estrategia con DSL roto no debe tumbar la respuesta.
    assert "estrategias_invalidas_omitidas" in body["advertencias"]


def test_screener_endpoint_umbral_angosto_devuelve_menos_filas(client_screener):
    amplio = client_screener.post("/api/inversiones/tecnico/screener", json={"umbral_pct": 15.0}).json()
    angosto = client_screener.post("/api/inversiones/tecnico/screener", json={"umbral_pct": 0.5}).json()
    assert len(angosto["filas"]) <= len(amplio["filas"])


def test_screener_endpoint_origen_invalido_422(client_screener):
    r = client_screener.post("/api/inversiones/tecnico/screener", json={"origen": "invalido"})
    assert r.status_code == 422


def test_screener_endpoint_filtra_por_origen(client_screener):
    r = client_screener.post("/api/inversiones/tecnico/screener", json={"umbral_pct": 15.0, "origen": "cartera"})
    assert r.status_code == 200
    for fila in r.json()["filas"]:
        assert fila["origen"] in ("cartera", "ambos")


def test_screener_endpoint_filtra_por_estrategia_ids(client_screener):
    r = client_screener.post("/api/inversiones/tecnico/screener", json={"estrategia_ids": [999999], "umbral_pct": 15.0})
    assert r.status_code == 200
    assert r.json()["filas"] == []


def test_screener_endpoint_fila_trae_desglose_y_precio_gatillo(client_screener):
    r = client_screener.post("/api/inversiones/tecnico/screener", json={"umbral_pct": 15.0})
    body = r.json()
    fila_al30 = next(f for f in body["filas"] if f["ticker"] == "AL30")
    # La caída sintética de AL30 puede haber disparado la entrada antes del final de la serie
    # (quedando "dentro", con `tipo == "venta"` vigilando la salida/los stops) o no — lo que importa
    # acá es que la fila trae desglose y que el precio-gatillo es coherente con la distancia.
    assert fila_al30["tipo"] in ("compra", "venta")
    assert fila_al30["condiciones"]
    assert fila_al30["precio_gatillo"] == pytest.approx(
        fila_al30["precio_actual"] * (1 + fila_al30["distancia_pct"] / 100), rel=1e-6,
    )
