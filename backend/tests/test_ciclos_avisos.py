"""Avisos de Ciclos de mercado por Telegram: qué cambio es novedad (motor puro) y qué se manda (adaptador).

Sólo se avisan cambios **confirmados** de grupos donde hay posición, una vez por cambio, sin recomendar nada.
"""
import re
from datetime import date, datetime, timedelta

import pytest
from app.database import AjustesAvisos, CiclosAvisoEmitido, CiclosEstadoHistorial
from app.services import ciclos_avisos as av
from app.services import ciclos_avisos_engine as ae
from app.services import ciclos_engine as eng
from app.services.notificaciones import telegram

from .ciclos_helpers import cartera_de_prueba, fin

HOY = date(2025, 3, 14)

PROHIBIDO = re.compile(r"compr\w*|vend\w*|recomend\w*|conviene|deber[ií]a", re.IGNORECASE)


def _c(tipo="empieza_a_mejorar", desde=date(2025, 3, 7), grupo="tecnologia", de="lagging", a="improving"):
    return ae.Cambio(grupo, "estados-unidos", tipo, desde, de, a, 3)


# -- motor puro ----------------------------------------------------------------------------------

def test_primera_vez_siembra_todo_sin_avisar():
    r = ae.clasificar([_c(), _c(desde=date(2025, 2, 28))], set(), HOY, primera_vez=True)
    assert len(r[ae.SEMBRADO]) == 2 and not r[ae.NUEVO] and not r[ae.VIEJO]


def test_un_cambio_reciente_es_novedad():
    assert ae.clasificar([_c()], set(), HOY)[ae.NUEVO] == [_c()]


def test_un_cambio_ya_registrado_no_se_repite():
    c = _c()
    r = ae.clasificar([c], {c.clave}, HOY)
    assert not any(r.values())


def test_un_cambio_viejo_se_registra_sin_avisar():
    viejo = _c(desde=HOY - timedelta(days=ae.MAX_DIAS_CAMBIO + 1))
    limite = _c(desde=HOY - timedelta(days=ae.MAX_DIAS_CAMBIO), grupo="salud")
    r = ae.clasificar([viejo, limite], set(), HOY)
    assert r[ae.VIEJO] == [viejo] and r[ae.NUEVO] == [limite]


def test_desde_senales_ignora_los_pendientes():
    senales = {"eventos": [
        {"tipo": "empieza_a_mejorar", "desde": date(2025, 3, 7), "de": "lagging", "a": "improving",
         "semanas_sostenido": 3, "confirmado": True},
        {"tipo": "pasa_a_liderar", "desde": date(2025, 3, 14), "de": "improving", "a": "leading",
         "semanas_sostenido": 1, "confirmado": False},
    ]}
    cambios = ae.desde_senales("tecnologia", "estados-unidos", senales)
    assert [c.tipo for c in cambios] == ["empieza_a_mejorar"] and cambios[0].semanas == 3


def test_un_cambio_con_dos_tipos_es_un_solo_aviso():
    grupos = ae.agrupar([_c("pierde_momentum", de="leading", a="weakening"), _c("pierde_fortaleza_relativa", de="leading", a="weakening"),
                         _c(grupo="salud")])
    assert sorted(len(g) for g in grupos) == [1, 2]


def _aviso(**kw):
    base = dict(nombre="Tecnología", tipo_grupo="sector", benchmark="S&P 500", de="lagging", a="improving",
                desde=date(2025, 3, 7), semanas=3, tipos=("empieza_a_mejorar",), peso_pct=34.5, tickers=("MSFT", "NVDA"))
    return ae.AvisoGrupo(**{**base, **kw})


def test_el_mensaje_dice_que_cambio_cuanto_pesa_y_no_recomienda():
    texto = ae.texto_notificacion([_aviso()])
    assert "Lagging → <b>Improving</b>" in texto and "34,5 %" in texto and "MSFT, NVDA" in texto
    assert "S&amp;P 500" in texto                                   # el HTML se escapa
    assert "desde la semana del 07/03/2025" in texto and "Sostenido 3 semanas" in texto
    assert not PROHIBIDO.search(texto.replace("no es una indicación de operar", ""))


