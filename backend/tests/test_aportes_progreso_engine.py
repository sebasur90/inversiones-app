"""Tests de la capa de progreso (`services/aportes_progreso_engine.py`), sin DB.

Fijan las reglas que hacen que la gamificación sea honesta: los niveles miden constancia y nunca
bajan, un objetivo recién creado no juzga el pasado, y sin objetivo configurado nada se da por
incumplido.

Se ejercita a través de `calcular_ritmo`, que es como la usa la app: así los tests también
protegen el contrato entre los dos motores.
"""
import pytest
from datetime import date

from app.services import aportes_engine as eng
from app.services.aportes_engine import calcular_ritmo

# 18 de septiembre: día 18 de 30, quedan 12.
HOY = date(2025, 9, 18)


def _m(neto: float, compras: float | None = None, salidas: float = 0.0) -> dict:
    return {"neto": neto, "compras": neto + salidas if compras is None else compras, "salidas": salidas}


def _serie(netos: list[float], hasta: str = "2025-09") -> dict[str, dict]:
    serie = {}
    mes = hasta
    for neto in reversed(netos):
        serie[mes] = _m(neto)
        mes = eng._sumar_meses(mes, -1)
    return serie


def _obj(monto: float, vigente_desde: str = "2025-09", retroactivo: bool = False) -> dict:
    return {"monto_usd": monto, "vigente_desde": vigente_desde, "retroactivo": retroactivo}


def _prog(netos: list[float], objetivo: dict | None = None, hoy: date = HOY) -> dict:
    return calcular_ritmo(_serie(netos), hoy, objetivo=objetivo)["progreso"]


def _logro(prog: dict, clave: str) -> dict | None:
    return next((l for l in prog["logros"] if l["clave"] == clave), None)


# ── Niveles ──────────────────────────────────────────────────────────────────

def test_sin_datos_no_tiene_progreso():
    assert calcular_ritmo({}, HOY)["progreso"] is None


def test_nivel_sin_aportes():
    prog = _prog([0.0, 0.0, 0.0])
    assert prog["nivel"]["clave"] == "sin_arrancar"
    assert prog["nivel"]["motivos"] == ["Todavía no registraste ningún aporte"]


def test_nivel_primer_paso():
    prog = _prog([0.0, 0.0, 100.0])
    assert prog["nivel"]["clave"] == "primer_paso"
    assert prog["nivel"]["orden"] == 1


def test_nivel_lo_limita_el_requisito_mas_exigente():
    """12 meses con aporte alcanzan para `disciplinado`, pero la mejor racha es 3: queda en
    `constante`, que pide racha 3."""
    netos = [100.0, 100.0, 100.0, 0.0] * 3 + [100.0]
    prog = _prog(netos)
    assert prog["nivel"]["clave"] == "constante"
    assert prog["nivel"]["siguiente"]["clave"] == "disciplinado"


def test_nivel_no_baja_tras_un_mes_en_cero():
    """La mejor racha es histórica: cortar la racha no degrada el nivel ya alcanzado."""
    con_racha = _prog([100.0] * 9 + [100.0])
    tras_corte = _prog([100.0] * 9 + [0.0])
    assert tras_corte["nivel"]["orden"] == con_racha["nivel"]["orden"]


def test_nivel_progreso_es_el_minimo_de_los_requisitos():
    prog = _prog([100.0] * 6)
    sig = prog["nivel"]["siguiente"]
    ratios = [r["actual"] / r["objetivo"] for r in sig["requisitos"] if r["objetivo"] > 0]
    assert sig["progreso_pct"] == pytest.approx(min(min(ratios) * 100, 100.0), abs=0.1)


