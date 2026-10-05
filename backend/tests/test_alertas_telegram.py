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
