"""Motor puro de Descomposición de cartera: `familia_de` (clasificación derivada, sin DB) y
`construir_arbol` (árbol Familia → País → Sector → Ticker)."""
import pytest

from app.services.descomposicion_engine import SIN_CLASIFICAR, construir_arbol, familia_de


# ── familia_de ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo", ["Bono", "ON", "Letra", "LECAP", "Obligacion Negociable"])
def test_familia_de_renta_fija(tipo):
    assert familia_de(tipo, sector=None, con_ficha=True) == "Renta fija"


@pytest.mark.parametrize("tipo", ["CEDEAR", "Accion", "Acción"])
def test_familia_de_renta_variable(tipo):
    assert familia_de(tipo, sector=None, con_ficha=True) == "Renta variable"


def test_familia_de_fci_sin_sector_liquidez_es_fondos():
    assert familia_de("FCI", sector="Money Market", con_ficha=True) == "Fondos"


def test_familia_de_fci_con_sector_liquidez_gana_liquidez():
    """El caso decidido con el usuario: un FCI money market con Sector="Liquidez" en el Sheet
    cae en "Liquidez", no en "Fondos" — el dato explícito del Sheet manda sobre el tipo."""
    assert familia_de("FCI", sector="Liquidez", con_ficha=True) == "Liquidez"


def test_familia_de_sector_liquidez_mayusculas_y_espacios():
    assert familia_de("Bono", sector="  LIQUIDEZ  ", con_ficha=True) == "Liquidez"


def test_familia_de_tipo_desconocido_es_otros():
    assert familia_de("Futuro", sector=None, con_ficha=True) == "Otros"


def test_familia_de_sin_ficha_es_sin_clasificar():
    assert familia_de(None, None, con_ficha=False) == SIN_CLASIFICAR
    # Sin ficha gana sobre cualquier dato que pudiera venir (no debería, pero por las dudas).
    assert familia_de("Bono", "Liquidez", con_ficha=False) == SIN_CLASIFICAR


# ── construir_arbol ───────────────────────────────────────────────────────

def _pos(ticker, tipo, sector, pais, valor_usd, con_ficha=True, nombre=None):
    return {
        "ticker": ticker,
        "nombre": nombre or ticker,
        "tipo_instrumento": tipo,
        "sector": sector,
        "pais": pais,
        "con_ficha": con_ficha,
        "valor_usd": valor_usd,
        "valor_ars": valor_usd * 1000,
    }


def test_arbol_vacio_sin_posiciones():
    assert construir_arbol([], total_usd=0.0, total_ars=0.0) == []


def test_arbol_nivel1_orden_fijo_de_familias():
    posiciones = [
        _pos("XLE", "CEDEAR", "Energía", "AR", 100.0),
        _pos("TZXD7", "Bono", "Soberano", "AR", 50.0),
        _pos("FCI1", "FCI", "Liquidez", "AR", 30.0),
        _pos("MSFT", "CEDEAR", "Tecnologia", "AR", 200.0),
    ]
    total = sum(p["valor_usd"] for p in posiciones)
    arbol = construir_arbol(posiciones, total, total * 1000)

    etiquetas = [n["etiqueta"] for n in arbol]
    # Orden fijo Renta fija / Renta variable / Fondos / Liquidez, no por peso (que pondría
    # Renta variable primero con 300 de 380).
    assert etiquetas == ["Renta fija", "Renta variable", "Liquidez"]


def test_arbol_porcentajes_padre_suman_100_en_cada_nivel():
    posiciones = [
        _pos("XLE", "CEDEAR", "Energía", "AR", 100.0),
        _pos("AAPL", "CEDEAR", "Tecnologia", "AR", 150.0),
        _pos("MSFT", "CEDEAR", "Tecnologia", "AR", 50.0),
    ]
    total = sum(p["valor_usd"] for p in posiciones)
    arbol = construir_arbol(posiciones, total, total * 1000)

    assert len(arbol) == 1  # todo Renta variable
    renta_variable = arbol[0]
    assert renta_variable["porcentaje_padre"] == pytest.approx(100.0)

    paises = renta_variable["hijos"]
    assert sum(n["porcentaje_padre"] for n in paises) == pytest.approx(100.0)

    sectores = paises[0]["hijos"]
    assert sum(n["porcentaje_padre"] for n in sectores) == pytest.approx(100.0)

    # Sector Tecnología: 2 tickers, 200 de 300 -> 66.67% del padre (AR).
    tecnologia = next(s for s in sectores if s["etiqueta"] == "Tecnologia")
    assert tecnologia["porcentaje_padre"] == pytest.approx(200 / 300 * 100, abs=0.01)
    assert tecnologia["instrumentos"] == 2

    tickers = tecnologia["hijos"]
    assert {t["etiqueta"] for t in tickers} == {"AAPL", "MSFT"}
    assert all(t["hijos"] == [] for t in tickers)
    assert all(t["nivel"] == "Ticker" for t in tickers)