def test_falta_texto_concuerda_en_numero():
    """"Te falta 1 mes", no "Te faltan 1 meses"."""
    uno = _prog([100.0] * 2 + [0.0])              # 2 meses con aporte: falta 1 para el siguiente
    assert uno["nivel"]["siguiente"]["falta_texto"] == "Te falta 1 mes con aporte"
    varios = _prog([100.0, 0.0, 0.0])
    assert varios["nivel"]["siguiente"]["falta_texto"] == "Te faltan 2 meses con aporte"
    # Con los dos requisitos pendientes se enumeran juntos, cada uno con su propio número.
    # Alternando aporte/cero: 5 meses con aporte pero ninguna racha mayor a 1.
    dos = _prog([100.0, 0.0] * 5 + [0.0])
    # Plural en el verbo porque son dos requisitos, singular en cada cantidad.
    assert dos["nivel"]["siguiente"]["falta_texto"] == "Te faltan 1 mes con aporte y 1 mes seguido aportando"


def test_nivel_maximo_no_tiene_siguiente():
    prog = _prog([100.0] * 30)
    assert prog["nivel"]["clave"] == "consolidado"
    assert prog["nivel"]["siguiente"] is None


def test_nivel_no_depende_del_monto():
    """Aportar 10 veces más no sube de nivel: lo que cuenta es el hábito."""
    chico = _prog([50.0] * 8)
    grande = _prog([5000.0] * 8)
    assert chico["nivel"]["clave"] == grande["nivel"]["clave"]


# ── Objetivo mensual ─────────────────────────────────────────────────────────

def test_sin_objetivo_no_se_inventa_nada():
    prog = _prog([100.0] * 6)
    obj = prog["objetivo"]
    assert obj["configurado"] is False
    assert obj["monto_usd"] is None and obj["mes_actual"] is None
    assert obj["meses_cumplidos"] is None and obj["racha_cumplimiento"] is None
    assert prog["records"]["mas_meses_cumpliendo_objetivo"] is None
    # El nivel funciona igual: no depende del objetivo.
    assert prog["nivel"]["clave"] != "sin_arrancar"
    assert prog["nivel"]["sello_objetivo"] is None


def test_sin_objetivo_la_serie_no_marca_incumplimiento():
    res = calcular_ritmo(_serie([100.0] * 4), HOY)
    assert all(s["cumple_objetivo"] is None for s in res["serie_mensual"])
    assert all(s["objetivo_usd"] is None for s in res["serie_mensual"])


def test_sin_objetivo_los_logros_de_esa_familia_quedan_no_aplica():
    prog = _prog([100.0] * 6)
    logro = _logro(prog, "objetivo_3")
    assert logro["bloqueado_por_falta_objetivo"] is True
    assert logro["desbloqueado"] is False
    # `actual is None` distingue "no se puede medir" de "vas 0 de 3".
    assert logro["actual"] is None and logro["progreso_pct"] is None


def test_objetivo_sin_aporte_es_cero_por_ciento():
    prog = _prog([100.0, 100.0, 0.0], _obj(200.0))
    mes = prog["objetivo"]["mes_actual"]
    assert mes["cumplimiento_pct"] == 0.0
    assert mes["restante_usd"] == 200.0
    assert mes["cumplido"] is False


def test_objetivo_a_la_mitad():
    prog = _prog([100.0, 100.0, 100.0], _obj(200.0))
    mes = prog["objetivo"]["mes_actual"]
    assert mes["cumplimiento_pct"] == 50.0
    assert mes["restante_usd"] == 100.0
    assert mes["cumplido"] is False


def test_objetivo_cumplido_exacto():
    prog = _prog([100.0, 100.0, 200.0], _obj(200.0))
    mes = prog["objetivo"]["mes_actual"]
    assert mes["cumplimiento_pct"] == 100.0
    assert mes["restante_usd"] == 0.0
    assert mes["cumplido"] is True
    assert mes["ritmo_necesario_diario_usd"] is None


def test_objetivo_sobrecumplido():
    """El porcentaje pasa de 100 (la barra satura en la UI, el número no miente) y no hay resto."""
    prog = _prog([100.0, 100.0, 360.0], _obj(200.0))
    mes = prog["objetivo"]["mes_actual"]
    assert mes["cumplimiento_pct"] == 180.0
    assert mes["restante_usd"] == 0.0
    assert mes["cumplido"] is True


