"""Tests del motor de alertas. Lo que se prueba es el antirrebote: que un cruce avise una vez."""
import pytest

from app.services import alertas_engine as ae


def candidata(cruzado, nivel=100.0, precio=99.0, tipo=ae.TIPO_STOP_LOSS, ticker="AL30", cartera="Principal"):
    return ae.Candidata(
        ticker=ticker, nombre=f"Nombre {ticker}", tipo=tipo, cartera=cartera,
        nivel=nivel, precio=precio, moneda="USD", cruzado=cruzado,
    )


# --- Disparo y no repetición -------------------------------------------------------------------

def test_cruce_nuevo_se_emite():
    d = ae.evaluar([candidata(cruzado=True)], {})
    assert len(d.a_emitir) == 1
    assert d.a_emitir[0].ticker == "AL30"
    assert d.a_emitir[0].tipo == ae.TIPO_STOP_LOSS


def test_cruce_ya_disparado_no_se_repite():
    """El corazón del antirrebote: sin esto el bot avisa lo mismo en cada corrida."""
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_DISPARADA}
    d = ae.evaluar([candidata(cruzado=True)], estados)
    assert d.a_emitir == []
    assert d.a_rearmar == []


def test_nivel_armado_sin_cruce_no_avisa_ni_se_recrea():
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_ARMADA}
    d = ae.evaluar([candidata(cruzado=False, precio=150.0)], estados)
    assert d.a_emitir == []
    assert d.a_crear == []


def test_nivel_nuevo_sin_cruce_se_guarda_armado():
    """Para que el próximo cruce sí avise hay que recordar que lo estamos vigilando."""
    d = ae.evaluar([candidata(cruzado=False, precio=150.0)], {})
    assert d.a_emitir == []
    assert d.a_crear == [("AL30", ae.TIPO_STOP_LOSS, "Principal")]


# --- Histéresis del re-armado ------------------------------------------------------------------

def test_no_se_rearma_apenas_cruza_de_vuelta():
    """Precio 100.5 contra nivel 100 está dentro de la banda del 2%: sigue disparada.

    Sin la banda, un precio oscilando por centavos alrededor del nivel se re-armaría y volvería a
    disparar en cada corrida.
    """
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_DISPARADA}
    d = ae.evaluar([candidata(cruzado=False, nivel=100.0, precio=100.5)], estados)
    assert d.a_rearmar == []


def test_se_rearma_al_alejarse_mas_que_la_banda():
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_DISPARADA}
    d = ae.evaluar([candidata(cruzado=False, nivel=100.0, precio=103.0)], estados)
    assert d.a_rearmar == [("AL30", ae.TIPO_STOP_LOSS, "Principal")]
    assert d.a_emitir == []


def test_ciclo_completo_dispara_rearma_y_vuelve_a_disparar():
    clave = ("AL30", ae.TIPO_STOP_LOSS, "Principal")

    d1 = ae.evaluar([candidata(cruzado=True, nivel=100.0, precio=99.0)], {})
    assert len(d1.a_emitir) == 1

    estados = {clave: ae.ESTADO_DISPARADA}
    d2 = ae.evaluar([candidata(cruzado=True, nivel=100.0, precio=98.0)], estados)
    assert d2.a_emitir == []  # sigue cruzado: no se repite

    d3 = ae.evaluar([candidata(cruzado=False, nivel=100.0, precio=105.0)], estados)
    assert d3.a_rearmar == [clave]

    estados = {clave: ae.ESTADO_ARMADA}
    d4 = ae.evaluar([candidata(cruzado=True, nivel=100.0, precio=99.5)], estados)
    assert len(d4.a_emitir) == 1  # cruce nuevo después del re-armado: avisa de nuevo


def test_banda_se_aplica_al_reves_para_el_objetivo():
    """El objetivo de una posición se cruza hacia arriba: se re-arma cuando el precio BAJA."""
    clave = ("GGAL", ae.TIPO_OBJETIVO, "Principal")
    estados = {clave: ae.ESTADO_DISPARADA}

    cerca = candidata(cruzado=False, nivel=100.0, precio=99.5, tipo=ae.TIPO_OBJETIVO, ticker="GGAL")
    assert ae.evaluar([cerca], estados).a_rearmar == []

    lejos = candidata(cruzado=False, nivel=100.0, precio=97.0, tipo=ae.TIPO_OBJETIVO, ticker="GGAL")
    assert ae.evaluar([lejos], estados).a_rearmar == [clave]


def test_nivel_cero_no_rearma_nunca():
    """Con nivel 0 el margen relativo no significa nada; no se re-arma para no oscilar."""
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_DISPARADA}
    d = ae.evaluar([candidata(cruzado=False, nivel=0.0, precio=50.0)], estados)
    assert d.a_rearmar == []


# --- Claves independientes ---------------------------------------------------------------------

