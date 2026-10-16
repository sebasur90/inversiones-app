"""Cambios de diagnóstico: cuándo se avisa, antirrebote por transición, silencios y texto."""
import random
import re
from datetime import date, timedelta

import pytest

from app.services import alertas_diagnostico_engine as ade
from app.services import alertas_engine as ae

HOY = date(2026, 10, 20)
D1, D2, D3, D4 = (
    (HOY - timedelta(days=15)).isoformat(), (HOY - timedelta(days=10)).isoformat(),
    (HOY - timedelta(days=5)).isoformat(), (HOY - timedelta(days=1)).isoformat(),
)
CLAVE = ("KO", "valuacion")


def cand(estado="Barata", fecha=D1, dimension="valuacion", version=2, confianza="alta", nivel="neutro",
         razon="Más barata que sus pares en P/E y EV/EBITDA.", ticker="KO"):
    return ade.CandidatoDiagnostico(
        ticker_base=ticker, ticker=ticker, nombre="Coca-Cola", dimension=dimension, estado=estado, nivel=nivel,
        razon=razon, regla="al menos 2 familias entre el 25 % más barato", fecha_dato=fecha, version=version,
        confianza=confianza, precio=65.5, moneda="USD",
        contexto=ae.Contexto(origen=ae.ORIGEN_WATCHLIST),
    )


def paso(candidato, guardados=None, hoy=HOY):
    d = ade.evaluar_diagnosticos([candidato], guardados or {}, hoy)
    return d, {**(guardados or {}), **d.nuevos}


# ── Antirrebote por transición ──────────────────────────────────────────────

def test_la_primera_vez_siembra_el_estado_y_no_avisa():
    d, est = paso(cand("Barata", D1))
    assert d.a_emitir == [] and d.sembradas == 1
    assert est[CLAVE] == ade.EstadoAlerta("Barata", None, None, 2)


def test_un_cambio_queda_pendiente_y_no_avisa_hasta_confirmarse_en_otro_snapshot():
    _, est = paso(cand("Barata", D1))
    d, est = paso(cand("En línea", D2), est)
    assert d.a_emitir == [] and d.pendientes == 1
    assert est[CLAVE].estado_base == "Barata" and est[CLAVE].pendiente == "En línea" and est[CLAVE].pendiente_fecha_dato == D2
    d, est = paso(cand("En línea", D3), est)
    assert len(d.a_emitir) == 1
    a = d.a_emitir[0]
    assert a.tipo == "diagnostico:valuacion" and a.cartera == "" and a.nivel is None
    assert (a.contexto.diag_de, a.contexto.diag_a) == ("Barata", "En línea")
    assert est[CLAVE] == ade.EstadoAlerta("En línea", None, None, 2)


def test_la_misma_lectura_del_mismo_snapshot_no_confirma():
    _, est = paso(cand("Barata", D1))
    _, est = paso(cand("Cara", D2), est)
    d, est2 = paso(cand("Cara", D2), est)
    assert d.a_emitir == [] and est2 == est


def test_una_vez_avisado_no_repite():
    _, est = paso(cand("Barata", D1))
    _, est = paso(cand("Cara", D2), est)
    d, est = paso(cand("Cara", D3), est)
    assert len(d.a_emitir) == 1
    d, est = paso(cand("Cara", D4), est)
    assert d.a_emitir == [] and d.nuevos == {}


def test_oscilar_en_el_borde_no_avisa():
    """Barata → En línea → Barata → En línea…: nunca se ve dos veces seguidas el estado nuevo."""
    _, est = paso(cand("Barata", D1))
    for estado, fecha in (("En línea", D2), ("Barata", D3), ("En línea", D4)):
        d, est = paso(cand(estado, fecha), est)
        assert d.a_emitir == []
    assert est[CLAVE].estado_base == "Barata"


def test_volver_al_estado_base_cancela_el_pendiente():
    _, est = paso(cand("Barata", D1))
    _, est = paso(cand("Cara", D2), est)
    d, est = paso(cand("Barata", D3), est)
    assert d.a_emitir == [] and est[CLAVE].pendiente is None and est[CLAVE].estado_base == "Barata"


def test_si_el_pendiente_cambia_se_empieza_de_nuevo():
    _, est = paso(cand("Barata", D1))
    _, est = paso(cand("Cara", D2), est)
    d, est = paso(cand("En línea", D3), est)
    assert d.a_emitir == [] and est[CLAVE].pendiente == "En línea" and est[CLAVE].pendiente_fecha_dato == D3


# ── Silencios ───────────────────────────────────────────────────────────────

def test_un_cambio_de_version_de_reglas_resiembra_sin_avisar():
    _, est = paso(cand("Barata", D1, version=2))
    d, est = paso(cand("Cara", D2, version=3), est)
    assert d.a_emitir == [] and d.sembradas == 1 and est[CLAVE] == ade.EstadoAlerta("Cara", None, None, 3)


def test_un_cambio_de_version_con_un_pendiente_no_confirma_el_cambio_viejo():
    _, est = paso(cand("Barata", D1, version=2))
    _, est = paso(cand("Cara", D2, version=2), est)
    d, _ = paso(cand("Cara", D3, version=3), est)
    assert d.a_emitir == []


def test_dato_viejo_silencia_y_no_toca_el_estado():
    _, est = paso(cand("Barata", D1))
    viejo = (HOY - timedelta(days=ade.MAX_DIAS_DATO + 1)).isoformat()
    d, est2 = paso(cand("Cara", viejo), est)
    assert d.a_emitir == [] and d.nuevos == {} and d.silenciadas_por_dato == 1 and est2 == est


