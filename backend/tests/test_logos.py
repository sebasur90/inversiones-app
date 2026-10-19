"""Logos de los emisores: validación de dominio e imagen, corrida con backoff, archivos en disco y
endpoint. Sin red: `logos._get_bytes` se reemplaza por un diccionario de URL → bytes."""
import hashlib
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, ClasificacionAuto, FundamentalesSnapshot, LogoEmpresa
from app.main import app
from app.services import logos

HOY = date.today()


def _png(ancho=128, alto=128, relleno=b"x"):
    """Un PNG mínimo: lo que mira el servicio es la firma y el IHDR, no los píxeles."""
    return logos._PNG + b"\x00\x00\x00\rIHDR" + ancho.to_bytes(4, "big") + alto.to_bytes(4, "big") + relleno * 40


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGOS_DIR", str(tmp_path / "logos"))
    monkeypatch.setenv("USE_EXTERNAL_APIS", "true")
    return tmp_path / "logos"


def _emisor(db, base, simbolo, website):
    db.add(ClasificacionAuto(ticker_base=base, simbolo_yahoo=simbolo, estado="ok", intentos_fallidos=0))
    db.add(FundamentalesSnapshot(simbolo_yahoo=simbolo, fecha=HOY, metricas={"website": website} if website else {}))
    db.commit()


@pytest.fixture
def web(monkeypatch):
    """Internet falsa: `web.sitio[url] = bytes`; registra los pedidos."""
    class Web:
        sitio: dict[str, bytes] = {}
        pedidos: list[str] = []

    w = Web()
    w.sitio, w.pedidos = {}, []

    def _get(url):
        w.pedidos.append(url)
        return w.sitio.get(url)

    monkeypatch.setattr(logos, "_get_bytes", _get)
    return w


# ── dominio ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("website,esperado", [
    ("https://www.ko.com", "ko.com"),
    ("http://www.coca-colacompany.com/about", "coca-colacompany.com"),
    ("microsoft.com", "microsoft.com"),
    ("HTTPS://Investor.Apple.COM/x?y=1", "investor.apple.com"),
    (None, None),
    ("", None),
    ("https://localhost", None),
    ("http://127.0.0.1", None),
    ("http://192.168.1.10/logo", None),
    ("https://ko.com:8080", None),
    ("https://user:clave@ko.com", None),
    ("https://sin-punto", None),
    ("https://ko .com", None),
    ("javascript:alert(1)", None),
])
def test_dominio_de(website, esperado):
    assert logos.dominio_de(website) == esperado


# ── imagen ───────────────────────────────────────────────────────────────────────────────────

def test_un_png_razonable_es_valido():
    assert logos.es_logo_valido(_png(128, 128))


@pytest.mark.parametrize("datos", [
    None, b"", b"<html>no hay logo</html>", b"GIF89a" + b"x" * 40,
    _png(16, 16),            # muy chico
    _png(4000, 4000),        # enorme
    _png(128, 128, b"y") + b"z" * (logos.MAX_BYTES + 1),   # pesa demasiado
])
def test_rechaza_lo_que_no_es_un_logo_usable(datos):
    assert not logos.es_logo_valido(datos)


def test_rechaza_el_icono_generico():
    generico = _png(128, 128, b"g")
    firma = {hashlib.sha1(generico).hexdigest()}
    assert not logos.es_logo_valido(generico, firma)
    assert logos.es_logo_valido(_png(128, 128, b"h"), firma)


# ── archivos ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("base", ["", "..", "../x", "a/b", "A\\B", ".oculto", "x" * 40, "ko", "K O"])
def test_ruta_rechaza_nombres_que_no_son_un_ticker_base(base, carpeta):
    carpeta.mkdir(parents=True)
    assert logos.ruta(base) is None


def test_ruta_devuelve_el_archivo_si_existe(carpeta):
    carpeta.mkdir(parents=True)
    (carpeta / "KO.png").write_bytes(_png())
    assert logos.ruta("KO") == str(carpeta / "KO.png")
    assert logos.ruta("PEP") is None


# ── corrida ──────────────────────────────────────────────────────────────────────────────────

def test_baja_el_logo_y_lo_guarda(db, web, carpeta):
    _emisor(db, "KO", "KO", "https://www.coca-colacompany.com")
    web.sitio["https://www.google.com/s2/favicons?domain=coca-colacompany.com&sz=128"] = _png()
    res = logos.correr(db)
    assert res == {"resultado": "ok", "intentados": 1, "ok": 1}
    assert (carpeta / "KO.png").read_bytes() == _png()
    fila = db.get(LogoEmpresa, "KO")
    assert fila.estado == "ok" and fila.dominio == "coca-colacompany.com"
    assert logos.con_logo(db) == {"KO"}


