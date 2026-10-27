"""Calendario de eventos: normalización de URLs y textos, y detección de duplicados. Puro."""
from datetime import date, datetime

from app.services.eventos import normalizacion_engine as ne


def test_normalizar_url_saca_tracking_fragmento_y_www():
    a = ne.normalizar_url("HTTPS://www.Reuters.com/markets/fed-holds/?utm_source=x&b=2&a=1#arriba")
    b = ne.normalizar_url("http://reuters.com/markets/fed-holds?a=1&b=2&fbclid=zzz")
    assert a == b == "https://reuters.com/markets/fed-holds?a=1&b=2"


def test_normalizar_url_rechaza_esquemas_peligrosos_o_vacios():
    for url in ("javascript:alert(1)", "ftp://x.com/a", "", None, "no es una url", "https://"):
        assert ne.normalizar_url(url) is None
        assert not ne.url_valida(url)


def test_texto_plano_saca_html_y_corta():
    assert ne.texto_plano("<p>Hola <b>mundo</b> &amp; más</p>") == "Hola mundo & más"
    assert ne.texto_plano("<script>x</script>") == "x"
    assert ne.texto_plano("   ") is None
    largo = ne.texto_plano("a" * 50, maximo=10)
    assert len(largo) == 10 and largo.endswith("…")


def test_tokens_ignoran_stopwords_y_acentos():
    assert ne.tokens("La Reserva Federal subió las tasas") == {"reserva", "federal", "subio", "tasas"}
    assert ne.tokens("The Fed raises rates by 25 bps") == {"fed", "raises", "rates", "25", "bps"}


def test_parse_fecha_formatos_y_rango():
    assert ne.parse_fecha("2026-03-04T21:15:00Z") == datetime(2026, 3, 4, 21, 15)
    assert ne.parse_fecha("2026-03-04T18:15:00-03:00") == datetime(2026, 3, 4, 21, 15)
    assert ne.parse_fecha("20260304T211500Z") == datetime(2026, 3, 4, 21, 15)
    assert ne.parse_fecha("2026-03-04") == datetime(2026, 3, 4)
    assert ne.parse_fecha("3000-01-01") is None
    assert ne.parse_fecha("ayer") is None
    assert ne.parse_fecha(None) is None


def _n(**kw):
    base = {"proveedor": "marketaux", "id_externo": None, "url_normalizada": None, "tokens": frozenset(), "fecha": None}
    base.update(kw)
    if "titulo" in kw:
        base["tokens"] = ne.tokens(base.pop("titulo"))
    return base


def test_duplicadas_por_id_url_o_titulo_cercano():
    t0 = datetime(2026, 3, 4, 12)
    assert ne.son_duplicadas(_n(id_externo="1"), _n(id_externo="1"))
    assert not ne.son_duplicadas(_n(id_externo="1"), _n(id_externo="1", proveedor="gdelt"))
    assert ne.son_duplicadas(_n(url_normalizada="https://a.com/x"), _n(url_normalizada="https://a.com/x"))
    a = _n(titulo="Fed holds interest rates steady in March meeting", fecha=t0)
    b = _n(titulo="Fed holds rates steady at March meeting", fecha=datetime(2026, 3, 4, 20))
    assert ne.son_duplicadas(a, b)
    # Mismo título pero una semana después: es otra noticia (otra reunión).
    c = _n(titulo="Fed holds interest rates steady in March meeting", fecha=datetime(2026, 3, 12))
    assert not ne.son_duplicadas(a, c)


def test_agrupar_duplicados_es_transitivo():
    t = datetime(2026, 3, 4, 12)
    items = [
        _n(id_externo="a", titulo="Apple reports record quarterly revenue", fecha=t),
        _n(id_externo="b", titulo="Tesla recalls vehicles", fecha=t),
        _n(id_externo="c", url_normalizada="https://x.com/1", titulo="Apple reports record quarterly revenue iphone", fecha=t),
        _n(id_externo="d", url_normalizada="https://x.com/1", titulo="otro", fecha=t),
    ]
    assert ne.agrupar_duplicados(items) == [[0, 2, 3], [1]]


def test_evento_duplicado_misma_categoria_y_fecha_cercana():
    cand = {"categoria": "banco_central", "fecha": date(2026, 3, 18), "tokens": ne.tokens("Decisión de tasas de la Fed (FOMC)")}
    existentes = [
        {"id": 1, "categoria": "banco_central", "fecha": date(2026, 3, 18), "tokens": ne.tokens("Decisión de tasas FOMC de la Fed")},
        {"id": 2, "categoria": "dato_macro", "fecha": date(2026, 3, 18), "tokens": ne.tokens("Decisión de tasas de la Fed (FOMC)")},
        {"id": 3, "categoria": "banco_central", "fecha": date(2026, 4, 29), "tokens": ne.tokens("Decisión de tasas de la Fed (FOMC)")},
    ]
    assert ne.evento_duplicado(cand, existentes)["id"] == 1
    assert ne.evento_duplicado({**cand, "categoria": "elecciones"}, existentes) is None


def test_clave_dedup_estable():
    a = ne.clave_dedup("resultados", date(2026, 1, 29), "Apple: resultados del primer trimestre fiscal")
    b = ne.clave_dedup("resultados", date(2026, 1, 30), "Apple resultados primer trimestre fiscal")
    assert a == b
    assert a.startswith("resultados:2026-W05:")
