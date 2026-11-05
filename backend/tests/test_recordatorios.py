"""Recordatorios con fecha: alta y edición, vencimiento en la zona del scheduler, y la regla central del
aviso: sólo se marca como enviado lo que Telegram confirmó."""
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, EventoMercado, PrecioInstrumento, PrecioSubyacente, Recordatorio, get_db
from app.main import app
from app.services import ohlcv_analytics, recordatorios as servicio, sync_lock
from app.services.eventos import eventos_analytics
from app.services.notificaciones import telegram

URL = "/api/inversiones/recordatorios"
AHORA = datetime(2026, 7, 8, 10, 0)


@pytest.fixture
def entorno(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)

    def override():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(servicio, "ahora_local", lambda: AHORA)
    yield TestClient(app), Sesion
    app.dependency_overrides.clear()


@pytest.fixture
def canal(monkeypatch):
    """Telegram prendido y configurado; `canal.enviados` junta lo que salió, `canal.falla` lo hace fallar."""
    class Canal:
        enviados: list[str] = []
        falla: str | None = None

    Canal.enviados = []
    Canal.falla = None

    def enviar(texto, parse_mode=None):
        if Canal.falla:
            return False, Canal.falla
        Canal.enviados.append(texto)
        return True, None

    monkeypatch.setattr(telegram, "alertas_habilitadas", lambda: True)
    monkeypatch.setattr(telegram, "configurado", lambda: True)
    monkeypatch.setattr(telegram, "enviar", enviar)
    return Canal


def _alta(s, **kw) -> Recordatorio:
    datos = dict(titulo="Revisar acciones", fecha=date(2026, 7, 8), estado="pendiente", tickers=[],
                 creado_en=datetime(2026, 1, 1), actualizado_en=datetime(2026, 1, 1))
    datos.update(kw)
    r = Recordatorio(**datos)
    s.add(r)
    s.commit()
    return r


# --- Alta, edición y baja ----------------------------------------------------------------------

