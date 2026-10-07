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


def _alertas_de_los_tres_tipos():
    return [
        ae.Alerta("AL30", "Bono AL30", ae.TIPO_STOP_LOSS, "Principal", 96.0, 95.5, "USD"),
        ae.Alerta("GGAL", "Galicia", ae.TIPO_OBJETIVO, "Principal", 7000.0, 7200.0, "ARS"),
        ae.Alerta("MSFT", "Microsoft", ae.TIPO_COMPRA_ZONA, "", 25000.0, 24000.0, "ARS"),
    ]


def test_texto_agrupa_por_tipo_y_usa_el_comparador_correcto():
    texto = ae.texto_notificacion(_alertas_de_los_tres_tipos())

    # Cada bloque dice en su encabezado qué acción implica, que es lo que el aviso tiene que
    # contestar primero.
    assert "<b>STOP-LOSS</b> — revisar salida" in texto
    assert "<b>OBJETIVO ALCANZADO</b> — revisar toma de ganancia" in texto
    assert "<b>OPORTUNIDAD DE COMPRA</b> — en zona" in texto
    # Stop-loss y zona de compra se cruzan hacia abajo; el objetivo, hacia arriba.
    assert "<code>USD 95,50</code> ≤ stop <code>USD 96,00</code>" in texto
    assert "<code>ARS 7.200,00</code> ≥ objetivo <code>ARS 7.000,00</code>" in texto
    # La cartera se nombra cuando la hay; la watchlist se nombra como tal.
    assert "<b>AL30</b> (Bono AL30) · cartera Principal" in texto
    assert "<b>MSFT</b> (Microsoft) · watchlist" in texto


def test_orden_de_bloques_pone_primero_el_riesgo_y_al_final_las_entradas():
    texto = ae.texto_notificacion(_alertas_de_los_tres_tipos())
    posiciones = [texto.index(ae.encabezado_html(c)) for c in (
        ae.TIPO_STOP_LOSS, ae.TIPO_OBJETIVO, ae.TIPO_COMPRA_ZONA,
    )]
    assert posiciones == sorted(posiciones)


def test_las_posiciones_van_antes_que_la_watchlist_en_el_mismo_bloque():
    alertas = [
        ae.Alerta("WL", "De la watchlist", ae.TIPO_COMPRA_ZONA, "", 100.0, 99.0, "USD",
                  ae.Contexto(origen=ae.ORIGEN_WATCHLIST)),
        ae.Alerta("POS", "En cartera", ae.TIPO_COMPRA_ZONA, "Principal", 100.0, 99.0, "USD",
                  ae.Contexto(origen=ae.ORIGEN_CARTERA)),
    ]
    texto = ae.texto_notificacion(alertas)
    assert texto.index("POS") < texto.index("WL")


def test_formato_de_precio_es_es_ar():
    assert ae._fmt_precio(1234.5) == "1.234,50"
    assert ae._fmt_precio(0.5) == "0,50"
    assert ae._fmt_precio(1234567.891) == "1.234.567,89"


# --- Escapado y round-trip del contexto --------------------------------------------------------

def test_escapar_html_protege_los_nombres_reales():
    """Hay instrumentos que se llaman "S&P 500" o "AT&T": un `&` crudo hace que Telegram rechace
    el mensaje **entero** con 400, no que se vea raro un nombre."""
    assert ae.escapar_html("S&P <X>") == "S&amp;P &lt;X&gt;"
    assert ae.escapar_html(None) == ""


def test_el_nombre_con_ampersand_no_sale_crudo_en_el_mensaje():
    alerta = ae.Alerta("SPY", "S&P 500 ETF", ae.TIPO_COMPRA_ZONA, "", 100.0, 99.0, "USD")
    texto = ae.texto_notificacion([alerta])
    assert "S&amp;P 500 ETF" in texto
    assert "S&P" not in texto


def test_round_trip_del_contexto_por_detalle():
    """Lo que no sobrevive este viaje se pierde en el reintento de envío."""
    ctx = ae.Contexto(
        origen=ae.ORIGEN_CARTERA, cartera_nombre="Principal", distancia_pct=-4.5, cantidad=10.0,
        precio_promedio=100.0, resultado_pct=-4.5, carteras_extra=2, nivel_modo="Porcentaje",
        nivel_valor=-10.0, en_cartera=False, estrategia_id=7, estrategia_nombre="RSI",
        senal_tipo=ae.SENAL_VENTA, senal_fecha="2026-10-06", senal_motivo="regla_salida",
        variante="subyacente", barras_desde=1,
    )
    detalle = ae.contexto_a_detalle("Bono AL30", ctx)
    assert detalle["nombre"] == "Bono AL30"
    assert ae.detalle_a_contexto(detalle) == ctx