def test_ritmo_necesario_usa_los_dias_que_quedan():
    """Faltan 120 de 200 y quedan 12 días: 10/día, 70/semana."""
    prog = _prog([100.0, 80.0], _obj(200.0))
    mes = prog["objetivo"]["mes_actual"]
    assert mes["dias_restantes"] == 12
    assert mes["ritmo_necesario_diario_usd"] == pytest.approx(10.0)
    assert mes["ritmo_necesario_semanal_usd"] == pytest.approx(70.0)


def test_ritmo_necesario_es_none_el_ultimo_dia():
    prog = _prog([100.0, 50.0], _obj(200.0), hoy=date(2025, 9, 30))
    mes = prog["objetivo"]["mes_actual"]
    assert mes["dias_restantes"] == 0
    assert mes["ritmo_necesario_diario_usd"] is None


def test_alcanzable_al_ritmo_actual():
    """Día 18 de 30 con 150 aportados proyecta 250: alcanza para una meta de 200, no para 400."""
    assert _prog([100.0, 150.0], _obj(200.0))["objetivo"]["mes_actual"]["alcanzable_al_ritmo_actual"] is True
    assert _prog([100.0, 150.0], _obj(400.0))["objetivo"]["mes_actual"]["alcanzable_al_ritmo_actual"] is False


def test_objetivo_no_juzga_meses_anteriores_a_su_vigencia():
    """Configurado en septiembre, agosto y julio quedan sin evaluar, no incumplidos."""
    res = calcular_ritmo(_serie([10.0, 10.0, 10.0, 300.0]), HOY, objetivo=_obj(200.0, "2025-09"))
    prog = res["progreso"]
    assert prog["objetivo"]["vigente_desde"] == "2025-09"
    # Sólo hay meses cerrados anteriores: ninguno entra en la evaluación.
    assert prog["objetivo"]["meses_evaluados"] == 0
    assert prog["objetivo"]["meses_cumplidos"] == 0
    anteriores = [s for s in res["serie_mensual"] if s["mes"] < "2025-09"]
    assert all(s["cumple_objetivo"] is None for s in anteriores)


def test_retroactivo_distingue_el_mes_efectivo_del_mes_en_que_se_fijo():
    """`vigente_desde` es desde cuándo se mide; `fijado_en`, cuándo se creó el objetivo. Con
    retroactividad divergen, y el modal necesita el segundo para explicar qué pasa al desmarcarla."""
    prog = _prog([300.0, 300.0, 300.0, 300.0], _obj(200.0, "2025-09", retroactivo=True))
    obj = prog["objetivo"]
    assert obj["vigente_desde"] == "2025-06"   # primer mes del historial
    assert obj["fijado_en"] == "2025-09"


def test_objetivo_retroactivo_evalua_todo_el_historial():
    res = calcular_ritmo(
        _serie([300.0, 100.0, 300.0, 50.0]), HOY, objetivo=_obj(200.0, "2025-09", retroactivo=True)
    )
    prog = res["progreso"]
    assert prog["objetivo"]["retroactivo"] is True
    assert prog["objetivo"]["meses_evaluados"] == 3     # los 3 cerrados
    assert prog["objetivo"]["meses_cumplidos"] == 2     # 300 y 300
    assert prog["objetivo"]["meses_cumplidos_pct"] == pytest.approx(66.7, abs=0.1)


def test_racha_y_record_de_cumplimiento():
    netos = [300.0, 300.0, 10.0, 300.0, 300.0, 300.0, 0.0]
    prog = _prog(netos, _obj(200.0, "2025-01", retroactivo=True))
    assert prog["objetivo"]["record_cumplimiento"] == 3
    assert prog["objetivo"]["racha_cumplimiento"] == 3   # el mes en curso no corta ni suma


def test_sello_de_objetivo_en_el_nivel():
    prog = _prog([300.0] * 6 + [0.0], _obj(200.0, "2025-01", retroactivo=True))
    assert prog["nivel"]["sello_objetivo"]["meses"] >= 3


def test_tolerancia_de_cumplimiento():
    """Quedar a centavos de la meta por el redondeo del MEP no es incumplir."""
    prog = _prog([100.0, 199.5], _obj(200.0))
    assert prog["objetivo"]["mes_actual"]["cumplido"] is True