def test_alta_normaliza_y_calcula_el_vencimiento(entorno):
    client, _ = entorno
    r = client.post(URL, json={"titulo": "  Tras las elecciones ", "fecha": "2026-07-10", "nota": " mirar ",
                               "tickers": ["aapl", " MELI ", "AAPL", ""]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["titulo"] == "Tras las elecciones"
    assert d["nota"] == "mirar"
    assert d["tickers"] == ["AAPL", "MELI"]
    assert client.post(URL, json={"titulo": "x", "fecha": "2026-07-10", "tickers": ["^merv", "brk.b"]}).json()["tickers"] == ["^MERV", "BRK.B"]
    assert d["vence_en"] == "2026-07-10T09:00"     # sin hora avisa a las 9
    assert d["vencido"] is False
    assert d["estado"] == "pendiente"


@pytest.mark.parametrize("cuerpo, mensaje", [
    ({"titulo": "x", "fecha": "2026-07-07"}, "Esa fecha ya pasó."),
    ({"titulo": "x", "fecha": "2026-07-08", "hora": "09:59"}, "Esa hora de hoy ya pasó."),
    ({"titulo": "x", "fecha": "2026-07-08", "hora": "10:00"}, "Esa hora de hoy ya pasó."),
    ({"titulo": "   ", "fecha": "2026-07-10"}, "El recordatorio necesita un título."),
    ({"titulo": "x", "fecha": "2026-07-10", "tickers": ["<b>"]}, "Hay un ticker con caracteres que no corresponden."),
    ({"titulo": "x", "fecha": "2026-07-10", "evento_id": 99}, "El evento vinculado ya no existe."),
])
def test_alta_rechaza_con_un_mensaje_claro(entorno, cuerpo, mensaje):
    client, _ = entorno
    r = client.post(URL, json=cuerpo)
    assert r.status_code == 422
    assert r.json()["detail"] == mensaje


@pytest.mark.parametrize("cuerpo", [
    {"titulo": "x", "fecha": "2026-07-10", "hora": "24:00"},
    {"titulo": "x", "fecha": "2026-07-10", "tickers": [f"T{i}" for i in range(21)]},
    {"titulo": "x" * 201, "fecha": "2026-07-10"},
    {"titulo": "x", "fecha": "2026-07-10", "nota": "x" * 1001},
])
def test_alta_valida_los_limites(entorno, cuerpo):
    client, _ = entorno
    assert client.post(URL, json=cuerpo).status_code == 422


def test_hoy_sin_hora_se_acepta_aunque_ya_hayan_pasado_las_nueve(entorno):
    client, _ = entorno
    d = client.post(URL, json={"titulo": "x", "fecha": "2026-07-08"}).json()
    assert d["vencido"] is True


def test_lista_vencidos_primero_y_hechos_al_final(entorno):
    client, Sesion = entorno
    s = Sesion()
    _alta(s, titulo="lejano", fecha=date(2026, 8, 1))
    _alta(s, titulo="vencido", fecha=date(2026, 7, 1))
    _alta(s, titulo="hecho", fecha=date(2026, 6, 1), estado="hecho", hecho_en=datetime(2026, 6, 2))
    s.close()
    d = client.get(URL).json()
    assert [i["titulo"] for i in d["items"]] == ["vencido", "lejano", "hecho"]
    assert [i["vencido"] for i in d["items"]] == [True, False, False]


def test_borrar_y_no_encontrado(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s).id
    s.close()
    assert client.delete(f"{URL}/{rid}").status_code == 204
    assert client.delete(f"{URL}/{rid}").status_code == 404
    assert client.patch(f"{URL}/{rid}", json={"titulo": "y"}).status_code == 404


def test_editar_sin_cambiar_la_fecha_no_exige_que_sea_futura_ni_rearma(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, fecha=date(2026, 7, 1), aviso_enviado_en=datetime(2026, 7, 1, 12)).id
    s.close()
    r = client.patch(f"{URL}/{rid}", json={"titulo": "otro", "nota": "n", "fecha": "2026-07-01"})
    assert r.status_code == 200, r.text
    assert r.json()["titulo"] == "otro"
    assert r.json()["aviso_enviado_en"] is not None


def test_editar_rechaza_sin_tocar_nada(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, titulo="original", fecha=date(2026, 7, 20)).id
    s.close()
    assert client.patch(f"{URL}/{rid}", json={"titulo": "nuevo", "fecha": "2026-07-01"}).status_code == 422
    s = Sesion()
    fila = s.get(Recordatorio, rid)
    assert (fila.titulo, fila.fecha) == ("original", date(2026, 7, 20))
    s.close()


def test_quitar_la_hora_con_null(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, fecha=date(2026, 7, 20), hora="15:30").id
    s.close()
    d = client.patch(f"{URL}/{rid}", json={"hora": None}).json()
    assert d["hora"] is None
    assert d["vence_en"] == "2026-07-20T09:00"


def test_hecho_y_reabrir(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, fecha=date(2026, 7, 1)).id
    s.close()
    d = client.patch(f"{URL}/{rid}", json={"estado": "hecho"}).json()
    assert d["estado"] == "hecho" and d["hecho_en"] is not None and d["vencido"] is False
    assert client.post(f"{URL}/{rid}/posponer", json={"dias": 1}).status_code == 422
    d = client.patch(f"{URL}/{rid}", json={"estado": "pendiente"}).json()
    assert d["estado"] == "pendiente" and d["hecho_en"] is None and d["vencido"] is True


# --- Posponer ----------------------------------------------------------------------------------

def test_posponer_uno_vencido_cuenta_desde_hoy_conserva_la_hora_y_rearma(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, fecha=date(2026, 7, 1), hora="15:30", aviso_enviado_en=datetime(2026, 7, 1, 18)).id
    s.close()
    d = client.post(f"{URL}/{rid}/posponer", json={"dias": 1}).json()
    assert d["fecha"] == "2026-07-09"
    assert d["hora"] == "15:30"
    assert d["aviso_enviado_en"] is None
    assert d["vencido"] is False


def test_posponer_uno_futuro_nunca_lo_adelanta(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, fecha=date(2026, 8, 1)).id
    s.close()
    assert client.post(f"{URL}/{rid}/posponer", json={"dias": 7}).json()["fecha"] == "2026-08-08"


def test_posponer_solo_uno_o_siete_dias(entorno):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s).id
    s.close()
    assert client.post(f"{URL}/{rid}/posponer", json={"dias": 3}).status_code == 422


def test_cambiar_la_fecha_rearma_el_aviso(entorno, canal):
    client, Sesion = entorno
    s = Sesion()
    rid = _alta(s, fecha=date(2026, 7, 1), aviso_enviado_en=datetime(2026, 7, 1, 12)).id
    s.close()
    d = client.patch(f"{URL}/{rid}", json={"fecha": "2026-07-09", "hora": "11:00"}).json()
    assert d["aviso_enviado_en"] is None
    s = Sesion()
    assert servicio.avisar_vencidos(s, ahora=datetime(2026, 7, 9, 11, 0))["entregados"] == 1
    s.close()


# --- Vencimiento en la zona del scheduler ------------------------------------------------------

@pytest.mark.parametrize("ahora, vencidos", [
    (datetime(2026, 7, 10, 8, 59), 0),
    (datetime(2026, 7, 10, 9, 0), 1),
])
def test_sin_hora_vence_a_las_nueve_justas(entorno, canal, ahora, vencidos):
    _, Sesion = entorno
    s = Sesion()
    _alta(s, fecha=date(2026, 7, 10))
    assert servicio.avisar_vencidos(s, ahora=ahora)["vencidos"] == vencidos
    s.close()


def test_ahora_local_usa_la_zona_del_scheduler_y_no_utc(monkeypatch):
    """A las 22:00 de Buenos Aires en UTC ya es el día siguiente: un recordatorio de mañana no venció."""
    import app.services.recordatorios as modulo

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(modulo, "datetime", Reloj)
    monkeypatch.delenv("SCHEDULER_TZ", raising=False)
    ahora = modulo.ahora_local()
    assert (ahora.year, ahora.month, ahora.day, ahora.hour) == (2026, 7, 9, 22)
    assert ahora.tzinfo is None
    monkeypatch.setenv("SCHEDULER_TZ", "UTC")
    assert modulo.ahora_local().day == 10


# --- Aviso por Telegram ------------------------------------------------------------------------

def test_avisa_una_sola_vez(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    r = _alta(s)
    assert servicio.avisar_vencidos(s, ahora=AHORA) == {"vencidos": 1, "entregados": 1, "motivo": None}
    assert s.get(Recordatorio, r.id).aviso_enviado_en is not None
    assert servicio.avisar_vencidos(s, ahora=AHORA)["vencidos"] == 0
    assert len(canal.enviados) == 1
    s.close()


def test_avisa_un_sabado(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    sabado = datetime(2026, 7, 11, 9, 5)
    assert sabado.weekday() == 5
    _alta(s, fecha=sabado.date())
    assert servicio.avisar_vencidos(s, ahora=sabado)["entregados"] == 1
    s.close()


def test_un_mensaje_por_recordatorio(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    _alta(s, titulo="uno")
    _alta(s, titulo="dos")
    assert servicio.avisar_vencidos(s, ahora=AHORA)["entregados"] == 2
    assert len(canal.enviados) == 2
    s.close()


def test_si_telegram_falla_no_marca_y_reintenta(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    r = _alta(s)
    canal.falla = "no hubo respuesta de Telegram"
    resumen = servicio.avisar_vencidos(s, ahora=AHORA)
    assert resumen["entregados"] == 0 and resumen["motivo"] == canal.falla
    assert s.get(Recordatorio, r.id).aviso_enviado_en is None
    canal.falla = None
    assert servicio.avisar_vencidos(s, ahora=AHORA)["entregados"] == 1
    s.close()


def test_un_fallo_no_frena_a_los_demas(entorno, canal, monkeypatch):
    _, Sesion = entorno
    s = Sesion()
    _alta(s, titulo="falla")
    otro = _alta(s, titulo="sale")

    def enviar(texto, parse_mode=None):
        return ("sale" in texto, None if "sale" in texto else "rechazado")

    monkeypatch.setattr(telegram, "enviar", enviar)
    assert servicio.avisar_vencidos(s, ahora=AHORA)["entregados"] == 1
    assert s.get(Recordatorio, otro.id).aviso_enviado_en is not None
    s.close()


@pytest.mark.parametrize("habilitadas, configurado", [(False, True), (True, False)])
def test_telegram_inactivo_no_envia_ni_marca(entorno, canal, monkeypatch, habilitadas, configurado):
    _, Sesion = entorno
    s = Sesion()
    r = _alta(s)
    monkeypatch.setattr(telegram, "alertas_habilitadas", lambda: habilitadas)
    monkeypatch.setattr(telegram, "configurado", lambda: configurado)
    assert servicio.avisar_vencidos(s, ahora=AHORA)["motivo"] == "telegram_inactivo"
    assert canal.enviados == []
    assert s.get(Recordatorio, r.id).aviso_enviado_en is None
    s.close()


def test_con_un_sync_en_curso_saltea_sin_enviar(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    r = _alta(s)
    sync_lock.lock.acquire()
    try:
        assert servicio.avisar_vencidos(s, ahora=AHORA)["motivo"] == "lock_ocupado"
    finally:
        sync_lock.lock.release()
    assert canal.enviados == []
    assert s.get(Recordatorio, r.id).aviso_enviado_en is None
    assert servicio.avisar_vencidos(s, ahora=AHORA)["entregados"] == 1
    s.close()


def test_un_hecho_no_se_avisa(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    _alta(s, estado="hecho", hecho_en=AHORA)
    assert servicio.avisar_vencidos(s, ahora=AHORA)["vencidos"] == 0
    assert canal.enviados == []
    s.close()


def test_el_texto_libre_va_escapado(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    _alta(s, titulo="<b>Fed</b> & tasas", nota="a < b")
    servicio.avisar_vencidos(s, ahora=AHORA)
    texto = canal.enviados[0]
    assert "&lt;b&gt;Fed&lt;/b&gt; &amp; tasas" in texto
    assert "a &lt; b" in texto
    s.close()


def test_el_mensaje_trae_precios_y_evento(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    ahora = datetime.utcnow()
    evento = EventoMercado(titulo="Elecciones", categoria="elecciones", fecha_evento=date(2026, 7, 9),
                           fecha_creacion=ahora, fecha_actualizacion=ahora)
    s.add(evento)
    s.add(PrecioSubyacente(ticker="AAPL", fecha=date(2026, 7, 7), precio=1180.2, moneda="USD", fuente="yahoo"))
    s.commit()
    _alta(s, tickers=["AAPL", "NOEXISTE"], evento_id=evento.id, hora="09:30", nota="mirar")
    servicio.avisar_vencidos(s, ahora=AHORA)
    texto = canal.enviados[0]
    assert "08/07/2026 09:30" in texto
    assert "• AAPL: USD 1.180,20 (07/07)" in texto
    assert "• NOEXISTE: sin precio" in texto
    assert "Evento: Elecciones" in texto
    s.close()


def test_si_fallan_los_precios_el_aviso_sale_igual(entorno, canal, monkeypatch):
    _, Sesion = entorno
    s = Sesion()
    r = _alta(s, tickers=["AAPL"])

    def rompe(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ohlcv_analytics, "ultimo_precio_subyacente", rompe)
    assert servicio.avisar_vencidos(s, ahora=AHORA)["entregados"] == 1
    assert "• AAPL: sin precio" in canal.enviados[0]
    assert s.get(Recordatorio, r.id).aviso_enviado_en is not None
    s.close()


# --- Estado del canal --------------------------------------------------------------------------

@pytest.mark.parametrize("scheduler_on, habilitadas, configurado, activo, pista", [
    (False, True, True, False, "SCHEDULER_ENABLED"),
    (True, False, True, False, "ALERTAS_ENABLED"),
    (True, True, False, False, "TELEGRAM_BOT_TOKEN"),
    (True, True, True, True, None),
])
def test_la_lista_dice_si_los_avisos_van_a_llegar(entorno, monkeypatch, scheduler_on, habilitadas, configurado, activo, pista):
    client, _ = entorno
    monkeypatch.setattr(servicio.scheduler, "habilitado", lambda: scheduler_on)
    monkeypatch.setattr(telegram, "alertas_habilitadas", lambda: habilitadas)
    monkeypatch.setattr(telegram, "configurado", lambda: configurado)
    d = client.get(URL).json()
    assert d["avisos_activos"] is activo
    assert (d["motivo_inactivo"] is None) if pista is None else (pista in d["motivo_inactivo"])


# --- Vínculo con eventos -----------------------------------------------------------------------

def test_borrar_un_evento_manual_suelta_el_recordatorio(entorno):
    client, Sesion = entorno
    s = Sesion()
    ahora = datetime.utcnow()
    evento = EventoMercado(titulo="Elecciones", categoria="elecciones", fecha_evento=date(2026, 7, 9), origen="manual",
                           fecha_creacion=ahora, fecha_actualizacion=ahora)
    s.add(evento)
    s.commit()
    rid = _alta(s, fecha=date(2026, 7, 10), evento_id=evento.id).id
    assert client.get(URL).json()["items"][0]["evento_titulo"] == "Elecciones"
    eventos_analytics.borrar(s, evento)
    s.close()
    item = client.get(URL).json()["items"][0]
    assert item["id"] == rid and item["evento_id"] is None and item["evento_titulo"] is None


# --- Precio local ------------------------------------------------------------------------------

def test_sin_subyacente_usa_el_ultimo_precio_local(entorno, canal):
    _, Sesion = entorno
    s = Sesion()
    s.add_all([
        PrecioInstrumento(ticker="GGAL", fecha=date(2026, 7, 1), precio=100.0, moneda="ARS"),
        PrecioInstrumento(ticker="GGAL", fecha=date(2026, 7, 7), precio=7500.5, moneda="ARS"),
        PrecioInstrumento(ticker="GGAL", fecha=date(2026, 7, 9), precio=9999.0, moneda="ARS"),   # posterior a "hoy"
    ])
    s.commit()
    _alta(s, tickers=["GGAL"])
    servicio.avisar_vencidos(s, ahora=AHORA)
    assert "• GGAL: ARS 7.500,50 (07/07)" in canal.enviados[0]
    s.close()
