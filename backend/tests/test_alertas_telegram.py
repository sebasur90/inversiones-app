"""Tests del canal de Telegram. La red está stubeada: nunca se le pega a la API real."""
import logging

import pytest

from app.services.notificaciones import telegram


@pytest.fixture(autouse=True)
def _configurado(monkeypatch):
    monkeypatch.setenv("ALERTAS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TOKEN-SECRETO")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99")


def _stub(monkeypatch, status, body=None, capturar=None):
    def falso(method, url, *, headers=None, data=None, timeout=None):
        if capturar is not None:
            capturar.update({"method": method, "url": url, "data": data})
        return status, body
    monkeypatch.setattr(telegram, "request_json", falso)


def test_envio_ok(monkeypatch):
    capturado = {}
    _stub(monkeypatch, 200, {"ok": True}, capturado)

    entregado, motivo = telegram.enviar("hola")

    assert (entregado, motivo) == (True, None)
    assert capturado["method"] == "POST"
    assert capturado["data"]["chat_id"] == "99"
    assert capturado["data"]["text"] == "hola"


def test_sin_token_no_envia(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    _stub(monkeypatch, 200, {"ok": True})

    entregado, motivo = telegram.enviar("hola")

    assert entregado is False
    assert "TELEGRAM_BOT_TOKEN" in motivo


def test_deshabilitado_no_envia(monkeypatch):
    monkeypatch.setenv("ALERTAS_ENABLED", "false")
    _stub(monkeypatch, 200, {"ok": True})

    entregado, motivo = telegram.enviar("hola")

    assert entregado is False
    assert "ALERTAS_ENABLED" in motivo


def test_mensaje_vacio_no_envia(monkeypatch):
    _stub(monkeypatch, 200, {"ok": True})
    assert telegram.enviar("   ")[0] is False


def test_error_de_telegram_devuelve_la_descripcion(monkeypatch):
    _stub(monkeypatch, 400, {"ok": False, "description": "chat not found"})

    entregado, motivo = telegram.enviar("hola")

    assert entregado is False
    assert "400" in motivo and "chat not found" in motivo


def test_sin_respuesta_no_lanza(monkeypatch):
    """Contrato del proyecto: una función de red nunca lanza."""
    _stub(monkeypatch, None, None)

    entregado, motivo = telegram.enviar("hola")

    assert entregado is False
    assert "no hubo respuesta" in motivo


def test_mensaje_largo_se_recorta(monkeypatch):
    """Telegram corta en 4096 y devuelve error; se recorta antes."""
    capturado = {}
    _stub(monkeypatch, 200, {"ok": True}, capturado)

    telegram.enviar("x" * 10_000)

    assert len(capturado["data"]["text"]) <= telegram._MAX_LARGO
    assert capturado["data"]["text"].endswith("…")


def test_el_token_nunca_aparece_en_los_logs(monkeypatch, caplog):
    """El token va en la URL de la API, así que tampoco se loguea la URL."""
    _stub(monkeypatch, 400, {"ok": False, "description": "bad request"})

    with caplog.at_level(logging.DEBUG):
        telegram.enviar("hola")

    assert "TOKEN-SECRETO" not in caplog.text


def test_configurado_refleja_las_variables(monkeypatch):
    assert telegram.configurado() is True
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    assert telegram.configurado() is False


# --- Formato HTML ------------------------------------------------------------------------------

def test_sin_parse_mode_el_payload_no_lo_incluye(monkeypatch):
    """El default deja el envío exactamente como era: un texto plano no tiene por qué pasar por
    el parser de Telegram y arriesgarse a un 400 por un `&` perdido."""
    capturado = {}
    _stub(monkeypatch, 200, {"ok": True}, capturado)

    telegram.enviar("hola")

    assert "parse_mode" not in capturado["data"]


def test_con_parse_mode_html_viaja_en_el_payload(monkeypatch):
    capturado = {}
    _stub(monkeypatch, 200, {"ok": True}, capturado)

    telegram.enviar("<b>hola</b>", parse_mode="HTML")

    assert capturado["data"]["parse_mode"] == "HTML"


def test_el_recorte_con_html_cae_en_un_salto_de_linea(monkeypatch):
    """Cortar a mitad de `<cod` no pierde un pedazo del mensaje: Telegram rechaza el mensaje
    entero con 400."""
    capturado = {}
    _stub(monkeypatch, 200, {"ok": True}, capturado)
    linea = "<b>ticker</b> · <code>USD 100,00</code>"
    largo = "\n".join([linea] * 300)
    assert len(largo) > telegram._MAX_LARGO

    telegram.enviar(largo, parse_mode="HTML")

    texto = capturado["data"]["text"]
    assert len(texto) <= telegram._MAX_LARGO
    assert capturado["data"]["parse_mode"] == "HTML"
    assert texto.count("<") == texto.count(">")
    assert texto.endswith(telegram._SUFIJO_RECORTE)


def test_un_texto_largo_sin_saltos_de_linea_se_manda_sin_formato(monkeypatch):
    """Caso patológico: no hay dónde cortar sin partir algo. Texto feo > aviso perdido."""
    capturado = {}
    _stub(monkeypatch, 200, {"ok": True}, capturado)

    telegram.enviar("<b>" + "x" * 5000 + "</b>", parse_mode="HTML")

    assert "parse_mode" not in capturado["data"]
    assert capturado["data"]["text"].endswith("…")


def test_un_400_por_formato_se_reintenta_en_texto_plano(monkeypatch):
    """Un bug de escapado tiene que degradar el aviso, no hacerlo desaparecer."""
    intentos = []

    def falso(method, url, *, headers=None, data=None, timeout=None):
        intentos.append(dict(data))
        if "parse_mode" in data:
            return 400, {"description": "Bad Request: can't parse entities"}
        return 200, {"ok": True}

    monkeypatch.setattr(telegram, "request_json", falso)

    entregado, motivo = telegram.enviar("<b>S&P</b>", parse_mode="HTML")

    assert (entregado, motivo) == (True, None)
    assert len(intentos) == 2
    assert "parse_mode" in intentos[0] and "parse_mode" not in intentos[1]


def test_un_400_que_no_es_de_formato_no_se_reintenta(monkeypatch):
    intentos = []

    def falso(method, url, *, headers=None, data=None, timeout=None):
        intentos.append(dict(data))
        return 400, {"description": "Bad Request: chat not found"}

    monkeypatch.setattr(telegram, "request_json", falso)

    entregado, motivo = telegram.enviar("<b>hola</b>", parse_mode="HTML")

    assert entregado is False
    assert "chat not found" in motivo
    assert len(intentos) == 1