def test_sugerido_sale_del_propio_ritmo_y_se_redondea():
    """Con 2 meses cerrados (100 y 200) no hay promedio de 3: cae al histórico, 150."""
    prog = _prog([100.0, 200.0, 300.0])
    assert prog["objetivo"]["sugerido_usd"] == 150.0
    assert prog["objetivo"]["sugerido_origen"] == "promedio_historico"


def test_sugerido_se_redondea_a_multiplos_de_diez():
    prog = _prog([187.0, 194.0, 0.0])
    assert prog["objetivo"]["sugerido_usd"] == 190.0


# ── Logros ───────────────────────────────────────────────────────────────────

def test_logro_desbloqueado_lleva_la_fecha():
    prog = _prog([100.0] * 5)
    logro = _logro(prog, "racha_3")
    assert logro["desbloqueado"] is True
    assert logro["fecha"] == "2025-07"   # el mes en que llegó a 3 seguidos


def test_logro_bloqueado_lleva_el_progreso():
    prog = _prog([100.0] * 8)
    logro = _logro(prog, "racha_12")
    assert logro["desbloqueado"] is False and logro["fecha"] is None
    assert logro["actual"] == 8 and logro["progreso_pct"] == pytest.approx(66.7, abs=0.1)


def test_logro_de_capital_usa_el_neto_acumulado():
    prog = _prog([600.0, 600.0])
    assert _logro(prog, "total_1000")["desbloqueado"] is True
    assert _logro(prog, "total_5000")["desbloqueado"] is False


def test_logro_anio_completo_solo_con_anio_cerrado():
    """12 meses seguidos a caballo de dos años no completan ningún año calendario."""
    prog = _prog([100.0] * 13)
    assert _logro(prog, "anio_completo")["desbloqueado"] is False


def test_logro_anio_completo_con_2024_entero():
    serie = {f"2024-{m:02d}": _m(100.0) for m in range(1, 13)}
    serie["2025-09"] = _m(100.0)
    prog = calcular_ritmo(serie, HOY)["progreso"]
    logro = _logro(prog, "anio_completo")
    assert logro["desbloqueado"] is True and logro["fecha"] == "2024-12"


def test_logros_de_objetivo_se_desbloquean_con_cumplimiento():
    prog = _prog([300.0, 300.0, 300.0, 0.0], _obj(200.0, "2025-01", retroactivo=True))
    assert _logro(prog, "objetivo_3")["desbloqueado"] is True
    assert _logro(prog, "objetivo_racha_3")["desbloqueado"] is True
    assert _logro(prog, "objetivo_racha_6")["desbloqueado"] is False


# ── Récords ──────────────────────────────────────────────────────────────────

def test_records_basicos():
    serie = {f"2024-{m:02d}": _m(100.0) for m in range(1, 13)}
    serie["2024-06"] = _m(900.0)
    serie["2025-09"] = _m(50.0)
    prog = calcular_ritmo(serie, HOY)["progreso"]
    rec = prog["records"]
    assert rec["mayor_aporte_mensual"]["mes"] == "2024-06"
    assert rec["mayor_aporte_mensual"]["neto_usd"] == 900.0
    # 11 meses de 100 + junio de 900.
    assert rec["mayor_aporte_anual"] == {"anio": 2024, "total_usd": 2000.0}
    assert rec["mayor_promedio_mensual_anual"]["anio"] == 2024
    assert rec["mejor_racha"]["meses"] >= 12


def test_records_sin_anio_cerrado():
    prog = _prog([100.0, 100.0, 100.0])
    assert prog["records"]["mayor_aporte_anual"] is None
    assert prog["records"]["mayor_promedio_mensual_anual"] is None


def test_record_de_meses_cumpliendo_objetivo():
    serie = {f"2024-{m:02d}": _m(300.0) for m in range(1, 6)}
    serie["2025-09"] = _m(300.0)
    prog = calcular_ritmo(serie, HOY, objetivo=_obj(200.0, "2024-01", retroactivo=True))["progreso"]
    assert prog["records"]["mas_meses_cumpliendo_objetivo"] == {"anio": 2024, "meses": 5}