def test_detalle_viejo_con_solo_el_nombre_no_explota():
    """Es el estado de la DB el día del deploy: filas con `detalle={"nombre": ...}`."""
    assert ae.detalle_a_contexto({"nombre": "Bono AL30"}) == ae.Contexto()
    assert ae.nombre_de_detalle({"nombre": "Bono AL30"}, "AL30") == "Bono AL30"
    assert ae.nombre_de_detalle(None, "AL30") == "AL30"


def test_detalle_con_claves_desconocidas_se_ignoran():
    """Una versión futura del formato no puede tirar abajo la evaluación."""
    ctx = ae.detalle_a_contexto({"nombre": "x", "v": 99, "campo_del_futuro": 1, "cantidad": 5.0})
    assert ctx.cantidad == 5.0


def test_el_detalle_solo_serializa_tipos_que_json_acepta():
    import json
    ctx = ae.Contexto(senal_fecha="2026-10-06", cantidad=10.0, en_cartera=True)
    json.dumps(ae.contexto_a_detalle("x", ctx))  # no debe lanzar


# --- Contexto en el texto ----------------------------------------------------------------------

def test_la_posicion_muestra_tenencia_y_resultado_y_la_watchlist_no():
    posicion = ae.Alerta(
        "AL30", "Bono AL30", ae.TIPO_STOP_LOSS, "Principal", 96.0, 95.5, "USD",
        ae.Contexto(origen=ae.ORIGEN_CARTERA, cantidad=10.0, precio_promedio=100.0,
                    resultado_pct=-4.5),
    )
    watch = ae.Alerta("MSFT", "Microsoft", ae.TIPO_COMPRA_ZONA, "", 100.0, 99.0, "ARS",
                      ae.Contexto(origen=ae.ORIGEN_WATCHLIST))

    texto = ae.texto_notificacion([posicion, watch])
    assert "10 un. · PPC <code>USD 100,00</code> · <b>-4,5%</b>" in texto
    # El bloque de la watchlist no inventa una tenencia que no existe.
    bloque_watch = texto.split(ae.encabezado_html(ae.TIPO_COMPRA_ZONA))[1]
    assert "un." not in bloque_watch and "PPC" not in bloque_watch


def test_watchlist_con_tenencia_lo_dice():
    """Desambigua si el aviso es una entrada nueva o un refuerzo de algo que ya está."""
    alerta = ae.Alerta("MSFT", "Microsoft", ae.TIPO_COMPRA_ZONA, "", 100.0, 99.0, "ARS",
                       ae.Contexto(origen=ae.ORIGEN_WATCHLIST, en_cartera=True))
    assert "ya tenés posición" in ae.texto_notificacion([alerta])


def test_la_distancia_al_nivel_lleva_signo():
    alerta = ae.Alerta("AL30", "Bono", ae.TIPO_STOP_LOSS, "P", 96.0, 95.5, "USD",
                       ae.Contexto(distancia_pct=ae.distancia_pct(95.5, 96.0)))
    assert "(-0,5%)" in ae.texto_notificacion([alerta])


def test_distancia_pct_se_mide_sobre_el_nivel():
    assert ae.distancia_pct(95.5, 96.0) == -0.52
    assert ae.distancia_pct(7200.0, 7000.0) == 2.86
    assert ae.distancia_pct(100.0, None) is None
    assert ae.distancia_pct(100.0, 0.0) is None


# --- Recorte -----------------------------------------------------------------------------------

def _muchas(n):
    tipos = (ae.TIPO_STOP_LOSS, ae.TIPO_OBJETIVO, ae.TIPO_COMPRA_ZONA)
    return [
        ae.Alerta(f"TICKER{i:03d}", f"Nombre {i}", tipos[i % 3],
                  "Principal" if i % 3 != 2 else "", 100.0, 99.0, "USD",
                  ae.Contexto(cantidad=10.0, precio_promedio=100.0, resultado_pct=-1.0,
                              distancia_pct=-1.0))
        for i in range(n)
    ]


def test_pocas_alertas_usan_el_detalle_completo():
    texto = ae.texto_notificacion(_muchas(15))
    assert len(texto) <= ae.PRESUPUESTO_CARACTERES
    assert "PPC" in texto  # la línea de tenencia sólo existe en el nivel completo


