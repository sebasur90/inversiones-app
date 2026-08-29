"""Tests de `market_data.iol_auth` — autenticación OAuth y cupo mensual de IOL. Sin red: mockea
`request_json`. Ninguno de estos tests debe depender de un archivo de credenciales real."""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.services.market_data import iol_auth


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@pytest.fixture(autouse=True)
def _cache_limpio(monkeypatch):
    """`_cache` es un singleton a nivel de módulo: aislarlo entre tests."""
    monkeypatch.setattr(iol_auth, "_cache", iol_auth._TokenCache())
    monkeypatch.setattr(iol_auth, "_leer_credenciales", lambda: ("user", "pass"))


def _token_response(status=200, access="tok-123", refresh="ref-456", expires_in=900):
    body = {"access_token": access, "refresh_token": refresh, "expires_in": expires_in}
    return status, body


# --- cupo mensual -----------------------------------------------------------------------------

def test_cupo_disponible_por_default():
    db = _db()
    assert iol_auth.cupo_disponible(db) is True


def test_registrar_llamada_incrementa_y_persiste():
    db = _db()
    iol_auth.registrar_llamada(db)
    iol_auth.registrar_llamada(db)
    fila = db.get(iol_auth.EstadoApiIol, iol_auth._periodo_actual())
    assert fila.llamadas == 2


def test_cupo_agotado_no_llama_a_iol(monkeypatch):
    db = _db()
    monkeypatch.setenv("IOL_LIMITE_MENSUAL", "2")
    iol_auth.registrar_llamada(db)
    iol_auth.registrar_llamada(db)
    assert iol_auth.cupo_disponible(db) is False

    def _boom(*a, **kw):
        raise AssertionError("no debería llamar a la red con el cupo agotado")

    monkeypatch.setattr(iol_auth, "request_json", _boom)
    assert iol_auth.get_bearer(db) is None


def test_cupo_error_de_db_se_trata_como_agotado(monkeypatch):
    """Un error inesperado leyendo el contador (tabla no migrada, etc.) nunca debe habilitar
    llamadas sin control -- se trata como "sin cupo", no como "cupo libre"."""
    db = _db()

    def _boom(*a, **kw):
        raise RuntimeError("tabla no existe")

    monkeypatch.setattr(db, "get", _boom)
    assert iol_auth.cupo_disponible(db) is False


def test_registrar_llamada_usa_la_misma_sesion_sin_comitear(monkeypatch):
    """No debe abrir una sesión/conexión separada: en SQLite eso choca con el lock de escritura
    de una transacción larga como la del sync (bug real visto en producción). El conteo tiene
    que quedar pendiente en `db` -- visible dentro de esa misma sesión-- sin comitear por su
    cuenta."""
    db = _db()
    commits = []
    monkeypatch.setattr(db, "commit", lambda: commits.append(1))

    iol_auth.registrar_llamada(db)

    assert commits == []  # no comitea la sesión del llamador
    fila = db.get(iol_auth.EstadoApiIol, iol_auth._periodo_actual())
    assert fila is not None and fila.llamadas == 1  # pero sí es visible en esa misma sesión


# --- autenticación / cacheo de token -----------------------------------------------------------

def test_get_bearer_sin_credenciales_devuelve_none(monkeypatch):
    db = _db()
    monkeypatch.setattr(iol_auth, "_leer_credenciales", lambda: None)

    def _boom(*a, **kw):
        raise AssertionError("no debería llamar a la red sin credenciales")

    monkeypatch.setattr(iol_auth, "request_json", _boom)
    assert iol_auth.get_bearer(db) is None


def test_iol_deshabilitada_devuelve_none_sin_tocar_la_red(monkeypatch):
    db = _db()
    monkeypatch.setenv("IOL_ENABLED", "false")

    def _boom(*a, **kw):
        raise AssertionError("no debería llamar a la red con IOL_ENABLED=false")

    monkeypatch.setattr(iol_auth, "request_json", _boom)
    assert iol_auth.get_bearer(db) is None


def test_get_bearer_autentica_y_cachea(monkeypatch):
    db = _db()
    llamadas = []

    def _fake(method, url, **kw):
        llamadas.append((method, url, kw.get("data")))
        return _token_response()

    monkeypatch.setattr(iol_auth, "request_json", _fake)

    token1 = iol_auth.get_bearer(db)
    assert token1 == "tok-123"
    assert len(llamadas) == 1
    assert llamadas[0][2]["grant_type"] == "password"

    # Token cacheado y vigente: la segunda llamada no vuelve a pegarle a la red.
    token2 = iol_auth.get_bearer(db)
    assert token2 == "tok-123"
    assert len(llamadas) == 1

    fila = db.get(iol_auth.EstadoApiIol, iol_auth._periodo_actual())
    assert fila.llamadas == 1  # sólo la autenticación real cuenta, no el hit de caché