def test_mismo_ticker_en_dos_carteras_son_alertas_distintas():
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_DISPARADA}
    d = ae.evaluar([
        candidata(cruzado=True, cartera="Principal"),
        candidata(cruzado=True, cartera="Jubilacion"),
    ], estados)
    assert [a.cartera for a in d.a_emitir] == ["Jubilacion"]


def test_stop_loss_y_objetivo_del_mismo_ticker_son_independientes():
    estados = {("AL30", ae.TIPO_STOP_LOSS, "Principal"): ae.ESTADO_DISPARADA}
    d = ae.evaluar([
        candidata(cruzado=True, tipo=ae.TIPO_STOP_LOSS),
        candidata(cruzado=True, tipo=ae.TIPO_OBJETIVO, nivel=200.0, precio=201.0),
    ], estados)
    assert [a.tipo for a in d.a_emitir] == [ae.TIPO_OBJETIVO]


# --- Armado de candidatas desde lo que calcula el backend --------------------------------------

def test_candidatas_de_posiciones_toma_los_dos_niveles():
    item = {
        "ticker": "AL30", "nombre": "Bono AL30", "precio_actual": 95.0, "moneda": "USD",
        "precio_stop_loss": 96.0, "stop_loss_disparado": True, "pct_a_stop_loss": 0.01,
        "precio_objetivo": 120.0, "objetivo_alcanzado": False, "pct_a_objetivo": 0.26,
    }
    cands = ae.candidatas_de_posiciones([item], "Principal")
    assert {c.tipo for c in cands} == {ae.TIPO_STOP_LOSS, ae.TIPO_OBJETIVO}
    stop = next(c for c in cands if c.tipo == ae.TIPO_STOP_LOSS)
    assert stop.cruzado is True and stop.nivel == 96.0 and stop.precio == 95.0


def test_posicion_sin_niveles_no_genera_candidatas():
    """`None` en el flag es "no hay nivel definido", no "alerta armada"."""
    item = {
        "ticker": "AL30", "nombre": "Bono", "precio_actual": 95.0,
        "precio_stop_loss": None, "stop_loss_disparado": None,
        "precio_objetivo": None, "objetivo_alcanzado": None,
    }
    assert ae.candidatas_de_posiciones([item], "Principal") == []


def test_posicion_sin_precio_no_genera_candidatas():
    item = {
        "ticker": "AL30", "nombre": "Bono", "precio_actual": None,
        "precio_stop_loss": 96.0, "stop_loss_disparado": True,
    }
    assert ae.candidatas_de_posiciones([item], "Principal") == []


def test_candidatas_de_watchlist_cruzan_hacia_abajo():
    """El objetivo de la watchlist es un precio de compra: `en_zona` es precio <= objetivo."""
    item = {
        "ticker": "MSFT", "nombre": "Microsoft", "precio_actual": 24000.0,
        "precio_objetivo": 25000.0, "en_zona": True, "moneda_precio": "ARS",
    }
    cands = ae.candidatas_de_watchlist([item])
    assert len(cands) == 1
    assert cands[0].tipo == ae.TIPO_COMPRA_ZONA
    assert cands[0].cartera == ae.SIN_CARTERA
    assert cands[0].cruzado is True


def test_watchlist_sin_objetivo_no_genera_candidatas():
    item = {"ticker": "MSFT", "nombre": "Microsoft", "precio_actual": 24000.0,
            "precio_objetivo": None, "en_zona": None}
    assert ae.candidatas_de_watchlist([item]) == []


# --- Texto del mensaje -------------------------------------------------------------------------

def test_texto_vacio_sin_alertas():
    assert ae.texto_notificacion([]) == ""


def test_texto_agrupa_por_tipo_y_usa_el_comparador_correcto():
    alertas = [
        ae.Alerta("AL30", "Bono AL30", ae.TIPO_STOP_LOSS, "Principal", 96.0, 95.5, "USD"),
        ae.Alerta("GGAL", "Galicia", ae.TIPO_OBJETIVO, "Principal", 7000.0, 7200.0, "ARS"),
        ae.Alerta("MSFT", "Microsoft", ae.TIPO_COMPRA_ZONA, "", 25000.0, 24000.0, "ARS"),
    ]
    texto = ae.texto_notificacion(alertas)
    assert "Stop-loss disparado" in texto
    assert "Objetivo alcanzado" in texto
    assert "Zona de compra" in texto
    # Stop-loss y zona de compra se cruzan hacia abajo; el objetivo, hacia arriba.
    assert "USD 95,50 ≤ USD 96,00" in texto
    assert "ARS 7.200,00 ≥ ARS 7.000,00" in texto
    # La cartera se nombra cuando la hay; la watchlist no tiene.
    assert "AL30 (Bono AL30) · Principal" in texto
    assert "MSFT (Microsoft):" in texto


def test_formato_de_precio_es_es_ar():
    assert ae._fmt_precio(1234.5) == "1.234,50"
    assert ae._fmt_precio(0.5) == "0,50"
    assert ae._fmt_precio(1234567.891) == "1.234.567,89"