def test_muchas_alertas_entran_en_el_presupuesto_sin_partir_un_tag():
    """Un recorte a mitad de tag no pierde un pedazo del mensaje: Telegram rechaza todo."""
    texto = ae.texto_notificacion(_muchas(200))
    assert len(texto) <= ae.PRESUPUESTO_CARACTERES
    assert texto.count("<") == texto.count(">")
    assert texto.count("<b>") == texto.count("</b>")
    assert texto.count("<code>") == texto.count("</code>")
    assert "… y " in texto  # el total siempre cierra


def test_ningun_bloque_con_alertas_desaparece_del_mensaje():
    texto = ae.texto_notificacion(_muchas(400))
    for tipo in (ae.TIPO_STOP_LOSS, ae.TIPO_OBJETIVO, ae.TIPO_COMPRA_ZONA):
        assert ae.BLOQUES[tipo].titulo in texto


def test_con_un_presupuesto_minimo_queda_el_resumen_por_conteo():
    texto = ae.texto_notificacion(_muchas(400), presupuesto=400)
    assert "Abrí la app para el detalle." in texto
    for tipo in (ae.TIPO_STOP_LOSS, ae.TIPO_OBJETIVO, ae.TIPO_COMPRA_ZONA):
        assert ae.BLOQUES[tipo].titulo in texto


# --- Tipos compuestos de las señales -----------------------------------------------------------

def test_tipo_senal_ida_y_vuelta():
    assert ae.tipo_senal(7) == "estrategia:7"
    assert ae.estrategia_de_tipo(ae.tipo_senal(7)) == 7
    assert ae.es_tipo_senal(ae.tipo_senal(7)) is True


def test_un_tipo_de_nivel_no_es_una_senal():
    for tipo in ae.TIPOS:
        assert ae.es_tipo_senal(tipo) is False
        assert ae.estrategia_de_tipo(tipo) is None


def test_etiqueta_de_una_senal_no_muestra_el_tipo_crudo():
    """`ETIQUETA_TIPO.get(tipo, tipo)` dejaba literalmente "estrategia:3" en la pantalla."""
    ctx = ae.Contexto(estrategia_nombre="RSI sobreventa", senal_tipo=ae.SENAL_COMPRA)
    etiqueta = ae.etiqueta_de(ae.tipo_senal(3), ctx)
    assert "estrategia:3" not in etiqueta
    assert etiqueta == "Señal de compra · RSI sobreventa"
    assert ae.etiqueta_de(ae.TIPO_STOP_LOSS) == "Stop-loss disparado"


def test_accion_de_cada_tipo():
    assert ae.accion_de(ae.TIPO_COMPRA_ZONA) == ae.ACCION_COMPRA
    assert ae.accion_de(ae.TIPO_STOP_LOSS) == ae.ACCION_REVISAR
    assert ae.accion_de(ae.TIPO_OBJETIVO) == ae.ACCION_REVISAR
    assert ae.accion_de(ae.tipo_senal(1), ae.Contexto(senal_tipo=ae.SENAL_VENTA)) == ae.ACCION_VENTA
    assert ae.accion_de(ae.tipo_senal(1), ae.Contexto(senal_tipo=ae.SENAL_COMPRA)) == ae.ACCION_COMPRA


# --- Antirrebote de las señales ----------------------------------------------------------------

def senal(fecha="2026-10-06", tipo=ae.SENAL_COMPRA, estrategia_id=3, ticker="AAPL"):
    return ae.SenalCandidata(
        ticker=ticker, nombre="Apple", estrategia_id=estrategia_id,
        estrategia_nombre="Cruce de medias", tipo=tipo, fecha=fecha, precio=231.4, moneda="USD",
        motivo="entrada", variante="local", barras_desde=0,
    )


def test_senal_nueva_se_avisa():
    alertas = ae.evaluar_senales([senal()], {})
    assert len(alertas) == 1
    assert alertas[0].tipo == ae.tipo_senal(3)
    assert alertas[0].nivel is None
    assert alertas[0].contexto.senal_fecha == "2026-10-06"
    assert alertas[0].contexto.estrategia_nombre == "Cruce de medias"


def test_la_misma_senal_no_se_repite():
    """`senales_recientes` devuelve la misma señal durante varias barras: sólo la primera avisa."""
    avisadas = {senal().clave: ("2026-10-06", ae.SENAL_COMPRA)}
    assert ae.evaluar_senales([senal()], avisadas) == []