def test_get_bearer_expirado_usa_refresh_token(monkeypatch):
    db = _db()
    llamadas = []

    def _fake(method, url, **kw):
        llamadas.append(kw.get("data"))
        return _token_response(access="tok-nuevo")

    monkeypatch.setattr(iol_auth, "request_json", _fake)
    iol_auth.get_bearer(db)  # autenticación inicial

    # Forzar expiración.
    iol_auth._cache.expira_en = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = iol_auth.get_bearer(db)

    assert token == "tok-nuevo"
    assert len(llamadas) == 2
    assert llamadas[1]["grant_type"] == "refresh_token"
    assert llamadas[1]["refresh_token"] == "ref-456"


def test_refresh_fallido_reautentica_con_password(monkeypatch):
    db = _db()
    llamadas = []

    def _fake(method, url, **kw):
        data = kw.get("data")
        llamadas.append(data)
        if data.get("grant_type") == "refresh_token":
            return 401, None
        return _token_response(access="tok-reautenticado")

    monkeypatch.setattr(iol_auth, "request_json", _fake)
    iol_auth._cache.refresh_token = "ref-viejo"
    iol_auth._cache.expira_en = datetime.now(timezone.utc) - timedelta(seconds=1)
    iol_auth._cache.access_token = "tok-viejo"

    token = iol_auth.get_bearer(db)
    assert token == "tok-reautenticado"
    assert llamadas[0]["grant_type"] == "refresh_token"
    assert llamadas[1]["grant_type"] == "password"


# --- get_autenticado: cupo, conteo y reintento de 401 -------------------------------------------

def test_get_autenticado_feliz(monkeypatch):
    db = _db()
    monkeypatch.setattr(iol_auth, "request_json",
                         lambda m, u, **kw: _token_response() if u == iol_auth.TOKEN_URL else (200, {"ok": True}))
    body = iol_auth.get_autenticado(db, "https://api.invertironline.com/api/v2/algo")
    assert body == {"ok": True}


def test_get_autenticado_401_reintenta_una_vez(monkeypatch):
    db = _db()
    estados = {"n": 0}

    def _fake(method, url, **kw):
        if url == iol_auth.TOKEN_URL:
            return _token_response(access=f"tok-{estados['n']}")
        estados["n"] += 1
        if estados["n"] == 1:
            return 401, {"mensaje": "no autorizado"}
        return 200, {"ok": True}

    monkeypatch.setattr(iol_auth, "request_json", _fake)
    body = iol_auth.get_autenticado(db, "https://api.invertironline.com/api/v2/algo")
    assert body == {"ok": True}
    assert estados["n"] == 2  # un 401 y un reintento exitoso, no más


def test_get_autenticado_cupo_agotado_no_pega_a_la_red(monkeypatch):
    db = _db()
    monkeypatch.setenv("IOL_LIMITE_MENSUAL", "0")

    def _boom(*a, **kw):
        raise AssertionError("no debería llamar a la red con el cupo agotado")

    monkeypatch.setattr(iol_auth, "request_json", _boom)
    assert iol_auth.get_autenticado(db, "https://api.invertironline.com/api/v2/algo") is None


def test_get_autenticado_error_http_devuelve_none(monkeypatch):
    db = _db()

    def _fake(method, url, **kw):
        if url == iol_auth.TOKEN_URL:
            return _token_response()
        return 500, None

    monkeypatch.setattr(iol_auth, "request_json", _fake)
    assert iol_auth.get_autenticado(db, "https://api.invertironline.com/api/v2/algo") is None


# --- higiene de secretos: nunca en logs ---------------------------------------------------------

def test_ningun_log_expone_password_ni_token(monkeypatch, caplog):
    db = _db()
    monkeypatch.setattr(iol_auth, "_leer_credenciales", lambda: ("secreto_user", "secreto_pass_123"))

    def _fake(method, url, **kw):
        if kw.get("data", {}).get("grant_type") == "password":
            return 401, {"access_token": "no-deberia-verse-nunca", "error": "bad_credentials"}
        return 500, None

    monkeypatch.setattr(iol_auth, "request_json", _fake)

    with caplog.at_level(logging.DEBUG):
        assert iol_auth.get_bearer(db) is None

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "secreto_pass_123" not in texto
    assert "secreto_user" not in texto
    assert "no-deberia-verse-nunca" not in texto


def test_ningun_log_expone_el_bearer_vigente(monkeypatch, caplog):
    db = _db()
    monkeypatch.setattr(iol_auth, "request_json",
                         lambda m, u, **kw: _token_response(access="bearer-secreto-xyz"))
    with caplog.at_level(logging.DEBUG):
        token = iol_auth.get_bearer(db)
        # 401 fuerza un log de advertencia; nunca debe traer el token adentro.
        monkeypatch.setattr(iol_auth, "request_json", lambda m, u, **kw: (401, {"access_token": token}))
        iol_auth.get_autenticado(db, "https://api.invertironline.com/api/v2/algo")

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "bearer-secreto-xyz" not in texto