def test_arbol_porcentaje_total_estable_al_bajar_de_nivel():
    """`porcentaje` (a diferencia de `porcentaje_padre`) se mantiene contra el total de la
    cartera en cualquier nivel."""
    posiciones = [
        _pos("XLE", "CEDEAR", "Energía", "AR", 100.0),
        _pos("TZXD7", "Bono", "Soberano", "AR", 900.0),
    ]
    total = 1000.0
    arbol = construir_arbol(posiciones, total, total * 1000)

    renta_variable = next(n for n in arbol if n["etiqueta"] == "Renta variable")
    assert renta_variable["porcentaje"] == pytest.approx(10.0)
    # Un único hijo en cada nivel siguiente: el % contra el total no cambia.
    pais = renta_variable["hijos"][0]
    sector = pais["hijos"][0]
    ticker = sector["hijos"][0]
    assert pais["porcentaje"] == pytest.approx(10.0)
    assert sector["porcentaje"] == pytest.approx(10.0)
    assert ticker["porcentaje"] == pytest.approx(10.0)


def test_arbol_sin_sector_y_sin_pais_cae_en_sin_clasificar():
    posiciones = [
        _pos("AAA", "CEDEAR", sector=None, pais=None, valor_usd=100.0),
    ]
    arbol = construir_arbol(posiciones, 100.0, 100000.0)
    renta_variable = arbol[0]
    pais = renta_variable["hijos"][0]
    assert pais["etiqueta"] == SIN_CLASIFICAR
    assert pais["sin_clasificar"] is True
    sector = pais["hijos"][0]
    assert sector["etiqueta"] == SIN_CLASIFICAR
    assert sector["sin_clasificar"] is True


def test_arbol_bucket_sin_clasificar_siempre_al_final():
    posiciones = [
        _pos("AAA", "CEDEAR", "Tecnologia", "AR", 10.0),
        _pos("BBB", "CEDEAR", None, "AR", 500.0),  # pesa mucho más pero es "Sin clasificar"
    ]
    total = 510.0
    arbol = construir_arbol(posiciones, total, total * 1000)
    sectores = arbol[0]["hijos"][0]["hijos"]
    # BBB pesa mucho más (500 vs 10) pero al ser "Sin clasificar" va siempre al final.
    assert [s["etiqueta"] for s in sectores] == ["Tecnologia", SIN_CLASIFICAR]


def test_arbol_ticker_sin_ficha_va_a_sin_clasificar_con_metadata_vacia():
    posiciones = [
        _pos("ZZZ", tipo=None, sector=None, pais=None, valor_usd=50.0, con_ficha=False, nombre="ZZZ"),
    ]
    arbol = construir_arbol(posiciones, 50.0, 50000.0)
    assert arbol[0]["etiqueta"] == SIN_CLASIFICAR
    ticker = arbol[0]["hijos"][0]["hijos"][0]["hijos"][0]
    assert ticker["etiqueta"] == "ZZZ"
    assert ticker["nivel"] == "Ticker"


def test_arbol_instrumentos_cuenta_tickers_distintos():
    posiciones = [
        _pos("AAA", "CEDEAR", "Tecnologia", "AR", 10.0),
        _pos("BBB", "CEDEAR", "Tecnologia", "AR", 20.0),
        _pos("CCC", "CEDEAR", "Energía", "AR", 30.0),
    ]
    total = 60.0
    arbol = construir_arbol(posiciones, total, total * 1000)
    renta_variable = arbol[0]
    assert renta_variable["instrumentos"] == 3
    pais = renta_variable["hijos"][0]
    assert pais["instrumentos"] == 3
    tecnologia = next(s for s in pais["hijos"] if s["etiqueta"] == "Tecnologia")
    assert tecnologia["instrumentos"] == 2