def test_la_senal_del_otro_lado_el_mismo_dia_si_avisa():
    avisadas = {senal().clave: ("2026-10-06", ae.SENAL_COMPRA)}
    assert len(ae.evaluar_senales([senal(tipo=ae.SENAL_VENTA)], avisadas)) == 1


def test_una_barra_nueva_vuelve_a_avisar():
    """Compra → venta → compra del mismo par: cada una tiene barra distinta, cada una avisa."""
    avisadas = {senal().clave: ("2026-10-06", ae.SENAL_COMPRA)}
    assert len(ae.evaluar_senales([senal(fecha="2026-10-09")], avisadas)) == 1


def test_senales_de_estrategias_distintas_no_se_pisan():
    avisadas = {senal(estrategia_id=3).clave: ("2026-10-06", ae.SENAL_COMPRA)}
    alertas = ae.evaluar_senales([senal(estrategia_id=3), senal(estrategia_id=4)], avisadas)
    assert [a.tipo for a in alertas] == [ae.tipo_senal(4)]


def test_el_bloque_de_una_senal_depende_del_lado():
    compra = ae.evaluar_senales([senal(tipo=ae.SENAL_COMPRA)], {})[0]
    venta = ae.evaluar_senales([senal(tipo=ae.SENAL_VENTA)], {})[0]
    assert ae.bloque_de(compra) == ae.BLOQUE_SENAL_COMPRA
    assert ae.bloque_de(venta) == ae.BLOQUE_SENAL_VENTA


def test_el_texto_de_una_senal_dice_la_estrategia_y_que_el_precio_es_un_cierre():
    """La serie OHLCV y `precios_instrumento` no coinciden por diseño: si el aviso dijera
    "precio" el usuario vería dos números distintos del mismo ticker el mismo día."""
    alerta = ae.evaluar_senales([senal()], {})[0]
    texto = ae.texto_notificacion([alerta])
    assert "<b>Cruce de medias</b> · entrada" in texto
    assert "cierre del 06/10: <code>USD 231,40</code>" in texto


def test_la_variante_subyacente_se_aclara_en_el_aviso():
    s = ae.replace(senal(), variante="subyacente")
    texto = ae.texto_notificacion(ae.evaluar_senales([s], {}))
    assert "serie del subyacente en USD" in texto


# --- El contexto viaja del nivel al aviso ------------------------------------------------------

def test_evaluar_propaga_el_contexto_de_la_candidata():
    ctx = ae.Contexto(origen=ae.ORIGEN_CARTERA, cantidad=10.0)
    cand = ae.replace(candidata(cruzado=True), contexto=ctx)
    assert ae.evaluar([cand], {}).a_emitir[0].contexto == ctx


def test_candidatas_de_posiciones_llenan_el_contexto():
    item = {
        "ticker": "AL30", "nombre": "Bono AL30", "precio_actual": 95.0, "moneda": "USD",
        "cantidad_actual": 10.0, "precio_promedio": 100.0, "rendimiento_simple_usd": -0.045,
        "precio_stop_loss": 96.0, "stop_loss_disparado": True,
        "stop_loss_modo": "Fijo", "stop_loss_valor": 96.0,
    }
    ctx = ae.candidatas_de_posiciones([item], "Principal")[0].contexto
    assert ctx.origen == ae.ORIGEN_CARTERA
    assert ctx.cantidad == 10.0 and ctx.precio_promedio == 100.0
    assert ctx.resultado_pct == -4.5           # fracción → puntos porcentuales
    assert ctx.nivel_modo == "Fijo" and ctx.nivel_valor == 96.0
    assert ctx.distancia_pct == ae.distancia_pct(95.0, 96.0)


def test_candidatas_de_watchlist_llenan_el_contexto():
    item = {
        "ticker": "MSFT", "nombre": "Microsoft", "precio_actual": 24000.0,
        "precio_objetivo": 25000.0, "en_zona": True, "moneda_precio": "ARS", "en_cartera": True,
    }
    ctx = ae.candidatas_de_watchlist([item])[0].contexto
    assert ctx.origen == ae.ORIGEN_WATCHLIST
    assert ctx.en_cartera is True
    assert ctx.cantidad is None  # la watchlist no sabe de tenencias


def test_pct_desde_fraccion():
    assert ae.pct_desde_fraccion(0.286) == 28.6
    assert ae.pct_desde_fraccion(None) is None