def test_el_limite_de_antiguedad_es_inclusivo():
    justo = (HOY - timedelta(days=ade.MAX_DIAS_DATO)).isoformat()
    d, _ = paso(cand("Barata", justo))
    assert d.sembradas == 1 and d.silenciadas_por_dato == 0


@pytest.mark.parametrize("confianza", ["baja", "sin_datos"])
def test_confianza_baja_silencia(confianza):
    d, _ = paso(cand("Barata", D1, confianza=confianza))
    assert d.nuevos == {} and d.silenciadas_por_dato == 1


@pytest.mark.parametrize("nivel", ["no_aplica", "sin_datos"])
def test_sin_estado_no_se_avisa(nivel):
    d, _ = paso(cand("No aplica", D1, nivel=nivel))
    assert d.nuevos == {} and d.silenciadas_por_dato == 1


def test_fecha_futura_o_ilegible_silencia():
    futura = (HOY + timedelta(days=3)).isoformat()
    assert paso(cand("Barata", futura))[0].silenciadas_por_dato == 1
    assert paso(cand("Barata", "no-es-fecha"))[0].silenciadas_por_dato == 1


def test_crecimiento_y_confianza_no_avisan():
    for dim in ("crecimiento", "confianza"):
        d, _ = paso(cand("Alta", D1, dimension=dim))
        assert d.nuevos == {} and d.sembradas == 0


# ── Determinismo y varias dimensiones ───────────────────────────────────────

def test_independiente_del_orden_y_una_dimension_no_afecta_a_otra():
    base = [cand("Barata", D1, dimension="valuacion"), cand("Sólida", D1, dimension="calidad"),
            cand("Sólida", D1, dimension="solidez"), cand("Barata", D1, ticker="PEP")]
    guardados = ade.evaluar_diagnosticos(base, {}, HOY).nuevos
    cambios = [cand("Cara", D3, dimension="valuacion"), cand("Sólida", D3, dimension="calidad"),
               cand("Sólida", D3, dimension="solidez"), cand("Barata", D3, ticker="PEP")]
    pendiente = {**guardados, **ade.evaluar_diagnosticos([cambios[0]], guardados, HOY).nuevos}
    esperado = ade.evaluar_diagnosticos(
        [cand("Cara", D4, dimension="valuacion")] + cambios[1:], pendiente, HOY)
    assert [a.contexto.diag_dimension for a in esperado.a_emitir] == ["valuacion"]
    for semilla in range(4):
        mezcla = [cand("Cara", D4, dimension="valuacion")] + cambios[1:]
        random.Random(semilla).shuffle(mezcla)
        assert ade.evaluar_diagnosticos(mezcla, pendiente, HOY) == esperado


# ── Texto del aviso ─────────────────────────────────────────────────────────

def _alerta(**kw):
    _, est = paso(cand("Barata", D1, **kw))
    _, est = paso(cand("Cara", D2, **kw), est)
    return ade.evaluar_diagnosticos([cand("Cara", D3, **kw)], est, HOY).a_emitir[0]


def test_el_mensaje_dice_que_cambio_con_que_datos_y_sin_indicar_que_hacer():
    texto = ae.texto_notificacion([_alerta()])
    assert "CAMBIO DE DIAGNÓSTICO" in texto and "<b>KO</b>" in texto
    assert "<b>Valuación</b>: Barata → <b>Cara</b>" in texto
    assert "Más barata que sus pares" in texto and "dato del" in texto and "reglas v2" in texto
    assert "no una indicación de operar" in texto
    assert not re.search(r"\b(compr\w*|vend\w*|recomend\w*)\b", texto, re.IGNORECASE), texto


def test_el_html_de_los_datos_se_escapa():
    texto = ae.texto_notificacion([_alerta(razon="P/E < 15 & margen > 10")])
    assert "P/E &lt; 15 &amp; margen &gt; 10" in texto and "<15" not in texto


def test_compacto_y_degradacion_por_presupuesto():
    alertas = [_alerta(ticker=f"T{i:03d}") for i in range(120)]
    texto = ae.texto_notificacion(alertas)
    assert len(texto) <= ae.PRESUPUESTO_CARACTERES and "CAMBIO DE DIAGNÓSTICO" in texto
    assert ae.texto_notificacion(alertas, presupuesto=300).count("\n") < 12      # último recurso: sólo conteos


def test_etiqueta_accion_y_encabezado_para_la_app():
    a = _alerta()
    assert ae.etiqueta_de(a.tipo, a.contexto) == "Cambio de diagnóstico · Valuación"
    assert ae.accion_de(a.tipo, a.contexto) == ae.ACCION_REVISAR
    assert ae.encabezado_texto(ae.bloque_de(a)) == "🔎 CAMBIO DE DIAGNÓSTICO"
    assert ae.es_tipo_diagnostico(a.tipo) and ae.dimension_de_tipo(a.tipo) == "valuacion"
    assert not ae.es_tipo_senal(a.tipo) and a.tipo not in ae.TIPOS


def test_el_contexto_sobrevive_al_round_trip_por_detalle():
    a = _alerta()
    detalle = ae.contexto_a_detalle(a.nombre, a.contexto)
    assert detalle["diag_dimension"] == "valuacion" and detalle["diag_version"] == 2
    ctx = ae.detalle_a_contexto(detalle)
    assert ctx == a.contexto
    assert ae.texto_notificacion([ae.Alerta(a.ticker, a.nombre, a.tipo, "", None, a.precio, a.moneda, ctx)]) == ae.texto_notificacion([a])