def test_el_mensaje_ordena_por_peso_y_recorta_los_tickers():
    texto = ae.texto_notificacion([_aviso(nombre="Chico", peso_pct=1.0),
                                   _aviso(nombre="Grande", peso_pct=50.0, tickers=tuple("ABCDEF"))])
    assert texto.index("Grande") < texto.index("Chico") and "2 cambios confirmados" in texto
    assert "A, B, C, D y 2 más" in texto


# -- adaptador -----------------------------------------------------------------------------------

@pytest.fixture
def sesion(tmp_path, monkeypatch):
    return cartera_de_prueba(tmp_path, monkeypatch)


@pytest.fixture
def db(sesion):
    s = sesion()
    yield s
    s.close()


@pytest.fixture
def enviados(monkeypatch):
    mandados = []
    monkeypatch.setattr(telegram, "enviar", lambda texto, parse_mode=None: (mandados.append(texto) or (True, None)))
    return mandados


def _historial(db, grupo, secuencia, bench="estados-unidos", semanas_despues=0):
    """Una semana por letra, terminando en el último viernes más `semanas_despues` (L/W/G/I = cuadrante).
    Reemplaza lo anterior. Para simular que pasó una semana, se agrega una letra y se suma 1 a `semanas_despues`."""
    db.query(CiclosEstadoHistorial).filter_by(grupo_id=grupo, benchmark_id=bench).delete()
    nombres = {"L": eng.LEADING, "W": eng.WEAKENING, "G": eng.LAGGING, "I": eng.IMPROVING}
    ultimo = fin() + timedelta(days=7 * semanas_despues)
    for i, letra in enumerate(secuencia):
        semana = ultimo - timedelta(days=7 * (len(secuencia) - 1 - i))
        db.add(CiclosEstadoHistorial(
            grupo_id=grupo, benchmark_id=bench, semana=semana, cuadrante=nombres[letra], rs_ratio=100, rs_momentum=100,
            version_algoritmo=eng.VERSION_ALGORITMO, ultima_fecha_datos=semana, calculado_en=datetime.utcnow()))
    db.commit()


def _filas(db):
    return db.query(CiclosAvisoEmitido).order_by(CiclosAvisoEmitido.id).all()


def test_la_primera_corrida_siembra_y_la_siguiente_avisa_lo_nuevo(db, enviados):
    _historial(db, "tecnologia", "GGGGGGGGGG")                         # sin cambios todavía
    r = av.evaluar_y_notificar(db)
    assert r["cambios_confirmados"] == 0 and not enviados
    assert db.query(AjustesAvisos).first().ciclos_semilla_en is not None   # sembrar es un hecho, aunque no haya filas

    _historial(db, "tecnologia", "GGGGGGGIIII")                        # ahora sí cambia
    r = av.evaluar_y_notificar(db)
    assert r["nuevos"] == 1 and r["avisados"] == 1 and r["entregado"] is True
    assert len(enviados) == 1 and "Tecnología" in enviados[0] and "Lagging → <b>Improving</b>" in enviados[0]
    assert "En tu cartera: 51,7 % del capital (MSFT, NVDA)" in enviados[0]      # 1.500 de 2.900 USD


def test_lo_que_ya_habia_en_la_primera_corrida_no_se_avisa(db, enviados):
    _historial(db, "tecnologia", "GGGGGGGIIII")
    r = av.evaluar_y_notificar(db)
    assert r["sembrados"] == 1 and r["avisados"] == 0 and not enviados
    assert [f.motivo for f in _filas(db)] == ["sembrado"]


def test_un_cambio_se_avisa_una_sola_vez(db, enviados):
    av.evaluar_y_notificar(db)                                         # siembra
    _historial(db, "tecnologia", "GGGGGGGIIII")
    av.evaluar_y_notificar(db)
    r = av.evaluar_y_notificar(db)
    assert r["nuevos"] == 0 and r["avisados"] == 0 and len(enviados) == 1
    _historial(db, "tecnologia", "GGGGGGGIIIII", semanas_despues=1)     # el tramo sigue creciendo: mismo cambio
    av.evaluar_y_notificar(db)
    assert len(enviados) == 1