# ── Evolución ────────────────────────────────────────────────────────────────

def test_evolucion_sube():
    prog = _prog([100.0, 100.0, 100.0, 200.0, 200.0, 200.0, 0.0])
    assert prog["evolucion"]["clave"] == "sube"
    assert prog["evolucion"]["delta_pct"] == pytest.approx(100.0)


def test_evolucion_baja():
    prog = _prog([200.0, 200.0, 200.0, 100.0, 100.0, 100.0, 0.0])
    assert prog["evolucion"]["clave"] == "baja"
    # Describe, no culpa.
    assert "abajo" in prog["evolucion"]["frase"]


def test_evolucion_estable():
    prog = _prog([100.0] * 7)
    assert prog["evolucion"]["clave"] == "estable"


def test_evolucion_sin_historial():
    prog = _prog([100.0, 100.0])
    assert prog["evolucion"]["clave"] == "sin_historial"
    assert prog["evolucion"]["delta_pct"] is None


# ── Proyección del ritmo ─────────────────────────────────────────────────────

def test_proyeccion_por_horizonte():
    prog = _prog([200.0] * 13)
    proy = prog["proyeccion_ritmo"]
    assert proy["ritmo_mensual_usd"] == 200.0
    assert proy["origen"] == "promedio_12"
    assert [h["total_usd"] for h in proy["horizontes"]] == [2400.0, 7200.0, 12000.0, 24000.0]


def test_proyeccion_sin_aportes_no_muestra_ceros():
    prog = _prog([0.0, 0.0, 0.0, 0.0])
    proy = prog["proyeccion_ritmo"]
    assert proy["origen"] == "insuficiente"
    assert proy["horizontes"] == [] and proy["escenarios_aumento"] == []


def test_proyeccion_cae_al_promedio_disponible():
    prog = _prog([300.0, 300.0, 300.0, 0.0])
    assert prog["proyeccion_ritmo"]["origen"] == "promedio_3"


def test_escenarios_de_aumento_solo_suman_aportes():
    prog = _prog([200.0] * 13)
    mas50 = next(e for e in prog["proyeccion_ritmo"]["escenarios_aumento"] if e["clave"] == "mas_50")
    assert mas50["ritmo_resultante_usd"] == 250.0
    un_anio = mas50["horizontes"][0]
    assert un_anio["total_usd"] == 3000.0 and un_anio["extra_usd"] == 600.0


def test_proyeccion_lleva_disclaimer():
    prog = _prog([200.0] * 13)
    assert "No incluye rendimiento" in prog["proyeccion_ritmo"]["disclaimer"]


# ── Misión ───────────────────────────────────────────────────────────────────

def test_mision_sin_aportes_es_el_primero():
    prog = _prog([0.0, 0.0])
    assert prog["mision"]["clave"] == "primer_aporte"


def test_mision_prioriza_el_objetivo_del_mes():
    prog = _prog([100.0, 100.0, 50.0], _obj(200.0))
    assert prog["mision"]["clave"] == "objetivo_mes"
    assert prog["mision"]["objetivo"] == 200.0


def test_mision_pasa_a_la_racha_de_cumplimiento_si_el_mes_ya_esta():
    prog = _prog([300.0, 300.0, 300.0], _obj(200.0, "2025-01", retroactivo=True))
    assert prog["mision"]["clave"].startswith("objetivo_racha_")


def test_mision_sin_objetivo_es_de_racha():
    prog = _prog([100.0, 100.0])
    assert prog["mision"]["clave"] == "racha_3"
    assert prog["mision"]["actual"] == 2.0


def test_mision_nunca_pide_aportar_mas():
    """Ninguna misión sugiere subir el aporte: sólo sostener el hábito o cumplir lo ya fijado."""
    for netos, obj in ([100.0, 100.0], None), ([100.0, 50.0], _obj(200.0)), ([0.0], None):
        mision = _prog(netos, obj)["mision"]
        assert mision is None or "más" not in mision["titulo"].lower()