def test_prueba_el_apple_touch_icon_si_el_favicon_no_sirve(db, web, carpeta):
    _emisor(db, "KO", "KO", "https://ko.com")
    web.sitio["https://ko.com/apple-touch-icon.png"] = _png(180, 180)
    logos.correr(db)
    assert db.get(LogoEmpresa, "KO").estado == "ok"


def test_el_icono_generico_de_google_no_cuenta_como_logo(db, web):
    generico = _png(128, 128, b"g")
    web.sitio["https://www.google.com/s2/favicons?domain=dominio-que-no-existe-zzqx.com&sz=128"] = generico
    web.sitio["https://www.google.com/s2/favicons?domain=ko.com&sz=128"] = generico   # lo mismo para ko.com
    _emisor(db, "KO", "KO", "https://ko.com")
    logos.correr(db)
    assert db.get(LogoEmpresa, "KO").estado == "sin_logo"


def test_un_emisor_sin_logo_no_se_reintenta_hasta_el_plazo(db, web):
    _emisor(db, "KO", "KO", "https://ko.com")
    logos.correr(db)
    fila = db.get(LogoEmpresa, "KO")
    assert fila.estado == "sin_logo" and fila.intentos == 1
    assert fila.proximo_intento == HOY + timedelta(days=logos.SIN_LOGO_REINTENTO_DIAS)

    web.pedidos.clear()
    assert logos.correr(db)["intentados"] == 0 and web.pedidos == []

    fila.proximo_intento = HOY            # venció el plazo
    db.commit()
    web.sitio["https://www.google.com/s2/favicons?domain=ko.com&sz=128"] = _png()
    assert logos.correr(db)["ok"] == 1
    assert db.get(LogoEmpresa, "KO").estado == "ok"


def test_un_emisor_sin_website_no_se_intenta(db, web):
    _emisor(db, "KO", "KO", None)
    assert logos.correr(db)["intentados"] == 0
    assert web.pedidos == []


def test_un_website_raro_no_se_consulta(db, web):
    _emisor(db, "KO", "KO", "http://127.0.0.1:8080/logo")
    assert logos.correr(db)["intentados"] == 0
    assert web.pedidos == []


def test_respeta_el_tope_por_corrida_y_empieza_por_lo_nuevo(db, web):
    for base in ("AAA", "BBB", "CCC"):
        _emisor(db, base, base, f"https://{base.lower()}.com")
        web.sitio[f"https://www.google.com/s2/favicons?domain={base.lower()}.com&sz=128"] = _png()
    assert logos.correr(db, max_por_corrida=2)["intentados"] == 2
    assert logos.correr(db, max_por_corrida=2)["intentados"] == 1
    assert logos.con_logo(db) == {"AAA", "BBB", "CCC"}


def test_si_el_archivo_se_perdio_se_baja_de_nuevo(db, web, carpeta):
    _emisor(db, "KO", "KO", "https://ko.com")
    web.sitio["https://www.google.com/s2/favicons?domain=ko.com&sz=128"] = _png()
    logos.correr(db)
    (carpeta / "KO.png").unlink()
    assert logos.con_logo(db) == set()        # la fila dice ok pero no hay archivo: no se promete un logo
    logos.correr(db)
    assert logos.con_logo(db) == {"KO"}


def test_sin_fuentes_externas_no_hace_nada(db, web, monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_APIS", "false")
    _emisor(db, "KO", "KO", "https://ko.com")
    assert logos.correr(db)["resultado"] == "sin_fuentes"
    assert web.pedidos == []


# ── endpoint ─────────────────────────────────────────────────────────────────────────────────

def test_el_endpoint_sirve_el_logo_con_cache(carpeta):
    carpeta.mkdir(parents=True)
    (carpeta / "KO.png").write_bytes(_png())
    r = TestClient(app).get("/api/inversiones/logos/KO.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "max-age" in r.headers["cache-control"]
    assert r.content == _png()


@pytest.mark.parametrize("ruta", [
    "/api/inversiones/logos/PEP.png",           # no existe
    "/api/inversiones/logos/KO",                # sin extensión
    "/api/inversiones/logos/..%2F..%2Fdata.png",
    "/api/inversiones/logos/%2e%2e.png",
    "/api/inversiones/logos/ko.png",            # minúsculas: no es un ticker_base
])
def test_el_endpoint_responde_404_ante_lo_que_no_es_un_logo(ruta, carpeta):
    carpeta.mkdir(parents=True)
    (carpeta / "KO.png").write_bytes(_png())
    assert TestClient(app).get(ruta).status_code == 404