def test_un_grupo_sin_posicion_no_avisa(db, enviados):
    av.evaluar_y_notificar(db)
    _historial(db, "salud", "GGGGGGGIIII")                             # no hay nada de salud en la cartera
    r = av.evaluar_y_notificar(db)
    assert r["nuevos"] == 1 and r["sin_posicion"] == 1 and r["avisados"] == 0 and not enviados
    assert [f.motivo for f in _filas(db)] == ["sin_posicion"]
    av.evaluar_y_notificar(db)
    assert len(_filas(db)) == 1                                         # y no se reevalúa en cada corrida


def test_un_cambio_pendiente_no_se_avisa_hasta_confirmarse(db, enviados):
    av.evaluar_y_notificar(db)
    _historial(db, "tecnologia", "GGGGGGGGGII")                        # 2 semanas en Improving: todavía no confirma
    assert av.evaluar_y_notificar(db)["cambios_confirmados"] == 0 and not enviados
    _historial(db, "tecnologia", "GGGGGGGGGIII")                       # la tercera confirma
    assert av.evaluar_y_notificar(db)["avisados"] == 1 and len(enviados) == 1


def test_con_el_aviso_apagado_se_registra_y_no_se_manda(db, enviados):
    av.evaluar_y_notificar(db)
    db.query(AjustesAvisos).update({"avisar_ciclos": 0})
    db.commit()
    _historial(db, "tecnologia", "GGGGGGGIIII")
    r = av.evaluar_y_notificar(db)
    assert r["silenciados"] == 1 and not enviados
    db.query(AjustesAvisos).update({"avisar_ciclos": 1})
    db.commit()
    assert av.evaluar_y_notificar(db)["avisados"] == 0 and not enviados     # prender después no manda lo que pasó


def test_si_el_envio_falla_se_reintenta_sin_duplicar(db, monkeypatch):
    av.evaluar_y_notificar(db)
    _historial(db, "tecnologia", "GGGGGGGIIII")
    monkeypatch.setattr(telegram, "enviar", lambda *a, **k: (False, "sin red"))
    r = av.evaluar_y_notificar(db)
    assert r["avisados"] == 1 and r["entregado"] is False and r["motivo"] == "sin red"
    assert [(f.motivo, f.entregado) for f in _filas(db)] == [("nuevo", 0)]

    mandados = []
    monkeypatch.setattr(telegram, "enviar", lambda texto, parse_mode=None: (mandados.append(texto) or (True, None)))
    r = av.evaluar_y_notificar(db)
    assert r["nuevos"] == 0 and r["avisados"] == 1 and len(mandados) == 1
    assert [(f.motivo, f.entregado) for f in _filas(db)] == [("nuevo", 1)] and _filas(db)[0].emitido_en is not None
    av.evaluar_y_notificar(db)
    assert len(mandados) == 1


def test_un_pendiente_que_envejece_se_descarta(db, monkeypatch):
    av.evaluar_y_notificar(db)
    _historial(db, "tecnologia", "GGGGGGGIIII")
    monkeypatch.setattr(telegram, "enviar", lambda *a, **k: (False, "sin red"))
    av.evaluar_y_notificar(db)
    monkeypatch.setattr(telegram, "enviar", lambda *a, **k: pytest.fail("un aviso viejo no se manda"))
    r = av.evaluar_y_notificar(db, hoy=date.today() + timedelta(days=ae.MAX_DIAS_CAMBIO + 1))
    assert r["avisados"] == 0 and [(f.motivo, f.entregado) for f in _filas(db)] == [("viejo", 1)]


def test_sin_notificar_siembra_sin_dejar_nada_encolado(db, monkeypatch):
    monkeypatch.setattr(telegram, "enviar", lambda *a, **k: pytest.fail("no debería mandar"))
    av.evaluar_y_notificar(db)
    _historial(db, "tecnologia", "GGGGGGGIIII")
    r = av.evaluar_y_notificar(db, notificar=False)
    assert r["silenciados"] == 1 and all(f.entregado == 1 for f in _filas(db))


def test_correr_nunca_lanza(db, monkeypatch):
    monkeypatch.setattr(av, "evaluar_y_notificar", lambda *a, **k: 1 / 0)
    assert av.correr(db)["resultado"] == "error"


def test_la_config_expone_el_interruptor(db):
    from app.services import avisos_config
    assert avisos_config.estado(db)["avisar_ciclos"] is True
    avisos_config.actualizar(db, avisar_ciclos=False)
    assert avisos_config.estado(db)["avisar_ciclos"] is False and avisos_config.ciclos_habilitado(db) is False
